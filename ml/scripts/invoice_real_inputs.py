"""Explicit, authorized input validation; never fitting, scoring or publication.

There is no CLI or automatic execution. This route may access the frozen TEST
and shared raw files only after consuming externally pinned permission. Tests
exercise it exclusively with generated, external fixtures.
"""

import hashlib
from datetime import timezone
from io import BytesIO

import numpy as np
import pandas as pd

from ml.scripts import invoice_data_adapter as adapter
from ml.scripts import invoice_final_evaluation as executor

TEST_INPUT = "data/processed/test_features.parquet"
ACCESS_SCOPE = "processed_test_and_physical_shared_raw_for_consistency_only"


def _documents(freeze_path, authorization_path, receipt_path, pins):
    freeze, authorization, paths, hashes, now = executor._load_real_authorization(
        freeze_path, authorization_path,
        expected_freeze_sha256=pins[0], expected_authorization_sha256=pins[1],
    )
    run_dir = paths[0].parent
    receipt_path = executor._external(receipt_path)
    if receipt_path != run_dir / "authorization_claim.json":
        raise ValueError("Recibo deve pertencer ao destino congelado")
    receipt_content = receipt_path.read_bytes()
    receipt_hash = executor._digest(pins[2])
    if hashlib.sha256(receipt_content).hexdigest() != receipt_hash:
        raise ValueError("Hash do recibo divergente")
    receipt = executor._json(receipt_content)
    if not isinstance(receipt, dict):
        raise TypeError("Recibo deve ser objeto JSON")
    claimed_at = executor._gate_time(receipt.get("created_at"))
    issued_at = executor._gate_time(authorization["issued_at"])
    if not issued_at <= claimed_at <= now:
        raise PermissionError("Cronologia do recibo incompativel com autorizacao")
    expected = executor._claim_record(freeze, authorization, *hashes, receipt["created_at"])
    normalized = receipt.copy()
    for key in ("freeze_sha256", "authorization_sha256", "configuration_sha256"):
        normalized[key] = executor._digest(receipt.get(key))
    if executor._canonical(normalized) != executor._canonical(expected):
        raise PermissionError("Recibo diverge da autorizacao/configuracao congelada")
    return freeze, authorization, (*paths, receipt_path), (*hashes, receipt_hash)


def _live_contract(freeze, authorization, documents, hashes):
    executor._check_sources(freeze)
    if [executor.sha256(path) for path in documents] != list(hashes):
        raise ValueError("Documento alterado durante a validacao")
    # Clock checked last: expensive hashes must not extend expired permission.
    now = executor.datetime.now(timezone.utc)
    executor._authorization_time(freeze, authorization, now)
    return now


def _read_inputs(paths, expected_hashes, content):
    for name, path in paths.items():
        payload = path.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        if name in expected_hashes and digest != executor._digest(expected_hashes[name]):
            raise ValueError("Hash do input diverge do congelamento; nao desserializar")
        content[name] = payload


def _development(content, configuration):
    frames = {name: pd.read_parquet(BytesIO(content[path]))
              for name, path in adapter.PROCESSED.items()}
    for name, frame in frames.items():
        adapter._processed_frame(frame, name)
    if set(frames["train"]["invoice_id"]) & set(frames["val"]["invoice_id"]):
        raise ValueError("Sobreposicao de IDs TRAIN/VALIDATION")
    adapter._metadata(content[adapter.METADATA])
    model = adapter._load_model(content[adapter.MODEL], configuration["legacy_offset"])
    return frames, model


def _source_consistency(frames, content):
    """Current row agreement only; never certify the legacy training provenance."""
    official = pd.read_parquet(BytesIO(content[adapter.RAW_SPLITS]), columns=["invoice_id", "split"])
    adapter._schema(official, ["invoice_id", "split"], "splits oficiais")
    if not official["split"].isin(["train", "val", "test"]).all():
        raise ValueError("Particao oficial desconhecida")
    seen = set()
    for split, frame in frames.items():
        ids = set(frame["invoice_id"])
        if seen & ids:
            raise ValueError("Sobreposicao de IDs entre particoes processadas")
        seen.update(ids)
        expected_ids = set(official.loc[official["split"].eq(split), "invoice_id"])
        if ids != expected_ids:
            raise ValueError("Coorte processada diverge dos IDs/split oficiais")
    if seen != set(official["invoice_id"]):
        raise ValueError("Perda ou inclusao silenciosa de IDs oficiais")
    frame = frames["test"].sort_values("invoice_id").reset_index(drop=True)
    ids = frame["invoice_id"].tolist()
    labels = pd.read_parquet(BytesIO(content[adapter.RAW_LABELS]),
                             columns=["invoice_id", "is_fraud", "fraud_type"])
    amounts = pd.read_parquet(BytesIO(content[adapter.RAW_AMOUNTS]),
                              columns=["invoice_id", "invoice_amount", "currency"])
    for source, columns, name in (
        (labels, ["invoice_id", "is_fraud", "fraud_type"], "labels"),
        (amounts, ["invoice_id", "invoice_amount", "currency"], "valores/moedas"),
    ):
        adapter._schema(source, columns, name)
        if set(source["invoice_id"]) != seen:
            raise ValueError("Cobertura de IDs da fonte diverge dos splits oficiais")
    labels = labels.set_index("invoice_id").loc[ids].reset_index()
    adapter.validate_target(labels)
    adapter._utf8(labels["fraud_type"])
    if not frame[["invoice_id", "is_fraud", "fraud_type"]].equals(labels):
        raise ValueError("Labels/fraud_type divergentes por ID; nenhuma correcao")
    amounts = amounts.set_index("invoice_id").loc[ids].reset_index()
    values = amounts["invoice_amount"]
    if (not pd.api.types.is_numeric_dtype(values.dtype)
            or pd.api.types.is_bool_dtype(values.dtype)
            or pd.api.types.is_complex_dtype(values.dtype) or values.isna().any()
            or not np.isfinite(values.to_numpy(dtype=float)).all()
            or not np.array_equal(values.to_numpy(), frame["invoice_amount"].to_numpy())):
        raise ValueError("Valores da fonte invalidos ou divergentes por ID")
    currency = amounts["currency"]
    if (not currency.map(lambda value: isinstance(value, str) and bool(value)
                         and value == value.strip()).all() or currency.nunique() != 1):
        raise ValueError("Exigida uma unica moeda nao nula, sem conversao")
    adapter._utf8(currency)
    return frame, str(currency.iloc[0])


