"""Pinned integrity checks for the three historical Invoice JSON records.

This verifies retained bytes and their internal consistency. It does not
certify the provenance of the original training inputs or reconcile sources.
"""

import hashlib
import json
import math
import re
from pathlib import Path

HISTORICAL_HASHES = {
    "ml/experiments/invoice_validation_v1.json":
        "1218ed395095c69dd8d3439e27b7e1416dfeba68b8f1d9d83328e2c2f27e12f9",
    "ml/experiments/invoice_triage_validation_v1.json":
        "ff218d45c54c2376d43b0be46bfda93ba8eb438c8ebd72c395e67fe7cfbdfb3d",
    "ml/experiments/invoice_value_comparison_v1.json":
        "9f47cdb9d70ca0cded04aef63cf4e8c1794118b84533fc880f1cba44ab59beea",
}


PRE_ACCESS_PATHS = (
    "data/processed/train_features.parquet",
    "data/processed/val_features.parquet",
    "ml/models/isolation_forest.joblib",
    "ml/models/model_metadata.json",
)
VERSIONS = (
    "invoice-validation-1.0",
    "invoice-triage-1.0",
    "invoice-value-comparison-1.0",
)
HEX_SHA256 = re.compile(r"[0-9a-fA-F]{64}\Z")


def _digest(value):
    if not isinstance(value, str) or HEX_SHA256.fullmatch(value) is None:
        raise ValueError("invalid SHA-256 digest")
    return value.lower()


def _pairs_without_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_nonfinite(value):
    raise ValueError(f"nonfinite JSON number: {value}")


def _finite_float(value):
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("nonfinite JSON number")
    return parsed


def _strict_equal(actual, expected):
    if type(actual) is not type(expected):
        return False
    if isinstance(actual, dict):
        return actual.keys() == expected.keys() and all(
            _strict_equal(actual[key], expected[key]) for key in actual
        )
    if isinstance(actual, list):
        return len(actual) == len(expected) and all(
            _strict_equal(left, right) for left, right in zip(actual, expected)
        )
    return actual == expected


def _read_pinned(root, relative, expected_digest):
    path = root
    if path.resolve() != path:
        raise ValueError("redirected history root")
    for part in Path(relative).parts:
        path = path / part
        if path.resolve() != path:
            raise ValueError("redirected history path")
    if not path.is_file():
        raise ValueError("missing historical evidence")
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != expected_digest:
        raise ValueError("historical evidence hash mismatch")
    try:
        parsed = json.loads(
            content, object_pairs_hook=_pairs_without_duplicates,
            parse_constant=_reject_nonfinite, parse_float=_finite_float,
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("malformed historical JSON") from exc
    if not isinstance(parsed, dict):
        raise ValueError("historical JSON must be an object")  # noqa: TRY004
    return parsed


def _require_equal(document, field, expected):
    if not _strict_equal(document.get(field), expected):
        raise ValueError(f"historical {field} mismatch")


def verify_historical_evidence(root, expected_hashes, configuration, pre_access_sha256):
    """Verify only the three fixed historical files against independent pins.

    All referenced input digests are compared as recorded values; referenced
    datasets, models, and other paths are never opened by this function.
    """
    if not isinstance(expected_hashes, dict) or set(expected_hashes) != set(HISTORICAL_HASHES):
        raise ValueError("historical hash keys mismatch")
    pins = {name: _digest(value) for name, value in expected_hashes.items()}
    if pins != {name: _digest(value) for name, value in HISTORICAL_HASHES.items()}:
        raise ValueError("historical hashes do not match pinned identities")
    if not isinstance(pre_access_sha256, dict) or set(pre_access_sha256) != set(PRE_ACCESS_PATHS):
        raise ValueError("pre-access hash keys mismatch")
    inputs = {name: _digest(value) for name, value in pre_access_sha256.items()}
    if inputs[PRE_ACCESS_PATHS[2]] != _digest(configuration.get("model_sha256")):
        raise ValueError("configuration model hash mismatch")
    if inputs[PRE_ACCESS_PATHS[3]] != _digest(configuration.get("model_metadata_sha256")):
        raise ValueError("configuration metadata hash mismatch")
    features = configuration.get("features")
    if not isinstance(features, list) or len(features) != 19 or any(
        not isinstance(item, str) or not item for item in features
    ) or len(set(features)) != 19:
        raise ValueError("invalid configured features")
    parameters = configuration.get("parameters")
    offset = configuration.get("legacy_offset")
    if not isinstance(parameters, dict) or not parameters:
        raise ValueError("invalid configured parameters")
    if type(offset) not in (int, float) or not math.isfinite(offset):
        raise ValueError("invalid configured offset")

    documents = []
    root_path = Path(root).absolute()
    for index, path in enumerate(HISTORICAL_HASHES):
        document = _read_pinned(root_path, path, pins[path])
        _require_equal(document, "protocol_version", VERSIONS[index])
        _require_equal(document, "split", "val")
        _require_equal(document, "test_used", False)
        _require_equal(document, "real_model_fits", 0)
        _require_equal(document, "features", features)
        _require_equal(document, "parameters", parameters)
        _require_equal(document, "offset" if index == 0 else "legacy_offset", offset)
        if index == 0:
            if document.get("threshold_selected_on_validation") is not False:
                raise ValueError("historical threshold flag mismatch")
        else:
            _require_equal(document, "threshold_selected", False)
            _require_equal(document, "budget_percentages", [1, 5, 10])
        if index == 2:
            _require_equal(document, "budget_selected", False)
        recorded_inputs = document.get("input_hashes_sha256")
        if not isinstance(recorded_inputs, dict):
            raise ValueError("missing historical input hashes")  # noqa: TRY004
        for name, digest in inputs.items():
            if _digest(recorded_inputs.get(name)) != digest:
                raise ValueError("historical pre-access hash mismatch")
        for previous in tuple(HISTORICAL_HASHES)[:index]:
            if _digest(recorded_inputs.get(previous)) != pins[previous]:
                raise ValueError("historical cross-reference mismatch")
        validation_ids = _digest(document.get("validation_ids_sha256"))
        if documents and validation_ids != _digest(documents[0]["validation_ids_sha256"]):
            raise ValueError("historical validation IDs mismatch")
        documents.append(document)
    triage = documents[1].get("validation")
    comparison = documents[2].get("isolation_forest")
    if not isinstance(triage, dict) or not _strict_equal(comparison, triage):
        raise ValueError("historical triage metrics mismatch")
    for budgets in (triage.get("budgets"), documents[2].get("comparisons")):
        if (not isinstance(budgets, list) or len(budgets) != 3 or
                any(not isinstance(item, dict) for item in budgets) or
                [item.get("percent") for item in budgets] != [1, 5, 10]):
            raise ValueError("historical budget structure mismatch")
    return {
        "sha256": pins.copy(),
        "validation_ids_sha256": _digest(documents[0]["validation_ids_sha256"]),
        "source_reconciled": False,
    }
