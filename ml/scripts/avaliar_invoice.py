"""Evaluate the existing Invoice model on validation only; never fit or tune."""

import argparse
import hashlib
import json
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
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    precision_recall_fscore_support,
    roc_auc_score,
)
from sklearn.utils.validation import check_is_fitted

from ml.scripts.treinar_modelo import FEATURES, validate_training_features

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_PARAMS = {
    "n_estimators": 200, "contamination": 0.22, "random_state": 42, "n_jobs": -1,
}
INPUTS = (
    "data/processed/train_features.parquet",
    "data/processed/val_features.parquet",
    "data/raw/splits.parquet",
    "data/raw/labels.parquet",
    "ml/models/isolation_forest.joblib",
    "ml/models/model_metadata.json",
)


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_ids(frame, label):
    if "invoice_id" not in frame:
        raise ValueError(f"invoice_id ausente: {label}")
    ids = frame["invoice_id"]
    if frame.empty or ids.isna().any() or ids.duplicated().any():
        raise ValueError(f"IDs vazios, nulos ou duplicados: {label}")
    if not ids.map(lambda value: isinstance(value, str) and bool(value)
                   and value == value.strip()).all():
        raise ValueError(f"IDs inválidos: {label}")


def validate_target(frame):
    y = frame["is_fraud"]
    if not pd.api.types.is_integer_dtype(y.dtype) or not y.isin([0, 1]).all():
        raise ValueError("label is_fraud deve ser inteira binária e não nula")
    if not frame["fraud_type"].map(lambda v: pd.isna(v) or isinstance(v, str)).all():
        raise ValueError("fraud_type deve ser texto ou nulo")
    if frame["fraud_type"].eq("__missing__").any():
        raise ValueError("fraud_type usa nome reservado __missing__")


def load_validation(root, split="val"):
    if split != "val":
        raise ValueError("Este avaliador permite somente split=val, nunca TEST.")
    root = Path(root)
    frame = pd.read_parquet(root / "data/processed/val_features.parquet")
    if list(frame.columns) != ["invoice_id", "split", "is_fraud", "fraud_type", *FEATURES]:
        raise ValueError("Schema de validação diferente do contrato Invoice")
    validate_ids(frame, "val")
    if not frame["split"].eq("val").all():
        raise ValueError("Arquivo val contém split indevido")
    validate_target(frame)
    validate_training_features(frame[FEATURES])
    if (frame["supplier_frequency"] < 0).any():
        raise ValueError("supplier_frequency negativa")
    train = pd.read_parquet(
        root / "data/processed/train_features.parquet", columns=["invoice_id", "split"],
    )
    validate_ids(train, "train")
    if not train["split"].eq("train").all():
        raise ValueError("Arquivo train contém split indevido")
    if set(frame["invoice_id"]) & set(train["invoice_id"]):
        raise ValueError("Overlap de IDs entre train e val")
    official = pd.read_parquet(
        root / "data/raw/splits.parquet", columns=["invoice_id", "split"],
        filters=[("split", "in", ["train", "val"])],
    )
    validate_ids(official, "split oficial")
    for name, part in (("train", train), ("val", frame)):
        expected = set(official.loc[official["split"].eq(name), "invoice_id"])
        if expected != set(part["invoice_id"]):
            raise ValueError(f"IDs não reconciliam com split oficial: {name}")
    labels = pd.read_parquet(
        root / "data/raw/labels.parquet",
        columns=["invoice_id", "is_fraud", "fraud_type"],
        filters=[("invoice_id", "in", frame["invoice_id"].tolist())],
    )
    validate_ids(labels, "labels")
    validate_target(labels)
    if set(labels["invoice_id"]) != set(frame["invoice_id"]):
        raise ValueError("Cobertura de labels diferente de val")
    actual = frame.set_index("invoice_id")[["is_fraud", "fraud_type"]].sort_index()
    expected = labels.set_index("invoice_id").sort_index()
    if not actual.equals(expected):
        raise ValueError("Labels ou fraud_type divergentes da fonte por invoice_id")
    return frame.sort_values("invoice_id").reset_index(drop=True)


def summarize(y, prediction, score):
    y, prediction, score = map(np.asarray, (y, prediction, score))
    if any(v.ndim != 1 for v in (y, prediction, score)) or not len(y):
        raise ValueError("Métricas requerem vetores não vazios")
    if len(y) != len(prediction) or len(y) != len(score):
        raise ValueError("Comprimentos divergentes")
    if not set(y) <= {0, 1} or not set(prediction) <= {0, 1}:
        raise ValueError("Labels e previsões devem ser binárias")
    if not np.isfinite(score).all():
        raise ValueError("Scores não finitos")
    precision, recall, f1, support = precision_recall_fscore_support(
        y, prediction, labels=[0, 1], zero_division=0,
    )
    both = set(y) == {0, 1}
    result = {
        "count": len(y), "confusion_matrix": confusion_matrix(y, prediction, labels=[0, 1]).tolist(),
        "f1_macro": float(np.mean(f1)), "accuracy": float(accuracy_score(y, prediction)),
        "balanced_accuracy": float(np.mean(recall)) if both else None,
        "roc_auc": float(roc_auc_score(y, score)) if both else None,
        "average_precision": float(average_precision_score(y, score)) if both else None,
        "alert_rate": float(np.mean(prediction)),
    }
    for label in (0, 1):
        result.update({
            f"precision_{label}": float(precision[label]),
            f"recall_{label}": float(recall[label]),
            f"f1_{label}": float(f1[label]), f"support_{label}": int(support[label]),
        })
    return result


