"""P5.13 controlled counterfactuals; no file access or estimator fitting.

Sampling is stratified by item/period, without scores, not population-weighted.
Each scenario replaces a single original operation against unchanged historical
references and ranking peers. All outputs are descriptive, not fraud labels.
"""

import copy
import hashlib
import json
import random
from bisect import bisect_left
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal, localcontext

import numpy as np
import pandas as pd

from ml.procurement_v2 import baseline, features
from ml.procurement_v2.batch import (
    BATCH_VERSION,
    MATRIX_FEATURES,
    PERIODS,
    prepare_batch,
)
from ml.procurement_v2.comparison import commercial_deviation

EXPERIMENT_VERSION = "procurement-controlled-injections/1.0"
SCENARIOS = ("A", "B", "C", "D", "E")
SCENARIO_DEFINITIONS = {
    "A": "unit_price * 1.5; quantity unchanged",
    "B": "unit_price * 2; quantity unchanged",
    "C": "quantity * 3; unit_price unchanged",
    "D": "max(1, ROUND_HALF_UP(quantity * 0.1)); unchanged -> not applicable",
    "E": "unit_price * 1.5; quantity * 3",
}
EVALUATION_PERIODS = ("validation_2025", "retrospective_2026")


class InjectionError(ValueError):
    """Invalid experiment inputs or outputs, without sensitive row values."""


def inject(operation, scenario, *, source):
    """Return an independent copy with exact Decimal total, or None for D(q=1).

    Currency is unspecified: do not silently round prices to two decimals.
    Identity, date, supplier and every unrelated field remain unchanged.
    """
    current = features._row(operation, source)
    if scenario not in SCENARIOS:
        raise InjectionError("scenario")
    changed = copy.deepcopy(operation)
    price, quantity = current["unit_price"], current["quantity"]
    with localcontext() as context:
        context.prec = max(28, len(price.as_tuple().digits) + len(str(quantity)) + 10)
        if scenario in ("A", "E"):
            price *= Decimal("1.5")
        elif scenario == "B":
            price *= 2
        if scenario in ("C", "E"):
            quantity *= 3
        elif scenario == "D":
            quantity = max(1, int((Decimal(quantity) * Decimal("0.1")).quantize(
                Decimal(1), rounding=ROUND_HALF_UP,
            )))
            if quantity == current["quantity"]:
                return None
        changed.update(unit_price=price, quantity=quantity, line_total=price * quantity)
    features._row(changed, source)
    return changed


def counterfactual_features(original, modified, reference, *, source):
    """Reuse the P5.6 formula implementation with frozen P5.8 diagnostics.

    reference must be the original operation's trusted P5.8 result. No scenario
    is inserted into history. All nine features are computed, including fields
    outside the five-column model. Missing references remain missing.
    """
    old = features._row(original, source)
    new = features._row(modified, source)
    allowed = {"unit_price", "quantity", "line_total"}
    if (original.keys() != modified.keys()
            or any(original[k] != modified[k] for k in original.keys() - allowed)):
        raise InjectionError("unrelated_change")
    if (reference["operation_id"] != original["po_id"]
            or reference["cutoff_date"] != original["order_date"]
            or reference["contract"] != features.CONTRACT_VERSION
            or reference["source"] != source
            or reference["feature_names"] != list(features.FEATURE_NAMES)):
        raise InjectionError("reference_identity")
    diagnostics = reference["diagnostics"]
    arguments = (reference["support"], diagnostics["item"], diagnostics["supplier_item"]["unit_price"])
    reconstructed = features._apply_references(copy.deepcopy(reference), old, *arguments)
    if reconstructed != reference:
        raise InjectionError("original_reference_values")
    return features._apply_references(copy.deepcopy(reference), new, *arguments)


