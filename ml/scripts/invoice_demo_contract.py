"""Pure demo contract: no model, dataset, network, scoring or persistence I/O."""

import math
import re

VERSION = "invoice-demo/1.0"
# Published transport order. A static regression test checks the scientific
# FEATURES constant without importing the training module or its dependencies.
FEATURE_NAMES = (
    "invoice_amount", "log_invoice_amount", "supplier_age_days",
    "supplier_frequency", "country_frequency", "amount_vs_supplier_mean",
    "supplier_amount_zscore", "department_frequency", "amount_vs_department_mean",
    "supplier_department_frequency", "payment_terms_days", "invoice_type_encoded",
    "submission_hour_sin", "submission_hour_cos", "day_of_week_sin",
    "day_of_week_cos", "month_sin", "month_cos", "is_weekend",
)
MAX_ROWS = 100  # Initial demo limit, not a measured capacity or scientific rule.


def _keys(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError("DEMO_SCHEMA")


def _number(value):
    try:
        valid = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError("DEMO_NUMBER")


def validate_request(payload):
    """Validate an already decoded JSON object; never infer missing features.

    The synthetic marker is a declaration, not proof of data provenance. The
    first demo must use the reviewed fixture, not unrestricted external uploads.
    """
    _keys(payload, ("contract", "origin", "feature_names", "rows"))
    if payload["contract"] != VERSION or payload["origin"] != "synthetic":
        raise ValueError("DEMO_SCOPE")
    if payload["feature_names"] != list(FEATURE_NAMES):
        raise ValueError("DEMO_FEATURE_ORDER")
    rows = payload["rows"]
    if type(rows) is not list or not 1 <= len(rows) <= MAX_ROWS:
        raise ValueError("DEMO_BATCH")
    ids = set()
    for row in rows:
        _keys(row, ("id", "values"))
        identifier = row["id"]
        if (type(identifier) is not str
                or re.fullmatch(r"demo-[a-z0-9-]{1,40}", identifier) is None
                or identifier in ids):
            raise ValueError("DEMO_ID")
        ids.add(identifier)
        values = row["values"]
        if type(values) is not list or len(values) != len(FEATURE_NAMES):
            raise ValueError("DEMO_FEATURE_COUNT")
        for value in values:
            _number(value)


def validate_response(response, request):
    """Validate future scoring output. No scores or rankings are calculated here."""
    validate_request(request)
    _keys(response, ("contract", "origin", "source_reconciled", "model_sha256",
                     "score_kind", "score_direction", "rows"))
    if (response["contract"] != VERSION or response["origin"] != "synthetic"
            or response["source_reconciled"] is not False
            or response["score_kind"] != "negative_score_samples"
            or response["score_direction"] != "higher_is_more_anomalous"):
        raise ValueError("DEMO_OUTPUT_SEMANTICS")
    digest = response["model_sha256"]
    if type(digest) is not str or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise ValueError("DEMO_MODEL_ID")
    rows = response["rows"]
    if type(rows) is not list or len(rows) != len(request["rows"]):
        raise ValueError("DEMO_OUTPUT_ROWS")
    expected = {row["id"] for row in request["rows"]}
    seen = set()
    previous = None
    for rank, row in enumerate(rows, 1):
        _keys(row, ("id", "score", "rank"))
        identifier = row["id"]
        if type(identifier) is not str or identifier not in expected or identifier in seen:
            raise ValueError("DEMO_OUTPUT_ID")
        seen.add(identifier)
        _number(row["score"])
        if type(row["rank"]) is not int or row["rank"] != rank:
            raise ValueError("DEMO_RANK")
        key = (-row["score"], identifier)
        if previous is not None and key < previous:
            raise ValueError("DEMO_RANK_ORDER")
        previous = key
