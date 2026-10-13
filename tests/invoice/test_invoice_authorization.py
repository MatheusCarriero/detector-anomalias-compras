"""Pre-access permission receipts must never inspect declared model/data inputs."""

import builtins
import copy
import hashlib
import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from invoice_context_fixtures import seal_context, separate
from invoice_history_fixtures import write_history

from ml.scripts import invoice_final_evaluation as executor

ROOT = Path(__file__).resolve().parents[2]
MODEL_SHA = "c9c0f51a9c962fac5ea6b34db5e0b74f09c120896bf9e7bf3a87418df2adba1b"
METADATA_SHA = "ba07485e8dda458e45376b6edc4bd164926efe2c6ca8385cde32f7309db86595"
PRE_ACCESS = (
    "data/processed/train_features.parquet", "data/processed/val_features.parquet",
    "ml/models/isolation_forest.joblib", "ml/models/model_metadata.json",
)
TEST_INPUT = "data/processed/test_features.parquet"
RAW_INPUTS = ("data/raw/splits.parquet", "data/raw/labels.parquet", "data/raw/invoices.parquet")
ACCESS_SCOPE = "processed_test_and_physical_shared_raw_for_consistency_only"
PROVENANCE = {
    "source_reconciled": False,
    "legacy_training_provenance_certified": False,
    "raw_independence_certified": False,
}
CONFIGURATION = {
    "schema": "invoice-real-configuration/1.0", "mode": "real_pre_access",
    "protocol_version": "invoice-academic-evaluation-1.0", "split": "test",
    "features": [
        "invoice_amount", "log_invoice_amount", "supplier_age_days", "supplier_frequency",
        "country_frequency", "amount_vs_supplier_mean", "supplier_amount_zscore",
        "department_frequency", "amount_vs_department_mean", "supplier_department_frequency",
        "payment_terms_days", "invoice_type_encoded", "submission_hour_sin",
        "submission_hour_cos", "day_of_week_sin", "day_of_week_cos", "month_sin",
        "month_cos", "is_weekend",
    ],
    "parameters": {
        "n_estimators": 200, "contamination": 0.22, "random_state": 42, "n_jobs": -1,
        "max_samples": "auto", "max_features": 1.0, "bootstrap": False,
        "warm_start": False, "verbose": 0,
    },
    "legacy_offset": -0.5211491197816622,
    "model_sha256": MODEL_SHA, "model_metadata_sha256": METADATA_SHA,
    "budget_percentages": [1, 5, 10], "decision_rule": "selection_at_k",
    "score_rule": "negative_score_samples_descending",
    "baseline": "invoice_amount_descending_signed", "tie_break": "invoice_id_ascending",
    "preprocessing": "existing_19_features_no_refit",
    "purpose": "academic_retrospective_triage", "provenance": PROVENANCE,
}


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


def digest(content):
    return hashlib.sha256(content).hexdigest()


def forbidden(*args, **kwargs):
    raise AssertionError("Pre-access gate must not inspect inputs, deserialize, fit, or score")


