from pathlib import Path

import numpy as np
import pandas as pd


# ============================================================
# CAMINHOS
# ============================================================

pasta_projeto = Path(__file__).resolve().parent
pasta_database = pasta_projeto / "DataBase"

pasta_processado = pasta_database / "processado"
pasta_processado.mkdir(exist_ok=True)


# ============================================================
# CARREGAMENTO
# ============================================================

print("=" * 70)
print("PREPARAÇÃO DAS FEATURES")
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
# INFORMAÇÕES SEGURAS DO FORNECEDOR
# ============================================================

# NÃO usamos:
# supplier_risk_score
# blacklisted_flag
# avg_invoice_amount
#
# O avg_invoice_amount será calculado por nós mesmos
# utilizando SOMENTE o conjunto de treino.

supplier_info = suppliers[
    [
        "supplier_id",
        "supplier_country",
        "supplier_age_days",
    ]
]


# ============================================================
# JUNÇÃO
# ============================================================

df = invoices.merge(
    supplier_info,
    on="supplier_id",
    how="left"
)

df = df.merge(
    splits,
    on="invoice_id",
    how="left"
)


# ============================================================
# FEATURES DE DATA
# ============================================================

df["invoice_date"] = pd.to_datetime(
    df["invoice_date"]
)

df["month"] = df["invoice_date"].dt.month

df["day_of_week"] = (
    df["invoice_date"]
    .dt.dayofweek
)

df["is_weekend"] = (
    df["day_of_week"] >= 5
).astype(int)


# ============================================================
# VARIÁVEIS CÍCLICAS
# ============================================================

# Horário:
# 23h deve ficar matematicamente próximo de 0h.

df["submission_hour_sin"] = np.sin(
    2 * np.pi
    * df["submission_hour"]
    / 24
)

df["submission_hour_cos"] = np.cos(
    2 * np.pi
    * df["submission_hour"]
    / 24
)


# Dia da semana

df["day_of_week_sin"] = np.sin(
    2 * np.pi
    * df["day_of_week"]
    / 7
)

df["day_of_week_cos"] = np.cos(
    2 * np.pi
    * df["day_of_week"]
    / 7
)


# Mês

df["month_sin"] = np.sin(
    2 * np.pi
    * (df["month"] - 1)
    / 12
)

df["month_cos"] = np.cos(
    2 * np.pi
    * (df["month"] - 1)
    / 12
)


# ============================================================
# CONDIÇÃO DE PAGAMENTO
# ============================================================

# NET30 -> 30
# NET60 -> 60
# NET90 -> 90

df["payment_terms_days"] = (
    df["payment_terms"]
    .str.extract(r"(\d+)")[0]
    .astype(int)
)


# ============================================================
# TIPO DA FATURA
# ============================================================

df["invoice_type_encoded"] = (
    df["invoice_type"]
    .map(
        {
            "GOODS": 0,
            "SERVICES": 1,
        }
    )
)


# ============================================================
# SEPARAÇÃO ANTES DAS ESTATÍSTICAS
# ============================================================

train = df[df["split"] == "train"].copy()
val = df[df["split"] == "val"].copy()
test = df[df["split"] == "test"].copy()


print("\nDivisão inicial:")

print(f"Train: {len(train):,}")
print(f"Val:   {len(val):,}")
print(f"Test:  {len(test):,}")


# ============================================================
# ESTATÍSTICAS CALCULADAS APENAS NO TREINO
# ============================================================

print("\nCalculando estatísticas somente com o TRAIN...")


# ------------------------------------------------------------
# FORNECEDOR
# ------------------------------------------------------------

supplier_stats = (
    train
    .groupby("supplier_id")
    ["invoice_amount"]
    .agg(
        supplier_purchase_count="count",
        supplier_amount_mean="mean",
        supplier_amount_std="std",
    )
    .reset_index()
)


# ------------------------------------------------------------
# DEPARTAMENTO
# ------------------------------------------------------------

department_stats = (
    train
    .groupby("department_id")
    ["invoice_amount"]
    .agg(
        department_purchase_count="count",
        department_amount_mean="mean",
    )
    .reset_index()
)


# ------------------------------------------------------------
# FORNECEDOR + DEPARTAMENTO
# ------------------------------------------------------------

supplier_department_stats = (
    train
    .groupby(
        [
            "supplier_id",
            "department_id",
        ]
    )
    .size()
    .reset_index(
        name="supplier_department_count"
    )
)


# ------------------------------------------------------------
# PAÍS
# ------------------------------------------------------------

country_stats = (
    train["supplier_country"]
    .value_counts()
    .rename("country_count")
    .reset_index()
)


# ============================================================
# MÉDIAS GLOBAIS DO TREINO
# ============================================================

global_amount_mean = (
    train["invoice_amount"].mean()
)

global_amount_std = (
    train["invoice_amount"].std()
)


# ============================================================
# FUNÇÃO PARA APLICAR FEATURES
# ============================================================

