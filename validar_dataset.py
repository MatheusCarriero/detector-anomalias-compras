from pathlib import Path

import pandas as pd


# ============================================================
# CAMINHOS
# ============================================================

pasta_projeto = Path(__file__).resolve().parent
pasta_database = pasta_projeto / "DataBase"


# ============================================================
# CARREGAMENTO
# ============================================================

labels = pd.read_parquet(
    pasta_database / "labels.parquet"
)

invoices = pd.read_parquet(
    pasta_database / "invoices.parquet"
)

suppliers = pd.read_parquet(
    pasta_database / "suppliers.parquet"
)


print("=" * 70)
print("VALIDAÇÃO DO DATASET")
print("=" * 70)


# ============================================================
# IS_FRAUD X FRAUD_TYPE
# ============================================================

print("\n")
print("=" * 70)
print("IS_FRAUD X FRAUD_TYPE")
print("=" * 70)

tabela = pd.crosstab(
    labels["is_fraud"],
    labels["fraud_type"],
)

print(tabela)


# ============================================================
# FRAUDES MARCADAS COMO NONE
# ============================================================

print("\n")
print("=" * 70)
print("FRAUDES COM FRAUD_TYPE = NONE")
print("=" * 70)

fraude_none = labels[
    (labels["is_fraud"] == 1)
    & (labels["fraud_type"] == "NONE")
]

print(
    f"Quantidade: {len(fraude_none):,}"
)

print("\nPrimeiros registros:")

print(
    fraude_none
    .head(20)
    .to_string(index=False)
)


# ============================================================
# NÃO FRAUDE COM TIPO DE FRAUDE
# ============================================================

print("\n")
print("=" * 70)
print("NÃO FRAUDES COM FRAUD_TYPE DIFERENTE DE NONE")
print("=" * 70)

normal_com_tipo = labels[
    (labels["is_fraud"] == 0)
    & (labels["fraud_type"] != "NONE")
]

print(
    f"Quantidade: {len(normal_com_tipo):,}"
)

print("\nPrimeiros registros:")

print(
    normal_com_tipo
    .head(20)
    .to_string(index=False)
)


# ============================================================
# FRAUD TAGS
# ============================================================

print("\n")
print("=" * 70)
print("FRAUD TAGS MAIS FREQUENTES")
print("=" * 70)

print(
    labels["fraud_tags"]
    .value_counts()
    .head(20)
)


# ============================================================
# EXPLICAÇÕES DOS CASOS INCONSISTENTES
# ============================================================

print("\n")
print("=" * 70)
print("EXPLICAÇÕES DOS FRAUD_TYPE NONE MARCADOS COMO FRAUDE")
print("=" * 70)

print(
    fraude_none["explanations"]
    .value_counts()
    .head(20)
)


# ============================================================
# QUANTIDADE POR TIPO DE FRAUDE
# ============================================================

fraudes = labels[
    labels["is_fraud"] == 1
]

print("\n")
print("=" * 70)
print("TIPOS ENTRE REGISTROS MARCADOS COMO FRAUDE")
print("=" * 70)

print(
    fraudes["fraud_type"]
    .value_counts()
)


# ============================================================
# VALORES POR TIPO DE FRAUDE
# ============================================================

dados = invoices.merge(
    labels[
        [
            "invoice_id",
            "is_fraud",
            "fraud_type",
        ]
    ],
    on="invoice_id",
    how="left",
)


print("\n")
print("=" * 70)
print("VALORES DAS FATURAS POR TIPO DE FRAUDE")
print("=" * 70)

estatisticas = (
    dados
    .groupby("fraud_type")["invoice_amount"]
    .agg(
        count="count",
        mean="mean",
        median="median",
        min="min",
        max="max",
        std="std",
    )
    .sort_values(
        "mean",
        ascending=False,
    )
)

print(estatisticas)


# ============================================================
# FORNECEDORES: CAMPOS DE RISCO
# ============================================================

dados_fornecedor = dados.merge(
    suppliers,
    on="supplier_id",
    how="left",
)


print("\n")
print("=" * 70)
print("SUPPLIER RISK SCORE: NORMAL X FRAUDE")
print("=" * 70)

print(
    dados_fornecedor
    .groupby("is_fraud")["supplier_risk_score"]
    .agg(
        [
            "mean",
            "median",
            "min",
            "max",
        ]
    )
)


print("\n")
print("=" * 70)
print("BLACKLISTED FLAG: NORMAL X FRAUDE")
print("=" * 70)

print(
    pd.crosstab(
        dados_fornecedor["blacklisted_flag"],
        dados_fornecedor["is_fraud"],
        normalize="index",
    )
    * 100
)


print("\nValidação concluída.")