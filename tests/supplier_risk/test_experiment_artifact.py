"""Synthetic contract tests for future Supplier experiment evidence."""

import copy
import hashlib
import importlib.util
import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = (
    REPOSITORY_ROOT / "ml" / "supplier_risk" / "scripts" / "experiment_artifact.py"
)
FEATURES_A = [
    "financial_stability_score",
    "on_time_delivery_rate",
    "defect_rate",
    "geopolitical_risk_index",
    "lead_time_days",
    "alternative_suppliers_available",
    "contract_length_months",
    "environmental_compliance",
    "previous_disruptions",
    "supplier_record_count",
]
FEATURES_BY_SCENARIO = {
    "A": FEATURES_A,
    "B": [name for name in FEATURES_A if name != "geopolitical_risk_index"],
    "C": [name for name in FEATURES_A if name != "supplier_record_count"],
    "D": [
        name
        for name in FEATURES_A
        if name not in {"geopolitical_risk_index", "supplier_record_count"}
    ],
}
S1_HASH = "90afadf3c4de0eae96e40b6ed96adcd5b08deca5b96afff5a38b0df92a73c2ac"
S2_HASH = "d6145b0b88d30c383f92038267781c45805b1a5e8f90197d5ff29f722a5efab1"
S1_S2_HASH = "06394624f2cd704e4dd0d91ccd71790d2cf253c14308d9555bd2baeacda0df99"


@pytest.fixture(scope="module")
def artifact_module():
    spec = importlib.util.spec_from_file_location("supplier_experiment_artifact", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def rows():
    return [
        {
            "supplier_id": "s2",
            "split": "validation",
            "y_true": 1,
            "y_pred": 0,
            "probability_class_1": 0.4,
        },
        {
            "supplier_id": "s1",
            "split": "train",
            "y_true": 0,
            "y_pred": 1,
            "probability_class_1": 0.6,
        },
    ]


@pytest.fixture
def metadata():
    return {
        "experiment_name": "synthetic-logistic-a",
        "estimator": "LogisticRegression",
        "scenario": "A",
        "features": FEATURES_A.copy(),
        "parameters": {"C": 1.0, "class_weight": None, "fit_intercept": True},
        "seeds": {"model": 42},
        "versions": {"python": "3.12.0", "scikit-learn": "1.5.0"},
        "input_hashes": {"synthetic_train": "a" * 64},
        "code_sha256": "b" * 64,
        "expected_id_hashes": {"train": S1_HASH, "validation": S2_HASH},
        "notebook_sha256": "c" * 64,
    }


def _one_row(split="validation"):
    return [
        {
            "supplier_id": "s1",
            "split": split,
            "y_true": 0,
            "y_pred": 1,
            "probability_class_1": 0.6,
        }
    ]


def _metadata_for_one(metadata, split="validation", scenario="A"):
    result = copy.deepcopy(metadata)
    result["scenario"] = scenario
    result["features"] = FEATURES_BY_SCENARIO[scenario].copy()
    result["expected_id_hashes"] = {split: S1_HASH}
    return result


def _rewrite(path, transform):
    document = json.loads(path.read_text(encoding="utf-8"))
    transform(document)
    path.write_text(
        json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ),
        encoding="utf-8",
    )


def test_round_trip_canonicalizes_rows_and_returns_validated_envelope(
    artifact_module, tmp_path, rows, metadata,
):
    destination = tmp_path / "nested" / "record.json"

    written = artifact_module.write_experiment_record(destination, rows, metadata)
    envelope = artifact_module.verify_experiment_record(written)

    assert written == destination
    assert envelope["schema_version"] == "1.0.0"
    assert envelope["created_at"].endswith("Z")
    assert envelope["payload"]["domain"] == "supplier_risk"
    assert envelope["payload"]["target"] == "Risk_Level"
    assert envelope["payload"]["record_count"] == 2
    assert [row["supplier_id"] for row in envelope["payload"]["predictions"]] == [
        "s1",
        "s2",
    ]


