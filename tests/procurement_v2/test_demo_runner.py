"""CLI tests with mocked adapters or a temporary checkout and synthetic CSV."""

import copy
import csv
import hashlib
import importlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def runner():
    return importlib.import_module("ml.procurement_v2.demo_runner")


@pytest.fixture
def adapter(runner, monkeypatch):
    from ml.procurement_v2 import demo
    mocked = SimpleNamespace(CONTRACT_VERSION=demo.CONTRACT_VERSION,
                             SOURCE_SHA256=demo.SOURCE_SHA256,
                             DemoValidationError=demo.DemoValidationError,
                             validate_request=demo.validate_request)
    mocked.list_operations = lambda: {"contract": demo.CONTRACT_VERSION, "operations": []}
    mocked.prepare_operation = lambda req: {"status": "eligible", "operation": req["operation"],
                                            "values": [1, 1, 0, 0, 0]}
    monkeypatch.setattr(runner, "_adapter", lambda: mocked)
    return mocked


def request(action="catalog"):
    req = {"protocol": "procurement-demo-cli/1.0", "action": action,
           "request": {"contract": "procurement-demo/1.0",
                       "source_sha256": "fba22a467e5dd800a0af960930d2ca5e2ecbd9d2bc747e37304867d8d031ae21"}}
    if action == "prepare":
        req["request"]["operation"] = {"po_id": "PO-2025-27239", "order_date": "2025-01-23", "occurrence": 1}
    return req


def invoke(runner, req, argv=()):
    payload = req if isinstance(req, bytes) else json.dumps(req).encode()
    output = io.BytesIO()
    code = runner.main(list(argv), stdin=io.BytesIO(payload), stdout=output)
    raw = output.getvalue()
    assert raw.endswith(b"\n") and raw.count(b"\n") == 1
    return code, json.loads(raw), raw


@pytest.mark.parametrize("action", ["catalog", "prepare"])
def test_delegates_without_changing_result(runner, adapter, action):
    req = request(action)
    before = copy.deepcopy(req)
    expected = adapter.list_operations() if action == "catalog" else adapter.prepare_operation(req["request"])
    code, result, raw = invoke(runner, req)
    assert code == 0
    assert result == {"protocol": runner.PROTOCOL_VERSION, "status": "ok", "result": expected}
    assert req == before and invoke(runner, req)[2] == raw


def test_unavailable_is_success_not_internal_error(runner, adapter):
    expected = {"status": "unavailable", "values": None,
                "unavailability": {"price_to_item_median_90d": "insufficient_history"}}
    adapter.prepare_operation = lambda req: expected
    code, result, _ = invoke(runner, request("prepare"))
    assert code == 0 and result["result"] == expected


@pytest.mark.parametrize("payload", [b"", b"{", b"{}{}", b"{}\n{}", b"\xff", b"[]", b"null",
                                       b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1e999}',
                                       b'{"x":1,"x":2}', b"[" * 1000 + b"]" * 1000])
def test_invalid_json_or_structure(runner, adapter, payload):
    adapter.list_operations = lambda: pytest.fail("must not access source")
    code, result, _ = invoke(runner, payload)
    assert code == 2 and result["status"] == "invalid_request"


@pytest.mark.parametrize("fault", ["version", "action", "extra", "path", "hash", "contract", "identity", "bool"])
def test_strict_protocol_before_adapter_io(runner, adapter, fault):
    req = request("prepare")
    if fault == "version": req["protocol"] = "other/1"
    elif fault == "action": req["action"] = "score"
    elif fault == "extra": req["url"] = "https://invalid"
    elif fault == "path": req["request"]["path"] = "model.joblib"
    elif fault == "hash": req["request"]["source_sha256"] = "0" * 64
    elif fault == "contract": req["request"]["contract"] = "invoice-demo/1.0"
    elif fault == "identity": req["request"]["operation"]["po_id"] = "OTHER"
    else: req["request"]["operation"]["occurrence"] = True
    adapter.prepare_operation = lambda req: pytest.fail("must not access source")
    assert invoke(runner, req)[0] == 2


