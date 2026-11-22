"""Offline tests for the Procurement V2 evidence contract."""

import copy
import hashlib
import json
from datetime import date, timedelta

import pytest

from ml.procurement_v2 import demo, evidence


def _line(po_id, day, price, quantity):
    return {
        "po_id": po_id, "order_date": day,
        "promised_delivery_date": "2025-02-01", "actual_delivery_date": "2025-02-02",
        "supplier_id": "SUP-A", "supplier_name": "Synthetic supplier",
        "supplier_country": "BR", "category": "Materials", "item": "Steel (kg)",
        "business_unit": "Operations", "unit_price": str(price), "quantity": str(quantity),
        "line_total": str(price * quantity), "payment_terms": "Net 30",
        "on_contract": "True", "quality_rejected": "False",
    }


def _prepare(monkeypatch, partial_coverage=False):
    po_id, order_date, occurrence = demo._ALLOWED_OPERATIONS[0]
    rows = [
        _line(
            f"H-{index:02d}",
            (date(2024, 12, 1) + timedelta(days=index - 1)).isoformat(),
            index, 2 * index,
        )
        for index in range(1, 21)
    ]
    rows.append(_line(po_id, order_date, 21, 42))
    monkeypatch.setattr(demo, "_read_source", lambda: copy.deepcopy(rows))

    if partial_coverage:
        original = demo.source_coverage

        def partial():
            coverage = original()
            coverage["start_date"] = "2024-12-01"
            return coverage

        monkeypatch.setattr(demo, "source_coverage", partial)

    request = {
        "contract": demo.CONTRACT_VERSION,
        "source_sha256": demo.SOURCE_SHA256,
        "operation": {"po_id": po_id, "order_date": order_date, "occurrence": occurrence},
    }
    return demo.prepare_operation(request)


def test_create_verify_and_json_round_trip(monkeypatch):
    result = evidence.create_evidence(_prepare(monkeypatch))
    assert result["contract"] == "procurement-evidence/1.0"
    assert result["origin"] == "synthetic"
    assert result["source_reconciled"] is False
    assert result["preparation"]["status"] == "eligible"
    assert len(result["content_sha256"]) == 64
    assert evidence.verify_evidence(result) is True
    json.dumps(result, allow_nan=False)


def test_creation_is_deterministic_and_does_not_mutate_input(monkeypatch):
    prepared = _prepare(monkeypatch)
    before = copy.deepcopy(prepared)
    assert evidence.create_evidence(prepared) == evidence.create_evidence(prepared)
    assert prepared == before


def test_tampered_content_fails_hash_verification(monkeypatch):
    result = evidence.create_evidence(_prepare(monkeypatch))
    result["context"]["unit_price"] = "999"
    with pytest.raises(evidence.EvidenceValidationError, match="hash_mismatch"):
        evidence.verify_evidence(result)


def test_rehashed_but_inconsistent_content_still_fails_contract(monkeypatch):
    result = evidence.create_evidence(_prepare(monkeypatch))
    result["context"]["unit_price"] = "999"
    body = {key: value for key, value in result.items() if key != "content_sha256"}
    canonical = json.dumps(
        body, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    result["content_sha256"] = hashlib.sha256(canonical).hexdigest()
    with pytest.raises(evidence.EvidenceValidationError, match="inconsistent_context_total"):
        evidence.verify_evidence(result)


def test_partial_coverage_is_preserved_as_unavailable(monkeypatch):
    prepared = _prepare(monkeypatch, partial_coverage=True)
    assert prepared["status"] == "unavailable"
    assert prepared["values"] is None
    assert set(prepared["unavailability"].values()) == {"partial_window"}
    result = evidence.create_evidence(prepared)
    assert result["preparation"]["status"] == "unavailable"
    assert evidence.verify_evidence(result) is True


def test_source_identity_cannot_be_replaced(monkeypatch):
    prepared = _prepare(monkeypatch)
    prepared["source"]["source_version"] = "0" * 64
    with pytest.raises(evidence.EvidenceValidationError, match="source_identity"):
        evidence.create_evidence(prepared)


def test_matrix_values_must_match_diagnostic_features(monkeypatch):
    prepared = _prepare(monkeypatch)
    prepared["values"][0] += 1
    with pytest.raises(evidence.EvidenceValidationError, match="feature_value_mismatch"):
        evidence.create_evidence(prepared)


def test_unknown_preparation_fields_are_rejected(monkeypatch):
    prepared = _prepare(monkeypatch)
    prepared["score"] = 0.99
    with pytest.raises(evidence.EvidenceValidationError, match="invalid_structure"):
        evidence.create_evidence(prepared)


def test_invalid_evidence_schema_is_rejected(monkeypatch):
    result = evidence.create_evidence(_prepare(monkeypatch))
    del result["source"]
    with pytest.raises(evidence.EvidenceValidationError, match="invalid_evidence_structure"):
        evidence.verify_evidence(result)
def test_prepare_operation_evidence_wraps_existing_preparation(monkeypatch):
    prepared = _prepare(monkeypatch)
    before = copy.deepcopy(prepared)

    po_id, order_date, occurrence = demo._ALLOWED_OPERATIONS[0]

    request = {
        "contract": demo.CONTRACT_VERSION,
        "source_sha256": demo.SOURCE_SHA256,
        "operation": {
            "po_id": po_id,
            "order_date": order_date,
            "occurrence": occurrence,
        },
    }

    calls = []

    def prepare(value):
        calls.append(copy.deepcopy(value))
        return prepared

    monkeypatch.setattr(demo, "prepare_operation", prepare)

    result = evidence.prepare_operation_evidence(request)

    assert calls == [request]
    assert evidence.verify_evidence(result) is True
    assert result["operation"] == prepared["operation"]
    assert prepared == before