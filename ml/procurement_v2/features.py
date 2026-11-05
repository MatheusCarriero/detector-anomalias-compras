"""Procurement V2: pure, synthetic, daily as-of feature preparation.

This module neither reads the source CSV nor imports any V1 pipeline/model.
An operation is a purchase *line*, not an inferred purchase-order header.
Availability at order time is an explicit simulation assumption, not evidence
of pre-approval availability in a real system. No output is a risk score.
"""

import math
import re
from datetime import date, timedelta
from decimal import Decimal, localcontext

import numpy as np

CONTRACT_VERSION = "procurement-temporal-features/1.0"
WINDOW_DAYS = 90
MIN_HISTORY = 20
FEATURE_NAMES = (
    "price_to_item_median_90d",
    "price_iqr_distance_90d",
    "item_price_relative_iqr_90d",
    "quantity_to_item_median_90d",
    "total_to_item_median_90d",
    "price_to_supplier_item_median_90d",
    "supplier_lines_90d",
    "supplier_item_lines_90d",
    "business_unit_lines_90d",
)
_IDENTITY_KEYS = ("source_id", "source_version", "entity_namespace")
_SOURCE_KEYS = (*_IDENTITY_KEYS, "origin", "monetary_unit", "temporal_assumption")
_COVERAGE_KEYS = (*_IDENTITY_KEYS, "start_date", "end_date", "complete")
_ROW_KEYS = (
    *_IDENTITY_KEYS, "po_id", "order_date", "supplier_id", "item",
    "business_unit", "unit_price", "quantity", "line_total",
)
_CONTEXT_ONLY_KEYS = (
    "promised_delivery_date", "actual_delivery_date", "supplier_name",
    "supplier_country", "category", "payment_terms", "on_contract", "quality_rejected",
)
_METRICS = ("unit_price", "quantity", "line_total")