def test_catalog_rejects_operation_and_bad_identity(runner, adapter):
    req = request("prepare"); req["action"] = "catalog"
    assert invoke(runner, req)[0] == 2
    for field in ("contract", "source_sha256"):
        req = request(); req["request"][field] = []
        assert invoke(runner, req)[0] == 2


def test_byte_limits_and_single_buffered_response(runner, adapter, monkeypatch):
    payload = json.dumps(request()).encode()
    monkeypatch.setattr(runner, "MAX_INPUT_BYTES", len(payload))
    assert invoke(runner, payload)[0] == 0
    assert invoke(runner, payload + b" ")[1]["error"] == "CLI_INPUT_SIZE"
    monkeypatch.setattr(runner, "MAX_OUTPUT_BYTES", 256)
    adapter.list_operations = lambda: {"large": "x" * 300}
    code, result, raw = invoke(runner, payload)
    assert code == 1 and result["error"] == "CLI_OUTPUT_SIZE" and len(raw) <= 256


def test_failures_and_debug_output_are_sanitized(runner, adapter, capsys):
    def broken():
        print("secret debug")
        print("secret stderr", file=sys.stderr)
        raise RuntimeError("D:/private/password")
    adapter.list_operations = broken
    code, result, raw = invoke(runner, request())
    assert code == 1 and result["status"] == "technical_error"
    assert b"secret" not in raw and b"password" not in raw
    assert capsys.readouterr() == ("", "")
    adapter.list_operations = lambda: {"invalid": float("nan")}
    assert invoke(runner, request())[0] == 1


def test_source_error_is_not_invalid_request(runner, adapter):
    def refused():
        raise adapter.DemoValidationError("source_hash")
    adapter.list_operations = refused
    assert invoke(runner, request())[:2] == (
        1, {"protocol": runner.PROTOCOL_VERSION, "status": "technical_error", "error": "CLI_SOURCE_HASH"})


def test_arguments_and_read_errors(runner, adapter):
    assert invoke(runner, request(), ["file.csv"])[0] == 2
    class BrokenInput:
        def read(self, size): raise OSError("sensitive")
    output = io.BytesIO()
    assert runner.main([], stdin=BrokenInput(), stdout=output) == 1
    assert b"sensitive" not in output.getvalue()


def test_dependency_failure_and_closed_output_are_sanitized(runner, monkeypatch):
    def broken_import():
        raise ImportError("sensitive internal path")
    monkeypatch.setattr(runner, "_adapter", broken_import)
    assert invoke(runner, request())[1]["error"] == "CLI_FAILURE"
    class BrokenOutput:
        def write(self, packet): raise BrokenPipeError("closed")
    assert runner.main([], stdin=io.BytesIO(b"{}"), stdout=BrokenOutput()) == 1


def test_successful_debug_prints_do_not_pollute_protocol(runner, adapter, capsys):
    def noisy():
        print("debug")
        print("warning", file=sys.stderr)
        return {"text": "a\u00e7\u00e3o"}
    adapter.list_operations = noisy
    code, result, raw = invoke(runner, request())
    assert code == 0 and result["result"] == {"text": "a\u00e7\u00e3o"}
    assert capsys.readouterr() == ("", "")
    assert raw.isascii()


