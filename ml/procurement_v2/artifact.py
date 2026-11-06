"""Trusted local Procurement V2 artifact; no training or file access on import.

Only load_baseline() opens the fixed V2 bundle. joblib is executable pickle:
trust comes from the independently pinned model AND metadata hashes in this
module, not the adjacent checksum file. Changing pins requires a reviewed new
artifact. Never use this loader for uploads or Invoice V1.

persist_baseline() accepts an already verified estimator, never fits, verifies
fixed reference scores and a serialization roundtrip before creating any files.
The caller remains responsible for the authorized fit and historical comparison.
"""

import copy
import hashlib
import io
import json
import math
import sys
import warnings
from importlib.metadata import version
from numbers import Real
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.exceptions import NotFittedError
from sklearn.tree import ExtraTreeRegressor
from sklearn.utils.validation import check_is_fitted

from ml.procurement_v2.baseline import EXPERIMENT_VERSION as BASELINE_VERSION
from ml.procurement_v2.baseline import MODEL_PARAMETERS
from ml.procurement_v2.batch import BATCH_VERSION as BATCH_CONTRACT
from ml.procurement_v2.batch import MATRIX_FEATURES as FEATURE_NAMES
from ml.procurement_v2.features import CONTRACT_VERSION as FEATURE_CONTRACT

ARTIFACT_CONTRACT = "procurement-baseline-artifact/1.0"
ARTIFACT_ID = "procurement_v2_isolation_forest_p5_9_v1"
CSV_SHA256 = "fba22a467e5dd800a0af960930d2ca5e2ecbd9d2bc747e37304867d8d031ae21"
MATRIX_SHA256 = "2b7844262ba4df7c10e3455c12ea3102edddf283c1a90c0d8d2590c8d3b09183"
EXPECTED_VERSIONS = {
    "python": "3.14.3", "scikit-learn": "1.9.0", "numpy": "2.5.2",
    "pandas": "2.3.3", "joblib": "1.6.0", "scipy": "1.18.1",
}
PARAMETERS = {**MODEL_PARAMETERS, "verbose": 0}
IMPLEMENTATION_SHA256 = {
    "features.py": "57ce275bfa802b3cfa28dc4b494338786e6192ed39ae4f101ec8d08fe0dee825",
    "batch.py": "2433f3bfe463a703a36c10f82945605e61c8469de55195b8f6433179468da452",
    "baseline.py": "1f3048853dbc7ec8792c13270f4b838392b8d4e79f9e3a26a05106ad569d1211",
}
# P5.14: independently pinned after the one authorized fit and exact checks.
# These are release trust anchors; never derive/update them from runtime files.
TRUSTED_MODEL_SHA256 = "fa9f21654626307cf139574707fccae543d9f18ea6f6fa272b8c3053b34bc56d"
TRUSTED_METADATA_SHA256 = "3a78f5014c24cbb3da3bf9e83955b6866b4d18d309fec50cf0efcb779f6a2ed1"
_ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts" / "baseline_v1"
_MODEL_LIMIT = 64 * 1024 * 1024
_METADATA_LIMIT = 2 * 1024 * 1024


class ArtifactError(ValueError):
    """Explicit, sanitized refusal; never silently changes versions or paths."""


def _sha(payload):
    return hashlib.sha256(payload).hexdigest()


def _runtime_versions():
    return {"python": sys.version.split()[0],
            **{name: version(name) for name in EXPECTED_VERSIONS if name != "python"}}


def _compatible_runtime():
    if _runtime_versions() != EXPECTED_VERSIONS:
        raise ArtifactError("runtime_versions")
    for name, expected in IMPLEMENTATION_SHA256.items():
        if _sha(Path(__file__).with_name(name).read_bytes()) != expected:
            raise ArtifactError("implementation_hash")


def _directory():
    # Reject symlink/junction redirection, including ancestors of this fixed path.
    if _ARTIFACT_DIR.resolve() != _ARTIFACT_DIR.absolute():
        raise ArtifactError("artifact_path")
    return _ARTIFACT_DIR


