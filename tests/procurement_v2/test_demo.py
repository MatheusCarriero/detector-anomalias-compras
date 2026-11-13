"""Offline preparation contracts; small fixtures, no real CSV or model."""

import copy
import csv
import hashlib
import importlib
import io
import json
import random
import socket
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from ml.procurement_v2 import batch, features


@pytest.fixture
def demo():
    return importlib.import_module("ml.procurement_v2.demo")


@pytest.fixture(autouse=True)
def no_network_or_real_source(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("network forbidden")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    original_open = Path.open
    root = Path(__file__).resolve().parents[2]
    protected = [root / "data", root / "ml/models", root / "ml/procurement_v2/artifacts"]

    def guarded_open(path, *args, **kwargs):
        assert not any(path.absolute().is_relative_to(folder) for folder in protected)
        return original_open(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", guarded_open)


@pytest.fixture
def rows():
    current = {
        "po_id": "PO-2025-27239", "order_date": "2025-01-23",
        "promised_delivery_date": "2025-02-01", "actual_delivery_date": "2025-02-02",
        "supplier_id": "SUP-A", "supplier_name": "Synthetic supplier",
        "supplier_country": "Unknown", "category": "Materials", "item": "Steel (kg)",
        "business_unit": "Operations", "unit_price": "21", "quantity": "42",
        "line_total": "882", "payment_terms": "Net 30", "on_contract": "True",
        "quality_rejected": "False",
    }
    history = [
        {**current, "po_id": f"H-{i:02d}", "order_date": f"2024-12-{i:02d}",
         "unit_price": str(i), "quantity": str(2 * i), "line_total": str(2 * i * i)}
        for i in range(1, 21)
    ]
    return history + [current]


def csv_bytes(rows):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode("utf-8")


@pytest.fixture
def install(demo, tmp_path, monkeypatch):
    path = tmp_path / "source.csv"
    monkeypatch.setattr(demo, "_CSV_PATH", path)

    def put(rows):
        payload = csv_bytes(rows)
        path.write_bytes(payload)
        # Explicit test-only trust pin, never the runtime trust policy.
        monkeypatch.setattr(demo, "SOURCE_SHA256", hashlib.sha256(payload).hexdigest())
        return path
    return put


def request(demo, identity=None):
    return {"contract": demo.CONTRACT_VERSION, "source_sha256": demo.SOURCE_SHA256,
            "operation": identity or {
                "po_id": "PO-2025-27239", "order_date": "2025-01-23", "occurrence": 1}}


def typed(row, source):
    keys = ("source_id", "source_version", "entity_namespace")
    return {**row, **{k: source[k] for k in keys}, "unit_price": Decimal(row["unit_price"]),
            "quantity": int(row["quantity"]), "line_total": Decimal(row["line_total"])}


def test_formulas_order_and_traceability(demo, rows, install):
    install(rows)
    result = demo.prepare_operation(request(demo))
    assert result["contract"] == "procurement-demo/1.0"
    assert result["status"] == "eligible"
    assert result["source"] == demo.source_identity()
    assert result["source"]["monetary_unit"] == "unspecified_source_unit"
    assert result["operation"] == request(demo)["operation"]
    assert result["feature_names"] == list(batch.MATRIX_FEATURES)
    assert result["values"] == pytest.approx([2, 2, 19 / 21, 20, 20])
    assert result["unavailability"] == {}
    assert result["window"] == {"start": "2024-10-25", "end": "2025-01-23", "end_exclusive": True}
    assert result["support"]["item"] == 20
    assert result["context"]["unit_price"] == "21"
    assert result["context"]["line_total"] == "882"
    assert result["context"]["quantity"] == 42
    assert not {"actual_delivery_date", "quality_rejected", "on_contract"} & result["context"].keys()
    reference = features.prepare_features(typed(rows[-1], result["source"]),
                                         [typed(r, result["source"]) for r in rows[:-1]],
                                         source=result["source"], coverage=demo.source_coverage())
    assert result["diagnostics"]["features"] == reference["features"]
    assert result["diagnostics"]["references"] == reference["diagnostics"]
    prepared = batch.prepare_batch([typed(r, result["source"]) for r in rows],
                                  source=result["source"], coverage=demo.source_coverage())
    assert result["values"] == prepared["matrices"]["validation_2025"]["values"][0]
    assert "score" not in json.dumps(result)
    json.dumps(result, allow_nan=False)


def test_catalog_only_allowed_and_fresh_copies(demo, rows, install, monkeypatch):
    identity = request(demo)["operation"]
    monkeypatch.setattr(demo, "_ALLOWED_OPERATIONS", ((identity["po_id"], identity["order_date"], 1),))
    install(rows)
    catalog = demo.list_operations()
    assert len(catalog["operations"]) == 1
    assert catalog["operations"][0]["operation"] == identity
    assert "values" not in catalog["operations"][0]
    catalog["operations"][0]["context"]["item"] = "changed"
    assert demo.list_operations()["operations"][0]["context"]["item"] == "Steel (kg)"
    source = demo.source_identity()
    source["origin"] = "real"
    assert demo.source_identity()["origin"] == "synthetic"


@pytest.mark.parametrize("fault", [None, [], {}, {"extra": 1}, "file.csv", True])
def test_invalid_request_never_reads_source(demo, monkeypatch, fault):
    monkeypatch.setattr(demo, "_read_source", lambda: pytest.fail("must validate before I/O"))
    with pytest.raises(demo.DemoValidationError):
        demo.prepare_operation(fault)


@pytest.mark.parametrize("key,value", [
    ("po_id", "UNAUTHORIZED"), ("po_id", "../model.joblib"), ("po_id", []),
    ("order_date", "2025-01-24"), ("order_date", "2025-02-30"),
    ("order_date", "20250123"), ("order_date", None),
    ("occurrence", 0), ("occurrence", True), ("occurrence", 1.0),
    ("occurrence", "1"), ("occurrence", 2),
])
def test_composite_allowlist_before_io(demo, monkeypatch, key, value):
    data = request(demo)
    data["operation"][key] = value
    monkeypatch.setattr(demo, "_read_source", lambda: pytest.fail("unauthorized source read"))
    with pytest.raises(demo.DemoValidationError):
        demo.prepare_operation(data)


@pytest.mark.parametrize("fault", ["version", "hash", "extra", "operation_extra"])
def test_request_contract_is_pinned(demo, fault):
    data = request(demo)
    if fault == "version":
        data["contract"] = "invoice-demo/1.0"
    elif fault == "hash":
        data["source_sha256"] = "0" * 64
    elif fault == "extra":
        data["path"] = "elsewhere.csv"
    else:
        data["operation"]["price"] = 100
    with pytest.raises(demo.DemoValidationError):
        demo.validate_request(data)


def test_no_public_paths_or_trust_override(demo):
    for fn in (demo.list_operations, demo.source_identity):
        with pytest.raises(TypeError):
            fn("arbitrary.csv")
    with pytest.raises(TypeError):
        demo.prepare_operation(request(demo), path="arbitrary.csv")


def test_hash_before_decode_or_csv_parsing(demo, rows, install, monkeypatch):
    path = install(rows)
    path.write_bytes(b"\xffinvalid untrusted CSV")
    monkeypatch.setattr(demo.csv, "DictReader", lambda *a, **k: pytest.fail("untrusted parsing"))
    with pytest.raises(demo.DemoValidationError, match="source_hash"):
        demo.prepare_operation(request(demo))


def test_parses_verified_bytes_without_reopening(demo, rows, install, monkeypatch):
    path = install(rows)
    parse = demo._parse_csv
    def replace_then_parse(payload):
        path.write_bytes(b"changed after verification")
        return parse(payload)
    monkeypatch.setattr(demo, "_parse_csv", replace_then_parse)
    assert demo.prepare_operation(request(demo))["values"] == pytest.approx([2, 2, 19 / 21, 20, 20])


@pytest.mark.parametrize("mode,reason", [("missing", "source_unavailable"), ("large", "source_size")])
def test_file_failures_sanitized(demo, rows, install, monkeypatch, mode, reason):
    path = install(rows)
    if mode == "missing":
        path.unlink()
    else:
        monkeypatch.setattr(demo, "_SOURCE_LIMIT", 10)
    with pytest.raises(demo.DemoValidationError) as caught:
        demo.prepare_operation(request(demo))
    assert str(caught.value) == reason
    assert str(path) not in str(caught.value)


def test_missing_authorized_record_is_not_empty_history(demo, rows, install):
    install(rows[:-1])
    with pytest.raises(demo.DemoValidationError, match="operation_missing"):
        demo.prepare_operation(request(demo))


def test_duplicates_preserve_occurrences_and_history_multiplicity(demo, rows, install, monkeypatch):
    identity = request(demo)["operation"]
    monkeypatch.setattr(demo, "_ALLOWED_OPERATIONS", (
        (identity["po_id"], identity["order_date"], 1), (identity["po_id"], identity["order_date"], 2)))
    install(rows + [copy.deepcopy(rows[0]), copy.deepcopy(rows[-1])])
    first = demo.prepare_operation(request(demo))
    second = demo.prepare_operation(request(demo, {**identity, "occurrence": 2}))
    assert first["support"]["item"] == 21
    assert first["values"] == second["values"]
    assert first["operation"]["occurrence"] == 1 and second["operation"]["occurrence"] == 2
    assert len(demo.list_operations()["operations"]) == 2


@pytest.mark.parametrize("where", [0, -1])
def test_conflicting_duplicates_rejected(demo, rows, install, where):
    rows.append({**rows[where], "item": "Conflicting (unit)"})
    install(rows)
    with pytest.raises(demo.DemoValidationError, match="conflicting_identity"):
        demo.prepare_operation(request(demo))


def test_temporal_boundaries_and_post_delivery_isolation(demo, rows, install):
    extra = {**rows[0], "po_id": "BOUNDARY", "order_date": "2024-10-25"}
    install(rows + [extra])
    expected = demo.prepare_operation(request(demo))
    for i, day in enumerate(["2024-10-24", "2025-01-23", "2025-01-24"]):
        rows.append({**extra, "po_id": f"EXCLUDED-{i}", "order_date": day,
                     "unit_price": "invalid", "quantity": "invalid", "line_total": "invalid"})
    for row in rows:
        row["quality_rejected"] = "arbitrary"
        row["actual_delivery_date"] = "not a date"
    install(rows + [extra])
    actual = demo.prepare_operation(request(demo))
    assert actual["values"] == expected["values"]
    assert actual["support"] == expected["support"]
    assert actual["diagnostics"] == expected["diagnostics"]


@pytest.mark.parametrize("n", [0, 17, 19, 20])
def test_availability_without_imputation(demo, rows, install, n):
    install(rows[:n] + [rows[-1]])
    result = demo.prepare_operation(request(demo))
    assert result["support"]["item"] == n
    assert result["status"] == ("eligible" if n == 20 else "unavailable")
    if n < 20:
        assert result["values"] is None
        assert result["unavailability"] == dict.fromkeys(batch.MATRIX_FEATURES[:3], "insufficient_history")
        assert result["diagnostics"]["features"]["supplier_item_lines_90d"] == n


def test_unavailable_diagnostics_and_zero_iqr_do_not_block_model_features(demo, rows, install):
    for row in rows[:-1]:
        row.update(unit_price="10", line_total=str(10 * int(row["quantity"])))
    rows[-1].update(supplier_id="NEW", business_unit="NEW-UNIT")
    install(rows)
    result = demo.prepare_operation(request(demo))
    assert result["status"] == "eligible"
    assert result["values"] == pytest.approx([2.1, 2, 0, 0, 0])
    assert result["diagnostics"]["unavailability"]["price_iqr_distance_90d"] == "zero_iqr"
    assert result["diagnostics"]["unavailability"]["price_to_supplier_item_median_90d"] == "insufficient_history"


@pytest.mark.parametrize("key,value", [
    ("quantity", "1.5"), ("quantity", "0"), ("quantity", "-1"),
    ("unit_price", "NaN"), ("unit_price", "Infinity"), ("unit_price", "0"),
    ("line_total", "999"), ("supplier_id", ""), ("order_date", "2025-02-30"),
])
def test_invalid_selected_data(demo, rows, install, key, value):
    rows[-1][key] = value
    install(rows)
    with pytest.raises(demo.DemoValidationError):
        demo.prepare_operation(request(demo))


def test_determinism_and_no_mutation(demo, rows, install, monkeypatch):
    before = copy.deepcopy(rows)
    install(rows)
    monkeypatch.setattr(demo, "_read_source", lambda: rows)
    data = request(demo)
    original = copy.deepcopy(data)
    result = demo.prepare_operation(data)
    assert rows == before and data == original
    assert result == demo.prepare_operation(data)
    result["diagnostics"]["features"][batch.MATRIX_FEATURES[0]] = 900
    assert demo.prepare_operation(data)["values"][0] == 2
    random.Random(42).shuffle(rows)
    assert demo.prepare_operation(data)["values"] == pytest.approx([2, 2, 19 / 21, 20, 20])


def test_decimal_context_preserved(demo, rows, install):
    rows[-1].update(unit_price="0.10", quantity="3", line_total="0.30")
    install(rows)
    result = demo.prepare_operation(request(demo))
    assert result["context"]["unit_price"] == "0.10"
    assert result["context"]["line_total"] == "0.30"


def test_csv_schema_refused(demo, rows, install):
    for row in rows:
        row["unexpected"] = "field"
    install(rows)
    with pytest.raises(demo.DemoValidationError, match="source_schema"):
        demo.prepare_operation(request(demo))


@pytest.mark.parametrize("payload,reason", [
    (b"\xff", "source_format"),
    (b"", "source_schema"),
    (b"wrong,header\n1,2\n", "source_schema"),
])
def test_malformed_trusted_fixture_is_refused(demo, rows, install, monkeypatch, payload, reason):
    path = install(rows)
    path.write_bytes(payload)
    monkeypatch.setattr(demo, "SOURCE_SHA256", hashlib.sha256(payload).hexdigest())
    with pytest.raises(demo.DemoValidationError, match=reason):
        demo.prepare_operation(request(demo))


@pytest.mark.parametrize("suffix,reason", [
    ("", "source_empty"), ("missing,columns\n", "source_schema"),
    ('"unclosed', "source_format"),
])
def test_empty_or_truncated_csv(demo, rows, install, monkeypatch, suffix, reason):
    path = install(rows)
    header = csv_bytes(rows).decode().splitlines()[0]
    payload = (header + "\n" + suffix).encode()
    path.write_bytes(payload)
    monkeypatch.setattr(demo, "SOURCE_SHA256", hashlib.sha256(payload).hexdigest())
    with pytest.raises(demo.DemoValidationError, match=reason):
        demo.prepare_operation(request(demo))


def test_redirected_source_is_refused_before_open(demo, rows, install, monkeypatch):
    path = install(rows)
    resolve = Path.resolve
    def redirected(value, *args, **kwargs):
        return value.with_name("elsewhere.csv") if value == path else resolve(value, *args, **kwargs)
    monkeypatch.setattr(Path, "resolve", redirected)
    with pytest.raises(demo.DemoValidationError, match="source_path"):
        demo.prepare_operation(request(demo))


def test_invalid_history_is_not_silently_dropped(demo, rows, install):
    rows[0]["line_total"] = "0"
    install(rows)
    with pytest.raises(demo.DemoValidationError, match="invalid_number"):
        demo.prepare_operation(request(demo))


def test_partial_coverage_preserves_reasons_and_support(demo, rows, install, monkeypatch):
    install(rows)
    coverage = {**demo.source_coverage(), "complete": False}
    monkeypatch.setattr(demo, "source_coverage", lambda: dict(coverage))
    result = demo.prepare_operation(request(demo))
    assert result["status"] == "unavailable" and result["values"] is None
    assert result["unavailability"] == dict.fromkeys(batch.MATRIX_FEATURES, "partial_window")
    assert result["support"]["item"] == 20


def test_context_validation_and_unchanged_source_bytes(demo, rows, install, monkeypatch):
    identity = request(demo)["operation"]
    monkeypatch.setattr(demo, "_ALLOWED_OPERATIONS", ((identity["po_id"], identity["order_date"], 1),))
    path = install(rows)
    original = path.read_bytes()
    demo.list_operations()
    demo.prepare_operation(request(demo))
    assert path.read_bytes() == original
    rows[-1]["supplier_name"] = "bad\x00name"
    install(rows)
    with pytest.raises(demo.DemoValidationError, match="invalid_context"):
        demo.list_operations()


def test_missing_duplicate_occurrence_is_refused(demo, rows, install, monkeypatch):
    identity = {**request(demo)["operation"], "occurrence": 2}
    monkeypatch.setattr(demo, "_ALLOWED_OPERATIONS", ((identity["po_id"], identity["order_date"], 2),))
    install(rows)
    with pytest.raises(demo.DemoValidationError, match="operation_missing"):
        demo.prepare_operation(request(demo, identity))


def test_import_is_inert_and_has_no_model_dependency(demo, monkeypatch):
    import builtins
    original_import = builtins.__import__
    def safe_import(name, *args, **kwargs):
        assert not any(part in name for part in ("artifact", "baseline", "joblib", "sklearn"))
        fromlist = args[2] if len(args) > 2 else kwargs.get("fromlist")
        assert not {"artifact", "baseline", "joblib", "sklearn"} & set(fromlist or ())
        return original_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", safe_import)
    monkeypatch.setattr(Path, "open", lambda *a, **k: pytest.fail("file I/O during import"))
    importlib.reload(demo)


def test_cold_import_has_no_transitive_model_data_or_network_access():
    code = r'''
import builtins, os, sys
from pathlib import Path
root = Path.cwd()
sys.path.insert(0, str(root))
original_import = builtins.__import__
def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    forbidden = {'artifact', 'baseline', 'joblib', 'sklearn'}
    assert not forbidden.intersection(name.split('.'))
    assert not forbidden.intersection(fromlist or ())
    return original_import(name, globals, locals, fromlist, level)
def guard(event, args):
    if event in {'socket.connect', 'socket.sendto', 'subprocess.Popen', 'os.system'}:
        raise AssertionError('network/process access')
    if event == 'open':
        path, mode, flags = args
        assert not flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
        if isinstance(path, str):
            target = Path(path).absolute()
            for folder in ('data', 'ml/models', 'ml/procurement_v2/artifacts'):
                assert not target.is_relative_to(root / folder)
builtins.__import__ = guarded_import
sys.addaudithook(guard)
from ml.procurement_v2 import demo
assert demo.CONTRACT_VERSION == 'procurement-demo/1.0'
assert not any(name.startswith(('sklearn', 'joblib')) for name in sys.modules)
print('import-only-ok')
'''
    result = subprocess.run([sys.executable, "-I", "-B", "-c", code],
                            cwd=Path(__file__).resolve().parents[2], capture_output=True,
                            text=True, timeout=20, check=False)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "import-only-ok"
    assert result.stderr == ""


def test_full_catalog_with_small_fixture_requires_all_seven_records(demo, rows, install):
    current = rows[-1]
    supplied = rows[:-1] + [
        {**current, "po_id": po_id, "order_date": day}
        for po_id, day, _ in demo._ALLOWED_OPERATIONS
    ]
    install(supplied)
    catalog = demo.list_operations()
    assert len(catalog["operations"]) == 7
    assert [(row["operation"]["po_id"], row["operation"]["order_date"], row["operation"]["occurrence"])
            for row in catalog["operations"]] == list(demo._ALLOWED_OPERATIONS)
    install(supplied[:-1])
    with pytest.raises(demo.DemoValidationError, match="operation_missing"):
        demo.list_operations()


def test_fixed_catalog(demo):
    assert demo._ALLOWED_OPERATIONS == (
        ("PO-2025-27239", "2025-01-23", 1), ("PO-2025-34347", "2025-07-15", 1),
        ("PO-2025-40702", "2025-12-24", 1), ("PO-2026-40862", "2026-01-16", 1),
        ("PO-2026-43834", "2026-03-11", 1), ("PO-2026-47088", "2026-06-17", 1),
        ("PO-2025-28121", "2025-01-04", 1),
    )
