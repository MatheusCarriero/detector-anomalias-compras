"""Synthetic-only executor contracts; never open project data or saved models."""

import copy
import hashlib
import importlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import IsolationForest

from ml.scripts.treinar_modelo import FEATURES

ROOT = Path(__file__).resolve().parents[2]
PARAMETERS = {
    "n_estimators": 200, "contamination": 0.22, "random_state": 42,
    "n_jobs": -1, "max_samples": "auto", "max_features": 1.0,
    "bootstrap": False, "warm_start": False, "verbose": 0,
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, allow_nan=False), encoding="utf-8")


@pytest.fixture
def api():
    return importlib.import_module("ml.scripts.invoice_final_evaluation")


@pytest.fixture(scope="module")
def fitted_synthetic_model():
    # This fit is test-fixture preparation only, never an executor operation.
    numbers = np.random.default_rng(721).normal(size=(32, 19))
    return IsolationForest(**PARAMETERS).fit(pd.DataFrame(numbers, columns=FEATURES))


@pytest.fixture
def model(fitted_synthetic_model):
    return copy.deepcopy(fitted_synthetic_model)


def hand_frame():
    frame = pd.DataFrame(np.zeros((100, 19)), columns=FEATURES)
    frame["invoice_amount"] = np.arange(100., 0., -1)
    frame.insert(0, "fraud_type", ["A" if i in {0, 1, 2} else "B" if i in {5, 6, 7}
                                 else "NONE" for i in range(100)])
    frame.insert(0, "is_fraud", [int(i in {0, 1, 2, 5, 6, 7, 20}) for i in range(100)])
    frame.insert(0, "split", "synthetic_holdout")
    frame.insert(0, "invoice_id", [f"synthetic-{i:03}" for i in range(100)])
    order = [0, *range(5, 14)] + [i for i in range(100) if i != 0 and i not in range(5, 14)]
    scores = np.empty(100)
    scores[order] = np.arange(100., 0., -1)
    return frame, scores


@pytest.fixture
def fixture_files(tmp_path, model):
    assert not tmp_path.resolve().is_relative_to(ROOT.resolve())
    source = tmp_path / "synthetic-fixtures"
    source.mkdir()
    frame, _ = hand_frame()
    dev = pd.DataFrame({"invoice_id": ["synthetic-train", "synthetic-val"],
                        "split": ["train", "val"]})
    frame.to_parquet(source / "holdout.parquet", index=False)
    dev.to_parquet(source / "development_ids.parquet", index=False)
    pd.concat([dev, frame[["invoice_id", "split"]]], ignore_index=True).to_parquet(
        source / "splits.parquet", index=False)
    frame[["invoice_id", "is_fraud", "fraud_type"]].to_parquet(source / "labels.parquet", index=False)
    frame[["invoice_id", "invoice_amount"]].assign(currency="SYN").to_parquet(
        source / "amounts.parquet", index=False)
    joblib.dump(model, source / "model.joblib")
    write_json(source / "model_metadata.json", {
        "algorithm": "IsolationForest", "feature_count": 19, "features": FEATURES,
        "parameters": PARAMETERS, "offset": float(model.offset_),
    })
    return source, tmp_path / "synthetic-run"


def freeze(api, fixture_files, model):
    source, run_dir = fixture_files
    return api.freeze_configuration(source, run_dir, api.configuration_contract(float(model.offset_)))


def execute(api, freeze_path):
    return api.run_synthetic_evaluation(freeze_path, expected_freeze_sha256=digest(freeze_path))


def forbid_training(*args, **kwargs):
    raise AssertionError("Executor must not fit, predict, or call decision_function")


def test_configuration_contract_requires_explicit_synthetic_scope():
    from ml.scripts.invoice_final_evaluation import configuration_contract

    configuration = configuration_contract(-0.5)
    assert configuration["mode"] == "synthetic_only"
    assert configuration["test_authorized"] is False
    assert configuration["split"] == "synthetic_holdout"
    assert configuration["legacy_offset"] == -0.5


