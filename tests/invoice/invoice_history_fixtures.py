"""Generated historical Invoice evidence for tests only."""

import hashlib
import json

from ml.scripts import invoice_historical_evidence as history

PATHS = tuple(history.HISTORICAL_HASHES)
VALIDATION_IDS = "d" * 64


def write_history(project, configuration, pre_access_hashes, monkeypatch):
    """Write three linked synthetic JSONs and install test-only byte pins."""
    pins = {}
    prior = {}
    validation = {}
    for index, path in enumerate(PATHS):
        document = {
            "protocol_version": (
                "invoice-validation-1.0", "invoice-triage-1.0",
                "invoice-value-comparison-1.0",
            )[index],
            "split": "val", "real_model_fits": 0, "test_used": False,
            "features": list(configuration["features"]),
            "parameters": dict(configuration["parameters"]),
            "input_hashes_sha256": {**pre_access_hashes, **prior},
            "validation_ids_sha256": VALIDATION_IDS,
        }
        if index == 0:
            document["offset"] = configuration["legacy_offset"]
            document["threshold_selected_on_validation"] = False
        else:
            document.update({
                "legacy_offset": configuration["legacy_offset"],
                "threshold_selected": False,
                "budget_percentages": [1, 5, 10],
            })
        if index == 1:
            document["validation"] = {
                "rows": 3, "known_positives": 1,
                "budgets": [{"percent": percent, "k": 1} for percent in (1, 5, 10)],
            }
        if index == 2:
            document.update({
                "budget_selected": False,
                "isolation_forest": validation,
                "invoice_value": {"rows": 3},
                "comparisons": [{"percent": percent} for percent in (1, 5, 10)],
            })
        file = project / path
        file.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
        file.write_bytes(encoded)
        pins[path] = hashlib.sha256(encoded).hexdigest()
        prior[path] = pins[path]
        if index == 1:
            validation = document["validation"]
    monkeypatch.setattr(history, "HISTORICAL_HASHES", pins.copy())
    return pins