@pytest.fixture
def documents(tmp_path, monkeypatch):
    """Only descriptors and code hashes: declared data/model files do not exist."""
    class FixedClock(datetime):
        @classmethod
        def now(cls, tz=None):
            instant = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
            return instant.astimezone(tz) if tz is not None else instant.replace(tzinfo=None)

    monkeypatch.setattr(executor, "datetime", FixedClock)
    project_root = tmp_path / "described-project"
    project_root.mkdir()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    freeze = {
        "schema": "invoice-real-preregistration/1.2", "access_scope": ACCESS_SCOPE,
        "authorized_operation": "evaluate_and_publish_once",
        "created_at": "2026-09-01T10:00:00+00:00", "run_dir": str(run_dir.resolve()),
        "project_root": str(project_root.resolve()), "configuration": copy.deepcopy(CONFIGURATION),
        "versions": executor._versions(),
        "source_sha256": {
            name: digest((ROOT / name).read_bytes())
            for name in executor.REAL_SOURCE_NAMES
        },
        "pre_access_sha256": dict(zip(PRE_ACCESS, ["1" * 64, "2" * 64, MODEL_SHA, METADATA_SHA])),
        "input_paths": {
            name: str(project_root / name) for name in (*PRE_ACCESS, TEST_INPUT, *RAW_INPUTS)
        },
    }
    freeze["historical_evidence_sha256"] = write_history(
        project_root, CONFIGURATION, freeze["pre_access_sha256"], monkeypatch,
    )
    authorization = {
        "schema": "invoice-real-authorization/1.2", "decision": "approve_once",
        "authorized_operation": "evaluate_and_publish_once",
        "access_scope": ACCESS_SCOPE, "expires_at": "2026-10-01T00:00:00+00:00",
        "authorized_by": "SYNTHETIC_FIXTURE_NOT_AN_APPROVER",
        "authorization_reference": "SYNTHETIC_CONTRACT_NOT_HUMAN_APPROVAL",
        "issued_at": "2026-09-01T10:01:00+00:00", "freeze_sha256": "",
        "configuration_sha256": "", "run_dir": str(run_dir.resolve()), "split": "test",
        "purpose": "academic_retrospective_triage", "provenance_acknowledged": copy.deepcopy(PROVENANCE),
    }
    context = separate(freeze, authorization, run_dir / "freeze.json")
    return freeze, authorization, run_dir / "freeze.json", tmp_path / "authorization.json", context


def seal(documents):
    freeze, authorization, freeze_path, authorization_path, context = documents
    return seal_context(freeze, context, authorization, freeze_path,
                        freeze_path.parent / "context.json", authorization_path)

@pytest.fixture
def no_input_access(monkeypatch, documents):
    # Guard both Path and lower-level opens/stat, without resolving declared input paths.
    declared = {os.path.normcase(os.path.abspath(path)) for path in documents[4]["input_paths"].values()}
    real_roots = [os.path.normcase(str(ROOT / suffix)) + os.sep
                  for suffix in ("data", "ml/models", "notebooks", "evidence")]

    def guard(operation):
        def checked(path, *args, **kwargs):
            if isinstance(path, (str, bytes, os.PathLike)):
                normalized = os.path.normcase(os.path.abspath(os.fsdecode(path)))
                if normalized in declared or any(normalized.startswith(root) for root in real_roots):
                    forbidden()
            return operation(path, *args, **kwargs)
        return checked

    monkeypatch.setattr(builtins, "open", guard(builtins.open))
    monkeypatch.setattr(io, "open", guard(io.open))
    monkeypatch.setattr(os, "stat", guard(os.stat))
    monkeypatch.setattr(os, "lstat", guard(os.lstat))
    monkeypatch.setattr(executor.joblib, "load", forbidden)
    monkeypatch.setattr(executor.pd, "read_parquet", forbidden)
    monkeypatch.setattr(executor.IsolationForest, "fit", forbidden)
    monkeypatch.setattr(executor.IsolationForest, "score_samples", forbidden)


def claim(documents, pins):
    return executor.claim_real_evaluation_authorization(documents[2], documents[3], **pins)


def assert_unclaimed(documents):
    assert {path.name for path in documents[2].parent.iterdir()} == {"freeze.json", "context.json"}


def test_legacy_input_only_authority_does_not_enable_final_execution(documents, no_input_access):
    documents[0]["schema"] = "invoice-real-preregistration/1.1"
    documents[1]["schema"] = "invoice-real-authorization/1.1"
    pins = seal(documents)
    with pytest.raises(ValueError):
        claim(documents, pins)
    assert_unclaimed(documents)


