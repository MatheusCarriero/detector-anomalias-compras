"""P5.11: compare existing IF scores with a fixed commercial-deviation rule.

No fitting, calibration, persistence or I/O. Inputs are explicit in-memory
P5.9 results and the source lines used to prepare them. Preparation is delegated
unchanged to P5.8; all five features and every occurrence are reconciled before
comparing the same eligible population. Historical medians remain causal.
"""

import copy
import hashlib
import json
import math
from collections import Counter

import numpy as np

from ml.procurement_v2.baseline import EXPERIMENT_VERSION, MODEL_PARAMETERS
from ml.procurement_v2.batch import MATRIX_FEATURES, PERIODS, prepare_batch

COMPARISON_VERSION = "procurement-commercial-comparison/1.0"
FORMULA = "max(abs(ln(price_to_item_median_90d)), abs(ln(quantity_to_item_median_90d)))"
_GROUPS = ("category", "item", "supplier_id", "business_unit", "order_month", "month_of_year")


class ComparisonError(ValueError):
    """Incompatible comparison inputs; messages contain codes, not row values."""


def _number(value):
    if type(value) not in (int, float):
        raise ComparisonError("invalid_number")
    try:
        number = float(value)
    except OverflowError:
        raise ComparisonError("invalid_number") from None
    if not math.isfinite(number):
        raise ComparisonError("invalid_number")
    return number


def commercial_deviation(price_ratio, quantity_ratio):
    """Largest absolute log ratio, with equal multiplicative sensitivity.

    Ratios 2 and 0.5 are equally distant from 1 mathematically. Direct logs
    avoid overflow from reciprocal conversion. No distribution calibration,
    epsilon, rounding, clipping or imputation is used. This measures magnitude,
    not empirical rarity: the wider quantity distribution can dominate. The
    smaller deviation does not accumulate, and sign is reported separately.
    """
    ratios = (_number(price_ratio), _number(quantity_ratio))
    if min(ratios) <= 0:
        raise ComparisonError("nonpositive_ratio")
    return max(abs(math.log(value)) for value in ratios)


def _key(row):
    return row["po_id"], row["order_date"], row["occurrence"]


def _rank(rows):
    ordered = sorted(rows, key=lambda row: (-row["score"], *_key(row)))
    return [{**row, "rank": rank} for rank, row in enumerate(ordered, 1)]


def _fraction(numerator, denominator):
    return numerator / denominator if denominator else None


