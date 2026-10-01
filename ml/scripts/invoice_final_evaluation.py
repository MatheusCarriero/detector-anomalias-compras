"""Invoice synthetic evaluation and metadata-only real authorization gate.

Only trusted, test-created joblib files may be supplied. A synthetic marker is
not proof of provenance or a security sandbox. No data/model defaults or fit.
The real gate records permission only: it never reads TEST or executes scoring.
"""

import hashlib
import json
import math
import platform
import warnings
from datetime import datetime, timezone
from importlib.metadata import version
from io import BytesIO
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.exceptions import InconsistentVersionWarning
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
INPUT_NAMES = (
    "holdout.parquet", "development_ids.parquet", "splits.parquet",
    "labels.parquet", "amounts.parquet", "model.joblib", "model_metadata.json",
)
PRE_ACCESS_NAMES = ("model.joblib", "model_metadata.json", "development_ids.parquet")
SOURCE_NAMES = (
    "ml/scripts/invoice_final_evaluation.py", "ml/scripts/avaliar_invoice.py",
    "ml/scripts/comparar_triagem_invoice.py", "ml/scripts/diagnosticar_triagem_invoice.py",
    "ml/scripts/treinar_modelo.py", "docs/invoice_academic_evaluation_protocol.md",
)
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


def _fixture_path(root, name):
    path = _external(root / name)
    if path.parent != root:
        raise ValueError("Arquivo da fixture escapou do diretorio autorizado")
    return path


def _versions():
    return {"python": platform.python_version(), **{
        name: version(name) for name in ("numpy", "pandas", "scikit-learn", "joblib", "pyarrow")
    }}


def configuration_contract(offset):
    """Pin ranking, never reinterpret the fixture's offset as the legacy model."""
    if isinstance(offset, bool) or not isinstance(offset, (int, float)) or not math.isfinite(offset):
        raise ValueError("Offset deve ser numerico e finito")
    return {
        "schema": "invoice-synthetic-freeze/1.0", "mode": "synthetic_only",
        "protocol_version": "invoice-academic-evaluation-1.0",
        "split": "synthetic_holdout", "features": list(ORDERED_FEATURES),
        "parameters": PARAMETERS.copy(), "legacy_offset": float(offset),
        "budget_percentages": [1, 5, 10], "decision_rule": "selection_at_k",
        "test_authorized": False,
    }


def _validate_configuration(configuration):
    if not isinstance(configuration, dict):
        raise TypeError("Configuracao deve ser objeto JSON")
    expected = configuration_contract(configuration.get("legacy_offset"))
    if _canonical(configuration) != _canonical(expected):
        raise ValueError("Configuracao congelada incompativel com contrato sintetico Invoice")


def freeze_configuration(fixture_root, run_dir, configuration):
    """Prepare immutable-by-policy evidence BEFORE any synthetic holdout read."""
    _validate_configuration(configuration)
    root, run_dir = _external(fixture_root), _external(run_dir)
    if not root.is_dir():
        raise ValueError("Diretorio de fixtures inexistente")
    if run_dir.exists():
        raise FileExistsError("Diretorio de execucao ja existe; nao substituir")
    freeze = {
        "schema": "invoice-synthetic-preregistration/1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "fixture_root": str(root), "run_dir": str(run_dir), "configuration": configuration,
        "versions": _versions(),
        "source_sha256": {name: sha256(PROJECT_ROOT / name) for name in SOURCE_NAMES},
        "pre_access_sha256": {name: sha256(_fixture_path(root, name)) for name in PRE_ACCESS_NAMES},
        "input_names": list(INPUT_NAMES), "scientific_evidence": False,
    }
    run_dir.mkdir(parents=True, exist_ok=False)
    _write_json(run_dir / "freeze.json", freeze)
    return run_dir / "freeze.json"