@pytest.mark.parametrize("missing", ["authorization", "freeze_pin", "authorization_pin"])
def test_missing_authorization_fails_closed_before_any_path_io(tmp_path, monkeypatch, missing):
    arguments = {
        "authorization_path": tmp_path / "absent-auth.json",
        "expected_freeze_sha256": "1" * 64,
        "expected_authorization_sha256": "2" * 64,
    }
    arguments.pop({"authorization": "authorization_path", "freeze_pin": "expected_freeze_sha256",
                   "authorization_pin": "expected_authorization_sha256"}[missing])
    with monkeypatch.context() as context:
        context.setattr(Path, "open", forbidden)
        context.setattr(Path, "stat", forbidden)
        context.setattr(Path, "resolve", forbidden)
        with pytest.raises(PermissionError):
            executor.claim_real_evaluation_authorization(tmp_path / "missing-freeze.json", **arguments)


@pytest.mark.parametrize("position", [2, 3])
def test_input_path_as_permission_document_rejected_before_resolution(documents, monkeypatch, position):
    pins = seal(documents)
    invalid = Path(documents[4]["input_paths"][TEST_INPUT])
    changed = list(documents)
    changed[position] = invalid
    original = Path.resolve

    def resolve(path, *args, **kwargs):
        assert path != invalid, "Input path resolved before document allowlist"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve)
    with pytest.raises(ValueError, match="documentos"):
        claim(changed, pins)
    assert_unclaimed(documents)


def test_valid_permission_writes_receipt_without_input_access(documents, no_input_access):
    pins = seal(documents)
    result = claim(documents, pins)
    assert result == documents[2].parent / "authorization_claim.json"
    receipt = json.loads(result.read_bytes())
    assert receipt["schema"] == "invoice-real-authorization-claim/1.2"
    assert receipt["freeze_sha256"] == pins["expected_freeze_sha256"]
    assert receipt["authorization_sha256"] == pins["expected_authorization_sha256"]
    assert receipt["configuration_sha256"] == digest(canonical(CONFIGURATION))
    assert receipt["configuration"] == CONFIGURATION
    assert receipt["run_dir"] == str(documents[2].parent)
    assert receipt["provenance"] == PROVENANCE
    assert receipt["authorization"]["expires_at"] == "2026-10-01T00:00:00+00:00"
    assert receipt["authorization"]["access_scope"] == ACCESS_SCOPE
    assert receipt["real_execution_available"] is True
    assert receipt["evaluation_started"] is False
    for field in ("test_used", "data_access_performed", "source_reconciled",
                  "input_hashes_verified"):
        assert receipt[field] is False
    assert receipt["model_fits"] == 0
    assert receipt["score_calls"] == 0
    assert {path.name for path in result.parent.iterdir()} == {"freeze.json", "context.json", "authorization_claim.json"}


@pytest.mark.parametrize("pin", ["expected_freeze_sha256", "expected_authorization_sha256"])
@pytest.mark.parametrize("bad_value", ["0" * 64, "not-a-digest", None, True])
def test_invalid_external_pins_do_not_claim(documents, no_input_access, pin, bad_value):
    pins = seal(documents)
    pins[pin] = bad_value
    with pytest.raises((ValueError, TypeError, PermissionError)):
        claim(documents, pins)
    assert_unclaimed(documents)


@pytest.mark.parametrize("field,value", [
    ("decision", "approve"), ("split", "val"), ("purpose", "production"),
    ("authorized_by", ""), ("authorization_reference", " "),
    ("authorized_by", "\ud800"), ("issued_at", "2026-09-01T09:00:00+00:00"),
    ("issued_at", "2026-09-01T10:01:00"),
    ("provenance_acknowledged", {**PROVENANCE, "source_reconciled": True}),
    ("unknown_field", "extra"), ("run_dir", "relative-run"),
])
def test_invalid_authorization_does_not_claim(documents, no_input_access, field, value):
    documents[1][field] = value
    pins = seal(documents)
    with pytest.raises((ValueError, TypeError, PermissionError)):
        claim(documents, pins)
    assert_unclaimed(documents)


