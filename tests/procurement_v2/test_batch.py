"""Batch contracts exercised only with artificial purchase lines in memory."""

import builtins
import copy
import io
import json
import random
import socket
from datetime import date, timedelta
from decimal import Decimal

import pytest

from ml.procurement_v2 import features
from ml.procurement_v2.batch import MATRIX_FEATURES, prepare_batch


@pytest.fixture
def source():
    return {
        "source_id": "procurement-spend", "source_version": "batch-fixture-v1",
        "entity_namespace": "synthetic-batch", "origin": "synthetic",
        "monetary_unit": "unspecified_source_unit",
        "temporal_assumption": "available_at_order_no_revisions",
    }


@pytest.fixture
def coverage(source):
    return {
        **{key: source[key] for key in ("source_id", "source_version", "entity_namespace")},
        "start_date": "2023-01-01", "end_date": "2026-06-30", "complete": True,
    }


def line(source, identity, day, price=10, quantity=1, **changes):
    return {
        **{key: source[key] for key in ("source_id", "source_version", "entity_namespace")},
        "po_id": identity, "order_date": day, "supplier_id": "SUP-A",
        "item": "Steel (kg)", "business_unit": "Operations", "category": "Materials",
        "unit_price": price, "quantity": quantity, "line_total": price * quantity,
        **changes,
    }


@pytest.fixture
def purchases(source):
    history = [line(source, f"H-{i:02d}", (date(2024, 3, 1) + timedelta(days=i - 1)).isoformat(),
                    i, 2 * i) for i in range(1, 21)]
    return history + [line(source, "CURRENT", "2024-04-01", 21, 42)]


def record(result, identity):
    return next(row for row in result["operations"]
                if row["feature_result"]["operation_id"] == identity)


def test_matrix_has_only_approved_numeric_columns_and_parallel_trace(purchases, source, coverage):
    result = prepare_batch(purchases, source=source, coverage=coverage)
    matrix = result["matrices"]["development"]
    assert list(MATRIX_FEATURES) == result["matrix_feature_names"] == [
        "price_to_item_median_90d", "quantity_to_item_median_90d",
        "item_price_relative_iqr_90d", "supplier_item_lines_90d", "business_unit_lines_90d",
    ]
    assert len(matrix["values"]) == 1
    assert matrix["values"][0] == pytest.approx([2, 2, 19 / 21, 20, 20])
    assert matrix["trace"] == [{
        "po_id": "CURRENT", "order_date": "2024-04-01", "occurrence": 1,
        "operation_index": 20,
    }]
    assert all(isinstance(value, (int, float)) for value in matrix["values"][0])
    current = record(result, "CURRENT")
    assert current["eligible"] and current["exclusion_reasons"] == []
    assert tuple(current["feature_result"]["features"]) == features.FEATURE_NAMES
    assert current["feature_result"]["features"]["total_to_item_median_90d"] == pytest.approx(882 / 221)
    assert result["summary"]["development"]["rows"] == 21
    assert result["summary"]["development"]["excluded"] == 20
    json.dumps(result, allow_nan=False)


def test_every_operation_matches_single_preparer(purchases, source, coverage):
    purchases += [line(source, "NEW", "2024-04-01", 10, 2, supplier_id="NEW-SUP"),
                  line(source, "OTHER", "2024-04-02", item="Another (litre)")]
    result = prepare_batch(purchases, source=source, coverage=coverage)
    for operation in purchases:
        assert record(result, operation["po_id"])["feature_result"] == features.prepare_features(
            operation, purchases, source=source, coverage=coverage,
        )


def test_order_independence_including_complete_serialized_result(purchases, source, coverage):
    baseline = prepare_batch(purchases, source=source, coverage=coverage)
    shuffled = copy.deepcopy(purchases)
    random.Random(31).shuffle(shuffled)
    assert json.dumps(prepare_batch(shuffled, source=source, coverage=coverage)) == json.dumps(baseline)


