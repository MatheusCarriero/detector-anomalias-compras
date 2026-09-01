import zipfile
from pathlib import Path


# Pastas do projeto
PROJECT_ROOT = Path(__file__).resolve().parents[2]
AUXILIARY_DATA_DIR = PROJECT_ROOT / "data" / "auxiliary"
LEGACY_DATA_DIR = PROJECT_ROOT / "DataBase"

AUXILIARY_DATA_DIR.mkdir(parents=True, exist_ok=True)

# O primeiro caminho é o recomendado. O segundo mantém compatibilidade
# com o ZIP local da estrutura anterior, que não é versionado.
candidatos_zip = (
    AUXILIARY_DATA_DIR / "dataset_auxiliar_kpi_compras.zip",
    LEGACY_DATA_DIR / "dataset_auxiliar_kpi_compras.zip",
)

arquivo_zip = next(
    (caminho for caminho in candidatos_zip if caminho.exists()),
    candidatos_zip[0],
)

# Nome que vamos usar para o CSV extraído
arquivo_saida = (
    AUXILIARY_DATA_DIR
    / "dataset_auxiliar_kpi_compras.csv"
)


print("=" * 70)
print("EXTRAÇÃO DO DATASET AUXILIAR")
print("=" * 70)


if not arquivo_zip.exists():
    print("\nERRO: ZIP auxiliar não encontrado.")
    print("Caminhos aceitos:")
    for caminho in candidatos_zip:
        print(f"- {caminho}")
    exit()


with zipfile.ZipFile(arquivo_zip, "r") as zip_ref:

    arquivos = zip_ref.namelist()

    arquivo_csv = None

    for arquivo in arquivos:
        if arquivo.lower().endswith(".csv"):
            arquivo_csv = arquivo
            break

    if arquivo_csv is None:
        print("\nERRO: nenhum arquivo CSV encontrado no ZIP.")
        exit()

    print(f"\nCSV encontrado: {arquivo_csv}")

    with zip_ref.open(arquivo_csv) as origem:
        with open(arquivo_saida, "wb") as destino:
            destino.write(origem.read())


print("\n[OK] Dataset auxiliar extraído.")
print(f"Arquivo criado: {arquivo_saida}")