@pytest.mark.parametrize("field,value", [
    ("legacy_offset", -0.5), ("split", "val"), ("budget_percentages", [True, 5, 10]),
    ("features", list(reversed(CONFIGURATION["features"]))), ("model_sha256", "a" * 64),
    ("parameters", {**CONFIGURATION["parameters"], "verbose": False}),
    ("parameters", {**CONFIGURATION["parameters"], "max_features": 1}),
    ("provenance", {**PROVENANCE, "source_reconciled": 0}),
    ("unknown_field", False), ("baseline", "invoice_amount_descending_absolute"),
])
def test_changed_configuration_is_rejected_even_when_both_docs_are_repinned(
        documents, no_input_access, field, value):
    documents[0]["configuration"][field] = value
    pins = seal(documents)
    with pytest.raises((ValueError, TypeError, PermissionError)):
        claim(documents, pins)
    assert_unclaimed(documents)


@pytest.mark.parametrize("field", ["freeze_sha256", "configuration_sha256"])
def test_authorization_must_bind_matching_documents(documents, no_input_access, field):
    pins = seal(documents)
    documents[1][field] = "0" * 64
    content = canonical(documents[1])
    documents[3].write_bytes(content)
    pins["expected_authorization_sha256"] = digest(content)
    with pytest.raises((ValueError, PermissionError)):
        claim(documents, pins)
    assert_unclaimed(documents)


@pytest.mark.parametrize("change", ["test_hash", "swapped_paths", "source_path", "source_digest", "environment",
                                  "metadata_digest", "created_at", "unknown_field"])
def test_changed_freeze_fails_without_inspecting_described_inputs(documents, no_input_access, change):
    freeze = documents[0]
    if change == "test_hash":
        freeze["pre_access_sha256"][TEST_INPUT] = "0" * 64
    elif change == "swapped_paths":
        documents[4]["input_paths"][TEST_INPUT] = documents[4]["input_paths"][PRE_ACCESS[0]]
    elif change == "source_path":
        freeze["source_sha256"][TEST_INPUT] = "0" * 64
    elif change == "source_digest":
        freeze["source_sha256"]["ml/scripts/invoice_data_adapter.py"] = "0" * 64
    elif change == "environment":
        freeze["versions"]["python"] = "0.0.0"
    elif change == "metadata_digest":
        freeze["pre_access_sha256"][PRE_ACCESS[3]] = "0" * 64
    elif change == "created_at":
        freeze["created_at"] = "2026-09-01T10:00:00"
    else:
        freeze["unexpected"] = True
    pins = seal(documents)
    with pytest.raises((ValueError, TypeError, PermissionError)):
        claim(documents, pins)
    assert_unclaimed(documents)


@pytest.mark.parametrize("marker", ["authorization_claim.json", "execution_started.json", "failure.json",
                                   "results.pending", "results", "inputs_validated.json"])
def test_existing_attempt_marker_blocks_claim_and_preserves_partial_evidence(documents, no_input_access, marker):
    pins = seal(documents)
    path = documents[2].parent / marker
    if marker in {"results.pending", "results"}:
        path.mkdir()
    else:
        path.write_bytes(b'{"partial":')
    with pytest.raises(FileExistsError):
        claim(documents, pins)
    if path.is_file():
        assert path.read_bytes() == b'{"partial":'


def test_claim_is_one_shot_even_if_authorization_file_changes(documents, no_input_access):
    pins = seal(documents)
    receipt = claim(documents, pins)
    original = receipt.read_bytes()
    documents[1]["authorization_reference"] = "SECOND_SYNTHETIC_CONTRACT_NOT_HUMAN_APPROVAL"
    pins = seal(documents)
    with pytest.raises(FileExistsError):
        claim(documents, pins)
    assert receipt.read_bytes() == original


