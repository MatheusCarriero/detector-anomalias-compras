"""Synthetic-only executor contracts; never open project data or saved models."""

import copy
import importlib
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


def forbid_training(*args, **kwargs):
    raise AssertionError("Executor must not fit, predict, or call decision_function")


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
    result = api.evaluate_frame(model, frame, api.configuration_contract(float(model.offset_), split="synthetic_holdout"))
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
    result = api.evaluate_frame(model, frame, api.configuration_contract(float(model.offset_), split="synthetic_holdout"))
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
    config = api.configuration_contract(float(model.offset_), split="synthetic_holdout")
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
        api.evaluate_frame(model, frame, api.configuration_contract(float(model.offset_), split="synthetic_holdout"))


@pytest.mark.parametrize("fault", ["parameter", "bool_parameter", "offset", "n_features", "not_fitted"])
def test_invalid_model_rejected_before_scoring(api, model, monkeypatch, fault):
    configuration = api.configuration_contract(float(model.offset_), split="synthetic_holdout")
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
    config = api.configuration_contract(float(model.offset_), split="synthetic_holdout")

    def mutating_score(self, features):
        self.offset_ += 0.1
        return -np.ones(len(features))

    monkeypatch.setattr(IsolationForest, "score_samples", mutating_score)
    with pytest.raises(ValueError):
        api.evaluate_frame(model, hand_frame()[0], config)


@pytest.mark.parametrize("key,value", [
    ("features", FEATURES[::-1]), ("budget_percentages", [10]),
    ("budget_percentages", [True, 5, 10]), ("parameters", {"n_estimators": 201}),
    ("decision_rule", "predict"), ("split", "unknown"),
])
def test_incompatible_scientific_configuration_rejected_before_scoring(
    api, model, monkeypatch, key, value
):
    config = api.configuration_contract(float(model.offset_), split="synthetic_holdout")
    config[key] = value
    monkeypatch.setattr(IsolationForest, "score_samples", forbid_training)
    with pytest.raises(ValueError):
        api.evaluate_frame(model, hand_frame()[0], config)


@pytest.mark.parametrize("offset", [float("nan"), float("inf"), True, "-0.5"])
def test_nonfinite_or_coerced_offset_rejected(api, offset):
    with pytest.raises(ValueError):
        api.configuration_contract(offset)
