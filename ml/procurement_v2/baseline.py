"""P5.9: one fixed, retrospective Isolation Forest baseline, entirely in memory.

run_baseline receives typed lines and explicit source/coverage metadata as in
P5.8. It prepares the same batch, fits development only, and scores eligible
lines independently per period. No loader, exporter, imputer, scaler, prediction
class, operational threshold or parameter search is provided.
"""

import hashlib
import json
import sys
from importlib.metadata import version

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from ml.procurement_v2.batch import (
    BATCH_VERSION,
    MATRIX_FEATURES,
    PERIODS,
    prepare_batch,
)
from ml.procurement_v2.features import CONTRACT_VERSION

EXPERIMENT_VERSION = "procurement-isolation-forest-baseline/1.0"
MODEL_PARAMETERS = {
    "n_estimators": 200, "contamination": "auto", "random_state": 42,
    "max_samples": "auto", "max_features": 1.0, "bootstrap": False,
    "n_jobs": 1, "warm_start": False,
}
_PERCENTILES = (1, 5, 25, 50, 75, 90, 95, 99)


class BaselineError(ValueError):
    """Invalid prepared matrix, trace or estimator output; contains no row data."""


def _matrix(batch, period, start, end):
    """Check each numeric row against its operation before any model is fitted."""
    matrix = batch["matrices"][period]
    values, traces = matrix["values"], matrix["trace"]
    if len(values) != len(traces) or len(values) != batch["summary"][period]["eligible"]:
        raise BaselineError("matrix_length")
    seen = set()
    for values_row, trace in zip(values, traces, strict=True):
        if len(values_row) != 5 or any(type(v) not in (int, float) for v in values_row):
            raise BaselineError("matrix_columns")
        index = trace["operation_index"]
        if type(index) is not int or not 0 <= index < len(batch["operations"]) or index in seen:
            raise BaselineError("matrix_trace")
        seen.add(index)
        operation = batch["operations"][index]
        reference = operation["feature_result"]
        if (not operation["eligible"] or operation["period"] != period
                or reference["operation_id"] != trace["po_id"]
                or reference["cutoff_date"] != trace["order_date"]
                or operation["occurrence"] != trace["occurrence"]
                or not start <= trace["order_date"] < end
                or values_row != [reference["features"][name] for name in MATRIX_FEATURES]):
            raise BaselineError("matrix_association")
    expected_indices = {i for i, op in enumerate(batch["operations"])
                        if op["eligible"] and op["period"] == period}
    if seen != expected_indices or (period == "warmup" and values):
        raise BaselineError("matrix_population")
    frame = pd.DataFrame(values, columns=list(MATRIX_FEATURES), dtype=float)
    # sklearn trees convert to float32. A finite float64 may still overflow there.
    with np.errstate(over="ignore", invalid="ignore"):
        if not np.isfinite(frame.to_numpy()).all() or not np.isfinite(frame.to_numpy(dtype=np.float32)).all():
            raise BaselineError("matrix_nonfinite")
    return frame


def _statistics(scores):
    if not len(scores):
        return None
    return {
        "n": len(scores), "min": float(np.min(scores)), "max": float(np.max(scores)),
        "mean": float(np.mean(scores)),
        "std_sample": float(np.std(scores, ddof=1)) if len(scores) > 1 else None,
        "percentiles": {f"p{p:02d}": float(value) for p, value in zip(
            _PERCENTILES, np.percentile(scores, _PERCENTILES, method="linear"), strict=True,
        )},
    }


def _ranking(batch, period, scores):
    ranked = []
    for score, trace, values in zip(scores, batch["matrices"][period]["trace"],
                                    batch["matrices"][period]["values"], strict=True):
        operation = batch["operations"][trace["operation_index"]]
        ranked.append({
            "po_id": trace["po_id"], "order_date": trace["order_date"],
            "occurrence": trace["occurrence"], "category": operation["category"],
            "score": float(score), "features": dict(zip(MATRIX_FEATURES, values, strict=True)),
        })
    ranked.sort(key=lambda r: (-r["score"], r["po_id"], r["order_date"], r["occurrence"]))
    return [{"rank": i, **row} for i, row in enumerate(ranked, 1)]


