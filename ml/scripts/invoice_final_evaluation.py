"""Academic Invoice evaluation with explicit data and model; never fit or implicit I/O."""

import hashlib
import json
import math
import platform
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.utils.validation import check_is_fitted

from ml.scripts import comparar_triagem_invoice as comparison
from ml.scripts import diagnosticar_triagem_invoice as triage
from ml.scripts.avaliar_invoice import (
    validate_ids,
    validate_target,
    validate_training_features,
)
from ml.scripts.treinar_modelo import FEATURES

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ORDERED_FEATURES = tuple(FEATURES)
PARAMETERS = {
    "n_estimators": 200, "contamination": 0.22, "random_state": 42, "n_jobs": -1,
    "max_samples": "auto", "max_features": 1.0, "bootstrap": False,
    "warm_start": False, "verbose": 0,
}
FRAME_COLUMNS = ["invoice_id", "split", "is_fraud", "fraud_type", *ORDERED_FEATURES]


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _digest(value):
    if (not isinstance(value, str) or len(value) != 64
            or any(c not in "0123456789abcdefABCDEF" for c in value)):
        raise ValueError("SHA-256 invalido")
    return value.lower()


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("JSON contem chave duplicada")
        result[key] = value
    return result


def _json(content):
    try:
        value = json.loads(content, object_pairs_hook=_unique_pairs)
        _canonical(value)  # Reject NaN/Infinity, including nested values.
        return value
    except (UnicodeError, TypeError, ValueError) as error:
        raise ValueError("JSON invalido, duplicado ou nao finito") from error


def _write_json(path, value):
    content = _canonical(value) + b"\n"
    with Path(path).open("xb") as stream:
        stream.write(content)


def _external(path):
    resolved = Path(path).resolve()
    if resolved == PROJECT_ROOT or PROJECT_ROOT in resolved.parents:
        raise ValueError("Fixtures e saidas sinteticas devem ficar fora do checkout")
    return resolved


def _versions():
    """Informative runtime versions, without imposing an execution environment gate."""
    result = {"python": platform.python_version()}
    for name in ("pandas", "numpy", "scikit-learn", "joblib", "pyarrow"):
        try:
            result[name] = version(name)
        except PackageNotFoundError:
            result[name] = "unavailable"
    return result


def configuration_contract(offset, split="test"):
    """Scientific settings, with an explicit partition and existing model offset."""
    if isinstance(offset, bool) or not isinstance(offset, (int, float)) or not math.isfinite(offset):
        raise ValueError("Offset deve ser numerico e finito")
    if not isinstance(split, str) or split not in {"train", "val", "test", "synthetic_holdout"}:
        raise ValueError("Particao Invoice desconhecida")
    return {
        "split": split, "features": list(ORDERED_FEATURES),
        "parameters": PARAMETERS.copy(), "legacy_offset": float(offset),
        "budget_percentages": [1, 5, 10], "decision_rule": "selection_at_k",
    }


def _validate_configuration(configuration):
    if not isinstance(configuration, dict):
        raise TypeError("Configuracao deve ser objeto JSON")
    expected = configuration_contract(configuration.get("legacy_offset"), configuration.get("split"))
    if _canonical(configuration) != _canonical(expected):
        raise ValueError("Configuracao cientifica Invoice incompativel")


def _schema(frame, columns, label):
    if not isinstance(frame, pd.DataFrame) or list(frame.columns) != list(columns):
        raise ValueError(f"Schema/ordem de colunas invalido: {label}")
    validate_ids(frame, label)
    for value in frame["invoice_id"]:
        try:
            value.encode("utf-8")
        except UnicodeError as error:
            raise ValueError("invoice_id contem Unicode invalido") from error


def _frame(frame, configuration):
    _schema(frame, FRAME_COLUMNS, "particao de avaliacao")
    if not frame["split"].eq(configuration["split"]).all():
        raise ValueError("Particao do frame diverge da configuracao")
    validate_target(frame)
    for value in frame["fraud_type"].dropna():
        try:
            value.encode("utf-8")
        except UnicodeError as error:
            raise ValueError("fraud_type contem Unicode invalido") from error
    validate_training_features(frame[list(ORDERED_FEATURES)])
    if frame["supplier_frequency"].lt(0).any():
        raise ValueError("supplier_frequency negativa")


def _model(model, configuration):
    if type(model) is not IsolationForest:
        raise TypeError("Modelo deve ser IsolationForest confiavel")
    check_is_fitted(model)
    if (getattr(model, "n_features_in_", None) != 19
            or list(getattr(model, "feature_names_in_", [])) != list(ORDERED_FEATURES)
            or len(model.estimators_) != 200):
        raise ValueError("Features/ordem/arvores do modelo divergentes")
    if _canonical(model.get_params()) != _canonical(configuration["parameters"]):
        raise ValueError("Parametros do IsolationForest divergentes")
    if not np.isfinite(model.offset_) or float(model.offset_) != configuration["legacy_offset"]:
        raise ValueError("Offset do modelo divergente da configuracao")


def _counts(y, selected):
    positive, selected = np.asarray(y) == 1, np.asarray(selected, dtype=bool)
    tp, fp = int(np.sum(positive & selected)), int(np.sum(~positive & selected))
    fn, tn = int(np.sum(positive & ~selected)), int(np.sum(~positive & ~selected))
    return {
        "count": len(y), "known_positives": tp + fn, "selected": tp + fp,
        "true_positive": tp, "false_positive": fp, "false_negative": fn, "true_negative": tn,
        "confusion_matrix": [[tn, fp], [fn, tp]],
        "recall_reference": tp / (tp + fn) if tp + fn else None,
        "false_positive_rate": fp / (fp + tn) if fp + tn else None,
        "precision_selected": tp / (tp + fp) if tp + fp else None,
    }


def evaluate_frame(model, frame, configuration):
    """Pure evaluation: one score call, same global selection for all type groups."""
    _validate_configuration(configuration)
    _frame(frame, configuration)
    _model(model, configuration)
    return _evaluate_validated_frame(model, frame, configuration)


def _evaluate_validated_frame(model, frame, configuration):
    """Shared calculation without I/O or model fitting."""
    frame = frame.sort_values("invoice_id").reset_index(drop=True)
    state = joblib.hash(model)
    scores = -np.asarray(model.score_samples(frame[list(ORDERED_FEATURES)]), dtype=float)
    if scores.shape != (len(frame),) or not np.isfinite(scores).all():
        raise ValueError("Scores devem ser finitos e alinhados")
    _model(model, configuration)
    if joblib.hash(model) != state:
        raise ValueError("Estado ajustado do modelo alterado durante scoring")
    result = comparison.compare_rankings(frame, scores)
    diagnostics = {}
    types = frame["fraud_type"].fillna("__missing__")
    for name, values in (("isolation_forest", scores), ("invoice_value", frame["invoice_amount"])):
        ranked = triage._rank(frame, values)
        diagnostics[name] = []
        for budget in result[name]["budgets"]:
            selected = frame["invoice_id"].isin(ranked.iloc[:budget["k"]]["invoice_id"])
            groups = {key: _counts(frame.loc[types.eq(key), "is_fraud"], selected[types.eq(key)])
                      for key in sorted(types.unique())}
            diagnostics[name].append({
                "percent": budget["percent"], **_counts(frame["is_fraud"], selected),
                "by_fraud_type": groups,
            })
    result["selection_diagnostics"] = diagnostics
    return result
