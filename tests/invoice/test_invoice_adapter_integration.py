"""Synthetic adapter/evaluator handoff; development rows never become holdout."""

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
from ml.scripts import invoice_real_evaluation as runner
from ml.scripts import invoice_real_inputs as inputs
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


def evaluation_tables(adapted, holdout):
    """All rows are generated fixtures; labels/amounts deliberately reverse order."""
    frames = {split: adapted[split].frame for split in ("train", "val")}
    frames["test"] = holdout.assign(split="test")
    all_rows = pd.concat(list(frames.values()), ignore_index=True)
    return {
        "frames": frames,
        "splits": all_rows[["invoice_id", "split"]],
        "labels": all_rows[["invoice_id", "is_fraud", "fraud_type"]].iloc[::-1],
        "amounts": all_rows[["invoice_id", "invoice_amount"]].assign(currency="SYN").iloc[::-1],
    }


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

    holdout_path = tmp_path / "generated-holdout.parquet"
    synthetic_frames["synthetic_holdout"].to_parquet(holdout_path, index=False)
    holdout = pd.read_parquet(holdout_path)
    for split in ("train", "val"):
        assert set(adapted[split].frame["invoice_id"]).isdisjoint(holdout["invoice_id"])
    assert holdout_path not in {development_files / name for name in ADAPTER_INPUTS[:2]}
    configuration = executor.configuration_contract(float(adapted["train"].model.offset_), split="test")
    metadata = json.loads((development_files / ADAPTER_INPUTS[3]).read_text())
    checked = inputs.validate_frames(
        **evaluation_tables(adapted, holdout), model=adapted["train"].model,
        metadata=metadata, configuration=configuration,
    )
    assert checked.technical_record["source_reconciled"] is False
    assert checked.technical_record["source_rows_consistent"] is True
    assert checked.technical_record["currency"] == "SYN"
    actual_score = IsolationForest.score_samples
    scored_models = []

    def score_independent_holdout(model, features):
        pd.testing.assert_frame_equal(features, holdout[FEATURES])
        assert model is loaded_states[0][0]
        assert joblib.hash(model) == loaded_states[0][1]
        assert_fitted_state_preserved(model, adapted["train"].model)
        scored_models.append(model)
        return actual_score(model, features)

    monkeypatch.setattr(IsolationForest, "score_samples", score_independent_holdout)
    results = runner.run_final_evaluation(
        tmp_path / "synthetic-result.json", **evaluation_tables(adapted, holdout),
        model=adapted["train"].model, metadata=metadata,
        configuration=configuration, evaluation_id="generated-fixture-only",
    )
    evidence = json.loads(results.read_text(encoding="utf-8"))
    assert len(scored_models) == 1
    assert len(loaded_states) == 2
    for model, state in loaded_states:
        assert joblib.hash(model) == state
    assert joblib.hash(fitted_synthetic_model) == original_state
    assert evidence["configuration"] == configuration
    assert evidence["features"] == FEATURES
    assert evidence["source_reconciled"] is False
    assert evidence["legacy_training_provenance_certified"] is False
    assert evidence["model_fits_in_executor"] == 0
    assert evidence["metrics"]["isolation_forest"]["rows"] == 100
    assert [item["k"] for item in evidence["metrics"]["comparisons"]] == [1, 5, 10]
    assert {name: digest(development_files / name) for name in ADAPTER_INPUTS} == original_hashes
    published_hash = digest(results)
    monkeypatch.setattr(IsolationForest, "score_samples", forbidden_operation)
    with pytest.raises(FileExistsError):
        runner.run_final_evaluation(
            results, **evaluation_tables(adapted, holdout), model=adapted["train"].model,
            metadata=metadata, configuration=configuration, evaluation_id="generated-fixture-only",
        )
    assert digest(results) == published_hash


@pytest.mark.parametrize("split", ["train", "val"])
def test_adapter_development_frame_is_deliberately_rejected_before_scoring(
    development_files, fitted_synthetic_model, monkeypatch, split
):
    adapted = adapt_development(development_files, fitted_synthetic_model, monkeypatch)[split]
    before = adapted.frame.copy(deep=True)
    monkeypatch.setattr(IsolationForest, "score_samples", forbidden_operation)
    with pytest.raises(ValueError, match="Particao"):
        executor.evaluate_frame(adapted.model, adapted.frame,
                                executor.configuration_contract(float(adapted.model.offset_)))
    pd.testing.assert_frame_equal(adapted.frame, before)


@pytest.mark.parametrize("fault", ["features", "parameters", "budget_percentages", "decision_rule"])
def test_incompatible_configuration_rejected_before_scoring(
    development_files, fitted_synthetic_model, synthetic_frames, monkeypatch, fault
):
    adapted = adapt_development(development_files, fitted_synthetic_model, monkeypatch)["train"]
    configuration = executor.configuration_contract(float(adapted.model.offset_))
    replacements = {
        "features": FEATURES[::-1], "parameters": {**PARAMETERS, "contamination": 0.1},
        "budget_percentages": [5], "decision_rule": "new_threshold",
    }
    configuration[fault] = replacements[fault]
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
    tables = evaluation_tables(adapted, holdout)
    tables["splits"] = tables["splits"].drop_duplicates("invoice_id")
    monkeypatch.setattr(IsolationForest, "score_samples", forbidden_operation)
    with pytest.raises(ValueError, match="Sobreposicao"):
        inputs.validate_frames(
            **tables, model=adapted["train"].model,
            metadata=json.loads((development_files / ADAPTER_INPUTS[3]).read_text()),
            configuration=executor.configuration_contract(float(adapted["train"].model.offset_)),
        )
    assert not (tmp_path / "synthetic-result.json").exists()


def test_incompatible_metadata_is_rejected_without_conversion(
    development_files, fitted_synthetic_model, synthetic_frames, tmp_path, monkeypatch
):
    adapted = adapt_development(development_files, fitted_synthetic_model, monkeypatch)
    metadata = json.loads((development_files / ADAPTER_INPUTS[3]).read_text())
    metadata["features"] = FEATURES[::-1]
    monkeypatch.setattr(IsolationForest, "score_samples", forbidden_operation)
    with pytest.raises(ValueError, match="Metadata"):
        inputs.validate_frames(
            **evaluation_tables(adapted, synthetic_frames["synthetic_holdout"]),
            model=adapted["train"].model, metadata=metadata,
            configuration=executor.configuration_contract(float(adapted["train"].model.offset_)),
        )
    assert not (tmp_path / "synthetic-result.json").exists()