def test_manual_global_selection_matrices_and_paired_counts(api, model, monkeypatch):
    frame, scores = hand_frame()
    calls = []

    def score_once(self, features):
        calls.append(features.copy())
        return -scores

    monkeypatch.setattr(IsolationForest, "score_samples", score_once)
    for method in ("fit", "predict", "decision_function"):
        monkeypatch.setattr(IsolationForest, method, forbid_training)
    before = joblib.hash(model)
    result = api.evaluate_frame(model, frame, api.configuration_contract(float(model.offset_)))
    assert joblib.hash(model) == before
    assert len(calls) == 1
    assert list(calls[0].columns) == FEATURES
    assert [row["k"] for row in result["comparisons"]] == [1, 5, 10]
    five = result["comparisons"][1]
    assert five["gross_additional_if_positives"] == 3
    assert five["value_positives_forgone"] == 2
    assert five["net_additional_positives"] == 1
    assert five["jaccard"] == pytest.approx(1 / 9)
    diagnostics = result["selection_diagnostics"]
    assert diagnostics["isolation_forest"][1]["confusion_matrix"] == [[92, 1], [3, 4]]
    assert diagnostics["invoice_value"][1]["confusion_matrix"] == [[91, 2], [4, 3]]
    a = diagnostics["isolation_forest"][1]["by_fraud_type"]["A"]
    assert a["count"] == a["known_positives"] == 3
    assert a["selected"] == a["true_positive"] == 1
    assert a["false_negative"] == 2
    assert a["false_positive"] == a["true_negative"] == 0
    assert a["recall_reference"] == pytest.approx(1 / 3)
    assert a["false_positive_rate"] is None
    assert a["precision_selected"] == 1
    assert a["confusion_matrix"] == [[0, 0], [2, 1]]


@pytest.mark.parametrize("label", [0, 1])
def test_zero_class_denominators_and_missing_type(api, model, monkeypatch, label):
    frame, _ = hand_frame()
    frame = frame.iloc[:3].assign(is_fraud=label, fraud_type=None)
    monkeypatch.setattr(IsolationForest, "score_samples", lambda self, features: -np.ones(len(features)))
    result = api.evaluate_frame(model, frame, api.configuration_contract(float(model.offset_)))
    for entry in result["selection_diagnostics"]["isolation_forest"]:
        group = entry["by_fraud_type"]["__missing__"]
        assert group["selected"] == 1
        assert group["recall_reference"] == (None if label == 0 else pytest.approx(1 / 3))
        assert group["false_positive_rate"] == (None if label == 1 else pytest.approx(1 / 3))
        assert entry["confusion_matrix"] == ([[2, 1], [0, 0]] if label == 0 else [[0, 0], [2, 1]])


def test_tie_breaking_is_id_based_and_amounts_are_signed(api, model, monkeypatch):
    frame, _ = hand_frame()
    frame["invoice_amount"] = -100.
    frame.loc[99, "invoice_amount"] = -1.
    monkeypatch.setattr(IsolationForest, "score_samples", lambda self, features: -np.ones(len(features)))
    config = api.configuration_contract(float(model.offset_))
    first = api.evaluate_frame(model, frame, config)
    assert first == api.evaluate_frame(model, frame.iloc[::-1], config)
    assert first["isolation_forest"]["budgets"][0]["known_positives"] == 1
    assert first["invoice_value"]["budgets"][0]["known_positives"] == 0
    assert first["isolation_forest"]["budgets"][0]["boundary_tie_count"] == 100


@pytest.mark.parametrize("fault", ["empty", "feature_order", "extra", "missing", "duplicate_id",
    "null_id", "bad_label", "bool_label", "real_test", "nan", "inf", "bool_feature", "text_feature",
    "reserved_type"])
