"""Synthetic checks for the fixed-budget Invoice triage diagnostic."""

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


@pytest.fixture
def api():
    path = ROOT / "ml/scripts/diagnosticar_triagem_invoice.py"
    assert path.exists(), "Diagnostico de triagem ainda ausente"
    spec = importlib.util.spec_from_file_location("invoice_triage_tests", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ranking_frame(n=100):
    return pd.DataFrame({
        "invoice_id": [f"{i:03}" for i in range(n)],
        "is_fraud": [int(i >= n - 10) for i in range(n)],
        "fraud_type": ["NONE"] * n,
    })


def test_top_k_hand_calculated_and_random_reference(api):
    result = api.rank_summary(ranking_frame(), np.arange(100.0))
    one, five, ten = result["budgets"]
    assert [item["k"] for item in (one, five, ten)] == [1, 5, 10]
    assert [item["known_positives"] for item in (one, five, ten)] == [1, 5, 10]
    assert five["precision_at_k"] == 1
    assert five["capture"] == .5
    assert five["lift"] == 10
    assert five["random_expected_positives"] == .5
    assert five["random_capture"] == .05
    assert five["ambiguous_labels"] == 5
    assert ten["by_fraud_type"]["NONE"] == {"rows": 10, "known_positives": 10}
    assert result["prevalence"] == .1


def test_ties_are_id_based_not_labels_or_input_order(api):
    frame = ranking_frame(20)
    score = np.ones(20)
    original = api.rank_summary(frame, score)
    reordered = api.rank_summary(frame.iloc[::-1], score)
    assert original == reordered
    ten = original["budgets"][2]
    assert ten["k"] == 2
    assert ten["known_positives"] == 0
    assert ten["boundary_tie_count"] == 20
    assert ten["boundary_ties_selected"] == 2


def test_no_positives_and_round_up(api):
    frame = ranking_frame(3).assign(is_fraud=0)
    result = api.rank_summary(frame, [3., 2., 1.])
    for budget in result["budgets"]:
        assert budget["k"] == 1
        assert budget["precision_at_k"] == 0
        assert budget["capture"] is None
        assert budget["lift"] is None
        assert budget["random_expected_positives"] == 0
        assert budget["random_capture"] is None


@pytest.mark.parametrize("fault", ["empty", "duplicate", "bad_label", "nan", "infinite", "length"])
def test_invalid_ranking_rejected(api, fault):
    frame = ranking_frame(20)
    scores = np.ones(20)
    if fault == "empty":
        frame, scores = frame.iloc[:0], scores[:0]
    elif fault == "duplicate":
        frame.loc[1, "invoice_id"] = frame.loc[0, "invoice_id"]
    elif fault == "bad_label":
        frame.loc[0, "is_fraud"] = 2
    elif fault in ("nan", "infinite"):
        scores[0] = np.nan if fault == "nan" else np.inf
    else:
        scores = scores[:2]
    with pytest.raises(ValueError):
        api.rank_summary(frame, scores)


def test_distribution_distance_and_quantiles(api):
    result = api.compare_distributions([0., 1., 2.], [2., 3.])
    assert result["cdf_distance"] == pytest.approx(2 / 3)
    assert result["validation_outside_train_range"] == 1
    assert result["train"]["p50"] == 1
    assert result["validation"]["p50"] == 2.5
    assert api.compare_distributions([2, 2], [2, 2])["cdf_distance"] == 0


@pytest.mark.parametrize("split", ["test", "train", "validation", "../test"])
def test_forbidden_split_fails_before_io(api, tmp_path, split):
    with pytest.raises(ValueError, match="val"):
        api.run(tmp_path, split=split)


@pytest.fixture
def source(api, tmp_path):
    train = pd.DataFrame(np.arange(8 * 19).reshape(8, 19) / 10, columns=api.FEATURES)
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
    official = pd.concat([official, pd.DataFrame({"invoice_id": ["closed"], "split": ["test"]})])
    official.to_parquet(tmp_path / "data/raw/splits.parquet", index=False)
    val[["invoice_id", "is_fraud", "fraud_type"]].iloc[::-1].to_parquet(
        tmp_path / "data/raw/labels.parquet", index=False,
    )
    pd.DataFrame({
        "invoice_id": ["closed", *train["invoice_id"], *val["invoice_id"]],
        "invoice_date": ["INVALID_TEST_DATE", *(["2023-01-01"] * 8),
                         "2023-09-14", "2023-09-14", "2023-10-01", "2023-10-01"],
    }).iloc[::-1].to_parquet(tmp_path / "data/raw/invoices.parquet", index=False)
    model = IsolationForest(**api.EXPECTED_PARAMS).fit(train[api.FEATURES])
    joblib.dump(model, tmp_path / "ml/models/isolation_forest.joblib")
    (tmp_path / "ml/models/model_metadata.json").write_text(json.dumps({
        "algorithm": "IsolationForest", **api.EXPECTED_PARAMS,
        "feature_count": 19, "features": api.FEATURES,
    }), encoding="utf-8")
    (tmp_path / "ml/experiments/invoice_validation_v1.json").write_text(json.dumps({
        "input_hashes_sha256": {name: api.sha256(tmp_path / name) for name in api.PRESERVED_INPUTS},
        "offset": float(model.offset_), "parameters": model.get_params(),
        "split": "val", "rows": 4, "test_used": False,
    }), encoding="utf-8")
    return tmp_path


def test_end_to_end_filtered_no_fit_no_test_and_exclusive_output(api, source, monkeypatch):
    def no_fit(*args, **kwargs):
        raise AssertionError("No fit during diagnosis")
    monkeypatch.setattr(IsolationForest, "fit", no_fit)
    original = pd.read_parquet
    def guarded(path, **kwargs):
        name = Path(path).name
        assert name not in ("test_features.parquet", "X_test.parquet", "y_test.parquet")
        if name == "splits.parquet":
            assert kwargs["filters"] == [("split", "in", ["train", "val"])]
        elif name == "labels.parquet":
            assert kwargs["filters"] == [("invoice_id", "in", ["v0", "v1", "v2", "v3"])]
        elif name == "invoices.parquet":
            assert kwargs["filters"] == [("invoice_id", "in", [
                "t0", "t1", "t2", "t3", "t4", "t5", "t6", "t7", "v0", "v1", "v2", "v3",
            ])]
        return original(path, **kwargs)
    monkeypatch.setattr(pd, "read_parquet", guarded)
    result = api.run(source)
    assert result["test_used"] is False
    assert result["real_model_fits"] == 0
    assert result["validation"]["rows"] == 4
    assert set(result["periods"]) == {"2023-09", "2023-10"}
    for group in result["periods"].values():
        assert group["rows"] == 2
    assert result["periods"]["2023-09"]["known_positives"] == 0
    assert result["periods"]["2023-10"]["known_positives"] == 2
    assert result["periods"]["2023-09"]["date_min"] == "2023-09-14T00:00:00"
    assert result["periods"]["2023-10"]["date_min"] == "2023-10-01T00:00:00"
    assert result["distributions"]["score"]["train"]["count"] == 8
    path = source / "ml/experiments/invoice_triage_validation_v1.json"
    assert json.loads(path.read_text(encoding="utf-8")) == result
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        api.run(source)
    assert path.read_bytes() == before


@pytest.mark.parametrize("fault", ["missing", "duplicate", "invalid"])
def test_bad_dates_rejected(api, source, fault):
    path = source / "data/raw/invoices.parquet"
    dates = pd.read_parquet(path)
    if fault == "missing":
        dates = dates[dates["invoice_id"].ne("v0")]
    elif fault == "duplicate":
        dates = pd.concat([dates, dates[dates["invoice_id"].eq("v0")]])
    else:
        dates.loc[dates["invoice_id"].eq("v0"), "invoice_date"] = "bad"
    dates.to_parquet(path, index=False)
    with pytest.raises(ValueError):
        api.run(source)
    assert not (source / "ml/experiments/invoice_triage_validation_v1.json").exists()


def test_changed_model_since_prior_evaluation_rejected(api, source):
    path = source / "ml/models/model_metadata.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="anterior"):
        api.run(source)


def test_unexpected_model_type_rejected(api, source):
    previous = json.loads((source / api.PREVIOUS).read_text(encoding="utf-8"))
    joblib.dump({"not": "a model"}, source / "ml/models/isolation_forest.joblib")
    with pytest.raises(TypeError, match="Isolation Forest"):
        api._load_model(source, previous)
