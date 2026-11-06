"""P5.11 comparison contracts: synthetic inputs and a non-training score double."""

import builtins
import copy
import io
import json
import math
import random
import socket

import numpy as np
import pytest

from ml.procurement_v2 import baseline, comparison
from ml.procurement_v2.batch import MATRIX_FEATURES


@pytest.fixture
def source():
    return {
        "source_id": "procurement-spend", "source_version": "comparison-fixture-v1",
        "entity_namespace": "synthetic-comparison", "origin": "synthetic",
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

    def line(po_id, day, price=10, quantity=10, supplier="SUP-A", unit="Operations"):
        return {
            **identity, "po_id": po_id, "order_date": day,
            "supplier_id": supplier, "item": "Steel (kg)", "business_unit": unit,
            "category": "Raw Materials", "unit_price": price, "quantity": quantity,
            "line_total": price * quantity,
        }

    result = []
    for prefix, day in (("H0", "2023-01-01"), ("H1", "2024-12-01"), ("H2", "2025-12-01")):
        result.extend(line(f"{prefix}-{i:02d}", day) for i in range(20))
    for prefix, day in (("D", "2023-04-01"), ("V", "2025-01-01"), ("R", "2026-01-01")):
        result.extend([
            line(f"{prefix}-A", day, price=20),
            line(f"{prefix}-B", day, quantity=30, supplier="SUP-B", unit="R&D"),
            line(f"{prefix}-C", day, price=5, supplier="SUP-C"),
            line(f"{prefix}-D", day),
        ])
    return result


@pytest.fixture(autouse=True)
def score_double(monkeypatch):
    class SyntheticEstimator:
        def __init__(self, **parameters):
            pass

        def fit(self, frame):
            self.n_features_in_ = len(frame.columns)
            self.feature_names_in_ = np.array(frame.columns)
            self.max_samples_ = min(256, len(frame))
            self.offset_ = -.5
            return self

        def score_samples(self, frame):
            price, quantity = frame.iloc[:, 0], frame.iloc[:, 1]
            return -np.where(price > 1, .9, np.where(price < 1, .8, np.where(quantity > 1, .2, .1)))

    monkeypatch.setattr(baseline, "IsolationForest", SyntheticEstimator)


@pytest.fixture
def result(purchases, source, coverage):
    return baseline.run_baseline(purchases, source=source, coverage=coverage)


@pytest.mark.parametrize(("price", "quantity", "expected"), [
    (1, 1, 0), (2, 1, .6931471805599453), (.5, 1, .6931471805599453),
    (1, 4, 1.3862943611198906), (1, .25, 1.3862943611198906),
    (2, 4, 1.3862943611198906), (.5, .25, 1.3862943611198906),
    (1e300, 1e-300, 690.7755278982137),
    (1.000000000001, 1, 1.000088900581841e-12),
])
def test_deviation_uses_largest_symmetric_multiplicative_distance(price, quantity, expected):
    assert comparison.commercial_deviation(price, quantity) == pytest.approx(expected, rel=1e-12, abs=0)


@pytest.mark.parametrize("value", [None, True, False, "2", [], {}, 0, -1, float("nan"), float("inf"), -float("inf")])
@pytest.mark.parametrize("position", [0, 1])
def test_missing_invalid_or_nonfinite_ratio_is_never_imputed(value, position):
    arguments = [1, 1]
    arguments[position] = value
    with pytest.raises(comparison.ComparisonError):
        comparison.commercial_deviation(*arguments)


def test_comparison_uses_identical_population_with_correct_overlap_and_denominators(result, purchases, source, coverage):
    report = comparison.compare_methods(result, purchases, source=source, coverage=coverage, k=2)
    for period, prefix in (("development", "D"), ("validation_2025", "V"), ("retrospective_2026", "R")):
        selected = report["periods"][period]
        assert selected["eligible"] == 4 and selected["k"] == 2
        assert [row["po_id"] for row in selected["top_a"]] == [f"{prefix}-A", f"{prefix}-C"]
        assert [row["po_id"] for row in selected["top_b"]] == [f"{prefix}-B", f"{prefix}-A"]
        assert selected["overlap"]["count"] == 1
        assert selected["overlap"]["fraction"] == .5
        assert selected["overlap"]["jaccard"] == pytest.approx(1 / 3)
        assert [row["po_id"] for row in selected["exclusive_a"]] == [f"{prefix}-C"]
        assert [row["po_id"] for row in selected["exclusive_b"]] == [f"{prefix}-B"]
        groups = {row["name"]: row for row in selected["groups"]["supplier_id"]}
        assert groups["SUP-B"]["eligible"] == 1
        assert groups["SUP-B"]["a"] == 0 and groups["SUP-B"]["b"] == 1
        assert groups["SUP-B"]["population_share"] == .25
        assert groups["SUP-B"]["b_share"] == .5
        assert groups["SUP-B"]["b_selection_rate"] == 1
        assert selected["top_b"][0]["score"] == pytest.approx(1.0986122886681098)
        assert selected["top_b"][0]["features"][MATRIX_FEATURES[1]] == 3
    assert report["metadata"]["calibration"] == "none"
    assert report["excluded_operations"] == result["excluded_operations"]
    json.dumps(report, allow_nan=False)


def test_ties_preserve_occurrences_and_expose_boundary_tie(result, purchases, source, coverage):
    purchases.append(copy.deepcopy(next(row for row in purchases if row["po_id"] == "D-A")))
    result = baseline.run_baseline(purchases, source=source, coverage=coverage)
    report = comparison.compare_methods(result, purchases, source=source, coverage=coverage, k=2)
    period = report["periods"]["development"]
    assert period["eligible"] == 5
    assert [(row["po_id"], row["occurrence"]) for row in period["top_a"]] == [("D-A", 1), ("D-A", 2)]
    assert [(row["po_id"], row["occurrence"]) for row in period["top_b"]] == [("D-B", 1), ("D-A", 1)]
    assert period["boundary_ties"]["b"]["tied"] == 3
    assert period["boundary_ties"]["b"]["selected_tied"] == 1
    assert period["overlap"]["count"] == 1


def test_order_independence_and_no_input_mutation(result, purchases, source, coverage):
    original = copy.deepcopy((result, purchases, source, coverage))
    first = comparison.compare_methods(result, purchases, source=source, coverage=coverage, k=3)
    shuffled = copy.deepcopy(purchases)
    random.Random(119).shuffle(shuffled)
    second = comparison.compare_methods(result, shuffled, source=source, coverage=coverage, k=3)
    assert first == second
    assert (result, purchases, source, coverage) == original


def test_later_extremes_cannot_calibrate_or_change_development_comparison(result, purchases, source, coverage):
    first = comparison.compare_methods(result, purchases, source=source, coverage=coverage, k=2)
    changed = copy.deepcopy(purchases)
    for row in changed:
        if row["order_date"] >= "2025-01-01":
            row["unit_price"] *= 100
            row["line_total"] *= 100
    later_result = baseline.run_baseline(changed, source=source, coverage=coverage)
    second = comparison.compare_methods(later_result, changed, source=source, coverage=coverage, k=2)
    assert first["periods"]["development"] == second["periods"]["development"]
    assert second["metadata"]["calibration"] == "none"


def test_post_delivery_fields_do_not_change_comparison(result, purchases, source, coverage):
    first = comparison.compare_methods(result, purchases, source=source, coverage=coverage)
    for row in purchases:
        row.update(quality_rejected={"unusable": True}, actual_delivery_date="not used")
    assert first == comparison.compare_methods(result, purchases, source=source, coverage=coverage)


def test_comparator_ignores_context_frequency_features(result, purchases, source, coverage):
    first = comparison.compare_methods(result, purchases, source=source, coverage=coverage, k=2)
    changed = copy.deepcopy(purchases)
    for row in changed:
        if row["po_id"].endswith("-A"):
            row["supplier_id"] = "NEW-SUPPLIER"
            row["business_unit"] = "NEW-UNIT"
    context_result = baseline.run_baseline(changed, source=source, coverage=coverage)
    second = comparison.compare_methods(context_result, changed, source=source, coverage=coverage, k=2)
    for period in ("development", "validation_2025", "retrospective_2026"):
        original = first["periods"][period]["top_b"]
        revised = second["periods"][period]["top_b"]
        assert [(r["po_id"], r["score"]) for r in original] == [(r["po_id"], r["score"]) for r in revised]
        assert original[1]["features"][MATRIX_FEATURES[3]] == 20
        assert revised[1]["features"][MATRIX_FEATURES[3]] == 0
        assert revised[1]["features"][MATRIX_FEATURES[4]] == 0


@pytest.mark.parametrize("fault", ["feature_order", "parameter", "matrix_hash", "source", "training_period", "convention"])
def test_incompatible_baseline_metadata_refuses_comparison(result, purchases, source, coverage, fault):
    metadata = result["metadata"]
    if fault == "feature_order":
        metadata["feature_names"].reverse()
    elif fault == "parameter":
        metadata["parameters"]["n_estimators"] = 100
    elif fault == "matrix_hash":
        metadata["training"]["matrix_sha256"] = "0" * 64
    elif fault == "source":
        metadata["source"]["source_version"] = "other"
    elif fault == "training_period":
        metadata["training"]["period"] = "validation_2025"
    else:
        metadata["score_convention"] = "score_samples"
    with pytest.raises(comparison.ComparisonError):
        comparison.compare_methods(result, purchases, source=source, coverage=coverage)


@pytest.mark.parametrize("metadata", [None, [], "untrusted"])
def test_malformed_metadata_is_an_explicit_validation_error(result, purchases, source, coverage, metadata):
    result["metadata"] = metadata
    with pytest.raises(comparison.ComparisonError):
        comparison.compare_methods(result, purchases, source=source, coverage=coverage)


@pytest.mark.parametrize("fault", ["missing_row", "duplicate_row", "wrong_id", "wrong_date", "wrong_occurrence", "wrong_feature", "nan_score", "wrong_category", "wrong_count"])
def test_rank_population_and_score_associations_are_checked(result, purchases, source, coverage, fault):
    period = result["periods"]["validation_2025"]
    ranking = period["ranking"]
    if fault == "missing_row":
        ranking.pop()
    elif fault == "duplicate_row":
        ranking[1] = copy.deepcopy(ranking[0])
    elif fault == "wrong_id":
        ranking[0]["po_id"] = "UNKNOWN"
    elif fault == "wrong_date":
        ranking[0]["order_date"] = "2024-01-01"
    elif fault == "wrong_occurrence":
        ranking[0]["occurrence"] = 2
    elif fault == "wrong_feature":
        ranking[0]["features"][MATRIX_FEATURES[0]] += .25
    elif fault == "nan_score":
        ranking[0]["score"] = math.nan
    elif fault == "wrong_category":
        ranking[0]["category"] = "Other"
    else:
        period["eligible"] += 1
    with pytest.raises(comparison.ComparisonError):
        comparison.compare_methods(result, purchases, source=source, coverage=coverage)


@pytest.mark.parametrize("k", [0, -1, True, 1.5, "30", None])
def test_invalid_review_budget_is_rejected(result, purchases, source, coverage, k):
    with pytest.raises(comparison.ComparisonError):
        comparison.compare_methods(result, purchases, source=source, coverage=coverage, k=k)


def test_empty_period_and_budget_larger_than_population(result, purchases, source, coverage):
    report = comparison.compare_methods(result, purchases, source=source, coverage=coverage)
    empty = report["periods"]["warmup"]
    assert empty["eligible"] == empty["k"] == 0
    assert empty["top_a"] == empty["top_b"] == []
    assert empty["overlap"]["count"] == 0
    assert empty["overlap"]["fraction"] is None
    assert empty["overlap"]["jaccard"] is None
    assert report["periods"]["development"]["k"] == 4


def test_profiles_report_signed_directions_separately_from_magnitude(result, purchases, source, coverage):
    period = comparison.compare_methods(result, purchases, source=source, coverage=coverage, k=2)["periods"]["development"]
    population = period["profiles"]["population"]
    assert population["directions"]["price"] == {"below": 1, "equal": 2, "above": 1}
    assert population["directions"]["quantity"] == {"below": 0, "equal": 3, "above": 1}
    assert population["features"][MATRIX_FEATURES[0]]["median"] == 1
    assert population["rule_dominance"] == {"price": 2, "quantity": 1, "equal": 1}
    assert period["profiles"]["a"]["directions"]["price"] == {"below": 1, "equal": 0, "above": 1}
    assert period["profiles"]["b"]["directions"]["quantity"] == {"below": 0, "equal": 1, "above": 1}
    assert period["profiles"]["both"]["n"] == 1


def test_insufficient_machinery_history_remains_excluded_from_both_methods(purchases, source, coverage):
    unknown = copy.deepcopy(next(row for row in purchases if row["po_id"] == "D-A"))
    unknown.update(po_id="MACHINE", item="CNC", category="Machinery")
    purchases.append(unknown)
    result = baseline.run_baseline(purchases, source=source, coverage=coverage)
    report = comparison.compare_methods(result, purchases, source=source, coverage=coverage)
    period = report["periods"]["development"]
    machine = next(row for row in period["groups"]["category"] if row["name"] == "Machinery")
    assert (machine["total"], machine["eligible"], machine["excluded"]) == (1, 0, 1)
    assert machine["a"] == machine["b"] == 0
    assert machine["a_selection_rate"] is machine["b_selection_rate"] is None
    excluded = next(row for row in report["excluded_operations"] if row["po_id"] == "MACHINE")
    assert excluded["reasons"] == ["insufficient_history"]
    assert "score" not in excluded


def test_comparison_never_opens_files_connects_or_trains(result, purchases, source, coverage, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("comparison must remain pure")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(io, "open", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(baseline, "IsolationForest", forbidden)
    monkeypatch.setattr(baseline, "run_baseline", forbidden)
    report = comparison.compare_methods(result, purchases, source=source, coverage=coverage, k=2)
    assert report["periods"]["development"]["overlap"]["count"] == 1