def group_summary(y, predicted):
    y, predicted = np.asarray(y), np.asarray(predicted)
    positives = int(np.sum(y == 1))
    negatives = int(np.sum(y == 0))
    tp = int(np.sum((y == 1) & (predicted == 1)))
    fp = int(np.sum((y == 0) & (predicted == 1)))
    return {
        "count": len(y), "frauds": positives, "normal": negatives,
        "alerts": int(np.sum(predicted)), "true_positive": tp,
        "false_negative": positives - tp, "false_positive": fp,
        "recall_fraud": tp / positives if positives else None,
        "false_positive_rate": fp / negatives if negatives else None,
    }


def evaluate_frame(model, frame):
    validate_target(frame)
    x = frame[FEATURES]
    validate_training_features(x)
    score = -np.asarray(model.score_samples(x))
    decision = np.asarray(model.decision_function(x))
    raw_prediction = np.asarray(model.predict(x))
    if (score.shape != (len(frame),) or decision.shape != score.shape
            or raw_prediction.shape != score.shape
            or not np.isfinite(score).all() or not np.isfinite(decision).all()
            or not set(raw_prediction) <= {-1, 1}):
        raise ValueError("Saída do modelo inválida")
    if not np.isfinite(model.offset_) or not np.allclose(decision, -score - model.offset_):
        raise ValueError("Score e decision_function inconsistentes")
    prediction = (raw_prediction == -1).astype(int)
    if not np.array_equal(prediction, (decision < 0).astype(int)):
        raise ValueError("predict diverge da regra original")
    y = frame["is_fraud"].to_numpy()
    by_type = {}
    types = frame["fraud_type"].fillna("__missing__")
    for name in sorted(types.unique()):
        mask = types.eq(name).to_numpy()
        by_type[name] = group_summary(y[mask], prediction[mask])
    seen = frame["supplier_frequency"].gt(0).to_numpy()
    return {
        "model": summarize(y, prediction, score),
        "baseline_no_alert": summarize(y, np.zeros(len(y), dtype=int), np.zeros(len(y))),
        "by_fraud_type": by_type,
        "by_supplier_seen": {
            "seen": group_summary(y[seen], prediction[seen]),
            "unseen": group_summary(y[~seen], prediction[~seen]),
        },
    }


def run(root=PROJECT_ROOT, output=None, split="val"):
    if split != "val":
        raise ValueError("Somente split=val autorizado")
    root = Path(root)
    output = Path(output) if output is not None else root / "ml/experiments/invoice_validation_v1.json"
    if output.exists():
        raise FileExistsError(f"Saída já existe; não sobrescrever: {output}")
    if output.suffix != ".json":
        raise ValueError("Saída deve ser JSON")
    hashes = {name: sha256(root / name) for name in INPUTS}
    frame = load_validation(root, split)
    metadata = json.loads((root / "ml/models/model_metadata.json").read_text(encoding="utf-8"))
    if metadata.get("features") != FEATURES or metadata.get("feature_count") != 19:
        raise ValueError("Metadata do modelo com features divergentes")
    for key in ("n_estimators", "contamination", "random_state"):
        if metadata.get(key) != EXPECTED_PARAMS[key]:
            raise ValueError(f"Metadata do modelo divergente: {key}")
    if metadata.get("algorithm") != "IsolationForest":
        raise ValueError("Metadata do modelo com algoritmo divergente")
    with warnings.catch_warnings():
        warnings.simplefilter("error", InconsistentVersionWarning)
        model = joblib.load(root / "ml/models/isolation_forest.joblib")
    if not isinstance(model, IsolationForest):
        raise TypeError("Tipo do modelo inesperado")
    check_is_fitted(model)
    if list(model.feature_names_in_) != FEATURES or model.n_features_in_ != 19:
        raise ValueError("Features do modelo divergentes")
    for key, expected in EXPECTED_PARAMS.items():
        if model.get_params()[key] != expected:
            raise ValueError(f"Configuração do modelo divergente: {key}")
    if len(model.estimators_) != 200:
        raise ValueError("Número de árvores ajustadas divergente")
    result = evaluate_frame(model, frame)
    for name, expected in hashes.items():
        if sha256(root / name) != expected:
            raise ValueError(f"Input alterado durante avaliação: {name}")
    protocol = PROJECT_ROOT / "docs/invoice_validation.md"
    result.update({
        "protocol_version": "invoice-validation-1.0", "split": "val", "rows": len(frame),
        "created_at": datetime.now(timezone.utc).isoformat(), "real_model_fits": 0,
        "test_used": False, "threshold_selected_on_validation": False,
        "features": FEATURES, "parameters": model.get_params(),
        "offset": float(model.offset_), "anomaly_score_threshold": float(-model.offset_),
        "decision_rule": "decision_function < 0; equality is normal",
        "score_definition": "-score_samples; higher means more anomalous; not a probability",
        "input_hashes_sha256": hashes, "code_sha256": sha256(__file__),
        "feature_contract_code_sha256": sha256(PROJECT_ROOT / "ml/scripts/treinar_modelo.py"),
        "protocol_sha256_at_execution": sha256(protocol),
        "validation_ids_sha256": hashlib.sha256(json.dumps(
            frame["invoice_id"].tolist(), separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")).hexdigest(),
        "versions": {"python": platform.python_version(), **{
            name: version(name) for name in ("numpy", "pandas", "scikit-learn", "joblib", "pyarrow")
        }},
        "training_provenance": "Legacy metadata has no training input hash; original fit provenance not retrospectively certified",
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
    print(json.dumps({"rows": result["rows"], "model": result["model"],
                      "baseline_no_alert": result["baseline_no_alert"]}, indent=2))


if __name__ == "__main__":
    main()
