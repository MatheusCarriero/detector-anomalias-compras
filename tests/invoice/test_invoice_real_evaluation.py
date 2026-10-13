"""The complete future route is exercised ONLY with generated external fixtures."""

import importlib
import json
import shutil
from datetime import datetime, timedelta

import pandas as pd
import pytest
import test_invoice_real_inputs as shared_fixtures
from sklearn.ensemble import IsolationForest
from test_invoice_real_inputs import (
    FEATURES,
    INPUTS,
    NOW,
    RAW,
    TEST_INPUT,
    canonical,
    claim,
    deny_declared_inputs,
    digest,
    seal,
)

from ml.scripts import invoice_final_evaluation as executor
from ml.scripts import invoice_real_inputs as inputs

ORIGINAL_SCORE = IsolationForest.score_samples
# Register the existing generated fixtures locally without duplicating setup.
bundle = shared_fixtures.bundle
generated = shared_fixtures.generated
guard_real_project_inputs = shared_fixtures.guard_real_project_inputs


def api():
    if importlib.util.find_spec("ml.scripts.invoice_real_evaluation") is None:
        pytest.fail("Missing authorized execution handoff")
    return importlib.import_module("ml.scripts.invoice_real_evaluation")


def run(bundle, **overrides):
    return api().run_authorized_evaluation(
        bundle["freeze_path"], **{
            "authorization_path": bundle["auth_path"], "receipt_path": bundle["receipt_path"],
            "start_evaluation": True, **bundle["pins"], **overrides,
        },
    )


def verify(bundle, result):
    return api().verify_real_bundle(
        result, expected_manifest_sha256=digest((result / "manifest.json").read_bytes()),
        expected_freeze_sha256=bundle["pins"]["expected_freeze_sha256"],
        expected_authorization_sha256=bundle["pins"]["expected_authorization_sha256"],
        expected_context_sha256=bundle["pins"]["expected_context_sha256"],
    )


def test_explicit_authorized_runner_exists():
    assert callable(getattr(api(), "run_authorized_evaluation", None))


def test_completion_time_uses_the_pinned_authorization_not_a_second_read(bundle, monkeypatch):
    claim(bundle)
    monkeypatch.setattr(IsolationForest, "score_samples", ORIGINAL_SCORE)
    result = run(bundle)
    completion_path = bundle["run"] / api().COMPLETION_FILE
    completion = json.loads(completion_path.read_bytes())
    completion["created_at"] = (NOW + timedelta(hours=2)).isoformat()
    completion_path.write_bytes(canonical(completion))
    authorization_path = result / "authorization.json"
    original_read = type(result).read_bytes
    reads = []

    def replaced_on_second_read(path):
        content = original_read(path)
        if path == authorization_path:
            reads.append(path)
            if len(reads) > 1:
                authorization = json.loads(content)
                authorization["expires_at"] = (NOW + timedelta(hours=3)).isoformat()
                return canonical(authorization)
        return content

    monkeypatch.setattr(type(result), "read_bytes", replaced_on_second_read)
    with pytest.raises(ValueError, match="Cronologia da conclusao"):
        verify(bundle, result)
    assert len(reads) == 1


def test_expiry_during_promoted_bundle_check_prevents_completion(bundle, monkeypatch):
    claim(bundle)
    monkeypatch.setattr(IsolationForest, "score_samples", ORIGINAL_SCORE)
    original_verify = api()._verify_real_bundle

    class ExpiredClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW + timedelta(hours=2)

    def expire_after_promoted_check(path, **kwargs):
        record = original_verify(path, **kwargs)
        if path == bundle["run"] / "results":
            monkeypatch.setattr(executor, "datetime", ExpiredClock)
        return record

    monkeypatch.setattr(api(), "_verify_real_bundle", expire_after_promoted_check)
    with pytest.raises(PermissionError, match="expirada"):
        run(bundle)
    assert (bundle["run"] / "failure.json").is_file()
    assert not (bundle["run"] / api().COMPLETION_FILE).exists()


