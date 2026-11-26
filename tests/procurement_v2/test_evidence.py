"""Offline tests for the Procurement V2 evidence contract."""

import copy
import csv
import hashlib
import io
import json
from datetime import date, timedelta

import pytest

from ml.procurement_v2 import batch, demo, evidence, features


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


def _prepare(monkeypatch, partial_coverage=False, history_size=20):
    po_id, order_date, occurrence = demo._ALLOWED_OPERATIONS[0]
    rows = [
        _line(
            f"H-{index:02d}",
            (date(2024, 12, 1) + timedelta(days=index - 1)).isoformat(),
            index, 2 * index,
        )
        for index in range(1, history_size + 1)
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

    result = evidence.prepare_operation_evidence(request)

    assert result == evidence.create_evidence(prepared)
    assert evidence.verify_evidence(result) is True
    assert result["operation"] == prepared["operation"]
    assert prepared == before


def _rehash(result):
    body = {key: value for key, value in result.items() if key != "content_sha256"}
    encoded = json.dumps(
        body, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    result["content_sha256"] = hashlib.sha256(encoded).hexdigest()


def _change_feature(prepared, name):
    prepared["diagnostics"]["features"][name] += 1
    if name in batch.MATRIX_FEATURES:
        prepared["values"][batch.MATRIX_FEATURES.index(name)] += 1


@pytest.mark.parametrize("name", features.FEATURE_NAMES)
def test_creation_rejects_joint_feature_and_diagnostic_tampering(monkeypatch, name):
    prepared = _prepare(monkeypatch)
    _change_feature(prepared, name)
    with pytest.raises(evidence.EvidenceValidationError):
        evidence.create_evidence(prepared)


@pytest.mark.parametrize("name", features.FEATURE_NAMES)
def test_rehash_cannot_legitimize_joint_feature_and_diagnostic_tampering(monkeypatch, name):
    result = evidence.create_evidence(_prepare(monkeypatch))
    _change_feature(result["preparation"], name)
    _rehash(result)
    with pytest.raises(evidence.EvidenceValidationError):
        evidence.verify_evidence(result)


def test_rehash_cannot_legitimize_changed_operation_amounts(monkeypatch):
    result = evidence.create_evidence(_prepare(monkeypatch))
    # Internally consistent commercial total, but different from the source operation.
    result["context"]["unit_price"] = "22"
    result["context"]["line_total"] = "924"
    _rehash(result)
    with pytest.raises(evidence.EvidenceValidationError):
        evidence.verify_evidence(result)


def test_rehash_cannot_legitimize_changed_historical_reference(monkeypatch):
    result = evidence.create_evidence(_prepare(monkeypatch))
    result["preparation"]["diagnostics"]["references"]["item"]["unit_price"]["mad"] += 1
    _rehash(result)
    with pytest.raises(evidence.EvidenceValidationError):
        evidence.verify_evidence(result)


def test_valid_evidence_contains_all_nine_canonical_values(monkeypatch):
    result = evidence.create_evidence(_prepare(monkeypatch))
    # Independent expectations for prices 1..20, quantities 2..40 and totals 2*i*i.
    assert result["preparation"]["diagnostics"]["features"] == {
        "price_to_item_median_90d": 2.0,
        "price_iqr_distance_90d": 10.5 / 9.5,
        "item_price_relative_iqr_90d": 9.5 / 10.5,
        "quantity_to_item_median_90d": 2.0,
        "total_to_item_median_90d": 882 / 221,
        "price_to_supplier_item_median_90d": 2.0,
        "supplier_lines_90d": 20,
        "supplier_item_lines_90d": 20,
        "business_unit_lines_90d": 20,
    }
    assert evidence.verify_evidence(json.loads(json.dumps(result))) is True


@pytest.mark.parametrize("history_size", [0, 19, 20])
def test_canonical_history_support_and_insufficient_history(monkeypatch, history_size):
    prepared = _prepare(monkeypatch, history_size=history_size)
    result = evidence.create_evidence(prepared)
    preparation = result["preparation"]
    assert preparation["support"] == dict.fromkeys(
        ("window", "item", "supplier", "supplier_item", "business_unit"), history_size,
    )
    if history_size < 20:
        assert preparation["status"] == "unavailable"
        assert preparation["values"] is None
        assert set(preparation["unavailability"].values()) == {"insufficient_history"}
    else:
        assert preparation["status"] == "eligible"
    assert evidence.verify_evidence(result) is True


@pytest.mark.parametrize("partial", [False, True])
def test_unavailable_evidence_cannot_forge_support_or_reasons(monkeypatch, partial):
    result = evidence.create_evidence(_prepare(monkeypatch, partial_coverage=partial, history_size=19))
    result["preparation"]["support"]["window"] += 1
    _rehash(result)
    with pytest.raises(evidence.EvidenceValidationError, match="canonical_preparation_mismatch"):
        evidence.verify_evidence(result)


def test_consistently_recomputed_evidence_from_false_history_is_rejected(monkeypatch):
    _prepare(monkeypatch)
    false_rows = demo._read_source()
    for row in false_rows[:-1]:
        row["unit_price"] = str(int(row["unit_price"]) * 2)
        row["line_total"] = str(int(row["line_total"]) * 2)
    # An attacker can recompute all statistics/features and the digest, but
    # cannot replace the independently verified source used by the verifier.
    with monkeypatch.context() as attacker:
        attacker.setattr(demo, "_read_source", lambda: copy.deepcopy(false_rows))
        result = evidence.prepare_operation_evidence({
            "contract": demo.CONTRACT_VERSION, "source_sha256": demo.SOURCE_SHA256,
            "operation": {"po_id": "PO-2025-27239", "order_date": "2025-01-23", "occurrence": 1},
        })
    with pytest.raises(evidence.EvidenceValidationError, match="canonical_preparation_mismatch"):
        evidence.verify_evidence(result)


@pytest.mark.parametrize("error", ["source_unavailable", "source_hash", "source_schema"])
@pytest.mark.parametrize("action", ["create", "verify"])
def test_source_failure_is_sanitized_and_has_no_cached_fallback(monkeypatch, error, action):
    prepared = _prepare(monkeypatch)
    result = evidence.create_evidence(prepared)

    def fail():
        raise demo.DemoValidationError(error)

    monkeypatch.setattr(demo, "_read_source", fail)
    with pytest.raises(evidence.EvidenceValidationError, match="^source_verification_failed$"):
        if action == "create":
            evidence.create_evidence(prepared)
        else:
            evidence.verify_evidence(result)


def test_source_bytes_verified_before_parsing_and_every_verification(monkeypatch, tmp_path):
    read_source = demo._read_source
    _prepare(monkeypatch)
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=demo._COLUMNS)
    writer.writeheader()
    writer.writerows(demo._read_source())
    payload = stream.getvalue().encode("utf-8")
    path = tmp_path / "synthetic.csv"
    path.write_bytes(payload)
    # Only the synthetic test source is trusted; no real CSV is accessed.
    monkeypatch.setattr(demo, "SOURCE_SHA256", hashlib.sha256(payload).hexdigest())
    monkeypatch.setattr(demo, "_CSV_PATH", path)
    monkeypatch.setattr(demo, "_read_source", read_source)
    result = evidence.prepare_operation_evidence({
        "contract": demo.CONTRACT_VERSION, "source_sha256": demo.SOURCE_SHA256,
        "operation": {"po_id": "PO-2025-27239", "order_date": "2025-01-23", "occurrence": 1},
    })
    assert evidence.verify_evidence(result) is True
    path.write_bytes(payload + b"tampered")

    def forbidden_parse(_):
        pytest.fail("Untrusted bytes must not reach the CSV parser")

    monkeypatch.setattr(demo, "_parse_csv", forbidden_parse)
    with pytest.raises(evidence.EvidenceValidationError, match="^source_verification_failed$"):
        evidence.verify_evidence(result)


def test_same_day_future_and_out_of_window_rows_do_not_change_evidence(monkeypatch):
    prepared = _prepare(monkeypatch)
    result = evidence.create_evidence(prepared)
    rows = demo._read_source()
    # Invalid numeric fields on excluded dates cannot affect the references.
    rows.extend({"order_date": day} for day in ["2025-01-23", "2025-01-24", "2024-10-24"])
    monkeypatch.setattr(demo, "_read_source", lambda: [
        {"po_id": f"excluded-{index}", **row} for index, row in enumerate(rows)
    ])
    assert evidence.verify_evidence(result) is True
    assert evidence.create_evidence(prepared) == result


def test_unavailable_reasons_cannot_be_replaced_even_when_representations_agree(monkeypatch):
    result = evidence.create_evidence(_prepare(monkeypatch, history_size=19))
    preparation = result["preparation"]
    for name, value in preparation["diagnostics"]["features"].items():
        if value is None:
            preparation["diagnostics"]["unavailability"][name] = "zero_denominator"
            if name in preparation["unavailability"]:
                preparation["unavailability"][name] = "zero_denominator"
    _rehash(result)
    with pytest.raises(evidence.EvidenceValidationError, match="canonical_preparation_mismatch"):
        evidence.verify_evidence(result)


def test_diagnostic_only_unavailability_does_not_block_eligible_vector(monkeypatch):
    prepared = _prepare(monkeypatch)
    rows = demo._read_source()
    for row in rows[:-1]:
        row.update(unit_price="10", quantity="2", line_total="20", supplier_id="OTHER")
    monkeypatch.setattr(demo, "_read_source", lambda: copy.deepcopy(rows))
    result = evidence.prepare_operation_evidence({
        "contract": demo.CONTRACT_VERSION, "source_sha256": demo.SOURCE_SHA256,
        "operation": prepared["operation"],
    })
    preparation = result["preparation"]
    assert preparation["status"] == "eligible"
    assert preparation["values"] == [2.1, 21.0, 0.0, 0, 20]
    assert preparation["diagnostics"]["unavailability"]["price_iqr_distance_90d"] == "zero_iqr"
    assert preparation["diagnostics"]["unavailability"]["price_to_supplier_item_median_90d"] == "insufficient_history"
    assert evidence.verify_evidence(result) is True


def test_invalid_digest_fails_before_source_access(monkeypatch):
    result = evidence.create_evidence(_prepare(monkeypatch))
    result["content_sha256"] = "0" * 64

    def forbidden_read():
        pytest.fail("An invalid envelope must be refused before I/O")

    monkeypatch.setattr(demo, "_read_source", forbidden_read)
    with pytest.raises(evidence.EvidenceValidationError, match="hash_mismatch"):
        evidence.verify_evidence(result)
