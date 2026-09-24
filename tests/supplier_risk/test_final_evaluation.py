"""Synthetic checks for the single-use final evaluation boundary."""

import hashlib
import importlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def evaluation(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT))
    assert (ROOT / "ml/supplier_risk/scripts/final_evaluation.py").is_file()
    return importlib.import_module("ml.supplier_risk.scripts.final_evaluation")


def test_metric_values_are_hand_checked(evaluation):
    result = evaluation.classification_metrics([0, 0, 1, 1], [0, 1, 1, 1], [.1, .8, .6, .9])
    assert result["confusion_matrix"] == [[1, 1], [0, 2]]
    assert result["f1_macro"] == pytest.approx(11 / 15)
    assert result["balanced_accuracy"] == .75
    assert result["roc_auc"] == .75
    assert result["average_precision"] == pytest.approx(5 / 6)
    assert result["recall_0"] == .5
    assert result["recall_1"] == 1


@pytest.mark.parametrize("truth,prediction,probability", [
    ([1, 1], [1, 1], [.5, .5]),
    ([0, 1], [0], [.2, .8]),
    ([0, 1], [0, 2], [.2, .8]),
    ([0, 1], [0, 1], [.2, np.inf]),
    ([0, 1], [0, 1], [.2, 1.1]),
])
def test_invalid_metric_inputs_fail(evaluation, truth, prediction, probability):
    with pytest.raises(ValueError):
        evaluation.classification_metrics(truth, prediction, probability)


def test_development_reader_rejects_test_before_io(evaluation, tmp_path):
    with pytest.raises(ValueError, match="development"):
        evaluation.load_development_split(tmp_path, "test")


def test_traceability_rejects_duplicate_ids(evaluation):
    x = pd.DataFrame(1., index=range(2), columns=evaluation.FEATURES_A)
    y = pd.DataFrame({"risk_level": [0, 1]})
    with pytest.raises(ValueError, match="IDs"):
        evaluation.validate_xy(x, y, ["a", "a"], "a" * 64)


def test_traceability_rejects_misaligned_index(evaluation):
    x = pd.DataFrame(1., index=[1, 0], columns=evaluation.FEATURES_A)
    y = pd.DataFrame({"risk_level": [0, 1]})
    with pytest.raises(ValueError, match="index"):
        evaluation.validate_xy(x, y, ["a", "b"], "a" * 64)


@pytest.mark.parametrize("value", [np.nan, np.inf, "bad"])
def test_invalid_features_fail(evaluation, value):
    x = pd.DataFrame(1., index=range(2), columns=evaluation.FEATURES_A).astype(object)
    x.iloc[0, 0] = value
    y = pd.DataFrame({"risk_level": [0, 1]})
    with pytest.raises(ValueError):
        evaluation.validate_xy(x, y, ["a", "b"], "a" * 64)


def test_single_use_marker_survives_failed_or_repeated_execution(evaluation, tmp_path):
    freeze = tmp_path / "freeze.json"
    freeze.write_text('{"frozen":true}', encoding="utf-8")
    digest = hashlib.sha256(freeze.read_bytes()).hexdigest()
    evaluation.claim_test_access(freeze, digest)
    original = (tmp_path / "test_access_started.json").read_bytes()
    with pytest.raises(FileExistsError):
        evaluation.claim_test_access(freeze, digest)
    assert (tmp_path / "test_access_started.json").read_bytes() == original


def test_modified_freeze_cannot_open_test(evaluation, tmp_path):
    freeze = tmp_path / "freeze.json"
    freeze.write_text('{}', encoding="utf-8")
    with pytest.raises(ValueError, match="hash"):
        evaluation.claim_test_access(freeze, "0" * 64)
    assert not (tmp_path / "test_access_started.json").exists()


def test_bundle_promoted_only_after_manifest_verification(evaluation, tmp_path):
    staging = tmp_path / "pending"
    staging.mkdir()
    (staging / "record.json").write_text('{}', encoding="utf-8")
    digest = hashlib.sha256(b'{}').hexdigest()
    (staging / "manifest.json").write_text(json.dumps({"files": {"record.json": digest}}))
    destination = tmp_path / "published"
    evaluation.publish_bundle(staging, destination)
    assert (destination / "record.json").read_text() == '{}'
    assert not staging.exists()