def test_frame_contract_rejected_before_scoring(api, model, monkeypatch, fault):
    frame, _ = hand_frame()
    if fault == "empty":
        frame = frame.iloc[:0]
    elif fault == "feature_order":
        columns = list(frame.columns)
        columns[-1], columns[-2] = columns[-2], columns[-1]
        frame = frame[columns]
    elif fault == "extra":
        frame["extra"] = 1
    elif fault == "missing":
        frame = frame.drop(columns=FEATURES[-1])
    elif fault == "duplicate_id":
        frame.loc[1, "invoice_id"] = frame.loc[0, "invoice_id"]
    elif fault == "null_id":
        frame.loc[0, "invoice_id"] = None
    elif fault == "bad_label":
        frame.loc[0, "is_fraud"] = 2
    elif fault == "bool_label":
        frame["is_fraud"] = True
    elif fault == "real_test":
        frame["split"] = "test"
    elif fault in ("nan", "inf"):
        frame.loc[0, FEATURES[-1]] = np.nan if fault == "nan" else np.inf
    elif fault == "bool_feature":
        frame[FEATURES[-1]] = False
    elif fault == "text_feature":
        frame[FEATURES[-1]] = "0"
    else:
        frame.loc[0, "fraud_type"] = "__missing__"
    monkeypatch.setattr(IsolationForest, "score_samples", forbid_training)
    with pytest.raises((ValueError, TypeError)):
        api.evaluate_frame(model, frame, api.configuration_contract(float(model.offset_)))


@pytest.mark.parametrize("fault", ["parameter", "bool_parameter", "offset", "n_features", "not_fitted"])
def test_invalid_model_rejected_before_scoring(api, model, monkeypatch, fault):
    configuration = api.configuration_contract(float(model.offset_))
    if fault == "parameter":
        model.set_params(n_estimators=201)
    elif fault == "bool_parameter":
        model.set_params(verbose=False)
    elif fault == "offset":
        model.offset_ += 0.1
    elif fault == "n_features":
        model.n_features_in_ = 18
    else:
        model = IsolationForest(**PARAMETERS)
    monkeypatch.setattr(IsolationForest, "score_samples", forbid_training)
    with pytest.raises((ValueError, TypeError)):
        api.evaluate_frame(model, hand_frame()[0], configuration)


def test_scoring_must_not_mutate_fitted_state(api, model, monkeypatch):
    config = api.configuration_contract(float(model.offset_))

    def mutating_score(self, features):
        self.offset_ += 0.1
        return -np.ones(len(features))

    monkeypatch.setattr(IsolationForest, "score_samples", mutating_score)
    with pytest.raises(ValueError):
        api.evaluate_frame(model, hand_frame()[0], config)


def test_lifecycle_hashes_uppercase_no_fit_and_no_overwrite(api, fixture_files, model, monkeypatch):
    for method in ("fit", "predict", "decision_function"):
        monkeypatch.setattr(IsolationForest, method, forbid_training)
    path = freeze(api, fixture_files, model)
    frozen = api.load_frozen_configuration(path, digest(path).upper())
    assert frozen["configuration"]["test_authorized"] is False
    source, run_dir = fixture_files
    assert set(frozen["pre_access_sha256"]) == {"model.joblib", "model_metadata.json", "development_ids.parquet"}
    assert not (run_dir / "execution_started.json").exists()
    results = api.run_synthetic_evaluation(path, expected_freeze_sha256=digest(path).upper())
    evidence = api.verify_bundle(results, expected_manifest_sha256=digest(results / "manifest.json").upper(),
                                 expected_freeze_sha256=digest(path).upper())
    assert evidence["schema"] == "invoice-synthetic-evidence/1.0"
    assert evidence["synthetic"] is True
    assert evidence["scientific_evidence"] is False
    assert evidence["test_used"] is False
    assert evidence["model_fits_in_executor"] == 0
    assert evidence["freeze_sha256"] == digest(path)
    assert evidence["configuration"] == frozen["configuration"]
    assert evidence["metrics"]["isolation_forest"]["rows"] == 100
    assert all(value == digest(source / name) for name, value in evidence["input_hashes_sha256"].items())
    assert len(evidence["ids_sha256"]) == 64
    assert (run_dir / "execution_started.json").exists()
    before = (results / "evidence.json").read_bytes()
    with pytest.raises((FileExistsError, ValueError)):
        execute(api, path)
    with pytest.raises((FileExistsError, ValueError)):
        freeze(api, fixture_files, model)
    assert (results / "evidence.json").read_bytes() == before