@pytest.mark.parametrize(("history_day", "expected"), [
    ("2024-01-01", 0), ("2024-01-02", 20), ("2024-03-31", 20),
    ("2024-04-01", 0), ("2024-04-02", 0),
])
def test_window_boundaries_exclude_whole_current_day(source, coverage, history_day, expected):
    rows = [line(source, f"H-{i}", history_day) for i in range(20)]
    rows.append(line(source, "CURRENT", "2024-04-01", 20, 2))
    current = record(prepare_batch(rows, source=source, coverage=coverage), "CURRENT")
    assert current["feature_result"]["support"]["item"] == expected
    assert current["eligible"] == (expected == 20)
    if expected == 20:
        # Zero price IQR blocks a diagnostic, never the five approved features.
        assert current["feature_result"]["features"]["price_iqr_distance_90d"] is None
        assert current["feature_result"]["unavailability"]["price_iqr_distance_90d"] == "zero_iqr"
        assert current["feature_result"]["features"]["item_price_relative_iqr_90d"] == 0


@pytest.mark.parametrize("count", [0, 1, 19, 20])
def test_support_threshold_and_explicit_exclusion(source, coverage, count):
    rows = [line(source, f"H-{i}", "2024-03-01") for i in range(count)]
    rows.append(line(source, "CURRENT", "2024-04-01"))
    current = record(prepare_batch(rows, source=source, coverage=coverage), "CURRENT")
    assert current["eligible"] == (count == 20)
    assert current["feature_result"]["support"]["item"] == count
    assert current["exclusion_reasons"] == ([] if count == 20 else ["insufficient_history"])


def test_future_changes_and_same_day_peers_do_not_change_past_results(purchases, source, coverage):
    baseline = prepare_batch(purchases, source=source, coverage=coverage)
    more = purchases + [line(source, "FUTURE", "2026-01-01", 999, 100),
                        line(source, "PEER", "2024-04-01", 999, 100)]
    changed = prepare_batch(more, source=source, coverage=coverage)
    assert record(changed, "CURRENT") == record(baseline, "CURRENT")
    assert record(changed, "PEER")["feature_result"]["diagnostics"] == record(changed, "CURRENT")["feature_result"]["diagnostics"]


def test_unavailable_pair_does_not_remove_eligible_product_reference(purchases, source, coverage):
    purchases[-1]["supplier_id"] = "UNSEEN"
    result = prepare_batch(purchases, source=source, coverage=coverage)
    current = record(result, "CURRENT")
    assert current["eligible"]
    assert result["matrices"]["development"]["values"][0][-2:] == [0, 20]
    assert current["feature_result"]["unavailability"]["price_to_supplier_item_median_90d"] == "insufficient_history"


def test_partial_coverage_keeps_records_and_reasons(purchases, source, coverage):
    coverage["complete"] = False
    result = prepare_batch(purchases, source=source, coverage=coverage)
    assert len(result["operations"]) == len(purchases)
    assert result["matrices"]["development"]["values"] == []
    assert all(row["exclusion_reasons"] == ["partial_window"] for row in result["operations"])
    assert record(result, "CURRENT")["feature_result"]["support"]["item"] == 20


def test_warmup_never_enters_matrix_even_with_complete_features(source, coverage):
    coverage["start_date"] = "2022-01-01"
    rows = [line(source, f"H-{i}", "2023-01-01") for i in range(20)]
    rows.append(line(source, "CURRENT", "2023-03-01"))
    result = prepare_batch(rows, source=source, coverage=coverage)
    current = record(result, "CURRENT")
    assert all(current["feature_result"]["features"][key] is not None for key in MATRIX_FEATURES)
    assert not current["eligible"]
    assert current["exclusion_reasons"] == ["warmup_period"]
    assert result["matrices"]["warmup"]["values"] == []


@pytest.mark.parametrize(("day", "period"), [
    ("2023-01-01", "warmup"), ("2023-03-31", "warmup"),
    ("2023-04-01", "development"), ("2024-12-31", "development"),
    ("2025-01-01", "validation_2025"), ("2025-12-31", "validation_2025"),
    ("2026-01-01", "retrospective_2026"), ("2026-06-30", "retrospective_2026"),
])
def test_approved_period_boundaries(source, coverage, day, period):
    result = prepare_batch([line(source, "X", day)], source=source, coverage=coverage)
    assert result["operations"][0]["period"] == period
    assert result["summary"][period]["rows"] == 1
    assert result["matrices"]["warmup"]["values"] == []