def load_frozen_configuration(path, expected_sha256):
    """The expected digest is supplied out-of-band, not trusted from the JSON."""
    expected = _digest(expected_sha256)
    path = _external(path)
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != expected:
        raise ValueError("Hash do congelamento divergente")
    freeze = _json(content)
    keys = {"schema", "created_at", "fixture_root", "run_dir", "configuration", "versions",
            "source_sha256", "pre_access_sha256", "input_names", "scientific_evidence"}
    if (not isinstance(freeze, dict) or set(freeze) != keys
            or freeze["schema"] != "invoice-synthetic-preregistration/1.0"
            or freeze["scientific_evidence"] is not False
            or freeze["input_names"] != list(INPUT_NAMES)):
        raise ValueError("Schema do congelamento incompativel")
    _validate_configuration(freeze["configuration"])
    _external(freeze["fixture_root"])
    if path != _external(freeze["run_dir"]) / "freeze.json":
        raise ValueError("Caminho da execucao diverge do destino congelado")
    for key, names in (("source_sha256", SOURCE_NAMES), ("pre_access_sha256", PRE_ACCESS_NAMES)):
        if not isinstance(freeze[key], dict) or set(freeze[key]) != set(names):
            raise ValueError("Conjunto de hashes congelados incompativel")
        for digest in freeze[key].values():
            _digest(digest)
    return freeze


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
    _schema(frame, FRAME_COLUMNS, "holdout sintetico")
    if not frame["split"].eq(configuration["split"]).all():
        raise ValueError("Split indevido; somente synthetic_holdout permitido")
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
        raise TypeError("Modelo deve ser IsolationForest sintetico confiavel")
    check_is_fitted(model)
    if (getattr(model, "n_features_in_", None) != 19
            or list(getattr(model, "feature_names_in_", [])) != list(ORDERED_FEATURES)
            or len(model.estimators_) != 200):
        raise ValueError("Features/ordem/arvores do modelo divergentes")
    if _canonical(model.get_params()) != _canonical(configuration["parameters"]):
        raise ValueError("Parametros do IsolationForest divergentes")
    if not np.isfinite(model.offset_) or float(model.offset_) != configuration["legacy_offset"]:
        raise ValueError("Offset do modelo divergente do congelamento")


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


def _load_inputs(root, freeze):
    # Decode exactly the hashed bytes. Never deserialize a caller-supplied real model.
    contents = {name: _fixture_path(root, name).read_bytes() for name in INPUT_NAMES}
    hashes = {name: hashlib.sha256(content).hexdigest() for name, content in contents.items()}
    for name, expected in freeze["pre_access_sha256"].items():
        if hashes[name] != _digest(expected):
            raise ValueError("Input alterado depois do congelamento")
    tables = {name: pd.read_parquet(BytesIO(contents[name])) for name in INPUT_NAMES if name.endswith(".parquet")}
    config = freeze["configuration"]
    frame, dev = tables["holdout.parquet"], tables["development_ids.parquet"]
    _frame(frame, config)
    _schema(dev, ["invoice_id", "split"], "desenvolvimento")
    if set(dev["split"]) != {"train", "val"}:
        raise ValueError("Desenvolvimento requer train e val sinteticos")
    official = tables["splits.parquet"]
    _schema(official, ["invoice_id", "split"], "splits")
    combined = pd.concat([dev, frame[["invoice_id", "split"]]], ignore_index=True)
    validate_ids(combined, "separacao train/val/holdout")
    if not combined.set_index("invoice_id").sort_index().equals(official.set_index("invoice_id").sort_index()):
        raise ValueError("IDs/splits nao reconciliam exatamente com fonte")
    labels, amounts = tables["labels.parquet"], tables["amounts.parquet"]
    _schema(labels, ["invoice_id", "is_fraud", "fraud_type"], "labels")
    validate_target(labels)
    _schema(amounts, ["invoice_id", "invoice_amount", "currency"], "valores")
    for source in (labels, amounts):
        if set(source["invoice_id"]) != set(frame["invoice_id"]):
            raise ValueError("Cobertura da fonte diverge do holdout")
    frame = frame.sort_values("invoice_id").reset_index(drop=True)
    aligned_labels = labels.set_index("invoice_id").loc[frame["invoice_id"]].reset_index()
    if not frame[["invoice_id", "is_fraud", "fraud_type"]].equals(aligned_labels):
        raise ValueError("Labels/fraud_type divergentes por ID")
    aligned_amounts = amounts.set_index("invoice_id").loc[frame["invoice_id"]]
    amount_values = aligned_amounts["invoice_amount"]
    if (not pd.api.types.is_numeric_dtype(amount_values.dtype)
            or not np.array_equal(amount_values.to_numpy(), frame["invoice_amount"].to_numpy())):
        raise ValueError("Valores da fonte divergentes por ID")
    currencies = aligned_amounts["currency"]
    if (not currencies.map(lambda x: isinstance(x, str) and bool(x) and x == x.strip()).all()
            or currencies.nunique() != 1):
        raise ValueError("Exigida uma unica moeda nao nula")
    metadata = _json(contents["model_metadata.json"])
    expected_metadata = {"algorithm": "IsolationForest", "feature_count": 19,
                         "features": list(ORDERED_FEATURES), "parameters": config["parameters"],
                         "offset": config["legacy_offset"]}
    if _canonical(metadata) != _canonical(expected_metadata):
        raise ValueError("Metadata do modelo diverge da configuracao")
    with warnings.catch_warnings():
        warnings.simplefilter("error", InconsistentVersionWarning)
        model = joblib.load(BytesIO(contents["model.joblib"]))
    _model(model, config)
    return model, frame, hashes, str(currencies.iloc[0])


