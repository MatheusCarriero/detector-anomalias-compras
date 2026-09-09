"""Targets sem resolução arbitrária e split SHA-256 independente das labels."""

import hashlib
import json
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest


def test_one_binary_target_per_supplier(target_module, source_frame):
    targets = target_module.consolidar_targets(source_frame, {"A", "B", "C"})
    assert targets.columns.tolist() == ["supplier_id", "risk_level"]
    assert targets.supplier_id.is_unique
    assert targets.supplier_id.tolist() == ["A", "B", "C"]
    assert targets.risk_level.tolist() == [0, 1, 0]
    assert targets.isna().sum().sum() == 0


@pytest.mark.parametrize("value", [None, np.nan, 2, -1, 0.5, "invalid", np.inf, True])
def test_rejects_null_nonbinary_or_invalid_target(target_module, source_frame, value):
    source = source_frame.assign(Risk_Level=value)
    _, audit = target_module.auditar_target(source)
    assert audit["status"] == "bloqueado"
    with pytest.raises(ValueError, match="Risk_Level"):
        target_module.consolidar_targets(source, {"A", "B", "C"})


@pytest.mark.parametrize("labels", [[0, 1, 0, 1, 0], [1, 0, 1, 1, 0]])
def test_conflict_detected_and_never_resolved(target_module, source_frame, labels):
    source = source_frame.assign(Risk_Level=labels)
    _, audit = target_module.auditar_target(source)
    assert audit["quantidade_conflitos"] == 1
    assert audit["fornecedores_com_0_e_1"] == 1
    assert audit["exemplos_conflitos"] == ["A"]
    assert audit["resolucao_automatica_de_conflitos"] is False
    with pytest.raises(ValueError, match="conflitante"):
        target_module.consolidar_targets(source, {"A", "B", "C"})


@pytest.mark.parametrize("ids", [{"A", "B"}, {"A", "B", "D"}, {"A", "B", "C", "D"}])
def test_target_ids_must_match_base_exactly(target_module, source_frame, ids):
    with pytest.raises(ValueError, match="Targets/base"):
        target_module.consolidar_targets(source_frame, ids)


@pytest.mark.parametrize("column", ["Supplier_ID", "Risk_Level"])
def test_missing_source_columns_block_audit(target_module, source_frame, column):
    _, audit = target_module.auditar_target(source_frame.drop(columns=column))
    assert audit["status"] == "bloqueado"


def test_null_supplier_id_blocks_audit(target_module, source_frame):
    source = source_frame.assign(Supplier_ID=[None, "A", "A", "B", "C"])
    _, audit = target_module.auditar_target(source)
    assert audit["supplier_id_nulos"] == 1
    with pytest.raises(ValueError, match="Supplier_ID nulo"):
        target_module.consolidar_targets(source, {"A", "B", "C"})


def test_all_ids_assigned_once_with_zero_overlap(target_module):
    ids = [f"SUP-{i:04}" for i in range(1000)]
    split = target_module.criar_split(ids)
    assert split.supplier_id.is_unique
    assert set(split.supplier_id) == set(ids)
    assert set(split.split) == {"train", "validation", "test"}
    checked = target_module.validar_split(split, set(ids))
    assert checked["overlap"] == {"train_validation": 0, "train_test": 0, "validation_test": 0}


def test_full_reordering_preserves_assignments(target_module):
    ids = [f"supplier-{i}" for i in range(333)]
    first = target_module.criar_split(ids)
    second = target_module.criar_split(list(reversed(ids)))
    pd.testing.assert_frame_equal(first, second)


@pytest.mark.parametrize("supplier_id", ["A", "SUP-0001", "00007", "Fornecedor-ç", " X "])
def test_sha256_protocol_is_stable_and_matches_independent_reference(target_module, supplier_id):
    digest = hashlib.sha256(supplier_id.encode("utf-8")).hexdigest()
    h = int(digest, 16)
    expected = "train" if h < 2**256 * 70 // 100 else (
        "validation" if h < 2**256 * 85 // 100 else "test"
    )
    assert target_module.particao_por_id(supplier_id) == expected
    assert target_module.particao_por_id(supplier_id) == expected


@pytest.mark.parametrize("point,expected", [
    (0, "train"), (2**256 * 70 // 100 - 1, "train"),
    (2**256 * 70 // 100, "validation"), (2**256 * 85 // 100 - 1, "validation"),
    (2**256 * 85 // 100, "test"), (2**256 - 1, "test"),
])
def test_hash_integer_boundaries(target_module, monkeypatch, point, expected):
    monkeypatch.setattr(target_module.hashlib, "sha256", Mock(
        return_value=Mock(digest=lambda: point.to_bytes(32, "big")),
    ))
    assert target_module.particao_por_id("A") == expected


def test_target_changes_cannot_change_split(target_module, source_frame):
    ids = {"A", "B", "C"}
    split = target_module.criar_split(ids)
    snapshot = split.copy(deep=True)
    for source in (source_frame, source_frame.assign(Risk_Level=1 - source_frame.Risk_Level)):
        targets = target_module.consolidar_targets(source, ids)
        target_module.observar_distribuicao(split, targets)
        pd.testing.assert_frame_equal(split, snapshot)
        pd.testing.assert_frame_equal(target_module.criar_split(ids), snapshot)


@pytest.mark.parametrize("problem", ["missing", "unexpected", "duplicate", "null", "invalid"])
def test_rejects_inconsistent_split(target_module, problem):
    split = target_module.criar_split(["A", "B"])
    if problem == "missing":
        split = split.iloc[:1]
    elif problem == "unexpected":
        split = split.assign(supplier_id=["A", "C"])
    elif problem == "duplicate":
        split = pd.concat([split, split.iloc[:1].assign(split="test")])
    else:
        split = split.assign(split=[None if problem == "null" else "invalid", "test"])
    with pytest.raises(ValueError):
        target_module.validar_split(split, {"A", "B"})


def test_conflict_main_writes_only_audit_in_tmp_path(target_module, source_frame):
    source = source_frame.assign(Risk_Level=[0, 1, 0, 1, 0])
    source.to_csv(target_module.SOURCE_PATH, index=False)
    target_module.OUTPUT_DIR.mkdir(parents=True)
    pd.DataFrame({"supplier_id": ["A", "B", "C"]}).to_parquet(target_module.BASE_PATH)
    with pytest.raises(ValueError, match="conflitante"):
        target_module.main()
    audit = json.loads(target_module.AUDIT_PATH.read_text(encoding="utf-8"))
    assert audit["status"] == "bloqueado"
    assert audit["quantidade_conflitos"] == 1
    assert not target_module.TARGETS_PATH.exists()
    assert not target_module.SPLIT_PATH.exists()
    assert not target_module.METADATA_PATH.exists()