def test_holdout_bytes_unopened_until_claim(api, fixture_files, model, monkeypatch):
    source, run_dir = fixture_files
    original = Path.open
    holdout_files = {source / name for name in ("holdout.parquet", "splits.parquet", "labels.parquet", "amounts.parquet")}

    def guarded(self, *args, **kwargs):
        if self in holdout_files:
            assert (run_dir / "execution_started.json").exists(), "Holdout read before persisted claim"
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded)
    path = freeze(api, fixture_files, model)
    execute(api, path)


@pytest.mark.parametrize("fault", ["dev_overlap", "dev_missing_val", "split_test", "split_missing",
    "label_changed", "label_missing", "label_duplicate", "amount_changed", "amount_missing",
    "mixed_currency", "null_currency", "metadata_features", "metadata_offset"])
def test_source_contract_failure_never_publishes(api, fixture_files, model, fault):
    source, run_dir = fixture_files
    filename = ("development_ids.parquet" if fault.startswith("dev_") else "splits.parquet"
                if fault.startswith("split_") else "labels.parquet" if fault.startswith("label_")
                else "model_metadata.json" if fault.startswith("metadata_") else "amounts.parquet")
    target = source / filename
    if fault.startswith("metadata_"):
        value = json.loads(target.read_text(encoding="utf-8"))
        if fault == "metadata_features":
            value["features"] = FEATURES[::-1]
        else:
            value["offset"] += 0.1
        write_json(target, value)
    else:
        value = pd.read_parquet(target)
        if fault == "dev_overlap":
            value.loc[0, "invoice_id"] = "synthetic-000"
        elif fault == "dev_missing_val":
            value["split"] = "train"
        elif fault == "split_test":
            value.loc[2, "split"] = "test"
        elif fault.endswith("missing"):
            value = value.iloc[1:]
        elif fault == "label_changed":
            value.loc[0, "is_fraud"] = 0
        elif fault == "label_duplicate":
            value = pd.concat([value, value.iloc[:1]], ignore_index=True)
        elif fault == "amount_changed":
            value.loc[0, "invoice_amount"] += 100
        elif fault == "mixed_currency":
            value.loc[0, "currency"] = "OTHER"
        else:
            value.loc[0, "currency"] = None
        value.to_parquet(target, index=False)
    with pytest.raises((ValueError, TypeError)):
        execute(api, freeze(api, fixture_files, model))
    assert not (run_dir / "results").exists()


@pytest.mark.parametrize("filename", ["model.joblib", "model_metadata.json", "development_ids.parquet"])
def test_frozen_preaccess_input_tamper_is_detected(api, fixture_files, model, filename):
    path = freeze(api, fixture_files, model)
    source, run_dir = fixture_files
    target = source / filename
    target.write_bytes(target.read_bytes() + b"tampered")
    with pytest.raises(ValueError):
        execute(api, path)
    assert not (run_dir / "results").exists()


