"""Inference orchestration with synthetic inputs and a simulated loaded model."""

import copy
import importlib
import math
import socket
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ml.procurement_v2 import demo
from ml.procurement_v2.batch import MATRIX_FEATURES


def request():
    return {"contract": demo.CONTRACT_VERSION, "source_sha256": demo.SOURCE_SHA256,
            "operation": {"po_id": "PO-2025-27239", "order_date": "2025-01-23", "occurrence": 1}}


@pytest.fixture(autouse=True)
def no_external_access(monkeypatch):
    from pathlib import Path

    import joblib
    from sklearn.ensemble import IsolationForest

    def forbidden(*args, **kwargs):
        raise AssertionError("No real source, model load, fit, predict, network or writes in unit tests")
    for name in ("fit", "fit_predict", "predict", "score_samples"):
        monkeypatch.setattr(IsolationForest, name, forbidden)
    monkeypatch.setattr(joblib, "load", forbidden)
    monkeypatch.setattr(joblib, "dump", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(Path, "open", forbidden)


@pytest.fixture
def setup(monkeypatch):
    module = importlib.import_module("ml.procurement_v2.demo_inference")
    prepared = {"contract": demo.CONTRACT_VERSION, "source": demo.source_identity(),
                "operation": request()["operation"], "status": "eligible",
                "feature_names": list(MATRIX_FEATURES), "values": [1., 1., 0., 3, 20],
                "unavailability": {}}
    monkeypatch.setattr(demo, "prepare_operation", Mock(return_value=prepared))
    class Error(ValueError):
        pass
    loaded = SimpleNamespace(artifact_id="synthetic-test-model", model_sha256="a" * 64,
                             score=Mock(return_value=0.25))
    api = SimpleNamespace(ArtifactError=Error, ARTIFACT_ID=loaded.artifact_id,
                          TRUSTED_MODEL_SHA256=loaded.model_sha256,
                          TRUSTED_METADATA_SHA256="b" * 64,
                          load_baseline=Mock(return_value=loaded))
    monkeypatch.setattr(module, "_artifact", Mock(return_value=api))
    return module, prepared, api, loaded


def test_one_official_score_call_preserves_identity_features_and_provenance(setup):
    module, prepared, api, model = setup
    req = request(); before = copy.deepcopy((req, prepared))
    result = module.run_operation(req)
    assert result == {"contract": "procurement-demo-inference/1.0", "status": "scored",
                      "preparation": prepared, "anomaly_score": .25,
                      "score_convention": "-score_samples", "score_semantics": "statistical_anomaly",
                      "score_direction": "higher_is_more_anomalous",
                      "model": {"domain": "procurement_v2", "artifact_id": model.artifact_id,
                                "model_sha256": "a" * 64, "metadata_sha256": "b" * 64}}
    api.load_baseline.assert_called_once_with()
    model.score.assert_called_once_with([1., 1., 0., 3, 20], feature_names=list(MATRIX_FEATURES))
    assert (req, prepared) == before
    assert module.run_operation(req) == result


def test_unavailable_never_imports_or_loads_artifact(setup):
    module, prepared, api, _ = setup
    prepared.update(status="unavailable", values=None,
                    unavailability={MATRIX_FEATURES[0]: "insufficient_history"})
    module._artifact.side_effect = AssertionError("must not import model dependencies")
    result = module.run_operation(request())
    assert result["status"] == "unavailable" and result["anomaly_score"] is None
    assert result["model"] is None and result["preparation"] == prepared
    api.load_baseline.assert_not_called()


@pytest.mark.parametrize("fault", ["order", "width", "nonfinite", "bool", "identity", "status", "null", "reasons"])
def test_bad_preparation_refused_before_model_load(setup, fault):
    module, prepared, api, _ = setup
    if fault == "order": prepared["feature_names"].reverse()
    elif fault == "width": prepared["values"].pop()
    elif fault == "nonfinite": prepared["values"][0] = math.inf
    elif fault == "bool": prepared["values"][0] = True
    elif fault == "identity": prepared["operation"] = {**prepared["operation"], "occurrence": 2}
    elif fault == "status": prepared["status"] = "scored"
    elif fault == "null": prepared["values"] = None
    else: prepared["unavailability"] = {MATRIX_FEATURES[0]: "insufficient_history"}
    with pytest.raises(module.InferenceError, match="PREPARATION_INVALID"):
        module.run_operation(request())
    api.load_baseline.assert_not_called()


def test_invalid_request_refused_before_preparation(setup):
    module, _, api, _ = setup
    with pytest.raises(demo.DemoValidationError):
        module.run_operation({**request(), "model_path": "untrusted"})
    demo.prepare_operation.assert_not_called()
    api.load_baseline.assert_not_called()


@pytest.mark.parametrize("reason,code", [
    ("artifact_unavailable", "MODEL_UNAVAILABLE"), ("hash_mismatch", "MODEL_INTEGRITY"),
    ("implementation_hash", "MODEL_INCOMPATIBLE"), ("runtime_versions", "MODEL_INCOMPATIBLE"),
    ("estimator_contract", "MODEL_INCOMPATIBLE"), ("deserialization", "MODEL_LOAD_FAILED"),
])
def test_loader_failures_sanitized_without_retry(setup, reason, code):
    module, _, api, model = setup
    api.load_baseline.side_effect = api.ArtifactError(reason)
    with pytest.raises(module.InferenceError, match=f"^{code}$"):
        module.run_operation(request())
    api.load_baseline.assert_called_once_with()
    model.score.assert_not_called()


@pytest.mark.parametrize("score", [math.nan, math.inf, -math.inf, True, [], "secret"])
def test_invalid_score_never_returned(setup, score):
    module, _, _, model = setup
    model.score.return_value = score
    with pytest.raises(module.InferenceError, match="INVALID_SCORE"):
        module.run_operation(request())


def test_wrong_model_identity_or_score_failure(setup):
    module, _, api, model = setup
    model.artifact_id = "invoice"
    with pytest.raises(module.InferenceError, match="MODEL_INCOMPATIBLE"):
        module.run_operation(request())
    model.score.assert_not_called()
    model.artifact_id = api.ARTIFACT_ID
    model.score.side_effect = api.ArtifactError("scoring_output")
    with pytest.raises(module.InferenceError, match="INVALID_SCORE"):
        module.run_operation(request())


def test_public_p514_wrapper_uses_score_samples_once_and_negates_once(setup, monkeypatch):
    from ml.procurement_v2 import artifact

    module, prepared, _, _ = setup
    calls = []
    class SimulatedEstimator:
        def score_samples(self, frame):
            calls.append(frame.copy())
            return [-.375]
    loaded = artifact._FrozenBaseline(SimulatedEstimator(), artifact.TRUSTED_MODEL_SHA256)
    loader = Mock(return_value=loaded)
    monkeypatch.setattr(artifact, "load_baseline", loader)
    monkeypatch.setattr(module, "_artifact", lambda: artifact)
    result = module.run_operation(request())
    loader.assert_called_once_with()
    assert result["anomaly_score"] == .375
    assert len(calls) == 1
    assert list(calls[0].columns) == list(MATRIX_FEATURES)
    assert calls[0].values.tolist() == [prepared["values"]]
