import re
import unicodedata
from pathlib import Path
from zipfile import BadZipFile

import pandas as pd

# ============================================================
# CAMINHOS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXTERNAL_DATA_DIR = PROJECT_ROOT / "data" / "external"

SUPPORTED_EXTENSIONS = {
    ".csv",
    ".tsv",
    ".parquet",
    ".xlsx",
    ".xlsm",
}


# ============================================================
# CARREGAMENTO
# ============================================================

def carregar_tabelas(caminho):
    extensao = caminho.suffix.lower()

    if extensao == ".csv":
        return {None: pd.read_csv(caminho)}

    if extensao == ".tsv":
        return {None: pd.read_csv(caminho, sep="\t")}

    if extensao == ".parquet":
        return {None: pd.read_parquet(caminho)}

    if extensao in {".xlsx", ".xlsm"}:
        return pd.read_excel(
            caminho,
            sheet_name=None,
        )

    raise ValueError(f"Formato não suportado: {extensao}")


# ============================================================
# IDENTIFICAÇÃO FLEXÍVEL DE COLUNAS
# ============================================================

def normalizar_texto(valor):
    texto = unicodedata.normalize("NFKD", str(valor))
    texto = texto.encode("ascii", "ignore").decode("ascii")
    texto = re.sub(r"[^a-zA-Z0-9]+", " ", texto)
    return " ".join(texto.lower().split())


def localizar_colunas(dados, termos):
    termos_normalizados = [
        normalizar_texto(termo)
        for termo in termos
    ]

    return [
        coluna
        for coluna in dados.columns
        if any(
            termo in normalizar_texto(coluna)
            for termo in termos_normalizados
        )
    ]


def mostrar_distribuicoes(dados, colunas, titulo):
    if not colunas:
        return

    print(f"\n{titulo}:")

    for coluna in colunas:
        print(f"\n{coluna}:")

        if (
            pd.api.types.is_numeric_dtype(dados[coluna])
            and dados[coluna].nunique(dropna=True) <= 20
        ):
            print(
                dados[coluna]
                .value_counts(dropna=False)
                .sort_index()
                .to_string()
            )
        elif pd.api.types.is_numeric_dtype(dados[coluna]):
            print(
                dados[coluna]
                .describe()
                .to_string()
            )
        else:
            print(
                dados[coluna]
                .value_counts(dropna=False)
                .head(20)
                .to_string()
            )


def mostrar_indicadores_numericos(
    dados,
    colunas,
    titulo,
):
    colunas_numericas = [
        coluna
        for coluna in colunas
        if pd.api.types.is_numeric_dtype(dados[coluna])
    ]

    if not colunas_numericas:
        return

    print(f"\n{titulo}:")
    print(
        dados[colunas_numericas]
        .describe()
        .transpose()
        .to_string()
    )


# ============================================================
# ANÁLISES ESPECÍFICAS
# ============================================================

def analisar_fornecedores(dados):
    colunas_fornecedor = localizar_colunas(
        dados,
        [
            "supplier id",
            "supplier name",
            "fornecedor id",
            "nome fornecedor",
        ],
    )

    if not colunas_fornecedor:
        return

    print("\nQuantidade de fornecedores:")

    for coluna in colunas_fornecedor:
        print(
            f"- {coluna}: "
            f"{dados[coluna].nunique(dropna=True):,}"
        )


def analisar_purchase_orders(dados):
    print("\n" + "-" * 70)
    print("ANÁLISES ESPECÍFICAS — PURCHASE ORDERS")
    print("-" * 70)

    analisar_fornecedores(dados)

    mostrar_distribuicoes(
        dados,
        localizar_colunas(
            dados,
            ["category", "categoria"],
        ),
        "Categorias",
    )

    mostrar_distribuicoes(
        dados,
        localizar_colunas(
            dados,
            ["status", "situacao"],
        ),
        "Status",
    )

    mostrar_distribuicoes(
        dados,
        localizar_colunas(
            dados,
            ["country", "pais"],
        ),
        "Países",
    )

    mostrar_distribuicoes(
        dados,
        localizar_colunas(
            dados,
            ["risk", "risco"],
        ),
        "Distribuição de riscos",
    )

    colunas_entrega = localizar_colunas(
        dados,
        [
            "delivery",
            "lead time",
            "days late",
            "entrega",
            "atraso",
        ],
    )

    mostrar_indicadores_numericos(
        dados,
        colunas_entrega,
        "Indicadores numéricos de entrega",
    )

    mostrar_distribuicoes(
        dados,
        [
            coluna
            for coluna in colunas_entrega
            if not pd.api.types.is_numeric_dtype(
                dados[coluna]
            )
        ],
        "Indicadores categóricos de entrega",
    )

    colunas_financeiras = localizar_colunas(
        dados,
        [
            "price",
            "amount",
            "total",
            "saving",
            "discount",
            "tax",
            "budget",
            "spend",
            "cost",
            "financial",
            "valor",
            "preco",
            "economia",
            "desconto",
            "imposto",
            "orcamento",
            "custo",
        ],
    )

    mostrar_indicadores_numericos(
        dados,
        colunas_financeiras,
        "Indicadores financeiros",
    )


