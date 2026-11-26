"""Deterministic evidence envelope for Procurement V2 preparation.

Creation and verification rebuild preparation through the demo adapter using
its fixed, hash-pinned local CSV. No supplied historical aggregate is trusted.
This requires the source to be available, but never loads a model, calculates
scores, accesses the network or certifies the source's real-world provenance.
"""

import copy
import hashlib
import json
import math
import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from ml.procurement_v2 import batch, demo, features

CONTRACT_VERSION = "procurement-evidence/1.0"
_PREPARATION_KEYS = (
    "contract", "feature_contract", "matrix_contract", "status", "cutoff_date",
    "window", "coverage", "support", "feature_names", "values",
    "unavailability", "diagnostics",
)
_PREPARED_KEYS = ("source", "operation", "context", *_PREPARATION_KEYS)
_EVIDENCE_KEYS = (
    "contract", "kind", "origin", "source_reconciled", "integrity", "source",
    "operation", "context", "preparation", "limitations", "content_sha256",
)
_CONTEXT_KEYS = (
    "supplier_id", "supplier_name", "supplier_country", "category", "item",
    "business_unit", "unit_price", "quantity", "line_total",
)
_CONTEXT_TEXT_KEYS = _CONTEXT_KEYS[:6]
_SUPPORT_KEYS = ("window", "item", "supplier", "supplier_item", "business_unit")
_REFERENCE_METRICS = ("unit_price", "quantity", "line_total")
_STATISTIC_KEYS = ("q1", "median", "q3", "iqr", "mad")
_INTEGRITY = {
    "algorithm": "sha256",
    "scope": "canonical_json_without_content_sha256",
    "authenticity": "not_attested",
}
_LIMITATIONS = [
    "synthetic_source",
    "source_reconciled_false",
    "no_model_score_or_fraud_probability",
    "sha256_provides_integrity_not_authenticity",
]
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class EvidenceValidationError(ValueError):
    """Invalid evidence contract; the message contains only a stable error code."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _keys(value, expected, code="invalid_structure"):
    if type(value) is not dict or set(value) != set(expected):
        raise EvidenceValidationError(code)


def _text(value, code="invalid_text"):
    if (type(value) is not str or not value or value.strip() != value
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise EvidenceValidationError(code)


def _number(value, code="invalid_number"):
    if type(value) not in (int, float):
        raise EvidenceValidationError(code)
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise EvidenceValidationError(code)


def _day(value):
    if type(value) is not str or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
        raise EvidenceValidationError("invalid_date")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise EvidenceValidationError("invalid_date") from None


def _decimal_text(value):
    _text(value, "invalid_context")
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise EvidenceValidationError("invalid_context") from None
    if not number.is_finite() or number <= 0:
        raise EvidenceValidationError("invalid_context")
    return number


def _validate_context(context):
    _keys(context, _CONTEXT_KEYS, "invalid_context")
    for key in _CONTEXT_TEXT_KEYS:
        _text(context[key], "invalid_context")
    if type(context["quantity"]) is not int or context["quantity"] <= 0:
        raise EvidenceValidationError("invalid_context")
    price = _decimal_text(context["unit_price"])
    total = _decimal_text(context["line_total"])
    try:
        consistent = price * context["quantity"] == total
    except InvalidOperation:
        consistent = False
    if not consistent:
        raise EvidenceValidationError("inconsistent_context_total")


def _validate_statistics(value):
    if value is None:
        return
    _keys(value, _STATISTIC_KEYS, "invalid_references")
    for number in value.values():
        _number(number, "invalid_references")
        if number < 0:
            raise EvidenceValidationError("invalid_references")


def _validate_prepared(prepared):
    """Validate the exact output contract of demo.prepare_operation()."""
    _keys(prepared, _PREPARED_KEYS)
    if prepared["contract"] != demo.CONTRACT_VERSION:
        raise EvidenceValidationError("preparation_contract")
    if prepared["feature_contract"] != features.CONTRACT_VERSION:
        raise EvidenceValidationError("feature_contract")
    if prepared["matrix_contract"] != batch.BATCH_VERSION:
        raise EvidenceValidationError("matrix_contract")
    if prepared["source"] != demo.source_identity():
        raise EvidenceValidationError("source_identity")

    try:
        identity = demo.validate_request({
            "contract": demo.CONTRACT_VERSION,
            "source_sha256": demo.SOURCE_SHA256,
            "operation": prepared["operation"],
        })
    except (demo.DemoValidationError, KeyError, TypeError):
        raise EvidenceValidationError("operation_identity") from None
    if identity != prepared["operation"]:
        raise EvidenceValidationError("operation_identity")
    _validate_context(prepared["context"])

    cutoff = _day(prepared["cutoff_date"])
    if prepared["cutoff_date"] != prepared["operation"]["order_date"]:
        raise EvidenceValidationError("cutoff_mismatch")
    try:
        expected_start = (cutoff - timedelta(days=features.WINDOW_DAYS)).isoformat()
    except OverflowError:
        raise EvidenceValidationError("invalid_date") from None
    expected_window = {"start": expected_start, "end": cutoff.isoformat(), "end_exclusive": True}
    _keys(prepared["window"], expected_window, "invalid_window")
    if prepared["window"] != expected_window:
        raise EvidenceValidationError("invalid_window")

    coverage = prepared["coverage"]
    _keys(coverage, ("start_date", "end_date", "complete", "status"), "invalid_coverage")
    coverage_start, coverage_end = _day(coverage["start_date"]), _day(coverage["end_date"])
    if coverage_start > coverage_end or type(coverage["complete"]) is not bool:
        raise EvidenceValidationError("invalid_coverage")
    try:
        complete = (
            coverage["complete"]
            and coverage_start <= cutoff - timedelta(days=features.WINDOW_DAYS)
            and coverage_end >= cutoff - timedelta(days=1)
        )
    except OverflowError:
        raise EvidenceValidationError("invalid_coverage") from None
    if coverage["status"] != ("complete" if complete else "partial_window"):
        raise EvidenceValidationError("coverage_status")

    _keys(prepared["support"], _SUPPORT_KEYS, "invalid_support")
    if any(type(value) is not int or value < 0 for value in prepared["support"].values()):
        raise EvidenceValidationError("invalid_support")
    if prepared["feature_names"] != list(batch.MATRIX_FEATURES):
        raise EvidenceValidationError("matrix_feature_order")

    diagnostics = prepared["diagnostics"]
    _keys(diagnostics, ("feature_names", "features", "unavailability", "references"), "invalid_diagnostics")
    if diagnostics["feature_names"] != list(features.FEATURE_NAMES):
        raise EvidenceValidationError("diagnostic_feature_order")
    diagnostic_features, reasons = diagnostics["features"], diagnostics["unavailability"]
    _keys(diagnostic_features, features.FEATURE_NAMES, "invalid_diagnostics")
    _keys(reasons, features.FEATURE_NAMES, "invalid_diagnostics")
    for name in features.FEATURE_NAMES:
        value, reason = diagnostic_features[name], reasons[name]
        if value is None:
            _text(reason, "invalid_diagnostics")
        else:
            _number(value, "invalid_diagnostics")
            if reason is not None:
                raise EvidenceValidationError("invalid_diagnostics")

    references = diagnostics["references"]
    _keys(references, ("item", "supplier_item"), "invalid_references")
    _keys(references["item"], _REFERENCE_METRICS, "invalid_references")
    _keys(references["supplier_item"], ("unit_price",), "invalid_references")
    for statistic in (*references["item"].values(), references["supplier_item"]["unit_price"]):
        _validate_statistics(statistic)

    unavailable = {
        name: reasons[name] for name in batch.MATRIX_FEATURES
        if diagnostic_features[name] is None
    }
    if prepared["unavailability"] != unavailable:
        raise EvidenceValidationError("matrix_unavailability")
    status = "unavailable" if unavailable else "eligible"
    if prepared["status"] != status:
        raise EvidenceValidationError("preparation_status")
    values = prepared["values"]
    if status == "unavailable":
        if values is not None:
            raise EvidenceValidationError("unavailable_values")
    else:
        if type(values) is not list or len(values) != len(batch.MATRIX_FEATURES):
            raise EvidenceValidationError("invalid_values")
        expected_values = [diagnostic_features[name] for name in batch.MATRIX_FEATURES]
        for value in values:
            _number(value, "invalid_values")
        if values != expected_values:
            raise EvidenceValidationError("feature_value_mismatch")

    # The envelope carries aggregates, not historical rows. Agreement between
    # its two feature representations (or a fresh digest) cannot prove the
    # mathematics. Reuse the adapter's source verification, compound identity,
    # temporal selection and P5.6 calculation without duplicating formulas.
    try:
        canonical = demo.prepare_operation({
            "contract": demo.CONTRACT_VERSION,
            "source_sha256": demo.SOURCE_SHA256,
            "operation": dict(identity),
        })
    except demo.DemoValidationError:
        raise EvidenceValidationError("source_verification_failed") from None
    # Compare the complete preparation, including the four diagnostic-only
    # features, references, context, support and unavailable/partial results.
    # Canonical JSON also distinguishes booleans from numeric counts.
    if _sha256(prepared) != _sha256(canonical):
        raise EvidenceValidationError("canonical_preparation_mismatch")


def _sha256(value):
    try:
        content = json.dumps(
            value, sort_keys=True, ensure_ascii=False,
            separators=(",", ":"), allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError):
        raise EvidenceValidationError("non_json_evidence") from None
    return hashlib.sha256(content).hexdigest()


def create_evidence(prepared):
    """Create evidence after rebuilding preparation from the trusted local CSV.

    Requires the fixed source; unavailable/corrupt source is a validation error,
    not a statistically unavailable operation. No model or inference is used.
    """
    _validate_prepared(prepared)
    result = {
        "contract": CONTRACT_VERSION,
        "kind": "prepared_purchase_features",
        "origin": "synthetic",
        "source_reconciled": False,
        "integrity": copy.deepcopy(_INTEGRITY),
        "source": copy.deepcopy(prepared["source"]),
        "operation": copy.deepcopy(prepared["operation"]),
        "context": copy.deepcopy(prepared["context"]),
        "preparation": {key: copy.deepcopy(prepared[key]) for key in _PREPARATION_KEYS},
        "limitations": list(_LIMITATIONS),
    }
    result["content_sha256"] = _sha256(result)
    return result


def verify_evidence(evidence):
    """Verify integrity and canonical source-backed preparation; return True.

    SHA-256 detects changes to the canonical payload. It is not a digital
    signature and does not authenticate who created the evidence.
    Even a correctly rehashed payload must match a fresh preparation from the
    adapter's fixed, independently hash-pinned source. No cached fallback is used.
    """
    _keys(evidence, _EVIDENCE_KEYS, "invalid_evidence_structure")
    if evidence["contract"] != CONTRACT_VERSION:
        raise EvidenceValidationError("evidence_contract")
    if evidence["kind"] != "prepared_purchase_features":
        raise EvidenceValidationError("evidence_kind")
    if evidence["origin"] != "synthetic" or evidence["source_reconciled"] is not False:
        raise EvidenceValidationError("evidence_provenance")
    if evidence["integrity"] != _INTEGRITY:
        raise EvidenceValidationError("integrity_contract")
    if evidence["limitations"] != _LIMITATIONS:
        raise EvidenceValidationError("evidence_limitations")

    digest = evidence["content_sha256"]
    if type(digest) is not str or _SHA256.fullmatch(digest) is None:
        raise EvidenceValidationError("invalid_digest")
    body = {key: copy.deepcopy(value) for key, value in evidence.items() if key != "content_sha256"}
    if _sha256(body) != digest:
        raise EvidenceValidationError("hash_mismatch")

    preparation = evidence["preparation"]
    _keys(preparation, _PREPARATION_KEYS, "invalid_preparation_structure")
    prepared = {
        "source": evidence["source"],
        "operation": evidence["operation"],
        "context": evidence["context"],
        **copy.deepcopy(preparation),
    }
    _validate_prepared(prepared)
    return True

def prepare_operation_evidence(request):
    prepared = demo.prepare_operation(request)
    return create_evidence(prepared)
