"""Synthetic adapter/executor handoff; development rows never become holdout.

Legacy adapter metadata and exact executor metadata are deliberately different
contracts. Only these test fixtures construct both representations.
"""

import hashlib
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import IsolationForest

from ml.scripts import invoice_data_adapter as adapter
from ml.scripts import invoice_final_evaluation as executor
from ml.scripts.treinar_modelo import FEATURES

ROOT = Path(__file__).resolve().parents[2]
PARAMETERS = {
    "n_estimators": 200, "contamination": 0.22, "random_state": 42,
    "n_jobs": -1, "max_samples": "auto", "max_features": 1.0,
    "bootstrap": False, "warm_start": False, "verbose": 0,
}
ADAPTER_INPUTS = (
    "data/processed/train_features.parquet", "data/processed/val_features.parquet",
    "ml/models/isolation_forest.joblib", "ml/models/model_metadata.json",
)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, allow_nan=False), encoding="utf-8")


def forbidden_operation(*args, **kwargs):
    raise AssertionError("No fitting or unauthorized scoring during handoff")


def assert_fitted_state_preserved(actual, expected):
    # Array values, unlike a whole-object joblib hash, survive serialization.
    assert actual.offset_ == expected.offset_
    assert len(actual.estimators_) == len(expected.estimators_) == 200
    for actual_tree, expected_tree in zip(actual.estimators_, expected.estimators_):
        actual_state, expected_state = actual_tree.tree_.__getstate__(), expected_tree.tree_.__getstate__()
        assert actual_state["max_depth"] == expected_state["max_depth"]
        assert actual_state["node_count"] == expected_state["node_count"]
        np.testing.assert_array_equal(actual_state["nodes"], expected_state["nodes"])
        np.testing.assert_array_equal(actual_state["values"], expected_state["values"])
    np.testing.assert_array_equal(actual.estimators_features_, expected.estimators_features_)


