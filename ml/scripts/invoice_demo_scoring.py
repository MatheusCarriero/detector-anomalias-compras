"""In-memory demo scoring; no artifact loading or scientific evaluation imports."""

import math
import re
from copy import deepcopy
from numbers import Integral, Real

import numpy as np
import pandas as pd

from ml.scripts.invoice_demo_contract import (
    FEATURE_NAMES,
    VERSION,
    validate_request,
    validate_response,
)


def _validated_score_method(estimator):
    names = getattr(estimator, "feature_names_in_", None)
    count = getattr(estimator, "n_features_in_", None)
    method = getattr(estimator, "score_samples", None)
    names_valid = isinstance(names, (list, tuple)) or (
        type(names) is np.ndarray and names.ndim == 1
    )
    if (not names_valid
            or not all(isinstance(name, str) for name in names)
            or tuple(names) != FEATURE_NAMES
            or isinstance(count, (bool, np.bool_))
            or not isinstance(count, Integral)
            or count != len(FEATURE_NAMES)
            or not callable(method)):
        raise ValueError("DEMO_ESTIMATOR_FEATURES")
    return method


def _score_values(output, row_count):
    # Reject labelled Series, nested arrays, booleans and implicit string coercion.
    if type(output) is np.ndarray:
        valid = output.shape == (row_count,) and output.dtype.kind in "iuf"
    else:
        valid = type(output) in (list, tuple) and len(output) == row_count
    if not valid:
        raise ValueError("DEMO_SCORE_OUTPUT")
    scores = []
    for value in output:
        numeric = isinstance(value, Real) and not isinstance(value, (bool, np.bool_))
        if not numeric:
            raise ValueError("DEMO_SCORE_OUTPUT")
        try:
            score = -float(value)
        except (TypeError, ValueError, OverflowError):
            raise ValueError("DEMO_SCORE_OUTPUT") from None
        if not math.isfinite(score):
            raise ValueError("DEMO_SCORE_OUTPUT")
        scores.append(score)
    return scores


def score_demo(request, estimator, *, model_sha256):
    """Score a validated synthetic batch once, using a caller-owned estimator.

    The trusted caller must supply an already fitted/validated estimator and the
    SHA-256 of the corresponding artifact. This function checks metadata/order
    and hash format; it neither loads files nor establishes artifact provenance.
    score_samples must return one value per input row, in the same order.
    """
    validate_request(request)
    if type(model_sha256) is not str or re.fullmatch(r"[0-9a-f]{64}", model_sha256) is None:
        raise ValueError("DEMO_MODEL_ID")
    score_samples = _validated_score_method(estimator)
    batch = deepcopy(request)
    identifiers = tuple(row["id"] for row in batch["rows"])
    frame = pd.DataFrame(
        [row["values"] for row in batch["rows"]], columns=FEATURE_NAMES, dtype=float,
    )
    original_frame = frame.copy(deep=True)
    try:
        output = score_samples(frame)
    except Exception:  # noqa: BLE001 - Estimator failures expose only a fixed diagnostic.
        raise ValueError("DEMO_SCORING_FAILED") from None
    if not frame.equals(original_frame):
        raise ValueError("DEMO_SCORING_INPUT_CHANGED")
    scores = _score_values(output, len(identifiers))
    rows = [{"id": identifier, "score": score}
            for identifier, score in zip(identifiers, scores, strict=True)]
    rows.sort(key=lambda row: (-row["score"], row["id"]))
    for rank, row in enumerate(rows, 1):
        row["rank"] = rank
    response = {
        "contract": VERSION,
        "origin": batch["origin"],
        "source_reconciled": False,
        "model_sha256": model_sha256,
        "score_kind": "negative_score_samples",
        "score_direction": "higher_is_more_anomalous",
        "rows": rows,
    }
    validate_response(response, batch)
    return response
