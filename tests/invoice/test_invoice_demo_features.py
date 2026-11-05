"""Hand-derived synthetic aggregates; no datasets, estimator or legacy imports."""

import copy
import io
import math
import socket
from unittest.mock import patch

import pytest

from ml.scripts.invoice_demo_contract import FEATURE_NAMES, validate_request
from ml.scripts.invoice_demo_features import prepare_features


@pytest.fixture
def invoice():
    return {
        "contract": "invoice-demo-invoice/1.0", "origin": "synthetic",
        "entity_namespace": "demo-construction", "currency": "ZAR",
        "invoice_amount": 50, "supplier_id": "demo-supplier-a",
        "department_id": "demo-department-x", "supplier_country": "ZA",
        "supplier_age_days": 365, "invoice_type": "GOODS",
        "payment_terms_days": 30, "invoice_date": "2026-04-12",
        "submission_hour": 6,
    }


@pytest.fixture
def history():
    # Four synthetic invoices: (supplier, department, country, amount).
    # a,x,ZA,10; a,y,ZA,30; b,x,GB,20; b,y,GB,40.
    # Mean=25; sum of squared deviations=500; sample std=sqrt(500/3).
    # Supplier a: mean=20, squared deviations=200, sample std=sqrt(200).
    # Literal expected stats deliberately do not use the implementation.
    return {
        "contract": "invoice-demo-history/1.0", "origin": "synthetic",
        "entity_namespace": "demo-construction", "currency": "ZAR",
        "coverage": "complete", "aggregation": "full_reference_population",
        "std_ddof": 1, "n": 4,
        "global_amount_mean": 25, "global_amount_std": 12.909944487358056,
        "suppliers": {
            "demo-supplier-a": {"count": 2, "amount_mean": 20,
                                "amount_std": 14.142135623730951, "country": "ZA"},
            "demo-supplier-b": {"count": 2, "amount_mean": 30,
                                "amount_std": 14.142135623730951, "country": "GB"},
        },
        "departments": {
            "demo-department-x": {"count": 2, "amount_mean": 15},
            "demo-department-y": {"count": 2, "amount_mean": 35},
        },
        "countries": {"ZA": 2, "GB": 2},
        "supplier_departments": [
            {"supplier_id": "demo-supplier-a", "department_id": "demo-department-x", "count": 1},
            {"supplier_id": "demo-supplier-a", "department_id": "demo-department-y", "count": 1},
            {"supplier_id": "demo-supplier-b", "department_id": "demo-department-x", "count": 1},
            {"supplier_id": "demo-supplier-b", "department_id": "demo-department-y", "count": 1},
        ],
    }


def test_all_19_features_in_transport_order_with_independent_oracle(invoice, history):
    result = prepare_features(invoice, history)
    expected = [
        50, 3.9318256327243257, 365, 0.5, 0.5, 2.5, 2.1213203435596424,
        0.5, 3.3333333333333335, 0.25, 30, 0, 1, 0,
        -0.7818314824680298, 0.6234898018587336, 1, 0, 1,
    ]
    assert list(result) == list(FEATURE_NAMES)
    assert list(result.values()) == pytest.approx(expected, abs=1e-12)
    validate_request({
        "contract": "invoice-demo/1.0", "origin": "synthetic",
        "feature_names": list(result), "rows": [{"id": "demo-001", "values": list(result.values())}],
    })


@pytest.mark.parametrize(("day", "hour", "expected"), [
    ("2024-01-01", 0, [0, 1, 0, 1, 0, 1, 0]),
    ("2024-02-29", 18, [-1, 0, 0.4338837391175582, -0.9009688679024191,
                        0.5, 0.8660254037844386, 0]),
    ("2026-10-03", 12, [0, -1, -0.9749279121818236, -0.2225209339563146, -1, 0, 1]),
])
def test_cyclic_boundaries_leap_day_and_weekend(invoice, history, day, hour, expected):
    invoice.update(invoice_date=day, submission_hour=hour, invoice_type="SERVICES", payment_terms_days=0)
    result = prepare_features(invoice, history)
    assert list(result.values())[12:] == pytest.approx(expected, abs=1e-12)
    assert result["invoice_type_encoded"] == 1
    assert result["payment_terms_days"] == 0


