"""Offline executor integration: fixed artificial fixture and a mocked model loader."""

import copy
import hashlib
import importlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

from ml.scripts.invoice_demo_contract import FEATURE_NAMES, validate_response

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/invoice/fixtures/invoice_demo_v1.json"


class DemoRunnerTests(unittest.TestCase):
    def setUp(self):
        from ml.scripts import invoice_demo_runner
        self.api = invoice_demo_runner
        self.content = FIXTURE.read_bytes()
        self.request = json.loads(self.content)
        temporary = tempfile.TemporaryDirectory(prefix="invoice-demo-runner-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.fixture = self.root / "tests/invoice/fixtures/invoice_demo_v1.json"
        self.fixture.parent.mkdir(parents=True)
        self.fixture.write_bytes(self.content)
        self.enterContext(patch.object(self.api, "PROJECT_ROOT", self.root))
        self.model = SimpleNamespace(
            feature_names_in_=np.array(FEATURE_NAMES), n_features_in_=19,
            score_samples=Mock(return_value=np.array([-0.2, -0.8, -0.2])),
        )
        self.loader = self.enterContext(patch(
            "ml.scripts.invoice_demo_loader.load_demo_model",
            return_value=SimpleNamespace(estimator=self.model, model_sha256="a1" * 32),
        ))
        self.guards = [self.enterContext(patch(target, side_effect=AssertionError("forbidden")))
                       for target in ("joblib.load", "socket.socket.connect",
                                      "socket.socket.connect_ex", "socket.create_connection",
                                      "sklearn.ensemble.IsolationForest.fit")]

    def tearDown(self):
        for guard in self.guards:
            guard.assert_not_called()

    def test_integration_loads_once_scores_once_and_validates_json(self):
        result = self.api.run_demo()
        self.loader.assert_called_once_with(self.root)
        self.model.score_samples.assert_called_once()
        validate_response(result, self.request)
        self.assertEqual(result["rows"], [
            {"id": "demo-002", "score": 0.8, "rank": 1},
            {"id": "demo-001", "score": 0.2, "rank": 2},
            {"id": "demo-003", "score": 0.2, "rank": 3},
        ])
        self.assertEqual(self.fixture.read_bytes(), self.content)
        self.assertEqual(len(list(self.root.rglob("*.*"))), 1)

    def test_cli_outputs_only_response_json(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = self.api.main([])
        self.assertEqual(code, 0)
        self.assertEqual(stderr.getvalue(), "")
        validate_response(json.loads(stdout.getvalue()), self.request)
        self.model.score_samples.assert_called_once()

    def test_arguments_cannot_select_another_model_or_input(self):
        for arguments in (["--model", "other.joblib"], ["--input", "other.json"], ["--help"]):
            stdout, stderr = io.StringIO(), io.StringIO()
            with self.subTest(arguments=arguments), redirect_stdout(stdout), redirect_stderr(stderr):
                self.assertEqual(self.api.main(arguments), 2)
            self.assertEqual(stdout.getvalue(), "")
            self.assertEqual(json.loads(stderr.getvalue()), {"error": "DEMO_ARGUMENTS"})
        self.loader.assert_not_called()

    def test_fixed_fixture_hash_is_verified_before_loading_model(self):
        self.fixture.write_bytes(self.content + b" ")
        with self.assertRaisesRegex(ValueError, "DEMO_FIXTURE_HASH"):
            self.api.run_demo()
        self.loader.assert_not_called()

    def test_missing_oversized_and_linked_fixture_are_rejected(self):
        with patch.object(Path, "open", side_effect=FileNotFoundError("private path")), \
                self.assertRaisesRegex(ValueError, "DEMO_FIXTURE_IO"):
            self.api.run_demo()
        self.fixture.write_bytes(b" " * (self.api.MAX_FIXTURE_BYTES + 1))
        with self.assertRaisesRegex(ValueError, "DEMO_FIXTURE_SIZE"):
            self.api.run_demo()
        for method in ("is_symlink", "is_junction"):
            with patch.object(Path, method, return_value=True), \
                    self.assertRaisesRegex(ValueError, "DEMO_FIXTURE_PATH"):
                self.api.run_demo()
        self.loader.assert_not_called()

    def test_schema_validation_precedes_model_loading(self):
        invalid = copy.deepcopy(self.request)
        invalid["rows"][0]["is_fraud"] = 1
        for content in (json.dumps(invalid).encode(), b"not json"):
            self.fixture.write_bytes(content)
            with patch.object(self.api, "FIXTURE_SHA256", hashlib.sha256(content).hexdigest()), \
                    self.assertRaisesRegex(ValueError, "DEMO_FIXTURE_SCHEMA"):
                self.api.run_demo()
        self.loader.assert_not_called()

    def test_model_rejection_stops_before_scoring_without_retry(self):
        self.loader.side_effect = ValueError("DEMO_MODEL_HASH")
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            self.assertEqual(self.api.main([]), 1)
        self.assertEqual(json.loads(stderr.getvalue()), {"error": "DEMO_MODEL_HASH"})
        self.assertEqual(stdout.getvalue(), "")
        self.loader.assert_called_once()
        self.model.score_samples.assert_not_called()

    def test_unexpected_errors_are_sanitized(self):
        self.loader.side_effect = RuntimeError("private path and details")
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            self.assertEqual(self.api.main([]), 1)
        self.assertEqual(json.loads(stderr.getvalue()), {"error": "DEMO_EXECUTION_FAILED"})
        self.assertEqual(stdout.getvalue(), "")
        self.model.score_samples.assert_not_called()

    def test_invalid_scoring_output_is_not_published(self):
        self.model.score_samples.return_value = np.array([np.nan, 0.2, 0.3])
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            self.assertEqual(self.api.main([]), 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(json.loads(stderr.getvalue()), {"error": "DEMO_SCORE_OUTPUT"})
        self.model.score_samples.assert_called_once()

    def test_import_is_passive(self):
        with patch.object(Path, "open", side_effect=AssertionError("file read")):
            importlib.reload(self.api)
        self.loader.assert_not_called()

    def test_direct_isolated_entry_point_refuses_arguments_without_loading(self):
        # The invalid argument must stop before any fixture/model access, even in a new process.
        result = subprocess.run(
            [sys.executable, "-I", "-B", str(ROOT / "ml/scripts/invoice_demo_runner.py"),
             "--model", "not-allowed"],
            cwd=self.root, capture_output=True, text=True, check=False, timeout=15,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertEqual(json.loads(result.stderr), {"error": "DEMO_ARGUMENTS"})


if __name__ == "__main__":
    unittest.main()
