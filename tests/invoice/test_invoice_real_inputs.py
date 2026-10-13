"""Only generated, external fixtures exercise the explicitly authorized input route."""

import builtins
import copy
import hashlib
import io
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
from invoice_context_fixtures import seal_context, separate
from invoice_history_fixtures import write_history
from sklearn.ensemble import IsolationForest

from ml.scripts import invoice_data_adapter as adapter
from ml.scripts import invoice_final_evaluation as executor
from ml.scripts import invoice_real_inputs as route

ROOT = Path(__file__).resolve().parents[2]
FEATURES = [
    "invoice_amount", "log_invoice_amount", "supplier_age_days", "supplier_frequency",
    "country_frequency", "amount_vs_supplier_mean", "supplier_amount_zscore",
    "department_frequency", "amount_vs_department_mean", "supplier_department_frequency",
    "payment_terms_days", "invoice_type_encoded", "submission_hour_sin", "submission_hour_cos",
    "day_of_week_sin", "day_of_week_cos", "month_sin", "month_cos", "is_weekend",
]
PARAMETERS = {
    "n_estimators": 200, "contamination": 0.22, "random_state": 42, "n_jobs": -1,
    "max_samples": "auto", "max_features": 1.0, "bootstrap": False,
    "warm_start": False, "verbose": 0,
}
PRE_ACCESS = (
    "data/processed/train_features.parquet", "data/processed/val_features.parquet",
    "ml/models/isolation_forest.joblib", "ml/models/model_metadata.json",
)
TEST_INPUT = "data/processed/test_features.parquet"
RAW = ("data/raw/splits.parquet", "data/raw/labels.parquet", "data/raw/invoices.parquet")
INPUTS = (*PRE_ACCESS, TEST_INPUT, *RAW)
SCOPE = "processed_test_and_physical_shared_raw_for_consistency_only"
PROVENANCE = {"source_reconciled": False, "legacy_training_provenance_certified": False,
              "raw_independence_certified": False}
NOW = datetime(2026, 9, 30, 15, tzinfo=timezone.utc)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False,
                      separators=(",", ":")).encode("utf-8")


def digest(value):
    return hashlib.sha256(value).hexdigest()


def forbidden(*args, **kwargs):
    raise AssertionError("Unauthorized input access, fitting, or scoring")


