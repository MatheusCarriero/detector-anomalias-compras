"""Portable/context boundary: descriptors only, no real data or permission."""

import copy
import json
from pathlib import Path

import pytest
import test_invoice_authorization as shared
from invoice_context_fixtures import canonical, digest, seal_context

from ml.scripts import invoice_final_evaluation as executor

documents = shared.documents
no_input_access = shared.no_input_access
pytestmark = pytest.mark.usefixtures("no_input_access")


@pytest.fixture
def portable(documents):
    freeze, auth, freeze_path, auth_path, context = documents
    context_path = freeze_path.parent / "context.json"
    return freeze, context, auth, freeze_path, context_path, auth_path


def seal(value):
    return seal_context(*value)


def claim(value, pins):
    return executor.claim_real_evaluation_authorization(value[3], value[5], **pins)


def test_portable_freeze_and_bound_context_valid_without_input_io(portable, monkeypatch):
    pins = seal(portable)
    monkeypatch.setattr(executor.joblib, "load", shared.forbidden)
    monkeypatch.setattr(executor.pd, "read_parquet", shared.forbidden)
    frozen = portable[0]
    assert not {"project_root", "run_dir", "input_paths", "destination"} & frozen.keys()
    assert frozen["test_authorized"] is False
    assert all(not Path(name).is_absolute() for name in frozen["input_names"])
    result = json.loads(claim(portable, pins).read_bytes())
    assert result["context_sha256"] == pins["expected_context_sha256"]
    assert result["destination"] == portable[1]["destination"]
    assert result["source_reconciled"] is False
    assert result["data_access_performed"] is False


@pytest.mark.parametrize("document", [0, 1, 2])
def test_document_bytes_tampering_blocked(portable, document):
    pins = seal(portable)
    path = portable[3 + document]
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="Hash|hash"):
        claim(portable, pins)


@pytest.mark.parametrize("field", ["project_root", "run_dir", "destination", "freeze_path"])
def test_context_rebinding_cannot_reuse_authorization(portable, field, tmp_path):
    pins = seal(portable)
    portable[1][field] = str(tmp_path / "another")
    payload = canonical(portable[1])
    portable[4].write_bytes(payload)
    pins["expected_context_sha256"] = digest(payload)
    with pytest.raises((ValueError, PermissionError)):
        claim(portable, pins)


@pytest.mark.parametrize("field", ["freeze_sha256", "context_sha256", "destination"])
def test_authorization_bound_to_other_artifact_or_destination(portable, field):
    pins = seal(portable)
    portable[2][field] = "0" * 64
    payload = canonical(portable[2])
    portable[5].write_bytes(payload)
    pins["expected_authorization_sha256"] = digest(payload)
    with pytest.raises((ValueError, PermissionError)):
        claim(portable, pins)


@pytest.mark.parametrize("field", ["context_path", "expected_context_sha256", "expected_authorization_sha256"])
def test_missing_binding_rejected_before_any_io(portable, monkeypatch, field):
    pins = seal(portable)
    pins[field] = None
    with monkeypatch.context() as guard:
        guard.setattr(Path, "open", shared.forbidden)
        guard.setattr(Path, "resolve", shared.forbidden)
        with pytest.raises(PermissionError):
            claim(portable, pins)


def test_copied_context_is_not_authorization_for_new_location(portable, tmp_path):
    pins = seal(portable)
    copied = tmp_path / "copied"
    copied.mkdir()
    path = copied / "context.json"
    path.write_bytes(portable[4].read_bytes())
    pins["context_path"] = path
    with pytest.raises(ValueError):
        claim(portable, pins)


@pytest.mark.parametrize("fault", ["missing", "absolute_input", "test_hash", "input_path",
                                  "input_hash", "config", "version", "human_permission"])
def test_incompatible_contract_despite_repinning(portable, fault):
    freeze, context = portable[:2]
    if fault == "missing":
        del context["context_id"]
    elif fault == "absolute_input":
        freeze["input_names"][0] = context["input_paths"][freeze["input_names"][0]]
    elif fault == "test_hash":
        context["input_hashes_sha256"][shared.TEST_INPUT] = "a" * 64
    elif fault == "input_path":
        context["input_paths"][shared.TEST_INPUT] = context["input_paths"][shared.PRE_ACCESS[0]]
    elif fault == "input_hash":
        context["input_hashes_sha256"][shared.PRE_ACCESS[0]] = "a" * 64
    elif fault == "config":
        freeze["configuration"]["features"].reverse()
    elif fault == "version":
        freeze["versions"]["python"] = "0.0.0"
    else:
        freeze["test_authorized"] = True
    pins = seal(portable)
    with pytest.raises((ValueError, PermissionError)):
        claim(portable, pins)