def test_equivalent_uppercase_receipt_publishes_without_rewriting_it(bundle, monkeypatch):
    claim(bundle)
    receipt = json.loads(bundle["receipt_path"].read_bytes())
    for key in ("freeze_sha256", "authorization_sha256", "configuration_sha256"):
        receipt[key] = receipt[key].upper()
    content = canonical(receipt)
    bundle["receipt_path"].write_bytes(content)
    bundle["pins"]["expected_receipt_sha256"] = digest(content)
    monkeypatch.setattr(IsolationForest, "score_samples", ORIGINAL_SCORE)
    result = run(bundle)
    assert (result / "authorization_claim.json").read_bytes() == content
    assert verify(bundle, result)["score_calls"] == 1


def test_complete_generated_run_scores_once_and_publishes_all_budgets(bundle, monkeypatch):
    claim(bundle)
    before = {name: digest((bundle["project"] / name).read_bytes()) for name in INPUTS}
    calls = []

    def score(model, frame):
        assert (bundle["run"] / "evaluation_started.json").is_file()
        assert not (bundle["run"] / "results").exists()
        calls.append(frame.index.tolist())
        return ORIGINAL_SCORE(model, frame)

    monkeypatch.setattr(IsolationForest, "score_samples", score)
    result = run(bundle)
    assert result == bundle["run"] / "results"
    assert len(calls) == 1
    with monkeypatch.context() as context:
        deny_declared_inputs(context, bundle)
        record = verify(bundle, result)
    assert record["configuration"]["features"] == FEATURES
    assert record["provenance"] == {
        "source_reconciled": False, "legacy_training_provenance_certified": False,
        "raw_independence_certified": False,
    }
    assert record["source_reconciled"] is False
    assert record["model_fits_in_executor"] == 0
    assert record["score_calls"] == 1
    assert record["input_hashes_sha256"] == before
    assert record["historical_evidence_sha256"] == bundle["freeze"]["historical_evidence_sha256"]
    for strategy in ("isolation_forest", "invoice_value"):
        summary = record["metrics"][strategy]
        assert summary["rows"] == 16
        assert summary["known_positives"] == 4
        assert [b["percent"] for b in summary["budgets"]] == [1, 5, 10]
        assert [b["k"] for b in summary["budgets"]] == [1, 1, 2]
        for item in record["metrics"]["selection_diagnostics"][strategy]:
            assert sum(map(sum, item["confusion_matrix"])) == 16
            assert item["true_positive"] + item["false_negative"] == 4
            assert sum(g["count"] for g in item["by_fraud_type"].values()) == 16
    assert {name: digest((bundle["project"] / name).read_bytes()) for name in INPUTS} == before
    with pytest.raises(FileExistsError):
        run(bundle)
    assert len(calls) == 1


@pytest.mark.parametrize("override", [
    {"start_evaluation": False}, {"start_evaluation": 1}, {"authorization_path": None},
    {"receipt_path": None}, {"expected_receipt_sha256": None},
    {"context_path": None}, {"expected_context_sha256": None},
    {"expected_freeze_sha256": None}, {"expected_authorization_sha256": None},
    {"split": "train"}, {"split": "val"}, {"split": "TEST"},
])
def test_invalid_request_fails_before_any_input(bundle, monkeypatch, override):
    claim(bundle)
    deny_declared_inputs(monkeypatch, bundle)
    with pytest.raises((ValueError, PermissionError, TypeError)):
        run(bundle, **override)
    assert not (bundle["run"] / "execution_started.json").exists()


@pytest.mark.parametrize("document", ["freeze_path", "auth_path", "receipt_path", "context_path"])
def test_tampered_permission_is_rejected_before_data(bundle, monkeypatch, document):
    claim(bundle)
    with bundle[document].open("ab") as stream:
        stream.write(b" ")
    deny_declared_inputs(monkeypatch, bundle)
    with pytest.raises(ValueError, match="Hash|hash"):
        run(bundle)


def test_expired_permission_cannot_read_shared_raw(bundle, monkeypatch):
    bundle["auth"]["expires_at"] = (NOW - timedelta(seconds=1)).isoformat()
    seal(bundle)
    bundle["pins"]["expected_receipt_sha256"] = "3" * 64
    deny_declared_inputs(monkeypatch, bundle)
    with pytest.raises(PermissionError):
        run(bundle)