def validate_authorized_inputs(freeze_path, authorization_path=None, receipt_path=None, *,
                               expected_freeze_sha256=None, expected_authorization_sha256=None,
                               expected_receipt_sha256=None, start_input_validation=False, split="test"):
    """Consume permission once and return validated inputs, without evaluation.

    All three pins must come from the trusted external approval/receipt workflow.
    A hash checks integrity, not human identity. Default invocation cannot read
    inputs. Starting validation consumes the run even on failure; never remove
    its marker to retry. A returned object is NOT authorization to score it.
    """
    if start_input_validation is not True:
        raise PermissionError("Validacao de inputs exige inicio explicito; avaliacao nao automatica")
    if not isinstance(split, str) or split != "test":
        raise PermissionError("Split solicitado nao autorizado pelo contrato final")
    pins = (expected_freeze_sha256, expected_authorization_sha256, expected_receipt_sha256)
    if authorization_path is None or receipt_path is None or any(pin is None for pin in pins):
        raise PermissionError("Autorizacao, recibo e tres hashes externos obrigatorios")
    pins = tuple(executor._digest(pin) for pin in pins)
    freeze, authorization, documents, hashes = _documents(
        freeze_path, authorization_path, receipt_path, pins,
    )
    run_dir = documents[0].parent
    executor._ensure_real_unused(run_dir, include_claim=False)
    now = _live_contract(freeze, authorization, documents, hashes)
    marker = {
        "schema": "invoice-real-input-start/1.0", "created_at": now.isoformat(),
        "freeze_sha256": hashes[0], "authorization_sha256": hashes[1],
        "receipt_sha256": hashes[2], "configuration": freeze["configuration"],
        "access_scope": freeze["access_scope"], "source_reconciled": False,
        "input_validation_started": True, "data_access_may_have_started": True,
        "evaluation_started": False, "model_fits": 0, "score_calls": 0,
    }
    # Exclusive creation arbitrates concurrent calls BEFORE any input I/O.
    executor._write_json(run_dir / "execution_started.json", marker)
    try:
        root = freeze["project_root"]
        content = {}
        paths = adapter._paths(root, adapter.HASHED_INPUTS)
        _read_inputs(paths, freeze["pre_access_sha256"], content)
        frames, model = _development(content, freeze["configuration"])
        # No TEST/raw stat or content has occurred yet. Recheck approval first.
        _live_contract(freeze, authorization, documents, hashes)
        for name in (TEST_INPUT, *adapter.RAW_INPUTS):
            _live_contract(freeze, authorization, documents, hashes)
            current_path = adapter._paths(root, (name,))
            paths.update(current_path)
            _live_contract(freeze, authorization, documents, hashes)
            _read_inputs(current_path, {}, content)
        frames["test"] = pd.read_parquet(BytesIO(content[TEST_INPUT]))
        adapter._processed_frame(frames["test"], "test")
        frame, currency = _source_consistency(frames, content)
        input_hashes = {name: hashlib.sha256(payload).hexdigest() for name, payload in content.items()}
        for name, path in paths.items():
            _live_contract(freeze, authorization, documents, hashes)
            if executor.sha256(path) != input_hashes[name]:
                raise ValueError("Input alterado durante validacao; nao publicar")
        _live_contract(freeze, authorization, documents, hashes)
        record = {
            "schema": "invoice-real-input-validation/1.0",
            "created_at": executor.datetime.now(timezone.utc).isoformat(),
            "freeze_sha256": hashes[0], "authorization_sha256": hashes[1],
            "receipt_sha256": hashes[2], "configuration": freeze["configuration"],
            "configuration_sha256": hashlib.sha256(executor._canonical(freeze["configuration"])).hexdigest(),
            "provenance": freeze["configuration"]["provenance"],
            "source_reconciled": False, "source_rows_consistent": True,
            "scientific_evidence": False, "final_evaluation": False, "evaluation_started": False,
            "test_used": True, "data_access_performed": True, "input_hashes_verified": True,
            "model_fits": 0, "score_calls": 0, "split": "test",
            "rows": {name: len(part) for name, part in frames.items()},
            "features": list(executor.ORDERED_FEATURES), "feature_count": 19,
            "currency": currency, "input_hashes_sha256": input_hashes,
            "accessed_files": list(content), "access_scope": freeze["access_scope"],
            "source_sha256": freeze["source_sha256"], "versions": executor._versions(),
        }
        executor._write_json(run_dir / "inputs_validated.json", record)
        return adapter.AdaptedInvoice(frame, model, record)
    except Exception as error:
        # Persist failure, never retry/clean markers or misreport TEST as closed.
        executor._write_json(run_dir / "failure.json", {
            "schema": "invoice-real-input-failure/1.0", "freeze_sha256": hashes[0],
            "error_type": type(error).__name__, "data_access_may_have_started": True,
            "evaluation_started": False, "model_fits": 0, "score_calls": 0,
        })
        raise
