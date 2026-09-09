"""Alinhamento X/y, train-only e reexecução exclusivamente em dados sintéticos."""

import json

import numpy as np
import pandas as pd
import pytest
from sklearn.impute import SimpleImputer


def test_expected_schema_alignment_and_finitude(ml_module, ml_inputs, approved_features):
    parts, checks = ml_module.preparar_particoes(**ml_inputs)
    outputs, _ = ml_module.transformar_particoes(parts)
    assert checks["fornecedores_apos_merge"] == 7
    assert checks["ids_perdidos"] == checks["ids_inesperados"] == 0
    assert not any(checks["overlap"].values())
    for name, count in (("train", 3), ("validation", 2), ("test", 2)):
        x, y = outputs[name]["X"], outputs[name]["y"]
        assert len(x) == len(y) == count
        assert x.columns.tolist() == approved_features
        assert y.columns.tolist() == ["risk_level"]
        assert not {"supplier_id", "Supplier_ID", "risk_level", "Risk_Level", "split"} & set(x)
        assert np.isfinite(x.to_numpy()).all()
        assert not x.isna().any().any()
        assert not x.isna().all().any()
        assert x.index.equals(y.index)
        assert x.index.name is None
        expected_y = ml_inputs["targets"].set_index("supplier_id").loc[
            parts[name]["supplier_ids"], "risk_level"
        ]
        assert y.risk_level.tolist() == expected_y.tolist()


def test_imputer_fit_only_train_despite_extreme_holdout(ml_module, ml_inputs, monkeypatch):
    parts, _ = ml_module.preparar_particoes(**ml_inputs)
    calls = []

    class ObservedImputer(SimpleImputer):
        def fit_transform(self, x, y=None, **kwargs):
            calls.append(("fit_transform", x.copy()))
            return super().fit_transform(x, y, **kwargs)

        def fit(self, x, y=None):
            calls.append(("fit", x.copy()))
            return super().fit(x, y)

        def transform(self, x):
            calls.append(("transform", x.copy()))
            return super().transform(x)

    monkeypatch.setattr(ml_module, "SimpleImputer", ObservedImputer)
    outputs, imputer = ml_module.transformar_particoes(parts)
    for operation in ("fit", "fit_transform"):
        inputs = [x for name, x in calls if name == operation]
        assert len(inputs) == 1
        pd.testing.assert_frame_equal(inputs[0], parts["train"]["X"])
    transforms = [x for name, x in calls if name == "transform"]
    # fit_transform transforma o próprio TRAIN internamente, seguido dos holdouts.
    assert len(transforms) == 3
    for actual, name in zip(transforms, ("train", "validation", "test"), strict=True):
        pd.testing.assert_frame_equal(actual, parts[name]["X"])
    np.testing.assert_array_equal(imputer.statistics_, np.full(10, 1.5))
    assert outputs["train"]["X"].iloc[2].eq(1.5).all()
    assert outputs["validation"]["X"].iloc[1].eq(1.5).all()
    assert outputs["test"]["X"].iloc[1].eq(1.5).all()
    assert outputs["validation"]["X"].iloc[0].eq(1000).all()
    assert outputs["test"]["X"].iloc[0].eq(2000).all()


def test_changing_targets_and_holdout_does_not_change_learned_medians(ml_module, ml_inputs):
    parts, _ = ml_module.preparar_particoes(**ml_inputs)
    outputs, imputer = ml_module.transformar_particoes(parts)
    changed = {
        **ml_inputs,
        "targets": ml_inputs["targets"].assign(risk_level=1 - ml_inputs["targets"].risk_level),
        "features": ml_inputs["features"].assign(
            financial_stability_score=[1.0, 2.0, np.nan, 1e10, np.nan, -1e10, np.nan],
        ),
    }
    changed_parts, _ = ml_module.preparar_particoes(**changed)
    changed_outputs, changed_imputer = ml_module.transformar_particoes(changed_parts)
    np.testing.assert_array_equal(imputer.statistics_, changed_imputer.statistics_)
    pd.testing.assert_frame_equal(outputs["train"]["X"], changed_outputs["train"]["X"])


def test_input_row_order_is_irrelevant(ml_module, ml_inputs):
    before = {key: frame.copy(deep=True) for key, frame in ml_inputs.items()}
    parts, _ = ml_module.preparar_particoes(**ml_inputs)
    shuffled, _ = ml_module.preparar_particoes(**{
        key: frame.iloc[::-1] for key, frame in ml_inputs.items()
    })
    for name in parts:
        assert parts[name]["supplier_ids"] == shuffled[name]["supplier_ids"]
        for kind in ("X", "y"):
            pd.testing.assert_frame_equal(parts[name][kind], shuffled[name][kind])
    for key in ml_inputs:
        pd.testing.assert_frame_equal(ml_inputs[key], before[key])


@pytest.mark.parametrize("table", ["features", "targets", "split"])
@pytest.mark.parametrize("problem", ["empty", "missing_id", "null_id", "duplicate_id"])
def test_invalid_keys_are_rejected(ml_module, ml_inputs, table, problem):
    frame = ml_inputs[table]
    if problem == "empty":
        frame = frame.iloc[:0]
    elif problem == "missing_id":
        frame = frame.drop(columns="supplier_id")
    elif problem == "null_id":
        frame = frame.assign(supplier_id=[None, *list("BCDEFG")])
    else:
        frame = pd.concat([frame, frame.iloc[:1]])
    with pytest.raises(ValueError):
        ml_module.preparar_particoes(**{**ml_inputs, table: frame})