@pytest.mark.parametrize("fault", ["split", "mode", "authorized", "features", "budgets", "bool_budget", "parameter"])
def test_invalid_configuration_rejected_before_creating_run(api, fixture_files, model, fault):
    configuration = api.configuration_contract(float(model.offset_))
    if fault == "parameter":
        configuration["parameters"]["n_estimators"] = 199
    else:
        key, value = {"split": ("split", "test"), "mode": ("mode", "real"),
                      "authorized": ("test_authorized", True), "features": ("features", FEATURES[::-1]),
                      "budgets": ("budget_percentages", [10]),
                      "bool_budget": ("budget_percentages", [True, 5, 10])}[fault]
        configuration[key] = value
    with pytest.raises((ValueError, TypeError)):
        api.freeze_configuration(*fixture_files, configuration)
    assert not fixture_files[1].exists()


@pytest.mark.parametrize("offset", [float("nan"), float("inf"), True, "-0.5"])
def test_nonfinite_or_coerced_offset_rejected(api, offset):
    with pytest.raises((ValueError, TypeError)):
        api.configuration_contract(offset)


@pytest.mark.parametrize("configuration", [None, [], "synthetic_only"])
def test_configuration_must_be_mapping_before_io(api, fixture_files, configuration):
    with pytest.raises(TypeError):
        api.freeze_configuration(*fixture_files, configuration)
    assert not fixture_files[1].exists()


@pytest.mark.parametrize("fault", ["bad_digest", "bad_schema", "duplicate_json_key"])
def test_frozen_record_validation(api, fixture_files, model, fault):
    path = freeze(api, fixture_files, model)
    expected = digest(path)
    if fault == "bad_digest":
        expected = "0" * 64
    elif fault == "bad_schema":
        record = json.loads(path.read_text(encoding="utf-8"))
        record["schema"] = "unknown"
        write_json(path, record)
        expected = digest(path)
    else:
        text = path.read_text(encoding="utf-8")
        path.write_text('{"schema":"invalid",' + text.lstrip()[1:], encoding="utf-8")
        expected = digest(path)
    with pytest.raises(ValueError):
        api.load_frozen_configuration(path, expected)


def test_failed_scoring_persists_claim_and_blocks_retry(api, fixture_files, model, monkeypatch):
    path = freeze(api, fixture_files, model)

    def fail_score(*args, **kwargs):
        raise RuntimeError("synthetic scoring interruption")

    monkeypatch.setattr(IsolationForest, "score_samples", fail_score)
    with pytest.raises(RuntimeError, match="synthetic scoring interruption"):
        execute(api, path)
    run_dir = fixture_files[1]
    assert (run_dir / "execution_started.json").exists()
    assert (run_dir / "failure.json").exists()
    assert not (run_dir / "results").exists()
    with pytest.raises((FileExistsError, ValueError)):
        execute(api, path)


@pytest.mark.parametrize("artifact", ["evidence.json", "manifest.json"])
def test_published_artifact_tamper_rejected(api, fixture_files, model, artifact):
    path = freeze(api, fixture_files, model)
    results = execute(api, path)
    expected_manifest = digest(results / "manifest.json")
    target = results / artifact
    target.write_bytes(target.read_bytes() + b" ")
    with pytest.raises(ValueError):
        api.verify_bundle(results, expected_manifest_sha256=expected_manifest,
                          expected_freeze_sha256=digest(path))


def test_real_project_path_rejected_without_opening_it(api, tmp_path, monkeypatch):
    original = Path.open

    def guarded(self, *args, **kwargs):
        if self.resolve().is_relative_to(ROOT / "data") or self.resolve().is_relative_to(ROOT / "ml/models"):
            raise AssertionError("Real project data/model path was opened")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded)
    with pytest.raises(ValueError):
        api.freeze_configuration(ROOT / "data", tmp_path / "run", api.configuration_contract(-0.5))
    assert not (tmp_path / "run").exists()


def test_output_inside_project_rejected_before_creation(api, fixture_files, model):
    with pytest.raises(ValueError):
        api.freeze_configuration(fixture_files[0], ROOT / "ml/experiments/synthetic-forbidden",
                                 api.configuration_contract(float(model.offset_)))
    assert not (ROOT / "ml/experiments/synthetic-forbidden").exists()


