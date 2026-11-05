"""Pure feature preparation for explicitly synthetic invoices and reference maps.

This is not the historical TRAIN transformer. Inputs are already decoded dicts;
there is no file access, model loading, scoring, currency conversion or imputation.
The synthetic declaration and complete maps establish a local contract, not proof
of provenance or point-in-time availability. No input is appended to the history.
"""

import math
import re
from datetime import date

from ml.scripts.invoice_demo_contract import FEATURE_NAMES

INVOICE_VERSION = "invoice-demo-invoice/1.0"
HISTORY_VERSION = "invoice-demo-history/1.0"


def _keys(value, required):
    if type(value) is not dict or set(value) != set(required):
        raise ValueError("FEATURE_SCHEMA")


def _number(value, *, positive=False):
    try:
        valid = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid or (value <= 0 if positive else value < 0):
        raise ValueError("FEATURE_NUMBER")
    return value


def _integer(value, minimum=0):
    _number(value)
    if type(value) is not int or value < minimum:
        raise ValueError("FEATURE_INTEGER")
    return value


def _identifier(value):
    if type(value) is not str or re.fullmatch(r"demo-[a-z0-9][a-z0-9-]{0,63}", value) is None:
        raise ValueError("FEATURE_IDENTITY")


def _country(value):
    if type(value) is not str or re.fullmatch(r"[A-Z]{2}", value) is None:
        raise ValueError("FEATURE_COUNTRY")


def _mapping(value):
    if type(value) is not dict or not value:
        raise ValueError("FEATURE_MAP")


def _consistent(actual, expected):
    # Floating round-off only; no rounding/repair of the caller's statistics.
    if not math.isfinite(actual) or not math.isclose(actual, expected, rel_tol=1e-9, abs_tol=0):
        raise ValueError("FEATURE_AGGREGATES")


def _at_most(actual, limit):
    if not math.isfinite(actual) or (
        actual > limit and not math.isclose(actual, limit, rel_tol=1e-9, abs_tol=0)
    ):
        raise ValueError("FEATURE_AGGREGATES")


def _validate_invoice(invoice):
    _keys(invoice, (
        "contract", "origin", "entity_namespace", "currency", "invoice_amount",
        "supplier_id", "department_id", "supplier_country", "supplier_age_days",
        "invoice_type", "payment_terms_days", "invoice_date", "submission_hour",
    ))
    if invoice["contract"] != INVOICE_VERSION or invoice["origin"] != "synthetic":
        raise ValueError("FEATURE_SCOPE")
    for key in ("entity_namespace", "supplier_id", "department_id"):
        _identifier(invoice[key])
    _country(invoice["supplier_country"])
    _number(invoice["invoice_amount"], positive=True)
    _integer(invoice["supplier_age_days"])
    _integer(invoice["payment_terms_days"])
    _integer(invoice["submission_hour"])
    if invoice["submission_hour"] > 23:
        raise ValueError("FEATURE_HOUR")
    if invoice["invoice_type"] not in ("GOODS", "SERVICES"):
        raise ValueError("FEATURE_INVOICE_TYPE")
    value = invoice["invoice_date"]
    if type(value) is not str or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
        raise ValueError("FEATURE_DATE")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError("FEATURE_DATE") from None


def _validate_history(history, invoice):
    _keys(history, (
        "contract", "origin", "entity_namespace", "currency", "coverage", "aggregation",
        "std_ddof", "n", "global_amount_mean", "global_amount_std", "suppliers",
        "departments", "countries", "supplier_departments",
    ))
    if (history["contract"] != HISTORY_VERSION or history["origin"] != "synthetic"
            or history["coverage"] != "complete"
            or history["aggregation"] != "full_reference_population"):
        raise ValueError("FEATURE_HISTORY_SCOPE")
    _identifier(history["entity_namespace"])
    if history["entity_namespace"] != invoice["entity_namespace"]:
        raise ValueError("FEATURE_IDENTITY")
    # Original Invoice amounts are in ZAR major units. Matching BRL is not
    # compatible; this preparer neither converts currency nor accepts cents.
    if history["currency"] != "ZAR" or invoice["currency"] != "ZAR":
        raise ValueError("FEATURE_CURRENCY")
    if type(history["std_ddof"]) is not int or history["std_ddof"] != 1:
        raise ValueError("FEATURE_STD_DDOF")
    n = _integer(history["n"], 2)
    mean = _number(history["global_amount_mean"], positive=True)
    std = _number(history["global_amount_std"], positive=True)
    suppliers, departments, countries = (history[key] for key in ("suppliers", "departments", "countries"))
    for mapping in (suppliers, departments, countries):
        _mapping(mapping)

    country_counts = {}
    std_components = []
    for identifier, row in suppliers.items():
        _identifier(identifier)
        _keys(row, ("count", "amount_mean", "amount_std", "country"))
        count = _integer(row["count"], 1)
        if count > n:
            raise ValueError("FEATURE_COUNTS")
        group_mean = _number(row["amount_mean"], positive=True)
        _country(row["country"])
        country_counts[row["country"]] = country_counts.get(row["country"], 0) + count
        # In a complete population without missing amounts, ddof=1 is undefined
        # only for a singleton. None explicitly represents that case; omitted
        # fields, NaN and missing deviations for larger groups are errors.
        if count == 1:
            if row["amount_std"] is not None:
                raise ValueError("FEATURE_SINGLETON_STD")
        else:
            group_std = _number(row["amount_std"])
            # Nonnegative amounts imply sample std <= mean * sqrt(count).
            _at_most(group_std / math.sqrt(count), group_mean)
            std_components.append(math.sqrt((count - 1) / (n - 1)) * group_std)
        std_components.append(math.sqrt(count / (n - 1)) * (group_mean - mean))

    for identifier, row in departments.items():
        _identifier(identifier)
        _keys(row, ("count", "amount_mean"))
        _integer(row["count"], 1)
        _number(row["amount_mean"], positive=True)

    for mapping in (suppliers, departments):
        if sum(row["count"] for row in mapping.values()) != n:
            raise ValueError("FEATURE_COUNTS")
        _consistent(math.fsum(row["count"] / n * row["amount_mean"] for row in mapping.values()), mean)
    # Validate the supplied global sample std via the pooled-variance identity.
    # Never replace it, infer ddof, or silently recompute supplied feature maps.
    _consistent(math.hypot(*std_components), std)
    # Without department stds, their between-group spread is still a lower
    # bound on the global sample std. Contradictory means must not be accepted.
    _at_most(math.hypot(*(
        math.sqrt(row["count"] / (n - 1)) * (row["amount_mean"] - mean)
        for row in departments.values()
    )), std)

    for country, count in countries.items():
        _country(country)
        _integer(count, 1)
    if countries != country_counts:
        raise ValueError("FEATURE_COUNTRY_COUNTS")

    pairs = history["supplier_departments"]
    if type(pairs) is not list or not pairs:
        raise ValueError("FEATURE_PAIRS")
    pair_counts = {}
    supplier_counts = dict.fromkeys(suppliers, 0)
    department_counts = dict.fromkeys(departments, 0)
    for row in pairs:
        _keys(row, ("supplier_id", "department_id", "count"))
        supplier, department = row["supplier_id"], row["department_id"]
        _identifier(supplier)
        _identifier(department)
        count = _integer(row["count"], 1)
        key = supplier, department
        if supplier not in suppliers or department not in departments or key in pair_counts:
            raise ValueError("FEATURE_PAIRS")
        pair_counts[key] = count
        supplier_counts[supplier] += count
        department_counts[department] += count
    if (supplier_counts != {key: row["count"] for key, row in suppliers.items()}
            or department_counts != {key: row["count"] for key, row in departments.items()}):
        raise ValueError("FEATURE_PAIR_COUNTS")

    known_supplier = suppliers.get(invoice["supplier_id"])
    if known_supplier is not None and known_supplier["country"] != invoice["supplier_country"]:
        raise ValueError("FEATURE_SUPPLIER_COUNTRY")
    return pair_counts