class FixedClock(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW if tz else NOW.replace(tzinfo=None)


@pytest.fixture(autouse=True)
def guard_real_project_inputs(monkeypatch):
    roots = [os.path.normcase(str(ROOT / part)) + os.sep
             for part in ("data", "ml/models", "notebooks", "evidence")]

    def guarded(operation):
        def call(path, *args, **kwargs):
            if isinstance(path, (str, bytes, os.PathLike)):
                name = os.path.normcase(os.path.abspath(os.fsdecode(path)))
                assert not any(name.startswith(root) for root in roots), "Real input access"
                assert not name.endswith(".ipynb"), "Notebook access"
            return operation(path, *args, **kwargs)
        return call

    for owner, name in ((builtins, "open"), (io, "open"), (os, "open"),
                        (pd, "read_parquet"), (joblib, "load")):
        monkeypatch.setattr(owner, name, guarded(getattr(owner, name)))
    monkeypatch.setattr(executor, "datetime", FixedClock)


@pytest.fixture(scope="module")
def generated():
    frames = {}
    for split, count, seed in (("train", 32, 1801), ("val", 12, 2801), ("test", 16, 3801)):
        frame = pd.DataFrame(np.random.default_rng(seed).uniform(0.1, 5, (count, 19)), columns=FEATURES)
        frame["invoice_amount"] *= np.where(np.arange(count) % 3 == 0, -100, 100)
        frame.insert(0, "fraud_type", ["synthetic" if i % 4 == 0 else None for i in range(count)])
        frame.insert(0, "is_fraud", (np.arange(count) % 4 == 0).astype(np.int64))
        frame.insert(0, "split", split)
        frame.insert(0, "invoice_id", [f"generated-{split}-{i:03}" for i in range(count)])
        frames[split] = frame
    # The only fit occurs during preparation, before calls into either production API.
    model = IsolationForest(**PARAMETERS).fit(frames["train"][FEATURES])
    return frames, model


@pytest.fixture
def bundle(tmp_path, generated, monkeypatch):
    assert not tmp_path.resolve().is_relative_to(ROOT)
    frames, model = generated
    project, run = tmp_path / "generated-project", tmp_path / "run"
    for folder in ("data/processed", "data/raw", "ml/models"):
        (project / folder).mkdir(parents=True)
    run.mkdir()
    for split, frame in frames.items():
        frame.iloc[::-1].to_parquet(project / f"data/processed/{split}_features.parquet", index=False)
    combined = pd.concat(list(frames.values()), ignore_index=True)
    combined[["invoice_id", "split"]].to_parquet(project / RAW[0], index=False)
    combined[["invoice_id", "is_fraud", "fraud_type"]].iloc[::-1].to_parquet(project / RAW[1], index=False)
    combined[["invoice_id", "invoice_amount"]].assign(currency="SYN").to_parquet(project / RAW[2], index=False)
    joblib.dump(model, project / PRE_ACCESS[2])
    (project / PRE_ACCESS[3]).write_bytes(canonical({
        "algorithm": "IsolationForest", "feature_count": 19, "features": FEATURES,
        "n_estimators": 200, "contamination": 0.22, "random_state": 42,
    }))
    configuration = {
        "schema": "invoice-real-configuration/1.0", "mode": "real_pre_access",
        "protocol_version": "invoice-academic-evaluation-1.0", "split": "test",
        "features": FEATURES.copy(), "parameters": PARAMETERS.copy(), "legacy_offset": float(model.offset_),
        "model_sha256": digest((project / PRE_ACCESS[2]).read_bytes()),
        "model_metadata_sha256": digest((project / PRE_ACCESS[3]).read_bytes()),
        "budget_percentages": [1, 5, 10], "decision_rule": "selection_at_k",
        "score_rule": "negative_score_samples_descending", "baseline": "invoice_amount_descending_signed",
        "tie_break": "invoice_id_ascending", "preprocessing": "existing_19_features_no_refit",
        "purpose": "academic_retrospective_triage", "provenance": copy.deepcopy(PROVENANCE),
    }
    # Sole test substitution: synthetic identity and offset; all validation still runs.
    monkeypatch.setattr(executor, "real_configuration_contract", lambda: copy.deepcopy(configuration))
    freeze = {
        "schema": "invoice-real-preregistration/1.2", "access_scope": SCOPE,
        "authorized_operation": "evaluate_and_publish_once",
        "created_at": (NOW - timedelta(minutes=2)).isoformat(), "run_dir": str(run),
        "project_root": str(project), "configuration": copy.deepcopy(configuration),
        "versions": executor._versions(),
        "source_sha256": {name: digest((ROOT / name).read_bytes()) for name in executor.REAL_SOURCE_NAMES},
        "pre_access_sha256": {name: digest((project / name).read_bytes()) for name in PRE_ACCESS},
        "input_paths": {name: str(project / name) for name in INPUTS},
    }
    freeze["historical_evidence_sha256"] = write_history(
        project, configuration, freeze["pre_access_sha256"], monkeypatch,
    )
    authorization = {
        "schema": "invoice-real-authorization/1.2", "access_scope": SCOPE, "decision": "approve_once",
        "authorized_operation": "evaluate_and_publish_once",
        "authorized_by": "SYNTHETIC_NOT_A_HUMAN_APPROVAL", "authorization_reference": "GENERATED_FIXTURE",
        "issued_at": (NOW - timedelta(minutes=1)).isoformat(), "expires_at": (NOW + timedelta(hours=1)).isoformat(),
        "freeze_sha256": "", "configuration_sha256": "", "run_dir": str(run), "split": "test",
        "purpose": "academic_retrospective_triage", "provenance_acknowledged": copy.deepcopy(PROVENANCE),
    }
    value = {"project": project, "run": run, "freeze": freeze, "auth": authorization,
             "freeze_path": run / "freeze.json", "auth_path": tmp_path / "authorization.json",
             "receipt_path": run / "authorization_claim.json"}
    value["context"] = separate(freeze, authorization, value["freeze_path"])
    value["context_path"] = run / "context.json"
    seal(value)
    for name in ("fit", "fit_predict", "predict", "score_samples", "decision_function"):
        monkeypatch.setattr(IsolationForest, name, forbidden)
    return value


def seal(bundle):
    bundle["pins"] = seal_context(
        bundle["freeze"], bundle["context"], bundle["auth"], bundle["freeze_path"],
        bundle["context_path"], bundle["auth_path"],
    )

def claim(bundle):
    receipt = executor.claim_real_evaluation_authorization(bundle["freeze_path"], bundle["auth_path"], **bundle["pins"])
    bundle["pins"]["expected_receipt_sha256"] = digest(receipt.read_bytes())


def invoke(bundle, **overrides):
    arguments = {"authorization_path": bundle["auth_path"], "receipt_path": bundle["receipt_path"],
                 "start_input_validation": True, **bundle["pins"], **overrides}
    return route.validate_authorized_inputs(bundle["freeze_path"], **arguments)


def deny_declared_inputs(monkeypatch, bundle):
    declared = {os.path.normcase(os.path.abspath(path)) for path in bundle["context"]["input_paths"].values()}
    for owner, name in ((builtins, "open"), (io, "open"), (os, "open"), (os, "stat"), (os, "lstat")):
        original = getattr(owner, name)

        def checked(path, *args, _original=original, **kwargs):
            if (isinstance(path, (str, bytes, os.PathLike))
                    and os.path.normcase(os.path.abspath(os.fsdecode(path))) in declared):
                forbidden()
            return _original(path, *args, **kwargs)

        monkeypatch.setattr(owner, name, checked)


def assert_not_started(bundle):
    assert not (bundle["run"] / "execution_started.json").exists()
    assert not (bundle["run"] / "inputs_validated.json").exists()


def assert_failed_once(bundle):
    assert (bundle["run"] / "execution_started.json").is_file()
    assert (bundle["run"] / "failure.json").is_file()
    assert not (bundle["run"] / "inputs_validated.json").exists()
    assert not (bundle["run"] / "results").exists()
    with pytest.raises(FileExistsError):
        invoke(bundle)


def test_explicit_validation_route_is_available():
    assert callable(getattr(route, "validate_authorized_inputs", None))


@pytest.mark.parametrize("overrides,error,reason", [
    ({"start_input_validation": False}, PermissionError, "inicio explicito"),
    ({"start_input_validation": 1}, PermissionError, "inicio explicito"),
    ({"authorization_path": None}, PermissionError, "quatro hashes externos"),
    ({"receipt_path": None}, PermissionError, "quatro hashes externos"),
    ({"expected_freeze_sha256": None}, PermissionError, "quatro hashes externos"),
    ({"expected_authorization_sha256": None}, PermissionError, "quatro hashes externos"),
    ({"expected_receipt_sha256": None}, PermissionError, "quatro hashes externos"),
    ({"expected_receipt_sha256": "bad"}, ValueError, "SHA-256 invalido"),
    ({"split": "train"}, PermissionError, "Split solicitado"),
    ({"split": "val"}, PermissionError, "Split solicitado"),
    ({"split": "TEST"}, PermissionError, "Split solicitado"),
    ({"split": None}, PermissionError, "Split solicitado"),
])
def test_invalid_request_rejected_before_any_filesystem_access(bundle, monkeypatch, overrides, error, reason):
    claim(bundle)
    args = {"authorization_path": bundle["auth_path"], "receipt_path": bundle["receipt_path"],
            "start_input_validation": True, **bundle["pins"], **overrides}
    with monkeypatch.context() as context:
        for name in ("open", "resolve", "stat"):
            context.setattr(Path, name, forbidden)
        with pytest.raises(error, match=reason):
            route.validate_authorized_inputs(bundle["freeze_path"], **args)


def test_valid_request_reaches_document_validation_with_complete_context(bundle, monkeypatch):
    claim(bundle)

    def reached_documents(*args, **kwargs):
        assert kwargs["context_path"] == bundle["context_path"]
        assert args[3][3] == bundle["pins"]["expected_context_sha256"]
        raise RuntimeError("Synthetic request reached document validation")

    monkeypatch.setattr(route, "_documents", reached_documents)
    with pytest.raises(RuntimeError, match="reached document validation"):
        invoke(bundle)


def test_input_path_as_receipt_rejected_before_resolution(bundle, monkeypatch):
    claim(bundle)
    invalid = bundle["project"] / TEST_INPUT
    original = Path.resolve

    def resolve(path, *args, **kwargs):
        assert path != invalid, "Input path resolved before receipt binding"
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve)
    with pytest.raises(ValueError, match="Recibo"):
        invoke(bundle, receipt_path=invalid)
    assert_not_started(bundle)


