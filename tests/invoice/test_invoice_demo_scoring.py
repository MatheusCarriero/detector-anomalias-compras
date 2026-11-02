"""Synthetic estimator only: no trained model, datasets or scientific evaluator."""

import copy
import io
import json
import socket
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from ml.scripts.invoice_demo_contract import FEATURE_NAMES, validate_response

FIXTURE = Path(__file__).parent / "fixtures/invoice_demo_v1.json"
DIGEST = "a1" * 32  # Synthetic loader identity, not a real artifact hash.


class SimulatedEstimator:
    def __init__(self, output=None):
        self.feature_names_in_ = np.array(FEATURE_NAMES)
        self.n_features_in_ = np.int64(19)
        self.output = np.array([-0.2, -0.8, -0.2]) if output is None else output
        self.calls = 0
        self.received = None

    def score_samples(self, frame):
        self.calls += 1
        self.received = frame.copy(deep=True)
        return self.output

    def fit(self, *args, **kwargs):
        raise AssertionError("fit forbidden")

    def predict(self, *args, **kwargs):
        raise AssertionError("predict forbidden")

    def decision_function(self, *args, **kwargs):
        raise AssertionError("decision_function forbidden")


class DemoScoringTests(unittest.TestCase):
    def setUp(self):
        self.request = json.loads(FIXTURE.read_text(encoding="utf-8"))
        # Tie sorting must not confuse original row order with ranking order.
        self.request["rows"].reverse()
        self.estimator = SimulatedEstimator()
        self.socket_guard = patch.object(
            socket.socket, "connect", side_effect=AssertionError("network forbidden")
        )
        self.network = self.socket_guard.start()
        self.addCleanup(self.socket_guard.stop)
        from ml.scripts.invoice_demo_scoring import score_demo
        self.score = score_demo

    def tearDown(self):
        self.network.assert_not_called()

    def test_named_features_single_call_sign_ties_and_ids(self):
        result = self.score(self.request, self.estimator, model_sha256=DIGEST)
        self.assertEqual(self.estimator.calls, 1)
        self.assertEqual(list(self.estimator.received.columns), list(FEATURE_NAMES))
        self.assertEqual(self.estimator.received.shape, (3, 19))
        self.assertEqual(self.estimator.received.index.tolist(), [0, 1, 2])
        self.assertEqual(
            self.estimator.received.to_numpy().tolist(),
            [row["values"] for row in self.request["rows"]],
        )
        self.assertEqual(result["rows"], [
            {"id": "demo-002", "score": 0.8, "rank": 1},
            {"id": "demo-001", "score": 0.2, "rank": 2},
            {"id": "demo-003", "score": 0.2, "rank": 3},
        ])
        self.assertEqual(result["model_sha256"], DIGEST)
        self.assertIs(result["source_reconciled"], False)
        validate_response(result, self.request)
        json.dumps(result, allow_nan=False)

    def test_distinct_scores_keep_original_ids_after_sorting(self):
        result = self.score(self.request, SimulatedEstimator([-0.1, 0.2, -0.3]),
                            model_sha256=DIGEST)
        self.assertEqual(result["rows"], [
            {"id": "demo-001", "score": 0.3, "rank": 1},
            {"id": "demo-003", "score": 0.1, "rank": 2},
            {"id": "demo-002", "score": -0.2, "rank": 3},
        ])

    def test_request_and_caller_rows_are_not_mutated_and_no_files_are_opened(self):
        before = copy.deepcopy(self.request)
        with patch("builtins.open", side_effect=AssertionError("file forbidden")), \
                patch.object(io, "open", side_effect=AssertionError("file forbidden")):
            self.score(self.request, self.estimator, model_sha256=DIGEST)
        self.assertEqual(self.request, before)

    def test_invalid_input_never_reaches_estimator(self):
        cases = []
        for key, value in (("origin", "test"), ("rows", []),
                           ("feature_names", list(reversed(FEATURE_NAMES))),
                           ("is_fraud", [0, 1, 0])):
            payload = copy.deepcopy(self.request)
            payload[key] = value
            cases.append(payload)
        for value in (None, True, "1", float("nan"), float("inf")):
            payload = copy.deepcopy(self.request)
            payload["rows"][0]["values"][0] = value
            cases.append(payload)
        duplicate = copy.deepcopy(self.request)
        duplicate["rows"][1]["id"] = duplicate["rows"][0]["id"]
        cases.append(duplicate)
        short = copy.deepcopy(self.request)
        short["rows"][0]["values"].pop()
        cases.append(short)
        for index, payload in enumerate(cases):
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.score(payload, self.estimator, model_sha256=DIGEST)
        self.assertEqual(self.estimator.calls, 0)

    def test_invalid_digest_rejected_before_scoring(self):
        for digest in (None, "", "a" * 63, "G" * 64, "A" * 64, 123):
            with self.subTest(digest=digest), self.assertRaisesRegex(ValueError, "DEMO_MODEL_ID"):
                self.score(self.request, self.estimator, model_sha256=digest)
        self.assertEqual(self.estimator.calls, 0)

    def test_estimator_feature_metadata_must_match(self):
        for attribute, value in (("feature_names_in_", list(reversed(FEATURE_NAMES))),
                                 ("feature_names_in_", list(FEATURE_NAMES[:-1])),
                                 ("feature_names_in_", None),
                                 ("feature_names_in_", np.array("invoice_amount")),
                                 ("feature_names_in_", np.array([FEATURE_NAMES])),
                                 ("n_features_in_", 18), ("n_features_in_", True),
                                 ("n_features_in_", "19"), ("score_samples", None)):
            estimator = SimulatedEstimator()
            setattr(estimator, attribute, value)
            with self.subTest(attribute=attribute, value=value), self.assertRaisesRegex(
                ValueError, "DEMO_ESTIMATOR_FEATURES"
            ):
                self.score(self.request, estimator, model_sha256=DIGEST)
            self.assertEqual(estimator.calls, 0)

    def test_wrong_output_shapes_or_types_are_refused(self):
        for output in ([], [-0.1], [-0.1] * 4, np.array(0.1),
                       np.array([[-0.1], [-0.2], [-0.3]]), "-0.1", {"x": -0.1},
                       [True, -0.2, -0.3], ["-0.1", "-0.2", "-0.3"],
                       np.array([True, False, True]), np.array([1j, 2j, 3j]),
                       np.array([0.1, 0.2, 0.3], dtype=object),
                       pd.Series([-0.1, -0.2, -0.3], index=[2, 1, 0])):
            with self.subTest(output=repr(output)), self.assertRaisesRegex(
                ValueError, "DEMO_SCORE_OUTPUT"
            ):
                self.score(self.request, SimulatedEstimator(output), model_sha256=DIGEST)

    def test_nonfinite_outputs_are_refused(self):
        for invalid in (float("nan"), float("inf"), float("-inf"), 10**400):
            with self.subTest(value=str(invalid)), self.assertRaisesRegex(
                ValueError, "DEMO_SCORE_OUTPUT"
            ):
                self.score(self.request, SimulatedEstimator([-0.1, invalid, -0.2]),
                           model_sha256=DIGEST)

    def test_single_record_and_zero_scores(self):
        request = copy.deepcopy(self.request)
        request["rows"] = request["rows"][:1]
        result = self.score(request, SimulatedEstimator([0]), model_sha256=DIGEST)
        self.assertEqual(result["rows"], [{"id": "demo-003", "score": 0.0, "rank": 1}])

    def test_scoring_failure_is_sanitized_without_retry(self):
        class Failing(SimulatedEstimator):
            def score_samples(self, frame):
                self.calls += 1
                raise RuntimeError("sensitive driver or model detail")

        estimator = Failing()
        with self.assertRaisesRegex(ValueError, "^DEMO_SCORING_FAILED$") as caught:
            self.score(self.request, estimator, model_sha256=DIGEST)
        self.assertEqual(estimator.calls, 1)
        self.assertTrue(caught.exception.__suppress_context__)

    def test_mutating_frame_cannot_silently_reassociate_scores(self):
        class Reorders(SimulatedEstimator):
            def score_samples(self, frame):
                frame.sort_values("invoice_amount", inplace=True)
                return self.output

        before = copy.deepcopy(self.request)
        with self.assertRaisesRegex(ValueError, "DEMO_SCORING_INPUT_CHANGED"):
            self.score(self.request, Reorders(), model_sha256=DIGEST)
        self.assertEqual(self.request, before)


if __name__ == "__main__":
    unittest.main()