def test_duplicate_rows_preserve_multiplicity_and_trace(source, coverage):
    repeated = [line(source, "SAME", "2024-03-01") for _ in range(20)]
    rows = (repeated + [line(source, "CURRENT", "2024-04-01")])*2
    result = prepare_batch(rows, source=source, coverage=coverage)
    assert len(result["operations"]) == 42
    assert [r["occurrence"] for r in result["matrices"]["development"]["trace"]] == [1, 2]
    assert result["matrices"]["development"]["values"] == [[1, 1, 0, 40, 40]]*2
    assert prepare_batch(list(reversed(rows)), source=source, coverage=coverage) == result


def test_near_duplicates_with_different_ids_remain_separate(purchases, source, coverage):
    purchases.append({**purchases[-1], "po_id": "COPY", "order_date": "2024-04-02"})
    result = prepare_batch(purchases, source=source, coverage=coverage)
    assert len(result["operations"]) == 22
    assert record(result, "COPY")["feature_result"]["support"]["item"] == 21


@pytest.mark.parametrize("change", [
    {"unit_price": 15, "line_total": 15}, {"order_date": "2024-03-02"},
    {"supplier_id": "OTHER"}, {"category": "Other"},
])
def test_ambiguous_ids_fail_instead_of_deduplicating(source, coverage, change):
    first = line(source, "SAME", "2024-03-01")
    with pytest.raises(features.FeatureValidationError, match="conflicting_identity"):
        prepare_batch([first, {**first, **change}], source=source, coverage=coverage)


def test_decimal_conflicts_are_not_hidden_by_float_precision(source, coverage):
    first = line(source, "SAME", "2024-03-01", Decimal("1.0"))
    second = line(source, "SAME", "2024-03-01", Decimal("1.0000000000000001"))
    with pytest.raises(features.FeatureValidationError, match="conflicting_identity"):
        prepare_batch([first, second], source=source, coverage=coverage)


@pytest.mark.parametrize(("field", "value"), [
    ("unit_price", None), ("quantity", 0), ("line_total", 123),
    ("order_date", "2024-02-30"), ("source_version", "other"),
    ("category", ["invalid"]), ("unit_price", float("inf")),
])
def test_invalid_rows_fail_the_batch_without_partial_matrix(source, coverage, field, value):
    row = line(source, "X", "2024-04-01")
    row[field] = value
    with pytest.raises(features.FeatureValidationError):
        prepare_batch([row], source=source, coverage=coverage)


@pytest.mark.parametrize("rows", [None, {}, "rows", False, [None]])
def test_absent_or_invalid_batch_is_not_known_empty_history(source, coverage, rows):
    with pytest.raises(features.FeatureValidationError):
        prepare_batch(rows, source=source, coverage=coverage)


def test_empty_batch_is_explicit_and_has_no_eligible_rows(source, coverage):
    result = prepare_batch([], source=source, coverage=coverage)
    assert result["operations"] == []
    assert all(m["values"] == m["trace"] == [] for m in result["matrices"].values())
    assert all(s["rows"] == s["eligible"] == s["excluded"] == 0 for s in result["summary"].values())


def test_missing_category_remains_unidentified(source, coverage):
    row = line(source, "X", "2024-04-01")
    del row["category"]
    result = prepare_batch([row], source=source, coverage=coverage)
    assert result["operations"][0]["category"] is None
    assert result["summary"]["development"]["by_category"][0]["category"] is None


def test_category_summary_reconciles_exclusions_without_counting_features_twice(purchases, source, coverage):
    result = prepare_batch(purchases, source=source, coverage=coverage)
    assert result["summary"]["development"]["by_category"] == [{
        "category": "Materials", "rows": 21, "eligible": 1, "excluded": 20,
        "exclusion_reasons": {"insufficient_history": 20},
    }]


