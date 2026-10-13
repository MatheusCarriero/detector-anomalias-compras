"""Explicit one-shot evaluation of authorized inputs; no CLI or automatic run.

Only generated fixtures exercise this module during development. A future real
call requires independent approval, a matching freeze and an unused receipt.
Checksums prove identity, not approval authenticity or legacy fit provenance.
"""

import hashlib
import math
from datetime import timezone
from pathlib import Path

import joblib

from ml.scripts import invoice_data_adapter as adapter
from ml.scripts import invoice_execution_context as binding
from ml.scripts import invoice_final_evaluation as executor
from ml.scripts import invoice_real_inputs as inputs

DOCUMENT_FILES = ("freeze.json", "authorization.json", "authorization_claim.json", "context.json")
STAGE_FILES = ("execution_started.json", "inputs_validated.json", "evaluation_started.json")
BUNDLE_FILES = (*DOCUMENT_FILES, *STAGE_FILES, "evidence.json")
COMPLETION_FILE = "publication_complete.json"


def _run_file(run_dir, name):
    return executor._fixture_path(run_dir, name)


def _reject_failed_publication(root):
    for parent in (root.parent, root):
        failure = parent / "failure.json"
        if failure.exists() or failure.is_symlink():
            raise ValueError("Tentativa falha: publicacao proibida")


def _completion_record(record, manifest_hash, created_at):
    return {
        "schema": "invoice-real-publication/1.0", "status": "complete",
        "created_at": created_at, "manifest_sha256": executor._digest(manifest_hash),
        "freeze_sha256": record["freeze_sha256"],
        "authorization_sha256": record["authorization_sha256"],
        "context_sha256": record["context_sha256"], "destination": record["destination"],
    }


def _live_inputs(freeze, authorization, documents, hashes, input_hashes):
    """No input resolution/hash without live, previously consumed permission."""
    if set(input_hashes) != set(freeze["input_paths"]):
        raise ValueError("Conjunto de inputs validados diverge do congelamento")
    for name, expected in input_hashes.items():
        inputs._live_contract(freeze, authorization, documents, hashes)
        path = adapter._paths(freeze["project_root"], (name,))[name]
        inputs._live_contract(freeze, authorization, documents, hashes)
        if executor.sha256(path) != expected:
            raise ValueError("Input alterado entre validacao e publicacao")
    return inputs._live_contract(freeze, authorization, documents, hashes)


def _metrics_contract(metrics, rows):
    """Reject incomplete results; no scoring or metric recomputation."""
    if not isinstance(metrics, dict) or set(metrics) != {
        "isolation_forest", "invoice_value", "comparisons", "selection_diagnostics",
    }:
        raise ValueError("Metricas incompletas")
    for strategy in ("isolation_forest", "invoice_value"):
        summary = metrics[strategy]
        budgets = summary["budgets"]
        if (summary["rows"] != rows or [b["percent"] for b in budgets] != [1, 5, 10]
                or [b["k"] for b in budgets] != [math.ceil(rows * p / 100) for p in (1, 5, 10)]):
            raise ValueError("Metricas/coorte/orcamentos divergentes")
        diagnostics = metrics["selection_diagnostics"][strategy]
        if [d["percent"] for d in diagnostics] != [1, 5, 10]:
            raise ValueError("Diagnosticos incompletos")
        for item in diagnostics:
            if sum(map(sum, item["confusion_matrix"])) != rows:
                raise ValueError("Matriz nao reconcilia com a coorte")
    if [item["percent"] for item in metrics["comparisons"]] != [1, 5, 10]:
        raise ValueError("Comparacoes incompletas")