def test_incompatible_config_rejected_even_with_matching_document_pins(bundle, monkeypatch):
    bundle["freeze"]["configuration"]["budget_percentages"] = [10]
    seal(bundle)
    bundle["pins"]["expected_receipt_sha256"] = "3" * 64
    deny_declared_inputs(monkeypatch, bundle)
    with pytest.raises(ValueError, match="Configuracao"):
        run(bundle)


@pytest.mark.parametrize("fault", ["split", "order", "labels", "nan", "ids"])
def test_invalid_generated_inputs_consume_attempt_without_scoring(bundle, fault):
    path = bundle["project"] / TEST_INPUT
    frame = pd.read_parquet(path)
    if fault == "split":
        frame.loc[0, "split"] = "val"
    elif fault == "order":
        frame = frame[list(frame.columns[:4]) + list(reversed(FEATURES))]
    elif fault == "labels":
        frame.loc[0, "is_fraud"] = 2
    elif fault == "nan":
        frame.loc[0, "invoice_amount"] = float("nan")
    else:
        frame.loc[0, "invoice_id"] = frame.loc[1, "invoice_id"]
    frame.to_parquet(path, index=False)
    claim(bundle)
    with pytest.raises(ValueError):
        run(bundle)
    assert (bundle["run"] / "failure.json").exists()
    assert not (bundle["run"] / "evaluation_started.json").exists()
    with pytest.raises(FileExistsError):
        run(bundle)


def test_preaccess_hash_mismatch_does_not_reach_shared_raw(bundle, monkeypatch):
    claim(bundle)
    path = bundle["project"] / "data/processed/train_features.parquet"
    path.write_bytes(b"altered synthetic file")
    original = inputs._read_inputs

    def read(paths, *args):
        assert not any(name in RAW or name == TEST_INPUT for name in paths)
        return original(paths, *args)

    monkeypatch.setattr(inputs, "_read_inputs", read)
    with pytest.raises(ValueError, match="Hash"):
        run(bundle)


def test_input_only_attempt_cannot_be_resumed_as_evaluation(bundle):
    claim(bundle)
    inputs.validate_authorized_inputs(
        bundle["freeze_path"], bundle["auth_path"], bundle["receipt_path"],
        start_input_validation=True, **bundle["pins"],
    )
    with pytest.raises(FileExistsError):
        run(bundle)


@pytest.mark.parametrize("name", ["results", "results.pending", "evaluation_started.json", "publication_complete.json"])
def test_existing_destination_blocks_before_data(bundle, monkeypatch, name):
    claim(bundle)
    (bundle["run"] / name).mkdir()
    deny_declared_inputs(monkeypatch, bundle)
    with pytest.raises(FileExistsError):
        run(bundle)


def test_copied_freeze_cannot_change_destination(bundle, tmp_path, monkeypatch):
    claim(bundle)
    other = tmp_path / "copy"
    other.mkdir()
    path = other / "freeze.json"
    path.write_bytes(bundle["freeze_path"].read_bytes())
    bundle["freeze_path"] = path
    deny_declared_inputs(monkeypatch, bundle)
    with pytest.raises(ValueError, match="Destino"):
        run(bundle)


def test_bundle_verification_cannot_publish_or_load_data(bundle, monkeypatch):
    deny_declared_inputs(monkeypatch, bundle)
    with pytest.raises((FileNotFoundError, ValueError)):
        api().verify_real_bundle(
            bundle["run"] / "results", expected_manifest_sha256="1" * 64,
            expected_freeze_sha256="2" * 64, expected_authorization_sha256="3" * 64,
            expected_context_sha256="4" * 64,
        )
    assert not (bundle["run"] / "results").exists()


def test_public_synthetic_evaluator_still_rejects_real_contract(bundle, generated):
    with pytest.raises(ValueError):
        executor.evaluate_frame(generated[1], generated[0]["test"], bundle["freeze"]["configuration"])