def test_outcome_fields_do_not_affect_batch(purchases, source, coverage):
    baseline = prepare_batch(purchases, source=source, coverage=coverage)
    for row in purchases:
        row.update(actual_delivery_date="not inspected", quality_rejected={"anything": True},
                   on_contract=False, promised_delivery_date=None)
    assert prepare_batch(purchases, source=source, coverage=coverage) == baseline


def test_io_is_forbidden_and_inputs_outputs_do_not_alias(purchases, source, coverage, monkeypatch):
    before = copy.deepcopy((purchases, source, coverage))

    def forbidden(*args, **kwargs):
        raise AssertionError("I/O forbidden")

    with monkeypatch.context() as p:
        for obj, attr in ((builtins, "open"), (io, "open"), (socket, "create_connection"),
                          (socket.socket, "connect")):
            p.setattr(obj, attr, forbidden)
        result = prepare_batch(purchases, source=source, coverage=coverage)
    result["source"]["source_version"] = "changed"
    result["coverage"]["complete"] = False
    result["operations"][-1]["feature_result"]["diagnostics"]["item"]["unit_price"]["median"] = 99
    assert (purchases, source, coverage) == before


def test_shared_reference_outputs_are_independent(purchases, source, coverage):
    purchases.append({**purchases[-1], "po_id": "PEER"})
    result = prepare_batch(purchases, source=source, coverage=coverage)
    current, peer = record(result, "CURRENT"), record(result, "PEER")
    current["feature_result"]["diagnostics"]["item"]["unit_price"]["median"] = 999
    current["feature_result"]["support"]["item"] = 0
    current["feature_result"]["features"][MATRIX_FEATURES[0]] = 999
    assert peer["feature_result"]["diagnostics"]["item"]["unit_price"]["median"] == 10.5
    assert peer["feature_result"]["support"]["item"] == 20
    assert result["matrices"]["development"]["values"][0][0] == 2


def test_values_from_other_items_never_enter_reference(purchases, source, coverage):
    purchases += [line(source, f"O-{i}", "2024-03-01", 999999, 999,
                       item="Other material (litre)", business_unit="Another unit") for i in range(25)]
    result = prepare_batch(purchases, source=source, coverage=coverage)
    current = record(result, "CURRENT")["feature_result"]
    assert current["support"] == {
        "window": 45, "item": 20, "supplier": 45, "supplier_item": 20, "business_unit": 20,
    }
    assert current["features"][MATRIX_FEATURES[0]] == 2
    assert current["features"][MATRIX_FEATURES[1]] == 2


def test_references_are_shared_for_same_day_item_and_pair(source, coverage, monkeypatch):
    rows = [line(source, f"H-{i}", "2024-03-01") for i in range(20)]
    rows += [line(source, f"X-{i}", "2024-04-01") for i in range(10)]
    calls = []
    original = features._statistics

    def measured(rows, metric):
        calls.append((len(rows), metric))
        return original(rows, metric)

    monkeypatch.setattr(features, "_statistics", measured)
    result = prepare_batch(rows, source=source, coverage=coverage)
    assert len(result["matrices"]["development"]["values"]) == 10
    assert calls.count((20, "unit_price")) == 2  # item and supplier-item, not ten recomputations
    assert calls.count((20, "quantity")) == calls.count((20, "line_total")) == 1


@pytest.mark.parametrize("day", ["2022-12-31", "2026-07-01"])
def test_outside_approved_experiment_is_not_silently_assigned(source, coverage, day):
    with pytest.raises(features.FeatureValidationError, match="outside_experiment"):
        prepare_batch([line(source, "X", day)], source=source, coverage=coverage)


def test_rows_outside_declared_coverage_fail(source, coverage):
    coverage["start_date"] = "2024-03-02"
    with pytest.raises(features.FeatureValidationError, match="inconsistent_coverage"):
        prepare_batch([line(source, "X", "2024-03-01")], source=source, coverage=coverage)