def test_copied_freeze_cannot_claim_in_new_directory(documents, no_input_access, tmp_path):
    pins = seal(documents)
    copied = tmp_path / "copied"
    copied.mkdir()
    copied_freeze = copied / "freeze.json"
    copied_freeze.write_bytes(documents[2].read_bytes())
    with pytest.raises(ValueError):
        executor.claim_real_evaluation_authorization(copied_freeze, documents[3], **pins)
    assert not (copied / "authorization_claim.json").exists()
    assert_unclaimed(documents)


@pytest.mark.parametrize("document", ["freeze", "authorization"])
@pytest.mark.parametrize("malformation", ["duplicate_key", "nan", "invalid_utf8"])
def test_malformed_json_rejected_before_claim(documents, no_input_access, document, malformation):
    pins = seal(documents)
    index, pin = ((2, "expected_freeze_sha256") if document == "freeze"
                  else (3, "expected_authorization_sha256"))
    content = documents[index].read_bytes()
    if malformation == "duplicate_key":
        content = content[:-1] + b',"schema":"duplicate"}'
    elif malformation == "nan":
        content = content[:-1] + b',"invalid":NaN}'
    else:
        content = b'\xff' + content
    documents[index].write_bytes(content)
    pins[pin] = digest(content)
    if document == "freeze":
        documents[1]["freeze_sha256"] = pins[pin]
        auth_bytes = canonical(documents[1])
        documents[3].write_bytes(auth_bytes)
        pins["expected_authorization_sha256"] = digest(auth_bytes)
    with pytest.raises(ValueError):
        claim(documents, pins)
    assert_unclaimed(documents)


@pytest.mark.parametrize("document_index", [2, 3])
def test_document_tamper_during_validation_is_detected_before_claim(
        documents, no_input_access, monkeypatch, document_index):
    pins = seal(documents)
    original_versions = executor._versions

    def versions_with_tamper():
        documents[document_index].write_bytes(documents[document_index].read_bytes() + b" ")
        return original_versions()

    monkeypatch.setattr(executor, "_versions", versions_with_tamper)
    with pytest.raises(ValueError):
        claim(documents, pins)
    assert_unclaimed(documents)


def test_real_configuration_never_enters_synthetic_executor(tmp_path):
    configuration = executor.real_configuration_contract()
    with pytest.raises(ValueError):
        executor.freeze_configuration(tmp_path / "missing-data", tmp_path / "run", configuration)
    assert not (tmp_path / "run").exists()


def test_equivalent_aware_timestamp_is_valid(documents, no_input_access):
    documents[1]["issued_at"] = "2026-09-01T07:01:00-03:00"
    pins = seal(documents)
    assert claim(documents, pins).is_file()


@pytest.mark.parametrize("future_document", ["freeze", "authorization"])
def test_future_timestamp_does_not_claim(documents, no_input_access, future_document):
    if future_document == "freeze":
        documents[0]["created_at"] = "2999-01-01T00:00:00+00:00"
    documents[1]["issued_at"] = "2999-01-01T00:01:00+00:00"
    pins = seal(documents)
    with pytest.raises((ValueError, PermissionError)):
        claim(documents, pins)
    assert_unclaimed(documents)


def test_authorization_for_other_absolute_run_is_rejected(documents, no_input_access, tmp_path):
    documents[1]["run_dir"] = str(tmp_path / "other-run")
    pins = seal(documents)
    with pytest.raises((ValueError, PermissionError)):
        claim(documents, pins)
    assert_unclaimed(documents)