def test_artifact_id_is_independent_of_input_row_order(
    artifact_module, tmp_path, rows, metadata,
):
    first = artifact_module.write_experiment_record(tmp_path / "first.json", rows, metadata)
    second = artifact_module.write_experiment_record(
        tmp_path / "second.json", list(reversed(rows)), metadata,
    )

    first_envelope = artifact_module.verify_experiment_record(first)
    second_envelope = artifact_module.verify_experiment_record(second)

    assert first_envelope["artifact_id"] == second_envelope["artifact_id"]
    assert first_envelope["payload"] == second_envelope["payload"]


def test_id_fingerprint_uses_sorted_ids_and_canonical_utf8_json(
    artifact_module, tmp_path, metadata,
):
    rows = [
        {**_one_row("train")[0], "supplier_id": "s2"},
        {**_one_row("train")[0], "supplier_id": "s1"},
    ]
    metadata = copy.deepcopy(metadata)
    metadata["expected_id_hashes"] = {"train": S1_S2_HASH}

    path = artifact_module.write_experiment_record(tmp_path / "record.json", rows, metadata)

    assert artifact_module.verify_experiment_record(path)["payload"]["id_hashes"] == {
        "train": S1_S2_HASH,
    }


def test_expected_id_hash_mismatch_is_rejected_before_writing(
    artifact_module, tmp_path, metadata,
):
    destination = tmp_path / "new-parent" / "record.json"
    metadata = _metadata_for_one(metadata)
    metadata["expected_id_hashes"]["validation"] = "0" * 64

    with pytest.raises(ValueError, match="expected_id_hashes"):
        artifact_module.write_experiment_record(destination, _one_row(), metadata)

    assert not destination.parent.exists()


def test_tampering_is_detected_by_payload_digest(
    artifact_module, tmp_path, rows, metadata,
):
    path = artifact_module.write_experiment_record(tmp_path / "record.json", rows, metadata)
    _rewrite(path, lambda document: document["payload"]["predictions"][0].update(y_pred=0))

    with pytest.raises(ValueError, match="artifact_id"):
        artifact_module.verify_experiment_record(path)


