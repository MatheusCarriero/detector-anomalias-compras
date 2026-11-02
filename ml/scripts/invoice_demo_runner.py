"""Local demo only: fixed P0 fixture -> trusted P1.5 loader -> P1 scoring -> stdout."""

import hashlib
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = "tests/invoice/fixtures/invoice_demo_v1.json"
# Identity of the reviewed P0 fixture; no auto-refresh or input path override.
FIXTURE_SHA256 = "ea94616d1bebdf91acb5c88dc93ca6042cb95a08147b4824b80519302e441a68"
MAX_FIXTURE_BYTES = 65536
ERROR_CODES = frozenset({
    "DEMO_FIXTURE_PATH", "DEMO_FIXTURE_IO", "DEMO_FIXTURE_SIZE", "DEMO_FIXTURE_HASH",
    "DEMO_FIXTURE_SCHEMA", "DEMO_TRUST_ANCHOR", "DEMO_RUNTIME_VERSION",
    "DEMO_ARTIFACT_PATH", "DEMO_ARTIFACT_IO", "DEMO_METADATA_HASH", "DEMO_MODEL_HASH",
    "DEMO_METADATA", "DEMO_ESTIMATOR_TYPE", "DEMO_ESTIMATOR_PARAMETERS",
    "DEMO_ESTIMATOR_STATE", "DEMO_MODEL_VERSION", "DEMO_DESERIALIZATION",
    "DEMO_ESTIMATOR_FEATURES", "DEMO_MODEL_ID", "DEMO_SCORE_OUTPUT",
    "DEMO_SCORING_FAILED", "DEMO_SCORING_INPUT_CHANGED",
})


def _read_fixture():
    from ml.scripts.invoice_demo_contract import validate_request

    path = PROJECT_ROOT / FIXTURE_PATH
    try:
        for component in (PROJECT_ROOT, PROJECT_ROOT / "tests", PROJECT_ROOT / "tests/invoice",
                          path.parent, path):
            if component.is_symlink() or component.is_junction():
                raise ValueError("DEMO_FIXTURE_PATH")
        if path.resolve(strict=True) != path.absolute() or not path.is_file():
            raise ValueError("DEMO_FIXTURE_PATH")
        with path.open("rb") as stream:
            content = stream.read(MAX_FIXTURE_BYTES + 1)
    except OSError:
        raise ValueError("DEMO_FIXTURE_IO") from None
    if len(content) > MAX_FIXTURE_BYTES:
        raise ValueError("DEMO_FIXTURE_SIZE")
    if hashlib.sha256(content).hexdigest() != FIXTURE_SHA256:
        raise ValueError("DEMO_FIXTURE_HASH")
    # Exact verified bytes, not an arbitrary JSON transport or upload endpoint.
    try:
        request = json.loads(content)
        validate_request(request)
        if len(request["rows"]) != 3:
            raise ValueError("DEMO_FIXTURE_SCHEMA")
    except (ValueError, TypeError, UnicodeError):
        raise ValueError("DEMO_FIXTURE_SCHEMA") from None
    return request


def run_demo():
    """Return the demo response in memory; no arguments, persistence or retries."""
    request = _read_fixture()
    from ml.scripts.invoice_demo_loader import load_demo_model
    from ml.scripts.invoice_demo_scoring import score_demo

    loaded = load_demo_model(PROJECT_ROOT)
    return score_demo(request, loaded.estimator, model_sha256=loaded.model_sha256)


def main(argv=None):
    arguments = sys.argv[1:] if argv is None else argv
    if arguments:
        print(json.dumps({"error": "DEMO_ARGUMENTS"}), file=sys.stderr)
        return 2
    try:
        response = run_demo()
        serialized = json.dumps(response, allow_nan=False, separators=(",", ":"))
    except Exception as error:  # noqa: BLE001 - CLI exposes only fixed diagnostic codes.
        code = str(error) if type(error) is ValueError else "DEMO_EXECUTION_FAILED"
        if code not in ERROR_CODES:
            code = "DEMO_EXECUTION_FAILED"
        print(json.dumps({"error": code}), file=sys.stderr)
        return 1
    print(serialized)
    return 0


if __name__ == "__main__":
    # Support direct execution with -I, independent of cwd/PYTHONPATH/user-site.
    # Only this trusted checkout is added, not a path supplied by the caller.
    sys.path.insert(0, str(PROJECT_ROOT))
    raise SystemExit(main())
