"""Read-only Procurement V2 preparation, independent of model loading/scoring.

Public entry points take no paths, CSV contents or historical statistics. Only
the fixed hash-pinned synthetic source and catalogue below are authorized.
Prices/totals in commercial context retain the CSV decimal text, not BRL.
Availability at order time remains a simulation assumption, not evidence of
pre-approval availability in a real procurement process.
"""

import csv
import hashlib
import io
import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

from ml.procurement_v2 import features
from ml.procurement_v2.batch import BATCH_VERSION, MATRIX_FEATURES

CONTRACT_VERSION = "procurement-demo/1.0"
# Independent trust pin from P5.14; never derive it from the runtime CSV.
SOURCE_SHA256 = "fba22a467e5dd800a0af960930d2ca5e2ecbd9d2bc747e37304867d8d031ae21"
_CSV_PATH = Path(__file__).resolve().parents[2] / "data/external/procurement_spend/purchase_orders.csv"
_SOURCE_LIMIT = 16 * 1024 * 1024  # Authorized source: 7,712,381 bytes.
_COLUMNS = (
    "po_id", "order_date", "promised_delivery_date", "actual_delivery_date",
    "supplier_id", "supplier_name", "supplier_country", "category", "item",
    "business_unit", "unit_price", "quantity", "line_total", "payment_terms",
    "on_contract", "quality_rejected",
)
_COMMERCIAL_FIELDS = (
    "supplier_id", "supplier_name", "supplier_country", "category", "item",
    "business_unit", "unit_price", "quantity", "line_total",
)
# First six: P5.14 metadata verification.fixed_references, occurrence 1 each.
# Last: first Machinery line in 2025 (date, ID order) with 0 < item support < 20.
# PO-2025-28121: Precision Jig Set, 17 prior lines in [2024-10-06, 2025-01-04).
# This is a demonstration catalogue, not a representative or fraud-labelled sample.
_ALLOWED_OPERATIONS = (
    ("PO-2025-27239", "2025-01-23", 1),
    ("PO-2025-34347", "2025-07-15", 1),
    ("PO-2025-40702", "2025-12-24", 1),
    ("PO-2026-40862", "2026-01-16", 1),
    ("PO-2026-43834", "2026-03-11", 1),
    ("PO-2026-47088", "2026-06-17", 1),
    ("PO-2025-28121", "2025-01-04", 1),
)


class DemoValidationError(ValueError):
    """Sanitized validation code, without source values or filesystem paths."""

    def __init__(self, code):
        self.code = code
        super().__init__(code)


def source_identity():
    """Fresh metadata for the approved synthetic source, without file access."""
    return {
        "source_id": "procurement-spend", "source_version": SOURCE_SHA256,
        "entity_namespace": "procurement-spend-synthetic", "origin": "synthetic",
        "monetary_unit": "unspecified_source_unit",
        "temporal_assumption": "available_at_order_no_revisions",
    }


def source_coverage():
    """P5.14's declared complete coverage; not inferred from observed dates."""
    source = source_identity()
    return {**{k: source[k] for k in ("source_id", "source_version", "entity_namespace")},
            "start_date": "2023-01-01", "end_date": "2026-06-30", "complete": True}


def _day(value):
    if type(value) is not str or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) is None:
        raise DemoValidationError("invalid_date")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise DemoValidationError("invalid_date") from None


def validate_request(request):
    """Validate the exact preparation request before I/O; return a fresh identity.

    Required keys: contract, source_sha256, operation. operation contains exactly
    po_id, order_date and positive integer occurrence. No user-supplied features,
    amounts, model identifiers, paths or alternate source hashes are accepted.
    """
    if type(request) is not dict or set(request) != {"contract", "source_sha256", "operation"}:
        raise DemoValidationError("invalid_request")
    if request["contract"] != CONTRACT_VERSION or request["source_sha256"] != SOURCE_SHA256:
        raise DemoValidationError("request_contract")
    op = request["operation"]
    if type(op) is not dict or set(op) != {"po_id", "order_date", "occurrence"}:
        raise DemoValidationError("invalid_identity")
    if type(op["po_id"]) is not str or type(op["occurrence"]) is not int or op["occurrence"] < 1:
        raise DemoValidationError("invalid_identity")
    _day(op["order_date"])
    if (op["po_id"], op["order_date"], op["occurrence"]) not in _ALLOWED_OPERATIONS:
        raise DemoValidationError("operation_not_allowed")
    return dict(op)


def _parse_csv(payload):
    # Called only after the independently pinned SHA-256 has matched.
    try:
        reader = csv.DictReader(io.StringIO(payload.decode("utf-8-sig"), newline=""), strict=True)
        if tuple(reader.fieldnames or ()) != _COLUMNS:
            raise DemoValidationError("source_schema")
        rows = []
        for row in reader:
            if set(row) != set(_COLUMNS) or any(type(v) is not str for v in row.values()):
                raise DemoValidationError("source_schema")
            _day(row["order_date"])
            if not "2023-01-01" <= row["order_date"] <= "2026-06-30":
                raise DemoValidationError("source_coverage")
            rows.append(row)
        if not rows:
            raise DemoValidationError("source_empty")
        return rows
    except (UnicodeError, csv.Error):
        raise DemoValidationError("source_format") from None


