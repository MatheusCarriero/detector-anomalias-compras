import zipfile
from pathlib import Path


# Pasta principal do projeto
pasta_projeto = Path(__file__).resolve().parent

# Pasta DataBase
pasta_database = pasta_projeto / "DataBase"

# ZIP auxiliar
arquivo_zip = (
    pasta_database
    / "dataset_auxiliar_kpi_compras.zip"
)

# Nome que vamos usar para o CSV extraído
arquivo_saida = (
    pasta_database
    / "dataset_auxiliar_kpi_compras.csv"
)


print("=" * 70)
print("EXTRAÇÃO DO DATASET AUXILIAR")
print("=" * 70)


if not arquivo_zip.exists():
    print("\nERRO: ZIP auxiliar não encontrado.")
    print(f"Caminho esperado: {arquivo_zip}")
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