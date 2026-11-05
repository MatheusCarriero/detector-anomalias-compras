"""Pure experimental matrices for Procurement V2, without I/O or model fitting."""

from collections import Counter, defaultdict
from datetime import timedelta
from itertools import groupby

from ml.procurement_v2 import features as single

BATCH_VERSION = "procurement-experimental-matrix/1.0"
MATRIX_FEATURES = (
    "price_to_item_median_90d",
    "quantity_to_item_median_90d",
    "item_price_relative_iqr_90d",
    "supplier_item_lines_90d",
    "business_unit_lines_90d",
)
# Inclusive start, exclusive end. These are approved retrospective periods, not blind sets.
PERIODS = (
    ("warmup", "2023-01-01", "2023-04-01"),
    ("development", "2023-04-01", "2025-01-01"),
    ("validation_2025", "2025-01-01", "2026-01-01"),
    ("retrospective_2026", "2026-01-01", "2026-07-01"),
)


def _period(day):
    text = day.isoformat()
    for name, start, end in PERIODS:
        if start <= text < end:
            return name
    raise single.FeatureValidationError("outside_experiment")


def _validated_rows(data, source, coverage_start, coverage_end):
    if type(data) not in (list, tuple):
        raise single.FeatureValidationError("invalid_batch")
    rows, identities = [], {}
    for raw in data:
        row = single._row(raw, source)
        row["period"] = _period(row["order_date"])
        if not coverage_start <= row["order_date"] <= coverage_end:
            raise single.FeatureValidationError("inconsistent_coverage")
        category = raw.get("category")
        if category is not None:
            single._identifier(category)
        row["category"] = category  # Reporting only; never a feature or grouping reference.
        previous = identities.get(row["po_id"])
        if previous is not None and previous != row:
            raise single.FeatureValidationError("conflicting_identity")
        identities[row["po_id"]] = row
        rows.append(row)  # Identical rows are deliberately retained with full multiplicity.
    return sorted(rows, key=lambda row: (row["order_date"], row["po_id"]))


def _daily_results(current_rows, history, source, coverage, coverage_start, coverage_end):
    by_item, by_pair = defaultdict(list), defaultdict(list)
    suppliers, units = Counter(), Counter()
    for row in history:
        by_item[row["item"]].append(row)
        by_pair[row["supplier_id"], row["item"]].append(row)
        suppliers[row["supplier_id"]] += 1
        units[row["business_unit"]] += 1
    item_cache, pair_cache = {}, {}
    for current in current_rows:
        item, supplier, unit = current["item"], current["supplier_id"], current["business_unit"]
        pair = supplier, item
        result = single._initialize_result(current, source, coverage, coverage_start, coverage_end)
        support = {
            "window": len(history), "item": len(by_item[item]), "supplier": suppliers[supplier],
            "supplier_item": len(by_pair[pair]), "business_unit": units[unit],
        }
        if result["coverage"]["status"] != "complete":
            yield single._apply_references(result, current, support, None, None)
            continue
        if item not in item_cache:
            item_cache[item] = {metric: single._statistics(by_item[item], metric)
                                for metric in single._METRICS}
        if pair not in pair_cache:
            pair_cache[pair] = single._statistics(by_pair[pair], "unit_price")
        yield single._apply_references(result, current, support, item_cache[item], pair_cache[pair])


def _summary(operations):
    summaries = {}
    for period, _, _ in PERIODS:
        selected = [op for op in operations if op["period"] == period]
        categories = defaultdict(list)
        for op in selected:
            categories[op["category"]].append(op)

        def counts(rows):
            eligible = sum(row["eligible"] for row in rows)
            reasons = Counter(reason for row in rows for reason in row["exclusion_reasons"])
            return {
                "rows": len(rows), "eligible": eligible, "excluded": len(rows) - eligible,
                "exclusion_reasons": dict(sorted(reasons.items())),
            }

        summaries[period] = {
            **counts(selected),
            "by_category": [
                {"category": category, **counts(categories[category])}
                for category in sorted(categories, key=lambda value: (value is not None, value or ""))
            ],
        }
    return summaries