def _read_source():
    try:
        # Reject redirects, including parent symlinks/junctions. No path arguments.
        if _CSV_PATH.resolve() != _CSV_PATH.absolute():
            raise DemoValidationError("source_path")
        with _CSV_PATH.open("rb") as stream:
            payload = stream.read(_SOURCE_LIMIT + 1)
    except OSError:
        raise DemoValidationError("source_unavailable") from None
    if len(payload) > _SOURCE_LIMIT:
        raise DemoValidationError("source_size")
    if hashlib.sha256(payload).hexdigest() != SOURCE_SHA256:
        raise DemoValidationError("source_hash")
    return _parse_csv(payload)  # The verified bytes, never a second file read.


def _resolve(rows, identity):
    matches = [row for row in rows if row["po_id"] == identity["po_id"]]
    if not matches:
        raise DemoValidationError("operation_missing")
    first = matches[0]
    # Occurrence distinguishes identical copies, never conflicting revisions.
    fields = ("order_date", *_COMMERCIAL_FIELDS)
    if (first["order_date"] != identity["order_date"]
            or any(any(row[k] != first[k] for k in fields) for row in matches)):
        raise DemoValidationError("conflicting_identity")
    if len(matches) < identity["occurrence"]:
        raise DemoValidationError("operation_missing")
    return dict(matches[identity["occurrence"] - 1])


def _as_operation(row):
    # Only pre-order columns are projected. Delivery/quality/contract flags and
    # payment terms cannot influence preparation or introduce outcome leakage.
    if re.fullmatch(r"[0-9]+", row["quantity"]) is None:
        raise DemoValidationError("invalid_quantity")
    source = source_identity()
    try:
        return {
            **{k: source[k] for k in ("source_id", "source_version", "entity_namespace")},
            **{k: row[k] for k in ("po_id", "order_date", "supplier_id", "item", "business_unit")},
            "unit_price": Decimal(row["unit_price"]), "quantity": int(row["quantity"]),
            "line_total": Decimal(row["line_total"]),
        }
    except (InvalidOperation, ValueError):
        raise DemoValidationError("invalid_number") from None


def _prepare(current, history):
    try:
        return features.prepare_features(current, history, source=source_identity(), coverage=source_coverage())
    except features.FeatureValidationError as exc:
        raise DemoValidationError(exc.code) from None


def _context(row, operation):
    result = {key: row[key] for key in _COMMERCIAL_FIELDS}
    for value in result.values():
        if not value or value.strip() != value or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise DemoValidationError("invalid_context")
    # Money remains original decimal text; quantity is an exact integer.
    result["quantity"] = operation["quantity"]
    return result


def list_operations():
    """Return the seven allowed identities and source commercial context only.

    Reads/verifies the fixed CSV; no model, inference, full batch or history
    calculation. All entries must resolve, otherwise the catalogue is refused.
    """
    rows = _read_source()
    entries = []
    for po_id, day, occurrence in _ALLOWED_OPERATIONS:
        identity = {"po_id": po_id, "order_date": day, "occurrence": occurrence}
        raw = _resolve(rows, identity)
        current = _as_operation(raw)
        _prepare(current, None)  # Existing P5.6 validates the current input, without history.
        entries.append({"operation": identity, "context": _context(raw, current)})
    return {"contract": CONTRACT_VERSION, "source": source_identity(), "operations": entries}


def prepare_operation(request):
    """Prepare one authorized occurrence; never load a model or calculate a score.

    status is eligible iff the five P5.8 features are complete. values is then
    the ordered numeric vector; otherwise None, with explicit unavailability.
    diagnostics retains all nine P5.6 features and their own reasons/references.
    A zero count or zero relative IQR is not missing data. An unavailable
    diagnostic-only feature does not block the five-feature vector.
    No mutation, imputation, deduplication, timestamps or persistence occurs.
    """
    identity = validate_request(request)
    rows = _read_source()
    raw = _resolve(rows, identity)
    current = _as_operation(raw)
    cutoff = _day(identity["order_date"])
    start = (cutoff - timedelta(days=features.WINDOW_DAYS)).isoformat()
    # Exclude the whole current day and future/older rows BEFORE numeric parsing.
    history = [_as_operation(row) for row in sorted(rows, key=lambda r: (r["order_date"], r["po_id"]))
               if start <= row["order_date"] < identity["order_date"]]
    prepared = _prepare(current, history)
    unavailable = {name: prepared["unavailability"][name] for name in MATRIX_FEATURES
                   if prepared["features"][name] is None}
    return {
        "contract": CONTRACT_VERSION, "source": source_identity(), "operation": identity,
        "context": _context(raw, current), "status": "unavailable" if unavailable else "eligible",
        "feature_contract": features.CONTRACT_VERSION, "matrix_contract": BATCH_VERSION,
        "cutoff_date": prepared["cutoff_date"], "window": prepared["window"],
        "coverage": prepared["coverage"], "support": prepared["support"],
        "feature_names": list(MATRIX_FEATURES),
        "values": None if unavailable else [prepared["features"][name] for name in MATRIX_FEATURES],
        "unavailability": unavailable,
        "diagnostics": {"feature_names": prepared["feature_names"], "features": prepared["features"],
                        "unavailability": prepared["unavailability"], "references": prepared["diagnostics"]},
    }
