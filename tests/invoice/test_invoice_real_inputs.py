"""Synthetic source consistency tests for the explicit academic input API."""

import copy
import json

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import IsolationForest

from ml.scripts import invoice_final_evaluation as evaluator
from ml.scripts import invoice_real_inputs as inputs


@pytest.fixture(scope="module")
def sample():
    frames = {}
    for split, count in (("train", 12), ("val", 6), ("test", 10)):
        frame = pd.DataFrame(np.ones((count, 19)), columns=evaluator.ORDERED_FEATURES)
        frame["invoice_amount"] = np.arange(count, dtype=float) - 3
        frame.insert(0, "fraud_type", ["A" if i % 2 else None for i in range(count)])
        frame.insert(0, "is_fraud", np.arange(count) % 2)
        frame.insert(0, "split", split)
        frame.insert(0, "invoice_id", [f"synthetic-{split}-{i:03}" for i in range(count)])
        frames[split] = frame
    model = IsolationForest(**evaluator.PARAMETERS).fit(frames["train"][list(evaluator.ORDERED_FEATURES)])
    combined = pd.concat(frames.values(), ignore_index=True)
    return {
        "frames": frames, "model": model,
        "metadata": {"algorithm": "IsolationForest", "feature_count": 19,
                  "features": list(evaluator.ORDERED_FEATURES), "n_estimators": 200,
                  "contamination": 0.22, "random_state": 42,
                  "parameters": evaluator.PARAMETERS.copy(), "offset": float(model.offset_)},
        "splits": combined[["invoice_id", "split"]].iloc[::-1],
        "labels": combined[["invoice_id", "is_fraud", "fraud_type"]].iloc[::-1],
        "amounts": combined[["invoice_id", "invoice_amount"]].assign(currency="SYN").iloc[::-1],
        "configuration": evaluator.configuration_contract(float(model.offset_)),
    }


@pytest.fixture
def tables(sample):
    return copy.deepcopy(sample)


def forbidden(*args, **kwargs):
    raise AssertionError("Validation must not fit or score")


def test_source_consistency_aligns_by_id_without_fit_or_score(tables, monkeypatch):
    for name in ("fit", "score_samples", "predict", "decision_function"):
        monkeypatch.setattr(IsolationForest, name, forbidden)
    state = joblib.hash(tables["model"])
    adapted = inputs.validate_frames(**tables)
    pd.testing.assert_frame_equal(adapted.frame, tables["frames"]["test"])
    assert joblib.hash(adapted.model) == state
    assert adapted.technical_record["source_rows_consistent"] is True
    assert adapted.technical_record["source_reconciled"] is False
    assert adapted.technical_record["currency"] == "SYN"
    assert adapted.technical_record["score_calls"] == adapted.technical_record["model_fits"] == 0


