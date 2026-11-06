"""Offline artifact tests: synthetic bytes/estimators, never a real fit."""

import copy
import hashlib
import importlib
import importlib.util
import io
import json
import socket

import joblib
import numpy as np
import pytest
from sklearn.ensemble import IsolationForest


def test_module_contract_exists():
    assert importlib.util.find_spec("ml.procurement_v2.artifact") is not None


class SimulatedEstimator:
    def score_samples(self, frame):
        return -np.asarray(frame.iloc[:, 0], dtype=float) / 10


@pytest.fixture
def artifact(monkeypatch, tmp_path):
    module = importlib.import_module("ml.procurement_v2.artifact")
    monkeypatch.setattr(module, "_ARTIFACT_DIR", tmp_path / "baseline_v1")
    monkeypatch.setattr(module, "TRUSTED_MODEL_SHA256", None)
    monkeypatch.setattr(module, "TRUSTED_METADATA_SHA256", None)

    def forbidden(*args, **kwargs):
        raise AssertionError("network and real fits are forbidden")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(IsolationForest, "fit", forbidden)
    return module


@pytest.fixture
def metadata(artifact):
    return {
        "artifact_contract": artifact.ARTIFACT_CONTRACT,
        "artifact_id": artifact.ARTIFACT_ID,
        "domain": "procurement_v2",
        "experiment": artifact.BASELINE_VERSION,
        "feature_contract": artifact.FEATURE_CONTRACT,
        "batch_contract": artifact.BATCH_CONTRACT,
        "feature_names": list(artifact.FEATURE_NAMES),
        "source": {"source_id": "procurement-spend", "source_version": artifact.CSV_SHA256,
                   "entity_namespace": "procurement-spend-synthetic", "origin": "synthetic",
                   "monetary_unit": "unspecified_source_unit",
                   "temporal_assumption": "available_at_order_no_revisions"},
        "source_path": "data/external/procurement_spend/purchase_orders.csv",
        "training": {"period": "development", "start": "2023-04-01", "end_exclusive": "2025-01-01",
                     "rows": 23671, "features": 5, "matrix_sha256": artifact.MATRIX_SHA256},
        "parameters": dict(artifact.PARAMETERS),
        "versions": dict(artifact.EXPECTED_VERSIONS),
        "score_convention": "-score_samples", "score_semantics": "statistical_anomaly",
        "preprocessing": "none", "operational_threshold": None,
        "verification": {"fit_calls": 1, "rtol": 0, "atol": 0,
                         "historical_statistics_match": True, "fixed_references_match": True},
        "limitations": ["Synthetic data; no certified fraud labels.", "Currency unidentified."],
    }


@pytest.fixture
def simulated(artifact, monkeypatch):
    monkeypatch.setattr(artifact, "_validate_estimator", lambda model: None)
    return SimulatedEstimator()


def persist(artifact, metadata, simulated):
    return artifact.persist_baseline(simulated, metadata, reference_values=[[1., 1., .2, 20., 200.]],
                                     reference_scores=[.1])


def trust(artifact, monkeypatch, result):
    monkeypatch.setattr(artifact, "TRUSTED_MODEL_SHA256", result["model_sha256"])
    monkeypatch.setattr(artifact, "TRUSTED_METADATA_SHA256", result["metadata_sha256"])


def test_persistence_roundtrip_scores_and_explicit_trust(artifact, metadata, simulated, monkeypatch):
    original = copy.deepcopy(metadata)
    result = persist(artifact, metadata, simulated)
    assert metadata == original
    with pytest.raises(artifact.ArtifactError, match="trust_not_configured"):
        artifact.load_baseline()
    trust(artifact, monkeypatch, result)
    loaded = artifact.load_baseline()
    assert loaded.score([2., 1., .2, 10., 100.], feature_names=artifact.FEATURE_NAMES) == .2
    assert loaded.score([2., 1., .2, 10., 100.], feature_names=artifact.FEATURE_NAMES) == .2
    assert loaded.model_sha256 == result["model_sha256"]
    assert loaded.artifact_id == artifact.ARTIFACT_ID
    assert {p.name for p in artifact._ARTIFACT_DIR.iterdir()} == {"model.joblib", "metadata.json", "model.sha256"}
    assert hashlib.sha256((artifact._ARTIFACT_DIR / "model.joblib").read_bytes()).hexdigest() == result["model_sha256"]