def analisar_supplier_risk(dados):
    print("\n" + "-" * 70)
    print("ANÁLISES ESPECÍFICAS — SUPPLIER RISK")
    print("-" * 70)

    analisar_fornecedores(dados)

    mostrar_distribuicoes(
        dados,
        localizar_colunas(
            dados,
            ["risk", "risco"],
        ),
        "Níveis e scores de risco",
    )

    mostrar_indicadores_numericos(
        dados,
        localizar_colunas(
            dados,
            [
                "financial",
                "financeiro",
                "stability",
                "estabilidade",
                "revenue",
                "cost",
                "amount",
                "value",
                "receita",
                "custo",
                "valor",
            ],
        ),
        "Indicadores financeiros",
    )

    mostrar_indicadores_numericos(
        dados,
        localizar_colunas(
            dados,
            [
                "quality",
                "defect",
                "compliance",
                "disruption",
                "qualidade",
                "defeito",
                "conformidade",
                "interrupcao",
            ],
        ),
        "Indicadores de qualidade",
    )

    mostrar_indicadores_numericos(
        dados,
        localizar_colunas(
            dados,
            [
                "delivery",
                "lead time",
                "days late",
                "entrega",
                "atraso",
            ],
        ),
        "Indicadores de entrega",
    )


# ============================================================
# INSPEÇÃO GERAL
# ============================================================

def inspecionar_tabela(
    caminho,
    nome_planilha,
    dados,
):
    caminho_relativo = caminho.relative_to(PROJECT_ROOT)

    print("\n")
    print("=" * 70)
    print(f"ARQUIVO: {caminho_relativo}")

    if nome_planilha is not None:
        print(f"PLANILHA: {nome_planilha}")

    print("=" * 70)

    print(f"\nQuantidade de linhas: {len(dados):,}")
    print(f"Quantidade de colunas: {len(dados.columns)}")

    print("\nNomes das colunas:")
    for coluna in dados.columns:
        print(f"- {coluna}")

    print("\nTipos dos dados:")
    print(dados.dtypes.to_string())

    print("\nPrimeiros 5 registros:")
    print(dados.head().to_string(index=False))

    valores_nulos = dados.isnull().sum()
    percentual_nulos = (
        valores_nulos
        .div(len(dados) if len(dados) else 1)
        .mul(100)
    )

    resumo_nulos = pd.DataFrame(
        {
            "valores_nulos": valores_nulos,
            "percentual_nulos": percentual_nulos,
        }
    )

    print("\nValores nulos e percentual de nulos:")
    print(resumo_nulos.to_string())

    print("\nQuantidade de valores únicos:")
    print(
        dados.nunique(dropna=True)
        .rename("valores_unicos")
        .to_string()
    )

    print(
        "\nLinhas totalmente duplicadas: "
        f"{dados.duplicated().sum():,}"
    )

    colunas_numericas = dados.select_dtypes(
        include="number"
    )

    print("\nEstatísticas das colunas numéricas:")

    if colunas_numericas.empty:
        print("Nenhuma coluna numérica encontrada.")
    else:
        print(
            colunas_numericas
            .describe()
            .transpose()
            .to_string()
        )

    partes = {
        normalizar_texto(parte)
        for parte in caminho.parts
    }

    if "purchase orders" in partes:
        analisar_purchase_orders(dados)
    elif "supplier risk" in partes:
        analisar_supplier_risk(dados)


# ============================================================
# EXECUÇÃO
# ============================================================

print("=" * 70)
print("INSPEÇÃO DOS DATASETS EXTERNOS")
print("=" * 70)

if not EXTERNAL_DATA_DIR.exists():
    raise FileNotFoundError(
        f"Diretório não encontrado: {EXTERNAL_DATA_DIR}"
    )

arquivos = sorted(
    caminho
    for caminho in EXTERNAL_DATA_DIR.rglob("*")
    if caminho.is_file()
    and caminho.suffix.lower() in SUPPORTED_EXTENSIONS
    and not caminho.name.startswith("~$")
)

if not arquivos:
    raise FileNotFoundError(
        f"Nenhum dataset encontrado em: {EXTERNAL_DATA_DIR}"
    )

print(f"\nArquivos encontrados: {len(arquivos)}")
for caminho in arquivos:
    print(f"- {caminho.relative_to(PROJECT_ROOT)}")

erros = []

for caminho in arquivos:
    try:
        tabelas = carregar_tabelas(caminho)

        for nome_planilha, dados in tabelas.items():
            inspecionar_tabela(
                caminho,
                nome_planilha,
                dados,
            )
    except (
        BadZipFile,
        ImportError,
        OSError,
        TypeError,
        UnicodeError,
        ValueError,
    ) as erro:
        erros.append((caminho, erro))
        print(f"\nERRO ao analisar {caminho}: {erro}")

if erros:
    raise RuntimeError(
        f"Falha na inspeção de {len(erros)} arquivo(s)."
    )

print("\n")
print("=" * 70)
print("INSPEÇÃO CONCLUÍDA")
print("=" * 70)
