import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "ml"
    / "supplier_risk"
    / "scripts"
    / "experiment_artifact.py"
)
MODULE_SPEC = importlib.util.spec_from_file_location("experiment_artifact", MODULE_PATH)
assert MODULE_SPEC is not None and MODULE_SPEC.loader is not None
artifact = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(artifact)


TEST_ID_HASH = "13660095d71ded8bdc274ff2294972234459d9f9af03565f853fc765b6de1288"
TWO_TEST_IDS_HASH = "faa03e43603b046ecbc0f4d43cf5dca6a8e94ed0404d0fc657d880591c97d42c"
TRAIN_ID_HASH = TEST_ID_HASH
FREEZE_SHA256 = "F" * 64


def _prediction(supplier_id="supplier-1", split="test", y_pred=1):
    return {
        "supplier_id": supplier_id,
        "split": split,
        "y_true": 1,
        "y_pred": y_pred,
        "probability_class_1": 0.75,
    }


def _metadata(split="test", id_hash=TEST_ID_HASH):
    return {
        "experiment_name": "final supplier evaluation",
        "estimator": "synthetic-estimator",
        "scenario": "D",
        "features": [
            "financial_stability_score",
            "on_time_delivery_rate",
            "defect_rate",
            "lead_time_days",
            "alternative_suppliers_available",
            "contract_length_months",
            "environmental_compliance",
            "previous_disruptions",
        ],
        "parameters": {"threshold": 0.5},
        "seeds": {"model": 42},
        "versions": {"python": "3.12"},
        "input_hashes": {"dataset": "a" * 64},
        "code_sha256": "b" * 64,
        "expected_id_hashes": {split: id_hash.upper()},
    }


def _canonical_sha256(value):
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def test_final_evaluation_roundtrip_preserves_hashes_and_binds_artifact_id(tmp_path):
    destination = tmp_path / "nested" / "final.json"
    predictions = [
        _prediction("supplier-2", y_pred=0),
        _prediction("supplier-1"),
    ]
    metadata = _metadata(id_hash=TWO_TEST_IDS_HASH)

    artifact.write_final_evaluation_record(
        destination,
        predictions,
        metadata,
        freeze_sha256=FREEZE_SHA256,
    )
    envelope = artifact.verify_final_evaluation_record(destination)

    assert envelope["schema_version"] == "supplier-risk-final/1.0.0"
    assert envelope["freeze_sha256"] == FREEZE_SHA256
    assert envelope["payload"]["metadata"]["expected_id_hashes"]["test"] == (
        TWO_TEST_IDS_HASH.upper()
    )
    assert [row["supplier_id"] for row in envelope["payload"]["predictions"]] == [
        "supplier-1",
        "supplier-2",
    ]
    assert envelope["artifact_id"] == _canonical_sha256(
        {
            "freeze_sha256": FREEZE_SHA256,
            "payload": envelope["payload"],
        }
    )


def test_development_writer_still_rejects_test_predictions(tmp_path):
    with pytest.raises(artifact.ArtifactValidationError, match="train or validation"):
        artifact.write_experiment_record(
            tmp_path / "development.json",
            [_prediction()],
            _metadata(),
        )


@pytest.mark.parametrize("split", ["train", "validation"])
def test_final_writer_rejects_development_splits(tmp_path, split):
    with pytest.raises(artifact.ArtifactValidationError, match="test"):
        artifact.write_final_evaluation_record(
            tmp_path / f"{split}.json",
            [_prediction(split=split)],
            _metadata(split=split),
            freeze_sha256="f" * 64,
        )


def test_final_writer_rejects_empty_predictions_before_creating_parent(tmp_path):
    destination = tmp_path / "not-created" / "final.json"

    with pytest.raises(artifact.ArtifactValidationError, match="non-empty"):
        artifact.write_final_evaluation_record(
            destination,
            [],
            _metadata(),
            freeze_sha256="f" * 64,
        )

    assert not destination.parent.exists()


@pytest.mark.parametrize("freeze_sha256", ["f" * 63, "g" * 64, 7])
def test_final_writer_rejects_invalid_freeze_hash(tmp_path, freeze_sha256):
    with pytest.raises(artifact.ArtifactValidationError, match="freeze_sha256"):
        artifact.write_final_evaluation_record(
            tmp_path / "final.json",
            [_prediction()],
            _metadata(),
            freeze_sha256=freeze_sha256,
        )


@pytest.mark.parametrize("tamper", ["freeze", "payload"])
def test_final_verifier_detects_tampering(tmp_path, tamper):
    destination = tmp_path / "final.json"
    artifact.write_final_evaluation_record(
        destination,
        [_prediction()],
        _metadata(),
        freeze_sha256="f" * 64,
    )
    envelope = json.loads(destination.read_text(encoding="utf-8"))
    if tamper == "freeze":
        envelope["freeze_sha256"] = "e" * 64
    else:
        envelope["payload"]["predictions"][0]["y_pred"] = 0
    destination.write_text(json.dumps(envelope), encoding="utf-8")

    with pytest.raises(artifact.ArtifactValidationError, match="artifact_id"):
        artifact.verify_final_evaluation_record(destination)


def test_final_writer_is_exclusive_and_preserves_existing_file(tmp_path):
    destination = tmp_path / "final.json"
    destination.write_text("already here", encoding="utf-8")

    with pytest.raises(FileExistsError):
        artifact.write_final_evaluation_record(
            destination,
            [_prediction()],
            _metadata(),
            freeze_sha256="f" * 64,
        )

    assert destination.read_text(encoding="utf-8") == "already here"


def test_final_writer_reports_invalid_unicode_without_creating_parent(tmp_path):
    destination = tmp_path / "not-created" / "final.json"

    with pytest.raises(artifact.ArtifactValidationError, match="invalid Unicode"):
        artifact.write_final_evaluation_record(
            destination,
            [_prediction(supplier_id="\ud800")],
            _metadata(),
            freeze_sha256="f" * 64,
        )

    assert not destination.parent.exists()


def test_development_and_final_verifiers_reject_each_others_schema(tmp_path):
    final_path = tmp_path / "final.json"
    development_path = tmp_path / "development.json"
    artifact.write_final_evaluation_record(
        final_path,
        [_prediction()],
        _metadata(),
        freeze_sha256="f" * 64,
    )
    artifact.write_experiment_record(
        development_path,
        [_prediction(split="train")],
        _metadata(split="train", id_hash=TRAIN_ID_HASH),
    )

    with pytest.raises(artifact.ArtifactValidationError, match="envelope keys"):
        artifact.verify_experiment_record(final_path)
    with pytest.raises(artifact.ArtifactValidationError, match="envelope keys"):
        artifact.verify_final_evaluation_record(development_path)


def test_verify_final_cli_prints_artifact_id(tmp_path, capsys):
    destination = tmp_path / "final.json"
    artifact.write_final_evaluation_record(
        destination,
        [_prediction()],
        _metadata(),
        freeze_sha256="f" * 64,
    )
    expected_id = artifact.verify_final_evaluation_record(destination)["artifact_id"]

    assert artifact.main(["verify-final", str(destination)]) == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == expected_id
    assert captured.err == ""