def _check_sources(freeze):
    if freeze["versions"] != _versions():
        raise ValueError("Ambiente diverge do congelamento")
    for name, expected in freeze["source_sha256"].items():
        if sha256(PROJECT_ROOT / name) != _digest(expected):
            raise ValueError("Codigo/protocolo diverge do congelamento")


def _publish_results(run_dir, record):
    destination, pending = run_dir / "results", run_dir / "results.pending"
    if destination.exists():
        raise FileExistsError("Resultado ja publicado")
    pending.mkdir(exist_ok=False)
    _write_json(pending / "evidence.json", record)
    _write_json(pending / "manifest.json", {
        "schema": "invoice-synthetic-manifest/1.0", "freeze_sha256": record["freeze_sha256"],
        "files": {"evidence.json": sha256(pending / "evidence.json")},
    })
    verify_bundle(pending, expected_manifest_sha256=sha256(pending / "manifest.json"),
                  expected_freeze_sha256=record["freeze_sha256"])
    pending.rename(destination)
    return destination


def run_synthetic_evaluation(freeze_path, *, expected_freeze_sha256):
    """One claim per freeze; failures consume the attempt, never delete evidence."""
    freeze_path = _external(freeze_path)
    freeze = load_frozen_configuration(freeze_path, expected_freeze_sha256)
    run_dir, root = freeze_path.parent, _external(freeze["fixture_root"])
    for name in ("execution_started.json", "failure.json", "results.pending", "results"):
        if (run_dir / name).exists():
            raise FileExistsError("Execucao ja iniciada; reexecucao automatica proibida")
    _check_sources(freeze)
    digest = _digest(expected_freeze_sha256)
    _write_json(run_dir / "execution_started.json", {
        "freeze_sha256": digest, "started_at": datetime.now(timezone.utc).isoformat(),
        "synthetic": True, "test_used": False, "automatic_retry": False,
    })
    try:
        model, frame, hashes, currency = _load_inputs(root, freeze)
        metrics = evaluate_frame(model, frame, freeze["configuration"])
        for name, expected in hashes.items():
            if sha256(_fixture_path(root, name)) != expected:
                raise ValueError("Input alterado durante avaliacao; nao publicar")
        _check_sources(freeze)
        if sha256(freeze_path) != digest:
            raise ValueError("Congelamento alterado durante avaliacao")
        record = {
            "schema": "invoice-synthetic-evidence/1.0", "synthetic": True,
            "scientific_evidence": False, "test_used": False, "model_fits_in_executor": 0,
            "freeze_sha256": digest, "configuration": freeze["configuration"],
            "metrics": metrics, "input_hashes_sha256": hashes,
            "ids_sha256": hashlib.sha256(_canonical(frame["invoice_id"].tolist())).hexdigest(),
            "currency": currency, "versions": freeze["versions"],
            "source_sha256": freeze["source_sha256"],
            "confusion_semantics": "rows reference [0,1]; columns [not selected,selected] at global K",
            "scope": "Synthetic software verification only; not academic evidence or fraud classification",
        }
        return _publish_results(run_dir, record)
    except Exception as error:
        # Log the phase, not potentially invalid Unicode or sensitive input values.
        _write_json(run_dir / "failure.json", {
            "freeze_sha256": digest, "exception_type": type(error).__name__,
            "phase": "after_synthetic_access_claim", "automatic_retry": False,
        })
        raise


