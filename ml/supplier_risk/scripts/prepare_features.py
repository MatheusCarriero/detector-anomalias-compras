import hashlib
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# ============================================================
# CAMINHOS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SOURCE_PATH = (
    PROJECT_ROOT
    / "data"
    / "external"
    / "supplier_risk"
    / "supplier_risk_dataset.csv"
)
OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "supplier_risk"
)
OUTPUT_PATH = OUTPUT_DIR / "supplier_features.parquet"
METADATA_PATH = OUTPUT_DIR / "supplier_features_metadata.json"


# ============================================================
# CONTRATO DE FEATURES
# ============================================================

IDENTIFIER_COLUMN = "Supplier_ID"
RECORD_COUNT_FEATURE = "supplier_record_count"

FEATURE_COLUMNS = [
    "Financial_Stability_Score",
    "On_Time_Delivery_Rate",
    "Defect_Rate",
    "Geopolitical_Risk_Index",
    "Lead_Time_Days",
    "Alternative_Suppliers_Available",
    "Contract_Length_Months",
    "Environmental_Compliance",
    "Previous_Disruptions",
]

OUTPUT_NAMES = {
    "Supplier_ID": "supplier_id",
    "Financial_Stability_Score": "financial_stability_score",
    "On_Time_Delivery_Rate": "on_time_delivery_rate",
    "Defect_Rate": "defect_rate",
    "Geopolitical_Risk_Index": "geopolitical_risk_index",
    "Lead_Time_Days": "lead_time_days",
    "Alternative_Suppliers_Available": (
        "alternative_suppliers_available"
    ),
    "Contract_Length_Months": "contract_length_months",
    "Environmental_Compliance": "environmental_compliance",
    "Previous_Disruptions": "previous_disruptions",
}

FINAL_FEATURE_COLUMNS = [
    OUTPUT_NAMES[coluna]
    for coluna in FEATURE_COLUMNS
] + [RECORD_COUNT_FEATURE]

PROHIBITED_COLUMNS = [
    "Risk_Level",
    "Risk_Category",
]

DERIVED_COLUMNS = [
    "Delivery_Quality_Index",
    "Supplier_Dependency_Score",
]

CATEGORICAL_COLUMNS = [
    "Country",
    "Region",
    "Industry",
    "Supplier_Tier",
]

EXCLUDED_COLUMNS = [
    *PROHIBITED_COLUMNS,
    IDENTIFIER_COLUMN,
    *DERIVED_COLUMNS,
    *CATEGORICAL_COLUMNS,
]


# ============================================================
# UTILITÁRIOS
# ============================================================

def calcular_hash(caminho):
    hash_sha256 = hashlib.sha256()

    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            hash_sha256.update(bloco)

    return hash_sha256.hexdigest().upper()


def validar_colunas(dados):
    colunas_obrigatorias = {
        IDENTIFIER_COLUMN,
        *FEATURE_COLUMNS,
    }
    colunas_ausentes = sorted(
        colunas_obrigatorias - set(dados.columns)
    )

    if colunas_ausentes:
        raise ValueError(
            "Colunas obrigatórias ausentes: "
            + ", ".join(colunas_ausentes)
        )


def validar_indices_derivados(dados):
    print("\nValidação dos índices derivados:")

    if {
        "Delivery_Quality_Index",
        "On_Time_Delivery_Rate",
        "Defect_Rate",
    }.issubset(dados.columns):
        esperado = (
            dados["On_Time_Delivery_Rate"]
            * (1 - dados["Defect_Rate"] / 100)
        )
        validos = (
            dados["Delivery_Quality_Index"].notna()
            & esperado.notna()
        )
        diferenca = (
            dados.loc[validos, "Delivery_Quality_Index"]
            - esperado.loc[validos]
        ).abs()
        percentual = (
            (diferenca <= 0.0001).mean() * 100
            if len(diferenca)
            else 0
        )
        print(
            "- Delivery_Quality_Index reproduz On_Time_Delivery_Rate "
            f"e Defect_Rate em {percentual:.2f}% dos valores válidos."
        )

    if {
        "Supplier_Dependency_Score",
        "Alternative_Suppliers_Available",
    }.issubset(dados.columns):
        esperado = 1 / (
            dados["Alternative_Suppliers_Available"] + 1
        )
        validos = (
            dados["Supplier_Dependency_Score"].notna()
            & esperado.notna()
        )
        diferenca = (
            dados.loc[validos, "Supplier_Dependency_Score"]
            - esperado.loc[validos]
        ).abs()
        percentual = (
            (diferenca <= 0.0001).mean() * 100
            if len(diferenca)
            else 0
        )
        print(
            "- Supplier_Dependency_Score reproduz "
            "Alternative_Suppliers_Available em "
            f"{percentual:.2f}% dos valores válidos."
        )