def _validate_metadata(metadata, *, bundled):
    try:
        expected = {
            "artifact_contract": ARTIFACT_CONTRACT, "artifact_id": ARTIFACT_ID,
            "domain": "procurement_v2", "experiment": BASELINE_VERSION,
            "feature_contract": FEATURE_CONTRACT, "batch_contract": BATCH_CONTRACT,
            "feature_names": list(FEATURE_NAMES), "parameters": PARAMETERS,
            "versions": EXPECTED_VERSIONS, "score_convention": "-score_samples",
            "score_semantics": "statistical_anomaly", "preprocessing": "none",
            "operational_threshold": None,
        }
        if any(metadata[key] != value for key, value in expected.items()):
            raise ArtifactError("metadata_contract")
        source = metadata["source"]
        if (source["source_id"] != "procurement-spend" or source["source_version"] != CSV_SHA256
                or source["entity_namespace"] != "procurement-spend-synthetic"
                or source["origin"] != "synthetic" or source["monetary_unit"] != "unspecified_source_unit"
                or source["temporal_assumption"] != "available_at_order_no_revisions"):
            raise ArtifactError("metadata_source")
        training = metadata["training"]
        for key, value in {"period": "development", "start": "2023-04-01", "end_exclusive": "2025-01-01",
                           "rows": 23671, "features": 5, "matrix_sha256": MATRIX_SHA256}.items():
            if training[key] != value:
                raise ArtifactError("metadata_training")
        verification = metadata["verification"]
        if (type(verification["fit_calls"]) is not int or verification["fit_calls"] != 1
                or verification["atol"] != 0 or verification["rtol"] != 0
                or verification["historical_statistics_match"] is not True
                or verification["fixed_references_match"] is not True):
            raise ArtifactError("metadata_verification")
        if not isinstance(metadata["limitations"], list) or not metadata["limitations"]:
            raise ArtifactError("metadata_limitations")
        if bundled and (metadata["artifact"]["filename"] != "model.joblib"
                        or metadata["artifact"]["sha256"] != TRUSTED_MODEL_SHA256
                        or metadata["artifact"]["format"] != "joblib-pickle5-zlib3"):
            raise ArtifactError("metadata_artifact")
    except (KeyError, TypeError, AttributeError):
        raise ArtifactError("metadata_structure") from None


def _validate_estimator(model):
    if type(model) is not IsolationForest:
        raise ArtifactError("estimator_type")
    try:
        check_is_fitted(model, ["estimators_", "estimators_features_", "feature_names_in_",
                               "n_features_in_", "max_samples_", "offset_"])
    except (NotFittedError, TypeError, ValueError, AttributeError):
        raise ArtifactError("estimator_unfitted") from None
    if (model.n_features_in_ != 5 or list(model.feature_names_in_) != list(FEATURE_NAMES)
            or model.get_params(deep=False) != PARAMETERS or model.max_samples_ != 256
            or model.offset_ != -.5 or len(model.estimators_) != 200
            or len(model.estimators_features_) != 200):
        raise ArtifactError("estimator_contract")
    for tree, columns in zip(model.estimators_, model.estimators_features_, strict=True):
        if type(tree) is not ExtraTreeRegressor or not np.array_equal(columns, np.arange(5)):
            raise ArtifactError("estimator_trees")
        try:
            check_is_fitted(tree, ["tree_", "n_features_in_"])
            if tree.n_features_in_ != 5 or tree.tree_.node_count < 1:
                raise ArtifactError("estimator_trees")
        except (NotFittedError, TypeError, ValueError, AttributeError):
            raise ArtifactError("estimator_trees") from None


def _frame(rows, feature_names):
    if not isinstance(feature_names, (list, tuple)) or tuple(feature_names) != FEATURE_NAMES:
        raise ArtifactError("feature_order")
    if not isinstance(rows, (list, tuple)) or not rows:
        raise ArtifactError("feature_values")
    for row in rows:
        if not isinstance(row, (list, tuple)) or len(row) != 5:
            raise ArtifactError("feature_values")
        try:
            if any(isinstance(v, (bool, np.bool_)) or not isinstance(v, Real)
                   or not math.isfinite(float(v)) for v in row):
                raise ArtifactError("feature_values")
            if row[0] <= 0 or row[1] <= 0 or row[2] < 0:
                raise ArtifactError("feature_values")
            if any(v < 0 or float(v) != int(v) for v in row[3:]):
                raise ArtifactError("feature_values")
        except (TypeError, OverflowError):
            raise ArtifactError("feature_values") from None
    with np.errstate(over="ignore", invalid="ignore"):
        values = np.asarray(rows, dtype=float)
        if not np.isfinite(values.astype(np.float32)).all():
            raise ArtifactError("feature_values")
    return pd.DataFrame(values, columns=list(FEATURE_NAMES))


def _score(model, frame):
    try:
        raw = np.asarray(model.score_samples(frame))
        if (raw.shape != (len(frame),) or not np.issubdtype(raw.dtype, np.number)
                or not np.isfinite(raw).all()):
            raise ArtifactError("scoring_output")
        return -raw.astype(float)
    except ArtifactError:
        raise
    except Exception:  # noqa: BLE001 - sanitize estimator-library failures at the scoring boundary.
        raise ArtifactError("scoring_failed") from None