def test_authorized_inputs_preserve_model_and_publish_only_validation(bundle, generated, monkeypatch):
    claim(bundle)
    before = {name: digest((bundle["project"] / name).read_bytes()) for name in INPUTS}
    original_open = io.open

    def require_marker(path, *args, **kwargs):
        if isinstance(path, (str, os.PathLike)) and Path(path) in {bundle["project"] / name for name in INPUTS}:
            assert (bundle["run"] / "execution_started.json").is_file()
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(io, "open", require_marker)
    result = invoke(bundle)
    assert isinstance(result, adapter.AdaptedInvoice)
    pd.testing.assert_frame_equal(result.frame, generated[0]["test"])
    assert result.model.get_params() == PARAMETERS
    assert result.model.offset_ == generated[1].offset_
    assert len(result.model.estimators_) == 200
    for actual, expected in zip(result.model.estimators_, generated[1].estimators_):
        np.testing.assert_array_equal(actual.tree_.__getstate__()["nodes"], expected.tree_.__getstate__()["nodes"])
        np.testing.assert_array_equal(actual.tree_.__getstate__()["values"], expected.tree_.__getstate__()["values"])
    record = result.technical_record
    assert record["input_hashes_sha256"] == before
    assert record["features"] == FEATURES
    assert record["model_fits"] == record["score_calls"] == 0
    assert record["source_rows_consistent"] is True
    for field in ("source_reconciled", "scientific_evidence", "final_evaluation", "evaluation_started"):
        assert record[field] is False
    assert record["data_access_performed"] is record["test_used"] is True
    assert record["provenance"] == PROVENANCE
    assert json.loads((bundle["run"] / "inputs_validated.json").read_bytes()) == record
    assert {path.name for path in bundle["run"].iterdir()} == {
        "freeze.json", "context.json", "authorization_claim.json", "execution_started.json", "inputs_validated.json"}
    assert {name: digest((bundle["project"] / name).read_bytes()) for name in INPUTS} == before
    with pytest.raises(FileExistsError):
        invoke(bundle)


