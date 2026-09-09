"""Contrato de deduplicação, consolidação e ausência de imputação na base."""

import json

import numpy as np
import pandas as pd
import pytest


def test_rejects_empty_dataset(feature_module, source_frame):
    with pytest.raises(ValueError, match="vazio"):
        feature_module.preparar_base(source_frame.iloc[:0])


def test_rejects_missing_supplier_id(feature_module, source_frame):
    with pytest.raises(ValueError, match="Supplier_ID"):
        feature_module.preparar_base(source_frame.drop(columns="Supplier_ID"))


@pytest.mark.parametrize("invalid_id", [None, "", "   "])
def test_rejects_invalid_supplier_id(feature_module, source_frame, invalid_id):
    invalid = source_frame.assign(Supplier_ID=[invalid_id, "A", "A", "B", "C"])
    with pytest.raises(ValueError, match="Supplier_ID"):
        feature_module.preparar_base(invalid)


@pytest.mark.parametrize("column", [
    "Financial_Stability_Score", "On_Time_Delivery_Rate", "Defect_Rate",
    "Geopolitical_Risk_Index", "Lead_Time_Days", "Alternative_Suppliers_Available",
    "Contract_Length_Months", "Environmental_Compliance", "Previous_Disruptions",
])
def test_rejects_missing_required_features(feature_module, source_frame, column):
    with pytest.raises(ValueError, match=column):
        feature_module.preparar_base(source_frame.drop(columns=column))


@pytest.mark.parametrize("value", ["invalid", np.inf, -np.inf, 1 + 2j])
def test_rejects_invalid_numeric_values(feature_module, source_frame, value):
    invalid = source_frame.assign(Financial_Stability_Score=value)
    with pytest.raises(ValueError, match="Financial_Stability_Score"):
        feature_module.preparar_base(invalid)


def test_exact_duplicates_counts_and_id_reconciliation(feature_module, source_frame):
    base, record = feature_module.preparar_base(source_frame)
    assert record["linhas_iniciais"] == 5
    assert record["duplicatas_exatas_removidas"] == 1
    assert record["linhas_apos_deduplicacao"] == 4
    assert set(base.supplier_id) == set(source_frame.Supplier_ID) == {"A", "B", "C"}
    assert base.supplier_id.is_unique
    assert base.set_index("supplier_id").supplier_record_count.to_dict() == {"A": 2, "B": 1, "C": 1}
    assert base.supplier_record_count.sum() == 4
    assert record["reconciliacao_ids"]["conjuntos_identicos"]


def test_complementary_records_and_no_global_imputation(feature_module, source_frame):
    before = source_frame.copy(deep=True)
    base, _ = feature_module.preparar_base(source_frame)
    by_id = base.set_index("supplier_id")
    assert by_id.loc["A", "on_time_delivery_rate"] == 80
    assert pd.isna(by_id.loc["B", "financial_stability_score"])
    assert by_id.loc["A", "financial_stability_score"] == 10
    assert by_id.loc["C", "financial_stability_score"] == 90
    pd.testing.assert_frame_equal(source_frame, before)


def test_consolidation_uses_current_within_supplier_median(feature_module, source_frame):
    source = source_frame.iloc[[0, 2]].assign(Financial_Stability_Score=[10.0, 30.0])
    base, record = feature_module.preparar_base(source)
    assert base.financial_stability_score.tolist() == [20.0]
    assert record["fornecedores_com_variacao_numerica_preenchida"] == 1


def test_fully_missing_feature_stays_missing(feature_module, source_frame):
    base, _ = feature_module.preparar_base(source_frame.assign(Defect_Rate=np.nan))
    assert base.defect_rate.isna().all()


def test_only_approved_features_no_labels_or_derived_indices(
    feature_module, source_frame, approved_features,
):
    base, _ = feature_module.preparar_base(source_frame)
    assert base.columns.tolist() == ["supplier_id", *approved_features]
    assert not {
        "Supplier_ID", "Risk_Level", "Risk_Category", "Country",
        "Delivery_Quality_Index", "Supplier_Dependency_Score",
    }.intersection(base.columns)


def test_extremes_and_domain_warnings_do_not_clip(feature_module, source_frame):
    source = source_frame.assign(Defect_Rate=1e9)
    base, _ = feature_module.preparar_base(source)
    quality = feature_module.gerar_qualidade(base).set_index("feature")
    assert base.defect_rate.eq(1e9).all()
    assert base.environmental_compliance.eq(100.95).all()
    assert base.lead_time_days.tolist() == [0.0, 0.0, -1.0]
    assert quality.loc["environmental_compliance", "quantidade_acima_100"] == 3
    assert quality.loc["lead_time_days", "quantidade_zeros"] == 2
    assert quality.loc["lead_time_days", "quantidade_negativos"] == 1


@pytest.mark.parametrize("bad_ids", [{"A", "B"}, {"A", "B", "C", "D"}])
def test_output_rejects_id_mismatch(feature_module, source_frame, bad_ids):
    base, _ = feature_module.preparar_base(source_frame)
    with pytest.raises(ValueError, match="reconciliação"):
        feature_module.validar_saida(base, bad_ids)


def test_output_rejects_duplicate_id(feature_module, source_frame):
    base, _ = feature_module.preparar_base(source_frame)
    with pytest.raises(ValueError, match="duplicado"):
        feature_module.validar_saida(pd.concat([base, base.iloc[:1]]), {"A", "B", "C"})


def test_metadata_quality_and_file_roundtrip_in_tmp_path(feature_module, source_frame):
    source_frame.to_csv(feature_module.SOURCE_PATH, index=False)
    original_hash = feature_module.calcular_hash(feature_module.SOURCE_PATH)
    feature_module.main()
    base = pd.read_parquet(feature_module.OUTPUT_PATH)
    metadata = json.loads(feature_module.METADATA_PATH.read_text(encoding="utf-8"))
    quality = pd.read_parquet(feature_module.QUALITY_PATH).set_index("feature")
    assert metadata["imputacao_aplicada"] is False
    assert metadata["scaling_aplicado"] is False
    assert metadata["encoding_aplicado"] is False
    assert metadata["clipping_aplicado"] is False
    assert metadata["nulos_por_feature"]["financial_stability_score"] == 1
    assert quality.loc["financial_stability_score", "valores_ausentes"] == 1
    assert "medianas_de_imputacao" not in metadata
    assert "histórico temporal" not in metadata["supplier_record_count"]["definicao"]
    assert metadata["supplier_record_count"]["historico_temporal_comprovado"] is False
    assert feature_module.calcular_hash(feature_module.SOURCE_PATH) == original_hash
    assert pd.isna(base.set_index("supplier_id").loc["B", "financial_stability_score"])
