"""Baseline checks use only synthetic lines, small fits and explicit score doubles."""

import copy
import json
import random

import numpy as np
import pytest

from ml.procurement_v2 import baseline
from ml.procurement_v2.batch import MATRIX_FEATURES, prepare_batch


@pytest.fixture
def source():
    return {
        "source_id": "procurement-spend", "source_version": "baseline-fixture-v1",
        "entity_namespace": "synthetic-baseline", "origin": "synthetic",
        "monetary_unit": "unspecified_source_unit",
        "temporal_assumption": "available_at_order_no_revisions",
    }


@pytest.fixture
def coverage(source):
    return {
        **{key: source[key] for key in ("source_id", "source_version", "entity_namespace")},
        "start_date": "2023-01-01", "end_date": "2026-06-30", "complete": True,
    }


@pytest.fixture
def purchases(source):
    identity = {key: source[key] for key in ("source_id", "source_version", "entity_namespace")}

    def line(po_id, day, price):
        return {
            **identity, "po_id": po_id, "order_date": day,
            "supplier_id": "SUP-A", "item": "Steel (kg)", "business_unit": "Operations",
            "category": "Raw Materials", "unit_price": price, "quantity": 1, "line_total": price,
        }

    result = []
    for prefix, day in (("H0", "2023-01-01"), ("H1", "2024-12-01"), ("H2", "2025-12-01")):
        result.extend(line(f"{prefix}-{i:02d}", day, i) for i in range(1, 21))
    for prefix, day in (("D", "2023-04-01"), ("V", "2025-01-01"), ("R", "2026-01-01")):
        result.extend([line(f"{prefix}-A", day, 10), line(f"{prefix}-B", day, 20)])
    return result


class RecordingEstimator:
    """Records fit/scoring populations and supplies independently known raw scores."""

    def __init__(self, **parameters):
        self.parameters = parameters
        self.fits = []
        self.scored = []
        self.raw_scores = [-0.2, -0.8]

    def fit(self, frame):
        self.fits.append(np.asarray(frame).copy())
        self.n_features_in_ = np.asarray(frame).shape[1]
        self.feature_names_in_ = np.array(MATRIX_FEATURES, dtype=object)
        self.max_samples_ = min(256, len(frame))
        self.offset_ = -0.5
        return self

    def score_samples(self, frame):
        self.scored.append(np.asarray(frame).copy())
        return np.array(self.raw_scores)

    def predict(self, frame):
        raise AssertionError("No risk classes may be created")

    def decision_function(self, frame):
        raise AssertionError("No operational decision threshold may be used")


@pytest.fixture
def estimators(monkeypatch):
    created = []

    def factory(**parameters):
        estimator = RecordingEstimator(**parameters)
        created.append(estimator)
        return estimator

    monkeypatch.setattr(baseline, "IsolationForest", factory)
    return created


def test_only_development_fits_and_exactly_five_columns_are_used(purchases, source, coverage, estimators):
    result = baseline.run_baseline(purchases, source=source, coverage=coverage)
    estimator = estimators[0]
    assert len(estimators) == len(estimator.fits) == 1
    assert estimator.fits[0].shape == (2, 5)
    assert estimator.fits[0][0] == pytest.approx([20 / 21, 1, 19 / 21, 20, 20])
    assert estimator.fits[0][1] == pytest.approx([40 / 21, 1, 19 / 21, 20, 20])
    assert len(estimator.scored) == 3
    assert result["metadata"]["training"]["period"] == "development"
    assert result["metadata"]["training"]["rows"] == 2
    assert result["metadata"]["feature_names"] == list(MATRIX_FEATURES)
    assert estimator.parameters == {
        "n_estimators": 200, "contamination": "auto", "random_state": 42,
        "max_samples": "auto", "max_features": 1.0, "bootstrap": False,
        "n_jobs": 1, "warm_start": False,
    }