@pytest.mark.parametrize("document", ["freeze_path", "auth_path", "receipt_path", "context_path"])
@pytest.mark.parametrize("fault", ["missing", "tampered"])
def test_missing_or_unpinned_documents_never_access_inputs(bundle, monkeypatch, document, fault):
    claim(bundle)
    path = bundle[document]
    if fault == "missing":
        path.unlink()
    else:
        path.write_bytes(path.read_bytes() + b" ")
    deny_declared_inputs(monkeypatch, bundle)
    with pytest.raises((ValueError, PermissionError, FileNotFoundError)):
        invoke(bundle)
    assert_not_started(bundle)


@pytest.mark.parametrize("field,value", [
    ("freeze_sha256", "0" * 64), ("authorization_sha256", "0" * 64),
    ("configuration_sha256", "0" * 64), ("context_sha256", "0" * 64),
    ("destination", "/other/results"), ("source_reconciled", True),
    ("data_access_performed", True), ("score_calls", 1), ("model_fits", 1),
    ("real_execution_available", False), ("unexpected", True),
])
def test_repinned_receipt_must_match_every_binding(bundle, monkeypatch, field, value):
    claim(bundle)
    receipt = json.loads(bundle["receipt_path"].read_bytes())
    receipt[field] = value
    content = canonical(receipt)
    bundle["receipt_path"].write_bytes(content)
    bundle["pins"]["expected_receipt_sha256"] = digest(content)
    deny_declared_inputs(monkeypatch, bundle)
    with pytest.raises((ValueError, PermissionError)):
        invoke(bundle)
    assert_not_started(bundle)