@pytest.mark.parametrize("phase", ["after_inputs", "after_score", "before_publish"])
def test_expiry_between_stages_prevents_publication(bundle, monkeypatch, phase):
    claim(bundle)
    monkeypatch.setattr(IsolationForest, "score_samples", ORIGINAL_SCORE)

    class ExpiredClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW + timedelta(hours=2)

    owner, name = {
        "after_inputs": (inputs, "validate_authorized_inputs"),
        "after_score": (executor, "_evaluate_validated_frame"),
        "before_publish": (api(), "_verify_real_bundle"),
    }[phase]
    original = getattr(owner, name)

    def expire(*args, **kwargs):
        result = original(*args, **kwargs)
        monkeypatch.setattr(executor, "datetime", ExpiredClock)
        # Once expired, no further input open/stat is authorized.
        deny_declared_inputs(monkeypatch, bundle)
        return result

    monkeypatch.setattr(owner, name, expire)
    with pytest.raises(PermissionError):
        run(bundle)
    assert not (bundle["run"] / "results").exists()
    assert (bundle["run"] / "failure.json").exists()


def test_complete_pending_bundle_after_failed_publication_is_not_a_final_result(bundle, monkeypatch):
    claim(bundle)
    monkeypatch.setattr(IsolationForest, "score_samples", ORIGINAL_SCORE)
    original = api()._live_inputs
    calls = []

    def fail_last_check(*args, **kwargs):
        calls.append(None)
        if (bundle["run"] / "results.pending" / "manifest.json").exists():
            raise ValueError("Synthetic final input check failed")
        return original(*args, **kwargs)

    monkeypatch.setattr(api(), "_live_inputs", fail_last_check)
    with pytest.raises(ValueError, match="Synthetic final input check"):
        run(bundle)
    assert len(calls) == 3
    assert not (bundle["run"] / "results").exists()
    assert (bundle["run"] / "failure.json").exists()
    deny_declared_inputs(monkeypatch, bundle)
    with pytest.raises(ValueError, match="publicad"):
        verify(bundle, bundle["run"] / "results.pending")
    with pytest.raises(FileExistsError):
        run(bundle)


@pytest.mark.parametrize("remove_failure", [False, True])
def test_failed_staging_manually_promoted_remains_failed(bundle, monkeypatch, remove_failure):
    claim(bundle)
    monkeypatch.setattr(IsolationForest, "score_samples", ORIGINAL_SCORE)
    original = api()._live_inputs

    def fail_last_check(*args, **kwargs):
        if (bundle["run"] / "results.pending" / "manifest.json").exists():
            raise ValueError("Synthetic final input check failed")
        return original(*args, **kwargs)

    monkeypatch.setattr(api(), "_live_inputs", fail_last_check)
    with pytest.raises(ValueError, match="Synthetic final input check"):
        run(bundle)
    assert (bundle["run"] / "failure.json").is_file()
    (bundle["run"] / "results.pending").rename(bundle["run"] / "results")
    if remove_failure:
        (bundle["run"] / "failure.json").unlink()
    deny_declared_inputs(monkeypatch, bundle)
    reason = "Conclusao de publicacao ausente" if remove_failure else "Tentativa falha"
    with pytest.raises(ValueError, match=reason):
        verify(bundle, bundle["run"] / "results")


@pytest.mark.parametrize("mutation", ["evidence", "manifest", "rehashed_evidence", "failure", "run_failure"])
def test_staging_mutation_during_final_input_check_never_publishes(bundle, monkeypatch, mutation):
    claim(bundle)
    monkeypatch.setattr(IsolationForest, "score_samples", ORIGINAL_SCORE)
    original = api()._live_inputs

    def change_staging(*args, **kwargs):
        result = original(*args, **kwargs)
        pending = bundle["run"] / "results.pending"
        if pending.exists():
            evidence = pending / "evidence.json"
            manifest = pending / "manifest.json"
            if mutation in {"failure", "run_failure"}:
                parent = pending if mutation == "failure" else bundle["run"]
                (parent / "failure.json").write_bytes(b'{"original_failure":true}')
            elif mutation == "manifest":
                manifest.write_bytes(manifest.read_bytes() + b" ")
            else:
                evidence.write_bytes(evidence.read_bytes() + b" ")
                if mutation == "rehashed_evidence":
                    value = json.loads(manifest.read_bytes())
                    value["files"]["evidence.json"] = digest(evidence.read_bytes())
                    manifest.write_bytes(canonical(value))
        return result

    monkeypatch.setattr(api(), "_live_inputs", change_staging)
    reason = "Tentativa falha" if mutation in {"failure", "run_failure"} else "Hash|hash"
    with pytest.raises(ValueError, match=reason):
        run(bundle)
    assert not (bundle["run"] / "results").exists()
    assert not (bundle["run"] / "publication_complete.json").exists()
    if mutation == "run_failure":
        assert (bundle["run"] / "failure.json").read_bytes() == b'{"original_failure":true}'