def test_context_receipt_is_not_reusable_or_overwritable(portable):
    pins = seal(portable)
    path = claim(portable, pins)
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        claim(portable, pins)
    assert path.read_bytes() == before


def test_portable_bytes_are_independent_of_execution_location(portable):
    freeze, context = portable[:2]
    before = canonical(freeze)
    other_context = copy.deepcopy(context)
    other_context["run_dir"] = "/different/run"
    assert canonical(freeze) == before
    assert canonical(context) != canonical(other_context)

@pytest.mark.parametrize("value", ["relative", "", "../run", "bad\u0000path", "\\ud800"])
@pytest.mark.parametrize("field", ["project_root", "run_dir", "freeze_path", "destination"])
def test_invalid_context_paths_fail_closed(portable, value, field):
    portable[1][field] = value
    pins = seal(portable)
    with pytest.raises((ValueError, PermissionError)):
        claim(portable, pins)


@pytest.mark.parametrize("field", ["schema", "context_id", "input_hashes_sha256", "freeze_path"])
def test_incomplete_context_fails_closed(portable, field):
    del portable[1][field]
    pins = seal(portable)
    with pytest.raises(ValueError):
        claim(portable, pins)


@pytest.mark.parametrize("date", ["2999-01-01T00:00:00+00:00", "2026-08-01T00:00:00+00:00",
                                 "2026-09-01T10:00:00"])
def test_context_chronology_is_bound_to_freeze_and_authorization(portable, date):
    portable[1]["created_at"] = date
    pins = seal(portable)
    with pytest.raises((ValueError, PermissionError)):
        claim(portable, pins)


def test_input_cannot_be_submitted_as_context_before_resolution(portable, monkeypatch):
    pins = seal(portable)
    invalid = Path(portable[1]["input_paths"][shared.TEST_INPUT])
    pins["context_path"] = invalid
    original = Path.resolve

    def resolve(path, *args, **kwargs):
        assert path != invalid, "Input was resolved as a context document"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve)
    with pytest.raises(ValueError, match="Somente documentos"):
        claim(portable, pins)


def test_freeze_and_context_alone_do_not_authorize(portable, monkeypatch):
    pins = seal(portable)
    with monkeypatch.context() as guard:
        guard.setattr(Path, "open", shared.forbidden)
        with pytest.raises(PermissionError):
            executor.claim_real_evaluation_authorization(portable[3], **pins)


def test_same_portable_bytes_require_new_context_and_new_independent_binding(portable, tmp_path):
    pins = seal(portable)
    before = portable[3].read_bytes()
    target = tmp_path / "relocated"
    target.mkdir()
    context = copy.deepcopy(portable[1])
    context.update({"run_dir": str(target), "destination": str(target / "results"),
                    "freeze_path": str(target / "freeze.json"),
                    "context_id": "e225c062-0a62-4e55-bb58-e9356cc20508"})
    (target / "freeze.json").write_bytes(before)
    (target / "context.json").write_bytes(canonical(context))
    pins.update({"context_path": target / "context.json",
                 "expected_context_sha256": digest(canonical(context))})
    with pytest.raises(PermissionError):
        executor.claim_real_evaluation_authorization(target / "freeze.json", portable[5], **pins)
    auth = copy.deepcopy(portable[2])
    auth.update({"context_sha256": pins["expected_context_sha256"], "run_dir": str(target),
                 "destination": context["destination"]})
    auth_path = target / "authorization.json"
    auth_path.write_bytes(canonical(auth))
    pins["expected_authorization_sha256"] = digest(canonical(auth))
    receipt = executor.claim_real_evaluation_authorization(target / "freeze.json", auth_path, **pins)
    assert receipt.parent == target
    assert (target / "freeze.json").read_bytes() == before

@pytest.mark.parametrize("substitute", [0, 1])
def test_control_document_cannot_be_interpreted_as_human_authorization(portable, substitute):
    pins = seal(portable)
    content = canonical(portable[substitute])
    portable[5].write_bytes(content)
    pins["expected_authorization_sha256"] = digest(content)
    with pytest.raises(ValueError, match="autorizacao"):
        claim(portable, pins)