def test_copied_receipt_cannot_substitute_for_canonical_claim(bundle, tmp_path, monkeypatch):
    claim(bundle)
    copied = tmp_path / "authorization_claim.json"
    copied.write_bytes(bundle["receipt_path"].read_bytes())
    deny_declared_inputs(monkeypatch, bundle)
    with pytest.raises((ValueError, PermissionError)):
        invoke(bundle, receipt_path=copied)
    assert_not_started(bundle)


def test_authorization_expired_after_claim_is_rejected_at_consumption(bundle, monkeypatch):
    claim(bundle)

    class ExpiredClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW + timedelta(hours=1)

    monkeypatch.setattr(executor, "datetime", ExpiredClock)
    deny_declared_inputs(monkeypatch, bundle)
    with pytest.raises((PermissionError, ValueError)):
        invoke(bundle)
    assert_not_started(bundle)


@pytest.mark.parametrize("marker", ["execution_started.json", "inputs_validated.json", "failure.json", "results", "results.pending"])
def test_existing_attempt_blocks_reads_and_preserves_evidence(bundle, monkeypatch, marker):
    claim(bundle)
    existing = bundle["run"] / marker
    existing.write_bytes(b"partial evidence")
    deny_declared_inputs(monkeypatch, bundle)
    with pytest.raises(FileExistsError):
        invoke(bundle)
    assert existing.read_bytes() == b"partial evidence"


@pytest.mark.parametrize("name", PRE_ACCESS)
def test_changed_preaccess_bytes_consume_attempt_without_loading_model(bundle, monkeypatch, name):
    claim(bundle)
    path = bundle["project"] / name
    path.write_bytes(path.read_bytes() + b"changed")
    monkeypatch.setattr(joblib, "load", forbidden)
    original_open = io.open

    def deny_holdout(path, *args, **kwargs):
        if isinstance(path, (str, os.PathLike)):
            assert Path(path) not in {bundle["project"] / item for item in (TEST_INPUT, *RAW)}
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(io, "open", deny_holdout)
    with pytest.raises(ValueError):
        invoke(bundle)
    assert_failed_once(bundle)


@pytest.mark.parametrize("fault", [
    "missing_feature", "feature_order", "nonfinite", "negative_frequency", "bad_label",
    "duplicate_id", "null_id", "wrong_split", "overlap", "incomplete_cohort",
    "raw_split", "raw_label", "raw_fraud_type", "raw_missing_id", "raw_duplicate_id",
    "amount", "amount_nan", "amount_text", "currency_mixed", "currency_null",
])
def test_invalid_processed_or_source_content_consumes_attempt(bundle, fault):
    path = bundle["project"] / TEST_INPUT
    frame = pd.read_parquet(path)
    if fault == "missing_feature":
        frame = frame.drop(columns="month_sin")
    elif fault == "feature_order":
        frame = frame[[*frame.columns[:4], *reversed(FEATURES)]]
    elif fault == "nonfinite":
        frame.loc[0, "month_sin"] = np.inf
    elif fault == "negative_frequency":
        frame.loc[0, "supplier_frequency"] = -1.0
    elif fault == "bad_label":
        frame.loc[0, "is_fraud"] = 2
    elif fault == "duplicate_id":
        frame.loc[0, "invoice_id"] = frame.loc[1, "invoice_id"]
    elif fault == "null_id":
        frame.loc[0, "invoice_id"] = None
    elif fault == "wrong_split":
        frame.loc[0, "split"] = "val"
    elif fault == "overlap":
        frame.loc[0, "invoice_id"] = "generated-train-000"
    elif fault == "incomplete_cohort":
        frame = frame.iloc[1:]
    elif fault.startswith("raw_"):
        path = bundle["project"] / (RAW[0] if fault == "raw_split" else RAW[1])
        frame = pd.read_parquet(path)
        index = frame.index[frame["invoice_id"].eq("generated-test-000")][0]
        if fault == "raw_split":
            frame.loc[index, "split"] = "train"
        elif fault == "raw_label":
            frame.loc[index, "is_fraud"] = 0
            frame.loc[index, "fraud_type"] = None
        elif fault == "raw_fraud_type":
            frame.loc[index, "fraud_type"] = "other_type"
        elif fault == "raw_missing_id":
            frame = frame.drop(index=index)
        else:
            frame = pd.concat([frame, frame.loc[[index]]], ignore_index=True)
    else:
        path = bundle["project"] / RAW[2]
        frame = pd.read_parquet(path)
        index = frame.index[frame["invoice_id"].eq("generated-test-000")][0]
        if fault == "amount":
            frame.loc[index, "invoice_amount"] += 1
        elif fault == "amount_nan":
            frame.loc[index, "invoice_amount"] = np.nan
        elif fault == "amount_text":
            frame["invoice_amount"] = frame["invoice_amount"].astype(str)
        else:
            frame.loc[index, "currency"] = None if fault == "currency_null" else "OTHER"
    frame.to_parquet(path, index=False)
    claim(bundle)
    with pytest.raises((ValueError, TypeError)):
        invoke(bundle)
    assert_failed_once(bundle)