def prepare_batch(data, *, source, coverage):
    """Return per-line diagnostics and four deterministic, separately identified matrices.

    data is the explicitly supplied purchase population (list/tuple); source,
    coverage and row fields follow P5.6. Each line is validated once. The caller
    must assert coverage/completeness truthfully; missing source rows cannot be
    detected from an empty calendar day. None is not an empty population.

    The approved experiment spans 2023-01-01 through 2026-06-30. Lines outside
    it, outside declared coverage, invalid inputs or conflicting versions of an
    ID reject the entire batch; no partial successful output silently drops them.
    Category is optional reporting metadata (string or None); it never affects
    references or features. Outcome/cadastral fields ignored by P5.6 stay ignored.

    Identical repeated IDs remain separate occurrences. Near duplicates with
    different IDs are never removed. Sorting by date and ID is for stable output
    only: every line on a day shares history [day-90d,day), never intraday order.
    Occurrences distinguish identical copies, not physical source-file positions.

    operations retains the complete nine-feature result, reasons, category,
    period and eligibility for every occurrence. matrices[period] contains only
    the five approved numeric columns in values, and separate trace entries
    (po_id, date, occurrence, operation_index). No identifiers enter values.
    Only complete five-feature rows enter a matrix; warmup never does. All other
    rows remain in operations and summary, without filling, imputation or scores.

    The later periods were already explored; no partition is a blind holdout.
    Only prior purchase fields are used to update rolling references within each
    period. This function performs no training, inference, file access or export.
    All results are fresh JSON-compatible objects and contain no runtime timestamp.
    """
    coverage_start, coverage_end = single._metadata(source, coverage)
    rows = _validated_rows(data, source, coverage_start, coverage_end)
    matrices = {period: {"values": [], "trace": []} for period, _, _ in PERIODS}
    operations, occurrences = [], Counter()
    left = right = 0
    for day, group in groupby(rows, key=lambda row: row["order_date"]):
        current_rows = list(group)
        lower = day - timedelta(days=single.WINDOW_DAYS)
        while right < len(rows) and rows[right]["order_date"] < day:
            right += 1
        while left < right and rows[left]["order_date"] < lower:
            left += 1
        results = _daily_results(
            current_rows, rows[left:right], source, coverage, coverage_start, coverage_end,
        )
        for current, result in zip(current_rows, results, strict=True):
            reasons = sorted({result["unavailability"][name] for name in MATRIX_FEATURES
                              if result["features"][name] is None})
            if not reasons and current["period"] == "warmup":
                reasons = ["warmup_period"]
            eligible = not reasons
            occurrences[current["po_id"]] += 1
            occurrence = occurrences[current["po_id"]]
            operation_index = len(operations)
            operations.append({
                "period": current["period"], "category": current["category"],
                "occurrence": occurrence, "eligible": eligible,
                "exclusion_reasons": reasons, "feature_result": result,
            })
            if eligible:
                matrix = matrices[current["period"]]
                matrix["values"].append([result["features"][name] for name in MATRIX_FEATURES])
                matrix["trace"].append({
                    "po_id": current["po_id"], "order_date": day.isoformat(),
                    "occurrence": occurrence, "operation_index": operation_index,
                })
    return {
        "contract": BATCH_VERSION, "feature_contract": single.CONTRACT_VERSION,
        "source": dict(source), "coverage": dict(coverage),
        "matrix_feature_names": list(MATRIX_FEATURES),
        "periods": [{"name": name, "start": start, "end": end, "end_exclusive": True}
                    for name, start, end in PERIODS],
        "later_periods_previously_explored": True,
        "operations": operations, "matrices": matrices, "summary": _summary(operations),
    }
