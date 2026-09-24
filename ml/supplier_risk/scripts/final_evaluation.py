"""Single-use academic Supplier evaluation; never tune using the holdout."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import warnings
from io import BytesIO
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from ml.supplier_risk.scripts import experiment_artifact as evidence

FEATURES_A = evidence.FEATURES_BY_SCENARIO["A"].copy()
FEATURES_C = evidence.FEATURES_BY_SCENARIO["C"].copy()
LR_PARAMETERS = {"C": 1.0, "solver": "lbfgs", "max_iter": 1000, "random_state": 42}
ML_PATH = Path("data/processed/supplier_risk/ml_ready")
SPLIT_PATH = Path("data/processed/supplier_risk/supplier_split_assignments.parquet")
REQUIRED_VERSIONS = {
    "pandas": "2.3.3", "numpy": "2.5.2", "pyarrow": "25.0.1", "scikit-learn": "1.9.0",
}
PROTOCOL_VERSION = "supplier-risk-1.0/final-academic-1.0"
CODE_BASE_COMMIT = "bb9965a735f2269aa1540b0c979b763fb2187fde"
TRACKED_PATHS = [
    ML_PATH / "X_train.parquet", ML_PATH / "y_train.parquet",
    ML_PATH / "preprocessing_metadata.json", SPLIT_PATH,
    Path("ml/supplier_risk/scripts/final_evaluation.py"),
    Path("ml/supplier_risk/scripts/experiment_artifact.py"),
    Path("ml/supplier_risk/notebooks/02_supplier_risk_baseline_models.ipynb"),
    Path("docs/supplier_risk_model.md"),
]


def configuration_contract():
    parameters = {name: step.get_params(deep=False) for name, step in make_pipeline().steps}
    parameters["imputer"]["missing_values"] = "NaN"
    return {
        "schema": "supplier-risk-freeze/1.0.0", "protocol_version": PROTOCOL_VERSION,
        "code_base_commit": CODE_BASE_COMMIT,
        "estimator": "LogisticRegression", "scenario": "C", "features": FEATURES_C,
        "parameters": parameters, "train_split": "train", "refit_train_validation": False,
        "decision_rule": "predict(); p(class 1) > 0.5, equality -> class 0",
        "threshold": 0.5, "calibration": None,
        "budget": {"classifier_fits": 1, "test_evaluations": 1, "tuning_trials": 0},
        "metrics": ["f1_macro", "balanced_accuracy", "precision_0", "recall_0", "f1_0",
                    "precision_1", "recall_1", "f1_1", "confusion_matrix", "roc_auc",
                    "average_precision", "accuracy", "support_0", "support_1"],
    }


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def write_json(path, value):
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
    with Path(path).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(serialized + "\n")


def check_hash(path, expected):
    if sha256(path) != expected.lower():
        raise ValueError(f"Input hash mismatch: {path}")


def check_runtime_sources(root):
    for source in (Path(__file__), Path(evidence.__file__)):
        target = Path(root) / "ml/supplier_risk/scripts" / source.name
        if sha256(source) != sha256(target):
            raise ValueError(f"Runtime code differs from recorded code: {source.name}")


def id_hash(ids):
    serialized = json.dumps(ids, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def read_verified_parquet(path, expected, **kwargs):
    content = Path(path).read_bytes()
    if hashlib.sha256(content).hexdigest() != expected.lower():
        raise ValueError(f"Input hash mismatch: {path}")
    frame = pd.read_parquet(BytesIO(content), **kwargs)
    check_hash(path, expected)
    return frame


def validate_xy(x, y, ids, expected_id_hash):
    if list(x.columns) != FEATURES_A or list(y.columns) != ["risk_level"]:
        raise ValueError("Unexpected X/y schema")
    if not len(x) or len(x) != len(y) or len(x) != len(ids):
        raise ValueError("X/y/IDs length mismatch or empty split")
    if not x.index.equals(pd.RangeIndex(len(x))) or not y.index.equals(x.index):
        raise ValueError("X/y index must be positional and aligned")
    if any(type(item) is not str or not item or item.strip() != item for item in ids):
        raise ValueError("Invalid supplier IDs")
    if len(set(ids)) != len(ids) or ids != sorted(ids):
        raise ValueError("Supplier IDs must be unique and sorted")
    if id_hash(ids) != expected_id_hash.lower():
        raise ValueError("Supplier IDs fingerprint mismatch")
    if any(dtype != np.dtype("float64") for dtype in x.dtypes):
        raise ValueError("X must contain only float64 numeric features")
    if not np.isfinite(x.to_numpy()).all():
        raise ValueError("Missing or infinite feature in ML-Ready")
    if y["risk_level"].dtype != np.dtype("int8") or set(y["risk_level"]) != {0, 1}:
        raise ValueError("Target must contain both binary int8 classes")


def _load_split(root, split, metadata):
    root = Path(root)
    data = []
    for prefix in ("X", "y"):
        relative = (ML_PATH / f"{prefix}_{split}.parquet").as_posix()
        data.append(read_verified_parquet(root / relative, metadata["hashes_saidas_sha256"][relative]))
    assignments = read_verified_parquet(
        root / SPLIT_PATH, metadata["hashes_entradas_sha256"][SPLIT_PATH.as_posix()],
        filters=[("split", "==", split)],
    )
    if set(assignments["split"]) != {split} or assignments["supplier_id"].isna().any():
        raise ValueError("Unexpected assignments")
    ids = sorted(assignments["supplier_id"].tolist())
    validate_xy(*data, ids, metadata["hash_ordenacao_ids_sha256"][split])
    if len(ids) != metadata["quantidade_registros_por_split"][split]:
        raise ValueError("Split count mismatch")
    return data[0].loc[:, FEATURES_C].copy(), data[1]["risk_level"].copy(), ids


def load_development_split(root, split):
    if split not in ("train", "validation"):
        raise ValueError("development reader only permits train/validation")
    metadata = json.loads((Path(root) / ML_PATH / "preprocessing_metadata.json").read_text(encoding="utf-8"))
    return _load_split(root, split, metadata)


def make_pipeline():
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
        ("model", LogisticRegression(**LR_PARAMETERS)),
    ])


def fit_candidate(x, y):
    if list(x.columns) != FEATURES_C or len(x) != len(y) or set(y) != {0, 1}:
        raise ValueError("Training schema or classes invalid")
    if x.isna().all().any() or np.isinf(x.to_numpy(dtype=float)).any():
        raise ValueError("Invalid training values")
    with warnings.catch_warnings():
        warnings.simplefilter("error", ConvergenceWarning)
        return make_pipeline().fit(x, y)


def classification_metrics(truth, prediction, probability):
    truth, prediction, probability = map(np.asarray, (truth, prediction, probability))
    if any(array.ndim != 1 for array in (truth, prediction, probability)):
        raise ValueError("Metrics require one-dimensional arrays")
    if not len(truth) or not (len(truth) == len(prediction) == len(probability)):
        raise ValueError("Metric input lengths differ")
    if set(truth) != {0, 1} or not set(prediction) <= {0, 1}:
        raise ValueError("Both true classes and binary predictions required")
    if not np.isfinite(probability).all() or ((probability < 0) | (probability > 1)).any():
        raise ValueError("Invalid probability")
    precision, recall, f1, support = precision_recall_fscore_support(
        truth, prediction, labels=[0, 1], zero_division=0,
    )
    result = {
        "f1_macro": float(f1_score(truth, prediction, labels=[0, 1], average="macro", zero_division=0)),
        "balanced_accuracy": float(balanced_accuracy_score(truth, prediction)),
        "accuracy": float(accuracy_score(truth, prediction)),
        "roc_auc": float(roc_auc_score(truth, probability)),
        "average_precision": float(average_precision_score(truth, probability)),
        "confusion_matrix": confusion_matrix(truth, prediction, labels=[0, 1]).tolist(),
    }
    for label in (0, 1):
        for name, values in (("precision", precision), ("recall", recall), ("f1", f1)):
            result[f"{name}_{label}"] = float(values[label])
        result[f"support_{label}"] = int(support[label])
    return result


def claim_test_access(freeze_path, expected_hash):
    freeze_path = Path(freeze_path)
    check_hash(freeze_path, expected_hash)
    write_json(freeze_path.parent / "test_access_started.json", {
        "freeze_sha256": expected_hash, "started_at": utc_now(),
        "policy": "No automatic retry, even after failure.",
    })


def publish_bundle(staging, destination):
    staging, destination = Path(staging), Path(destination)
    if destination.exists():
        raise FileExistsError(destination)
    manifest = json.loads((staging / "manifest.json").read_text(encoding="utf-8"))
    expected = manifest["files"]
    if set(expected) != {path.name for path in staging.iterdir() if path.name != "manifest.json"}:
        raise ValueError("Incomplete bundle")
    for name, digest in expected.items():
        if Path(name).name != name or name in (".", ".."):
            raise ValueError("Unsafe manifest path")
        check_hash(staging / name, digest)
    # Same-parent rename: readers see the complete result directory or nothing.
    os.rename(staging, destination)


def freeze_configuration(root, run_dir):
    """Persist the preregistration without opening TEST or fitting an estimator."""
    root, run_dir = Path(root), Path(run_dir)
    if run_dir.exists():
        raise FileExistsError(run_dir)
    versions = {name: version(name) for name in REQUIRED_VERSIONS}
    if platform.python_version() != "3.14.3" or versions != REQUIRED_VERSIONS:
        raise ValueError("Use the preregistered isolated Python/library versions")
    check_runtime_sources(root)
    x, y, ids = load_development_split(root, "train")
    majority = int(y.value_counts().sort_index().idxmax())
    metadata = json.loads((root / ML_PATH / "preprocessing_metadata.json").read_text(encoding="utf-8"))
    freeze = {
        **configuration_contract(), "created_at": utc_now(),
        "selection": "VALIDATION F1-macro, balanced accuracy, exact tie D/B/C/A then LR/RF",
        "selection_confusion_matrix": [[979, 131], [81, 2348]],
        "baseline_class": majority,
        "train_rows": len(x), "train_ids_sha256": id_hash(ids),
        "versions": {"python": platform.python_version(), **versions},
        "hashes": {path.as_posix(): sha256(root / path) for path in TRACKED_PATHS},
        "split_identification": {
            "path": SPLIT_PATH.as_posix(),
            "id_hashes": metadata["hash_ordenacao_ids_sha256"],
            "rows": metadata["quantidade_registros_por_split"],
            "policy": "Existing deterministic supplier_id assignments; no resplit",
        },
        "expected_test_hashes_from_producer": {
            name: metadata["hashes_saidas_sha256"][(ML_PATH / f"{name}.parquet").as_posix()]
            for name in ("X_test", "y_test")
        },
        "budget": {"classifier_fits": 1, "test_evaluations": 1, "tuning_trials": 0},
        "failure_policy": "Stop, preserve evidence, never select or retry from TEST results.",
        "scope": "Academic classification of dataset Risk_Level, not real failure probability",
    }
    run_dir.mkdir(parents=True, exist_ok=False)
    write_json(run_dir / "freeze.json", freeze)
    return run_dir / "freeze.json"


def fitted_state(candidate):
    imputer, scaler, model = (candidate.named_steps[key] for key in ("imputer", "scaler", "model"))
    return {
        "features": FEATURES_C, "imputer_statistics": imputer.statistics_.tolist(),
        "scaler_mean": scaler.mean_.tolist(), "scaler_var": scaler.var_.tolist(),
        "scaler_scale": scaler.scale_.tolist(), "scaler_rows_seen": int(scaler.n_samples_seen_),
        "classes": model.classes_.tolist(), "coefficients": model.coef_.tolist(),
        "intercept": model.intercept_.tolist(), "n_iter": model.n_iter_.tolist(),
    }


def run_final_evaluation(root, freeze_path, *, expected_freeze_sha256):
    """Execute only an already-frozen configuration; results are never used for selection."""
    execution_id = uuid4().hex
    try:
        return _run_final_evaluation(root, freeze_path, expected_freeze_sha256, execution_id)
    except Exception as error:  # noqa: BLE001 -- record any failure and re-raise, never recover or retry.
        run_dir = Path(freeze_path).parent
        marker = run_dir / "execution_started.json"
        if marker.exists():
            owner = json.loads(marker.read_text(encoding="utf-8"))
            if owner.get("execution_id") == execution_id:
                write_json(run_dir / "failure.json", {
                    "execution_id": execution_id, "failed_at": utc_now(),
                    "freeze_sha256": expected_freeze_sha256,
                    "phase": "after_test_access" if (run_dir / "test_access_started.json").exists() else "before_test_access",
                    "exception_type": type(error).__name__, "message": str(error),
                    "automatic_retry": False,
                })
        raise


def _run_final_evaluation(root, freeze_path, expected_freeze_sha256, execution_id):
    root, freeze_path = Path(root), Path(freeze_path)
    check_hash(freeze_path, expected_freeze_sha256)
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    digest = expected_freeze_sha256.lower()
    for name in ("execution_started.json", "test_access_started.json", "results.pending", "results"):
        if (freeze_path.parent / name).exists():
            raise FileExistsError("Final evaluation already started; automatic retry prohibited")
    for key, expected in configuration_contract().items():
        if freeze.get(key) != expected:
            raise ValueError(f"Frozen configuration differs: {key}")
    if set(freeze["hashes"]) != {path.as_posix() for path in TRACKED_PATHS}:
        raise ValueError("Frozen input/code hash set differs")
    if freeze["versions"] != {"python": platform.python_version(), **{k: version(k) for k in REQUIRED_VERSIONS}}:
        raise ValueError("Frozen environment differs")
    for relative, expected in freeze["hashes"].items():
        check_hash(root / relative, expected)
    check_runtime_sources(root)
    metadata = json.loads((root / ML_PATH / "preprocessing_metadata.json").read_text(encoding="utf-8"))
    for prefix in ("X", "y"):
        key = f"{prefix}_test"
        expected = metadata["hashes_saidas_sha256"][(ML_PATH / f"{key}.parquet").as_posix()]
        if freeze["expected_test_hashes_from_producer"][key].lower() != expected.lower():
            raise ValueError("Frozen TEST input hash differs from frozen producer metadata")
    if freeze["split_identification"]["id_hashes"] != metadata["hash_ordenacao_ids_sha256"]:
        raise ValueError("Frozen split fingerprints differ")
    # Exclusive claim BEFORE fitting also prevents concurrent/repeated fits.
    write_json(freeze_path.parent / "execution_started.json", {
        "freeze_sha256": digest, "started_at": utc_now(), "automatic_retry": False,
        "execution_id": execution_id,
    })
    x_train, y_train, train_ids = load_development_split(root, "train")
    if len(x_train) != freeze["train_rows"] or id_hash(train_ids) != freeze["train_ids_sha256"]:
        raise ValueError("Frozen TRAIN identity differs")
    if int(y_train.value_counts().sort_index().idxmax()) != freeze["baseline_class"]:
        raise ValueError("Baseline no longer matches freeze")
    candidate = fit_candidate(x_train, y_train)
    np.testing.assert_allclose(candidate.named_steps["imputer"].statistics_, x_train.median().to_numpy())
    np.testing.assert_allclose(candidate.named_steps["scaler"].mean_, x_train.mean().to_numpy())
    state = fitted_state(candidate)
    write_json(freeze_path.parent / "fitted_state_before_test.json", {
        "freeze_sha256": digest, "fit_completed_at": utc_now(), "state": state,
    })
    # One-shot marker is written BEFORE the first TEST hash/read, including failures.
    claim_test_access(freeze_path, digest)
    x_test, y_test, test_ids = _load_split(root, "test", metadata)
    if set(train_ids) & set(test_ids):
        raise ValueError("Train/test supplier overlap")
    probability = candidate.predict_proba(x_test)[:, list(candidate.classes_).index(1)]
    predicted = candidate.predict(x_test)
    if fitted_state(candidate) != state:
        raise ValueError("Fitted state changed during TEST prediction")
    np.testing.assert_array_equal(predicted, (probability > .5).astype(int))
    baseline_prediction = np.full(len(y_test), freeze["baseline_class"], dtype=int)
    baseline_probability = baseline_prediction.astype(float)
    metrics = {
        "LogisticRegression_C": classification_metrics(y_test, predicted, probability),
        "Baseline_majoritaria": classification_metrics(y_test, baseline_prediction, baseline_probability),
    }
    staging = freeze_path.parent / "results.pending"
    staging.mkdir(exist_ok=False)
    input_hashes = freeze["hashes"].copy()
    for prefix in ("X", "y"):
        relative = (ML_PATH / f"{prefix}_test.parquet").as_posix()
        input_hashes[relative] = metadata["hashes_saidas_sha256"][relative]
    for label, classes, probabilities in (
        ("LogisticRegression_C", predicted, probability),
        ("Baseline_majoritaria", baseline_prediction, baseline_probability),
    ):
        rows = [
            {"supplier_id": supplier_id, "split": "test", "y_true": int(actual),
             "y_pred": int(prediction), "probability_class_1": float(score)}
            for supplier_id, actual, prediction, score in zip(test_ids, y_test, classes, probabilities, strict=True)
        ]
        record_metadata = {
            "experiment_name": "supplier-final-academic-v1", "estimator": label,
            "scenario": "C", "features": FEATURES_C,
            "parameters": freeze["parameters"] if label == "LogisticRegression_C" else {
                "strategy": "most_frequent", "learned_class": freeze["baseline_class"],
            },
            "seeds": {"model": 42}, "versions": freeze["versions"],
            "input_hashes": input_hashes,
            "code_sha256": freeze["hashes"]["ml/supplier_risk/scripts/final_evaluation.py"],
            "expected_id_hashes": {"test": metadata["hash_ordenacao_ids_sha256"]["test"]},
        }
        record_path = staging / f"{label}.json"
        evidence.write_final_evaluation_record(record_path, rows, record_metadata, freeze_sha256=digest)
        evidence.verify_final_evaluation_record(record_path)
    write_json(staging / "metrics.json", {
        "freeze_sha256": digest, "completed_at": utc_now(), "test_rows": len(y_test),
        "metrics": metrics, "training_rows": len(y_train), "test_used_for_selection": False,
        "classifier_fits": 1, "test_evaluations": 1,
    })
    for relative, expected in input_hashes.items():
        check_hash(root / relative, expected)
    write_json(staging / "manifest.json", {
        "freeze_sha256": digest, "files": {p.name: sha256(p) for p in staging.iterdir()},
    })
    publish_bundle(staging, freeze_path.parent / "results")
    return metrics
