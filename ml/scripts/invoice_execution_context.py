"""Versioned metadata-only binding. No emitter, dataset access or permission issuer.

Portable identity is independent of a machine; execution authority is not.
An effective bound mapping is internal, never persisted as the portable freeze.
"""

import hashlib
from pathlib import Path
from uuid import UUID

from ml.scripts import invoice_final_evaluation as executor

PRE_ACCESS = (
    "data/processed/train_features.parquet", "data/processed/val_features.parquet",
    "ml/models/isolation_forest.joblib", "ml/models/model_metadata.json",
)
DEFERRED = ("data/processed/test_features.parquet", "data/raw/splits.parquet",
            "data/raw/labels.parquet", "data/raw/invoices.parquet")
ACCESS_SCOPE = "processed_test_and_physical_shared_raw_for_consistency_only"


def _uuid(value):
    try:
        if str(UUID(value)) != value:
            raise ValueError("Identificador deve ser UUID canonico")
    except (ValueError, TypeError, AttributeError) as error:
        raise ValueError("Identificador de contrato invalido") from error


def validate_portable(freeze):
    """Validate structure/identity only; no files, not even model metadata opened."""
    keys = {"schema", "freeze_id", "created_at", "configuration", "versions",
            "source_sha256", "pre_access_sha256", "input_names", "access_scope",
            "historical_evidence_sha256", "authorized_operation", "test_authorized"}
    if (not isinstance(freeze, dict) or set(freeze) != keys
            or freeze["schema"] != "invoice-portable-freeze/1.1"
            or freeze["test_authorized"] is not False
            or freeze["authorized_operation"] != "evaluate_and_publish_once"
            or freeze["access_scope"] != ACCESS_SCOPE
            or freeze["input_names"] != [*PRE_ACCESS, *DEFERRED]):
        raise ValueError("Schema do congelamento portatil incompativel; nao e autorizacao")
    _uuid(freeze["freeze_id"])
    executor._gate_time(freeze["created_at"])
    config = freeze["configuration"]
    if not isinstance(config, dict):
        raise TypeError("Configuracao deve ser objeto JSON")
    normalized = config.copy()
    for key in ("model_sha256", "model_metadata_sha256"):
        normalized[key] = executor._digest(config.get(key))
    if executor._canonical(normalized) != executor._canonical(executor.real_configuration_contract()):
        raise ValueError("Configuracao real incompativel com protocolo legado")
    for key, names in (("pre_access_sha256", PRE_ACCESS),
                       ("source_sha256", executor.REAL_SOURCE_NAMES),
                       ("historical_evidence_sha256", executor.history.HISTORICAL_HASHES)):
        hashes = freeze[key]
        if not isinstance(hashes, dict) or set(hashes) != set(names):
            raise ValueError("Conjunto de hashes congelados incompativel; TEST nao permitido")
        for value in hashes.values():
            executor._digest(value)
    if (executor._digest(freeze["pre_access_sha256"][PRE_ACCESS[2]]) != normalized["model_sha256"]
            or executor._digest(freeze["pre_access_sha256"][PRE_ACCESS[3]]) != normalized["model_metadata_sha256"]):
        raise ValueError("Identidade do modelo/metadata diverge da configuracao")
    versions = freeze["versions"]
    if (not isinstance(versions, dict) or set(versions) != set(executor._versions())
            or any(not isinstance(v, str) or not v or len(v) > 64
                   or any(c not in "0123456789abcdefghijklmnopqrstuvwxyz.+-" for c in v.lower())
                   for v in versions.values())):
        raise ValueError("Versoes do congelamento invalidas")


