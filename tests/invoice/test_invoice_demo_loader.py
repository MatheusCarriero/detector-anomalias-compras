"""Artificial bytes and simulated fitted state only: never unpickle, fit or score a tree."""

import copy
import hashlib
import importlib
import io
import json
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.exceptions import InconsistentVersionWarning
from sklearn.tree import ExtraTreeRegressor

from ml.scripts.invoice_demo_contract import FEATURE_NAMES, validate_response
from ml.scripts.invoice_demo_scoring import score_demo

ARTIFICIAL_BYTES = b"synthetic fixture, not a serialized estimator"
PARAMETERS = {
    "n_estimators": 200, "contamination": 0.22, "random_state": 42, "n_jobs": -1,
    "max_samples": "auto", "max_features": 1.0, "bootstrap": False,
    "warm_start": False, "verbose": 0,
}
OFFSET = -0.5211491197816622


def simulated_model():
    # Constructor only. Structural fixtures are not fitted models.
    model = IsolationForest(**PARAMETERS)
    tree = ExtraTreeRegressor()
    tree.tree_ = object()
    tree.n_features_in_ = 19
    model.estimators_ = [tree] * 200
    model.estimators_features_ = [np.arange(19)] * 200
    model.n_features_in_ = np.int64(19)
    model.feature_names_in_ = np.array(FEATURE_NAMES)
    model.max_samples_ = 256
    model._n_samples = 210000
    model.offset_ = OFFSET
    return model