def test_no_overwrite_or_implicit_cleanup(artifact, metadata, simulated):
    persist(artifact, metadata, simulated)
    before = {p.name: p.read_bytes() for p in artifact._ARTIFACT_DIR.iterdir()}
    with pytest.raises(artifact.ArtifactError, match="artifact_exists"):
        persist(artifact, metadata, simulated)
    assert before == {p.name: p.read_bytes() for p in artifact._ARTIFACT_DIR.iterdir()}


@pytest.mark.parametrize("target", ["model.joblib", "metadata.json"])
def test_tampering_refused_before_deserialization(artifact, metadata, simulated, monkeypatch, target):
    result = persist(artifact, metadata, simulated)
    trust(artifact, monkeypatch, result)
    path = artifact._ARTIFACT_DIR / target
    path.write_bytes(path.read_bytes() + b"tampered")

    def forbidden(payload):
        raise AssertionError("must refuse before deserialization")

    monkeypatch.setattr(artifact, "_deserialize", forbidden)
    with pytest.raises(artifact.ArtifactError, match="hash_mismatch"):
        artifact.load_baseline()


def test_sidecar_is_not_a_trust_anchor(artifact, metadata, simulated, monkeypatch):
    result = persist(artifact, metadata, simulated)
    trust(artifact, monkeypatch, result)
    payload = b"arbitrary untrusted pickle"
    (artifact._ARTIFACT_DIR / "model.joblib").write_bytes(payload)
    (artifact._ARTIFACT_DIR / "model.sha256").write_text(hashlib.sha256(payload).hexdigest(), encoding="utf-8")
    with pytest.raises(artifact.ArtifactError, match="hash_mismatch"):
        artifact.load_baseline()


@pytest.mark.parametrize("field,value", [
    ("domain", "invoice_v1"), ("artifact_id", "invoice-demo/1.0"),
    ("feature_names", [f"invoice_{i}" for i in range(19)]),
    ("score_convention", "predict_proba"), ("score_semantics", "fraud_probability"),
    ("operational_threshold", .5), ("preprocessing", "scaler"),
])
def test_wrong_contract_cannot_be_persisted(artifact, metadata, simulated, field, value):
    metadata[field] = value
    with pytest.raises(artifact.ArtifactError):
        persist(artifact, metadata, simulated)
    assert not artifact._ARTIFACT_DIR.exists()