@pytest.mark.parametrize("table", ["targets", "split"])
@pytest.mark.parametrize("problem", ["missing_supplier", "unexpected_supplier"])
def test_id_sets_must_match(ml_module, ml_inputs, table, problem):
    frame = ml_inputs[table]
    frame = frame.iloc[:-1] if problem == "missing_supplier" else frame.assign(
        supplier_id=[*list("ABCDEF"), "Z"],
    )
    with pytest.raises(ValueError, match="IDs não correspondem"):
        ml_module.preparar_particoes(**{**ml_inputs, table: frame})


@pytest.mark.parametrize("bad_split", [None, "invalid", ""])
def test_missing_or_invalid_split_rejected(ml_module, ml_inputs, bad_split):
    split = ml_inputs["split"].assign(split=["train"] * 3 + [bad_split] * 2 + ["test"] * 2)
    with pytest.raises(ValueError, match="Split ausente ou inválido"):
        ml_module.preparar_particoes(**{**ml_inputs, "split": split})


def test_rejects_empty_partition(ml_module, ml_inputs):
    split = ml_inputs["split"].assign(split="train")
    with pytest.raises(ValueError, match="Partição validation vazia"):
        ml_module.preparar_particoes(**{**ml_inputs, "split": split})


@pytest.mark.parametrize("bad_target", [None, 2, 0.5, "invalid"])
def test_invalid_targets_rejected(ml_module, ml_inputs, bad_target):
    targets = ml_inputs["targets"].assign(risk_level=bad_target)
    with pytest.raises(ValueError):
        ml_module.preparar_particoes(**{**ml_inputs, "targets": targets})


@pytest.mark.parametrize("column", ["Risk_Level", "risk_level", "Risk_Category", "unexpected"])
def test_extra_feature_columns_rejected(ml_module, ml_inputs, column):
    features = ml_inputs["features"].assign(**{column: 1})
    with pytest.raises(ValueError, match="inesperadas"):
        ml_module.preparar_particoes(**{**ml_inputs, "features": features})


def test_missing_feature_rejected(ml_module, ml_inputs):
    features = ml_inputs["features"].drop(columns="defect_rate")
    with pytest.raises(ValueError, match="defect_rate"):
        ml_module.preparar_particoes(**{**ml_inputs, "features": features})


@pytest.mark.parametrize("value", [np.inf, -np.inf, "invalid", True, 1 + 2j])
def test_invalid_numeric_input_rejected(ml_module, ml_inputs, value):
    features = ml_inputs["features"].assign(defect_rate=value)
    with pytest.raises(ValueError):
        ml_module.preparar_particoes(**{**ml_inputs, "features": features})


def test_all_missing_train_feature_blocks_without_using_holdout(ml_module, ml_inputs):
    features = ml_inputs["features"].assign(defect_rate=[np.nan] * 3 + [1000.0] * 4)
    parts, _ = ml_module.preparar_particoes(**{**ml_inputs, "features": features})
    with pytest.raises(ValueError, match="defect_rate"):
        ml_module.transformar_particoes(parts)


def test_all_missing_holdout_feature_uses_train_median(ml_module, ml_inputs):
    features = ml_inputs["features"].assign(defect_rate=[1.0, 2.0] + [np.nan] * 5)
    parts, _ = ml_module.preparar_particoes(**{**ml_inputs, "features": features})
    outputs, _ = ml_module.transformar_particoes(parts)
    for name in ("validation", "test"):
        assert outputs[name]["X"].defect_rate.eq(1.5).all()


@pytest.mark.parametrize("problem", ["length", "id", "label", "null", "infinite", "index"])
def test_invalid_output_rejected(ml_module, ml_inputs, problem):
    parts, _ = ml_module.preparar_particoes(**ml_inputs)
    outputs, _ = ml_module.transformar_particoes(parts)
    x, y = outputs["train"]["X"], outputs["train"]["y"]
    if problem == "length":
        y = y.iloc[:1]
    elif problem == "id":
        x = x.assign(supplier_id="A")
    elif problem == "label":
        x = x.assign(Risk_Level=1)
    elif problem == "index":
        x = x.set_axis([1, 2, 3])
    else:
        x = x.assign(defect_rate=np.nan if problem == "null" else np.inf)
    with pytest.raises(ValueError):
        ml_module.validar_saida(x, y, "test")


def test_missing_files_block_before_any_output(ml_module):
    with pytest.raises(FileNotFoundError, match="Entradas obrigatórias"):
        ml_module.main()
    assert not ml_module.OUTPUT_DIR.exists()


def test_repeat_file_pipeline_is_equivalent_and_keeps_input_hashes(ml_module, write_ml_inputs):
    write_ml_inputs()
    before = {path: ml_module.calcular_hash(path) for path in ml_module.INPUT_PATHS.values()}
    ml_module.main()
    first_metadata = json.loads(ml_module.METADATA_PATH.read_text(encoding="utf-8"))
    expected = {
        path.name: pd.read_parquet(path) for path in ml_module.OUTPUT_DIR.glob("*.parquet")
    }
    ml_module.main()
    metadata = json.loads(ml_module.METADATA_PATH.read_text(encoding="utf-8"))
    assert len(expected) == 6
    for name, frame in expected.items():
        pd.testing.assert_frame_equal(pd.read_parquet(ml_module.OUTPUT_DIR / name), frame)
    assert first_metadata["hashes_saidas_sha256"] == metadata["hashes_saidas_sha256"]
    assert metadata["imputador_ajustado_somente_no_treino"] is True
    assert set(metadata["medianas_aprendidas_no_train"].values()) == {1.5}
    assert metadata["quantidade_registros_por_split"] == {"train": 3, "validation": 2, "test": 2}
    assert metadata["modelo_preditivo_treinado"] is False
    for path, digest in before.items():
        assert ml_module.calcular_hash(path) == digest
        assert metadata["hashes_entradas_sha256"][path.relative_to(ml_module.PROJECT_ROOT).as_posix()] == digest