@pytest.fixture(autouse=True)
def forbid_real_inputs(monkeypatch):
    original_open, original_parquet, original_load = Path.open, pd.read_parquet, joblib.load

    def check_path(value):
        if isinstance(value, (str, Path)):
            path = Path(value).resolve()
            assert not path.is_relative_to(ROOT / "data"), "Real project data accessed"
            assert not path.is_relative_to(ROOT / "ml/models"), "Real saved model accessed"
            assert path.suffix != ".ipynb", "Notebook accessed"

    def checked_open(path, *args, **kwargs):
        check_path(path)
        return original_open(path, *args, **kwargs)

    def checked_parquet(path, *args, **kwargs):
        check_path(path)
        return original_parquet(path, *args, **kwargs)

    def checked_load(path, *args, **kwargs):
        check_path(path)
        return original_load(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", checked_open)
    monkeypatch.setattr(pd, "read_parquet", checked_parquet)
    monkeypatch.setattr(joblib, "load", checked_load)


@pytest.fixture(scope="module")
def synthetic_frames():
    frames = {}
    # Separate generators create every cohort from scratch, with disjoint IDs.
    for split, count, seed in (("train", 32, 1307), ("val", 16, 2411),
                               ("synthetic_holdout", 100, 3571)):
        values = np.random.default_rng(seed).uniform(0.1, 5.0, (count, 19))
        frame = pd.DataFrame(values, columns=FEATURES)
        frame["invoice_amount"] *= np.where(np.arange(count) % 3 == 0, -100, 100)
        frame.insert(0, "fraud_type", ["synthetic_amount" if i % 4 == 0 else None
                                       for i in range(count)])
        frame.insert(0, "is_fraud", (np.arange(count) % 4 == 0).astype(np.int64))
        frame.insert(0, "split", split)
        frame.insert(0, "invoice_id", [f"integration-{split}-{i:03}" for i in range(count)])
        frames[split] = frame
    return frames


@pytest.fixture(scope="module")
def fitted_synthetic_model(synthetic_frames):
    # The only fit: preparation on synthetic TRAIN, before either public API.
    return IsolationForest(**PARAMETERS).fit(synthetic_frames["train"][FEATURES])


@pytest.fixture
def development_files(tmp_path, synthetic_frames, fitted_synthetic_model):
    assert not tmp_path.resolve().is_relative_to(ROOT)
    root = tmp_path / "synthetic-development"
    (root / "data/processed").mkdir(parents=True)
    (root / "ml/models").mkdir(parents=True)
    for split in ("train", "val"):
        synthetic_frames[split].iloc[::-1].to_parquet(
            root / f"data/processed/{split}_features.parquet", index=False)
    joblib.dump(fitted_synthetic_model, root / ADAPTER_INPUTS[2])
    write_json(root / ADAPTER_INPUTS[3], {
        "algorithm": "IsolationForest", "feature_count": 19, "features": FEATURES,
        "n_estimators": 200, "contamination": 0.22, "random_state": 42,
        "training_date": "2000-01-01T00:00:00",
    })
    # No shared raw files exist: the production-safe adapter must not need them.
    return root


def adapt_development(root, model, monkeypatch):
    hashes = {name: digest(root / name) for name in ADAPTER_INPUTS}
    with monkeypatch.context() as phase:
        for operation in ("fit", "predict", "decision_function", "score_samples"):
            phase.setattr(IsolationForest, operation, forbidden_operation)
        return {split: adapter.load_development_data(
            root, split=split, expected_hashes=hashes, expected_offset=float(model.offset_)
        ) for split in ("train", "val")}


def executor_fixture(tmp_path, adapted, holdout):
    """Test-only fixture creation, never a production metadata converter."""
    root = tmp_path / "synthetic-executor"
    root.mkdir()
    development_ids = pd.concat([
        adapted[split].frame[["invoice_id", "split"]] for split in ("train", "val")
    ], ignore_index=True)
    development_ids.to_parquet(root / "development_ids.parquet", index=False)
    holdout.to_parquet(root / "holdout.parquet", index=False)
    pd.concat([development_ids, holdout[["invoice_id", "split"]]], ignore_index=True).to_parquet(
        root / "splits.parquet", index=False)
    holdout[["invoice_id", "is_fraud", "fraud_type"]].iloc[::-1].to_parquet(
        root / "labels.parquet", index=False)
    holdout[["invoice_id", "invoice_amount"]].assign(currency="SYN").iloc[::-1].to_parquet(
        root / "amounts.parquet", index=False)
    model = adapted["train"].model
    joblib.dump(model, root / "model.joblib")
    write_json(root / "model_metadata.json", {
        "algorithm": "IsolationForest", "feature_count": int(model.n_features_in_),
        "features": model.feature_names_in_.tolist(), "parameters": model.get_params(),
        "offset": float(model.offset_),
    })
    return root, tmp_path / "synthetic-run"


def test_adapted_model_and_unchanged_development_ids_complete_synthetic_lifecycle(
    development_files, fitted_synthetic_model, synthetic_frames, tmp_path, monkeypatch
):
    # Catches dropped/relabelled IDs, refitting, model drift, or real evidence claims.
    for operation in ("fit", "predict", "decision_function"):
        monkeypatch.setattr(IsolationForest, operation, forbidden_operation)
    original_state = joblib.hash(fitted_synthetic_model)
    original_hashes = {name: digest(development_files / name) for name in ADAPTER_INPUTS}
    deserialize = joblib.load
    loaded_states = []

    def capture_loaded_state(*args, **kwargs):
        model = deserialize(*args, **kwargs)
        loaded_states.append((model, joblib.hash(model)))
        return model

    monkeypatch.setattr(joblib, "load", capture_loaded_state)
    adapted = adapt_development(development_files, fitted_synthetic_model, monkeypatch)
    assert len(loaded_states) == 2
    for index, split in enumerate(("train", "val")):
        result = adapted[split]
        pd.testing.assert_frame_equal(result.frame, synthetic_frames[split])
        assert result.model is loaded_states[index][0]
        assert joblib.hash(result.model) == loaded_states[index][1]
        assert_fitted_state_preserved(result.model, fitted_synthetic_model)
        assert result.model.get_params() == PARAMETERS
        assert list(result.model.feature_names_in_) == FEATURES
        assert len(result.model.estimators_) == 200
        record = result.technical_record
        assert record["source_reconciled"] is False
        assert record["split"] == split
        assert record["input_hashes_sha256"] == original_hashes
        assert record["accessed_files"] == list(ADAPTER_INPUTS)
        assert record["features"] == FEATURES
        assert record["parameters"] == PARAMETERS
        assert record["legacy_offset"] == float(fitted_synthetic_model.offset_)
        assert record["model_fits"] == record["score_calls"] == 0
        assert record["test_used"] is record["scientific_evidence"] is False

    holdout = synthetic_frames["synthetic_holdout"]
    source, run_dir = executor_fixture(tmp_path, adapted, holdout)
    expected_dev = pd.concat([synthetic_frames[s][["invoice_id", "split"]]
                              for s in ("train", "val")], ignore_index=True)
    pd.testing.assert_frame_equal(pd.read_parquet(source / "development_ids.parquet"), expected_dev)
    assert set(expected_dev["invoice_id"]).isdisjoint(holdout["invoice_id"])
    assert (source / "holdout.parquet").resolve() not in {
        (development_files / name).resolve() for name in ADAPTER_INPUTS[:2]}
    configuration = executor.configuration_contract(float(adapted["train"].model.offset_))
    expected_configuration = {
        "schema": "invoice-synthetic-freeze/1.0", "mode": "synthetic_only",
        "protocol_version": "invoice-academic-evaluation-1.0", "split": "synthetic_holdout",
        "features": FEATURES, "parameters": PARAMETERS,
        "legacy_offset": float(fitted_synthetic_model.offset_), "budget_percentages": [1, 5, 10],
        "decision_rule": "selection_at_k", "test_authorized": False,
    }
    assert configuration == expected_configuration
    actual_score = IsolationForest.score_samples
    scored_models = []

    def score_independent_holdout(model, features):
        pd.testing.assert_frame_equal(features, holdout[FEATURES])
        assert model is loaded_states[-1][0]
        assert joblib.hash(model) == loaded_states[-1][1]
        assert_fitted_state_preserved(model, adapted["train"].model)
        scored_models.append(model)
        return actual_score(model, features)

    monkeypatch.setattr(IsolationForest, "score_samples", score_independent_holdout)
    frozen_path = executor.freeze_configuration(source, run_dir, configuration)
    frozen_hash = digest(frozen_path)
    frozen = executor.load_frozen_configuration(frozen_path, frozen_hash)
    assert frozen["pre_access_sha256"] == {
        name: digest(source / name)
        for name in ("model.joblib", "model_metadata.json", "development_ids.parquet")}
    results = executor.run_synthetic_evaluation(frozen_path, expected_freeze_sha256=frozen_hash)
    evidence = executor.verify_bundle(
        results, expected_manifest_sha256=digest(results / "manifest.json"),
        expected_freeze_sha256=frozen_hash)
    assert len(scored_models) == 1
    assert len(loaded_states) == 3
    for model, state in loaded_states:
        assert joblib.hash(model) == state
    assert joblib.hash(fitted_synthetic_model) == original_state
    assert evidence["configuration"] == expected_configuration
    assert evidence["schema"] == "invoice-synthetic-evidence/1.0"
    assert evidence["synthetic"] is True
    assert evidence["scientific_evidence"] is evidence["test_used"] is False
    assert evidence["model_fits_in_executor"] == 0
    assert evidence["freeze_sha256"] == frozen_hash
    assert evidence["currency"] == "SYN"
    assert evidence["metrics"]["isolation_forest"]["rows"] == 100
    assert [item["k"] for item in evidence["metrics"]["comparisons"]] == [1, 5, 10]
    expected_ids_bytes = json.dumps(holdout["invoice_id"].tolist(), separators=(",", ":")).encode()
    assert evidence["ids_sha256"] == hashlib.sha256(expected_ids_bytes).hexdigest()
    assert evidence["input_hashes_sha256"] == {
        name: digest(source / name) for name in (
            "holdout.parquet", "development_ids.parquet", "splits.parquet", "labels.parquet",
            "amounts.parquet", "model.joblib", "model_metadata.json")}
    assert {name: digest(development_files / name) for name in ADAPTER_INPUTS} == original_hashes
    published_hash = digest(results / "evidence.json")
    monkeypatch.setattr(IsolationForest, "score_samples", forbidden_operation)
    with pytest.raises(FileExistsError):
        executor.run_synthetic_evaluation(frozen_path, expected_freeze_sha256=frozen_hash)
    assert digest(results / "evidence.json") == published_hash


@pytest.mark.parametrize("split", ["train", "val"])
def test_adapter_development_frame_is_deliberately_rejected_before_scoring(
    development_files, fitted_synthetic_model, monkeypatch, split
):
    adapted = adapt_development(development_files, fitted_synthetic_model, monkeypatch)[split]
    before = adapted.frame.copy(deep=True)
    monkeypatch.setattr(IsolationForest, "score_samples", forbidden_operation)
    with pytest.raises(ValueError, match="synthetic_holdout"):
        executor.evaluate_frame(adapted.model, adapted.frame,
                                executor.configuration_contract(float(adapted.model.offset_)))
    pd.testing.assert_frame_equal(adapted.frame, before)


@pytest.mark.parametrize("fault", ["train", "val", "test", "real", "authorization"])
def test_configuration_cannot_expand_adapter_handoff_to_development_or_real_evaluation(
    development_files, fitted_synthetic_model, synthetic_frames, monkeypatch, fault
):
    adapted = adapt_development(development_files, fitted_synthetic_model, monkeypatch)["train"]
    configuration = executor.configuration_contract(float(adapted.model.offset_))
    key, value = (("mode", "real") if fault == "real" else
                  ("test_authorized", True) if fault == "authorization" else ("split", fault))
    configuration[key] = value
    monkeypatch.setattr(IsolationForest, "score_samples", forbidden_operation)
    with pytest.raises(ValueError, match="Configuracao"):
        executor.evaluate_frame(adapted.model, synthetic_frames["synthetic_holdout"], configuration)


@pytest.mark.parametrize("split", ["train", "val"])
def test_collision_with_unchanged_adapter_development_id_fails_before_scoring(
    development_files, fitted_synthetic_model, synthetic_frames, tmp_path, monkeypatch, split
):
    adapted = adapt_development(development_files, fitted_synthetic_model, monkeypatch)
    holdout = synthetic_frames["synthetic_holdout"].copy(deep=True)
    holdout.loc[0, "invoice_id"] = adapted[split].frame.loc[0, "invoice_id"]
    source, run_dir = executor_fixture(tmp_path, adapted, holdout)
    # Unique official IDs let the combined development/holdout gate detect the collision.
    official = pd.read_parquet(source / "splits.parquet").drop_duplicates("invoice_id")
    official.to_parquet(source / "splits.parquet", index=False)
    monkeypatch.setattr(IsolationForest, "score_samples", forbidden_operation)
    frozen = executor.freeze_configuration(source, run_dir,
        executor.configuration_contract(float(adapted["train"].model.offset_)))
    with pytest.raises(ValueError, match="separacao train/val/holdout"):
        executor.run_synthetic_evaluation(frozen, expected_freeze_sha256=digest(frozen))
    assert (run_dir / "failure.json").is_file()
    assert not (run_dir / "results").exists()


def test_legacy_adapter_metadata_is_not_an_executor_metadata_converter(
    development_files, fitted_synthetic_model, synthetic_frames, tmp_path, monkeypatch
):
    adapted = adapt_development(development_files, fitted_synthetic_model, monkeypatch)
    source, run_dir = executor_fixture(tmp_path, adapted, synthetic_frames["synthetic_holdout"])
    (source / "model_metadata.json").write_bytes((development_files / ADAPTER_INPUTS[3]).read_bytes())
    monkeypatch.setattr(IsolationForest, "score_samples", forbidden_operation)
    frozen = executor.freeze_configuration(source, run_dir,
        executor.configuration_contract(float(adapted["train"].model.offset_)))
    with pytest.raises(ValueError, match="Metadata"):
        executor.run_synthetic_evaluation(frozen, expected_freeze_sha256=digest(frozen))
    assert not (run_dir / "results").exists()