def test_inversion_ranking_and_trace_match_original_operations(purchases, source, coverage, estimators):
    result = baseline.run_baseline(purchases, source=source, coverage=coverage)
    ranked = result["periods"]["development"]["ranking"]
    assert [(row["rank"], row["po_id"], row["score"]) for row in ranked] == [(1, "D-B", .8), (2, "D-A", .2)]
    assert ranked[0]["features"][MATRIX_FEATURES[0]] == pytest.approx(40 / 21)
    assert ranked[0]["order_date"] == "2023-04-01"
    assert ranked[0]["occurrence"] == 1
    assert not {"risk", "probability", "fraud", "prediction", "class"} & ranked[0].keys()
    assert result["periods"]["warmup"]["ranking"] == []
    assert result["periods"]["warmup"]["statistics"] is None


def test_statistics_and_tails_use_development_reference(purchases, source, coverage, estimators):
    result = baseline.run_baseline(purchases, source=source, coverage=coverage)
    stats = result["periods"]["development"]["statistics"]
    assert stats["mean"] == pytest.approx(.5)
    assert stats["std_sample"] == pytest.approx(.4242640687119285)
    assert stats["percentiles"]["p95"] == pytest.approx(.77)
    for period in ("development", "validation_2025", "retrospective_2026"):
        tail = result["periods"][period]["upper_tails"]["p95"]
        assert tail["reference_value"] == pytest.approx(.77)
        assert tail["count"] == 1 and tail["fraction"] == .5


def test_ties_are_deterministic_and_tail_fraction_is_not_forced(purchases, source, coverage, monkeypatch):
    class TiedEstimator(RecordingEstimator):
        def __init__(self, **parameters):
            super().__init__(**parameters)
            self.raw_scores = [-.25, -.25]

    monkeypatch.setattr(baseline, "IsolationForest", TiedEstimator)
    result = baseline.run_baseline(purchases, source=source, coverage=coverage)
    assert [row["po_id"] for row in result["periods"]["development"]["ranking"]] == ["D-A", "D-B"]
    assert result["periods"]["development"]["upper_tails"]["p99"]["fraction"] == 1


def test_excluded_lines_stay_traceable_without_scores(purchases, source, coverage, estimators):
    result = baseline.run_baseline(purchases, source=source, coverage=coverage)
    assert len(result["excluded_operations"]) == 60
    assert {row["po_id"] for row in result["excluded_operations"]} == {
        row["po_id"] for row in purchases if row["po_id"].startswith("H")
    }
    assert all("score" not in row for row in result["excluded_operations"])
    assert result["periods"]["development"]["rows"] == 22
    assert result["periods"]["development"]["eligible"] == 2
    assert result["periods"]["development"]["excluded"] == 20


def test_empty_development_fails_before_fit(purchases, source, coverage, estimators):
    purchases = [row for row in purchases if not row["po_id"].startswith("D-")]
    with pytest.raises(baseline.BaselineError):
        baseline.run_baseline(purchases, source=source, coverage=coverage)
    assert not estimators or not estimators[0].fits


@pytest.mark.parametrize("fault", ["order", "width", "nan", "float32_overflow", "trace_id", "trace_period", "association"])
def test_invalid_prepared_contract_fails_before_any_fit(purchases, source, coverage, estimators, monkeypatch, fault):
    prepared = prepare_batch(purchases, source=source, coverage=coverage)
    matrix = prepared["matrices"]["validation_2025"]
    if fault == "order":
        prepared["matrix_feature_names"].reverse()
    elif fault == "width":
        matrix["values"][0].append(5)
    elif fault == "nan":
        matrix["values"][0][0] = float("nan")
    elif fault == "float32_overflow":
        matrix["values"][0][0] = 1e100
        idx = matrix["trace"][0]["operation_index"]
        prepared["operations"][idx]["feature_result"]["features"][MATRIX_FEATURES[0]] = 1e100
    elif fault == "trace_id":
        matrix["trace"][0]["po_id"] = "WRONG"
    elif fault == "trace_period":
        matrix["trace"][0]["order_date"] = "2024-12-31"
    else:
        matrix["values"].reverse()
    monkeypatch.setattr(baseline, "prepare_batch", lambda *args, **kwargs: prepared)
    with pytest.raises(baseline.BaselineError):
        baseline.run_baseline(purchases, source=source, coverage=coverage)
    assert not estimators or not estimators[0].fits