def test_explicit_new_entities_use_original_global_fallbacks(invoice, history):
    invoice.update(supplier_id="demo-new-supplier", department_id="demo-new-department",
                   supplier_country="AU")
    result = prepare_features(invoice, history)
    for name in ("supplier_frequency", "department_frequency", "country_frequency",
                 "supplier_department_frequency"):
        assert result[name] == 0
    assert result["amount_vs_supplier_mean"] == 2
    assert result["amount_vs_department_mean"] == 2
    assert result["supplier_amount_zscore"] == pytest.approx(1.9364916731037085)


def test_unknown_supplier_can_have_known_country_and_department(invoice, history):
    invoice["supplier_id"] = "demo-new-supplier"
    result = prepare_features(invoice, history)
    assert result["supplier_frequency"] == result["supplier_department_frequency"] == 0
    assert result["country_frequency"] == result["department_frequency"] == 0.5


def test_unseen_pair_is_not_a_missing_entity_or_product_of_frequencies(invoice, history):
    # Same amounts, but a only used x and b only used y.
    history["supplier_departments"] = [
        {"supplier_id": "demo-supplier-a", "department_id": "demo-department-x", "count": 2},
        {"supplier_id": "demo-supplier-b", "department_id": "demo-department-y", "count": 2},
    ]
    history["departments"]["demo-department-x"]["amount_mean"] = 20
    history["departments"]["demo-department-y"]["amount_mean"] = 30
    invoice["department_id"] = "demo-department-y"
    result = prepare_features(invoice, history)
    assert result["supplier_department_frequency"] == 0
    assert result["supplier_frequency"] == result["department_frequency"] == 0.5
    assert result["amount_vs_department_mean"] == pytest.approx(5 / 3)


@pytest.mark.parametrize("singleton", [False, True])
def test_zero_or_singleton_supplier_std_uses_global_std(invoice, history, singleton):
    # a=[20,20], b=[20,40] (or a=[20], b=[20,40] for singleton).
    a_count = 1 if singleton else 2
    history.update(n=a_count + 2, global_amount_mean=80 / 3 if singleton else 25,
                   global_amount_std=11.547005383792516 if singleton else 10)
    history["suppliers"]["demo-supplier-a"].update(count=a_count, amount_std=None if singleton else 0)
    history["countries"]["ZA"] = a_count
    history["departments"] = {"demo-department-x": {"count": a_count + 2,
                                                   "amount_mean": history["global_amount_mean"]}}
    history["supplier_departments"] = [
        {"supplier_id": "demo-supplier-a", "department_id": "demo-department-x", "count": a_count},
        {"supplier_id": "demo-supplier-b", "department_id": "demo-department-x", "count": 2},
    ]
    result = prepare_features(invoice, history)
    assert result["supplier_amount_zscore"] == pytest.approx(2.598076211353316 if singleton else 3)
    assert result["amount_vs_supplier_mean"] == 2.5


@pytest.mark.parametrize(("key", "value"), [
    ("contract", "invoice-demo-invoice/2.0"), ("origin", "real"),
    ("entity_namespace", "demo-other"), ("supplier_id", ""), ("department_id", None),
    ("supplier_country", "za"), ("supplier_country", "GB"), ("currency", "BRL"),
    ("invoice_amount", 0), ("invoice_amount", -1), ("invoice_amount", True),
    ("invoice_amount", "50"), ("invoice_amount", None), ("invoice_amount", math.inf),
    ("invoice_amount", math.nan), ("invoice_amount", 10**400),
    ("supplier_age_days", -1), ("supplier_age_days", None), ("supplier_age_days", 1.5),
    ("payment_terms_days", -1), ("payment_terms_days", "NET30"), ("payment_terms_days", True),
    ("invoice_type", "goods"), ("invoice_type", "PRODUCT"), ("invoice_type", []),
    ("submission_hour", -1), ("submission_hour", 24), ("submission_hour", 6.5),
    ("invoice_date", "2026-02-29"), ("invoice_date", "2026-04-31"),
    ("invoice_date", "2026-4-12"), ("invoice_date", "20260412"),
    ("invoice_date", "2026-04-12T06:00:00"), ("invoice_date", None),
])
def test_invalid_invoice_is_rejected(invoice, history, key, value):
    invoice[key] = value
    with pytest.raises(ValueError, match="FEATURE_"):
        prepare_features(invoice, history)


def test_each_invoice_and_context_field_is_required(invoice, history):
    for original in (invoice, history):
        for key in original:
            missing = copy.deepcopy(original)
            del missing[key]
            with pytest.raises(ValueError, match="FEATURE_SCHEMA"):
                prepare_features(missing, history) if original is invoice else prepare_features(invoice, missing)