def test_corrupt_bundle_never_published(evaluation, tmp_path):
    staging = tmp_path / "pending"
    staging.mkdir()
    (staging / "record.json").write_text('bad', encoding="utf-8")
    (staging / "manifest.json").write_text(json.dumps({"files": {"record.json": "0" * 64}}))
    with pytest.raises(ValueError, match="hash"):
        evaluation.publish_bundle(staging, tmp_path / "published")
    assert not (tmp_path / "published").exists()


def test_existing_bundle_never_overwritten(evaluation, tmp_path):
    destination = tmp_path / "published"
    destination.mkdir()
    with pytest.raises(FileExistsError):
        evaluation.publish_bundle(tmp_path / "pending", destination)


def test_fit_pipeline_preserves_fold_local_statistics(evaluation):
    x = pd.DataFrame({name: [1., 2., np.nan, 4., 5., 6.] for name in evaluation.FEATURES_C})
    fitted = evaluation.fit_candidate(x, np.array([0, 0, 0, 1, 1, 1]))
    assert fitted.named_steps["imputer"].statistics_.tolist() == [4.] * 9
    np.testing.assert_allclose(fitted.named_steps["scaler"].mean_, [22 / 6] * 9)
    assert fitted.named_steps["scaler"].n_samples_seen_ == 6
    assert fitted.n_features_in_ == 9