def verify_bundle(results_dir, *, expected_manifest_sha256, expected_freeze_sha256):
    """Verify a synthetic bundle against externally supplied manifest/freeze hashes."""
    root = _external(results_dir)
    expected_manifest, expected_freeze = _digest(expected_manifest_sha256), _digest(expected_freeze_sha256)
    manifest_bytes = _fixture_path(root, "manifest.json").read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest() != expected_manifest:
        raise ValueError("Hash do manifesto divergente")
    manifest = _json(manifest_bytes)
    if (not isinstance(manifest, dict) or set(manifest) != {"schema", "files", "freeze_sha256"}
            or manifest["schema"] != "invoice-synthetic-manifest/1.0"
            or not isinstance(manifest["files"], dict) or set(manifest["files"]) != {"evidence.json"}
            or _digest(manifest["freeze_sha256"]) != expected_freeze):
        raise ValueError("Manifesto incompativel")
    if {p.name for p in root.iterdir()} != {"manifest.json", "evidence.json"}:
        raise ValueError("Bundle incompleto ou com arquivos inesperados")
    content = _fixture_path(root, "evidence.json").read_bytes()
    if hashlib.sha256(content).hexdigest() != _digest(manifest["files"]["evidence.json"]):
        raise ValueError("Hash da evidencia divergente")
    record = _json(content)
    if (not isinstance(record, dict) or record.get("schema") != "invoice-synthetic-evidence/1.0"
            or record.get("synthetic") is not True or record.get("scientific_evidence") is not False
            or record.get("test_used") is not False or record.get("model_fits_in_executor") != 0
            or _digest(record.get("freeze_sha256")) != expected_freeze):
        raise ValueError("Evidencia deve ser exclusivamente sintetica")
    _validate_configuration(record.get("configuration"))
    return record


def real_configuration_contract():
    """Admissible legacy contract, NOT a freeze or permission to open TEST."""
    return {
        "schema": "invoice-real-configuration/1.0", "mode": "real_pre_access",
        "protocol_version": "invoice-academic-evaluation-1.0", "split": "test",
        "features": list(ORDERED_FEATURES), "parameters": PARAMETERS.copy(),
        "legacy_offset": -0.5211491197816622,
        "model_sha256": "c9c0f51a9c962fac5ea6b34db5e0b74f09c120896bf9e7bf3a87418df2adba1b",
        "model_metadata_sha256": "ba07485e8dda458e45376b6edc4bd164926efe2c6ca8385cde32f7309db86595",
        "budget_percentages": [1, 5, 10], "decision_rule": "selection_at_k",
        "score_rule": "negative_score_samples_descending",
        "baseline": "invoice_amount_descending_signed", "tie_break": "invoice_id_ascending",
        "preprocessing": "existing_19_features_no_refit", "purpose": "academic_retrospective_triage",
        "provenance": {"source_reconciled": False,
                       "legacy_training_provenance_certified": False,
                       "raw_independence_certified": False},
    }


def _gate_text(value):
    if (not isinstance(value, str) or not value or value != value.strip()
            or any(ord(char) < 32 for char in value)):
        raise ValueError("Texto obrigatorio invalido no contrato de autorizacao")
    try:
        value.encode("utf-8")
    except UnicodeError as error:
        raise ValueError("Unicode invalido no contrato de autorizacao") from error
    return value


def _gate_time(value):
    try:
        result = datetime.fromisoformat(_gate_text(value))
    except ValueError as error:
        raise ValueError("Data invalida no contrato de autorizacao") from error
    if result.utcoffset() is None:
        raise ValueError("Data deve incluir fuso horario")
    return result