def test_substituted_staging_directory_is_not_promoted_even_with_identical_bytes(bundle, monkeypatch):
    claim(bundle)
    monkeypatch.setattr(IsolationForest, "score_samples", ORIGINAL_SCORE)
    original = api()._live_inputs

    def substitute(*args, **kwargs):
        result = original(*args, **kwargs)
        pending = bundle["run"] / "results.pending"
        if pending.exists():
            moved = bundle["run"] / "original-staging"
            pending.rename(moved)
            shutil.copytree(moved, pending)
        return result

    monkeypatch.setattr(api(), "_live_inputs", substitute)
    with pytest.raises(ValueError, match="Identidade do staging"):
        run(bundle)
    assert not (bundle["run"] / "results").exists()
    assert not (bundle["run"] / "publication_complete.json").exists()


def test_missing_completion_receipt_cannot_certify_publication(bundle, monkeypatch):
    claim(bundle)
    monkeypatch.setattr(IsolationForest, "score_samples", ORIGINAL_SCORE)
    result = run(bundle)
    completion = bundle["run"] / "publication_complete.json"
    assert completion.is_file(), "Successful publication must create its own completion receipt"
    completion.unlink()
    deny_declared_inputs(monkeypatch, bundle)
    with pytest.raises(ValueError, match="Conclusao de publicacao ausente"):
        verify(bundle, result)


@pytest.mark.parametrize("location", ["run", "result"])
def test_failure_marker_invalidates_even_complete_publication(bundle, monkeypatch, location):
    claim(bundle)
    monkeypatch.setattr(IsolationForest, "score_samples", ORIGINAL_SCORE)
    result = run(bundle)
    parent = bundle["run"] if location == "run" else result
    (parent / "failure.json").write_bytes(b"{}")
    deny_declared_inputs(monkeypatch, bundle)
    with pytest.raises(ValueError, match="Tentativa falha"):
        verify(bundle, result)


@pytest.mark.parametrize("mutation", ["evidence", "manifest"])
def test_bytes_changed_during_promotion_do_not_receive_success(bundle, monkeypatch, mutation):
    claim(bundle)
    monkeypatch.setattr(IsolationForest, "score_samples", ORIGINAL_SCORE)
    original = api().Path.rename

    def rename(path, target):
        result = original(path, target)
        if path.name == "results.pending":
            changed = target / ("evidence.json" if mutation == "evidence" else "manifest.json")
            changed.write_bytes(changed.read_bytes() + b" ")
        return result

    monkeypatch.setattr(api().Path, "rename", rename)
    with pytest.raises(ValueError, match="Hash|hash"):
        run(bundle)
    assert (bundle["run"] / "failure.json").is_file()
    assert not (bundle["run"] / "publication_complete.json").exists()


def test_completion_receipt_is_bound_to_the_published_manifest(bundle, monkeypatch):
    claim(bundle)
    monkeypatch.setattr(IsolationForest, "score_samples", ORIGINAL_SCORE)
    result = run(bundle)
    completion_path = bundle["run"] / "publication_complete.json"
    assert completion_path.is_file()
    receipt = json.loads(completion_path.read_bytes())
    assert receipt["manifest_sha256"] == digest((result / "manifest.json").read_bytes())
    assert receipt["destination"] == str(result)
    receipt["manifest_sha256"] = "0" * 64
    completion_path.write_bytes(canonical(receipt))
    deny_declared_inputs(monkeypatch, bundle)
    with pytest.raises(ValueError, match="Conclusao de publicacao divergente"):
        verify(bundle, result)