def _validate_metadata(result, batch):
    metadata = result["metadata"]
    if type(metadata) is not dict:
        raise ComparisonError("baseline_metadata")
    expected = {
        "experiment": EXPERIMENT_VERSION, "parameters": MODEL_PARAMETERS,
        "batch_contract": batch["contract"], "feature_contract": batch["feature_contract"],
        "feature_names": list(MATRIX_FEATURES), "source": batch["source"],
        "coverage": batch["coverage"], "periods": batch["periods"],
        "score_convention": "-score_samples", "score_semantics": "statistical_anomaly",
        "preprocessing": "none", "fit_calls": 1, "later_periods_previously_explored": True,
    }
    if any(metadata.get(key) != value for key, value in expected.items()):
        raise ComparisonError("baseline_metadata")
    matrix = batch["matrices"]["development"]
    fingerprint = hashlib.sha256(json.dumps({
        "feature_names": list(MATRIX_FEATURES), "source": batch["source"], "matrix": matrix,
    }, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
    if metadata["training"] != {
        "period": "development", "rows": len(matrix["values"]), "features": 5,
        "matrix_sha256": fingerprint, "effective_max_samples": min(256, len(matrix["values"])),
    }:
        raise ComparisonError("training_identity")
    if set(result["periods"]) != {period for period, _, _ in PERIODS}:
        raise ComparisonError("periods")
    if result["eligibility_summary"] != batch["summary"]:
        raise ComparisonError("eligibility_summary")


def _enrich(row, catalog):
    source_row = catalog[row["po_id"]]
    return {**row, **{name: source_row[name] for name in ("supplier_id", "item", "business_unit")},
            "order_month": row["order_date"][:7], "month_of_year": row["order_date"][5:7]}


def _period_rows(result, batch, period, catalog):
    matrix = batch["matrices"][period]
    expected = {}
    for trace, values in zip(matrix["trace"], matrix["values"], strict=True):
        operation = batch["operations"][trace["operation_index"]]
        expected[_key(trace)] = (values, operation["category"])
    supplied = result["periods"][period]
    summary = batch["summary"][period]
    if any(supplied[key] != summary[key] for key in ("rows", "eligible", "excluded")):
        raise ComparisonError("population_counts")
    if len(supplied["ranking"]) != len(expected):
        raise ComparisonError("ranking_length")
    seen, rows = set(), []
    for row in supplied["ranking"]:
        key = _key(row)
        if type(row["occurrence"]) is not int or key not in expected or key in seen:
            raise ComparisonError("ranking_identity")
        seen.add(key)
        values, category = expected[key]
        features = row["features"]
        if list(features) != list(MATRIX_FEATURES):
            raise ComparisonError("feature_order")
        supplied_values = [_number(features[name]) for name in MATRIX_FEATURES]
        if supplied_values != values or row["category"] != category:
            raise ComparisonError("feature_association")
        score = _number(row["score"])
        # Copy only approved reporting fields; no delivery/quality labels.
        rows.append(_enrich({"po_id": key[0], "order_date": key[1], "occurrence": key[2],
                             "category": category, "score": score,
                             "features": dict(features), "rank": row["rank"]}, catalog))
    ordered = _rank(rows)
    recorded_ranks = {_key(row): row["rank"] for row in rows}
    if any(type(recorded_ranks[_key(row)]) is not int
           or recorded_ranks[_key(row)] != row["rank"] for row in ordered):
        raise ComparisonError("ranking_order")
    return ordered


def _group_counts(all_rows, eligible, a, b):
    output = {}
    for name in _GROUPS:
        total, population, selected_a, selected_b = (
            Counter(row[name] for row in rows) for rows in (all_rows, eligible, a, b)
        )
        output[name] = [{
            "name": group, "total": total[group], "eligible": population[group],
            "excluded": total[group] - population[group], "a": selected_a[group], "b": selected_b[group],
            "population_share": _fraction(population[group], len(eligible)),
            "a_share": _fraction(selected_a[group], len(a)), "b_share": _fraction(selected_b[group], len(b)),
            "a_selection_rate": _fraction(selected_a[group], population[group]),
            "b_selection_rate": _fraction(selected_b[group], population[group]),
        } for group in sorted(total, key=lambda value: (value is not None, value or ""))]
    return output


def _quantiles(values):
    if not values:
        return None
    return dict(zip(("min", "p05", "median", "p95", "max"),
                    (float(v) for v in np.quantile(values, [0, .05, .5, .95, 1], method="linear")),
                    strict=True))


def _profile(rows):
    features = {name: [row["features"][name] for row in rows] for name in MATRIX_FEATURES}
    prices, quantities = features[MATRIX_FEATURES[0]], features[MATRIX_FEATURES[1]]
    price_logs, quantity_logs = ([abs(math.log(value)) for value in values] for values in (prices, quantities))
    return {
        "n": len(rows), "features": {name: _quantiles(values) for name, values in features.items()},
        "directions": {name: {"below": sum(v < 1 for v in values), "equal": sum(v == 1 for v in values),
                              "above": sum(v > 1 for v in values)}
                       for name, values in (("price", prices), ("quantity", quantities))},
        "absolute_log_deviation": {"price": _quantiles(price_logs), "quantity": _quantiles(quantity_logs)},
        "rule_dominance": {
            "price": sum(p > q for p, q in zip(price_logs, quantity_logs, strict=True)),
            "quantity": sum(q > p for p, q in zip(price_logs, quantity_logs, strict=True)),
            "equal": sum(p == q for p, q in zip(price_logs, quantity_logs, strict=True)),
        },
    }


def _boundary(ranking, k):
    if not k:
        return {"score": None, "tied": 0, "selected_tied": 0}
    value = ranking[k - 1]["score"]
    return {"score": value, "tied": sum(row["score"] == value for row in ranking),
            "selected_tied": sum(row["score"] == value for row in ranking[:k])}


def compare_methods(baseline_result, data, *, source, coverage, k=30):
    """Reconcile approved scores, rank the fixed rule, return descriptive evidence.

    The caller supplies the original baseline result from a trusted execution;
    internal consistency does not authenticate its provenance. This function
    never invokes run_baseline/fit/score_samples. It recomputes P5.8 only, checks
    its development fingerprint and all period associations, and refuses stale
    scores instead of silently scoring/retraining. Source hashes and dependency
    versions must be checked by the experiment executor before using results.

    K is a review budget, not a score threshold. Float scores are never rounded
    before sorting. Exact ties use ID/date/occurrence; boundary ties are reported.
    Identical duplicate lines retain occurrences. Both methods use all five-
    feature eligible rows, even though the rule itself needs only two columns.

    Directions are relative to median=1, not abnormality flags. Profiles and
    group shares describe associations, never causal attribution or accuracy.
    Development is in-sample; 2025/2026 are retrospective, previously explored.
    """
    if type(k) is not int or k < 1:
        raise ComparisonError("invalid_k")
    batch = prepare_batch(data, source=source, coverage=coverage)
    try:
        _validate_metadata(baseline_result, batch)
        # P5.8 already rejected conflicting repeated IDs. Ignore post-delivery fields.
        catalog = {row["po_id"]: row for row in data}
        all_rows = {period: [] for period, _, _ in PERIODS}
        excluded = []
        for operation in batch["operations"]:
            reference = operation["feature_result"]
            row = {"po_id": reference["operation_id"], "order_date": reference["cutoff_date"],
                   "occurrence": operation["occurrence"], "category": operation["category"]}
            all_rows[operation["period"]].append(_enrich(row, catalog))
            if not operation["eligible"]:
                excluded.append({**row, "period": operation["period"],
                                 "reasons": list(operation["exclusion_reasons"]),
                                 "support": dict(reference["support"])})
        if excluded != baseline_result["excluded_operations"]:
            raise ComparisonError("excluded_population")
        reports = {}
        for period, _, _ in PERIODS:
            a = _period_rows(baseline_result, batch, period, catalog)
            b = _rank([{**row, "score": commercial_deviation(
                row["features"][MATRIX_FEATURES[0]], row["features"][MATRIX_FEATURES[1]],
            )} for row in a])
            effective_k = min(k, len(a))
            top_a, top_b = a[:effective_k], b[:effective_k]
            keys_a, keys_b = {_key(row) for row in top_a}, {_key(row) for row in top_b}
            common = keys_a & keys_b
            only_a = [row for row in top_a if _key(row) not in common]
            only_b = [row for row in top_b if _key(row) not in common]
            both = [row for row in top_a if _key(row) in common]
            groups = _group_counts(all_rows[period], a, top_a, top_b)
            reports[period] = {
                **{key: batch["summary"][period][key] for key in ("rows", "eligible", "excluded")},
                "k": effective_k, "top_a": top_a, "top_b": top_b,
                "overlap": {"count": len(common), "fraction": _fraction(len(common), effective_k),
                            "jaccard": _fraction(len(common), len(keys_a | keys_b)),
                            "keys": [list(key) for key in sorted(common)]},
                "exclusive_a": only_a, "exclusive_b": only_b,
                "profiles": {label: _profile(rows) for label, rows in (
                    ("population", a), ("a", top_a), ("b", top_b),
                    ("both", both), ("a_only", only_a), ("b_only", only_b),
                )},
                "groups": groups,
                "diversity": {method: {name: sum(row[method] > 0 for row in groups[name])
                                       for name in _GROUPS[:4]} for method in ("a", "b")},
                "boundary_ties": {"a": _boundary(a, effective_k), "b": _boundary(b, effective_k)},
            }
    except (KeyError, TypeError, IndexError) as exc:
        raise ComparisonError("invalid_result_structure") from exc
    return {
        "metadata": {
            "comparator": COMPARISON_VERSION, "formula": FORMULA, "k": k, "calibration": "none",
            "tie_break": ["score_desc", "po_id", "order_date", "occurrence"],
            "baseline": copy.deepcopy(baseline_result["metadata"]), "new_fits": 0,
            "score_scales_comparable": False, "later_periods_previously_explored": True,
        },
        "periods": reports, "excluded_operations": excluded,
    }
