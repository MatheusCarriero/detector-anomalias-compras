"""Historical fixed-budget triage; filesystem runs require external synthetic fixtures."""

import argparse
import hashlib
import json
import math
import platform
import warnings
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.exceptions import InconsistentVersionWarning
from sklearn.utils.validation import check_is_fitted

from ml.scripts.avaliar_invoice import (
    EXPECTED_PARAMS,
    FEATURES,
    PROJECT_ROOT,
    load_validation,
    require_external_invoice_fixture,
    sha256,
    validate_ids,
    validate_target,
    validate_training_features,
)

BUDGETS = (1, 5, 10)
QUANTILES = (0, .01, .05, .25, .5, .75, .95, .99, 1)
QUANTILE_NAMES = ("min", "p01", "p05", "p25", "p50", "p75", "p95", "p99", "max")
PRESERVED_INPUTS = (
    "data/processed/train_features.parquet", "data/processed/val_features.parquet",
    "ml/models/isolation_forest.joblib", "ml/models/model_metadata.json",
)
PREVIOUS = "ml/experiments/invoice_validation_v1.json"
OUTPUT = "ml/experiments/invoice_triage_validation_v1.json"
PROTOCOL = PROJECT_ROOT / "docs/invoice_triage_protocol.md"
RAW_INPUTS = ("data/raw/splits.parquet", "data/raw/labels.parquet", "data/raw/invoices.parquet")


def _vector(values, count=None):
    array = np.asarray(values, dtype=float)
    if (array.ndim != 1 or not len(array) or not np.isfinite(array).all()
            or (count is not None and len(array) != count)):
        raise ValueError("Vetor deve ser não vazio, finito e alinhado.")
    return array


def distribution(values):
    array = _vector(values)
    quantiles = np.quantile(array, QUANTILES, method="linear")
    return {"count": len(array), **dict(zip(QUANTILE_NAMES, map(float, quantiles), strict=True))}


def compare_distributions(train, validation):
    train, validation = _vector(train), _vector(validation)
    grid = np.union1d(train, validation)
    train_cdf = np.searchsorted(np.sort(train), grid, side="right") / len(train)
    val_cdf = np.searchsorted(np.sort(validation), grid, side="right") / len(validation)
    outside = int(np.sum((validation < train.min()) | (validation > train.max())))
    return {
        "train": distribution(train), "validation": distribution(validation),
        "cdf_distance": float(np.max(np.abs(train_cdf - val_cdf))),
        "validation_outside_train_range": outside,
        "validation_outside_train_fraction": outside / len(validation),
    }


