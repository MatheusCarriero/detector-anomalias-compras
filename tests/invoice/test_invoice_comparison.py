"""Independent expected counts and synthetic safeguards for Invoice comparison."""

import importlib.util
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import IsolationForest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def load_api():
    path = ROOT / "ml/scripts/comparar_triagem_invoice.py"
    assert path.exists(), "Comparação operacional ainda não implementada"
    spec = importlib.util.spec_from_file_location("invoice_comparison_tests", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def api():
    return load_api()


def hand_frame():
    positive = {0, 1, 2, 5, 6, 7, 20}
    frame = pd.DataFrame({
        "invoice_id": [f"{i:03}" for i in range(100)],
        "is_fraud": [int(i in positive) for i in range(100)],
        "fraud_type": ["INFLATED" if i in {0, 1, 2} else "SPLIT" if i in {5, 6, 7}
                       else "NONE" for i in range(100)],
        "invoice_amount": np.arange(100., 0., -1),
    })
    order = [0, *range(5, 14)] + [i for i in range(100) if i != 0 and i not in range(5, 14)]
    scores = np.empty(100)
    scores[order] = np.arange(100., 0., -1)
    return frame, scores


def test_equal_capacity_gross_net_overlap_and_concentration():
    api = load_api()
    frame, scores = hand_frame()
    result = api.compare_rankings(frame, scores)
    assert [row["k"] for row in result["comparisons"]] == [1, 5, 10]
    five = result["comparisons"][1]
    assert five["common"]["rows"] == five["common"]["known_positives"] == 1
    assert five["if_only"]["rows"] == 4
    assert five["if_only"]["known_positives"] == 3
    assert five["value_only"]["known_positives"] == 2
    assert five["net_additional_positives"] == 1
    assert five["overlap_fraction"] == .2
    assert five["jaccard"] == pytest.approx(1 / 9)
    assert five["union"]["rows"] == 9
    assert five["union"]["known_positives"] == 6
    assert five["precision_delta"] == .2
    assert five["capture_delta"] == pytest.approx(1 / 7)
    forest = result["isolation_forest"]["budgets"][1]
    value = result["invoice_value"]["budgets"][1]
    assert forest["precision_at_k"] == .8
    assert value["precision_at_k"] == .6
    assert forest["capture"] == pytest.approx(4 / 7)
    assert forest["lift"] == pytest.approx(.8 / .07)
    assert five["if_selected"]["concentration"]["all"] == {"types": ["SPLIT"], "count": 3, "share": .6}
    assert five["if_selected"]["concentration"]["positive"]["share"] == .75


def test_identical_disjoint_and_negative_increment(api):
    frame, _ = hand_frame()
    for row in api.compare_rankings(frame, frame["invoice_amount"])["comparisons"]:
        assert row["overlap_fraction"] == row["jaccard"] == 1
        assert row["if_only"]["rows"] == row["value_only"]["rows"] == 0
        assert row["net_additional_positives"] == 0
        assert row["if_only"]["concentration"]["positive"] is None
    five = api.compare_rankings(frame, -frame["invoice_amount"])["comparisons"][1]
    assert five["common"]["rows"] == five["overlap_fraction"] == 0
    assert five["net_additional_positives"] == -3


def test_ties_not_labels_input_order_or_absolute_amount(api):
    frame, _ = hand_frame()
    frame["invoice_amount"] = -100.
    frame.loc[99, "invoice_amount"] = -1.
    first = api.compare_rankings(frame, np.ones(100))
    assert first == api.compare_rankings(frame.iloc[::-1], np.ones(100))
    assert first["invoice_value"]["budgets"][0]["known_positives"] == 0
    assert first["isolation_forest"]["budgets"][0]["known_positives"] == 1
    assert first["isolation_forest"]["budgets"][0]["boundary_tie_count"] == 100


def test_no_positives_small_cohort_and_missing_type(api):
    frame, _ = hand_frame()
    frame = frame.iloc[:3].assign(is_fraud=0, fraud_type=None)
    for row in api.compare_rankings(frame, [3., 2., 1.])["comparisons"]:
        assert row["k"] == 1
        assert row["capture_delta"] is None
        assert row["if_selected"]["by_fraud_type"] == {"__missing__": {"rows": 1, "known_positives": 0}}


@pytest.mark.parametrize("fault", ["empty", "duplicate", "label", "nan", "inf", "length", "amount"])
def test_invalid_comparison_inputs(api, fault):
    frame, score = hand_frame()
    if fault == "empty":
        frame, score = frame.iloc[:0], score[:0]
    elif fault == "duplicate":
        frame.loc[1, "invoice_id"] = "000"
    elif fault == "label":
        frame.loc[0, "is_fraud"] = 2
    elif fault == "length":
        score = score[:1]
    elif fault == "amount":
        frame.loc[0, "invoice_amount"] = np.inf
    else:
        score[0] = np.nan if fault == "nan" else np.inf
    with pytest.raises(ValueError):
        api.compare_rankings(frame, score)


@pytest.mark.parametrize("split", ["train", "test", "validation", "../test"])
def test_only_val_before_io(api, tmp_path, split):
    with pytest.raises(ValueError, match="val"):
        api.run(tmp_path, split=split)


@pytest.fixture
def source(api, tmp_path):
    train = pd.DataFrame(np.arange(8 * 19).reshape(8, 19) / 10, columns=api.triage.FEATURES)
    val = train.iloc[:4].copy()
    for frame, prefix, split in ((train, "t", "train"), (val, "v", "val")):
        frame.insert(0, "fraud_type", ["NONE", "NONE", "SPLIT", "SPLIT"] * (len(frame) // 4))
        frame.insert(0, "is_fraud", [0, 0, 1, 1] * (len(frame) // 4))
        frame.insert(0, "split", split)
        frame.insert(0, "invoice_id", [f"{prefix}{i}" for i in range(len(frame))])
    for folder in ("data/raw", "data/processed", "ml/models", "ml/experiments"):
        (tmp_path / folder).mkdir(parents=True)
    train.to_parquet(tmp_path / "data/processed/train_features.parquet", index=False)
    val.to_parquet(tmp_path / "data/processed/val_features.parquet", index=False)
    official = pd.concat([train, val])[["invoice_id", "split"]]
    pd.concat([official, pd.DataFrame({"invoice_id": ["closed"], "split": ["test"]})]).to_parquet(
        tmp_path / "data/raw/splits.parquet", index=False,
    )
    val[["invoice_id", "is_fraud", "fraud_type"]].to_parquet(tmp_path / "data/raw/labels.parquet", index=False)
    invoices = val[["invoice_id", "invoice_amount"]].assign(currency="ZAR")
    pd.concat([invoices, pd.DataFrame({"invoice_id": ["closed"], "invoice_amount": [np.inf],
                                    "currency": [None]})]).to_parquet(tmp_path / "data/raw/invoices.parquet", index=False)
    model = IsolationForest(**api.triage.EXPECTED_PARAMS).fit(train[api.triage.FEATURES])
    joblib.dump(model, tmp_path / "ml/models/isolation_forest.joblib")
    (tmp_path / "ml/models/model_metadata.json").write_text(json.dumps({
        "algorithm": "IsolationForest", **api.triage.EXPECTED_PARAMS,
        "feature_count": 19, "features": api.triage.FEATURES,
    }), encoding="utf-8")
    hashes = {name: api.triage.sha256(tmp_path / name) for name in api.triage.PRESERVED_INPUTS}
    (tmp_path / api.triage.PREVIOUS).write_text(json.dumps({
        "input_hashes_sha256": hashes, "offset": float(model.offset_),
        "parameters": model.get_params(), "split": "val", "rows": 4, "test_used": False,
    }), encoding="utf-8")
    (tmp_path / api.triage.OUTPUT).write_text(json.dumps({
        "input_hashes_sha256": {**hashes, api.triage.PREVIOUS: api.triage.sha256(tmp_path / api.triage.PREVIOUS)},
        "validation": api.triage.rank_summary(val, -model.score_samples(val[api.triage.FEATURES])),
        "validation_ids_sha256": api.triage._fingerprint(val["invoice_id"].tolist()),
        "split": "val", "test_used": False, "budget_percentages": [1, 5, 10],
    }), encoding="utf-8")
    return tmp_path


def test_end_to_end_no_fit_only_val_and_exclusive_output(api, source, monkeypatch):
    def no_fit(*args, **kwargs):
        raise AssertionError("Fit não autorizado")
    monkeypatch.setattr(IsolationForest, "fit", no_fit)
    original = pd.read_parquet
    def guarded(path, **kwargs):
        name = Path(path).name
        assert "test" not in name.lower()
        if name == "train_features.parquet":
            assert kwargs["columns"] == ["invoice_id", "split"]
        elif name == "splits.parquet":
            assert kwargs["filters"] == [("split", "in", ["train", "val"])]
        elif name in ("labels.parquet", "invoices.parquet"):
            assert kwargs["filters"] == [("invoice_id", "in", ["v0", "v1", "v2", "v3"])]
        return original(path, **kwargs)
    monkeypatch.setattr(pd, "read_parquet", guarded)
    result = api.run(source)
    assert result["test_used"] is False
    assert result["real_model_fits"] == 0
    assert result["isolation_forest"]["rows"] == 4
    assert result["currency"] == "ZAR"
    assert result["previous_triage_reconciled"] is True
    path = source / api.OUTPUT
    assert json.loads(path.read_text(encoding="utf-8")) == result
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        api.run(source)
    assert path.read_bytes() == before


@pytest.mark.parametrize("fault", ["missing", "duplicate", "amount", "currency", "null_currency"])
def test_bad_source_amounts_or_currency_rejected(api, source, fault):
    path = source / "data/raw/invoices.parquet"
    frame = pd.read_parquet(path)
    if fault == "missing":
        frame = frame[frame["invoice_id"].ne("v0")]
    elif fault == "duplicate":
        frame = pd.concat([frame, frame[frame["invoice_id"].eq("v0")]])
    elif fault == "amount":
        frame.loc[frame["invoice_id"].eq("v0"), "invoice_amount"] = 999.
    else:
        frame.loc[frame["invoice_id"].eq("v0"), "currency"] = None if fault == "null_currency" else "USD"
    frame.to_parquet(path, index=False)
    with pytest.raises(ValueError):
        api.run(source)
    assert not (source / api.OUTPUT).exists()


@pytest.mark.parametrize("fault", ["input_hash", "previous_selection", "previous_ids", "previous_split"])
def test_changed_inputs_or_prior_cohort_rejected(api, source, fault):
    path = source / api.triage.OUTPUT
    previous = json.loads(path.read_text(encoding="utf-8"))
    if fault == "input_hash":
        previous["input_hashes_sha256"][api.triage.PRESERVED_INPUTS[0]] = "0" * 64
    elif fault == "previous_selection":
        previous["validation"]["budgets"][0]["selected_ids_sha256"] = "0" * 64
    elif fault == "previous_ids":
        previous["validation_ids_sha256"] = "0" * 64
    else:
        previous["split"] = "test"
    path.write_text(json.dumps(previous), encoding="utf-8")
    with pytest.raises(ValueError):
        api.run(source)
    assert not (source / api.OUTPUT).exists()
