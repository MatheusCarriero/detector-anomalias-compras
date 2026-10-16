"""Ordinary JSON result writing uses only generated academic evaluation inputs."""

import json

import pytest
import test_invoice_real_inputs as input_fixtures
from sklearn.ensemble import IsolationForest

from ml.scripts import invoice_real_evaluation as runner
from ml.scripts import invoice_real_inputs as inputs

sample = input_fixtures.sample
tables = input_fixtures.tables


def forbidden(*args, **kwargs):
    raise AssertionError("No fit, predict or decision_function during evaluation")


def test_validation_failure_never_evaluates_or_writes(tables, tmp_path, monkeypatch):
    destination = tmp_path / "result.json"
    failure = ValueError("Synthetic source inconsistency")

    def reject_inputs(**kwargs):
        raise failure

    monkeypatch.setattr(inputs, "validate_frames", reject_inputs)
    monkeypatch.setattr(runner.evaluator, "evaluate_frame", forbidden)
    monkeypatch.setattr(runner.evaluator, "_write_json", forbidden)
    with pytest.raises(ValueError) as caught:
        runner.run_final_evaluation(
            destination, **tables, evaluation_id="synthetic-only",
        )
    assert caught.value is failure
    assert not destination.exists()


def test_runner_records_all_budgets_and_limits_without_fit(tables, tmp_path, monkeypatch):
    for name in ("fit", "predict", "decision_function"):
        monkeypatch.setattr(IsolationForest, name, forbidden)
    destination = tmp_path / "result.json"
    result = runner.run_final_evaluation(
        destination, **tables, evaluation_id="synthetic-only",
    )
    assert result == destination
    record = json.loads(result.read_text())
    assert record["evaluation_id"] == "synthetic-only"
    assert record["split"] == "test"  # Generated table, never the actual TEST.
    assert [item["percent"] for item in record["metrics"]["comparisons"]] == [1, 5, 10]
    assert record["metrics"]["isolation_forest"]["rows"] == 10
    assert record["created_at"].endswith("+00:00")
    assert record["source_reconciled"] is False
    assert record["legacy_training_provenance_certified"] is False
    assert record["raw_independence_certified"] is False
    assert record["model_fits_in_executor"] == 0
    assert record["limitations"]
    assert record["features"] == tables["configuration"]["features"]
    original = result.read_bytes()
    monkeypatch.setattr(IsolationForest, "score_samples", forbidden)
    with pytest.raises(FileExistsError):
        runner.run_final_evaluation(
            destination, **tables, evaluation_id="another",
        )
    assert result.read_bytes() == original


def test_invalid_inputs_do_not_create_a_result(tables, tmp_path):
    destination = tmp_path / "result.json"
    tables["frames"]["test"] = tables["frames"]["test"].drop(columns="month_sin")
    with pytest.raises(ValueError):
        runner.run_final_evaluation(destination, **tables, evaluation_id="synthetic")
    assert not destination.exists()


@pytest.mark.parametrize("evaluation_id", [None, "", "   ", 12])
def test_invalid_identification_rejected_before_scoring(tmp_path, evaluation_id, monkeypatch):
    monkeypatch.setattr(inputs, "validate_frames", forbidden)
    with pytest.raises(ValueError):
        runner.run_final_evaluation(
            tmp_path / "result.json", frames=None, model=None, metadata=None,
            splits=None, labels=None, amounts=None, configuration=None, evaluation_id=evaluation_id,
        )


