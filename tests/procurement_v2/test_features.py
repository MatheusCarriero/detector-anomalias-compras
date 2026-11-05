"""Pure Procurement V2 contracts; all observations are artificial and in memory."""

import builtins
import copy
import io
import json
import math
import random
import socket
from datetime import date, timedelta
from decimal import Decimal

import pytest

from ml.procurement_v2.features import (
    CONTRACT_VERSION,
    FEATURE_NAMES,
    FeatureValidationError,
    prepare_features,
)

NAMES = (
    "price_to_item_median_90d", "price_iqr_distance_90d",
    "item_price_relative_iqr_90d", "quantity_to_item_median_90d",
    "total_to_item_median_90d", "price_to_supplier_item_median_90d",
    "supplier_lines_90d", "supplier_item_lines_90d", "business_unit_lines_90d",
)


@pytest.fixture
def source():
    return {
        "source_id": "procurement-spend", "source_version": "fixture-v1",
        "origin": "synthetic", "entity_namespace": "synthetic-fixture",
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
def operation(source):
    return {
        **{key: source[key] for key in ("source_id", "source_version", "entity_namespace")},
        "po_id": "CURRENT", "order_date": "2024-04-01", "supplier_id": "SUP-A",
        "item": "Material A (unit A)", "business_unit": "Manufacturing",
        "unit_price": 21, "quantity": 42, "line_total": 882,
    }


@pytest.fixture
def history(operation):
    # Prices 1..20; quantities 2..40; totals 2,8,...,800.
    # Linear quartiles of price: 5.75,10.5,15.25; MAD=5.
    # Median(total)=221, NOT median(price)*median(quantity)=220.5.
    return [
        {
            **operation, "po_id": f"H-{i:02d}",
            "order_date": (date(2024, 3, 1) + timedelta(days=i - 1)).isoformat(),
            "unit_price": i, "quantity": 2 * i, "line_total": 2 * i * i,
        }
        for i in range(1, 21)
    ]


def run(operation, history, source, coverage):
    return prepare_features(operation, history, source=source, coverage=coverage)


def test_nine_formulas_order_and_traceability(operation, history, source, coverage):
    result = run(operation, history, source, coverage)
    assert tuple(result["features"]) == tuple(result["feature_names"]) == FEATURE_NAMES == NAMES
    assert list(result["features"].values()) == pytest.approx(
        [2, 21 / 19, 19 / 21, 2, 882 / 221, 2, 20, 20, 20]
    )
    assert result["unavailability"] == dict.fromkeys(NAMES)
    assert result["operation_id"] == "CURRENT"
    assert result["contract"] == CONTRACT_VERSION
    assert result["source"] == source
    assert result["cutoff_date"] == "2024-04-01"
    assert result["window"] == {
        "start": "2024-01-02", "end": "2024-04-01", "end_exclusive": True,
    }
    assert result["coverage"]["status"] == "complete"
    assert result["support"] == {
        "window": 20, "item": 20, "supplier": 20, "supplier_item": 20, "business_unit": 20,
    }
    assert result["diagnostics"]["item"]["unit_price"] == {
        "median": 10.5, "q1": 5.75, "q3": 15.25, "iqr": 9.5, "mad": 5,
    }
    assert result["diagnostics"]["item"]["line_total"]["median"] == 221
    assert result["diagnostics"]["item"]["quantity"] == {
        "median": 21, "q1": 11.5, "q3": 30.5, "iqr": 19, "mad": 10,
    }
    assert result["diagnostics"]["item"]["line_total"] == {
        "median": 221, "q1": 66.5, "q3": 465.5, "iqr": 399, "mad": 180,
    }
    json.dumps(result, allow_nan=False)
    assert not {"score", "risk", "fraud", "probability"} & result.keys()


def test_lower_boundary_included_and_same_day_future_excluded(operation, history, source, coverage):
    history[-1]["order_date"] = "2024-01-02"
    baseline = run(operation, history, source, coverage)
    ignored = [
        {**history[-1], "po_id": "OLD", "order_date": "2024-01-01"},
        dict(operation),
        {**history[-1], "po_id": "EARLIER-ID", "order_date": "2024-04-01"},
        {**history[-1], "po_id": "FUTURE", "order_date": "2024-04-02"},
    ]
    assert run(operation, history + ignored, source, coverage) == baseline
    history[-1]["order_date"] = "2024-01-01"
    result = run(operation, history, source, coverage)
    assert result["support"]["item"] == 19
    assert result["features"][NAMES[0]] is None
    assert result["unavailability"][NAMES[0]] == "insufficient_history"


def test_order_independence_and_future_content_invariance(operation, history, source, coverage):
    baseline = run(operation, history, source, coverage)
    shuffled = copy.deepcopy(history)
    random.Random(42).shuffle(shuffled)
    assert run(operation, shuffled, source, coverage) == baseline
    # Only the date is inspected outside the window. No future statistics/maps.
    future = {"order_date": "2026-01-01", "unit_price": math.inf, "supplier_id": None}
    assert run(operation, shuffled + [future], source, coverage) == baseline


def test_same_day_operations_have_identical_references(operation, history, source, coverage):
    other = {**operation, "po_id": "ANOTHER", "unit_price": 42, "line_total": 1764}
    first = run(operation, history + [operation, other], source, coverage)
    second = run(other, history + [other, operation], source, coverage)
    assert first["support"] == second["support"]
    assert first["diagnostics"] == second["diagnostics"]
    assert second["features"][NAMES[0]] == 4


@pytest.mark.parametrize("count", [0, 1, 19, 20])
def test_support_threshold_does_not_hide_counts(operation, history, source, coverage, count):
    result = run(operation, history[:count], source, coverage)
    assert result["support"]["item"] == count
    for name in NAMES[6:]:
        assert result["features"][name] == count
        assert result["unavailability"][name] is None
    for name in NAMES[:6]:
        if count < 20:
            assert result["features"][name] is None
            assert result["unavailability"][name] == "insufficient_history"
        else:
            assert result["features"][name] is not None


def test_absent_history_is_not_a_known_empty_population(operation, source, coverage):
    result = run(operation, None, source, coverage)
    assert result["features"] == dict.fromkeys(NAMES)
    assert result["unavailability"] == dict.fromkeys(NAMES, "missing_history")
    assert all(value is None for value in result["support"].values())


def test_zero_iqr_preserves_ratios_and_zero_dispersion(operation, history, source, coverage):
    constant = [{**row, "unit_price": 10, "quantity": 1, "line_total": 10} for row in history]
    current = {**operation, "unit_price": 20, "quantity": 2, "line_total": 40}
    result = run(current, constant, source, coverage)
    assert list(result["features"].values()) == [2, None, 0, 2, 4, 2, 20, 20, 20]
    assert result["unavailability"][NAMES[1]] == "zero_iqr"
    assert result["diagnostics"]["item"]["quantity"]["mad"] == 0


@pytest.mark.parametrize("change", [
    {"start_date": "2024-01-03"}, {"end_date": "2024-03-30"}, {"complete": False},
])
def test_partial_window_retains_support_but_no_ninety_day_features(
    operation, history, source, coverage, change,
):
    coverage.update(change)
    result = run(operation, history, source, coverage)
    assert result["coverage"]["status"] == "partial_window"
    assert result["features"] == dict.fromkeys(NAMES)
    assert result["unavailability"] == dict.fromkeys(NAMES, "partial_window")
    assert result["support"]["item"] == 20
    assert result["diagnostics"]["item"]["unit_price"] is None


def test_exact_coverage_until_previous_day_suffices(operation, history, source, coverage):
    coverage.update(start_date="2024-01-02", end_date="2024-03-31")
    result = run(operation, history, source, coverage)
    assert result["coverage"]["status"] == "complete"
    assert result["features"][NAMES[0]] == 2


def test_new_supplier_retains_item_reference_without_pair_fallback(operation, history, source, coverage):
    operation["supplier_id"] = "SUP-NEW"
    result = run(operation, history, source, coverage)
    assert result["features"][NAMES[0]] == 2
    assert result["features"][NAMES[5]] is None
    assert result["unavailability"][NAMES[5]] == "insufficient_history"
    assert result["features"][NAMES[6]] == result["features"][NAMES[7]] == 0


def test_pair_requires_own_twenty_observations(operation, history, source, coverage):
    history[-1]["supplier_id"] = "SUP-B"
    result = run(operation, history, source, coverage)
    assert result["support"]["item"] == 20
    assert result["support"]["supplier_item"] == 19
    assert result["features"][NAMES[0]] == 2
    assert result["features"][NAMES[5]] is None


def test_material_supplier_and_unit_counts_have_distinct_populations(
    operation, history, source, coverage,
):
    others = [
        {**history[0], "po_id": "X", "item": "Another material (unit B)", "unit_price": 999,
         "quantity": 1, "line_total": 999},
        {**history[0], "po_id": "Y", "supplier_id": "OTHER", "business_unit": "Other unit"},
    ]
    result = run(operation, history + others, source, coverage)
    assert result["support"] == {
        "window": 22, "item": 21, "supplier": 21, "supplier_item": 20, "business_unit": 21,
    }
    assert result["features"][NAMES[5]] == 2
    # No reference from another material even for a completely unseen item.
    operation["item"] = "Unseen"
    result = run(operation, history + others, source, coverage)
    assert result["features"][NAMES[0]] is None
    assert result["features"][NAMES[7]] == 0


def test_duplicate_lines_are_not_deduplicated(operation, history, source, coverage):
    repeated = [copy.deepcopy(history[0]) for _ in range(20)]
    result = run(operation, repeated, source, coverage)
    assert result["support"]["item"] == 20
    assert result["features"][NAMES[0]] == 21
    assert result["features"][NAMES[7]] == 20


def test_post_event_and_unapproved_fields_cannot_change_features(operation, history, source, coverage):
    baseline = run(operation, history, source, coverage)
    extras = {
        "actual_delivery_date": "not-a-date", "quality_rejected": {"untrusted": None},
        "promised_delivery_date": None, "payment_terms": "changed", "on_contract": None,
        "supplier_name": "Changed", "supplier_country": "Unknown", "category": "Changed",
    }
    current = {**operation, **extras}
    enriched = [{**row, **extras} for row in history]
    assert run(current, enriched, source, coverage) == baseline


def test_pure_computation_without_file_or_network_access(operation, history, source, coverage, monkeypatch):
    before = copy.deepcopy((operation, history, source, coverage))

    def forbidden(*args, **kwargs):
        raise AssertionError("I/O is forbidden")

    with monkeypatch.context() as patcher:
        for obj, attr in ((builtins, "open"), (io, "open"), (socket, "create_connection"),
                          (socket.socket, "connect")):
            patcher.setattr(obj, attr, forbidden)
        result = run(operation, history, source, coverage)
    assert (operation, history, source, coverage) == before
    result["source"]["source_version"] = "changed"
    result["coverage"]["start_date"] = "changed"
    assert (operation, history, source, coverage) == before


@pytest.mark.parametrize(("field", "bad"), [
    ("unit_price", None), ("unit_price", True), ("unit_price", "21"),
    ("unit_price", 0), ("unit_price", -1), ("unit_price", math.nan),
    ("unit_price", math.inf), ("unit_price", -math.inf), ("unit_price", 10**400),
    ("unit_price", Decimal("NaN")), ("unit_price", Decimal("1e-1000")),
    ("quantity", None), ("quantity", True), ("quantity", "42"), ("quantity", 42.0),
    ("quantity", -1), ("quantity", 0), ("quantity", math.inf),
    ("line_total", None), ("line_total", True), ("line_total", "882"),
    ("line_total", -1), ("line_total", math.nan), ("line_total", math.inf),
    ("po_id", None), ("supplier_id", ""), ("item", " "), ("business_unit", " unit"),
    ("supplier_id", 123), ("item", []), ("business_unit", "unit\n"),
    ("order_date", None), ("order_date", "2024-4-01"), ("order_date", "2023-02-29"),
    ("order_date", "2024-04-01T00:00:00"), ("order_date", date(2024, 4, 1)),
    ("source_id", "invoice"), ("source_version", "other"), ("entity_namespace", "other"),
])
def test_invalid_current_fields_are_rejected(operation, history, source, coverage, field, bad):
    operation[field] = bad
    with pytest.raises(FeatureValidationError):
        run(operation, history, source, coverage)


@pytest.mark.parametrize("field", [
    "po_id", "order_date", "supplier_id", "item", "business_unit",
    "unit_price", "quantity", "line_total", "source_id", "source_version", "entity_namespace",
])
def test_required_current_fields_are_not_inferred(operation, history, source, coverage, field):
    del operation[field]
    with pytest.raises(FeatureValidationError):
        run(operation, history, source, coverage)


@pytest.mark.parametrize(("field", "bad"), [
    ("unit_price", None), ("line_total", 999), ("supplier_id", None),
    ("source_id", "invoice"), ("source_version", "wrong"), ("entity_namespace", "wrong"),
    ("order_date", "invalid"), ("quantity", -1),
])
def test_selected_invalid_history_blocks_instead_of_dropping_rows(
    operation, history, source, coverage, field, bad,
):
    history[0][field] = bad
    with pytest.raises(FeatureValidationError):
        run(operation, history, source, coverage)


def test_current_id_cannot_reappear_as_an_earlier_reference(operation, history, source, coverage):
    history[0]["po_id"] = operation["po_id"]
    with pytest.raises(FeatureValidationError):
        run(operation, history, source, coverage)


def test_conflicting_versions_of_same_historical_line_are_rejected(
    operation, history, source, coverage,
):
    conflicting = {**history[0], "unit_price": 5, "line_total": 10}
    with pytest.raises(FeatureValidationError, match="conflicting_identity"):
        run(operation, history + [conflicting], source, coverage)


def test_price_distance_preserves_negative_direction(operation, history, source, coverage):
    operation.update(unit_price=10, line_total=420)
    result = run(operation, history, source, coverage)
    assert result["features"][NAMES[1]] == pytest.approx(-1 / 19)


def test_identity_comparison_precedes_float_conversion(operation, history, source, coverage):
    first = {**history[0], "unit_price": Decimal("1.0"), "quantity": 1,
             "line_total": Decimal("1.0")}
    second = {**first, "unit_price": Decimal("1.0000000000000001"),
              "line_total": Decimal("1.0000000000000001")}
    with pytest.raises(FeatureValidationError, match="conflicting_identity"):
        run(operation, [first, second], source, coverage)


@pytest.mark.parametrize("bad_history", [False, {}, "history", 123, [None], [1]])
def test_invalid_history_container_is_not_empty_history(operation, source, coverage, bad_history):
    with pytest.raises(FeatureValidationError):
        run(operation, bad_history, source, coverage)


@pytest.mark.parametrize(("field", "bad"), [
    ("source_id", "invoice"), ("source_version", ""), ("origin", "real"),
    ("entity_namespace", ""), ("monetary_unit", "USD"), ("temporal_assumption", None),
])
def test_unidentified_source_or_temporal_assumption_is_rejected(
    operation, history, source, coverage, field, bad,
):
    source[field] = bad
    with pytest.raises(FeatureValidationError):
        run(operation, history, source, coverage)


@pytest.mark.parametrize(("field", "bad"), [
    ("source_id", "other"), ("source_version", "other"), ("entity_namespace", "other"),
    ("complete", None), ("complete", 1), ("start_date", None),
    ("start_date", "2024-05-01"), ("end_date", "2022-01-01"),
])
def test_invalid_or_contradictory_coverage_is_rejected(
    operation, history, source, coverage, field, bad,
):
    coverage[field] = bad
    with pytest.raises(FeatureValidationError):
        run(operation, history, source, coverage)


def test_coverage_is_required_not_inferred_from_rows(operation, history, source, coverage):
    for value in (None, {}, {k: v for k, v in coverage.items() if k != "start_date"}):
        with pytest.raises(FeatureValidationError):
            run(operation, history, source, value)


@pytest.mark.parametrize("total", [Decimal("0.31"), 0.30000000000000004])
def test_total_is_not_rounded_to_conceal_discrepancies(operation, source, coverage, total):
    operation.update(unit_price=0.1, quantity=3, line_total=total)
    with pytest.raises(FeatureValidationError):
        run(operation, [], source, coverage)


def test_decimal_price_multiplication_and_leap_day_are_valid(operation, source, coverage):
    operation.update(order_date="2024-02-29", unit_price=Decimal("0.1"), quantity=3, line_total=0.3)
    result = run(operation, (), source, coverage)
    assert result["cutoff_date"] == "2024-02-29"
    assert result["features"][NAMES[6]] == 0


def test_nonfinite_derived_feature_fails_explicitly(operation, history, source, coverage):
    operation.update(unit_price=1e300, quantity=1, line_total=1e300)
    tiny = [{**r, "unit_price": 1e-100, "quantity": 1, "line_total": 1e-100} for r in history]
    with pytest.raises(FeatureValidationError):
        run(operation, tiny, source, coverage)


def test_exception_does_not_include_sensitive_input(operation, history, source, coverage):
    operation["supplier_id"] = " secret-supplier "
    with pytest.raises(FeatureValidationError) as caught:
        run(operation, history, source, coverage)
    assert isinstance(caught.value.code, str)
    assert "secret-supplier" not in str(caught.value)


@pytest.mark.parametrize("container", ["operation", "source", "coverage"])
def test_unknown_keys_fail_closed(operation, history, source, coverage, container):
    {"operation": operation, "source": source, "coverage": coverage}[container]["currency"] = "BRL"
    with pytest.raises(FeatureValidationError):
        run(operation, history, source, coverage)