def select_operations(data, batch, *, seed=42, per_item=5):
    """Sample min(per_item,N) without replacement per eligible item/period.

    A separate RNG seeded by SHA256(JSON([seed,period,item])) prevents changes
    in one stratum from changing another. Candidates sort by date/ID/occurrence.
    No model scores, post-delivery attributes or anomaly outcomes are consulted.
    """
    if type(seed) is not int or type(per_item) is not int or per_item < 1:
        raise InjectionError("selection_configuration")
    catalog = {row["po_id"]: row for row in data}
    groups = defaultdict(list)
    for period in EVALUATION_PERIODS:
        for trace in batch["matrices"][period]["trace"]:
            row = catalog[trace["po_id"]]
            groups[period, row["item"]].append({
                **trace, "period": period, "item": row["item"], "category": row.get("category"),
            })
    selected = []
    for (period, item), candidates in sorted(groups.items()):
        candidates.sort(key=lambda row: (row["order_date"], row["po_id"], row["occurrence"]))
        digest = hashlib.sha256(json.dumps([seed, period, item], separators=(",", ":"),
                                           ensure_ascii=True).encode()).hexdigest()
        selected.extend(random.Random(int(digest, 16)).sample(candidates, min(per_item, len(candidates))))
    return sorted(selected, key=lambda row: (row["period"], row["order_date"], row["po_id"], row["occurrence"]))


def replacement_rank(population_keys, old_key, new_key):
    """1-based rank replacing just one occurrence, keeping all peers unchanged.

    Keys must be sorted (-score,ID,date,occurrence). Population stays same size.
    Exact ties follow the original ordering; no tolerance or rounding is added.
    """
    index = bisect_left(population_keys, old_key)
    if index == len(population_keys) or population_keys[index] != old_key or old_key[1:] != new_key[1:]:
        raise InjectionError("ranking_identity")
    return bisect_left(population_keys, new_key) + 1 - int(old_key < new_key)


def _distribution(values):
    if not values:
        return None
    values = np.asarray(values, dtype=float)
    return {"min": float(values.min()), "max": float(values.max()), "mean": float(values.mean()),
            **dict(zip(("p05", "median", "p95"),
                       map(float, np.quantile(values, [.05, .5, .95], method="linear")), strict=True))}


def summarize_pairs(rows, references):
    """Effect denominators exclude NA; category statistics require >=10 pairs."""
    groups = defaultdict(list)
    for row in rows:
        key = (row["period"], row["scenario"], row["method"])
        groups[(*key, None)].append(row)
        if row["category"] is not None:
            groups[(*key, row["category"])].append(row)
    reports = []
    for (period, scenario, method, category), selected in sorted(groups.items(), key=lambda kv: str(kv[0])):
        valid = [row for row in selected if row["applicable"]]
        report = {"period": period, "scenario": scenario, "method": method, "category": category,
                  "selected": len(selected), "valid": len(valid), "not_applicable": len(selected) - len(valid),
                  "metrics_available": bool(valid) and (category is None or len(valid) >= 10)}
        if report["metrics_available"]:
            delta = [r["score_after"] - r["score_before"] for r in valid]
            for label, count in (("increased", sum(v > 0 for v in delta)),
                                 ("equal", sum(v == 0 for v in delta)),
                                 ("decreased", sum(v < 0 for v in delta))):
                report[label] = count
                report[label + "_pct"] = 100 * count / len(valid)
            report.update(score_before=_distribution([r["score_before"] for r in valid]),
                          score_after=_distribution([r["score_after"] for r in valid]),
                          delta=_distribution(delta), absolute_delta=_distribution([abs(v) for v in delta]),
                          rank_gain=_distribution([r["rank_before"] - r["rank_after"] for r in valid]))
            for quantile, value in references[method].items():
                for when in ("before", "after"):
                    report[f"{quantile}_{when}_pct"] = 100 * sum(r[f"score_{when}"] >= value for r in valid) / len(valid)
        reports.append(report)
    return reports


def _scores(model, values):
    frame = pd.DataFrame(values, columns=list(MATRIX_FEATURES), dtype=float)
    with np.errstate(over="ignore", invalid="ignore"):
        if not np.isfinite(frame.to_numpy()).all() or not np.isfinite(frame.to_numpy(dtype=np.float32)).all():
            raise InjectionError("invalid_matrix")
    if frame.empty:
        return []
    raw = np.asarray(model.score_samples(frame), dtype=float)
    if raw.shape != (len(frame),) or not np.isfinite(raw).all():
        raise InjectionError("invalid_scores")
    return (-raw).tolist()


