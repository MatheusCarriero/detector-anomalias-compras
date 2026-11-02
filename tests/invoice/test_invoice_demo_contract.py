"""Technical contract tests with handcrafted data, no estimator or scientific run."""

import ast
import copy
import importlib.util
import json
import math
import socket
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "invoice_demo_contract", ROOT / "ml/scripts/invoice_demo_contract.py"
)
contract = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(contract)
FIXTURE = Path(__file__).parent / "fixtures/invoice_demo_v1.json"


class DemoContractTests(unittest.TestCase):
    def setUp(self):
        self.request = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def response(self):
        # Invented test values: NOT scores obtained from the Invoice model.
        return {
            "contract": contract.VERSION, "origin": "synthetic",
            "source_reconciled": False, "model_sha256": "0" * 64,
            "score_kind": "negative_score_samples",
            "score_direction": "higher_is_more_anomalous",
            "rows": [{"id": row["id"], "score": 0.5, "rank": index}
                     for index, row in enumerate(self.request["rows"], 1)],
        }

    def test_feature_order_matches_official_constant_without_importing_training(self):
        tree = ast.parse((ROOT / "ml/scripts/treinar_modelo.py").read_text(encoding="utf-8"))
        features = next(ast.literal_eval(node.value) for node in tree.body
                        if isinstance(node, ast.Assign)
                        and any(isinstance(t, ast.Name) and t.id == "FEATURES"
                                for t in node.targets))
        self.assertEqual(list(contract.FEATURE_NAMES), features)
        self.assertEqual(len(features), 19)

    def test_fixture_is_coherent_with_explicit_invented_context(self):
        contract.validate_request(self.request)
        for row in self.request["rows"]:
            v = dict(zip(contract.FEATURE_NAMES, row["values"], strict=True))
            self.assertAlmostEqual(v["log_invoice_amount"], math.log1p(v["invoice_amount"]))
            self.assertEqual(v["amount_vs_supplier_mean"], v["invoice_amount"] / 100)
            self.assertEqual(v["amount_vs_department_mean"], v["invoice_amount"] / 100)
            self.assertEqual(v["supplier_amount_zscore"], (v["invoice_amount"] - 100) / 50)
            for period in ("submission_hour", "day_of_week", "month"):
                self.assertEqual(v[f"{period}_sin"] ** 2 + v[f"{period}_cos"] ** 2, 1)

    def test_validation_has_no_io_network_or_input_mutation(self):
        before = copy.deepcopy(self.request)
        with patch("builtins.open", side_effect=AssertionError("file access")), \
                patch.object(socket.socket, "connect", side_effect=AssertionError("network")):
            contract.validate_request(self.request)
            contract.validate_response(self.response(), self.request)
        self.assertEqual(self.request, before)

    def test_rejects_extra_keys_including_labels_paths_and_model_upload(self):
        for key in ("is_fraud", "fraud_type", "split", "model_path", "dataset_path"):
            with self.subTest(key=key):
                payload = copy.deepcopy(self.request)
                payload[key] = "forbidden"
                with self.assertRaisesRegex(ValueError, "DEMO_SCHEMA"):
                    contract.validate_request(payload)

    def test_rejects_feature_order_count_and_duplicate_ids(self):
        for failure in ("order", "count", "id"):
            payload = copy.deepcopy(self.request)
            if failure == "order":
                payload["feature_names"].reverse()
            elif failure == "count":
                payload["rows"][0]["values"].pop()
            else:
                payload["rows"][1]["id"] = payload["rows"][0]["id"]
            with self.subTest(failure=failure), self.assertRaises(ValueError):
                contract.validate_request(payload)

    def test_rejects_non_numeric_non_finite_and_overflow(self):
        for value in (None, True, "100", float("nan"), float("inf"), 10**400):
            payload = copy.deepcopy(self.request)
            payload["rows"][0]["values"][0] = value
            with self.subTest(value=type(value)), self.assertRaisesRegex(ValueError, "DEMO_NUMBER"):
                contract.validate_request(payload)

    def test_rejects_wrong_scope_and_batch_size(self):
        for key, value in (("origin", "test"), ("contract", "old"),
                           ("rows", []), ("rows", self.request["rows"] * 34)):
            payload = copy.deepcopy(self.request)
            payload[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                contract.validate_request(payload)

    def test_mock_response_ties_use_id_and_reject_misalignment(self):
        response = self.response()
        contract.validate_response(response, self.request)
        for key, value in (("id", "demo-absent"), ("id", "demo-001"),
                           ("rank", True), ("score", float("nan")), ("score", 0.7)):
            bad = copy.deepcopy(response)
            bad["rows"][1][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                contract.validate_response(bad, self.request)

    def test_response_cannot_claim_probability_or_reconciled_provenance(self):
        for key, value in (("score_kind", "fraud_probability"),
                           ("source_reconciled", True), ("model_sha256", "unknown")):
            response = self.response()
            response[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                contract.validate_response(response, self.request)

    def test_missing_rows_extra_fields_and_wrong_shapes_are_rejected(self):
        for value in (None, [], {}, "payload"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                contract.validate_request(value)
        for change in ("missing", "extra", "tie"):
            response = self.response()
            if change == "missing":
                response["rows"].pop()
            elif change == "extra":
                response["rows"][0]["probability"] = 0.99
            else:
                response["rows"][0]["id"], response["rows"][1]["id"] = (
                    response["rows"][1]["id"], response["rows"][0]["id"]
                )
            with self.subTest(change=change), self.assertRaises(ValueError):
                contract.validate_response(response, self.request)


if __name__ == "__main__":
    unittest.main()