def verify_real_bundle(results_dir, *, expected_manifest_sha256, expected_freeze_sha256,
                       expected_authorization_sha256, expected_context_sha256=None):
    """Verify a PUBLISHED result, never a partial bundle from a failed attempt.

    Read bundle JSONs and the run's completion/failure state; never reopen datasets or
    score. Freeze portability does not relocate a published bundle. Expiry is historical.
    External pins must be retained independently. An internally consistent
    fabricated bundle is not proof of execution or a human signature.
    """
    return _verify_real_bundle(
        results_dir, expected_manifest_sha256=expected_manifest_sha256,
        expected_freeze_sha256=expected_freeze_sha256,
        expected_authorization_sha256=expected_authorization_sha256,
        expected_context_sha256=expected_context_sha256, require_completion=True,
    )


def _verify_real_bundle(results_dir, *, expected_manifest_sha256, expected_freeze_sha256,
                        expected_authorization_sha256, expected_context_sha256=None,
                        allow_pending=False, require_completion=False):
    """Internal staging verification is not confirmation of publication."""
    if expected_context_sha256 is None:
        raise PermissionError("Pin externo do contexto obrigatorio")
    root = executor._external(results_dir)
    if root.name != ("results.pending" if allow_pending else "results"):
        raise ValueError("Bundle nao publicado ou destino de staging incompativel")
    _reject_failed_publication(root)
    manifest_bytes = _run_file(root, "manifest.json").read_bytes()
    if hashlib.sha256(manifest_bytes).hexdigest() != executor._digest(expected_manifest_sha256):
        raise ValueError("Hash do manifesto divergente")
    manifest = executor._json(manifest_bytes)
    if (not isinstance(manifest, dict) or set(manifest) != {
            "schema", "freeze_sha256", "authorization_sha256", "context_sha256", "files"}
            or manifest["schema"] != "invoice-real-manifest/1.2"
            or set(manifest["files"]) != set(BUNDLE_FILES)
            or {p.name for p in root.iterdir()} != {*BUNDLE_FILES, "manifest.json"}):
        raise ValueError("Manifesto/conjunto de arquivos incompativel")
    pins = [executor._digest(value) for value in (expected_freeze_sha256, expected_authorization_sha256, expected_context_sha256)]
    if [executor._digest(manifest[key]) for key in ("freeze_sha256", "authorization_sha256", "context_sha256")] != pins:
        raise ValueError("Manifesto nao vinculado aos pins externos")
    values, digests = {}, {}
    for name in BUNDLE_FILES:
        content = _run_file(root, name).read_bytes()
        digests[name] = hashlib.sha256(content).hexdigest()
        if digests[name] != executor._digest(manifest["files"][name]):
            raise ValueError("Hash de arquivo do bundle divergente")
        values[name] = executor._json(content)
    if [digests[name] for name in ("freeze.json", "authorization.json", "context.json")] != pins:
        raise ValueError("Documentos do bundle divergem dos pins externos")
    portable, auth, claim, context = (values[name] for name in DOCUMENT_FILES)
    start, validated, scored, record = (values[name] for name in (*STAGE_FILES, "evidence.json"))
    freeze = binding.bind(
        portable, context, freeze_path=context.get("freeze_path"), context_path=root.parent / "context.json",
        freeze_hash=pins[0], context_hash=pins[2], check_locations=False,
    )
    binding.validate_authorization(freeze, auth, pins[0])
    config = freeze["configuration"]
    expected_claim = executor._claim_record(freeze, auth, *pins[:2], claim["created_at"])
    normalized_claim = claim.copy()
    for key in ("freeze_sha256", "authorization_sha256", "configuration_sha256", "context_sha256"):
        normalized_claim[key] = executor._digest(claim.get(key))
    if executor._canonical(normalized_claim) != executor._canonical(expected_claim):
        raise ValueError("Recibo do bundle divergente")
    for item in (start, validated, scored, record):
        if ([executor._digest(item[key]) for key in ("freeze_sha256", "authorization_sha256", "context_sha256")] != pins
                or executor._digest(item["receipt_sha256"]) != digests["authorization_claim.json"]
                or executor._canonical(item["configuration"]) != executor._canonical(config)
                or item["destination"] != freeze["destination"]):
            raise ValueError("Registro nao pertence a execucao autorizada")
    for item in (claim, start, validated, scored, record):
        executor._authorization_time(freeze, auth, executor._gate_time(item["created_at"]))
    times = [executor._gate_time(item["created_at"]) for item in (claim, start, validated, scored, record)]
    if times != sorted(times):
        raise ValueError("Cronologia dos estagios invalida")
    if (start["schema"] != "invoice-real-input-start/1.1"
            or validated["schema"] != "invoice-real-input-validation/1.1"
            or scored["schema"] != "invoice-real-score-start/1.1"
            or record["schema"] != "invoice-real-evidence/1.1"
            or record["source_reconciled"] is not False
            or record["source_rows_consistent"] is not True
            or record["frame_sha256"] != validated["frame_sha256"]
            or executor._canonical(record["provenance"]) != executor._canonical(config["provenance"])
            or record["test_used"] is not True or record["model_fits_in_executor"] != 0
            or record["score_calls"] != 1 or record["final_evaluation"] is not True
            or record["input_hashes_sha256"] != validated["input_hashes_sha256"]
            or record["historical_evidence_sha256"] != freeze["historical_evidence_sha256"]
            or record["source_sha256"] != freeze["source_sha256"]
            or record["versions"] != freeze["versions"]
            or record["currency"] != validated["currency"]):
        raise ValueError("Evidencia nao corresponde aos inputs/execucao")
    input_hashes = validated["input_hashes_sha256"]
    if not isinstance(input_hashes, dict) or set(input_hashes) != set(freeze["input_names"]):
        raise ValueError("Conjunto de hashes de inputs nao corresponde ao contrato autorizado")
    normalized_inputs = {name: executor._digest(value) for name, value in input_hashes.items()}
    if any(normalized_inputs[name] != executor._digest(expected)
           for name, expected in freeze["pre_access_sha256"].items()):
        raise ValueError("Hash de input registrado diverge da identidade congelada")
    bound = {name: digests[name] for name in STAGE_FILES}
    if record["execution_records_sha256"] != bound or scored["inputs_validated_sha256"] != bound["inputs_validated.json"]:
        raise ValueError("Cadeia de recibos divergente")
    _metrics_contract(record["metrics"], validated["rows"]["test"])
    if require_completion:
        completion_path = _run_file(root.parent, COMPLETION_FILE)
        if not completion_path.is_file():
            raise ValueError("Conclusao de publicacao ausente; renomear staging nao conclui execucao")
        completion = executor._json(completion_path.read_bytes())
        if not isinstance(completion, dict):
            raise ValueError("Conclusao de publicacao divergente")
        expected = _completion_record(record, expected_manifest_sha256, completion.get("created_at"))
        if executor._canonical(completion) != executor._canonical(expected):
            raise ValueError("Conclusao de publicacao divergente do manifesto/destino")
        completed_at = executor._gate_time(completion["created_at"])
        # Reuse the exact authorization bytes already verified against external pins.
        if not executor._gate_time(record["created_at"]) <= completed_at < executor._gate_time(auth["expires_at"]):
            raise ValueError("Cronologia da conclusao de publicacao invalida")
        _reject_failed_publication(root)
    return record