@pytest.fixture
def synthetic_case(evaluation, tmp_path, monkeypatch):
    root = tmp_path / "project"
    ml_ready = root / evaluation.ML_PATH
    ml_ready.mkdir(parents=True)
    assignments = []
    output_hashes = {}
    fingerprints = {}
    for split, count in (("train", 8), ("test", 4)):
        ids = [f"{split}-{i}" for i in range(count)]
        assignments.extend({"supplier_id": item, "split": split} for item in ids)
        fingerprints[split] = hashlib.sha256(json.dumps(ids, separators=(",", ":")).encode()).hexdigest()
        x = pd.DataFrame({name: np.arange(count, dtype=float) for name in evaluation.FEATURES_A})
        y = pd.DataFrame({"risk_level": np.array([0] * (count // 2) + [1] * (count // 2), dtype="int8")})
        for prefix, frame in (("X", x), ("y", y)):
            path = ml_ready / f"{prefix}_{split}.parquet"
            frame.to_parquet(path, index=False)
            output_hashes[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    pd.DataFrame(assignments).to_parquet(root / evaluation.SPLIT_PATH, index=False)
    metadata = {
        "hashes_saidas_sha256": output_hashes,
        "hashes_entradas_sha256": {evaluation.SPLIT_PATH.as_posix(): hashlib.sha256((root / evaluation.SPLIT_PATH).read_bytes()).hexdigest()},
        "hash_ordenacao_ids_sha256": fingerprints,
        "quantidade_registros_por_split": {"train": 8, "test": 4},
    }
    (ml_ready / "preprocessing_metadata.json").write_text(json.dumps(metadata))
    for relative in (
        "ml/supplier_risk/scripts/final_evaluation.py",
        "ml/supplier_risk/scripts/experiment_artifact.py",
        "ml/supplier_risk/notebooks/02_supplier_risk_baseline_models.ipynb",
        "docs/supplier_risk_model.md",
    ):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if relative.endswith(".py"):
            path.write_bytes((ROOT / relative).read_bytes())
        else:
            path.write_text("synthetic source")
    read_parquet = evaluation.read_verified_parquet
    observed = []
    run_dir = root / "run"

    def guarded_reader(path, expected, **kwargs):
        if Path(path).name in {"X_test.parquet", "y_test.parquet"}:
            assert (run_dir / "freeze.json").exists()
            assert (run_dir / "test_access_started.json").exists()
        observed.append(Path(path).name)
        return read_parquet(path, expected, **kwargs)

    monkeypatch.setattr(evaluation, "read_verified_parquet", guarded_reader)
    return root, run_dir, observed


def test_synthetic_end_to_end_freezes_before_test_and_never_retries(evaluation, synthetic_case):
    root, run_dir, observed = synthetic_case
    freeze = evaluation.freeze_configuration(root, run_dir)
    digest = hashlib.sha256(freeze.read_bytes()).hexdigest()
    assert not {"X_test.parquet", "y_test.parquet"} & set(observed)
    metrics = evaluation.run_final_evaluation(root, freeze, expected_freeze_sha256=digest)
    assert set(metrics) == {"LogisticRegression_C", "Baseline_majoritaria"}
    assert observed.count("X_test.parquet") == observed.count("y_test.parquet") == 1
    record = evaluation.evidence.verify_final_evaluation_record(run_dir / "results/LogisticRegression_C.json")
    assert record["payload"]["record_count"] == 4
    assert (run_dir / "results/manifest.json").is_file()
    reads_before_retry = len(observed)
    with pytest.raises(FileExistsError):
        evaluation.run_final_evaluation(root, freeze, expected_freeze_sha256=digest)
    assert len(observed) == reads_before_retry
    assert not (run_dir / "failure.json").exists()


@pytest.mark.parametrize("field,value", [
    ("threshold", .8), ("refit_train_validation", True),
    ("train_split", "validation"), ("calibration", "sigmoid"),
    ("protocol_version", "unapproved"), ("estimator", "RandomForestClassifier"),
])
def test_changed_freeze_rejected_even_with_new_digest(evaluation, synthetic_case, field, value):
    root, run_dir, observed = synthetic_case
    freeze = evaluation.freeze_configuration(root, run_dir)
    contents = json.loads(freeze.read_text())
    contents[field] = value
    freeze.write_text(json.dumps(contents))
    before = len(observed)
    with pytest.raises(ValueError, match="Frozen"):
        evaluation.run_final_evaluation(root, freeze, expected_freeze_sha256=evaluation.sha256(freeze))
    assert len(observed) == before
    assert not (run_dir / "test_access_started.json").exists()


def test_file_change_during_parse_is_rejected(evaluation, tmp_path, monkeypatch):
    path = tmp_path / "synthetic.parquet"
    pd.DataFrame({"x": [1]}).to_parquet(path)
    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    read_parquet = pd.read_parquet

    def mutate_after_verified_read(buffer, **kwargs):
        frame = read_parquet(buffer, **kwargs)
        pd.DataFrame({"x": [999]}).to_parquet(path)
        return frame

    monkeypatch.setattr(pd, "read_parquet", mutate_after_verified_read)
    with pytest.raises(ValueError, match="hash"):
        evaluation.read_verified_parquet(path, expected)


def test_rejects_modified_freeze_against_external_anchor(evaluation, synthetic_case):
    root, run_dir, observed = synthetic_case
    freeze = evaluation.freeze_configuration(root, run_dir)
    digest = evaluation.sha256(freeze)
    freeze.write_text(freeze.read_text() + " ")
    before = len(observed)
    with pytest.raises(ValueError, match="hash"):
        evaluation.run_final_evaluation(root, freeze, expected_freeze_sha256=digest)
    assert len(observed) == before


def test_fit_failure_is_locked_before_any_test_access(evaluation, synthetic_case, monkeypatch):
    root, run_dir, observed = synthetic_case
    freeze = evaluation.freeze_configuration(root, run_dir)
    digest = evaluation.sha256(freeze)

    def failed_fit(x, y):
        assert (run_dir / "execution_started.json").exists()
        raise RuntimeError("injected training failure")

    monkeypatch.setattr(evaluation, "fit_candidate", failed_fit)
    with pytest.raises(RuntimeError, match="injected"):
        evaluation.run_final_evaluation(root, freeze, expected_freeze_sha256=digest)
    with pytest.raises(FileExistsError):
        evaluation.run_final_evaluation(root, freeze, expected_freeze_sha256=digest)
    assert "X_test.parquet" not in observed
    assert not (run_dir / "test_access_started.json").exists()
    failure = json.loads((run_dir / "failure.json").read_text())
    assert failure["phase"] == "before_test_access"
    assert failure["exception_type"] == "RuntimeError"


def test_freeze_refuses_different_runtime_code(evaluation, synthetic_case):
    root, run_dir, _ = synthetic_case
    (root / "ml/supplier_risk/scripts/final_evaluation.py").write_text("different implementation")
    with pytest.raises(ValueError, match="code"):
        evaluation.freeze_configuration(root, run_dir)
    assert not run_dir.exists()
