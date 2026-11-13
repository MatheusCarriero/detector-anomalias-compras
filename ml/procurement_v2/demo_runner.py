"""One bounded JSON request on stdin, one JSON response on stdout, then exit.

Protocol procurement-demo-cli/1.0 wraps the existing adapter request/result.
Actions: catalog (contract + source_sha256) and prepare (also operation).
Exit 0 includes eligible AND unavailable preparation; 2 means invalid request;
1 means technical failure. No model imports, scoring, persistence or retries.
The caller must close stdin and enforce process timeout/concurrency limits.
"""

import contextlib
import json
import math
import sys
from pathlib import Path

PROTOCOL_VERSION = "procurement-demo-cli/1.0"
MAX_INPUT_BYTES = 1024
MAX_OUTPUT_BYTES = 65536


class _InvalidRequest(ValueError):
    pass


class _Discard:
    def write(self, text):
        return len(text)

    def flush(self):
        pass


def _adapter():
    from ml.procurement_v2 import demo
    return demo


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate key")
        result[key] = value
    return result


def _constant(value):
    raise ValueError("nonfinite constant")


def _float(value):
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError("nonfinite number")
    return parsed


def _request(payload):
    try:
        value = json.loads(payload.decode("utf-8"), object_pairs_hook=_pairs,
                           parse_constant=_constant, parse_float=_float)
    except (ValueError, UnicodeError, RecursionError):
        raise _InvalidRequest("CLI_JSON") from None
    if type(value) is not dict or set(value) != {"protocol", "action", "request"}:
        raise _InvalidRequest("CLI_REQUEST")
    if value["protocol"] != PROTOCOL_VERSION:
        raise _InvalidRequest("CLI_PROTOCOL")
    if type(value["action"]) is not str or value["action"] not in ("catalog", "prepare"):
        raise _InvalidRequest("CLI_ACTION")
    return value


def _dispatch(value, adapter):
    req = value["request"]
    if value["action"] == "catalog":
        if (type(req) is not dict or set(req) != {"contract", "source_sha256"}
                or req["contract"] != adapter.CONTRACT_VERSION
                or req["source_sha256"] != adapter.SOURCE_SHA256):
            raise _InvalidRequest("CLI_REQUEST")
        return adapter.list_operations()
    try:
        adapter.validate_request(req)  # Reuse exact identity/allowlist before source I/O.
    except adapter.DemoValidationError:
        raise _InvalidRequest("CLI_REQUEST") from None
    return adapter.prepare_operation(req)


def _encode(value):
    # ASCII escapes guarantee portable UTF-8 JSON even on Windows terminals.
    return (json.dumps(value, ensure_ascii=True, allow_nan=False,
                       sort_keys=True, separators=(",", ":")) + "\n").encode("ascii")


def _error(status, code):
    return _encode({"protocol": PROTOCOL_VERSION, "status": status, "error": code})


def main(argv=None, *, stdin=None, stdout=None):
    """Binary streams are injectable for tests; never paths or runtime overrides."""
    arguments = sys.argv[1:] if argv is None else argv
    source = sys.stdin.buffer if stdin is None else stdin
    target = sys.stdout.buffer if stdout is None else stdout
    exit_code = 0
    adapter = None
    # Suppress accidental prints/warnings from dependencies without buffering
    # unbounded debug text. Only the completed protocol packet reaches stdout.
    with contextlib.redirect_stdout(_Discard()), contextlib.redirect_stderr(_Discard()):
        try:
            if arguments:
                raise _InvalidRequest("CLI_ARGUMENTS")
            payload = source.read(MAX_INPUT_BYTES + 1)
            if len(payload) > MAX_INPUT_BYTES:
                raise _InvalidRequest("CLI_INPUT_SIZE")
            value = _request(payload)
            adapter = _adapter()
            result = _dispatch(value, adapter)
            if type(result) is not dict:
                raise ValueError("invalid adapter response")
            packet = _encode({"protocol": PROTOCOL_VERSION, "status": "ok", "result": result})
            if len(packet) > MAX_OUTPUT_BYTES:
                packet = _error("technical_error", "CLI_OUTPUT_SIZE")
                exit_code = 1
        except _InvalidRequest as exc:
            packet = _error("invalid_request", str(exc))
            exit_code = 2
        except Exception as exc:  # noqa: BLE001 - CLI boundary never exposes exception text.
            code = "CLI_FAILURE"
            if adapter is not None and isinstance(exc, adapter.DemoValidationError):
                # Only predefined diagnostics; unrecognized adapter errors remain generic.
                code = {"source_hash": "CLI_SOURCE_HASH", "source_path": "CLI_SOURCE_PATH",
                        "source_unavailable": "CLI_SOURCE_UNAVAILABLE"}.get(exc.code, "CLI_ADAPTER_FAILURE")
            packet = _error("technical_error", code)
            exit_code = 1
    try:
        target.write(packet)
        target.flush()
    except (OSError, ValueError):
        return 1  # Closed output cannot receive a second packet; no traceback to stderr.
    return exit_code


if __name__ == "__main__":
    # Fixed trusted repository location; independent of cwd and PYTHONPATH under -I.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    raise SystemExit(main())