def _publish(freeze, authorization, documents, hashes, record, stage_bytes):
    """Only the runner produces these stage bytes; never accept user metrics."""
    if set(stage_bytes) != set(STAGE_FILES):
        raise ValueError("Recibos de execucao incompletos; nao preparar publicacao")
    run_dir = Path(freeze["run_dir"])
    inputs._live_contract(freeze, authorization, documents, hashes)
    for name, content in stage_bytes.items():
        if _run_file(run_dir, name).read_bytes() != content:
            raise ValueError("Recibo de execucao alterado antes de publicar")
    destination, pending = run_dir / "results", run_dir / "results.pending"
    _reject_failed_publication(destination)
    completion_path = run_dir / COMPLETION_FILE
    if completion_path.exists() or completion_path.is_symlink():
        raise FileExistsError("Conclusao de publicacao ja existente")
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Destino ja existente")
    pending.mkdir(exist_ok=False)
    identity = (pending.stat().st_dev, pending.stat().st_ino)
    contents = {name: path.read_bytes() for name, path in zip(DOCUMENT_FILES, documents, strict=True)}
    contents.update(stage_bytes)
    contents["evidence.json"] = executor._canonical(record) + b"\n"
    for name, content in contents.items():
        with (pending / name).open("xb") as stream:
            stream.write(content)
    manifest = {
        "schema": "invoice-real-manifest/1.2", "freeze_sha256": hashes[0],
        "authorization_sha256": hashes[1], "context_sha256": hashes[3],
        "files": {name: hashlib.sha256(content).hexdigest() for name, content in contents.items()},
    }
    # Pin the bytes generated here, never adopt a potentially replaced manifest.
    manifest_hash = hashlib.sha256(executor._canonical(manifest) + b"\n").hexdigest()
    executor._write_json(pending / "manifest.json", manifest)
    verification = {"expected_manifest_sha256": manifest_hash,
                    "expected_freeze_sha256": hashes[0], "expected_authorization_sha256": hashes[1],
                    "expected_context_sha256": hashes[3]}
    _verify_real_bundle(pending, **verification, allow_pending=True)
    _live_inputs(freeze, authorization, documents, hashes, record["input_hashes_sha256"])
    _verify_real_bundle(pending, **verification, allow_pending=True)
    if (pending.stat().st_dev, pending.stat().st_ino) != identity:
        raise ValueError("Identidade do staging alterada antes da promocao")
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Destino ja existente")
    pending.rename(destination)
    if (destination.stat().st_dev, destination.stat().st_ino) != identity:
        raise ValueError("Identidade do staging alterada durante a promocao")
    inputs._live_contract(freeze, authorization, documents, hashes)
    _verify_real_bundle(destination, **verification)
    completed_at = inputs._live_contract(freeze, authorization, documents, hashes)
    # This separate exclusive commit marker is never present in staging.
    # A crash before it leaves an unpublished attempt, not a resumable run.
    executor._write_json(completion_path, _completion_record(record, manifest_hash, completed_at.isoformat()))
    verify_real_bundle(destination, **verification)
    return destination


