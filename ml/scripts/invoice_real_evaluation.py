"""Academic evaluation entry point producing a single ordinary JSON result."""

from datetime import datetime, timezone
from pathlib import Path

from ml.scripts import invoice_final_evaluation as evaluator
from ml.scripts import invoice_real_inputs as inputs


def run_final_evaluation(output_path, *, frames, model, metadata, splits, labels,
                         amounts, configuration, evaluation_id):
    """Validate all explicit inputs before evaluating; never overwrite or fit."""
    destination = Path(output_path)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Resultado existente; nao substituir")
    if not isinstance(evaluation_id, str) or not evaluation_id.strip():
        raise ValueError("Identificacao da avaliacao obrigatoria")
    validated = inputs.validate_frames(
        frames=frames, model=model, metadata=metadata, splits=splits,
        labels=labels, amounts=amounts, configuration=configuration,
    )
    metrics = evaluator.evaluate_frame(validated.model, validated.frame, configuration)
    record = {
        "evaluation_id": evaluation_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "split": configuration["split"], "configuration": configuration,
        "features": list(evaluator.ORDERED_FEATURES), "metrics": metrics,
        "source_reconciled": False, "legacy_training_provenance_certified": False,
        "raw_independence_certified": False, "model_fits_in_executor": 0,
        "confusion_semantics": "rows reference [0,1]; columns [not selected,selected] at global K",
        "limitations": [
            "Retrospective triage; anomaly scores are not fraud probabilities or confirmed fraud.",
            "Reference labels and legacy training provenance are not independently certified.",
            "Temporal availability and operational usefulness have not been demonstrated.",
        ],
    }
    evaluator._write_json(destination, record)
    return destination
