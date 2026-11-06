"""Controlled-injection contracts: synthetic histories, no real estimator fit."""

import copy
import random
from datetime import date, timedelta
from decimal import Decimal

import numpy as np
import pytest

from ml.procurement_v2 import features, injections
from ml.procurement_v2.batch import MATRIX_FEATURES, prepare_batch


@pytest.fixture
def source():
    return {
        "source_id": "procurement-spend", "source_version": "injections-fixture-v1",
        "entity_namespace": "synthetic-injections", "origin": "synthetic",
        "monetary_unit": "unspecified_source_unit",
        "temporal_assumption": "available_at_order_no_revisions",
    }


@pytest.fixture
def coverage(source):
    return {
        **{k: source[k] for k in ("source_id", "source_version", "entity_namespace")},
        "start_date": "2023-01-01", "end_date": "2026-06-30", "complete": True,
    }


def line(source, po_id, day, price=10, quantity=10, **changes):
    price = Decimal(str(price))
    return {
        **{k: source[k] for k in ("source_id", "source_version", "entity_namespace")},
        "po_id": po_id, "order_date": day, "supplier_id": "SUP-A", "item": "Steel (kg)",
        "business_unit": "Operations", "category": "Materials", "unit_price": price,
        "quantity": quantity, "line_total": price * quantity, **changes,
    }


@pytest.fixture
def operation(source):
    return line(source, "CURRENT", "2025-04-01", "6.07", 25)


@pytest.fixture
def history(source):
    return [line(source, f"H-{i:02d}", (date(2025, 3, 1) + timedelta(days=i)).isoformat(), i + 1, i + 1)
            for i in range(20)]


@pytest.mark.parametrize(("scenario", "price", "quantity", "total"), [
    ("A", "9.105", 25, "227.625"), ("B", "12.14", 25, "303.50"),
    ("C", "6.07", 75, "455.25"), ("D", "6.07", 3, "18.21"),
    ("E", "9.105", 75, "682.875"),
])
def test_injection_preserves_identity_and_exact_decimal_total(operation, source, scenario, price, quantity, total):
    original = copy.deepcopy(operation)
    changed = injections.inject(operation, scenario, source=source)
    assert changed["unit_price"] == Decimal(price)
    assert changed["quantity"] == quantity and type(changed["quantity"]) is int
    assert changed["line_total"] == Decimal(total)
    for key in operation.keys() - {"unit_price", "quantity", "line_total"}:
        assert changed[key] == operation[key]
    assert operation == original
    assert changed == injections.inject(operation, scenario, source=source)


@pytest.mark.parametrize(("quantity", "expected"), [(1, None), (2, 1), (14, 1), (15, 2), (25, 3)])
def test_reduction_uses_half_up_and_unchanged_quantity_is_not_applicable(source, quantity, expected):
    current = line(source, "Q", "2025-04-01", quantity=quantity)
    changed = injections.inject(current, "D", source=source)
    if expected is None:
        assert changed is None
    else:
        assert changed["quantity"] == expected


@pytest.mark.parametrize("quantity", [True, 0, -1, 1.5, "10"])
def test_invalid_original_quantity_is_rejected(operation, source, quantity):
    operation["quantity"] = quantity
    with pytest.raises(ValueError):
        injections.inject(operation, "A", source=source)


def test_invalid_scenario_and_original_total_are_rejected(operation, source):
    with pytest.raises(ValueError):
        injections.inject(operation, "F", source=source)
    operation["line_total"] += 1
    with pytest.raises(ValueError):
        injections.inject(operation, "A", source=source)


@pytest.mark.parametrize("scenario", ["A", "B", "C", "D", "E"])
@pytest.mark.parametrize("kind", ["varying", "zero_iqr", "unseen_pair", "nineteen_rows"])
def test_frozen_references_match_full_single_preparer(operation, history, source, coverage, scenario, kind):
    if kind == "zero_iqr":
        history = [line(source, f"H-{i:02d}", "2025-03-01", 10, 10) for i in range(20)]
    elif kind == "unseen_pair":
        operation["supplier_id"] = "NEW"
    elif kind == "nineteen_rows":
        history = history[:19]
    # Current-day and future observations must not contribute even when extreme.
    history += [line(source, "SAME-DAY", operation["order_date"], 999999, 999999),
                line(source, "FUTURE", "2025-04-02", 888888, 888888)]
    reference = features.prepare_features(operation, history, source=source, coverage=coverage)
    saved = copy.deepcopy((operation, history, reference))
    changed = injections.inject(operation, scenario, source=source)
    actual = injections.counterfactual_features(operation, changed, reference, source=source)
    expected = features.prepare_features(changed, history, source=source, coverage=coverage)
    assert actual == expected
    assert (operation, history, reference) == saved
    assert actual["window"] == reference["window"]
    assert actual["support"] == reference["support"]
    assert actual["diagnostics"] == reference["diagnostics"]
    assert tuple(actual["features"]) == features.FEATURE_NAMES
    for name in MATRIX_FEATURES[2:]:
        assert actual["features"][name] == reference["features"][name]


