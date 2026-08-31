from pathlib import Path
import pandas as pd


# ============================================================
# CAMINHOS
# ============================================================

pasta_projeto = Path(__file__).resolve().parent
pasta_database = pasta_projeto / "DataBase"

arquivo_csv = (
    pasta_database
    / "dataset_auxiliar_kpi_compras.csv"
)


# ============================================================
# VERIFICAÇÃO
# ============================================================

print("=" * 70)
print("INSPEÇÃO DO DATASET AUXILIAR")
print("=" * 70)

if not arquivo_csv.exists():
    print("\nERRO: dataset auxiliar não encontrado.")
    print(f"Caminho esperado: {arquivo_csv}")
    exit()


# ============================================================
# CARREGAMENTO
# ============================================================

df = pd.read_csv(arquivo_csv)


# ============================================================
# INFORMAÇÕES GERAIS
# ============================================================

print(f"\nQuantidade de linhas: {len(df):,}")
print(f"Quantidade de colunas: {len(df.columns)}")


print("\nCOLUNAS:")

for coluna in df.columns:
    print(f"- {coluna}")


# ============================================================
# TIPOS DOS DADOS
# ============================================================

print("\n")
print("=" * 70)
print("TIPOS DOS DADOS")
print("=" * 70)

print(df.dtypes)


# ============================================================
# PRIMEIROS REGISTROS
# ============================================================

print("\n")
print("=" * 70)
print("PRIMEIROS 5 REGISTROS")
print("=" * 70)

print(df.head().to_string())


# ============================================================
# VALORES NULOS
# ============================================================

print("\n")
print("=" * 70)
print("VALORES NULOS")
print("=" * 70)

print(df.isnull().sum())


# ============================================================
# VALORES ÚNICOS
# ============================================================

print("\n")
print("=" * 70)
print("QUANTIDADE DE VALORES ÚNICOS")
print("=" * 70)

for coluna in df.columns:
    print(
        f"{coluna}: "
        f"{df[coluna].nunique(dropna=True)}"
    )


# ============================================================
# ESTATÍSTICAS NUMÉRICAS
# ============================================================

print("\n")
print("=" * 70)
print("ESTATÍSTICAS DAS COLUNAS NUMÉRICAS")
print("=" * 70)

print(
    df.describe()
    .transpose()
    .to_string()
)


# ============================================================
# DUPLICIDADES
# ============================================================

print("\n")
print("=" * 70)
print("DUPLICIDADES")
print("=" * 70)

print(
    f"Linhas totalmente duplicadas: "
    f"{df.duplicated().sum()}"
)


print("\nInspeção concluída.")