@pytest.mark.parametrize("fault", ["features", "versions", "parameters", "source", "matrix", "verification"])
def test_invalid_metadata_refused_before_load_even_with_test_pin(artifact, metadata, simulated, monkeypatch, fault):
    result = persist(artifact, metadata, simulated)
    path = artifact._ARTIFACT_DIR / "metadata.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    if fault == "features":
        document["feature_names"].reverse()
    elif fault == "versions":
        document["versions"]["scikit-learn"] = "0.0"
    elif fault == "parameters":
        document["parameters"]["n_estimators"] = 100
    elif fault == "source":
        document["source"]["origin"] = "real"
    elif fault == "matrix":
        document["training"]["matrix_sha256"] = "0" * 64
    else:
        document["verification"]["fit_calls"] = 2
    path.write_text(json.dumps(document), encoding="utf-8")
    result["metadata_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    trust(artifact, monkeypatch, result)

    def forbidden(payload):
        raise AssertionError("invalid metadata reached deserialization")

    monkeypatch.setattr(artifact, "_deserialize", forbidden)
    with pytest.raises(artifact.ArtifactError):
        artifact.load_baseline()


def test_incompatible_runtime_refused_before_load(artifact, metadata, simulated, monkeypatch):
    result = persist(artifact, metadata, simulated)
    trust(artifact, monkeypatch, result)
    monkeypatch.setattr(artifact, "_runtime_versions", lambda: {**artifact.EXPECTED_VERSIONS, "numpy": "0.0"})
    monkeypatch.setattr(artifact, "_deserialize", lambda _: pytest.fail("must not deserialize"))
    with pytest.raises(artifact.ArtifactError, match="runtime_versions"):
        artifact.load_baseline()


@pytest.mark.parametrize("values", [[], [1] * 4, [1] * 6, [True, 1, 1, 1, 1], ["1", 1, 1, 1, 1],
                                    [None, 1, 1, 1, 1], [float("nan"), 1, 1, 1, 1],
                                    [float("inf"), 1, 1, 1, 1], [1e100, 1, 1, 1, 1],
                                    [10**1000, 1, 1, 1, 1], [[1], 1, 1, 1, 1],
                                    [0, 1, 1, 1, 1], [1, -1, 1, 1, 1], [1, 1, -1, 1, 1],
                                    [1, 1, 1, -1, 1], [1, 1, 1, 1.5, 1]])
def test_invalid_inputs_rejected(artifact, metadata, simulated, monkeypatch, values):
    result = persist(artifact, metadata, simulated)
    trust(artifact, monkeypatch, result)
    with pytest.raises(artifact.ArtifactError, match="feature_values"):
        artifact.load_baseline().score(values, feature_names=artifact.FEATURE_NAMES)


def test_feature_order_and_arbitrary_paths_rejected(artifact, metadata, simulated, monkeypatch):
    result = persist(artifact, metadata, simulated)
    trust(artifact, monkeypatch, result)
    with pytest.raises(TypeError):
        artifact.load_baseline("ml/models/isolation_forest.joblib")
    with pytest.raises(artifact.ArtifactError, match="feature_order"):
        artifact.load_baseline().score([1] * 5, feature_names=artifact.FEATURE_NAMES[::-1])


@pytest.mark.parametrize("output", [[float("nan")], [float("inf")], [], [.1, .2], [[.1]]])
def test_invalid_output_rejected(artifact, metadata, simulated, monkeypatch, output):
    result = persist(artifact, metadata, simulated)
    trust(artifact, monkeypatch, result)
    monkeypatch.setattr(SimulatedEstimator, "score_samples", lambda self, frame: output)
    with pytest.raises(artifact.ArtifactError, match="scoring_output"):
        artifact.load_baseline().score([1] * 5, feature_names=artifact.FEATURE_NAMES)


def test_reference_divergence_prevents_persistence(artifact, metadata, simulated):
    with pytest.raises(artifact.ArtifactError, match="reference_scores"):
        artifact.persist_baseline(simulated, metadata, reference_values=[[1] * 5], reference_scores=[.9])
    assert not artifact._ARTIFACT_DIR.exists()


def test_serialization_divergence_prevents_persistence(artifact, metadata, simulated, monkeypatch):
    class WrongEstimator:
        def score_samples(self, frame):
            return np.full(len(frame), -.9)

    monkeypatch.setattr(artifact, "_deserialize", lambda _: WrongEstimator())
    with pytest.raises(artifact.ArtifactError, match="roundtrip_scores"):
        persist(artifact, metadata, simulated)
    assert not artifact._ARTIFACT_DIR.exists()


def test_deserialization_errors_are_sanitized(artifact, metadata, simulated, monkeypatch):
    result = persist(artifact, metadata, simulated)
    trust(artifact, monkeypatch, result)

    def broken(stream):
        raise RuntimeError("sensitive arbitrary driver detail")

    monkeypatch.setattr(joblib, "load", broken)
    with pytest.raises(artifact.ArtifactError, match="deserialization") as error:
        artifact.load_baseline()
    assert "sensitive" not in str(error.value)


def test_loaded_bytes_are_the_bytes_hashed(artifact, metadata, simulated, monkeypatch):
    result = persist(artifact, metadata, simulated)
    trust(artifact, monkeypatch, result)
    original = artifact._deserialize

    def replace_after_read(payload):
        (artifact._ARTIFACT_DIR / "model.joblib").write_bytes(b"changed after integrity check")
        return original(payload)

    monkeypatch.setattr(artifact, "_deserialize", replace_after_read)
    assert artifact.load_baseline().score([1] * 5, feature_names=artifact.FEATURE_NAMES) == .1


def test_estimator_type_and_unfitted_state_rejected(artifact):
    with pytest.raises(artifact.ArtifactError, match="estimator_type"):
        artifact._validate_estimator(SimulatedEstimator())
    with pytest.raises(artifact.ArtifactError, match="estimator_unfitted"):
        artifact._validate_estimator(IsolationForest(**artifact.PARAMETERS))


@pytest.mark.parametrize("fault", ["width", "names", "params", "trees", "offset", "samples"])
def test_estimator_fitted_contract_rejected(artifact, fault):
    model = IsolationForest(**artifact.PARAMETERS)
    model.n_features_in_ = 5
    model.feature_names_in_ = np.array(artifact.FEATURE_NAMES)
    model.estimators_ = [None] * 200
    model.estimators_features_ = [np.arange(5)] * 200
    model.max_samples_ = 256
    model.offset_ = -.5
    if fault == "width":
        model.n_features_in_ = 19
    elif fault == "names":
        model.feature_names_in_ = model.feature_names_in_[::-1]
    elif fault == "params":
        model.set_params(random_state=7)
    elif fault == "trees":
        model.estimators_ = []
    elif fault == "offset":
        model.offset_ = -.2
    else:
        model.max_samples_ = 100
    with pytest.raises(artifact.ArtifactError):
        artifact._validate_estimator(model)


def test_import_has_no_model_loading_or_training():
    from unittest.mock import patch

    with patch.object(joblib, "load", side_effect=AssertionError("import must not load")), \
            patch.object(IsolationForest, "fit", side_effect=AssertionError("import must not fit")):
        importlib.reload(importlib.import_module("ml.procurement_v2.artifact"))


def test_serialization_uses_only_in_memory_buffer(artifact, metadata, simulated, monkeypatch):
    original = joblib.dump

    def dump(model, target, **kwargs):
        assert isinstance(target, io.BytesIO)
        return original(model, target, **kwargs)

    monkeypatch.setattr(joblib, "dump", dump)
    persist(artifact, metadata, simulated)


def test_serialization_is_deterministic_without_another_fit(artifact, metadata, simulated, monkeypatch):
    first = persist(artifact, metadata, simulated)
    monkeypatch.setattr(artifact, "_ARTIFACT_DIR", artifact._ARTIFACT_DIR.with_name("second_synthetic_bundle"))
    assert persist(artifact, metadata, simulated) == first


def test_wrong_deserialized_type_rejected_after_integrity_checks(artifact, metadata, monkeypatch):
    with monkeypatch.context() as context:
        context.setattr(artifact, "_validate_estimator", lambda model: None)
        result = persist(artifact, metadata, SimulatedEstimator())
    trust(artifact, monkeypatch, result)
    with pytest.raises(artifact.ArtifactError, match="estimator_type"):
        artifact.load_baseline()


@pytest.mark.parametrize("fault", ["missing", "size", "json", "path"])
def test_file_boundary_refusals(artifact, metadata, simulated, monkeypatch, fault):
    result = persist(artifact, metadata, simulated)
    trust(artifact, monkeypatch, result)
    if fault == "missing":
        (artifact._ARTIFACT_DIR / "model.joblib").unlink()
        code = "artifact_unavailable"
    elif fault == "size":
        monkeypatch.setattr(artifact, "_MODEL_LIMIT", 1)
        code = "artifact_size"
    elif fault == "json":
        payload = b"not JSON"
        (artifact._ARTIFACT_DIR / "metadata.json").write_bytes(payload)
        monkeypatch.setattr(artifact, "TRUSTED_METADATA_SHA256", hashlib.sha256(payload).hexdigest())
        code = "metadata_json"
    else:
        monkeypatch.setattr(artifact, "_ARTIFACT_DIR", artifact._ARTIFACT_DIR / ".." / "baseline_v1")
        code = "artifact_path"
    monkeypatch.setattr(artifact, "_deserialize", lambda _: pytest.fail("must not deserialize"))
    with pytest.raises(artifact.ArtifactError, match=code):
        artifact.load_baseline()