def _gate_absolute_path(value):
    path = Path(_gate_text(value))
    if not path.is_absolute() or str(path.resolve()) != value:
        raise ValueError("Caminho deve ser absoluto e canonico")
    return path


def _validate_real_freeze(freeze, path):
    keys = {"schema", "created_at", "run_dir", "project_root", "configuration", "versions",
            "source_sha256", "pre_access_sha256", "input_paths", "access_scope"}
    if (not isinstance(freeze, dict) or set(freeze) != keys
            or freeze["schema"] != "invoice-real-preregistration/1.1"
            or freeze["access_scope"] != "processed_test_and_physical_shared_raw_for_consistency_only"):
        raise ValueError("Schema do congelamento real incompativel")
    created_at = _gate_time(freeze["created_at"])
    run_dir = _external(_gate_absolute_path(freeze["run_dir"]))
    if path != run_dir / "freeze.json":
        raise ValueError("Destino diverge do congelamento real; copia nao autoriza tentativa")
    config = freeze["configuration"]
    if not isinstance(config, dict):
        raise TypeError("Configuracao real deve ser objeto JSON")
    normalized = config.copy()
    for key in ("model_sha256", "model_metadata_sha256"):
        normalized[key] = _digest(config.get(key))
    if _canonical(normalized) != _canonical(real_configuration_contract()):
        raise ValueError("Configuracao real incompativel com protocolo legado")
    # These are declared identities, not a claim that data bytes were verified here.
    names = ("data/processed/train_features.parquet", "data/processed/val_features.parquet",
             "ml/models/isolation_forest.joblib", "ml/models/model_metadata.json")
    hashes = freeze["pre_access_sha256"]
    if not isinstance(hashes, dict) or set(hashes) != set(names):
        raise ValueError("Hashes pre-acesso incompatíveis; nenhum hash TEST e permitido")
    hashes = {key: _digest(value) for key, value in hashes.items()}
    if (hashes[names[2]] != normalized["model_sha256"]
            or hashes[names[3]] != normalized["model_metadata_sha256"]):
        raise ValueError("Identidade do modelo/metadata diverge da configuracao")
    project = _gate_absolute_path(freeze["project_root"])
    # Do NOT resolve, stat, hash or read any declared data path, including TEST.
    after_access = ("data/processed/test_features.parquet", "data/raw/splits.parquet",
                    "data/raw/labels.parquet", "data/raw/invoices.parquet")
    expected_paths = {name: str(project / name) for name in (*names, *after_access)}
    if _canonical(freeze["input_paths"]) != _canonical(expected_paths):
        raise ValueError("Allowlist de caminhos de entrada incompativel")
    sources = freeze["source_sha256"]
    if (not isinstance(sources, dict)
            or set(sources) != {*SOURCE_NAMES, "ml/scripts/invoice_data_adapter.py",
                               "ml/scripts/invoice_real_inputs.py"}):
        raise ValueError("Conjunto de hashes de codigo/protocolo incompativel")
    for digest in sources.values():
        _digest(digest)
    _check_sources(freeze)  # Exact code allowlist only; never data/model files.
    return run_dir, created_at


def _authorization_time(freeze, authorization, now):
    created_at = _gate_time(freeze["created_at"])
    issued_at = _gate_time(authorization["issued_at"])
    expires_at = _gate_time(authorization["expires_at"])
    if not created_at <= issued_at <= now < expires_at:
        raise PermissionError("Autorizacao futura/expirada: congelamento <= emissao <= presente < expiracao")