@pytest.mark.parametrize("extra", ["is_fraud", "model_path", "product", "totalCents"])
def test_undeclared_fields_are_not_silently_used_or_ignored(invoice, history, extra):
    invoice[extra] = "unexpected"
    with pytest.raises(ValueError, match="FEATURE_SCHEMA"):
        prepare_features(invoice, history)


@pytest.mark.parametrize(("key", "value"), [
    ("contract", "invoice-demo-history/2.0"), ("origin", "train"),
    ("coverage", "partial"), ("aggregation", "rolling"),
    ("std_ddof", 0), ("std_ddof", True), ("std_ddof", 1.0),
    ("n", 0), ("n", 1), ("n", 4.0), ("n", True), ("n", 5),
    ("global_amount_mean", 0), ("global_amount_mean", -1), ("global_amount_mean", 26),
    ("global_amount_std", 0), ("global_amount_std", None),
    ("global_amount_std", math.nan), ("global_amount_std", math.inf),
    ("global_amount_std", 11.180339887498949),  # population std (ddof=0)
    ("global_amount_std", 166.66666666666666),  # variance, not std
    ("suppliers", {}), ("suppliers", []), ("departments", {}),
    ("countries", {}), ("supplier_departments", []),
])
def test_invalid_history_is_rejected_without_repair(invoice, history, key, value):
    history[key] = value
    before = copy.deepcopy(history)
    with pytest.raises(ValueError, match="FEATURE_"):
        prepare_features(invoice, history)
    assert repr(history) == repr(before)


@pytest.mark.parametrize(("group", "key", "field", "value"), [
    ("suppliers", "demo-supplier-a", "count", 0),
    ("suppliers", "demo-supplier-a", "count", 1.5),
    ("suppliers", "demo-supplier-a", "amount_mean", 0),
    ("suppliers", "demo-supplier-a", "amount_mean", 21),
    ("suppliers", "demo-supplier-a", "amount_std", None),
    ("suppliers", "demo-supplier-a", "amount_std", -1),
    ("suppliers", "demo-supplier-a", "amount_std", math.nan),
    ("suppliers", "demo-supplier-a", "amount_std", 200),
    ("suppliers", "demo-supplier-a", "amount_std", 10),  # population instead of sample
    ("suppliers", "demo-supplier-a", "country", "AU"),
    ("departments", "demo-department-x", "count", 5),
    ("departments", "demo-department-x", "amount_mean", math.inf),
])
def test_invalid_or_inconsistent_group_statistics(invoice, history, group, key, field, value):
    history[group][key][field] = value
    with pytest.raises(ValueError, match="FEATURE_"):
        prepare_features(invoice, history)


def test_missing_group_field_is_not_an_unseen_entity(invoice, history):
    for key in history["suppliers"]["demo-supplier-a"]:
        context = copy.deepcopy(history)
        del context["suppliers"]["demo-supplier-a"][key]
        with pytest.raises(ValueError, match="FEATURE_SCHEMA"):
            prepare_features(invoice, context)
    del history["suppliers"]["demo-supplier-a"]
    with pytest.raises(ValueError, match="FEATURE_"):
        prepare_features(invoice, history)


@pytest.mark.parametrize("case", ["duplicate", "unknown_supplier", "unknown_department", "marginal", "country"])
def test_pair_and_country_maps_must_match_population(invoice, history, case):
    pairs = history["supplier_departments"]
    if case == "duplicate":
        pairs.append(copy.deepcopy(pairs[0]))
    elif case == "unknown_supplier":
        pairs[0]["supplier_id"] = "demo-missing"
    elif case == "unknown_department":
        pairs[0]["department_id"] = "demo-missing"
    elif case == "marginal":
        pairs[0]["count"] = 2
        pairs.pop(1)  # still sums to N but department marginals disagree
    else:
        history["countries"] = {"ZA": 1, "GB": 3}
    with pytest.raises(ValueError, match="FEATURE_"):
        prepare_features(invoice, history)


def test_matching_but_incompatible_currency_is_not_accepted(invoice, history):
    invoice["currency"] = history["currency"] = "BRL"
    with pytest.raises(ValueError, match="FEATURE_CURRENCY"):
        prepare_features(invoice, history)


@pytest.mark.parametrize("bad", [None, [], "invoice", 1, True])
def test_non_objects_are_rejected(invoice, history, bad):
    with pytest.raises(ValueError, match="FEATURE_SCHEMA"):
        prepare_features(bad, history)
    with pytest.raises(ValueError, match="FEATURE_SCHEMA"):
        prepare_features(invoice, bad)