@pytest.mark.parametrize(
    "text, message",
    [
        ('{"schema_version":"1.0.0","schema_version":"1.0.0"}', "duplicate"),
        ('{"schema_version":NaN}', "finite"),
        ('{"schema_version":Infinity}', "finite"),
    ],
)
def test_verifier_rejects_duplicate_keys_and_non_finite_json(
    artifact_module, tmp_path, text, message,
):
    path = tmp_path / "malformed.json"
    path.write_text(text, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        artifact_module.verify_experiment_record(path)


@pytest.mark.parametrize(
    "transform, message",
    [
        (lambda envelope: envelope.update(schema_version="2.0.0"), "schema_version"),
        (lambda envelope: envelope.update(unexpected=True), "keys"),
        (lambda envelope: envelope["payload"].update(unexpected=True), "keys"),
        (
            lambda envelope: envelope["payload"]["predictions"][0].update(unexpected=True),
            "keys",
        ),
    ],
)
def test_verifier_rejects_unknown_version_and_unexpected_keys(
    artifact_module, tmp_path, rows, metadata, transform, message,
):
    path = artifact_module.write_experiment_record(tmp_path / "record.json", rows, metadata)
    _rewrite(path, transform)

    with pytest.raises(ValueError, match=message):
        artifact_module.verify_experiment_record(path)


def test_existing_destination_is_never_overwritten(
    artifact_module, tmp_path, metadata,
):
    destination = tmp_path / "record.json"
    destination.write_text("keep me", encoding="utf-8")

    with pytest.raises(FileExistsError):
        artifact_module.write_experiment_record(
            destination, _one_row(), _metadata_for_one(metadata),
        )

    assert destination.read_text(encoding="utf-8") == "keep me"


@pytest.mark.parametrize("split", ["test", "holdout", "TRAIN", ""])
def test_writer_rejects_test_and_unknown_splits_before_mkdir(
    artifact_module, tmp_path, metadata, split,
):
    destination = tmp_path / split.replace("", "empty", 1) / "record.json"
    metadata = _metadata_for_one(metadata, split=split)

    with pytest.raises(ValueError, match="split"):
        artifact_module.write_experiment_record(destination, _one_row(split), metadata)

    assert not destination.parent.exists()


@pytest.mark.parametrize("supplier_id", ["", " ", " s1", "s1 ", 1, None])
def test_writer_rejects_invalid_supplier_ids(
    artifact_module, tmp_path, metadata, supplier_id,
):
    rows = [{**_one_row()[0], "supplier_id": supplier_id}]

    with pytest.raises((TypeError, ValueError), match="supplier_id"):
        artifact_module.write_experiment_record(
            tmp_path / "record.json", rows, _metadata_for_one(metadata),
        )


def test_writer_rejects_duplicate_supplier_ids_across_splits(
    artifact_module, tmp_path, metadata,
):
    rows = [_one_row("train")[0], _one_row("validation")[0]]
    metadata = copy.deepcopy(metadata)
    metadata["expected_id_hashes"] = {"train": S1_HASH, "validation": S1_HASH}

    with pytest.raises(ValueError, match="unique"):
        artifact_module.write_experiment_record(tmp_path / "record.json", rows, metadata)


@pytest.mark.parametrize(
    "field, value",
    [
        ("y_true", True),
        ("y_true", 1.0),
        ("y_true", -1),
        ("y_pred", False),
        ("y_pred", 2),
        ("y_pred", "1"),
    ],
)
def test_writer_rejects_non_binary_integer_classes(
    artifact_module, tmp_path, metadata, field, value,
):
    rows = [{**_one_row()[0], field: value}]

    with pytest.raises((TypeError, ValueError), match=field):
        artifact_module.write_experiment_record(
            tmp_path / "record.json", rows, _metadata_for_one(metadata),
        )


@pytest.mark.parametrize("probability", [math.nan, math.inf, -math.inf, -0.01, 1.01, True])
def test_writer_rejects_invalid_probabilities(
    artifact_module, tmp_path, metadata, probability,
):
    rows = [{**_one_row()[0], "probability_class_1": probability}]

    with pytest.raises((TypeError, ValueError), match="probability_class_1"):
        artifact_module.write_experiment_record(
            tmp_path / "record.json", rows, _metadata_for_one(metadata),
        )


@pytest.mark.parametrize("scenario", ["A", "B", "C", "D"])
def test_each_scenario_accepts_only_its_ordered_feature_contract(
    artifact_module, tmp_path, metadata, scenario,
):
    scenario_metadata = _metadata_for_one(metadata, scenario=scenario)

    path = artifact_module.write_experiment_record(
        tmp_path / f"{scenario}.json", _one_row(), scenario_metadata,
    )

    assert artifact_module.verify_experiment_record(path)["payload"]["metadata"][
        "features"
    ] == FEATURES_BY_SCENARIO[scenario]


@pytest.mark.parametrize("scenario", ["A", "B", "C", "D", "E"])
def test_wrong_features_or_unknown_scenario_are_rejected(
    artifact_module, tmp_path, metadata, scenario,
):
    scenario_metadata = copy.deepcopy(metadata)
    scenario_metadata["scenario"] = scenario
    scenario_metadata["features"] = list(reversed(FEATURES_A))
    scenario_metadata["expected_id_hashes"] = {"validation": S1_HASH}

    with pytest.raises(ValueError, match="scenario|features"):
        artifact_module.write_experiment_record(
            tmp_path / "record.json", _one_row(), scenario_metadata,
        )


def test_unhashable_scenario_is_reported_as_contract_error(
    artifact_module, tmp_path, metadata,
):
    scenario_metadata = _metadata_for_one(metadata)
    scenario_metadata["scenario"] = ["A"]

    with pytest.raises(ValueError, match="scenario"):
        artifact_module.write_experiment_record(
            tmp_path / "record.json", _one_row(), scenario_metadata,
        )


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda value: value.pop("estimator"), "metadata keys"),
        (lambda value: value.update(extra="no"), "metadata keys"),
        (lambda value: value.update(experiment_name=" "), "experiment_name"),
        (lambda value: value.update(parameters={"bad": math.nan}), "parameters"),
        (lambda value: value.update(parameters={1: "bad"}), "parameters"),
        (lambda value: value.update(seeds={}), "seeds"),
        (lambda value: value.update(seeds={"model": True}), "seeds"),
        (lambda value: value.update(versions={"python": ""}), "versions"),
        (lambda value: value.update(input_hashes={"source": "bad"}), "input_hashes"),
        (lambda value: value.update(code_sha256="BAD"), "code_sha256"),
        (lambda value: value.update(notebook_sha256="BAD"), "notebook_sha256"),
        (
            lambda value: value.update(
                expected_id_hashes={"validation": S1_HASH, "train": S1_HASH},
            ),
            "expected_id_hashes",
        ),
    ],
)
def test_writer_rejects_invalid_metadata(
    artifact_module, tmp_path, metadata, mutate, message,
):
    metadata = _metadata_for_one(metadata)
    mutate(metadata)

    with pytest.raises((TypeError, ValueError), match=message):
        artifact_module.write_experiment_record(tmp_path / "record.json", _one_row(), metadata)