@pytest.mark.parametrize("field", ["frame", "model", "receipt"])
def test_changed_returned_inputs_rejected_before_scoring(bundle, monkeypatch, field):
    claim(bundle)
    original = inputs.validate_authorized_inputs

    def change(*args, **kwargs):
        adapted = original(*args, **kwargs)
        if field == "frame":
            adapted.frame.loc[0, "invoice_amount"] += 1
        elif field == "model":
            adapted.model.offset_ += 1
        else:
            adapted.technical_record["currency"] = "OTHER"
        return adapted

    monkeypatch.setattr(inputs, "validate_authorized_inputs", change)
    with pytest.raises(ValueError):
        run(bundle)
    assert not (bundle["run"] / "evaluation_started.json").exists()
    assert not (bundle["run"] / "results").exists()


@pytest.mark.parametrize("phase", ["scoring", "publication"])
def test_input_change_after_validation_blocks_publication(bundle, monkeypatch, phase):
    claim(bundle)
    monkeypatch.setattr(IsolationForest, "score_samples", ORIGINAL_SCORE)
    owner, name = (executor, "_evaluate_validated_frame") if phase == "scoring" else (api(), "_verify_real_bundle")
    original = getattr(owner, name)

    def change(*args, **kwargs):
        result = original(*args, **kwargs)
        with (bundle["project"] / TEST_INPUT).open("ab") as stream:
            stream.write(b"changed generated bytes")
        return result

    monkeypatch.setattr(owner, name, change)
    with pytest.raises(ValueError, match="Input alterado"):
        run(bundle)
    assert not (bundle["run"] / "results").exists()
    assert (bundle["run"] / "failure.json").exists()


@pytest.mark.parametrize("field,value", [
    ("source_reconciled", True), ("frame_sha256", "0" * 64),
    ("source_rows_consistent", False), ("score_calls", 2),
])
def test_verifier_rejects_inconsistent_rehashed_evidence(bundle, monkeypatch, field, value):
    claim(bundle)
    monkeypatch.setattr(IsolationForest, "score_samples", ORIGINAL_SCORE)
    result = run(bundle)
    record = json.loads((result / "evidence.json").read_bytes())
    record[field] = value
    content = canonical(record)
    (result / "evidence.json").write_bytes(content)
    manifest = json.loads((result / "manifest.json").read_bytes())
    manifest["files"]["evidence.json"] = digest(content)
    (result / "manifest.json").write_bytes(canonical(manifest))
    deny_declared_inputs(monkeypatch, bundle)
    with pytest.raises(ValueError):
        verify(bundle, result)


def test_publication_without_execution_cannot_create_results(bundle):
    claim(bundle)
    freeze, auth, documents, hashes = inputs._documents(
        bundle["freeze_path"], bundle["auth_path"], bundle["receipt_path"],
        tuple(bundle["pins"][key] for key in (
            "expected_freeze_sha256", "expected_authorization_sha256", "expected_receipt_sha256", "expected_context_sha256",
        )), context_path=bundle["context_path"],
    )
    with pytest.raises(ValueError, match="Recibos de execucao incompletos"):
        api()._publish(freeze, auth, documents, hashes, {}, {})
    assert not (bundle["run"] / "results").exists()
    assert not (bundle["run"] / "results.pending").exists()


@pytest.mark.parametrize("fault", ["extra", "missing", "tampered", "manifest_pin"])
def test_bundle_verification_requires_exact_files_and_external_pin(bundle, monkeypatch, fault):
    claim(bundle)
    monkeypatch.setattr(IsolationForest, "score_samples", ORIGINAL_SCORE)
    result = run(bundle)
    if fault == "extra":
        (result / "extra.json").write_bytes(b"{}")
    elif fault == "missing":
        (result / "evaluation_started.json").unlink()
    elif fault == "tampered":
        (result / "evidence.json").write_bytes(b"{}")
    deny_declared_inputs(monkeypatch, bundle)
    with pytest.raises(ValueError):
        if fault == "manifest_pin":
            api().verify_real_bundle(
                result, expected_manifest_sha256="0" * 64,
                expected_freeze_sha256=bundle["pins"]["expected_freeze_sha256"],
                expected_authorization_sha256=bundle["pins"]["expected_authorization_sha256"],
                expected_context_sha256=bundle["pins"]["expected_context_sha256"],
            )
        else:
            verify(bundle, result)