def test_nonfinite_derived_values_are_rejected(invoice, history):
    # Coherent tiny positive history; a finite invoice still overflows its ratios.
    for key in ("global_amount_mean", "global_amount_std"):
        history[key] *= 1e-200
    for group in ("suppliers", "departments"):
        for row in history[group].values():
            row["amount_mean"] *= 1e-200
            if "amount_std" in row:
                row["amount_std"] *= 1e-200
    invoice["invoice_amount"] = 1e308
    with pytest.raises(ValueError, match="FEATURE_OUTPUT"):
        prepare_features(invoice, history)


def test_preparation_is_pure_and_does_not_change_context_or_use_io(invoice, history):
    before = copy.deepcopy((invoice, history))
    with patch("builtins.open", side_effect=AssertionError("file IO forbidden")), \
            patch.object(io, "open", side_effect=AssertionError("file IO forbidden")), \
            patch.object(socket.socket, "connect", side_effect=AssertionError("network forbidden")):
        first = prepare_features(invoice, history)
        second = prepare_features(invoice, history)
    assert first == second
    assert (invoice, history) == before
    assert history["n"] == 4  # new invoice was never inserted into reference history


def test_singletons_still_produce_negative_zscore_without_clipping(invoice, history):
    # Reference: a=10 and b=30. Both supplier sample stds are undefined.
    history.update(n=2, global_amount_mean=20, global_amount_std=14.142135623730951)
    for identifier, mean in (("demo-supplier-a", 10), ("demo-supplier-b", 30)):
        history["suppliers"][identifier].update(count=1, amount_mean=mean, amount_std=None)
    history["countries"] = {"ZA": 1, "GB": 1}
    history["departments"] = {"demo-department-x": {"count": 2, "amount_mean": 20}}
    history["supplier_departments"] = [
        {"supplier_id": identifier, "department_id": "demo-department-x", "count": 1}
        for identifier in history["suppliers"]
    ]
    invoice.update(invoice_amount=5.25, supplier_age_days=0)
    result = prepare_features(invoice, history)
    assert result["supplier_amount_zscore"] == pytest.approx(-0.3358757210636101)
    assert result["amount_vs_supplier_mean"] == 0.525
    assert result["log_invoice_amount"] == pytest.approx(1.8325814637483102)
    assert result["supplier_age_days"] == 0
    assert result["department_frequency"] == 1
    # A missing sample std may not be silently filled with a numeric value.
    history["suppliers"]["demo-supplier-a"]["amount_std"] = 0
    with pytest.raises(ValueError, match="FEATURE_SINGLETON_STD"):
        prepare_features(invoice, history)


def test_context_order_does_not_change_features(invoice, history):
    expected = prepare_features(invoice, history)
    for group in ("suppliers", "departments", "countries"):
        history[group] = dict(reversed(list(history[group].items())))
    history["supplier_departments"].reverse()
    assert prepare_features(invoice, history) == expected


def test_impossible_huge_group_count_is_validation_error(invoice, history):
    history["suppliers"]["demo-supplier-a"]["count"] = 10**308
    with pytest.raises(ValueError, match="FEATURE_COUNTS"):
        prepare_features(invoice, history)


def test_inconsistent_history_means_do_not_raise_numeric_overflow(invoice, history):
    history["suppliers"]["demo-supplier-a"].update(count=10**308, amount_mean=1e308)
    with pytest.raises(ValueError, match="FEATURE_COUNTS"):
        prepare_features(invoice, history)


def test_department_spread_cannot_exceed_global_sample_deviation(invoice, history):
    # Counts and weighted mean still agree, but the between-group spread alone
    # exceeds the entire population's supplied sample deviation.
    history["departments"]["demo-department-x"]["amount_mean"] = 1
    history["departments"]["demo-department-y"]["amount_mean"] = 49
    with pytest.raises(ValueError, match="FEATURE_AGGREGATES"):
        prepare_features(invoice, history)


def test_consistent_pooled_std_cannot_imply_negative_historical_amounts(invoice, history):
    # For two strictly positive amounts with mean 20, std 100 is impossible.
    # The global deviation here deliberately passes the pooled-variance check.
    for row in history["suppliers"].values():
        row["amount_std"] = 100
    history["global_amount_std"] = 81.8535277187245  # sqrt(6700), ddof=1
    with pytest.raises(ValueError, match="FEATURE_AGGREGATES"):
        prepare_features(invoice, history)