def aplicar_features(dados):

    dados = dados.copy()

    dados = dados.merge(
        supplier_stats,
        on="supplier_id",
        how="left",
    )

    dados = dados.merge(
        department_stats,
        on="department_id",
        how="left",
    )

    dados = dados.merge(
        supplier_department_stats,
        on=[
            "supplier_id",
            "department_id",
        ],
        how="left",
    )

    dados = dados.merge(
        country_stats,
        on="supplier_country",
        how="left",
    )


    # ========================================================
    # TRATAMENTO DE CATEGORIAS NÃO VISTAS
    # ========================================================

    dados["supplier_purchase_count"] = (
        dados["supplier_purchase_count"]
        .fillna(0)
    )

    dados["supplier_amount_mean"] = (
        dados["supplier_amount_mean"]
        .fillna(global_amount_mean)
    )

    dados["supplier_amount_std"] = (
        dados["supplier_amount_std"]
        .fillna(global_amount_std)
    )

    dados["department_purchase_count"] = (
        dados["department_purchase_count"]
        .fillna(0)
    )

    dados["department_amount_mean"] = (
        dados["department_amount_mean"]
        .fillna(global_amount_mean)
    )

    dados["supplier_department_count"] = (
        dados["supplier_department_count"]
        .fillna(0)
    )

    dados["country_count"] = (
        dados["country_count"]
        .fillna(0)
    )


    # ========================================================
    # FREQUÊNCIAS
    # ========================================================

    total_train = len(train)

    dados["supplier_frequency"] = (
        dados["supplier_purchase_count"]
        / total_train
    )

    dados["department_frequency"] = (
        dados["department_purchase_count"]
        / total_train
    )

    dados["supplier_department_frequency"] = (
        dados["supplier_department_count"]
        / total_train
    )

    dados["country_frequency"] = (
        dados["country_count"]
        / total_train
    )


    # ========================================================
    # COMPARAÇÃO COM HISTÓRICO DO FORNECEDOR
    # ========================================================

    dados["amount_vs_supplier_mean"] = (
        dados["invoice_amount"]
        / dados["supplier_amount_mean"]
    )


    # Evita divisão por zero

    std_seguro = (
        dados["supplier_amount_std"]
        .replace(0, global_amount_std)
    )

    dados["supplier_amount_zscore"] = (
        (
            dados["invoice_amount"]
            - dados["supplier_amount_mean"]
        )
        / std_seguro
    )


    # ========================================================
    # COMPARAÇÃO COM DEPARTAMENTO
    # ========================================================

    dados["amount_vs_department_mean"] = (
        dados["invoice_amount"]
        / dados["department_amount_mean"]
    )


    # ========================================================
    # LOG DO VALOR
    # ========================================================

    dados["log_invoice_amount"] = np.log1p(
        dados["invoice_amount"]
    )


    return dados


# ============================================================
# APLICAÇÃO
# ============================================================

train = aplicar_features(train)
val = aplicar_features(val)
test = aplicar_features(test)


# ============================================================
# LABELS SOMENTE PARA AVALIAÇÃO
# ============================================================

labels_avaliacao = labels[
    [
        "invoice_id",
        "is_fraud",
        "fraud_type",
    ]
]


train = train.merge(
    labels_avaliacao,
    on="invoice_id",
    how="left",
)

val = val.merge(
    labels_avaliacao,
    on="invoice_id",
    how="left",
)

test = test.merge(
    labels_avaliacao,
    on="invoice_id",
    how="left",
)


# ============================================================
# FEATURES QUE ENTRARÃO NO MODELO
# ============================================================

features_modelo = [

    # Valor
    "invoice_amount",
    "log_invoice_amount",

    # Fornecedor
    "supplier_age_days",
    "supplier_frequency",
    "country_frequency",

    # Histórico
    "amount_vs_supplier_mean",
    "supplier_amount_zscore",

    # Departamento
    "department_frequency",
    "amount_vs_department_mean",

    # Relação fornecedor/departamento
    "supplier_department_frequency",

    # Compra
    "payment_terms_days",
    "invoice_type_encoded",

    # Tempo
    "submission_hour_sin",
    "submission_hour_cos",
    "day_of_week_sin",
    "day_of_week_cos",
    "month_sin",
    "month_cos",
    "is_weekend",
]


# ============================================================
# VERIFICAÇÃO FINAL
# ============================================================

print("\n")
print("=" * 70)
print("FEATURES DO MODELO")
print("=" * 70)

for feature in features_modelo:
    print(f"- {feature}")


print("\nQuantidade de features:")
print(len(features_modelo))


for nome, dados in [
    ("TRAIN", train),
    ("VAL", val),
    ("TEST", test),
]:

    print("\n")
    print("=" * 70)
    print(nome)
    print("=" * 70)

    print(
        "Valores nulos nas features:",
        dados[features_modelo]
        .isnull()
        .sum()
        .sum()
    )

    print(
        "Valores infinitos:",
        np.isinf(
            dados[features_modelo]
        )
        .sum()
        .sum()
    )


# ============================================================
# SALVAMENTO
# ============================================================

colunas_salvar = (
    [
        "invoice_id",
        "split",
        "is_fraud",
        "fraud_type",
    ]
    + features_modelo
)


train[colunas_salvar].to_parquet(
    pasta_processado
    / "train_features.parquet",
    index=False,
)

val[colunas_salvar].to_parquet(
    pasta_processado
    / "val_features.parquet",
    index=False,
)

test[colunas_salvar].to_parquet(
    pasta_processado
    / "test_features.parquet",
    index=False,
)


print("\n")
print("=" * 70)
print("ARQUIVOS CRIADOS")
print("=" * 70)

print(
    pasta_processado
    / "train_features.parquet"
)

print(
    pasta_processado
    / "val_features.parquet"
)

print(
    pasta_processado
    / "test_features.parquet"
)


print("\nPreparação concluída.")