"""Write and verify future Supplier Risk experiment evidence.

This module validates caller-supplied predictions and provenance metadata. It
does not read datasets, load models, run training, or attest that the supplied
provenance is true.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0.0"
DOMAIN = "supplier_risk"
TARGET = "Risk_Level"
PROBABILITY_SEMANTICS = "estimated_probability_of_Risk_Level_1"
ALLOWED_SPLITS = ("train", "validation")
PREDICTION_KEYS = {
    "supplier_id",
    "split",
    "y_true",
    "y_pred",
    "probability_class_1",
}
FEATURES_A = [
    "financial_stability_score",
    "on_time_delivery_rate",
    "defect_rate",
    "geopolitical_risk_index",
    "lead_time_days",
    "alternative_suppliers_available",
    "contract_length_months",
    "environmental_compliance",
    "previous_disruptions",
    "supplier_record_count",
]
FEATURES_BY_SCENARIO = {
    "A": FEATURES_A,
    "B": [name for name in FEATURES_A if name != "geopolitical_risk_index"],
    "C": [name for name in FEATURES_A if name != "supplier_record_count"],
    "D": [
        name
        for name in FEATURES_A
        if name not in {"geopolitical_risk_index", "supplier_record_count"}
    ],
}
REQUIRED_METADATA_KEYS = {
    "experiment_name",
    "estimator",
    "scenario",
    "features",
    "parameters",
    "seeds",
    "versions",
    "input_hashes",
    "code_sha256",
    "expected_id_hashes",
}
OPTIONAL_METADATA_KEYS = {"notebook_sha256"}
ENVELOPE_KEYS = {"schema_version", "created_at", "artifact_id", "payload"}
PAYLOAD_KEYS = {
    "domain",
    "target",
    "probability_semantics",
    "metadata",
    "predictions",
    "record_count",
    "id_hashes",
}
SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


class ArtifactValidationError(ValueError):
    """Raised when an experiment record violates the evidence contract."""

    def __init__(self, message: str) -> None:
        # Diagnostics must remain printable even when a field name is malformed.
        safe_message = message.encode("utf-8", errors="backslashreplace").decode("utf-8")
        super().__init__(safe_message)


def _canonical_json(value: Any) -> str:
    try:
        serialized = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        # ensure_ascii=False can retain lone surrogates that UTF-8 cannot encode.
        serialized.encode("utf-8")
        return serialized
    except UnicodeError as error:
        raise ArtifactValidationError(
            "value contains invalid Unicode; valid UTF-8 text is required",
        ) from error
    except (TypeError, ValueError) as error:
        raise ArtifactValidationError(f"value is not strict finite JSON: {error}") from error


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _require_exact_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if type(value) is not dict:
        raise ArtifactValidationError(f"{label} must be an object")
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        unexpected = sorted(actual - expected, key=str)
        raise ArtifactValidationError(
            f"{label} keys are invalid; missing={missing}, unexpected={unexpected}",
        )
    return value


def _require_nonempty_string(value: Any, label: str) -> None:
    if type(value) is not str or not value.strip():
        raise ArtifactValidationError(f"{label} must be a non-empty string")


def _require_sha256(value: Any, label: str) -> None:
    if type(value) is not str or SHA256_PATTERN.fullmatch(value) is None:
        raise ArtifactValidationError(f"{label} must be a SHA-256 hexadecimal string")


def _validate_strict_json(value: Any, label: str) -> None:
    if value is None or type(value) in {str, bool, int}:
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ArtifactValidationError(f"{label} contains a non-finite number")
        return
    if type(value) is list:
        for index, item in enumerate(value):
            _validate_strict_json(item, f"{label}[{index}]")
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise ArtifactValidationError(f"{label} object keys must be strings")
            _validate_strict_json(item, f"{label}.{key}")
        return
    raise ArtifactValidationError(f"{label} contains a non-JSON value")


def _validate_named_map(value: Any, label: str, value_validator) -> None:
    if type(value) is not dict or not value:
        raise ArtifactValidationError(f"{label} must be a non-empty object")
    for name, item in value.items():
        _require_nonempty_string(name, f"{label} name")
        value_validator(item, f"{label}.{name}")


def _validate_seed(value: Any, label: str) -> None:
    if type(value) is not int:
        raise ArtifactValidationError(f"{label} must be an integer and not bool")


def _validate_metadata(metadata: Any, id_hashes: dict[str, str]) -> dict[str, Any]:
    if type(metadata) is not dict:
        raise ArtifactValidationError("metadata must be an object")
    actual_keys = set(metadata)
    allowed_keys = REQUIRED_METADATA_KEYS | OPTIONAL_METADATA_KEYS
    if not REQUIRED_METADATA_KEYS <= actual_keys or not actual_keys <= allowed_keys:
        missing = sorted(REQUIRED_METADATA_KEYS - actual_keys)
        unexpected = sorted(actual_keys - allowed_keys, key=str)
        raise ArtifactValidationError(
            f"metadata keys are invalid; missing={missing}, unexpected={unexpected}",
        )

    _require_nonempty_string(metadata["experiment_name"], "experiment_name")
    _require_nonempty_string(metadata["estimator"], "estimator")

    scenario = metadata["scenario"]
    if type(scenario) is not str or scenario not in FEATURES_BY_SCENARIO:
        raise ArtifactValidationError("scenario must be one of A, B, C, or D")
    if type(metadata["features"]) is not list:
        raise ArtifactValidationError("features must be a list")
    if metadata["features"] != FEATURES_BY_SCENARIO[scenario]:
        raise ArtifactValidationError(f"features do not match scenario {scenario}")

    if type(metadata["parameters"]) is not dict:
        raise ArtifactValidationError("parameters must be a strict JSON object")
    _validate_strict_json(metadata["parameters"], "parameters")
    _validate_named_map(metadata["seeds"], "seeds", _validate_seed)
    _validate_named_map(metadata["versions"], "versions", _require_nonempty_string)
    _validate_named_map(metadata["input_hashes"], "input_hashes", _require_sha256)
    _require_sha256(metadata["code_sha256"], "code_sha256")
    if "notebook_sha256" in metadata:
        _require_sha256(metadata["notebook_sha256"], "notebook_sha256")

    expected_hashes = metadata["expected_id_hashes"]
    if type(expected_hashes) is not dict:
        raise ArtifactValidationError("expected_id_hashes must be an object")
    if set(expected_hashes) != set(id_hashes):
        raise ArtifactValidationError(
            "expected_id_hashes keys must exactly match the splits present",
        )
    for split, expected_hash in expected_hashes.items():
        _require_sha256(expected_hash, f"expected_id_hashes.{split}")
        if expected_hash.lower() != id_hashes[split]:
            raise ArtifactValidationError(
                f"expected_id_hashes mismatch for split {split}",
            )

    return deepcopy(metadata)


def _validate_predictions(predictions: Any) -> tuple[list[dict[str, Any]], dict[str, str]]:
    if type(predictions) is not list:
        raise ArtifactValidationError("predictions must be a list")

    validated = []
    seen_ids = set()
    ids_by_split = {split: [] for split in ALLOWED_SPLITS}
    for index, row in enumerate(predictions):
        row = _require_exact_keys(row, PREDICTION_KEYS, f"predictions[{index}]")
        supplier_id = row["supplier_id"]
        if (
            type(supplier_id) is not str
            or not supplier_id
            or supplier_id != supplier_id.strip()
        ):
            raise ArtifactValidationError(
                f"predictions[{index}].supplier_id must be a non-empty trimmed string",
            )
        if supplier_id in seen_ids:
            raise ArtifactValidationError("supplier_id values must be unique")
        seen_ids.add(supplier_id)

        split = row["split"]
        if split not in ALLOWED_SPLITS:
            raise ArtifactValidationError(
                f"predictions[{index}].split must be train or validation",
            )
        for class_name in ("y_true", "y_pred"):
            if type(row[class_name]) is not int or row[class_name] not in (0, 1):
                raise ArtifactValidationError(
                    f"predictions[{index}].{class_name} must be integer 0 or 1",
                )
        probability = row["probability_class_1"]
        if (
            type(probability) not in {int, float}
            or type(probability) is bool
            or not math.isfinite(probability)
            or not 0 <= probability <= 1
        ):
            raise ArtifactValidationError(
                f"predictions[{index}].probability_class_1 must be finite and in [0, 1]",
            )

        validated.append(deepcopy(row))
        ids_by_split[split].append(supplier_id)

    validated.sort(key=lambda row: (row["split"], row["supplier_id"]))
    id_hashes = {
        split: _sha256(sorted(ids))
        for split, ids in ids_by_split.items()
        if ids
    }
    return validated, id_hashes


def _validate_created_at(value: Any) -> None:
    if type(value) is not str or not value.endswith("Z"):
        raise ArtifactValidationError("created_at must be an ISO-8601 UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(f"{value[:-1]}+00:00")
    except ValueError as error:
        raise ArtifactValidationError("created_at must be a valid UTC timestamp") from error
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ArtifactValidationError("created_at must be UTC")


def _validate_payload(payload: Any) -> dict[str, Any]:
    payload = _require_exact_keys(payload, PAYLOAD_KEYS, "payload")
    if payload["domain"] != DOMAIN:
        raise ArtifactValidationError(f"domain must be {DOMAIN}")
    if payload["target"] != TARGET:
        raise ArtifactValidationError(f"target must be {TARGET}")
    if payload["probability_semantics"] != PROBABILITY_SEMANTICS:
        raise ArtifactValidationError("probability_semantics is invalid")

    predictions, id_hashes = _validate_predictions(payload["predictions"])
    if payload["predictions"] != predictions:
        raise ArtifactValidationError("predictions must be in canonical split/supplier_id order")
    if type(payload["record_count"]) is not int or type(payload["record_count"]) is bool:
        raise ArtifactValidationError("record_count must be an integer")
    if payload["record_count"] != len(predictions):
        raise ArtifactValidationError("record_count does not match predictions")
    stored_id_hashes = payload["id_hashes"]
    if type(stored_id_hashes) is not dict or set(stored_id_hashes) != set(id_hashes):
        raise ArtifactValidationError("id_hashes do not match predictions")
    for split, digest in stored_id_hashes.items():
        _require_sha256(digest, f"id_hashes.{split}")
        if digest.lower() != id_hashes[split]:
            raise ArtifactValidationError("id_hashes do not match predictions")

    metadata = _validate_metadata(payload["metadata"], id_hashes)
    return {
        "domain": DOMAIN,
        "target": TARGET,
        "probability_semantics": PROBABILITY_SEMANTICS,
        "metadata": metadata,
        "predictions": predictions,
        "record_count": len(predictions),
        # Preserve the actual payload representation when verifying its digest.
        "id_hashes": deepcopy(stored_id_hashes),
    }


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ArtifactValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_nonfinite_constant(value: str) -> None:
    raise ArtifactValidationError(f"JSON number must be finite: {value}")


def write_experiment_record(path, predictions, metadata) -> Path:
    """Validate and exclusively write one future Supplier experiment record."""

    destination = Path(path)
    normalized_predictions, id_hashes = _validate_predictions(predictions)
    normalized_metadata = _validate_metadata(metadata, id_hashes)
    payload = {
        "domain": DOMAIN,
        "target": TARGET,
        "probability_semantics": PROBABILITY_SEMANTICS,
        "metadata": normalized_metadata,
        "predictions": normalized_predictions,
        "record_count": len(normalized_predictions),
        "id_hashes": id_hashes,
    }
    artifact_id = _sha256(payload)
    envelope = {
        "schema_version": SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "artifact_id": artifact_id,
        "payload": payload,
    }
    serialized = _canonical_json(envelope)

    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8", newline="") as artifact_file:
        artifact_file.write(serialized)
    return destination


def verify_experiment_record(path) -> dict[str, Any]:
    """Load and validate one Supplier experiment evidence envelope."""

    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8")
        envelope = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_nonfinite_constant,
        )
    except (json.JSONDecodeError, UnicodeError) as error:
        raise ArtifactValidationError(f"invalid strict JSON: {error}") from error

    envelope = _require_exact_keys(envelope, ENVELOPE_KEYS, "envelope")
    if envelope["schema_version"] != SCHEMA_VERSION:
        raise ArtifactValidationError(
            f"schema_version must be {SCHEMA_VERSION}",
        )
    _validate_created_at(envelope["created_at"])
    _require_sha256(envelope["artifact_id"], "artifact_id")
    payload = _validate_payload(envelope["payload"])
    expected_artifact_id = _sha256(payload)
    if envelope["artifact_id"].lower() != expected_artifact_id:
        raise ArtifactValidationError("artifact_id does not match the canonical payload")

    return {
        "schema_version": SCHEMA_VERSION,
        "created_at": envelope["created_at"],
        "artifact_id": envelope["artifact_id"],
        "payload": payload,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    verify_parser = subparsers.add_parser("verify", help="verify one JSON record")
    verify_parser.add_argument("path", type=Path)
    arguments = parser.parse_args(argv)

    if arguments.command == "verify":
        try:
            envelope = verify_experiment_record(arguments.path)
        except (ArtifactValidationError, OSError) as error:
            print(f"verification failed: {error}", file=sys.stderr)
            return 1
        print(envelope["artifact_id"])
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