@pytest.fixture
def isolated(tmp_path):
    # Real CLI + adapter + original preparers. Only the copied demo trust pin
    # is replaced for the tiny synthetic fixture; production pins stay intact.
    checkout = tmp_path / "checkout"
    modules = checkout / "ml/procurement_v2"
    modules.mkdir(parents=True)
    for name in ("demo_runner.py", "demo.py", "features.py", "batch.py"):
        (modules / name).write_bytes((ROOT / "ml/procurement_v2" / name).read_bytes())
    # Tripwires in the trusted temporary import root: importing a model module
    # would fail this subprocess test instead of permitting fit/deserialization.
    for forbidden in (checkout / "sklearn.py", checkout / "joblib.py",
                      modules / "artifact.py", modules / "baseline.py"):
        forbidden.write_text("raise AssertionError('model access forbidden')", encoding="utf-8")
    from ml.procurement_v2 import demo
    columns = demo._COLUMNS
    def row(identity, day, item="Material (kg)"):
        return dict(zip(columns, [identity, day, "", "", "SYN-SUP", "Synthetic", "Unknown", "Synthetic",
                                  item, "Synthetic unit", "10.0", "2", "20.0", "", "", ""], strict=True))
    rows = [row(f"H-{i}", f"2024-12-{i:02d}") for i in range(1, 21)]
    rows += [row(f"M-{i}", f"2024-12-{i:02d}", "Rare material") for i in range(1, 18)]
    rows += [row(po, day, "Rare material" if po == "PO-2025-28121" else "Material (kg)")
             for po, day, _ in demo._ALLOWED_OPERATIONS]
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=columns); writer.writeheader(); writer.writerows(rows)
    payload = stream.getvalue().encode()
    pin = hashlib.sha256(payload).hexdigest()
    data = checkout / "data/external/procurement_spend/purchase_orders.csv"
    data.parent.mkdir(parents=True); data.write_bytes(payload)
    copied = modules / "demo.py"
    copied.write_text(copied.read_text().replace(demo.SOURCE_SHA256, pin), encoding="utf-8")
    return modules / "demo_runner.py", pin


@pytest.mark.parametrize("action,status", [("catalog", None), ("prepare", "eligible"), ("unavailable", "unavailable")])
def test_actual_isolated_cli_with_fixture_from_unrelated_cwd(isolated, tmp_path, action, status):
    script, pin = isolated
    req = request("catalog" if action == "catalog" else "prepare")
    req["request"]["source_sha256"] = pin
    if action == "unavailable":
        req["request"]["operation"] = {"po_id": "PO-2025-28121", "order_date": "2025-01-04", "occurrence": 1}
    # -I must ignore both PYTHONPATH and cwd as sources of imports.
    (tmp_path / "ml.py").write_text("raise RuntimeError('untrusted cwd import')")
    env = {**os.environ, "PYTHONPATH": str(tmp_path)}
    result = subprocess.run([sys.executable, "-I", "-B", str(script)], cwd=tmp_path,
                            env=env, input=json.dumps(req).encode(), capture_output=True, timeout=20, check=False)
    assert result.returncode == 0, result.stderr
    assert result.stderr == b"" and result.stdout.count(b"\n") == 1
    response = json.loads(result.stdout)
    assert response["status"] == "ok"
    if status:
        assert response["result"]["status"] == status
        # 20 ordinary historical lines + 17 rare lines + the earlier Jan 4 operation.
        assert response["result"]["values"] == ([1, 1, 0, 20, 38] if status == "eligible" else None)
    else:
        assert len(response["result"]["operations"]) == 7
    assert not list(tmp_path.rglob("__pycache__"))


def test_import_inert_no_model_dependencies(tmp_path):
    code = r'''
import builtins, os, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
original = builtins.__import__
def guarded(name, globals=None, locals=None, fromlist=(), level=0):
    forbidden = {'artifact', 'baseline', 'joblib', 'sklearn'}
    assert not forbidden.intersection(name.split('.'))
    assert not forbidden.intersection(fromlist or ())
    return original(name, globals, locals, fromlist, level)
builtins.__import__ = guarded
def audit(event, args):
    if event in {'socket.connect','subprocess.Popen'}: raise AssertionError('external access')
    if event == 'open':
        path, mode, flags = args
        assert not flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
        if isinstance(path,str): assert not path.endswith(('.csv','.joblib','metadata.json'))
sys.addaudithook(audit)
from ml.procurement_v2 import demo_runner
assert 'ml.procurement_v2.demo' not in sys.modules
print('inert')
'''
    result = subprocess.run([sys.executable, "-I", "-B", "-c", code, str(ROOT)],
                            cwd=tmp_path, capture_output=True, timeout=20, check=False)
    assert result.returncode == 0
    assert result.stdout.strip() == b"inert"
    assert result.stderr == b""


def run_request():
    req = request("prepare")
    req.update(protocol="procurement-demo-cli/1.1", action="run")
    return req