class DemoLoaderTests(unittest.TestCase):
    def setUp(self):
        from ml.scripts import invoice_demo_loader
        self.api = invoice_demo_loader
        self.temporary = tempfile.TemporaryDirectory(prefix="invoice-demo-loader-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.model_path = self.root / "ml/models/isolation_forest.joblib"
        self.metadata_path = self.root / "ml/models/model_metadata.json"
        self.model_path.parent.mkdir(parents=True)
        self.model_path.write_bytes(ARTIFICIAL_BYTES)
        self.metadata = {
            "algorithm": "IsolationForest", "feature_count": 19,
            "features": list(FEATURE_NAMES), "n_estimators": 200,
            "contamination": 0.22, "random_state": 42,
            "training_date": "synthetic fixture only",
        }
        self.metadata_bytes = json.dumps(self.metadata).encode()
        self.metadata_path.write_bytes(self.metadata_bytes)
        self.model_hash = hashlib.sha256(ARTIFICIAL_BYTES).hexdigest()
        for name, value in (
            ("EXPECTED_MODEL_SHA256", self.model_hash),
            ("EXPECTED_METADATA_SHA256", hashlib.sha256(self.metadata_bytes).hexdigest()),
        ):
            self.enterContext(patch.object(self.api, name, value))
        self.runtime = self.enterContext(patch.object(
            self.api, "_runtime_versions", return_value=dict(self.api.RUNTIME_VERSIONS)
        ))
        self.guards = [self.enterContext(patch(target, side_effect=AssertionError("forbidden")))
                       for target in ("socket.socket.connect", "socket.socket.connect_ex",
                                      "socket.create_connection", "joblib.load")]
        self.fit = self.enterContext(patch.object(
            IsolationForest, "fit", side_effect=AssertionError("fit forbidden")
        ))
        self.score = self.enterContext(patch.object(
            IsolationForest, "score_samples", side_effect=AssertionError("scoring forbidden")
        ))
        self.model = simulated_model()
        self.deserialize = Mock(return_value=self.model)

    def tearDown(self):
        for guard in [*self.guards, self.fit, self.score]:
            guard.assert_not_called()

    def load(self):
        return self.api.load_demo_model(self.root, deserialize=self.deserialize)

    def write_trusted_synthetic_metadata(self, content):
        self.metadata_path.write_bytes(content)
        self.enterContext(patch.object(
            self.api, "EXPECTED_METADATA_SHA256", hashlib.sha256(content).hexdigest()
        ))

    def test_validated_model_and_verified_digest_reach_existing_scorer(self):
        loaded = self.load()
        self.assertIs(loaded.estimator, self.model)
        self.assertEqual(loaded.model_sha256, self.model_hash)
        self.deserialize.assert_called_once()
        request = {"contract": "invoice-demo/1.0", "origin": "synthetic",
                   "feature_names": list(FEATURE_NAMES),
                   "rows": [{"id": "demo-b", "values": [0] * 19},
                            {"id": "demo-a", "values": [0] * 19}]}
        with patch.object(self.model, "score_samples", return_value=np.array([-0.2, -0.8])):
            response = score_demo(request, loaded.estimator, model_sha256=loaded.model_sha256)
        validate_response(response, request)
        self.assertEqual(response["rows"][0], {"id": "demo-a", "score": 0.8, "rank": 1})
        self.assertIs(response["source_reconciled"], False)

    def test_deserializer_uses_verified_bytes_despite_file_replacement(self):
        def deserialize(stream):
            self.model_path.write_bytes(b"changed after verification")
            self.assertIsInstance(stream, io.BytesIO)
            self.assertEqual(stream.read(), ARTIFICIAL_BYTES)
            return self.model
        self.deserialize.side_effect = deserialize
        self.assertEqual(self.load().model_sha256, self.model_hash)

    def test_tampered_artifact_or_metadata_never_reaches_deserializer(self):
        for path, original, diagnostic in (
            (self.model_path, ARTIFICIAL_BYTES, "DEMO_MODEL_HASH"),
            (self.metadata_path, self.metadata_bytes, "DEMO_METADATA_HASH"),
        ):
            with self.subTest(path=path.name):
                path.write_bytes(original + b"tampered")
                with self.assertRaisesRegex(ValueError, diagnostic):
                    self.load()
                path.write_bytes(original)
        self.deserialize.assert_not_called()

    def test_missing_trust_anchor_is_rejected_before_file_io(self):
        for name in ("EXPECTED_MODEL_SHA256", "EXPECTED_METADATA_SHA256"):
            for invalid in (None, "", "g" * 64, "A" * 64):
                with self.subTest(name=name, value=invalid), \
                        patch.object(self.api, name, invalid), \
                        patch.object(Path, "read_bytes", side_effect=AssertionError("file read")), \
                        self.assertRaisesRegex(ValueError, "DEMO_TRUST_ANCHOR"):
                    self.load()
        self.deserialize.assert_not_called()

    def test_runtime_mismatch_rejected_before_file_io(self):
        for dependency in self.api.RUNTIME_VERSIONS:
            versions = dict(self.api.RUNTIME_VERSIONS)
            versions[dependency] = "different"
            self.runtime.return_value = versions
            with self.subTest(dependency=dependency), \
                    patch.object(Path, "read_bytes", side_effect=AssertionError("file read")), \
                    self.assertRaisesRegex(ValueError, "DEMO_RUNTIME_VERSION"):
                self.load()
        self.deserialize.assert_not_called()

    def test_missing_unreadable_or_linked_files_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "DEMO_ARTIFACT_IO"):
            self.api.load_demo_model(self.root / "absent", deserialize=self.deserialize)
        with patch.object(Path, "read_bytes", side_effect=OSError("private path")), \
                self.assertRaisesRegex(ValueError, "^DEMO_ARTIFACT_IO$"):
            self.load()
        # Simulate detection: no Windows symlink privilege or system changes needed.
        for method in ("is_symlink", "is_junction"):
            with patch.object(Path, method, return_value=True), \
                    self.assertRaisesRegex(ValueError, "DEMO_ARTIFACT_PATH"):
                self.load()
        self.deserialize.assert_not_called()

    def test_invalid_metadata_rejected_before_deserialization(self):
        variants = [b"{invalid", b"[]", b'{"algorithm":"x","algorithm":"IsolationForest"}',
                    b'{"value":NaN}']
        for key, value in (("algorithm", "RandomForest"), ("feature_count", 18),
                           ("features", list(reversed(FEATURE_NAMES))),
                           ("contamination", 0.1), ("n_estimators", 100),
                           ("random_state", True)):
            metadata = copy.deepcopy(self.metadata)
            metadata[key] = value
            variants.append(json.dumps(metadata).encode())
        for content in variants:
            with self.subTest(content=content):
                self.write_trusted_synthetic_metadata(content)
                with self.assertRaisesRegex(ValueError, "DEMO_METADATA"):
                    self.load()
        self.deserialize.assert_not_called()

    def test_wrong_type_and_unfitted_estimators_are_rejected(self):
        class OtherIsolationForest(IsolationForest):
            pass

        for model in (object(), ExtraTreeRegressor(), IsolationForest(**PARAMETERS),
                      OtherIsolationForest(**PARAMETERS)):
            self.deserialize.return_value = model
            with self.subTest(model=type(model)), self.assertRaisesRegex(
                ValueError, "DEMO_ESTIMATOR_(TYPE|STATE)"
            ):
                self.load()

    def test_legacy_state_rejections(self):
        for attribute, value in (
            ("n_features_in_", 18), ("n_features_in_", True),
            ("feature_names_in_", np.array(list(reversed(FEATURE_NAMES)))),
            ("feature_names_in_", None), ("feature_names_in_", np.array("scalar")),
            ("estimators_", []), ("estimators_", [ExtraTreeRegressor()] * 200),
            ("estimators_features_", [np.arange(18)] * 200),
            ("max_samples_", 128), ("_n_samples", 123),
            ("offset_", float("nan")), ("offset_", True), ("offset_", OFFSET + 0.01),
        ):
            model = simulated_model()
            setattr(model, attribute, value)
            self.deserialize.return_value = model
            with self.subTest(attribute=attribute), self.assertRaisesRegex(
                ValueError, "DEMO_ESTIMATOR_STATE"
            ):
                self.load()

    def test_every_legacy_parameter_is_checked(self):
        changes = {"n_estimators": 100, "contamination": 0.1, "random_state": 7,
                   "n_jobs": 1, "max_samples": 128, "max_features": 0.5,
                   "bootstrap": True, "warm_start": True, "verbose": 1}
        for parameter, value in changes.items():
            model = simulated_model()
            model.set_params(**{parameter: value})
            self.deserialize.return_value = model
            with self.subTest(parameter=parameter), self.assertRaisesRegex(
                ValueError, "DEMO_ESTIMATOR_PARAMETERS"
            ):
                self.load()

    def test_deserialization_error_is_sanitized_and_not_retried(self):
        streams = []

        def fail(stream):
            streams.append(stream)
            raise RuntimeError("private model detail")

        self.deserialize.side_effect = fail
        with self.assertRaisesRegex(ValueError, "^DEMO_DESERIALIZATION$") as caught:
            self.load()
        self.deserialize.assert_called_once()
        self.assertTrue(caught.exception.__suppress_context__)
        self.assertTrue(streams[0].closed)

    def test_sklearn_version_warning_is_rejected_without_leaking_warning(self):
        def incompatible(stream):
            warnings.warn(InconsistentVersionWarning(
                estimator_name="private", current_sklearn_version="new",
                original_sklearn_version="old",
            ), stacklevel=2)
            return self.model
        self.deserialize.side_effect = incompatible
        with warnings.catch_warnings(record=True) as emitted, \
                self.assertRaisesRegex(ValueError, "^DEMO_MODEL_VERSION$"):
            self.load()
        self.assertEqual(emitted, [])

    def test_joblib_adapter_is_replaceable_without_real_unpickling(self):
        stream = io.BytesIO(ARTIFICIAL_BYTES)
        with patch("joblib.load", return_value=self.model) as simulated_load:
            self.assertIs(self.api.deserialize_joblib(stream), self.model)
            simulated_load.assert_called_once_with(stream)

    def test_default_adapter_receives_verified_stream_and_closes_it(self):
        streams = []

        def simulated_load(stream):
            self.assertEqual(stream.read(), ARTIFICIAL_BYTES)
            streams.append(stream)
            return self.model

        with patch("joblib.load", side_effect=simulated_load) as mocked:
            loaded = self.api.load_demo_model(self.root)
            mocked.assert_called_once()
        self.assertIs(loaded.estimator, self.model)
        self.assertTrue(streams[0].closed)

    def test_invalid_deserializer_is_refused_before_io(self):
        with patch.object(Path, "read_bytes", side_effect=AssertionError("file read")), \
                self.assertRaisesRegex(TypeError, "DEMO_DESERIALIZER"):
            self.api.load_demo_model(self.root, deserialize="not callable")

    def test_result_keeps_verified_identity_if_module_configuration_changes(self):
        def deserialize(stream):
            self.api.EXPECTED_MODEL_SHA256 = "0" * 64
            return self.model
        self.deserialize.side_effect = deserialize
        self.assertEqual(self.load().model_sha256, self.model_hash)


