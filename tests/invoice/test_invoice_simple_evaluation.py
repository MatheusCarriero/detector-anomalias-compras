"""Simple scientific configuration without execution documents."""

import json

import pytest

from ml.scripts import invoice_final_evaluation as evaluator
from ml.scripts import invoice_real_evaluation as runner
from ml.scripts import invoice_real_inputs as inputs


def test_configuration_accepts_explicit_partition_without_execution_documents():
    configuration = evaluator.configuration_contract(-0.5, split="test")
    assert configuration["split"] == "test"
    assert set(configuration) == {"split", "features", "parameters", "legacy_offset",
                                 "budget_percentages", "decision_rule"}


def test_existing_result_is_preserved_before_scoring(tmp_path, monkeypatch):
    destination = tmp_path / "result.json"
    destination.write_text('{"original":true}', encoding="utf-8")
    run = getattr(runner, "run_final_evaluation", None)
    assert callable(run), "Explicit academic runner required"

    def forbidden(*args, **kwargs):
        raise AssertionError("Existing output must fail before validation or scoring")

    monkeypatch.setattr(inputs, "validate_frames", forbidden)
    monkeypatch.setattr(evaluator, "evaluate_frame", forbidden)
    with pytest.raises(FileExistsError):
        run(destination, frames=None, model=None, metadata=None, splits=None,
            labels=None, amounts=None, configuration=None, evaluation_id="synthetic")
    assert json.loads(destination.read_text()) == {"original": True}