@pytest.mark.parametrize("phase", ["after_inputs", "after_score", "before_publish"])
def test_context_change_between_stages_blocks_next_input_and_publication(bundle, monkeypatch, phase):
    claim(bundle)
    monkeypatch.setattr(IsolationForest, "score_samples", ORIGINAL_SCORE)
    owner, name = {
        "after_inputs": (inputs, "validate_authorized_inputs"),
        "after_score": (executor, "_evaluate_validated_frame"),
        "before_publish": (api(), "_verify_real_bundle"),
    }[phase]
    original = getattr(owner, name)

    def tamper(*args, **kwargs):
        result = original(*args, **kwargs)
        bundle["context_path"].write_bytes(bundle["context_path"].read_bytes() + b" ")
        deny_declared_inputs(monkeypatch, bundle)
        return result

    monkeypatch.setattr(owner, name, tamper)
    with pytest.raises(ValueError, match="Documento alterado"):
        run(bundle)
    assert not (bundle["run"] / "results").exists()
    assert (bundle["run"] / "failure.json").exists()


def test_published_manifest_and_all_receipts_bind_context_and_destination(bundle, monkeypatch):
    claim(bundle)
    monkeypatch.setattr(IsolationForest, "score_samples", ORIGINAL_SCORE)
    result = run(bundle)
    context_hash = bundle["pins"]["expected_context_sha256"]
    manifest = json.loads((result / "manifest.json").read_bytes())
    assert manifest["context_sha256"] == context_hash
    assert manifest["files"]["context.json"] == context_hash
    assert (result / "freeze.json").read_bytes() == bundle["freeze_path"].read_bytes()
    for name in ("authorization_claim.json", *api().STAGE_FILES, "evidence.json"):
        record = json.loads((result / name).read_bytes())
        assert record["context_sha256"] == context_hash
        assert record["destination"] == str(result)
    deny_declared_inputs(monkeypatch, bundle)
    with pytest.raises(ValueError, match="pins externos"):
        api().verify_real_bundle(
            result, expected_manifest_sha256=digest((result / "manifest.json").read_bytes()),
            expected_freeze_sha256=bundle["pins"]["expected_freeze_sha256"],
            expected_authorization_sha256=bundle["pins"]["expected_authorization_sha256"],
            expected_context_sha256="0" * 64,
        )

@pytest.mark.parametrize("fault", ["model_hash", "missing_input", "extra_input", "invalid_digest"])
def test_rechained_bundle_cannot_contradict_frozen_input_identity(bundle, monkeypatch, fault):
    claim(bundle)
    monkeypatch.setattr(IsolationForest, "score_samples", ORIGINAL_SCORE)
    result = run(bundle)
    validated = json.loads((result / "inputs_validated.json").read_bytes())
    hashes = validated["input_hashes_sha256"]
    if fault == "model_hash":
        hashes["ml/models/isolation_forest.joblib"] = "0" * 64
    elif fault == "missing_input":
        del hashes[RAW[0]]
    elif fault == "extra_input":
        hashes["unapproved.parquet"] = "0" * 64
    else:
        hashes[TEST_INPUT] = "not-a-digest"
    (result / "inputs_validated.json").write_bytes(canonical(validated))
    scored = json.loads((result / "evaluation_started.json").read_bytes())
    scored["inputs_validated_sha256"] = digest((result / "inputs_validated.json").read_bytes())
    (result / "evaluation_started.json").write_bytes(canonical(scored))
    record = json.loads((result / "evidence.json").read_bytes())
    record["input_hashes_sha256"] = hashes.copy()
    record["execution_records_sha256"] = {
        name: digest((result / name).read_bytes()) for name in api().STAGE_FILES
    }
    (result / "evidence.json").write_bytes(canonical(record))
    manifest = json.loads((result / "manifest.json").read_bytes())
    manifest["files"] = {name: digest((result / name).read_bytes()) for name in api().BUNDLE_FILES}
    (result / "manifest.json").write_bytes(canonical(manifest))
    # Freeze/context/auth and their independent pins have NOT changed.
    deny_declared_inputs(monkeypatch, bundle)
    with pytest.raises(ValueError, match="input|Input|SHA"):
        verify(bundle, result)
