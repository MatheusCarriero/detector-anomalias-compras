"""Explicit local Invoice loader. Importing this module never reads an artifact."""

import hashlib
import json
import math
import platform
import re
import warnings
from dataclasses import dataclass
from io import BytesIO
from numbers import Integral, Real
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import scipy
import sklearn
from sklearn.ensemble import IsolationForest
from sklearn.exceptions import InconsistentVersionWarning
from sklearn.tree import ExtraTreeRegressor
from sklearn.utils.validation import check_is_fitted

from ml.scripts.invoice_demo_contract import FEATURE_NAMES
from ml.scripts.invoice_demo_scoring import _validated_score_method

MODEL_PATH = "ml/models/isolation_forest.joblib"
METADATA_PATH = "ml/models/model_metadata.json"
# Reviewed identities: docs/invoice_academic_evaluation_protocol.md, section 4.
# Never derive these expected values from the files being loaded or request data.
EXPECTED_MODEL_SHA256 = "c9c0f51a9c962fac5ea6b34db5e0b74f09c120896bf9e7bf3a87418df2adba1b"
EXPECTED_METADATA_SHA256 = "ba07485e8dda458e45376b6edc4bd164926efe2c6ca8385cde32f7309db86595"
PARAMETERS = {
    "n_estimators": 200, "contamination": 0.22, "random_state": 42, "n_jobs": -1,
    "max_samples": "auto", "max_features": 1.0, "bootstrap": False,
    "warm_start": False, "verbose": 0,
}
LEGACY_OFFSET = -0.5211491197816622
# Current pinned environment, not a claim about the unknown original fit environment.
RUNTIME_VERSIONS = {
    "python": "3.14.3", "numpy": "2.5.2", "pandas": "2.3.3",
    "scikit-learn": "1.9.0", "joblib": "1.6.0", "scipy": "1.18.1",
}


@dataclass(frozen=True)
class LoadedDemoModel:
    estimator: IsolationForest
    model_sha256: str


def _runtime_versions():
    return {"python": platform.python_version(), "numpy": np.__version__,
            "pandas": pd.__version__, "scikit-learn": sklearn.__version__,
            "joblib": joblib.__version__, "scipy": scipy.__version__}


def deserialize_joblib(stream):
    """Trusted adapter, called only after hash checks; replace with a mock in tests."""
    return joblib.load(stream)


def _verified_bytes(root, relative_path, expected_hash, diagnostic):
    path = root / relative_path
    try:
        for component in (root, root / "ml", root / "ml/models", path):
            if component.is_symlink() or component.is_junction():
                raise ValueError("DEMO_ARTIFACT_PATH")
        if path.resolve(strict=True) != root.resolve(strict=True) / relative_path or not path.is_file():
            raise ValueError("DEMO_ARTIFACT_PATH")
        content = path.read_bytes()
    except OSError:
        raise ValueError("DEMO_ARTIFACT_IO") from None
    if hashlib.sha256(content).hexdigest() != expected_hash:
        raise ValueError(diagnostic)
    return content


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("DEMO_METADATA")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("DEMO_METADATA")


def _canonical(value):
    return json.dumps(value, sort_keys=True, allow_nan=False)


def _validate_metadata(content):
    required = {"algorithm": "IsolationForest", "feature_count": 19,
                "features": list(FEATURE_NAMES),
                **{key: PARAMETERS[key] for key in ("n_estimators", "contamination", "random_state")}}
    try:
        metadata = json.loads(content, object_pairs_hook=_unique_pairs,
                              parse_constant=_reject_constant)
        valid = type(metadata) is dict and all(
            key in metadata and _canonical(metadata[key]) == _canonical(value)
            for key, value in required.items()
        )
        if not valid:
            raise ValueError("DEMO_METADATA")
    except (ValueError, TypeError, UnicodeError):
        raise ValueError("DEMO_METADATA") from None


def _integer_is(value, expected):
    return (isinstance(value, Integral) and not isinstance(value, (bool, np.bool_))
            and value == expected)


def _validate_estimator(model):
    if type(model) is not IsolationForest:
        raise ValueError("DEMO_ESTIMATOR_TYPE")
    try:
        if _canonical(model.get_params(deep=False)) != _canonical(PARAMETERS):
            raise ValueError("DEMO_ESTIMATOR_PARAMETERS")
    except (AttributeError, TypeError, ValueError):
        raise ValueError("DEMO_ESTIMATOR_PARAMETERS") from None
    try:
        check_is_fitted(model, attributes=["estimators_", "estimators_features_", "offset_",
                                          "max_samples_", "_n_samples"])
        _validated_score_method(model)  # P1 checks exact feature order/count; no scoring.
        if (len(model.estimators_) != 200 or len(model.estimators_features_) != 200
                or not _integer_is(model.max_samples_, 256)
                or not _integer_is(model._n_samples, 210000)
                or isinstance(model.offset_, (bool, np.bool_))
                or not isinstance(model.offset_, Real)
                or not math.isfinite(model.offset_) or float(model.offset_) != LEGACY_OFFSET):
            raise ValueError("DEMO_ESTIMATOR_STATE")
        for tree, features in zip(model.estimators_, model.estimators_features_, strict=True):
            if (type(tree) is not ExtraTreeRegressor
                    or not _integer_is(getattr(tree, "n_features_in_", None), 19)
                    or type(features) is not np.ndarray or features.dtype.kind not in "iu"
                    or not np.array_equal(features, np.arange(19))):
                raise ValueError("DEMO_ESTIMATOR_STATE")
            check_is_fitted(tree, attributes=["tree_"])
    except (AttributeError, TypeError, ValueError, OverflowError):
        raise ValueError("DEMO_ESTIMATOR_STATE") from None


def load_demo_model(project_root, *, deserialize=None):
    """Explicitly load the pinned local artifact, without fit, scoring or evaluation.

    project_root and the optional deserializer are trusted application/test
    configuration, never request inputs. Hashes are fixed reviewed references.
    Deserialization can execute code: type/state checks afterwards are not a
    sandbox, and SHA-256 does not establish historical training provenance.
    """
    model_hash, metadata_hash = EXPECTED_MODEL_SHA256, EXPECTED_METADATA_SHA256
    for digest in (model_hash, metadata_hash):
        if type(digest) is not str or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ValueError("DEMO_TRUST_ANCHOR")
    if _runtime_versions() != RUNTIME_VERSIONS:
        raise ValueError("DEMO_RUNTIME_VERSION")
    deserializer = deserialize_joblib if deserialize is None else deserialize
    if not callable(deserializer):
        raise TypeError("DEMO_DESERIALIZER")
    root = Path(project_root).absolute()
    metadata = _verified_bytes(root, METADATA_PATH, metadata_hash, "DEMO_METADATA_HASH")
    _validate_metadata(metadata)
    content = _verified_bytes(root, MODEL_PATH, model_hash, "DEMO_MODEL_HASH")
    try:
        # Record other warnings rather than exposing arbitrary messages to callers.
        with warnings.catch_warnings(record=True), BytesIO(content) as stream:
            warnings.simplefilter("error", InconsistentVersionWarning)
            model = deserializer(stream)
    except InconsistentVersionWarning:
        raise ValueError("DEMO_MODEL_VERSION") from None
    except Exception:  # noqa: BLE001 - Do not leak arbitrary deserializer errors.
        raise ValueError("DEMO_DESERIALIZATION") from None
    _validate_estimator(model)
    return LoadedDemoModel(estimator=model, model_sha256=model_hash)