@pytest.mark.parametrize("fault", ["trees", "features", "offset", "parameters", "metadata"])
def test_repinned_model_identity_does_not_bypass_fitted_contract(bundle, generated, monkeypatch, fault):
    model = copy.deepcopy(generated[1])
    if fault == "trees":
        model.estimators_ = model.estimators_[:-1]
    elif fault == "features":
        model.feature_names_in_ = model.feature_names_in_[::-1]
    elif fault == "offset":
        model.offset_ += 0.01
    elif fault == "parameters":
        model.n_jobs = 1
    else:
        metadata = json.loads((bundle["project"] / PRE_ACCESS[3]).read_bytes())
        metadata["features"] = list(reversed(FEATURES))
        (bundle["project"] / PRE_ACCESS[3]).write_bytes(canonical(metadata))
    joblib.dump(model, bundle["project"] / PRE_ACCESS[2])
    config = bundle["freeze"]["configuration"]
    for name, key in ((PRE_ACCESS[2], "model_sha256"), (PRE_ACCESS[3], "model_metadata_sha256")):
        value = digest((bundle["project"] / name).read_bytes())
        config[key] = bundle["freeze"]["pre_access_sha256"][name] = value
        bundle["context"]["input_hashes_sha256"][name] = value
    expected = copy.deepcopy(config)
    monkeypatch.setattr(executor, "real_configuration_contract", lambda: copy.deepcopy(expected))
    # Bind generated history to this fixture so validation reaches the fitted
    # model contract, rather than failing at the independent byte-identity gate.
    bundle["freeze"]["historical_evidence_sha256"] = write_history(
        bundle["project"], config, bundle["freeze"]["pre_access_sha256"], monkeypatch,
    )
    seal(bundle)
    claim(bundle)
    with pytest.raises((ValueError, TypeError)):
        invoke(bundle)
    assert_failed_once(bundle)


@pytest.mark.parametrize("phase", ["development", "consistency", "path_resolution"])
def test_expiry_during_slow_validation_prevents_next_holdout_open(bundle, monkeypatch, phase):
    claim(bundle)
    clock = {"expired": False}

    class AdvancingClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW + timedelta(hours=1) if clock["expired"] else NOW

    monkeypatch.setattr(executor, "datetime", AdvancingClock)
    original_open = io.open

    def reject_expired_read(path, *args, **kwargs):
        if isinstance(path, (str, os.PathLike)) and Path(path) in {bundle["project"] / name for name in (TEST_INPUT, *RAW)}:
            assert not clock["expired"], "TEST/raw reopened after authorization expiry"
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(io, "open", reject_expired_read)
    owner, name = ((adapter, "_load_model") if phase == "development" else
                   (route, "_source_consistency") if phase == "consistency" else (adapter, "_paths"))
    original = getattr(owner, name)

    def expire_after(*args, **kwargs):
        result = original(*args, **kwargs)
        if phase != "path_resolution" or TEST_INPUT in args[1]:
            clock["expired"] = True
        return result

    monkeypatch.setattr(owner, name, expire_after)
    with pytest.raises((PermissionError, ValueError)):
        invoke(bundle)
    assert (bundle["run"] / "execution_started.json").is_file()
    assert (bundle["run"] / "failure.json").is_file()
    assert not (bundle["run"] / "inputs_validated.json").exists()