def test_interrupted_publication_preserves_pending_and_consumes_attempt(api, fixture_files, model, monkeypatch):
    path = freeze(api, fixture_files, model)
    original = Path.rename

    def interrupt_publish(self, target):
        if self.name == "results.pending":
            raise OSError("synthetic publication interruption")
        return original(self, target)

    monkeypatch.setattr(Path, "rename", interrupt_publish)
    with pytest.raises(OSError, match="synthetic publication interruption"):
        execute(api, path)
    run_dir = fixture_files[1]
    assert (run_dir / "results.pending/evidence.json").is_file()
    assert (run_dir / "results.pending/manifest.json").is_file()
    assert (run_dir / "execution_started.json").is_file()
    assert (run_dir / "failure.json").is_file()
    assert not (run_dir / "results").exists()
    with pytest.raises((FileExistsError, ValueError)):
        execute(api, path)


def test_input_change_during_scoring_aborts_publication(api, fixture_files, model, monkeypatch):
    path = freeze(api, fixture_files, model)
    target = fixture_files[0] / "holdout.parquet"

    def score_and_change_input(self, features):
        target.write_bytes(target.read_bytes() + b"changed after read")
        return -np.ones(len(features))

    monkeypatch.setattr(IsolationForest, "score_samples", score_and_change_input)
    with pytest.raises(ValueError):
        execute(api, path)
    assert (fixture_files[1] / "failure.json").is_file()
    assert not (fixture_files[1] / "results").exists()


@pytest.mark.parametrize("fault", ["source_hash", "runtime_version"])
def test_frozen_runtime_and_source_identity_rejected_before_holdout(api, fixture_files, model, monkeypatch, fault):
    path = freeze(api, fixture_files, model)
    value = json.loads(path.read_text(encoding="utf-8"))
    if fault == "source_hash":
        value["source_sha256"]["ml/scripts/invoice_final_evaluation.py"] = "0" * 64
    else:
        value["versions"]["python"] = "0.0.0"
    write_json(path, value)
    original = Path.open

    def no_holdout(self, *args, **kwargs):
        if self == fixture_files[0] / "holdout.parquet":
            raise AssertionError("Holdout read despite changed source/runtime identity")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", no_holdout)
    with pytest.raises(ValueError):
        execute(api, path)
    assert not (fixture_files[1] / "results").exists()


def test_symlink_escape_rejected_before_target_read(api, fixture_files, model, tmp_path, monkeypatch):
    root = tmp_path / "escaped-fixtures"
    root.mkdir()
    target = fixture_files[0] / "model.joblib"
    try:
        (root / "model.joblib").symlink_to(target)
    except OSError:
        pytest.skip("Creating symlinks requires Windows privilege on this host")
    original = Path.open

    def no_target_read(self, *args, **kwargs):
        if self == target:
            raise AssertionError("Escaped symlink target was read")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", no_target_read)
    with pytest.raises(ValueError):
        api.freeze_configuration(root, tmp_path / "escape-run", api.configuration_contract(float(model.offset_)))
    assert not (tmp_path / "escape-run").exists()


def test_copied_freeze_cannot_bypass_consumed_attempt(api, fixture_files, model, tmp_path, monkeypatch):
    path = freeze(api, fixture_files, model)
    execute(api, path)
    copied_dir = tmp_path / "copied-run"
    copied_dir.mkdir()
    copied = copied_dir / "freeze.json"
    copied.write_bytes(path.read_bytes())
    assert digest(copied) == digest(path)
    original = Path.open

    def no_second_holdout(self, *args, **kwargs):
        if self == fixture_files[0] / "holdout.parquet":
            raise AssertionError("Copied freeze bypassed original attempt claim")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", no_second_holdout)
    with pytest.raises(ValueError):
        execute(api, copied)
    assert not (copied_dir / "execution_started.json").exists()
    assert not (copied_dir / "results").exists()