class DemoLoaderReferenceTests(unittest.TestCase):
    def test_import_does_not_open_artifacts_or_deserialize(self):
        from ml.scripts import invoice_demo_loader as api

        with patch.object(Path, "read_bytes", side_effect=AssertionError("artifact read")), \
                patch("joblib.load", side_effect=AssertionError("unpickle")) as unpickle, \
                patch("socket.socket.connect", side_effect=AssertionError("network")) as network:
            importlib.reload(api)
        unpickle.assert_not_called()
        network.assert_not_called()

    def test_reviewed_hash_anchors_and_runtime_pins_match_documented_sources(self):
        from ml.scripts import invoice_demo_loader as api

        root = Path(__file__).resolve().parents[2]
        protocol = (root / "docs/invoice_academic_evaluation_protocol.md").read_text(encoding="utf-8")
        self.assertIn(api.EXPECTED_MODEL_SHA256, protocol)
        self.assertIn(api.EXPECTED_METADATA_SHA256, protocol)
        requirements = (root / "requirements.txt").read_text(encoding="utf-8").splitlines()
        for package, version in api.RUNTIME_VERSIONS.items():
            if package == "python":
                self.assertEqual(version, (root / ".python-version").read_text().strip())
            else:
                self.assertIn(f"{package}=={version}", requirements)


if __name__ == "__main__":
    unittest.main()