@pytest.mark.parametrize("fault", ["freeze_schema", "authorization_schema", "missing_expiry", "naive_expiry",
                                  "scope", "configuration", "paths", "prehash", "source_hash"])
def test_repinned_contract_must_still_match_protocol_before_inputs(bundle, monkeypatch, fault):
    claim(bundle)
    receipt = json.loads(bundle["receipt_path"].read_bytes())
    if fault == "freeze_schema":
        bundle["freeze"]["schema"] = "invoice-real-preregistration/1.0"
    elif fault == "authorization_schema":
        bundle["auth"]["schema"] = "invoice-real-authorization/1.0"
    elif fault == "missing_expiry":
        del bundle["auth"]["expires_at"]
    elif fault == "naive_expiry":
        bundle["auth"]["expires_at"] = "2026-09-30T16:00:00"
    elif fault == "scope":
        bundle["auth"]["access_scope"] = "score_everything"
    elif fault == "configuration":
        bundle["freeze"]["configuration"]["features"] = list(reversed(FEATURES))
    elif fault == "paths":
        bundle["context"]["input_paths"][TEST_INPUT] = str(bundle["project"] / PRE_ACCESS[0])
    elif fault == "prehash":
        bundle["freeze"]["pre_access_sha256"][PRE_ACCESS[2]] = "0" * 64
    else:
        bundle["freeze"]["source_sha256"]["ml/scripts/invoice_real_inputs.py"] = "0" * 64
    seal(bundle)
    # Even an internally consistent, re-pinned receipt cannot expand protocol authority.
    receipt.update({"freeze_sha256": bundle["pins"]["expected_freeze_sha256"],
                    "context_sha256": bundle["pins"]["expected_context_sha256"],
                    "authorization_sha256": bundle["pins"]["expected_authorization_sha256"],
                    "configuration_sha256": digest(canonical(bundle["freeze"]["configuration"])),
                    "configuration": bundle["freeze"]["configuration"], "authorization": bundle["auth"]})
    content = canonical(receipt)
    bundle["receipt_path"].write_bytes(content)
    bundle["pins"]["expected_receipt_sha256"] = digest(content)
    deny_declared_inputs(monkeypatch, bundle)
    with pytest.raises((ValueError, TypeError, PermissionError)):
        invoke(bundle)
    assert_not_started(bundle)


def test_competing_exclusive_marker_wins_without_input_access(bundle, monkeypatch):
    claim(bundle)
    write_json = executor._write_json

    def competing_write(path, value):
        if path.name == "execution_started.json":
            path.write_bytes(b"other attempt")
        return write_json(path, value)

    monkeypatch.setattr(executor, "_write_json", competing_write)
    deny_declared_inputs(monkeypatch, bundle)
    with pytest.raises(FileExistsError):
        invoke(bundle)
    assert (bundle["run"] / "execution_started.json").read_bytes() == b"other attempt"
    assert not (bundle["run"] / "failure.json").exists()


@pytest.mark.parametrize("name", [TEST_INPUT, *RAW])
def test_file_changed_during_consistency_is_not_published(bundle, monkeypatch, name):
    claim(bundle)
    original = route._source_consistency

    def alter_after_consistency(*args, **kwargs):
        result = original(*args, **kwargs)
        path = bundle["project"] / name
        path.write_bytes(path.read_bytes() + b"changed")
        return result

    monkeypatch.setattr(route, "_source_consistency", alter_after_consistency)
    with pytest.raises(ValueError):
        invoke(bundle)
    assert_failed_once(bundle)