def test_inference_requires_new_protocol_and_preserves_old_actions(runner, adapter, monkeypatch):
    req = run_request()
    result = {"contract": "procurement-demo-inference/1.0", "status": "scored", "anomaly_score": .25}
    from ml.procurement_v2 import demo_inference
    calls = []
    def run(value):
        calls.append(copy.deepcopy(value))
        return result
    monkeypatch.setattr(demo_inference, "run_operation", run)
    code, response, _ = invoke(runner, req)
    assert code == 0 and response == {"protocol": req["protocol"], "status": "ok", "result": result}
    assert calls == [req["request"]]
    req["protocol"] = "procurement-demo-cli/1.0"
    assert invoke(runner, req)[0] == 2
    assert len(calls) == 1
    for action in ("catalog", "prepare"):
        assert invoke(runner, request(action))[1]["protocol"] == "procurement-demo-cli/1.0"


@pytest.mark.parametrize("code", ["MODEL_UNAVAILABLE", "MODEL_INTEGRITY", "MODEL_INCOMPATIBLE",
                                 "MODEL_LOAD_FAILED", "INVALID_SCORE", "SCORING_FAILED", "PREPARATION_INVALID"])
def test_inference_error_codes_are_sanitized(runner, adapter, monkeypatch, code):
    from ml.procurement_v2 import demo_inference
    def rejected(req):
        raise demo_inference.InferenceError(code)
    monkeypatch.setattr(demo_inference, "run_operation", rejected)
    exit_code, response, _ = invoke(runner, run_request())
    assert exit_code == 1 and response == {"protocol": "procurement-demo-cli/1.1",
                                          "status": "technical_error", "error": "CLI_" + code}


def test_run_invalid_request_and_unknown_failure(runner, adapter, monkeypatch):
    from ml.procurement_v2 import demo_inference
    def forbidden(req):
        raise AssertionError("private/path/password")
    monkeypatch.setattr(demo_inference, "run_operation", forbidden)
    req = run_request(); req["request"]["path"] = "untrusted"
    assert invoke(runner, req)[0] == 2
    code, response, raw = invoke(runner, run_request())
    assert code == 1 and response["error"] == "CLI_FAILURE"
    assert b"private" not in raw


def test_run_unavailable_and_output_limit(runner, adapter, monkeypatch):
    from ml.procurement_v2 import demo_inference
    monkeypatch.setattr(demo_inference, "run_operation", lambda req: {"status": "unavailable", "anomaly_score": None})
    assert invoke(runner, run_request())[0] == 0
    monkeypatch.setattr(runner, "MAX_OUTPUT_BYTES", 256)
    monkeypatch.setattr(demo_inference, "run_operation", lambda req: {"large": "x" * 300})
    assert invoke(runner, run_request())[1]["error"] == "CLI_OUTPUT_SIZE"


def test_isolated_run_uses_only_simulated_artifact(isolated, tmp_path):
    script, pin = isolated
    modules = script.parent
    (modules / "demo_inference.py").write_bytes((ROOT / "ml/procurement_v2/demo_inference.py").read_bytes())
    # In this temporary checkout the real model libraries remain tripwires.
    # The official loaded-model interface is simulated, never a real joblib.
    (modules / "artifact.py").write_text('''
ARTIFACT_ID = 'synthetic-fixture'
TRUSTED_MODEL_SHA256 = 'a' * 64
TRUSTED_METADATA_SHA256 = 'b' * 64
class ArtifactError(ValueError): pass
class Loaded:
    artifact_id = ARTIFACT_ID
    model_sha256 = TRUSTED_MODEL_SHA256
    def score(self, values, *, feature_names):
        assert len(values) == len(feature_names) == 5
        return .25
def load_baseline(): return Loaded()
''', encoding="utf-8")
    req = run_request(); req["request"]["source_sha256"] = pin
    result = subprocess.run([sys.executable, "-I", "-B", "-X", "utf8", str(script)], cwd=tmp_path,
                            input=json.dumps(req).encode(), capture_output=True, timeout=20, check=False)
    assert result.returncode == 0 and result.stderr == b""
    value = json.loads(result.stdout)
    assert value["protocol"] == "procurement-demo-cli/1.1"
    assert value["result"]["status"] == "scored" and value["result"]["anomaly_score"] == .25
    assert not list(tmp_path.rglob("__pycache__"))