def test_invalid_input_does_not_create_parent_or_touch_existing_file(
    artifact_module, tmp_path, metadata,
):
    absent_destination = tmp_path / "absent" / "record.json"
    existing_destination = tmp_path / "existing.json"
    existing_destination.write_text("original", encoding="utf-8")
    invalid_rows = [{**_one_row()[0], "probability_class_1": 2.0}]

    with pytest.raises(ValueError):
        artifact_module.write_experiment_record(
            absent_destination, invalid_rows, _metadata_for_one(metadata),
        )
    with pytest.raises(ValueError):
        artifact_module.write_experiment_record(
            existing_destination, invalid_rows, _metadata_for_one(metadata),
        )

    assert not absent_destination.parent.exists()
    assert existing_destination.read_text(encoding="utf-8") == "original"


def test_verifier_rejects_internally_consistent_but_disallowed_split(
    artifact_module, tmp_path, rows, metadata,
):
    path = artifact_module.write_experiment_record(tmp_path / "record.json", rows, metadata)

    def insert_test_split(document):
        document["payload"]["predictions"][0]["split"] = "test"

    _rewrite(path, insert_test_split)

    with pytest.raises(ValueError, match="split"):
        artifact_module.verify_experiment_record(path)


def test_cli_verify_returns_zero_only_for_valid_artifact(
    artifact_module, tmp_path, metadata,
):
    valid_path = artifact_module.write_experiment_record(
        tmp_path / "valid.json", _one_row(), _metadata_for_one(metadata),
    )
    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text("{}", encoding="utf-8")

    valid = subprocess.run(
        [sys.executable, "-I", "-B", str(SCRIPT_PATH), "verify", str(valid_path)],
        capture_output=True,
        check=False,
        text=True,
    )
    invalid = subprocess.run(
        [sys.executable, "-I", "-B", str(SCRIPT_PATH), "verify", str(invalid_path)],
        capture_output=True,
        check=False,
        text=True,
    )

    assert valid.returncode == 0
    assert invalid.returncode != 0