def analisar_outliers(dados):
    linhas = []

    for coluna in FEATURE_COLUMNS:
        serie = dados[coluna].dropna()
        q1 = serie.quantile(0.25)
        q3 = serie.quantile(0.75)
        iqr = q3 - q1
        limite_inferior = q1 - 1.5 * iqr
        limite_superior = q3 + 1.5 * iqr
        outliers = int(
            (
                (serie < limite_inferior)
                | (serie > limite_superior)
            ).sum()
        )
        linhas.append(
            {
                "feature": coluna,
                "min": serie.min(),
                "median": serie.median(),
                "max": serie.max(),
                "iqr_outliers": outliers,
            }
        )

    return pd.DataFrame(linhas)


def validar_saida(dados, features):
    quantidade_nulos = int(
        dados[features].isnull().sum().sum()
    )
    quantidade_infinitos = int(
        np.isinf(dados[features].to_numpy()).sum()
    )
    fornecedores_duplicados = int(
        dados["supplier_id"].duplicated().sum()
    )
    perfis_duplicados = int(
        dados[features].duplicated().sum()
    )

    if quantidade_nulos:
        raise ValueError(
            "O dataset final contém valores nulos nas features."
        )

    if quantidade_infinitos:
        raise ValueError(
            "O dataset final contém valores infinitos nas features."
        )

    if fornecedores_duplicados:
        raise ValueError(
            "O dataset final contém fornecedores duplicados."
        )

    return {
        "nulos": quantidade_nulos,
        "infinitos": quantidade_infinitos,
        "fornecedores_duplicados": fornecedores_duplicados,
        "perfis_duplicados": perfis_duplicados,
    }


# ============================================================
# PIPELINE
# ============================================================