def bind(freeze, context, *, freeze_path, context_path, freeze_hash, context_hash,
         check_locations=True):
    """Bind metadata. Archive verification can avoid filesystem path resolution.

No declared input path is resolved/stat'ed here. Deferred digests MUST be null:
they are recorded only by a separately authorized future input validation.
"""
    validate_portable(freeze)
    keys = {"schema", "context_id", "created_at", "freeze_sha256", "freeze_path",
            "project_root", "run_dir", "destination", "input_paths", "input_hashes_sha256"}
    if (not isinstance(context, dict) or set(context) != keys
            or context["schema"] != "invoice-execution-context/1.0"):
        raise ValueError("Schema do contexto incompativel")
    _uuid(context["context_id"])
    if executor._digest(context["freeze_sha256"]) != executor._digest(freeze_hash):
        raise ValueError("Contexto vinculado a outro congelamento")
    project, run, declared_freeze = (Path(executor._gate_text(context[k]))
                                    for k in ("project_root", "run_dir", "freeze_path"))
    for path in (project, run, declared_freeze):
        if not path.is_absolute() or ".." in path.parts:
            raise ValueError("Caminhos do contexto devem ser absolutos e canonicos")
    if (str(freeze_path) != context["freeze_path"]
            or Path(context_path) != run / "context.json"
            or context["destination"] != str(run / "results")
            or declared_freeze.name != "freeze.json"):
        raise ValueError("Destino/caminho diverge do contexto; copia nao autoriza tentativa")
    if check_locations:
        for key in ("project_root", "run_dir", "freeze_path"):
            executor._gate_absolute_path(context[key])
        executor._external(run)
        executor._external(declared_freeze)
    expected_paths = {name: str(project / name) for name in (*PRE_ACCESS, *DEFERRED)}
    if executor._canonical(context["input_paths"]) != executor._canonical(expected_paths):
        raise ValueError("Allowlist de caminhos de entrada incompativel")
    hashes = context["input_hashes_sha256"]
    if not isinstance(hashes, dict) or set(hashes) != set(expected_paths):
        raise ValueError("Conjunto de hashes do contexto incompativel")
    if (any(hashes[name] is not None for name in DEFERRED)
            or any(executor._digest(hashes[name]) != executor._digest(freeze["pre_access_sha256"][name])
                   for name in PRE_ACCESS)):
        raise ValueError("Hashes do contexto divergentes; TEST/raw devem permanecer nao verificados")
    bound = {**freeze, **{k: context[k] for k in ("project_root", "run_dir", "destination", "input_paths")},
             "context_created_at": context["created_at"], "context_sha256": executor._digest(context_hash)}
    executor._gate_time(context["created_at"])
    return bound


def validate_authorization(freeze, authorization, freeze_hash):
    keys = {"schema", "decision", "authorized_by", "authorization_reference", "issued_at",
            "freeze_sha256", "context_sha256", "configuration_sha256", "run_dir", "destination",
            "split", "purpose", "provenance_acknowledged", "expires_at", "access_scope", "authorized_operation"}
    if not isinstance(authorization, dict) or set(authorization) != keys:
        raise ValueError("Schema da autorizacao incompativel")
    config = freeze["configuration"]
    if (authorization["schema"] != "invoice-real-authorization/1.3"
            or authorization["decision"] != "approve_once"
            or executor._digest(authorization["freeze_sha256"]) != executor._digest(freeze_hash)
            or executor._digest(authorization["context_sha256"]) != freeze["context_sha256"]
            or executor._digest(authorization["configuration_sha256"]) != hashlib.sha256(executor._canonical(config)).hexdigest()
            or authorization["run_dir"] != freeze["run_dir"]
            or authorization["destination"] != freeze["destination"]
            or authorization["split"] != "test" or authorization["purpose"] != config["purpose"]
            or authorization["access_scope"] != freeze["access_scope"]
            or authorization["authorized_operation"] != freeze["authorized_operation"]
            or executor._canonical(authorization["provenance_acknowledged"]) != executor._canonical(config["provenance"])):
        raise PermissionError("Autorizacao nao corresponde ao congelamento/contexto/destino/escopo")
    executor._gate_text(authorization["authorized_by"])
    executor._gate_text(authorization["authorization_reference"])