def prepare_features(invoice, history):
    """Return an ordered dict containing exactly invoice-demo/1.0's 19 features.

    invoice (invoice-demo-invoice/1.0): origin='synthetic', a demo-* namespace
    and supplier/department IDs, ZAR invoice_amount in major units (not P4's
    totalCents), supplier_country (uppercase two-letter code), nonnegative
    integer supplier_age_days and payment_terms_days, GOODS/SERVICES,
    invoice_date YYYY-MM-DD, and submission_hour 0..23 in the source clock.
    Age is the supplied cadastral attribute, not recomputed from invoice_date.

    history (invoice-demo-history/1.0): same origin/namespace/currency,
    coverage='complete', aggregation='full_reference_population', std_ddof=1,
    n>=2, positive global_amount_mean/global_amount_std, suppliers mapping
    {id: {count, amount_mean, amount_std, country}}, departments mapping
    {id: {count, amount_mean}}, countries mapping {code: count}, and unique
    supplier_departments [{supplier_id, department_id, count}]. Amounts in the
    reference population must be positive and complete. A singleton's sample
    std must explicitly be None; otherwise supply the finite sample std.

    Complete means every observed group is present and counts reconcile to n.
    Only an absent key in these validated complete maps means 'unseen'. A new
    supplier/department uses the original global fallback; unseen frequencies
    are zero. Singleton/zero supplier std uses the supplied global sample std.
    This does not certify historical provenance or eligibility for real scoring.
    Raises ValueError with a FEATURE_* code; never repairs or mutates inputs.
    """
    invoice_day = _validate_invoice(invoice)
    pairs = _validate_history(history, invoice)
    supplier_id, department_id = invoice["supplier_id"], invoice["department_id"]
    supplier = history["suppliers"].get(supplier_id)
    department = history["departments"].get(department_id)
    supplier_mean = supplier["amount_mean"] if supplier is not None else history["global_amount_mean"]
    supplier_std = supplier["amount_std"] if supplier is not None else None
    if supplier_std is None or supplier_std == 0:
        supplier_std = history["global_amount_std"]
    department_mean = department["amount_mean"] if department is not None else history["global_amount_mean"]
    amount, n = invoice["invoice_amount"], history["n"]
    hour_angle = 2 * math.pi * invoice["submission_hour"] / 24
    week_angle = 2 * math.pi * invoice_day.weekday() / 7
    month_angle = 2 * math.pi * (invoice_day.month - 1) / 12
    values = [
        amount, math.log1p(amount), invoice["supplier_age_days"],
        (supplier["count"] if supplier is not None else 0) / n,
        history["countries"].get(invoice["supplier_country"], 0) / n,
        amount / supplier_mean, (amount - supplier_mean) / supplier_std,
        (department["count"] if department is not None else 0) / n,
        amount / department_mean, pairs.get((supplier_id, department_id), 0) / n,
        invoice["payment_terms_days"], 0 if invoice["invoice_type"] == "GOODS" else 1,
        math.sin(hour_angle), math.cos(hour_angle), math.sin(week_angle), math.cos(week_angle),
        math.sin(month_angle), math.cos(month_angle), int(invoice_day.weekday() >= 5),
    ]
    if not all(math.isfinite(value) for value in values):
        raise ValueError("FEATURE_OUTPUT")
    return dict(zip(FEATURE_NAMES, values, strict=True))