@pytest.mark.parametrize("field", ["supplier_id", "item", "business_unit", "order_date", "po_id"])
def test_counterfactual_cannot_change_noncommercial_identity(operation, history, source, coverage, field):
    reference = features.prepare_features(operation, history, source=source, coverage=coverage)
    changed = injections.inject(operation, "A", source=source)
    changed[field] = "2025-04-02" if field == "order_date" else "DIFFERENT"
    with pytest.raises(ValueError):
        injections.counterfactual_features(operation, changed, reference, source=source)


@pytest.mark.parametrize("fault", ["identity", "date", "contract", "source"])
def test_counterfactual_refuses_reference_from_another_operation(operation, history, source, coverage, fault):
    reference = features.prepare_features(operation, history, source=source, coverage=coverage)
    if fault == "identity":
        reference["operation_id"] = "OTHER"
    elif fault == "date":
        reference["cutoff_date"] = "2025-04-02"
    elif fault == "contract":
        reference["contract"] = "future/99"
    else:
        reference["source"]["source_version"] = "OTHER"
    changed = injections.inject(operation, "A", source=source)
    with pytest.raises(ValueError):
        injections.counterfactual_features(operation, changed, reference, source=source)


@pytest.fixture
def population(source):
    rows = []
    for prefix, history_day, current_day in (
        ("D", "2024-03-01", "2024-04-01"),
        ("V", "2025-03-01", "2025-04-01"),
        ("R", "2026-03-01", "2026-04-01"),
    ):
        for item in ("Steel (kg)", "Pipe (m)"):
            rows += [line(source, f"{prefix}-{item}-H{i}", history_day, i + 1, i + 1, item=item)
                     for i in range(20)]
            rows += [line(source, f"{prefix}-{item}-C{i}", current_day, 10 + i, i + 1, item=item)
                     for i in range(8)]
    return rows


def test_selection_is_deterministic_stratified_and_independent_of_input_order(population, source, coverage):
    batch = prepare_batch(population, source=source, coverage=coverage)
    before = copy.deepcopy((population, batch))
    selected = injections.select_operations(population, batch, seed=42, per_item=5)
    shuffled = copy.deepcopy(population)
    random.Random(19).shuffle(shuffled)
    shuffled_batch = prepare_batch(shuffled, source=source, coverage=coverage)
    assert injections.select_operations(shuffled, shuffled_batch, seed=42, per_item=5) == selected
    assert len(selected) == 20
    assert {row["period"] for row in selected} == {"validation_2025", "retrospective_2026"}
    assert len({(row["po_id"], row["order_date"], row["occurrence"]) for row in selected}) == 20
    for period in ("validation_2025", "retrospective_2026"):
        for item in ("Steel (kg)", "Pipe (m)"):
            assert sum(row["period"] == period and row["item"] == item for row in selected) == 5
    assert (population, batch) == before


def test_selection_retains_all_members_when_stratum_smaller_than_budget(population, source, coverage):
    batch = prepare_batch(population, source=source, coverage=coverage)
    selected = injections.select_operations(population, batch, seed=42, per_item=10)
    assert len(selected) == 32


@pytest.mark.parametrize(("old", "new", "expected"), [
    ((-.7, "B", "2025-01-01", 1), (-.95, "B", "2025-01-01", 1), 1),
    ((-.7, "B", "2025-01-01", 1), (-.1, "B", "2025-01-01", 1), 3),
    ((-.7, "B", "2025-01-01", 1), (-.7, "B", "2025-01-01", 1), 2),
    ((-.7, "B", "2025-01-01", 1), (-.9, "B", "2025-01-01", 1), 2),
])
def test_replacement_rank_removes_only_original_and_keeps_peers_fixed(old, new, expected):
    population_keys = [(-.9, "A", "2025-01-01", 1), (-.7, "B", "2025-01-01", 1),
                       (-.2, "C", "2025-01-01", 1)]
    before = list(population_keys)
    assert injections.replacement_rank(population_keys, old, new) == expected
    assert population_keys == before


def test_replacement_rank_keeps_duplicate_occurrences():
    population_keys = [(-.9, "A", "2025-01-01", 1), (-.7, "A", "2025-01-01", 2)]
    assert injections.replacement_rank(population_keys, population_keys[1], (-.9, "A", "2025-01-01", 2)) == 2
    with pytest.raises(ValueError):
        injections.replacement_rank(population_keys, (-.8, "MISSING", "2025-01-01", 1), population_keys[0])