@pytest.mark.parametrize("raw_scores", [[-.2], [[-.2], [-.8]], [float("nan"), -.8], [-.2, float("inf")]])
def test_bad_estimator_outputs_never_become_rankings(purchases, source, coverage, monkeypatch, raw_scores):
    class BadEstimator(RecordingEstimator):
        def __init__(self, **parameters):
            super().__init__(**parameters)
            self.raw_scores = raw_scores

    monkeypatch.setattr(baseline, "IsolationForest", BadEstimator)
    with pytest.raises(baseline.BaselineError):
        baseline.run_baseline(purchases, source=source, coverage=coverage)


def test_real_estimator_is_reproducible_without_mutating_inputs(purchases, source, coverage):
    original = copy.deepcopy((purchases, source, coverage))
    first = baseline.run_baseline(purchases, source=source, coverage=coverage)
    shuffled = copy.deepcopy(purchases)
    random.Random(77).shuffle(shuffled)
    second = baseline.run_baseline(shuffled, source=source, coverage=coverage)
    assert first == second
    assert (purchases, source, coverage) == original
    json.dumps(first, allow_nan=False)


def test_future_values_cannot_change_development_fit_or_scores(purchases, source, coverage):
    first = baseline.run_baseline(purchases, source=source, coverage=coverage)
    changed = copy.deepcopy(purchases)
    for row in changed:
        if row["order_date"] >= "2025-01-01":
            row["unit_price"] *= 7
            row["line_total"] *= 7
    second = baseline.run_baseline(changed, source=source, coverage=coverage)
    assert first["metadata"]["training"] == second["metadata"]["training"]
    assert first["periods"]["development"] == second["periods"]["development"]


def test_post_delivery_fields_never_enter_model(purchases, source, coverage, estimators):
    first = baseline.run_baseline(purchases, source=source, coverage=coverage)
    for row in purchases:
        row.update(actual_delivery_date="irrelevant", quality_rejected={"ignored": True})
    second = baseline.run_baseline(purchases, source=source, coverage=coverage)
    assert first == second


def test_eligible_duplicates_retain_occurrences_in_scoring_and_ranking(
    purchases, source, coverage, monkeypatch,
):
    class DynamicEstimator(RecordingEstimator):
        def score_samples(self, frame):
            self.scored.append(np.asarray(frame).copy())
            return np.full(len(frame), -.4)

    monkeypatch.setattr(baseline, "IsolationForest", DynamicEstimator)
    purchases.append(copy.deepcopy(next(row for row in purchases if row["po_id"] == "D-A")))
    result = baseline.run_baseline(purchases, source=source, coverage=coverage)
    development = result["periods"]["development"]
    assert result["metadata"]["training"]["rows"] == development["eligible"] == 3
    assert [(row["po_id"], row["occurrence"], row["rank"]) for row in development["ranking"]] == [
        ("D-A", 1, 1), ("D-A", 2, 2), ("D-B", 1, 3),
    ]
    assert development["upper_tails"]["p95"]["count"] == 3


def test_empty_later_periods_are_not_scored(purchases, source, coverage, estimators):
    purchases = [row for row in purchases if row["order_date"] < "2025-01-01"]
    result = baseline.run_baseline(purchases, source=source, coverage=coverage)
    assert len(estimators[0].scored) == 1
    for name in ("validation_2025", "retrospective_2026"):
        period = result["periods"][name]
        assert period["rows"] == period["eligible"] == period["excluded"] == 0
        assert period["ranking"] == []
        assert period["statistics"] is None
        for tail in period["upper_tails"].values():
            assert tail["count"] == 0 and tail["fraction"] is None


@pytest.mark.parametrize("fault", ["width", "order"])
def test_estimator_fitted_feature_contract_is_checked_before_scoring(
    purchases, source, coverage, monkeypatch, fault,
):
    class WrongFeatureEstimator(RecordingEstimator):
        def fit(self, frame):
            super().fit(frame)
            if fault == "width":
                self.n_features_in_ = 6
            else:
                self.feature_names_in_ = self.feature_names_in_[::-1]
            return self

        def score_samples(self, frame):
            raise AssertionError("Incompatible fitted model must never score")

    monkeypatch.setattr(baseline, "IsolationForest", WrongFeatureEstimator)
    with pytest.raises(baseline.BaselineError, match="fitted_feature_contract"):
        baseline.run_baseline(purchases, source=source, coverage=coverage)