def _deserialize(payload):
    # Byte stream avoids reopening a path after hashing (TOCTOU).
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            return joblib.load(io.BytesIO(payload))
    except Exception:  # noqa: BLE001 - never expose raw pickle/library exceptions to callers.
        raise ArtifactError("deserialization") from None


class _FrozenBaseline:
    """Local anomaly scoring only; inputs must already follow the P5.8 contract."""

    def __init__(self, estimator, model_sha256):
        self._estimator = estimator
        self.model_sha256 = model_sha256
        self.artifact_id = ARTIFACT_ID

    def score(self, values, *, feature_names):
        """Return -score_samples for exactly one prepared row, not a probability."""
        return float(_score(self._estimator, _frame([values], feature_names))[0])


def _read_pinned(name, expected, limit):
    if (type(expected) is not str or len(expected) != 64
            or any(c not in "0123456789abcdef" for c in expected)):
        raise ArtifactError("trust_not_configured")
    path = _directory() / name
    if path.resolve() != path.absolute():
        raise ArtifactError("artifact_path")
    try:
        with path.open("rb") as stream:
            payload = stream.read(limit + 1)
    except OSError:
        raise ArtifactError("artifact_unavailable") from None
    if len(payload) > limit:
        raise ArtifactError("artifact_size")
    if _sha(payload) != expected:
        raise ArtifactError("hash_mismatch")
    return payload


def load_baseline():
    """Load only the fixed, independently hash-pinned V2 artifact; no paths/URLs."""
    _compatible_runtime()
    metadata_bytes = _read_pinned("metadata.json", TRUSTED_METADATA_SHA256, _METADATA_LIMIT)
    try:
        metadata = json.loads(metadata_bytes)
    except (ValueError, UnicodeError):
        raise ArtifactError("metadata_json") from None
    _validate_metadata(metadata, bundled=True)
    payload = _read_pinned("model.joblib", TRUSTED_MODEL_SHA256, _MODEL_LIMIT)
    model = _deserialize(payload)
    _validate_estimator(model)
    return _FrozenBaseline(model, TRUSTED_MODEL_SHA256)


def persist_baseline(model, metadata, *, reference_values, reference_scores):
    """Persist once after strict historical and in-memory roundtrip verification.

    Receives an already fitted estimator: no fit, dataset loading, model path
    argument or trust-pin updates. Leaves incomplete bundles in place on I/O
    failure for inspection; never removes/overwrites any existing directory.
    """
    directory = _directory()
    if directory.exists():
        raise ArtifactError("artifact_exists")
    _compatible_runtime()
    _validate_metadata(metadata, bundled=False)
    _validate_estimator(model)
    frame = _frame(reference_values, FEATURE_NAMES)
    expected = np.asarray(reference_scores, dtype=float)
    before = _score(model, frame)
    if expected.shape != before.shape or not np.isfinite(expected).all() or not np.array_equal(before, expected):
        raise ArtifactError("reference_scores")
    buffer = io.BytesIO()
    joblib.dump(model, buffer, compress=3, protocol=5)
    payload = buffer.getvalue()
    if len(payload) > _MODEL_LIMIT:
        raise ArtifactError("artifact_size")
    restored = _deserialize(payload)  # Bytes just created in this trusted process.
    _validate_estimator(restored)
    if not np.array_equal(_score(restored, frame), before):
        raise ArtifactError("roundtrip_scores")
    document = copy.deepcopy(metadata)
    model_hash = _sha(payload)
    document["artifact"] = {"filename": "model.joblib", "sha256": model_hash, "format": "joblib-pickle5-zlib3"}
    document["verification"]["serialization_roundtrip_exact"] = True
    document["verification"]["serialization_reference_rows"] = len(frame)
    try:
        metadata_bytes = (json.dumps(document, sort_keys=True, indent=2, ensure_ascii=False,
                                     allow_nan=False) + "\n").encode("utf-8")
    except (TypeError, ValueError):
        raise ArtifactError("metadata_json") from None
    if len(metadata_bytes) > _METADATA_LIMIT:
        raise ArtifactError("artifact_size")
    try:
        directory.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise ArtifactError("artifact_exists") from None
    # Metadata written last; until completion no trusted loader can accept bundle.
    for name, content in (("model.joblib", payload),
                          ("model.sha256", f"{model_hash}  model.joblib\n".encode()),
                          ("metadata.json", metadata_bytes)):
        with (directory / name).open("xb") as stream:
            stream.write(content)
    return {"model_sha256": model_hash, "metadata_sha256": _sha(metadata_bytes)}