def test_public_runner_validates_then_evaluates_then_writes(tables, tmp_path, monkeypatch):
    events = []
    validated = []
    validate = inputs.validate_frames
    evaluate = runner.evaluator.evaluate_frame
    write = runner.evaluator._write_json

    def tracked_validation(**kwargs):
        result = validate(**kwargs)
        validated.append(result)
        events.append("validate")
        return result

    def tracked_evaluation(model, frame, configuration):
        assert events == ["validate"]
        assert model is validated[0].model
        assert frame is validated[0].frame
        result = evaluate(model, frame, configuration)
        events.append("evaluate")
        return result

    def tracked_write(path, record):
        assert events == ["validate", "evaluate"]
        write(path, record)
        events.append("write")

    monkeypatch.setattr(inputs, "validate_frames", tracked_validation)
    monkeypatch.setattr(runner.evaluator, "evaluate_frame", tracked_evaluation)
    monkeypatch.setattr(runner.evaluator, "_write_json", tracked_write)
    for method in ("fit", "predict", "decision_function"):
        monkeypatch.setattr(IsolationForest, method, forbidden)
    destination = runner.run_final_evaluation(
        tmp_path / "result.json", **tables, evaluation_id="synthetic-order",
    )
    assert events == ["validate", "evaluate", "write"]
    assert json.loads(destination.read_text())["metrics"]["isolation_forest"]["rows"] == 10


@pytest.mark.parametrize("fault", [
    "official_ids", "wrong_split", "labels", "fraud_type", "amounts",
    "currency_mixed", "currency_null", "overlap_train", "overlap_val",
    "feature_order", "metadata", "model_offset", "configuration",
])
def test_public_runner_rejects_invalid_sources_before_evaluation(tables, tmp_path, monkeypatch, fault):
    frame = tables["frames"]["test"]
    target_id = frame.loc[0, "invoice_id"]
    if fault == "official_ids":
        tables["splits"] = tables["splits"].loc[tables["splits"]["invoice_id"].ne(target_id)]
    elif fault == "wrong_split":
        frame.loc[0, "split"] = "val"
    elif fault in ("labels", "fraud_type"):
        source = tables["labels"]
        column = "is_fraud" if fault == "labels" else "fraud_type"
        source.loc[source["invoice_id"].eq(target_id), column] = 1 if fault == "labels" else "OTHER"
    elif fault in ("amounts", "currency_mixed", "currency_null"):
        source = tables["amounts"]
        mask = source["invoice_id"].eq(target_id)
        if fault == "amounts":
            source.loc[mask, "invoice_amount"] += 1
        else:
            source.loc[mask, "currency"] = "OTHER" if fault == "currency_mixed" else None
    elif fault.startswith("overlap_"):
        split = fault.removeprefix("overlap_")
        frame.loc[0, "invoice_id"] = tables["frames"][split].loc[0, "invoice_id"]
    elif fault == "feature_order":
        tables["frames"]["test"] = frame[[*frame.columns[:4], *reversed(frame.columns[4:])]]
    elif fault == "metadata":
        tables["metadata"]["feature_count"] = 18
    elif fault == "model_offset":
        tables["model"].offset_ += 0.1
    else:
        tables["configuration"]["budget_percentages"] = [10]
    monkeypatch.setattr(runner.evaluator, "evaluate_frame", forbidden)
    monkeypatch.setattr(runner.evaluator, "_write_json", forbidden)
    for method in ("fit", "score_samples", "predict", "decision_function"):
        monkeypatch.setattr(IsolationForest, method, forbidden)
    destination = tmp_path / "result.json"
    with pytest.raises(ValueError):
        runner.run_final_evaluation(destination, **tables, evaluation_id="synthetic-invalid")
    assert not destination.exists()


def test_frame_and_model_alone_cannot_bypass_source_validation(tables, tmp_path, monkeypatch):
    monkeypatch.setattr(runner.evaluator, "evaluate_frame", forbidden)
    destination = tmp_path / "result.json"
    with pytest.raises(TypeError):
        runner.run_final_evaluation(
            tables["frames"]["test"], tables["model"], destination,
            configuration=tables["configuration"], evaluation_id="old-call",
        )
    assert not destination.exists()


@pytest.mark.parametrize("missing", ["frames", "metadata", "splits", "labels", "amounts"])
def test_required_sources_cannot_be_omitted(tables, tmp_path, monkeypatch, missing):
    tables.pop(missing)
    monkeypatch.setattr(runner.evaluator, "evaluate_frame", forbidden)
    destination = tmp_path / "result.json"
    with pytest.raises(TypeError):
        runner.run_final_evaluation(destination, **tables, evaluation_id="missing-source")
    assert not destination.exists()