def run_baseline(data, *, source, coverage):
    """Prepare P5.8, fit once on development, return scores/eligibility/metadata.

    Sorting and temporal references are owned by prepare_batch. Fit sees exactly
    five named columns, never IDs, categories, delivery outcomes or later rows.
    All period matrices are checked before fit. Empty development is rejected;
    empty later periods remain explicit with no scores. Repeated source lines
    retain their occurrence identifiers, without deduplication.

    No transformation is learned. n_jobs=1 and fixed random_state make repeated
    runs deterministic for the same inputs and dependency versions. max_samples
    remains 'auto'; its effective value is recorded. contamination='auto' sets
    an internal sklearn offset only: neither predict nor decision_function is
    called, and the offset is never used to classify a line.

    Scores are -score_samples, not fraud probabilities. Development summaries
    are in-sample. Both later periods were explored in the EDA, so this is not
    blind evaluation. P95/P99 of development are descriptive reference values;
    >= counts retain ties and are never operational flags or risk classes.
    Excluded operations remain traceable, without scores or fabricated values.

    The fitted estimator is used only in memory and is not returned/persisted.
    No files, model uploads, external joblib loading or database are involved.
    """
    batch = prepare_batch(data, source=source, coverage=coverage)
    if (batch["contract"] != BATCH_VERSION or batch["feature_contract"] != CONTRACT_VERSION
            or batch["matrix_feature_names"] != list(MATRIX_FEATURES)):
        raise BaselineError("feature_contract")
    frames = {period: _matrix(batch, period, start, end) for period, start, end in PERIODS}
    development = frames["development"]
    if len(development) < 2:
        raise BaselineError("insufficient_development")
    training_bytes = json.dumps({
        "feature_names": list(MATRIX_FEATURES), "source": batch["source"],
        "matrix": batch["matrices"]["development"],
    }, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    model = IsolationForest(**MODEL_PARAMETERS)
    model.fit(development)
    if model.n_features_in_ != 5 or list(model.feature_names_in_) != list(MATRIX_FEATURES):
        raise BaselineError("fitted_feature_contract")
    scores_by_period = {}
    for period, frame in frames.items():
        if frame.empty:
            scores_by_period[period] = np.array([], dtype=float)
            continue
        raw = np.asarray(model.score_samples(frame), dtype=float)
        if raw.shape != (len(frame),) or not np.isfinite(raw).all():
            raise BaselineError("invalid_scores")
        scores_by_period[period] = -raw
    stats = {period: _statistics(scores) for period, scores in scores_by_period.items()}
    references = {key: stats["development"]["percentiles"][key] for key in ("p95", "p99")}
    periods = {}
    for period, scores in scores_by_period.items():
        summary = batch["summary"][period]
        periods[period] = {
            "rows": summary["rows"], "eligible": summary["eligible"], "excluded": summary["excluded"],
            "statistics": stats[period], "ranking": _ranking(batch, period, scores),
            "upper_tails": {
                key: {"reference_value": value, "count": int(np.count_nonzero(scores >= value)),
                      "fraction": float(np.mean(scores >= value)) if len(scores) else None}
                for key, value in references.items()
            },
        }
    excluded = [{
        "po_id": op["feature_result"]["operation_id"],
        "order_date": op["feature_result"]["cutoff_date"], "occurrence": op["occurrence"],
        "period": op["period"], "category": op["category"],
        "reasons": list(op["exclusion_reasons"]), "support": dict(op["feature_result"]["support"]),
    } for op in batch["operations"] if not op["eligible"]]
    return {
        "metadata": {
            "experiment": EXPERIMENT_VERSION, "batch_contract": BATCH_VERSION,
            "feature_contract": CONTRACT_VERSION, "feature_names": list(MATRIX_FEATURES),
            "source": dict(batch["source"]), "coverage": dict(batch["coverage"]),
            "parameters": dict(MODEL_PARAMETERS), "periods": batch["periods"],
            "training": {"period": "development", "rows": len(development), "features": 5,
                         "matrix_sha256": hashlib.sha256(training_bytes).hexdigest(),
                         "effective_max_samples": int(model.max_samples_)},
            "versions": {"python": sys.version.split()[0], **{name: version(name)
                         for name in ("scikit-learn", "numpy", "pandas")}},
            "score_convention": "-score_samples", "score_semantics": "statistical_anomaly",
            "preprocessing": "none", "fit_calls": 1,
            "sklearn_internal_offset_unused": float(model.offset_),
            "later_periods_previously_explored": True,
            "reference_quantiles": {"population": "development_in_sample", "method": "linear",
                                    "comparison": ">=", "purpose": "descriptive_only"},
        },
        "periods": periods, "excluded_operations": excluded,
        "eligibility_summary": batch["summary"],
    }