def _fingerprint(values):
    return hashlib.sha256(json.dumps(
        values, ensure_ascii=False, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")).hexdigest()


def _rank(frame, scores):
    validate_ids(frame, "ranking")
    validate_target(frame)
    scores = _vector(scores, len(frame))
    return frame.assign(anomaly_score=scores).sort_values(
        ["anomaly_score", "invoice_id"], ascending=[False, True],
    ).reset_index(drop=True)


def rank_summary(frame, scores):
    ranked = _rank(frame, scores)
    n = len(ranked)
    positives = int(ranked["is_fraud"].sum())
    prevalence = positives / n
    budgets = []
    for percent in BUDGETS:
        k = min(n, math.ceil(n * percent / 100))
        selected = ranked.iloc[:k]
        hits = int(selected["is_fraud"].sum())
        boundary = float(selected["anomaly_score"].iloc[-1])
        ambiguous = (
            (selected["is_fraud"].eq(1) & selected["fraud_type"].eq("NONE"))
            | (selected["is_fraud"].eq(0) & selected["fraud_type"].notna()
               & selected["fraud_type"].ne("NONE"))
        )
        by_type = {}
        for name, group in selected.groupby(selected["fraud_type"].fillna("__missing__")):
            by_type[name] = {"rows": len(group), "known_positives": int(group["is_fraud"].sum())}
        budgets.append({
            "percent": percent, "k": k, "fraction": k / n, "known_positives": hits,
            "reference_negatives": k - hits, "precision_at_k": hits / k,
            "capture": hits / positives if positives else None,
            "lift": (hits / k) / prevalence if positives else None,
            "random_expected_positives": k * prevalence,
            "random_precision_at_k": prevalence,
            "random_capture": k / n if positives else None,
            "random_lift": 1.0 if positives else None,
            "boundary_score": boundary,
            "boundary_tie_count": int(ranked["anomaly_score"].eq(boundary).sum()),
            "boundary_ties_selected": int(selected["anomaly_score"].eq(boundary).sum()),
            "selected_ids_sha256": _fingerprint(selected["invoice_id"].tolist()),
            "ambiguous_labels": int(ambiguous.sum()), "by_fraud_type": by_type,
        })
    return {"rows": n, "known_positives": positives, "prevalence": prevalence,
            "scores": distribution(ranked["anomaly_score"]), "budgets": budgets}


def _load_frames(root):
    root = require_external_invoice_fixture(root)
    validation = load_validation(root)
    train = pd.read_parquet(
        root / PRESERVED_INPUTS[0], columns=["invoice_id", "split", *FEATURES],
    ).sort_values("invoice_id").reset_index(drop=True)
    validate_ids(train, "TRAIN")
    if not train["split"].eq("train").all():
        raise ValueError("TRAIN contém split indevido.")
    validate_training_features(train[FEATURES])
    ids = train["invoice_id"].tolist() + validation["invoice_id"].tolist()
    dates = pd.read_parquet(
        root / "data/raw/invoices.parquet", columns=["invoice_id", "invoice_date"],
        filters=[("invoice_id", "in", ids)],
    )
    validate_ids(dates, "datas autorizadas")
    if set(dates["invoice_id"]) != set(ids):
        raise ValueError("Datas não reconciliam com TRAIN/val.")
    dates["invoice_date"] = pd.to_datetime(dates["invoice_date"], errors="raise")
    if dates["invoice_date"].isna().any():
        raise ValueError("Datas nulas não são permitidas.")
    joined = [part.merge(dates, on="invoice_id", how="left", validate="one_to_one")
              for part in (train, validation)]
    dates = dates.sort_values("invoice_id")
    fingerprint = _fingerprint([
        [row.invoice_id, row.invoice_date.isoformat()] for row in dates.itertuples()
    ])
    return *joined, fingerprint


def _load_model(root, previous):
    metadata = json.loads((root / PRESERVED_INPUTS[3]).read_text(encoding="utf-8"))
    if (metadata.get("features") != FEATURES or metadata.get("feature_count") != 19
            or metadata.get("algorithm") != "IsolationForest"
            or any(metadata.get(k) != EXPECTED_PARAMS[k]
                   for k in ("n_estimators", "contamination", "random_state"))):
        raise ValueError("Metadata diverge do contrato Invoice.")
    with warnings.catch_warnings():
        warnings.simplefilter("error", InconsistentVersionWarning)
        model = joblib.load(root / PRESERVED_INPUTS[2])
    if not isinstance(model, IsolationForest):
        raise TypeError("Modelo deve ser o Isolation Forest existente.")
    check_is_fitted(model)
    if (list(model.feature_names_in_) != FEATURES or model.n_features_in_ != 19
            or len(model.estimators_) != 200
            or any(model.get_params()[k] != v for k, v in EXPECTED_PARAMS.items())
            or model.get_params() != previous["parameters"]
            or not np.isfinite(model.offset_) or model.offset_ != previous["offset"]):
        raise ValueError("Modelo diverge da configuração anterior.")
    return model


def _global_selections(ranked, group_ids):
    records = []
    n_group = len(group_ids)
    for percent in BUDGETS:
        k = min(len(ranked), math.ceil(len(ranked) * percent / 100))
        selected = ranked.iloc[:k]
        count = int(selected["invoice_id"].isin(group_ids).sum())
        records.append({
            "percent": percent, "k_global": k, "selected_from_group": count,
            "share_of_global_queue": count / k,
            "selection_rate_within_group": count / n_group if n_group else None,
        })
    return records


def diagnose(model, train, validation):
    # Only approved numerical columns reach the existing model.
    train_score = _vector(-model.score_samples(train[FEATURES]), len(train))
    val_score = _vector(-model.score_samples(validation[FEATURES]), len(validation))
    ranked = _rank(validation, val_score)
    result = {
        "validation": rank_summary(validation, val_score),
        "distributions": {
            "score": compare_distributions(train_score, val_score),
            "features": {f: compare_distributions(train[f], validation[f]) for f in FEATURES},
        },
        "periods": {},
        "context_groups": {},
        "dates": {name: {
            "rows": len(frame), "min": frame["invoice_date"].min().isoformat(),
            "max": frame["invoice_date"].max().isoformat(),
        } for name, frame in (("train", train), ("validation", validation))},
    }
    val_periods = validation["invoice_date"].dt.to_period("M").astype(str)
    for period in sorted(val_periods.unique()):
        mask = val_periods.eq(period).to_numpy()
        group = validation.loc[mask]
        result["periods"][period] = {
            **rank_summary(group, val_score[mask]),
            "date_min": group["invoice_date"].min().isoformat(),
            "date_max": group["invoice_date"].max().isoformat(),
            "global_selections": _global_selections(ranked, set(group["invoice_id"])),
        }
    contexts = {
        "unseen_supplier_department": validation["supplier_department_frequency"].eq(0),
        "month_absent_from_train": ~validation["invoice_date"].dt.month.isin(
            train["invoice_date"].dt.month.unique()),
    }
    for name, mask in contexts.items():
        group = validation.loc[mask]
        result["context_groups"][name] = {
            "rows": len(group), "known_positives": int(group["is_fraud"].sum()),
            "scores": distribution(val_score[mask.to_numpy()]) if len(group) else None,
            "global_selections": _global_selections(ranked, set(group["invoice_id"])),
        }
    return result


def _raw_stats(root):
    return {name: {"bytes": (root / name).stat().st_size,
                   "mtime_ns": (root / name).stat().st_mtime_ns} for name in RAW_INPUTS}


def run(root=PROJECT_ROOT, output=None, split="val"):
    if split != "val":
        raise ValueError("Somente val autorizado; TEST permanece fechado.")
    root = require_external_invoice_fixture(root)
    output = Path(output) if output is not None else root / OUTPUT
    if output.exists():
        raise FileExistsError(f"Saída já existe; não sobrescrever: {output}")
    if output.suffix != ".json":
        raise ValueError("Saída deve ser JSON.")
    hashes = {name: sha256(root / name) for name in (*PRESERVED_INPUTS, PREVIOUS)}
    code_paths = [Path(__file__), PROJECT_ROOT / "ml/scripts/avaliar_invoice.py",
                  PROJECT_ROOT / "ml/scripts/treinar_modelo.py", PROTOCOL]
    code_hashes = {p.relative_to(PROJECT_ROOT).as_posix(): sha256(p) for p in code_paths}
    raw_before = _raw_stats(root)
    previous = json.loads((root / PREVIOUS).read_text(encoding="utf-8"))
    for name in PRESERVED_INPUTS:
        if hashes[name] != previous["input_hashes_sha256"][name].lower():
            raise ValueError(f"Input diverge da avaliação anterior: {name}")
    train, validation, dates_hash = _load_frames(root)
    if (previous["rows"] != len(validation) or previous["split"] != "val"
            or previous["test_used"] is not False):
        raise ValueError("Referência anterior não corresponde à VALIDATION.")
    model = _load_model(root, previous)
    result = diagnose(model, train, validation)
    for name, expected in hashes.items():
        if sha256(root / name) != expected:
            raise ValueError(f"Input alterado durante diagnóstico: {name}")
    for path in code_paths:
        if sha256(path) != code_hashes[path.relative_to(PROJECT_ROOT).as_posix()]:
            raise ValueError("Código/protocolo alterado durante diagnóstico.")
    if _raw_stats(root) != raw_before:
        raise ValueError("Fonte compartilhada alterada durante diagnóstico.")
    result.update({
        "protocol_version": "invoice-triage-1.0", "split": "val",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "real_model_fits": 0, "test_used": False, "threshold_selected": False,
        "budget_percentages": list(BUDGETS), "quantile_method": "linear",
        "score_definition": "-score_samples; not a probability",
        "tie_break": "score descending, invoice_id ascending; no labels",
        "features": FEATURES, "parameters": model.get_params(), "legacy_offset": float(model.offset_),
        "input_hashes_sha256": hashes, "code_and_protocol_sha256": code_hashes,
        "shared_raw_stat_before_after": raw_before, "authorized_dates_sha256": dates_hash,
        "train_ids_sha256": _fingerprint(train["invoice_id"].tolist()),
        "validation_ids_sha256": _fingerprint(validation["invoice_id"].tolist()),
        "versions": {"python": platform.python_version(), **{
            name: version(name) for name in ("numpy", "pandas", "scikit-learn", "joblib", "pyarrow")
        }},
        "limits": [
            "is_fraud is an unverified secondary reference, not business ground truth",
            "TRAIN scores are in-sample; CDF distance is descriptive, not causal or a p-value",
            "partial calendar periods and known suppliers; no operational capacity defined",
            "legacy fit provenance is not retrospectively certified",
            "shared raw Parquets filtered by authorized IDs; physical row groups may be shared",
        ],
    })
    serialized = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        stream.write(serialized + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=["val"], default="val")
    args = parser.parse_args()
    result = run(split=args.split)
    print(json.dumps(result["validation"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