def test_uppercase_metadata_hashes_are_accepted_without_rewriting(
    artifact_module, tmp_path, rows, metadata,
):
    metadata["expected_id_hashes"] = {
        split: digest.upper() for split, digest in metadata["expected_id_hashes"].items()
    }
    metadata["input_hashes"]["synthetic_train"] = "A" * 64
    metadata["code_sha256"] = "B" * 64
    metadata["notebook_sha256"] = "C" * 64
    original_metadata = copy.deepcopy(metadata)

    path = artifact_module.write_experiment_record(tmp_path / "record.json", rows, metadata)
    original_bytes = path.read_bytes()
    envelope = artifact_module.verify_experiment_record(path)

    assert envelope["payload"]["metadata"] == original_metadata
    assert metadata == original_metadata
    assert path.read_bytes() == original_bytes


def test_uppercase_stored_hashes_preserve_payload_digest_validation(
    artifact_module, tmp_path, rows, metadata,
):
    path = artifact_module.write_experiment_record(tmp_path / "record.json", rows, metadata)
    document = json.loads(path.read_text(encoding="utf-8"))
    document["payload"]["id_hashes"] = {"train": S1_HASH.upper(), "validation": S2_HASH.upper()}
    payload_bytes = json.dumps(
        document["payload"], ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    document["artifact_id"] = hashlib.sha256(payload_bytes).hexdigest().upper()
    path.write_text(json.dumps(document), encoding="utf-8")
    original_bytes = path.read_bytes()

    assert artifact_module.verify_experiment_record(path) == document
    assert path.read_bytes() == original_bytes

    # Hex case is ignored in comparisons, not when hashing the payload's bytes.
    document["payload"]["metadata"]["expected_id_hashes"]["train"] = S1_HASH.upper()
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(artifact_module.ArtifactValidationError, match="artifact_id"):
        artifact_module.verify_experiment_record(path)


@pytest.mark.parametrize("location", ["supplier_id", "experiment_name", "parameter"])
def test_writer_reports_invalid_unicode_before_creating_files(
    artifact_module, tmp_path, rows, metadata, location,
):
    if location == "supplier_id":
        rows[0]["supplier_id"] = "\ud800"
    elif location == "experiment_name":
        metadata["experiment_name"] = "\ud800"
    else:
        metadata["parameters"]["note"] = "\ud800"
    destination = tmp_path / "absent" / "record.json"

    with pytest.raises(artifact_module.ArtifactValidationError, match="invalid Unicode"):
        artifact_module.write_experiment_record(destination, rows, metadata)

    assert not destination.parent.exists()


def test_verifier_reports_escaped_invalid_unicode_as_validation_error(
    artifact_module, tmp_path, rows, metadata,
):
    path = artifact_module.write_experiment_record(tmp_path / "record.json", rows, metadata)
    document = json.loads(path.read_text(encoding="utf-8"))
    document["payload"]["metadata"]["experiment_name"] = "\ud800"
    path.write_text(json.dumps(document, ensure_ascii=True), encoding="utf-8")

    with pytest.raises(artifact_module.ArtifactValidationError, match="invalid Unicode"):
        artifact_module.verify_experiment_record(path)


@pytest.mark.parametrize("location", ["duplicate_key", "payload"])
def test_cli_validation_errors_remain_printable_for_malformed_unicode(
    artifact_module, tmp_path, rows, metadata, location,
):
    path = artifact_module.write_experiment_record(tmp_path / "record.json", rows, metadata)
    if location == "duplicate_key":
        text = '{"bad\\ud800":1,"bad\\ud800":2}'
    else:
        document = json.loads(path.read_text(encoding="utf-8"))
        document["payload"]["metadata"]["experiment_name"] = "\ud800"
        text = json.dumps(document, ensure_ascii=True)
    path.write_text(text, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-I", "-B", str(SCRIPT_PATH), "verify", str(path)],
        capture_output=True, check=False, text=True, encoding="utf-8",
    )

    assert result.returncode == 1
    assert "verification failed:" in result.stderr
    assert "Traceback" not in result.stderr
    result.stderr.encode("utf-8")