def test_metrics_exclude_nonapplicable_cases_from_effect_denominator():
    rows = [
        {"period": "validation_2025", "scenario": "D", "method": "IF", "category": "Materials",
         "applicable": applicable, "score_before": before, "score_after": after,
         "rank_before": 4, "rank_after": rank}
        for applicable, before, after, rank in (
            (True, .2, .8, 1), (True, .8, .2, 6), (True, .5, .5, 4), (False, .1, None, None),
        )
    ]
    reports = injections.summarize_pairs(rows, {"IF": {"p95": .5, "p99": .75}, "B": {"p95": 1, "p99": 2}})
    overall = next(row for row in reports if row["category"] is None)
    assert (overall["selected"], overall["valid"], overall["not_applicable"]) == (4, 3, 1)
    assert (overall["increased"], overall["equal"], overall["decreased"]) == (1, 1, 1)
    assert overall["increased_pct"] == pytest.approx(100 / 3)
    assert overall["delta"]["mean"] == pytest.approx(0)
    assert overall["absolute_delta"]["mean"] == pytest.approx(.4)
    assert overall["p95_before_pct"] == overall["p95_after_pct"] == pytest.approx(200 / 3)


class ScoreOnlyEstimator:
    n_features_in_ = 5
    feature_names_in_ = np.array(MATRIX_FEATURES)

    def score_samples(self, frame):
        assert list(frame.columns) == list(MATRIX_FEATURES)
        return -np.asarray(frame.iloc[:, 0], dtype=float) / 10


def test_experiment_uses_fitted_estimator_and_preserves_original_batch(population, source, coverage):
    batch = prepare_batch(population, source=source, coverage=coverage)
    original = copy.deepcopy((population, batch))
    result = injections.run_experiment(ScoreOnlyEstimator(), population, source=source, coverage=coverage,
                                      seed=42, per_item=2)
    assert len(result["selection"]) == 8
    assert len(result["pairs"]) == 8 * 5 * 2
    assert {row["method"] for row in result["pairs"]} == {"IF", "B"}
    assert (population, batch) == original
    development = batch["matrices"]["development"]["values"]
    expected_p95 = float(np.quantile([row[0] / 10 for row in development], .95, method="linear"))
    assert result["references"]["IF"]["p95"] == expected_p95
    for row in result["pairs"]:
        if not row["applicable"]:
            assert row["score_after"] is None and row["rank_after"] is None
            continue
        price, quantity = row["features_after"][:2]
        expected = price / 10 if row["method"] == "IF" else max(abs(np.log(price)), abs(np.log(quantity)))
        assert row["score_after"] == pytest.approx(expected)


def test_separate_untrusted_batch_cannot_be_supplied(population, source, coverage):
    batch = prepare_batch(population, source=source, coverage=coverage)
    class MustNotScore(ScoreOnlyEstimator):
        def score_samples(self, frame):
            raise AssertionError("must reject before scoring")

    with pytest.raises(TypeError):
        injections.run_experiment(MustNotScore(), population, batch, source=source, coverage=coverage)


def test_tampered_reference_feature_is_rejected(operation, history, source, coverage):
    reference = features.prepare_features(operation, history, source=source, coverage=coverage)
    reference["features"]["price_to_item_median_90d"] += 1
    changed = injections.inject(operation, "A", source=source)
    with pytest.raises(ValueError, match="original_reference_values"):
        injections.counterfactual_features(operation, changed, reference, source=source)


def test_later_data_cannot_change_development_references(population, source, coverage):
    first = injections.run_experiment(ScoreOnlyEstimator(), population,
                                     source=source, coverage=coverage, per_item=2)
    changed = copy.deepcopy(population)
    for row in changed:
        if row["order_date"] >= "2025-01-01":
            row["unit_price"] *= 100
            row["line_total"] *= 100
    second = injections.run_experiment(ScoreOnlyEstimator(), changed,
                                      source=source, coverage=coverage, per_item=2)
    assert first["references"] == second["references"]
    assert first["original_statistics"]["development"] == second["original_statistics"]["development"]
    assert first["selection"] == second["selection"]


@pytest.mark.parametrize("fault", ["width", "order", "nan", "output_length"])
def test_invalid_estimator_contract_and_outputs_refuse_experiment(population, source, coverage, fault):
    class InvalidEstimator(ScoreOnlyEstimator):
        def score_samples(self, frame):
            if fault == "nan":
                return np.full(len(frame), np.nan)
            if fault == "output_length":
                return np.zeros(len(frame) + 1)
            return super().score_samples(frame)

    model = InvalidEstimator()
    if fault == "width":
        model.n_features_in_ = 4
    elif fault == "order":
        model.feature_names_in_ = np.array(MATRIX_FEATURES[::-1])
    with pytest.raises(ValueError):
        injections.run_experiment(model, population, source=source, coverage=coverage)
