"""Historical evidence checks use generated JSON only."""

import hashlib
import json

import pytest

from ml.scripts import invoice_historical_evidence as history
from tests.invoice.invoice_history_fixtures import PATHS, VALIDATION_IDS, write_history


@pytest.fixture
def documents(tmp_path, monkeypatch):
    configuration = {
        "features": [f"feature_{n}" for n in range(19)],
        "parameters": {"n_estimators": 200, "bootstrap": False},
        "legacy_offset": -0.5,
        "model_sha256": "c" * 64,
        "model_metadata_sha256": "b" * 64,
    }
    inputs = {
        "data/processed/train_features.parquet": "1" * 64,
        "data/processed/val_features.parquet": "2" * 64,
        "ml/models/isolation_forest.joblib": "c" * 64,
        "ml/models/model_metadata.json": "b" * 64,
    }
    pins = write_history(tmp_path, configuration, inputs, monkeypatch)
    return tmp_path, pins, configuration, inputs


def verify(documents):
    root, pins, configuration, inputs = documents
    return history.verify_historical_evidence(root, pins, configuration, inputs)


def rewrite(documents, index, mutate):
    root, pins, _, _ = documents
    file = root / PATHS[index]
    value = json.loads(file.read_bytes())
    mutate(value)
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    file.write_bytes(encoded)
    pins[PATHS[index]] = hashlib.sha256(encoded).hexdigest()
    history.HISTORICAL_HASHES[PATHS[index]] = pins[PATHS[index]]
    # Keep descendant references valid so an unrelated stale hash cannot mask
    # the semantic defect this test intends to exercise.
    for next_index in range(index + 1, len(PATHS)):
        descendant = root / PATHS[next_index]
        value = json.loads(descendant.read_bytes())
        for prior in PATHS[:next_index]:
            value["input_hashes_sha256"][prior] = pins[prior]
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        descendant.write_bytes(encoded)
        pins[PATHS[next_index]] = hashlib.sha256(encoded).hexdigest()
        history.HISTORICAL_HASHES[PATHS[next_index]] = pins[PATHS[next_index]]


def test_verified_history_reports_integrity_without_provenance_claim(documents):
    assert verify(documents) == {
        "sha256": documents[1],
        "validation_ids_sha256": VALIDATION_IDS,
        "source_reconciled": False,
    }


def test_canonical_key_order_does_not_change_historical_sequence(documents):
    root, pins, configuration, inputs = documents
    reversed_pins = dict(reversed(list(pins.items())))
    result = history.verify_historical_evidence(root, reversed_pins, configuration, inputs)
    assert result["validation_ids_sha256"] == VALIDATION_IDS
    assert result["sha256"] == pins


def test_missing_or_changed_historical_bytes_rejected(documents):
    root, _, _, _ = documents
    (root / PATHS[0]).write_bytes(b"{}")
    with pytest.raises(ValueError):
        verify(documents)
    (root / PATHS[0]).unlink()
    with pytest.raises((ValueError, FileNotFoundError)):
        verify(documents)


def test_caller_cannot_self_approve_new_history_hashes(documents):
    root, pins, _, _ = documents
    pins[PATHS[0]] = "a" * 64
    with pytest.raises(ValueError):
        verify(documents)
    pins[PATHS[0]] = hashlib.sha256((root / PATHS[0]).read_bytes()).hexdigest()
    pins["extra.json"] = "a" * 64
    with pytest.raises(ValueError):
        verify(documents)


@pytest.mark.parametrize("index,key,value,reason", [
    (0, "split", "test", "historical split mismatch"),
    (1, "test_used", True, "historical test_used mismatch"),
    (2, "real_model_fits", 1, "historical real_model_fits mismatch"),
    (1, "threshold_selected", True, "historical threshold_selected mismatch"),
    (2, "budget_selected", True, "historical budget_selected mismatch"),
    (2, "budget_percentages", [1, 5], "historical budget_percentages mismatch"),
    (1, "validation_ids_sha256", "e" * 64, "historical validation IDs mismatch"),
    (0, "features", ["wrong"] * 19, "historical features mismatch"),
    (2, "legacy_offset", -0.3, "historical legacy_offset mismatch"),
    (0, "parameters", {"n_estimators": 201, "bootstrap": False}, "historical parameters mismatch"),
])
def test_pinned_but_semantically_wrong_history_rejected(documents, index, key, value, reason):
    rewrite(documents, index, lambda document: document.__setitem__(key, value))
    with pytest.raises(ValueError, match=reason):
        verify(documents)


def test_cross_reference_rejected(documents):
    rewrite(documents, 2, lambda document: document["input_hashes_sha256"].__setitem__(PATHS[1], "e" * 64))
    with pytest.raises(ValueError):
        verify(documents)


def test_prior_input_mismatch_rejected(documents):
    rewrite(documents, 1, lambda document: document["input_hashes_sha256"].__setitem__(
        "data/processed/val_features.parquet", "e" * 64))
    with pytest.raises(ValueError):
        verify(documents)


def test_mixed_nonobject_budget_entries_rejected(documents):
    rewrite(documents, 2, lambda document: document["comparisons"].insert(1, "extra"))
    with pytest.raises(ValueError):
        verify(documents)


def test_duplicate_key_and_nonfinite_number_rejected(documents):
    root, pins, _, _ = documents
    file = root / PATHS[2]
    original = file.read_bytes()
    for inserted in (
        b'"budget_selected":false,"budget_selected":false',
        b'"budget_selected":false,"extra":NaN',
    ):
        encoded = original.replace(b'"budget_selected":false', inserted)
        file.write_bytes(encoded)
        pins[PATHS[2]] = hashlib.sha256(encoded).hexdigest()
        history.HISTORICAL_HASHES[PATHS[2]] = pins[PATHS[2]]
        with pytest.raises(ValueError):
            verify(documents)


def test_json_numeric_overflow_rejected_even_in_auxiliary_field(documents):
    root, pins, _, _ = documents
    file = root / PATHS[2]
    encoded = file.read_bytes().replace(
        b'"budget_selected":false', b'"budget_selected":false,"extra":1e999')
    file.write_bytes(encoded)
    pins[PATHS[2]] = hashlib.sha256(encoded).hexdigest()
    history.HISTORICAL_HASHES[PATHS[2]] = pins[PATHS[2]]
    with pytest.raises(ValueError):
        verify(documents)


def test_symlinked_history_is_rejected(documents, tmp_path):
    root, _, _, _ = documents
    file = root / PATHS[0]
    outside = tmp_path.parent / "invoice-history-symlink-target.json"
    outside.write_bytes(file.read_bytes())
    file.unlink()
    try:
        file.symlink_to(outside)
    except OSError:
        pytest.skip("symlinks unavailable")
    with pytest.raises(ValueError):
        verify(documents)
