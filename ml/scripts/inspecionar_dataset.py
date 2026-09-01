import zipfile
from pathlib import Path

import pandas as pd


# ============================================================
# CAMINHOS DO PROJETO
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DATA_DIR = PROJECT_ROOT / "data" / "raw"
LEGACY_DATA_DIR = PROJECT_ROOT / "DataBase"

RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)

# O primeiro caminho é o recomendado. O segundo mantém compatibilidade
# com o ZIP local da estrutura anterior, que não é versionado.
candidatos_zip = (
    RAW_DATA_DIR / "archive.zip",
    LEGACY_DATA_DIR / "archive.zip",
)

arquivo_zip = next(
    (caminho for caminho in candidatos_zip if caminho.exists()),
    candidatos_zip[0],
)


# ============================================================
# ARQUIVOS QUE REALMENTE PRECISAMOS
# ============================================================

arquivos_interesse = [
    "invoices.parquet",
    "labels.parquet",
    "suppliers.parquet",
    "splits.parquet",
    "images_metadata.parquet",
    "manifest.json",
]


# ============================================================
# VERIFICA SE O ZIP EXISTE
# ============================================================

if not arquivo_zip.exists():
    print("ERRO: archive.zip não encontrado.")
    print("Caminhos aceitos:")
    for caminho in candidatos_zip:
        print(f"- {caminho}")
    exit()


print("=" * 70)
print("EXTRAÇÃO DOS ARQUIVOS NECESSÁRIOS")
print("=" * 70)


# ============================================================
# ABRE O ZIP E EXTRAI SOMENTE OS ARQUIVOS NECESSÁRIOS
# ============================================================

with zipfile.ZipFile(arquivo_zip, "r") as zip_ref:

    arquivos_zip = zip_ref.namelist()

    for nome_desejado in arquivos_interesse:

        arquivo_encontrado = None

        # Procura pelo nome do arquivo,
        # ignorando a pasta interna do ZIP
        for caminho_interno in arquivos_zip:

            if Path(caminho_interno).name == nome_desejado:
                arquivo_encontrado = caminho_interno
                break

        if arquivo_encontrado is None:
            print(f"[NÃO ENCONTRADO] {nome_desejado}")
            continue

        destino = RAW_DATA_DIR / nome_desejado

        # Copia apenas esse arquivo para data/raw
        with zip_ref.open(arquivo_encontrado) as origem:
            with open(destino, "wb") as saida:
                saida.write(origem.read())

        print(f"[OK] {nome_desejado}")


print("\nExtração concluída.")


# ============================================================
# INSPEÇÃO DOS ARQUIVOS PARQUET
# ============================================================

arquivos_parquet = [
    "invoices.parquet",
    "labels.parquet",
    "suppliers.parquet",
    "splits.parquet",
    "images_metadata.parquet",
]


print("\n")
print("=" * 70)
print("INSPEÇÃO DO DATASET")
print("=" * 70)


for nome_arquivo in arquivos_parquet:

    caminho = RAW_DATA_DIR / nome_arquivo

    print("\n")
    print("=" * 70)
    print(f"ARQUIVO: {nome_arquivo}")
    print("=" * 70)

    if not caminho.exists():
        print("ERRO: arquivo não encontrado.")
        continue

    df = pd.read_parquet(caminho)

    print(f"\nQuantidade de linhas: {len(df):,}")
    print(f"Quantidade de colunas: {len(df.columns)}")

    print("\nCOLUNAS:")

    for coluna in df.columns:
        print(f"- {coluna}")

    print("\nTIPOS DOS DADOS:")
    print(df.dtypes)

    print("\nPRIMEIROS 5 REGISTROS:")
    print(df.head().to_string())

    print("\nVALORES NULOS:")
    print(df.isnull().sum())
