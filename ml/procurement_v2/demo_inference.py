"""One authorized synthetic operation, using the unchanged P5.14 loader.

No I/O on import, fitting, thresholds, persistence or user-supplied model paths.
The adapter verifies the source; the loader verifies the model and metadata.
An unavailable preparation never imports the artifact module or loads a model.
"""

import math
from numbers import Real

from ml.procurement_v2 import demo
from ml.procurement_v2.batch import MATRIX_FEATURES

CONTRACT_VERSION = "procurement-demo-inference/1.0"


class InferenceError(ValueError):
    """Stable technical refusal, without paths or library messages."""


def _artifact():
    from ml.procurement_v2 import artifact
    return artifact


def _prepared(result, identity):
    if (type(result) is not dict or result.get("contract") != demo.CONTRACT_VERSION
            or result.get("source") != demo.source_identity() or result.get("operation") != identity
            or result.get("feature_names") != list(MATRIX_FEATURES)):
        raise InferenceError("PREPARATION_INVALID")
    status, values, reasons = result.get("status"), result.get("values"), result.get("unavailability")
    if status == "unavailable":
        if values is not None or type(reasons) is not dict or not reasons:
            raise InferenceError("PREPARATION_INVALID")
        return
    if status != "eligible" or reasons != {} or type(values) is not list or len(values) != 5:
        raise InferenceError("PREPARATION_INVALID")
    try:
        if (any(isinstance(v, bool) or not isinstance(v, Real) or not math.isfinite(v) for v in values)
                or values[0] <= 0 or values[1] <= 0 or values[2] < 0
                or any(v < 0 or int(v) != v for v in values[3:])):
            raise InferenceError("PREPARATION_INVALID")
    except (OverflowError, TypeError):
        raise InferenceError("PREPARATION_INVALID") from None


def run_operation(request):
    """Prepare then score exactly once; return traceable, deterministic output."""
    identity = demo.validate_request(request)
    prepared = demo.prepare_operation(request)
    _prepared(prepared, identity)
    result = {"contract": CONTRACT_VERSION, "preparation": prepared, "status": "unavailable",
              "anomaly_score": None, "model": None, "score_convention": "-score_samples",
              "score_semantics": "statistical_anomaly", "score_direction": "higher_is_more_anomalous"}
    if prepared["status"] == "unavailable":
        return result
    artifact = _artifact()
    try:
        loaded = artifact.load_baseline()
        if loaded.artifact_id != artifact.ARTIFACT_ID or loaded.model_sha256 != artifact.TRUSTED_MODEL_SHA256:
            raise InferenceError("MODEL_INCOMPATIBLE")
        # Public P5.14 interface constructs the ordered DataFrame, validates it,
        # calls only score_samples, and already inverts its sign. Never negate twice.
        score = loaded.score(prepared["values"], feature_names=prepared["feature_names"])
    except artifact.ArtifactError as exc:
        code = {"artifact_unavailable": "MODEL_UNAVAILABLE", "hash_mismatch": "MODEL_INTEGRITY",
                "artifact_path": "MODEL_INTEGRITY", "artifact_size": "MODEL_INTEGRITY",
                "trust_not_configured": "MODEL_INTEGRITY", "deserialization": "MODEL_LOAD_FAILED",
                "scoring_output": "INVALID_SCORE", "scoring_failed": "SCORING_FAILED"}.get(
                    str(exc), "MODEL_INCOMPATIBLE")
        raise InferenceError(code) from None
    if isinstance(score, bool) or not isinstance(score, Real) or not math.isfinite(score):
        raise InferenceError("INVALID_SCORE")
    result.update(status="scored", anomaly_score=float(score), model={
        "domain": "procurement_v2", "artifact_id": loaded.artifact_id,
        "model_sha256": loaded.model_sha256, "metadata_sha256": artifact.TRUSTED_METADATA_SHA256,
    })
    return result