def run_experiment(model, data, *, source, coverage, seed=42, per_item=5):
    """Score original/counterfactual pairs with an already fitted estimator.

    Caller owns the authorized fit, checksum/version preflight and persistence.
    This function never fits. It validates P5.8 matrices, selects before seeing
    scores, and derives both methods' P95/P99 solely from original development.
    P5.8 prepares the batch from these same source rows, preventing a separately
    supplied matrix from being joined to unrelated supplier/item identities.
    No per-scenario history is rebuilt or modified.
    Categories/months are reporting context only. NA scenarios receive no new
    score/rank; all effects use paired valid cases. No operational thresholds.
    """
    batch = prepare_batch(data, source=source, coverage=coverage)
    if (batch["contract"] != BATCH_VERSION or batch["feature_contract"] != features.CONTRACT_VERSION
            or batch["matrix_feature_names"] != list(MATRIX_FEATURES)
            or model.n_features_in_ != 5 or list(model.feature_names_in_) != list(MATRIX_FEATURES)):
        raise InjectionError("feature_contract")
    for period, start, end in PERIODS:
        baseline._matrix(batch, period, start, end)
    selected = select_operations(data, batch, seed=seed, per_item=per_item)
    catalog = {row["po_id"]: row for row in data}
    originals, rankings, lookups = {}, {}, {}
    for period in ("development", *EVALUATION_PERIODS):
        matrix = batch["matrices"][period]
        originals[period] = {"IF": _scores(model, matrix["values"]),
                             "B": [commercial_deviation(v[0], v[1]) for v in matrix["values"]]}
        lookups[period] = {r["operation_index"]: i for i, r in enumerate(matrix["trace"])}
        rankings[period] = {method: sorted((-score, r["po_id"], r["order_date"], r["occurrence"])
                                          for score, r in zip(scores, matrix["trace"], strict=True))
                            for method, scores in originals[period].items()}
    if not originals["development"]["IF"]:
        raise InjectionError("empty_development")
    references = {method: dict(zip(("p95", "p99"), map(float, np.quantile(scores, [.95, .99], method="linear")), strict=True))
                  for method, scores in originals["development"].items()}
    pending, changed_values = [], []
    for selected_row in selected:
        original = catalog[selected_row["po_id"]]
        reference = batch["operations"][selected_row["operation_index"]]["feature_result"]
        for scenario in SCENARIOS:
            modified = inject(original, scenario, source=batch["source"])
            vector = None
            if modified is not None:
                result = counterfactual_features(original, modified, reference, source=batch["source"])
                vector = [result["features"][f] for f in MATRIX_FEATURES]
                if any(v is None for v in vector):
                    raise InjectionError("unexpected_ineligibility")
                changed_values.append(vector)
            pending.append((selected_row, original, modified, scenario, vector))
    changed_if = iter(_scores(model, changed_values))
    pairs = []
    for selected_row, original, modified, scenario, vector in pending:
        period = selected_row["period"]
        i = lookups[period][selected_row["operation_index"]]
        changed = {"IF": next(changed_if), "B": commercial_deviation(vector[0], vector[1])} if vector is not None else None
        for method in ("IF", "B"):
            before = originals[period][method][i]
            old_key = (-before, selected_row["po_id"], selected_row["order_date"], selected_row["occurrence"])
            after = changed[method] if changed else None
            before_rank = bisect_left(rankings[period][method], old_key) + 1
            after_rank = replacement_rank(rankings[period][method], old_key, (-after, *old_key[1:])) if changed else None
            pairs.append({**selected_row, "supplier_id": original["supplier_id"], "business_unit": original["business_unit"],
                          "scenario": scenario, "method": method, "applicable": modified is not None,
                          "not_applicable_reason": "unchanged_quantity" if modified is None else None,
                          "price_before": str(original["unit_price"]), "quantity_before": original["quantity"],
                          "total_before": str(original["line_total"]),
                          "price_after": str(modified["unit_price"]) if modified else None,
                          "quantity_after": modified["quantity"] if modified else None,
                          "total_after": str(modified["line_total"]) if modified else None,
                          "features_before": list(batch["matrices"][period]["values"][i]), "features_after": vector,
                          "score_before": before, "score_after": after, "rank_before": before_rank, "rank_after": after_rank,
                          "delta": after - before if changed else None,
                          "rank_gain": before_rank - after_rank if changed else None})
    return {"experiment": EXPERIMENT_VERSION, "selection": selected, "pairs": pairs,
            "references": references, "summary": summarize_pairs(pairs, references),
            "source_summary": copy.deepcopy(batch["summary"]),
            "original_statistics": {period: {method: baseline._statistics(np.asarray(scores))
                                               for method, scores in methods.items()} for period, methods in originals.items()}}