def _load_real_authorization(freeze_path, authorization_path=None, *,
                             expected_freeze_sha256=None, expected_authorization_sha256=None):
    """Revalidate pinned permission documents, without claiming or reading inputs."""
    if (authorization_path is None or expected_freeze_sha256 is None
            or expected_authorization_sha256 is None):
        raise PermissionError("Autorizacao explicita e hashes externos obrigatorios; TEST bloqueado")
    freeze_hash, auth_hash = _digest(expected_freeze_sha256), _digest(expected_authorization_sha256)
    paths = (_external(freeze_path), _external(authorization_path))
    if [path.name for path in paths] != ["freeze.json", "authorization.json"]:
        raise ValueError("Somente documentos freeze.json e authorization.json sao aceitos")
    contents = [path.read_bytes() for path in paths]
    if [hashlib.sha256(content).hexdigest() for content in contents] != [freeze_hash, auth_hash]:
        raise ValueError("Hash externo do congelamento/autorizacao divergente")
    freeze, authorization = [_json(content) for content in contents]
    run_dir, _ = _validate_real_freeze(freeze, paths[0])
    keys = {"schema", "decision", "authorized_by", "authorization_reference", "issued_at",
            "freeze_sha256", "configuration_sha256", "run_dir", "split", "purpose",
            "provenance_acknowledged", "expires_at", "access_scope"}
    if not isinstance(authorization, dict) or set(authorization) != keys:
        raise ValueError("Schema da autorizacao incompativel")
    config = freeze["configuration"]
    config_hash = hashlib.sha256(_canonical(config)).hexdigest()
    if (authorization["schema"] != "invoice-real-authorization/1.1"
            or authorization["decision"] != "approve_once"
            or _digest(authorization["freeze_sha256"]) != freeze_hash
            or _digest(authorization["configuration_sha256"]) != config_hash
            or authorization["run_dir"] != str(run_dir)
            or authorization["split"] != "test"
            or authorization["purpose"] != config["purpose"]
            or authorization["access_scope"] != freeze["access_scope"]
            or _canonical(authorization["provenance_acknowledged"]) != _canonical(config["provenance"])):
        raise PermissionError("Autorizacao nao corresponde ao congelamento/escopo/limitacoes")
    _gate_text(authorization["authorized_by"])
    _gate_text(authorization["authorization_reference"])
    now = datetime.now(timezone.utc)
    _authorization_time(freeze, authorization, now)
    return freeze, authorization, paths, (freeze_hash, auth_hash), now


def _ensure_real_unused(run_dir, *, include_claim=True):
    names = ("execution_started.json", "failure.json", "inputs_validated.json", "results.pending", "results")
    for name in (("authorization_claim.json", *names) if include_claim else names):
        marker = run_dir / name
        if marker.exists() or marker.is_symlink():
            raise FileExistsError("Tentativa/resultado existente; repeticao ou sobrescrita proibida")


def _claim_record(freeze, authorization, freeze_hash, auth_hash, created_at):
    config = freeze["configuration"]
    return {
        "schema": "invoice-real-authorization-claim/1.0",
        "created_at": created_at, "run_dir": freeze["run_dir"],
        "freeze_sha256": freeze_hash, "authorization_sha256": auth_hash,
        "configuration_sha256": hashlib.sha256(_canonical(config)).hexdigest(), "configuration": config,
        "provenance": config["provenance"], "source_reconciled": False,
        "authorization": authorization, "test_used": False, "data_access_performed": False,
        "real_execution_available": False, "input_hashes_verified": False,
        "model_fits": 0, "score_calls": 0,
    }


def claim_real_evaluation_authorization(freeze_path, authorization_path=None, *,
                                      expected_freeze_sha256=None, expected_authorization_sha256=None):
    """Validate external permission; create a one-use metadata-only receipt.

    Pins verify bytes, not human identity. This API has no data loader or scoring
    callback. Consuming a receipt requires a separate explicit operation.
    """
    freeze, authorization, paths, hashes, _ = _load_real_authorization(
        freeze_path, authorization_path, expected_freeze_sha256=expected_freeze_sha256,
        expected_authorization_sha256=expected_authorization_sha256,
    )
    run_dir = paths[0].parent
    _ensure_real_unused(run_dir)
    _check_sources(freeze)
    if [sha256(path) for path in paths] != list(hashes):
        raise ValueError("Contrato alterado durante validacao; autorizacao nao consumida")
    now = datetime.now(timezone.utc)
    _authorization_time(freeze, authorization, now)
    claim = _claim_record(freeze, authorization, *hashes, now.isoformat())
    destination = run_dir / "authorization_claim.json"
    _write_json(destination, claim)  # Exclusive xb; partial failure consumes the attempt.
    return destination