def main():
    print("=" * 70)
    print("PREPARAÇÃO DE FEATURES — SUPPLIER RISK")
    print("=" * 70)

    if not SOURCE_PATH.exists():
        raise FileNotFoundError(
            f"Dataset não encontrado: {SOURCE_PATH}"
        )

    hash_antes = calcular_hash(SOURCE_PATH)
    dados = pd.read_csv(SOURCE_PATH)

    validar_colunas(dados)

    print("\nCarregamento e validação inicial:")
    print(f"- Arquivo: {SOURCE_PATH}")
    print(f"- Registros: {len(dados):,}")
    print(
        "- Fornecedores: "
        f"{dados[IDENTIFIER_COLUMN].nunique(dropna=True):,}"
    )
    print(f"- Colunas: {len(dados.columns)}")
    print(
        "- Células nulas: "
        f"{int(dados.isnull().sum().sum()):,}"
    )
    print(
        "- Linhas totalmente duplicadas: "
        f"{int(dados.duplicated().sum()):,}"
    )

    print("\nColunas e tipos:")
    print(dados.dtypes.to_string())

    print("\nValores nulos por coluna:")
    print(dados.isnull().sum().to_string())

    print("\nValores únicos por coluna:")
    print(dados.nunique(dropna=True).to_string())

    print("\nCampos proibidos encontrados:")
    proibidos_encontrados = [
        coluna
        for coluna in PROHIBITED_COLUMNS
        if coluna in dados.columns
    ]
    for coluna in proibidos_encontrados:
        print(f"- {coluna}: excluído das features")

    validar_indices_derivados(dados)

    print("\nVariáveis categóricas avaliadas:")
    for coluna in CATEGORICAL_COLUMNS:
        if coluna in dados.columns:
            print(
                f"- {coluna}: "
                f"{dados[coluna].nunique(dropna=True)} categorias; "
                "não utilizada nesta primeira versão"
            )

    duplicadas_exatas = int(dados.duplicated().sum())
    dados_sem_duplicatas = dados.drop_duplicates().copy()

    contagens_por_fornecedor = (
        dados_sem_duplicatas
        .groupby(IDENTIFIER_COLUMN)
        .size()
        .rename(RECORD_COUNT_FEATURE)
    )
    fornecedores_multiplos = int(
        (contagens_por_fornecedor > 1).sum()
    )

    print("\nConsolidação por fornecedor:")
    print(f"- Duplicatas exatas removidas: {duplicadas_exatas:,}")
    print(
        "- Registros distintos após deduplicação: "
        f"{len(dados_sem_duplicatas):,}"
    )
    print(
        "- Fornecedores com múltiplos registros distintos: "
        f"{fornecedores_multiplos:,}"
    )
    print(
        "- Estratégia: mediana por fornecedor para todas as "
        "features numéricas aprovadas"
    )
    print(
        "- supplier_record_count: quantidade de registros "
        "distintos usados na consolidação"
    )

    features_originais = dados_sem_duplicatas[
        FEATURE_COLUMNS
    ].copy()
    features_convertidas = (
        features_originais
        .apply(pd.to_numeric, errors="coerce")
        .replace([np.inf, -np.inf], np.nan)
    )

    conversoes_invalidas = {
        coluna: int(
            features_convertidas[coluna].isnull().sum()
            - features_originais[coluna].isnull().sum()
        )
        for coluna in FEATURE_COLUMNS
    }

    dados_numericos = pd.concat(
        [
            dados_sem_duplicatas[[IDENTIFIER_COLUMN]],
            features_convertidas,
        ],
        axis=1,
    )

    consolidados = (
        dados_numericos
        .groupby(IDENTIFIER_COLUMN, as_index=False)
        [FEATURE_COLUMNS]
        .median()
        .merge(
            contagens_por_fornecedor.reset_index(),
            on=IDENTIFIER_COLUMN,
            how="left",
            validate="one_to_one",
        )
    )

    print("\nConversões numéricas inválidas:")
    for coluna, quantidade in conversoes_invalidas.items():
        print(f"- {coluna}: {quantidade}")

    outliers = analisar_outliers(consolidados)
    print("\nAnálise de escala e outliers antes da imputação:")
    print(outliers.to_string(index=False))
    print(
        "\nObservação: outliers não foram removidos ou limitados, "
        "pois podem representar sinais relevantes de risco."
    )

    valores_imputacao = (
        consolidados[FEATURE_COLUMNS]
        .median()
    )
    nulos_antes_imputacao = (
        consolidados[FEATURE_COLUMNS]
        .isnull()
        .sum()
    )

    consolidados = consolidados.assign(
        **{
            coluna: consolidados[coluna].fillna(
                valores_imputacao[coluna]
            )
            for coluna in FEATURE_COLUMNS
        }
    )

    print("\nImputação por mediana do conjunto consolidado:")
    for coluna in FEATURE_COLUMNS:
        print(
            f"- {coluna}: "
            f"{int(nulos_antes_imputacao[coluna])} valores; "
            f"mediana = {valores_imputacao[coluna]:.6f}"
        )

    dataset_final = consolidados.rename(
        columns=OUTPUT_NAMES
    )
    features_finais = FINAL_FEATURE_COLUMNS
    dataset_final = dataset_final[
        ["supplier_id", *features_finais]
    ]

    validacao = validar_saida(
        dataset_final,
        features_finais,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    dataset_final.to_parquet(
        OUTPUT_PATH,
        index=False,
    )

    hash_depois = calcular_hash(SOURCE_PATH)

    if hash_antes != hash_depois:
        raise RuntimeError(
            "O hash do dataset original foi alterado durante o pipeline."
        )

    metadata = {
        "nome_modelo": "Supplier Risk Model",
        "dataset_origem": str(
            SOURCE_PATH.relative_to(PROJECT_ROOT)
        ).replace("\\", "/"),
        "hash_dataset_origem_sha256": hash_antes,
        "data_geracao": datetime.now()
        .astimezone()
        .isoformat(timespec="seconds"),
        "quantidade_final_fornecedores": len(dataset_final),
        "quantidade_final_features": len(features_finais),
        "features": features_finais,
        "coluna_rastreabilidade": "supplier_id",
        "colunas_excluidas": EXCLUDED_COLUMNS,
        "tratamentos_aplicados": [
            "remoção de linhas totalmente duplicadas",
            "consolidação por Supplier_ID com mediana",
            (
                "cálculo de supplier_record_count após a remoção "
                "de duplicatas exatas"
            ),
            "conversão das features aprovadas para valores numéricos",
            "substituição de valores infinitos por valores nulos",
            "imputação de valores nulos pela mediana",
            "preservação de outliers como possíveis sinais de risco",
            "normalização dos nomes das features para snake_case",
        ],
        "observacoes_data_leakage": [
            (
                "Risk_Level e Risk_Category não integram o dataset "
                "de features por representarem possíveis labels."
            ),
            (
                "supplier_id é preservado apenas para rastreabilidade "
                "e não deve ser fornecido ao modelo."
            ),
            (
                "Delivery_Quality_Index e Supplier_Dependency_Score "
                "foram excluídos por serem derivados de features "
                "já aprovadas."
            ),
            (
                "Em experimentos futuros, os parâmetros de imputação "
                "devem ser aprendidos exclusivamente no conjunto de "
                "treino e apenas aplicados à validação e ao teste."
            ),
        ],
    }

    with METADATA_PATH.open("w", encoding="utf-8") as arquivo:
        json.dump(
            metadata,
            arquivo,
            ensure_ascii=False,
            indent=2,
        )
        arquivo.write("\n")

    print("\n" + "=" * 70)
    print("DATASET FINAL")
    print("=" * 70)
    print(f"Fornecedores: {len(dataset_final):,}")
    print(f"Features: {len(features_finais)}")
    print("Nomes das features:")
    for feature in features_finais:
        print(f"- {feature}")
    print(f"Valores nulos finais: {validacao['nulos']}")
    print(f"Valores infinitos finais: {validacao['infinitos']}")
    print(
        "Fornecedores duplicados finais: "
        f"{validacao['fornecedores_duplicados']}"
    )
    print(
        "Perfis de features duplicados: "
        f"{validacao['perfis_duplicados']}"
    )
    print(f"Hash da fonte preservado: {hash_antes}")
    print(f"Arquivo salvo em: {OUTPUT_PATH}")
    print(f"Metadata salvo em: {METADATA_PATH}")
    print("=" * 70)


if __name__ == "__main__":
    main()