def run_authorized_evaluation(freeze_path, authorization_path=None, receipt_path=None, *,
                              expected_freeze_sha256=None, expected_authorization_sha256=None,
                              expected_receipt_sha256=None, start_evaluation=False, split="test",
                              context_path=None, expected_context_sha256=None):
    """Consume a FRESH receipt once. Never resume an input-only or failed attempt.

    No path override, caller-provided model/frame, automatic authorization or CLI.
    A valid receipt alone cannot execute this function. Defaults fail before I/O.
    """
    if start_evaluation is not True or split != "test":
        raise PermissionError("Avaliacao requer inicio explicito e split autorizado")
    pins = (expected_freeze_sha256, expected_authorization_sha256, expected_receipt_sha256,
            expected_context_sha256)
    if authorization_path is None or receipt_path is None or context_path is None or any(pin is None for pin in pins):
        raise PermissionError("Autorizacao, recibo e pins externos obrigatorios")
    pins = tuple(executor._digest(pin) for pin in pins)
    freeze, authorization, documents, hashes = inputs._documents(
        freeze_path, authorization_path, receipt_path, pins, context_path=context_path,
    )
    run_dir = Path(freeze["run_dir"])
    executor._ensure_real_unused(run_dir, include_claim=False)
    adapted = inputs.validate_authorized_inputs(
        freeze_path, authorization_path, receipt_path, expected_freeze_sha256=pins[0],
        expected_authorization_sha256=pins[1], expected_receipt_sha256=pins[2],
        start_input_validation=True, split=split,
        context_path=context_path, expected_context_sha256=pins[3],
    )
    try:
        technical = adapted.technical_record
        stage_bytes = {name: _run_file(run_dir, name).read_bytes() for name in STAGE_FILES[:2]}
        if executor._json(stage_bytes["inputs_validated.json"]) != technical:
            raise ValueError("Recibo retornado diverge do registro persistido")
        if (adapter._table_digest(adapted.frame) != technical["frame_sha256"]
                or joblib.hash(adapted.model) != technical["model_state_joblib_hash"]):
            raise ValueError("Inputs em memoria alterados depois da validacao")
        executor._frame(adapted.frame, freeze["configuration"])
        executor._model(adapted.model, freeze["configuration"])
        now = _live_inputs(freeze, authorization, documents, hashes, technical["input_hashes_sha256"])
        scoring = {
            "schema": "invoice-real-score-start/1.1", "created_at": now.isoformat(),
            "freeze_sha256": hashes[0], "authorization_sha256": hashes[1], "receipt_sha256": hashes[2],
            "configuration": freeze["configuration"], "source_reconciled": False,
            "context_sha256": hashes[3], "destination": freeze["destination"],
            "inputs_validated_sha256": hashlib.sha256(stage_bytes["inputs_validated.json"]).hexdigest(),
            "automatic_retry": False,
        }
        executor._write_json(run_dir / "evaluation_started.json", scoring)
        stage_bytes["evaluation_started.json"] = _run_file(run_dir, "evaluation_started.json").read_bytes()
        inputs._live_contract(freeze, authorization, documents, hashes)
        metrics = executor._evaluate_validated_frame(adapted.model, adapted.frame, freeze["configuration"])
        if adapter._table_digest(adapted.frame) != technical["frame_sha256"]:
            raise ValueError("Frame alterado durante scoring")
        _live_inputs(freeze, authorization, documents, hashes, technical["input_hashes_sha256"])
        record = {
            "schema": "invoice-real-evidence/1.1", "created_at": executor.datetime.now(timezone.utc).isoformat(),
            "freeze_sha256": hashes[0], "authorization_sha256": hashes[1], "receipt_sha256": hashes[2],
            "configuration": freeze["configuration"], "provenance": freeze["configuration"]["provenance"],
            "context_sha256": hashes[3], "destination": freeze["destination"],
            "source_reconciled": False, "source_rows_consistent": True,
            "test_used": True, "final_evaluation": True, "model_fits_in_executor": 0, "score_calls": 1,
            "metrics": metrics, "currency": technical["currency"], "frame_sha256": technical["frame_sha256"],
            "input_hashes_sha256": technical["input_hashes_sha256"],
            "ids_sha256": hashlib.sha256(executor._canonical(adapted.frame["invoice_id"].tolist())).hexdigest(),
            "historical_evidence_sha256": freeze["historical_evidence_sha256"],
            "source_sha256": freeze["source_sha256"], "versions": freeze["versions"],
            "execution_records_sha256": {name: hashlib.sha256(content).hexdigest() for name, content in stage_bytes.items()},
            "confusion_semantics": "rows reference [0,1]; columns [not selected,selected] at global K",
            "scope": "Retrospective triage; labels are not certified fraud; legacy fit provenance unverified",
        }
        return _publish(freeze, authorization, documents, hashes, record, stage_bytes)
    except Exception as error:
        try:
            executor._write_json(run_dir / "failure.json", {
                "schema": "invoice-real-evaluation-failure/1.0", "freeze_sha256": hashes[0],
                "exception_type": type(error).__name__, "data_access_may_have_started": True,
                "evaluation_may_have_started": (run_dir / "evaluation_started.json").exists(),
                "automatic_retry": False,
            })
        except FileExistsError:
            # Preserve the original failure, including a competing writer's marker.
            pass
        raise