class FeatureValidationError(ValueError):
    """Invalid contract input or unrepresentable result; never includes row values."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _keys(value, required, optional=()):
    if type(value) is not dict or not set(required) <= value.keys():
        raise FeatureValidationError("invalid_structure")
    if value.keys() - set(required) - set(optional):
        raise FeatureValidationError("unknown_fields")


def _identifier(value):
    if (type(value) is not str or not value or value.strip() != value
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise FeatureValidationError("invalid_identity")


def _day(value):
    if type(value) is not str or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
        raise FeatureValidationError("invalid_date")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise FeatureValidationError("invalid_date") from None


def _positive_number(value):
    if type(value) not in (int, float, Decimal):
        raise FeatureValidationError("invalid_number")
    try:
        number = float(value)
    except (OverflowError, ValueError):
        raise FeatureValidationError("invalid_number") from None
    if not math.isfinite(number) or number <= 0:
        raise FeatureValidationError("invalid_number")
    return Decimal(str(value))


def _identity(value, source):
    for key in _IDENTITY_KEYS:
        _identifier(value[key])
        if value[key] != source[key]:
            raise FeatureValidationError("incompatible_identity")


def _metadata(source, coverage):
    _keys(source, _SOURCE_KEYS)
    for key in _SOURCE_KEYS:
        _identifier(source[key])
    if (source["source_id"] != "procurement-spend"
            or source["origin"] != "synthetic"
            or source["monetary_unit"] != "unspecified_source_unit"
            or source["temporal_assumption"] != "available_at_order_no_revisions"):
        raise FeatureValidationError("incompatible_source")
    _keys(coverage, _COVERAGE_KEYS)
    _identity(coverage, source)
    start, end = _day(coverage["start_date"]), _day(coverage["end_date"])
    if start > end or type(coverage["complete"]) is not bool:
        raise FeatureValidationError("invalid_coverage")
    return start, end


def _row(value, source):
    _keys(value, _ROW_KEYS, _CONTEXT_ONLY_KEYS)
    _identity(value, source)
    for key in ("po_id", "supplier_id", "item", "business_unit"):
        _identifier(value[key])
    row_day = _day(value["order_date"])
    if type(value["quantity"]) is not int or value["quantity"] <= 0:
        raise FeatureValidationError("invalid_quantity")
    _positive_number(value["quantity"])
    price = _positive_number(value["unit_price"])
    total = _positive_number(value["line_total"])
    # Exact decimal equality for the supplied values, not binary multiplication
    # or rounding to cents. Never accept a discrepancy by repairing a total.
    with localcontext() as context:
        context.prec = max(28, len(price.as_tuple().digits) + len(str(value["quantity"])))
        if price * value["quantity"] != total:
            raise FeatureValidationError("inconsistent_total")
    # An isolated projection: optional cadastral/processing/outcome fields have
    # no role in features or in validation of the pre-order numeric inputs.
    return {
        "po_id": value["po_id"], "order_date": row_day,
        "supplier_id": value["supplier_id"], "item": value["item"],
        "business_unit": value["business_unit"],
        "unit_price": price, "quantity": value["quantity"],
        "line_total": total,
    }


def _select_history(history, source, operation, start, cutoff, coverage_start, coverage_end):
    if type(history) not in (list, tuple):
        raise FeatureValidationError("invalid_history")
    selected = []
    identities = {}
    for value in history:
        if type(value) is not dict or "order_date" not in value:
            raise FeatureValidationError("invalid_history")
        row_day = _day(value["order_date"])
        # Inspect only the date before selection. Future/out-of-window fields
        # cannot affect references, entity maps or numeric validation.
        if not start <= row_day < cutoff:
            continue
        row = _row(value, source)
        if not coverage_start <= row_day <= coverage_end:
            raise FeatureValidationError("inconsistent_coverage")
        if row["po_id"] == operation["po_id"]:
            raise FeatureValidationError("current_operation_in_history")
        previous = identities.get(row["po_id"])
        if previous is not None and previous != row:
            raise FeatureValidationError("conflicting_identity")
        identities[row["po_id"]] = row
        # Retain repeated observations as supplied. No deduplication, weighting,
        # outlier removal, hidden fallback or reconstructed order headers.
        selected.append(row)
    return selected


def _statistics(rows, metric):
    if len(rows) < MIN_HISTORY:
        return None
    values = np.array([row[metric] for row in rows], dtype=float)
    try:
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            q1, median, q3 = np.quantile(values, [.25, .5, .75], method="linear")
            mad = np.quantile(np.abs(values - median), .5, method="linear")
            stats = dict(zip(("q1", "median", "q3", "iqr", "mad"),
                             (q1, median, q3, q3 - q1, mad), strict=True))
    except (FloatingPointError, OverflowError):
        raise FeatureValidationError("numeric_range") from None
    if any(not math.isfinite(value) or value < 0 for value in stats.values()):
        raise FeatureValidationError("numeric_range")
    return {key: float(value) for key, value in stats.items()}


def _divide(numerator, denominator, zero_reason="zero_denominator"):
    if denominator == 0:
        return None, zero_reason
    result = float(numerator) / denominator
    if not math.isfinite(result) or (result == 0 and numerator != 0):
        raise FeatureValidationError("numeric_range")
    return result, None


def _initialize_result(current, source, coverage, coverage_start, coverage_end):
    """Common result skeleton for single-line and daily batch preparation."""
    cutoff = current["order_date"]
    try:
        start = cutoff - timedelta(days=WINDOW_DAYS)
        previous_day = cutoff - timedelta(days=1)
    except OverflowError:
        raise FeatureValidationError("invalid_date") from None
    complete = coverage["complete"] and coverage_start <= start and coverage_end >= previous_day
    return {
        "operation_id": current["po_id"],
        "contract": CONTRACT_VERSION,
        "source": dict(source),
        "feature_names": list(FEATURE_NAMES),
        "features": dict.fromkeys(FEATURE_NAMES),
        "cutoff_date": cutoff.isoformat(),
        "window": {"start": start.isoformat(), "end": cutoff.isoformat(), "end_exclusive": True},
        "coverage": {
            "start_date": coverage["start_date"], "end_date": coverage["end_date"],
            "complete": coverage["complete"], "status": "complete" if complete else "partial_window",
        },
        "support": dict.fromkeys(("window", "item", "supplier", "supplier_item", "business_unit")),
        "unavailability": dict.fromkeys(FEATURE_NAMES),
        "diagnostics": {
            "item": dict.fromkeys(_METRICS),
            "supplier_item": {"unit_price": None},
        },
    }


def _apply_references(result, current, support, item_stats, pair_stats):
    """One implementation of all nine formulas; callers only supply causal references."""
    result["support"] = dict(support)
    if result["coverage"]["status"] != "complete":
        result["unavailability"] = dict.fromkeys(FEATURE_NAMES, "partial_window")
        return result
    features, reasons = result["features"], result["unavailability"]
    for name, group in zip(FEATURE_NAMES[6:], ("supplier", "supplier_item", "business_unit"), strict=True):
        features[name] = support[group]
    # Batch references can be shared internally; each public result owns its diagnostics.
    result["diagnostics"] = {
        "item": {metric: None if stats is None else dict(stats) for metric, stats in item_stats.items()},
        "supplier_item": {"unit_price": None if pair_stats is None else dict(pair_stats)},
    }
    for name, metric in (
        (FEATURE_NAMES[0], "unit_price"),
        (FEATURE_NAMES[3], "quantity"),
        (FEATURE_NAMES[4], "line_total"),
        (FEATURE_NAMES[5], "unit_price"),
    ):
        stats = pair_stats if name == FEATURE_NAMES[5] else item_stats[metric]
        if stats is None:
            reasons[name] = "insufficient_history"
        else:
            features[name], reasons[name] = _divide(current[metric], stats["median"])
    price_stats = item_stats["unit_price"]
    if price_stats is None:
        reasons[FEATURE_NAMES[1]] = reasons[FEATURE_NAMES[2]] = "insufficient_history"
    else:
        features[FEATURE_NAMES[1]], reasons[FEATURE_NAMES[1]] = _divide(
            float(current["unit_price"]) - price_stats["median"], price_stats["iqr"], "zero_iqr",
        )
        features[FEATURE_NAMES[2]], reasons[FEATURE_NAMES[2]] = _divide(
            price_stats["iqr"], price_stats["median"],
        )
    return result


def prepare_features(operation, history, *, source, coverage):
    """Return nine ordered features, causal support and explicit missing reasons.

    Inputs are ordinary dicts; history is a list/tuple of dicts or None.
    source contains source_id='procurement-spend', a nonempty source_version
    and entity_namespace, origin='synthetic',
    monetary_unit='unspecified_source_unit', and
    temporal_assumption='available_at_order_no_revisions'.
    These metadata are supplied assertions, not verified external provenance.

    Each line contains matching source_id/source_version/entity_namespace,
    po_id, order_date (strict YYYY-MM-DD), supplier_id, item, business_unit,
    unit_price, quantity and line_total. Names/IDs must be nonempty strings
    without surrounding whitespace or control characters. Quantity is a positive Python int;
    money is a positive finite int/float/Decimal, with exact decimal equality
    line_total = unit_price * quantity. Item names identify units only within
    this source version/namespace; no unit conversion or fuzzy matching occurs.
    The other eight CSV fields are optional context and deliberately ignored,
    including delivery and quality. Unknown keys are rejected for selected rows.

    coverage contains matching identity keys, start_date and end_date
    (inclusive bounds), and complete (bool, no internal gaps when True).
    No dates, coverage, currency code or entity catalogue are inferred from
    observed rows. The known CSV span must be supplied explicitly by its caller.
    History rows selected in [t-90d,t) must lie within these declared bounds.
    Their invalid inputs block the call rather than being silently discarded.
    Identical repeated lines are retained; conflicting pre-order versions of
    the same po_id are rejected, never resolved by picking one silently.
    Same-day/future/older rows are excluded before inspecting their other fields.

    None history returns nulls with missing_history and unknown support.
    Empty history with full coverage returns valid zero counts. Incomplete
    coverage yields partial_window for every feature, with observed support
    retained separately. References require 20 rows; counts do not. No missing
    value is imputed. Medians/quantiles use linear interpolation; MAD is an
    auxiliary diagnostic. Sample std is not needed by this contract.

    This is preparation only: no model, fraud probability, score or claim of
    training readiness. All returned structures are fresh, JSON-compatible
    objects. Raises FeatureValidationError for invalid inputs/numeric range.
    """
    coverage_start, coverage_end = _metadata(source, coverage)
    current = _row(operation, source)
    cutoff = current["order_date"]
    result = _initialize_result(current, source, coverage, coverage_start, coverage_end)
    if history is None:
        result["unavailability"] = dict.fromkeys(FEATURE_NAMES, "missing_history")
        return result
    selected = _select_history(
        history, source, current, date.fromisoformat(result["window"]["start"]), cutoff,
        coverage_start, coverage_end,
    )
    item_rows = [row for row in selected if row["item"] == current["item"]]
    supplier_rows = [row for row in selected if row["supplier_id"] == current["supplier_id"]]
    pair_rows = [row for row in item_rows if row["supplier_id"] == current["supplier_id"]]
    unit_rows = [row for row in selected if row["business_unit"] == current["business_unit"]]
    support = {
        "window": len(selected), "item": len(item_rows), "supplier": len(supplier_rows),
        "supplier_item": len(pair_rows), "business_unit": len(unit_rows),
    }
    if result["coverage"]["status"] != "complete":
        return _apply_references(result, current, support, None, None)
    item_stats = {metric: _statistics(item_rows, metric) for metric in _METRICS}
    pair_stats = _statistics(pair_rows, "unit_price")
    return _apply_references(result, current, support, item_stats, pair_stats)
