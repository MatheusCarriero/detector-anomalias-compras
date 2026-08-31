from pathlib import Path

import pandas as pd


# ============================================================
# CAMINHOS
# ============================================================

pasta_projeto = Path(__file__).resolve().parent
pasta_database = pasta_projeto / "DataBase"


# ============================================================
# CARREGAMENTO DOS DADOS
# ============================================================

print("=" * 70)
print("CARREGANDO DATASET")
print("=" * 70)

invoices = pd.read_parquet(
    pasta_database / "invoices.parquet"
)

labels = pd.read_parquet(
    pasta_database / "labels.parquet"
)

suppliers = pd.read_parquet(
    pasta_database / "suppliers.parquet"
)

splits = pd.read_parquet(
    pasta_database / "splits.parquet"
)


# ============================================================
# JUNÇÃO PRINCIPAL
# ============================================================

df = invoices.merge(
    labels,
    on="invoice_id",
    how="left"
)

df = df.merge(
    suppliers,
    on="supplier_id",
    how="left"
)

df = df.merge(
    splits,
    on="invoice_id",
    how="left"
)


print("\nDataset combinado:")
print(f"Linhas: {len(df):,}")
print(f"Colunas: {len(df.columns)}")


# ============================================================
# FRAUDES
# ============================================================

print("\n")
print("=" * 70)
print("DISTRIBUIÇÃO DE FRAUDES")
print("=" * 70)

fraudes = df["is_fraud"].value_counts().sort_index()

print(fraudes)

print("\nPercentual:")

percentual_fraudes = (
    df["is_fraud"]
    .value_counts(normalize=True)
    .sort_index()
    * 100
)

print(percentual_fraudes.round(2))


# ============================================================
# TIPOS DE FRAUDE
# ============================================================

print("\n")
print("=" * 70)
print("TIPOS DE FRAUDE")
print("=" * 70)

print(
    df["fraud_type"]
    .value_counts()
)


# ============================================================
# SPLITS
# ============================================================

print("\n")
print("=" * 70)
print("DIVISÃO TRAIN / VALIDATION / TEST")
print("=" * 70)

print(
    df["split"]
    .value_counts()
)


print("\nFraudes por split:")

print(
    pd.crosstab(
        df["split"],
        df["is_fraud"]
    )
)


# ============================================================
# FORNECEDORES
# ============================================================

print("\n")
print("=" * 70)
print("FORNECEDORES")
print("=" * 70)

print(
    f"Quantidade de fornecedores: "
    f"{df['supplier_id'].nunique():,}"
)

print(
    f"Quantidade de países: "
    f"{df['supplier_country'].nunique():,}"
)


# ============================================================
# DEPARTAMENTOS
# ============================================================

print("\n")
print("=" * 70)
print("DEPARTAMENTOS")
print("=" * 70)

print(
    f"Quantidade de departamentos: "
    f"{df['department_id'].nunique():,}"
)


print("\nTop 10 departamentos:")

print(
    df["department_id"]
    .value_counts()
    .head(10)
)


# ============================================================
# MOEDAS
# ============================================================

print("\n")
print("=" * 70)
print("MOEDAS")
print("=" * 70)

print(
    df["currency"]
    .value_counts()
)


# ============================================================
# TIPOS DE INVOICE
# ============================================================

print("\n")
print("=" * 70)
print("TIPOS DE FATURA")
print("=" * 70)

print(
    df["invoice_type"]
    .value_counts()
)


# ============================================================
# CONDIÇÕES DE PAGAMENTO
# ============================================================

print("\n")
print("=" * 70)
print("CONDIÇÕES DE PAGAMENTO")
print("=" * 70)

print(
    df["payment_terms"]
    .value_counts()
)


# ============================================================
# VALORES DAS COMPRAS
# ============================================================

print("\n")
print("=" * 70)
print("ESTATÍSTICAS DOS VALORES")
print("=" * 70)

print(
    df["invoice_amount"]
    .describe()
)


# ============================================================
# VALOR MÉDIO NORMAL X FRAUDE
# ============================================================

print("\n")
print("=" * 70)
print("VALORES: NORMAL X FRAUDE")
print("=" * 70)

print(
    df.groupby("is_fraud")["invoice_amount"]
    .agg(
        [
            "count",
            "mean",
            "median",
            "min",
            "max",
            "std",
        ]
    )
)


# ============================================================
# HORÁRIOS
# ============================================================

print("\n")
print("=" * 70)
print("HORÁRIOS DE SUBMISSÃO")
print("=" * 70)

print(
    df.groupby("submission_hour")
    .size()
)


print("\nFraudes por horário:")

print(
    df[df["is_fraud"] == 1]["submission_hour"]
    .value_counts()
    .sort_index()
)


# ============================================================
# PERÍODO DO DATASET
# ============================================================

print("\n")
print("=" * 70)
print("PERÍODO DOS DADOS")
print("=" * 70)

print(
    f"Primeira fatura: "
    f"{df['invoice_date'].min()}"
)

print(
    f"Última fatura: "
    f"{df['invoice_date'].max()}"
)


# ============================================================
# DUPLICIDADES
# ============================================================

print("\n")
print("=" * 70)
print("VERIFICAÇÃO DE DUPLICIDADES")
print("=" * 70)

print(
    f"Invoice IDs duplicados: "
    f"{df['invoice_id'].duplicated().sum()}"
)


print("\nAnálise concluída.")