def test_digest_case_does_not_change_identity_or_rewrite_configuration(documents, no_input_access):
    freeze, authorization, _, authorization_path, _ = documents
    for field in ("model_sha256", "model_metadata_sha256"):
        freeze["configuration"][field] = freeze["configuration"][field].upper()
    for group in ("source_sha256", "pre_access_sha256"):
        freeze[group] = {name: value.upper() for name, value in freeze[group].items()}
    pins = seal(documents)
    for field in ("freeze_sha256", "configuration_sha256"):
        authorization[field] = authorization[field].upper()
    content = canonical(authorization)
    authorization_path.write_bytes(content)
    pins["expected_authorization_sha256"] = digest(content)
    pins = {name: value.upper() if name.startswith("expected_") else value for name, value in pins.items()}
    receipt = json.loads(claim(documents, pins).read_bytes())
    assert receipt["configuration"] == freeze["configuration"]
    assert receipt["configuration_sha256"] == digest(canonical(freeze["configuration"]))


@pytest.mark.parametrize("expires_at", [
    "2026-09-30T11:59:59+00:00",  # Expired when the receipt is requested.
    "2026-09-30T12:00:00+00:00",  # Equality is expired: now must be strictly earlier.
    "2026-09-30T09:00:00-03:00",  # The same expiry instant with another UTC offset.
    "2026-10-01T00:00:00",  # Future but timezone-naive.
    "2026-09-01T10:00:00+00:00",  # Before issuance.
    "2026-09-01T10:01:00+00:00",  # No valid interval after issuance.
])
def test_expired_or_invalid_expiry_rejects_without_claim(documents, no_input_access, expires_at):
    documents[1]["expires_at"] = expires_at
    pins = seal(documents)
    with pytest.raises((ValueError, PermissionError)):
        claim(documents, pins)
    assert_unclaimed(documents)


def test_missing_expiry_rejects_without_claim(documents, no_input_access):
    del documents[1]["expires_at"]
    pins = seal(documents)
    with pytest.raises((ValueError, PermissionError)):
        claim(documents, pins)
    assert_unclaimed(documents)


def test_expiry_one_microsecond_after_now_is_valid(documents, no_input_access):
    documents[1]["expires_at"] = "2026-09-30T09:00:00.000001-03:00"
    pins = seal(documents)
    receipt = json.loads(claim(documents, pins).read_bytes())
    assert receipt["created_at"] == "2026-09-30T12:00:00+00:00"
    assert receipt["authorization"]["expires_at"] == "2026-09-30T09:00:00.000001-03:00"


@pytest.mark.parametrize("document_index", [0, 1])
@pytest.mark.parametrize("scope", [None, "processed_test_only", "physical_shared_raw_for_training"])
def test_missing_or_wrong_access_scope_rejects_without_claim(
        documents, no_input_access, document_index, scope):
    if scope is None:
        del documents[document_index]["access_scope"]
    else:
        documents[document_index]["access_scope"] = scope
    pins = seal(documents)
    with pytest.raises((ValueError, PermissionError)):
        claim(documents, pins)
    assert_unclaimed(documents)


@pytest.mark.parametrize("raw_input", RAW_INPUTS)
@pytest.mark.parametrize("change", ["missing", "redirected", "pre_access_hash"])
def test_raw_allowlist_tamper_rejects_without_input_access(
        documents, no_input_access, raw_input, change):
    freeze = documents[0]
    if change == "missing":
        del documents[4]["input_paths"][raw_input]
    elif change == "redirected":
        documents[4]["input_paths"][raw_input] = documents[4]["input_paths"][TEST_INPUT]
    else:
        freeze["pre_access_sha256"][raw_input] = "0" * 64
    pins = seal(documents)
    with pytest.raises((ValueError, PermissionError)):
        claim(documents, pins)
    assert_unclaimed(documents)


@pytest.mark.parametrize("change", ["missing", "digest"])
def test_real_input_route_source_must_be_pinned(documents, no_input_access, change):
    sources = documents[0]["source_sha256"]
    source = "ml/scripts/invoice_real_inputs.py"
    if change == "missing":
        del sources[source]
    else:
        sources[source] = "0" * 64
    pins = seal(documents)
    with pytest.raises((ValueError, PermissionError)):
        claim(documents, pins)
    assert_unclaimed(documents)