@pytest.mark.parametrize("fault", [
    "missing_feature", "feature_order", "nonfinite", "negative_frequency", "bad_label",
    "duplicate_id", "null_id", "wrong_split", "overlap", "incomplete_cohort",
    "source_split", "source_label", "source_type", "source_missing_id", "source_duplicate_id",
    "amount", "amount_nan", "amount_text", "currency_mixed", "currency_null",
    "metadata_features", "metadata_parameter", "metadata_offset",
])
def test_invalid_processed_or_source_content_is_rejected(tables, monkeypatch, fault):
    for name in ("fit", "score_samples", "predict", "decision_function"):
        monkeypatch.setattr(IsolationForest, name, forbidden)
    frame = tables["frames"]["test"]
    if fault == "missing_feature":
        tables["frames"]["test"] = frame.drop(columns="month_sin")
    elif fault == "feature_order":
        tables["frames"]["test"] = frame[[*frame.columns[:4], *reversed(evaluator.ORDERED_FEATURES)]]
    elif fault == "nonfinite":
        frame.loc[0, "month_sin"] = np.inf
    elif fault == "negative_frequency":
        frame.loc[0, "supplier_frequency"] = -1.0
    elif fault == "bad_label":
        frame.loc[0, "is_fraud"] = 2
    elif fault == "duplicate_id":
        frame.loc[0, "invoice_id"] = frame.loc[1, "invoice_id"]
    elif fault == "null_id":
        frame.loc[0, "invoice_id"] = None
    elif fault == "wrong_split":
        frame.loc[0, "split"] = "val"
    elif fault == "overlap":
        frame.loc[0, "invoice_id"] = tables["frames"]["train"].loc[0, "invoice_id"]
    elif fault == "incomplete_cohort":
        tables["frames"]["test"] = frame.iloc[1:]
    elif fault.startswith("source_"):
        key = "splits" if fault == "source_split" else "labels"
        source = tables[key]
        index = source.index[source["invoice_id"].eq("synthetic-test-000")][0]
        if fault == "source_split":
            source.loc[index, "split"] = "train"
        elif fault == "source_label":
            source.loc[index, "is_fraud"] = 1
        elif fault == "source_type":
            source.loc[index, "fraud_type"] = "other"
        elif fault == "source_missing_id":
            tables[key] = source.drop(index=index)
        else:
            tables[key] = pd.concat([source, source.loc[[index]]], ignore_index=True)
    elif fault.startswith("metadata_"):
        if fault == "metadata_features":
            tables["metadata"]["features"] = list(reversed(evaluator.ORDERED_FEATURES))
        elif fault == "metadata_parameter":
            tables["metadata"]["parameters"]["verbose"] = False
        else:
            tables["metadata"]["offset"] += 0.1
    else:
        source = tables["amounts"]
        index = source.index[source["invoice_id"].eq("synthetic-test-000")][0]
        if fault == "amount":
            source.loc[index, "invoice_amount"] += 1
        elif fault == "amount_nan":
            source.loc[index, "invoice_amount"] = np.nan
        elif fault == "amount_text":
            source["invoice_amount"] = source["invoice_amount"].astype(str)
        else:
            source.loc[index, "currency"] = None if fault == "currency_null" else "OTHER"
    with pytest.raises((ValueError, TypeError)):
        inputs.validate_frames(**tables)


@pytest.mark.parametrize("fault", ["trees", "features", "offset", "parameters"])
def test_model_compatibility_rejected_without_inference(tables, monkeypatch, fault):
    model = tables["model"]
    if fault == "trees":
        model.estimators_ = model.estimators_[:-1]
    elif fault == "features":
        model.feature_names_in_ = model.feature_names_in_[::-1]
    elif fault == "offset":
        model.offset_ += 0.1
    else:
        model.set_params(n_estimators=201)
    monkeypatch.setattr(IsolationForest, "score_samples", forbidden)
    with pytest.raises((ValueError, TypeError)):
        inputs.validate_frames(**tables)


@pytest.mark.parametrize("wide_sources", [False, True])
def test_explicit_paths_roundtrip_uses_only_generated_files(tables, tmp_path, monkeypatch, wide_sources):
    paths = {}
    for split, frame in tables["frames"].items():
        paths[split] = tmp_path / f"{split}.parquet"
        frame.to_parquet(paths[split], index=False)
    sources = {}
    for name in ("splits", "labels", "amounts"):
        sources[name + "_path"] = tmp_path / f"{name}.parquet"
        source = tables[name]
        if wide_sources:
            source = source.assign(original_source_field="synthetic")
            source = source[list(reversed(source.columns))]
        source.to_parquet(sources[name + "_path"], index=False)
    model_path, metadata_path = tmp_path / "model.joblib", tmp_path / "metadata.json"
    joblib.dump(tables["model"], model_path)
    metadata_path.write_text(json.dumps(tables["metadata"]), encoding="utf-8")
    for name in ("fit", "score_samples", "predict", "decision_function"):
        monkeypatch.setattr(IsolationForest, name, forbidden)
    adapted = inputs.validate_inputs(
        processed_paths=paths, model_path=model_path, metadata_path=metadata_path,
        configuration=tables["configuration"], **sources,
    )
    pd.testing.assert_frame_equal(adapted.frame, tables["frames"]["test"])
    assert adapted.technical_record["source_reconciled"] is False


def test_file_inputs_reject_unavailable_partition_before_io(tmp_path):
    missing = tmp_path / "must-not-be-opened"
    with pytest.raises(ValueError, match="Particao"):
        inputs.validate_inputs(
            processed_paths={split: missing for split in ("train", "val", "test")},
            model_path=missing, metadata_path=missing, splits_path=missing,
            labels_path=missing, amounts_path=missing,
            configuration=evaluator.configuration_contract(-0.5, split="synthetic_holdout"),
        )


def test_memory_inputs_reject_unavailable_partition(tables):
    tables["configuration"]["split"] = "synthetic_holdout"
    with pytest.raises(ValueError, match="Particao"):
        inputs.validate_frames(**tables)
