import re
import unicodedata
from pathlib import Path

import pandas as pd

# ============================================================
# CAMINHOS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SUPPLIER_RISK_DIR = (
    PROJECT_ROOT / "data" / "external" / "supplier_risk"
)
PURCHASE_ORDERS_DIR = (
    PROJECT_ROOT / "data" / "external" / "purchase_orders"
)
REPORT_PATH = (
    PROJECT_ROOT / "docs" / "external_datasets_analysis.md"
)


# ============================================================
# UTILITÁRIOS
# ============================================================

def normalizar_texto(valor):
    texto = unicodedata.normalize("NFKD", str(valor))
    texto = texto.encode("ascii", "ignore").decode("ascii")
    texto = re.sub(r"[^a-zA-Z0-9]+", " ", texto)
    return " ".join(texto.lower().split())


def contem_termo(coluna, termos):
    nome = normalizar_texto(coluna)
    return any(
        normalizar_texto(termo) in nome
        for termo in termos
    )


def formatar_numero(valor, casas=4):
    if pd.isna(valor):
        return "—"

    if isinstance(valor, int):
        return f"{valor:,}".replace(",", ".")

    return f"{float(valor):,.{casas}f}"


def escapar_markdown(valor):
    return str(valor).replace("|", "\\|").replace("\n", " ")


def tabela_markdown(cabecalhos, linhas):
    resultado = [
        "| " + " | ".join(cabecalhos) + " |",
        "| " + " | ".join("---" for _ in cabecalhos) + " |",
    ]

    for linha in linhas:
        resultado.append(
            "| "
            + " | ".join(
                escapar_markdown(valor)
                for valor in linha
            )
            + " |"
        )

    return resultado


def localizar_coluna_fornecedor(dados):
    prioridades = [
        "supplier id",
        "supplier name",
        "fornecedor id",
        "nome fornecedor",
    ]

    for termo in prioridades:
        for coluna in dados.columns:
            if normalizar_texto(coluna) == termo:
                return coluna

    return None


def resumo_qualidade(dados):
    coluna_fornecedor = localizar_coluna_fornecedor(dados)

    return {
        "registros": len(dados),
        "colunas": len(dados.columns),
        "fornecedores": (
            dados[coluna_fornecedor].nunique(dropna=True)
            if coluna_fornecedor is not None
            else None
        ),
        "nulos": int(dados.isnull().sum().sum()),
        "colunas_com_nulos": int(
            (dados.isnull().sum() > 0).sum()
        ),
        "duplicadas": int(dados.duplicated().sum()),
    }


def resumo_numerico(dados):
    linhas = []

    for coluna in dados.select_dtypes(include="number").columns:
        serie = dados[coluna]
        descricao = serie.describe()
        linhas.append(
            [
                f"`{coluna}`",
                formatar_numero(int(descricao["count"]), 0),
                formatar_numero(descricao["mean"]),
                formatar_numero(descricao["std"]),
                formatar_numero(descricao["min"]),
                formatar_numero(descricao["50%"]),
                formatar_numero(descricao["max"]),
            ]
        )

    return linhas


# ============================================================
# CLASSIFICAÇÃO — SUPPLIER RISK
# ============================================================

SUPPLIER_LABEL_TERMS = [
    "risk level",
    "risk category",
    "risk class",
    "risk label",
    "target",
]

SUPPLIER_IDENTIFICATION_TERMS = [
    "supplier id",
    "supplier name",
    "fornecedor id",
    "nome fornecedor",
]

SUPPLIER_CATEGORY_RULES = [
    (
        "possíveis labels",
        SUPPLIER_LABEL_TERMS,
    ),
    (
        "identificação",
        SUPPLIER_IDENTIFICATION_TERMS,
    ),
    (
        "financeiras",
        [
            "financial",
            "stability",
            "credit",
            "revenue",
            "turnover",
            "financeiro",
            "estabilidade",
        ],
    ),
    (
        "qualidade",
        [
            "quality",
            "defect",
            "compliance",
            "qualidade",
            "defeito",
            "conformidade",
        ],
    ),
    (
        "entrega",
        [
            "delivery",
            "lead time",
            "entrega",
            "prazo",
        ],
    ),
    (
        "risco",
        [
            "risk",
            "dependency",
            "alternative supplier",
            "disruption",
            "supplier tier",
            "contract length",
            "risco",
            "dependencia",
            "interrupcao",
        ],
    ),
    (
        "localização",
        [
            "country",
            "region",
            "city",
            "latitude",
            "longitude",
            "pais",
            "regiao",
        ],
    ),
]


def classificar_coluna_supplier(coluna):
    for categoria, termos in SUPPLIER_CATEGORY_RULES:
        if contem_termo(coluna, termos):
            return categoria

    # Campos de contexto setorial ou contratual são tratados como risco
    # contextual quando não se encaixam nas demais categorias.
    return "risco"


def orientacao_supplier(coluna):
    nome = normalizar_texto(coluna)
    categoria = classificar_coluna_supplier(coluna)

    if categoria == "possíveis labels":
        return (
            "Excluir das features; reservar para avaliação ou futuro "
            "modelo supervisionado."
        )

    if categoria == "identificação":
        return (
            "Não usar diretamente; manter apenas para junção, "
            "agrupamento e rastreabilidade."
        )

    if nome in {
        "delivery quality index",
        "supplier dependency score",
    }:
        return (
            "Uso condicionado à auditoria da fórmula e da origem "
            "temporal do indicador."
        )

    return "Candidato inicial, sujeito à validação e ao pré-processamento."


# ============================================================
# CLASSIFICAÇÃO — PURCHASE ORDERS
# ============================================================

PURCHASE_LABEL_TERMS = [
    "supplier risk",
    "maverick spend",
    "po status",
    "supplier status",
    "invoice status",
    "payment status",
    "on time delivery",
    "days late",
    "actual delivery",
    "invoice match",
]

PURCHASE_IDENTIFICATION_TERMS = [
    "po number",
    "supplier id",
    "supplier name",
    "item code",
    "item description",
    "requestor name",
    "approver name",
    "contract id",
]

PURCHASE_CATEGORY_RULES = [
    (
        "possíveis labels",
        PURCHASE_LABEL_TERMS,
    ),
    (
        "identificação",
        PURCHASE_IDENTIFICATION_TERMS,
    ),
    (
        "financeira",
        [
            "price",
            "amount",
            "total",
            "line net",
            "saving",
            "discount",
            "tax",
            "budget",
            "currency",
            "payment terms",
            "preco",
            "valor",
            "orcamento",
        ],
    ),
    (
        "qualidade",
        [
            "quality",
            "compliance",
            "esg",
            "qualidade",
            "conformidade",
        ],
    ),
    (
        "fornecedor",
        [
            "supplier",
            "preferred supplier",
            "local international",
            "fornecedor",
        ],
    ),
    (
        "operação",
        [
            "po ",
            "date",
            "year",
            "quarter",
            "month",
            "type",
            "category",
            "quantity",
            "unit of measure",
            "requested delivery",
            "lead time",
            "department",
            "cost centre",
            "contract",
            "single source",
            "data",
            "categoria",
            "quantidade",
            "entrega",
        ],
    ),
]


def classificar_coluna_purchase(coluna):
    for categoria, termos in PURCHASE_CATEGORY_RULES:
        if contem_termo(coluna, termos):
            return categoria

    return "operação"


def orientacao_purchase(coluna):
    nome = normalizar_texto(coluna)
    categoria = classificar_coluna_purchase(coluna)

    if categoria == "identificação":
        return (
            "Não usar diretamente; manter para rastreabilidade, "
            "junções ou agregações."
        )

    if nome in {
        "supplier risk",
        "maverick spend",
        "po status",
        "supplier status",
    }:
        return (
            "Possível classificação ou resultado; excluir inicialmente "
            "e reservar para avaliação."
        )

    if nome in {
        "actual delivery",
        "days late",
        "on time delivery",
        "invoice status",
        "payment status",
        "invoice match type",
    }:
        return (
            "Informação pós-evento; não usar em um score calculado no "
            "momento da criação ou aprovação do pedido."
        )

    if nome in {
        "po date",
        "requested delivery",
        "contract start",
        "contract end",
    }:
        return (
            "Não usar como texto bruto; considerar somente transformações "
            "temporais definidas no futuro."
        )

    if nome in {
        "discount amount",
        "tax amount",
        "line total gross",
        "line net",
        "line total inc tax",
        "budget total",
        "savings amount",
        "savings pct",
    }:
        return (
            "Indicador calculado ou redundante; auditar fórmula e "
            "colinearidade antes do uso."
        )

    if nome == "supplier esg score":
        return (
            "Score externo; auditar metodologia e temporalidade antes "
            "de utilizar."
        )

    return "Candidato inicial, sujeito à validação e ao pré-processamento."


# ============================================================
# AUDITORIA DE COLUNAS E PLANILHAS
# ============================================================

def auditar_colunas(dados, classificador, orientador):
    linhas = []

    for coluna in dados.columns:
        quantidade_nulos = int(dados[coluna].isnull().sum())
        percentual_nulos = (
            quantidade_nulos / len(dados) * 100
            if len(dados)
            else 0
        )

        linhas.append(
            [
                f"`{coluna}`",
                str(dados[coluna].dtype),
                classificador(coluna),
                formatar_numero(quantidade_nulos, 0),
                f"{percentual_nulos:.2f}%",
                formatar_numero(
                    int(dados[coluna].nunique(dropna=True)),
                    0,
                ),
                orientador(coluna),
            ]
        )

    return linhas


def classificar_planilha(nome_planilha, dados):
    nome = normalizar_texto(nome_planilha)

    if any(
        termo in nome
        for termo in [
            "vocabulary",
            "notes",
            "dictionary",
            "documentation",
            "glossary",
        ]
    ):
        return "documental"

    colunas_normalizadas = [
        normalizar_texto(coluna)
        for coluna in dados.columns
    ]

    sinais_transacionais = [
        "po number",
        "supplier id",
        "unit price",
        "quantity",
        "budget total",
    ]

    pontuacao = sum(
        any(
            sinal in coluna
            for coluna in colunas_normalizadas
        )
        for sinal in sinais_transacionais
    )

    if pontuacao >= 3:
        return "transacional"

    return "auxiliar"


def colunas_por_categoria(dados, classificador):
    categorias = {}

    for coluna in dados.columns:
        categoria = classificador(coluna)
        categorias.setdefault(categoria, []).append(coluna)

    return categorias


def carregar_supplier_risk():
    if not SUPPLIER_RISK_DIR.exists():
        raise FileNotFoundError(
            f"Diretório não encontrado: {SUPPLIER_RISK_DIR}"
        )

    arquivos = sorted(SUPPLIER_RISK_DIR.glob("*.csv"))

    if not arquivos:
        raise FileNotFoundError(
            "Nenhum CSV encontrado em "
            f"{SUPPLIER_RISK_DIR}"
        )

    return {
        caminho: pd.read_csv(caminho)
        for caminho in arquivos
    }


def carregar_purchase_orders():
    if not PURCHASE_ORDERS_DIR.exists():
        raise FileNotFoundError(
            f"Diretório não encontrado: {PURCHASE_ORDERS_DIR}"
        )

    arquivos = sorted(
        caminho
        for caminho in PURCHASE_ORDERS_DIR.iterdir()
        if caminho.suffix.lower() in {".xlsx", ".xlsm"}
    )

    if not arquivos:
        raise FileNotFoundError(
            "Nenhum arquivo Excel encontrado em "
            f"{PURCHASE_ORDERS_DIR}"
        )

    resultado = {}

    for caminho in arquivos:
        resultado[caminho] = pd.read_excel(
            caminho,
            sheet_name=None,
        )

    return resultado


def comparar_versoes_supplier(dados_supplier):
    if len(dados_supplier) < 2:
        return []

    itens = list(dados_supplier.items())
    caminho_referencia, dados_referencia = min(
        itens,
        key=lambda item: len(item[1].columns),
    )
    caminho_enriquecido, dados_enriquecidos = max(
        itens,
        key=lambda item: len(item[1].columns),
    )

    if len(dados_referencia) != len(dados_enriquecidos):
        return []

    colunas_compartilhadas = [
        coluna
        for coluna in dados_referencia.columns
        if coluna in dados_enriquecidos.columns
    ]

    comparacao = []

    for coluna in colunas_compartilhadas:
        referencia = dados_referencia[coluna]
        enriquecida = dados_enriquecidos[coluna]
        iguais = (
            referencia.eq(enriquecida)
            | (referencia.isna() & enriquecida.isna())
        )
        diferentes = int((~iguais).sum())

        comparacao.append(
            [
                f"`{coluna}`",
                formatar_numero(int(iguais.sum()), 0),
                formatar_numero(diferentes, 0),
                f"{iguais.mean() * 100:.2f}%",
                (
                    f"`{caminho_referencia.name}` × "
                    f"`{caminho_enriquecido.name}`"
                ),
            ]
        )

    return comparacao


# ============================================================
# RECOMENDAÇÕES
# ============================================================

def selecionar_colunas(dados, nomes_normalizados):
    nomes_normalizados = set(nomes_normalizados)
    return [
        coluna
        for coluna in dados.columns
        if normalizar_texto(coluna) in nomes_normalizados
    ]


def recomendacoes_supplier(dados):
    candidatos_principais = selecionar_colunas(
        dados,
        [
            "financial stability score",
            "on time delivery rate",
            "defect rate",
            "geopolitical risk index",
            "lead time days",
            "alternative suppliers available",
            "contract length months",
            "environmental compliance",
            "previous disruptions",
        ],
    )

    contexto_categorico = selecionar_colunas(
        dados,
        [
            "country",
            "region",
            "industry",
            "supplier tier",
        ],
    )

    uso_condicionado = selecionar_colunas(
        dados,
        [
            "delivery quality index",
            "supplier dependency score",
        ],
    )

    excluir = [
        coluna
        for coluna in dados.columns
        if classificar_coluna_supplier(coluna)
        in {"identificação", "possíveis labels"}
    ]

    return {
        "candidatos_principais": candidatos_principais,
        "contexto_categorico": contexto_categorico,
        "uso_condicionado": uso_condicionado,
        "excluir": excluir,
    }


def recomendacoes_purchase(dados):
    candidatos_principais = selecionar_colunas(
        dados,
        [
            "po type",
            "supplier tier",
            "payment terms",
            "category",
            "sub category",
            "unit of measure",
            "unit price",
            "quantity",
            "discount pct",
            "tax pct",
            "currency",
            "budget unit price",
            "requested delivery",
            "department",
            "cost centre",
            "contract type",
            "single source flag",
            "preferred supplier",
            "local international",
        ],
    )

    uso_pos_evento = selecionar_colunas(
        dados,
        [
            "actual delivery",
            "days late",
            "on time delivery",
            "invoice status",
            "payment status",
            "invoice match type",
            "lead time days",
        ],
    )

    uso_condicionado = selecionar_colunas(
        dados,
        [
            "supplier esg score",
            "discount amount",
            "tax amount",
            "line total gross",
            "line net",
            "line total inc tax",
            "budget total",
            "savings amount",
            "savings pct",
        ],
    )

    excluir = [
        coluna
        for coluna in dados.columns
        if classificar_coluna_purchase(coluna)
        in {"identificação", "possíveis labels"}
        and coluna not in uso_pos_evento
    ]

    return {
        "candidatos_principais": candidatos_principais,
        "uso_pos_evento": uso_pos_evento,
        "uso_condicionado": uso_condicionado,
        "excluir": excluir,
    }


# ============================================================
# RELATÓRIO MARKDOWN
# ============================================================

def lista_colunas_markdown(colunas):
    if not colunas:
        return ["- Nenhuma coluna correspondente foi encontrada."]

    return [
        f"- `{coluna}`"
        for coluna in colunas
    ]


def gerar_relatorio(dados_supplier, workbooks_purchase):
    linhas = [
        "# Auditoria dos Datasets para Modelos Externos",
        "",
        "## 1. Objetivo e escopo",
        "",
        (
            "Este documento registra a auditoria inicial dos datasets "
            "externos candidatos aos futuros **Supplier Risk Model** e "
            "**Purchase Risk Model**. A análise é exploratória: nenhum "
            "modelo foi criado, nenhuma feature foi implementada e os "
            "arquivos de dados não foram alterados."
        ),
        "",
        (
            "As recomendações distinguem identificação, possíveis labels, "
            "variáveis disponíveis no momento da decisão e informações "
            "pós-evento. Essa separação é necessária para evitar data "
            "leakage e preservar a auditabilidade dos modelos futuros."
        ),
        "",
        "## 2. Supplier Risk Dataset",
        "",
        f"**Diretório:** `{SUPPLIER_RISK_DIR.relative_to(PROJECT_ROOT).as_posix()}/`",
        "",
        "### 2.1. Arquivos e qualidade geral",
        "",
    ]

    resumo_arquivos = []

    for caminho, dados in dados_supplier.items():
        qualidade = resumo_qualidade(dados)
        resumo_arquivos.append(
            [
                f"`{caminho.name}`",
                formatar_numero(qualidade["registros"], 0),
                formatar_numero(qualidade["colunas"], 0),
                formatar_numero(qualidade["fornecedores"], 0),
                formatar_numero(qualidade["nulos"], 0),
                formatar_numero(qualidade["duplicadas"], 0),
            ]
        )

    linhas.extend(
        tabela_markdown(
            [
                "Arquivo",
                "Registros",
                "Colunas",
                "Fornecedores",
                "Células nulas",
                "Linhas duplicadas",
            ],
            resumo_arquivos,
        )
    )

    linhas.extend(
        [
            "",
            (
                "Os dois arquivos possuem o mesmo número de registros e "
                "compartilham 11 colunas. A versão enriquecida acrescenta "
                "contexto de localização, indústria, tier, qualidade de "
                "entrega e dependência do fornecedor."
            ),
            "",
            "#### Consistência entre as versões",
            "",
        ]
    )

    comparacao_versoes = comparar_versoes_supplier(
        dados_supplier
    )

    if comparacao_versoes:
        linhas.extend(
            tabela_markdown(
                [
                    "Coluna compartilhada",
                    "Valores iguais",
                    "Valores diferentes",
                    "% de igualdade",
                    "Comparação",
                ],
                comparacao_versoes,
            )
        )
        linhas.extend(
            [
                "",
                (
                    "A comparação mostra que `Geopolitical_Risk_Index` "
                    "não é equivalente entre as duas versões, embora as "
                    "demais colunas compartilhadas coincidam. A versão "
                    "autoritativa desse indicador deve ser definida antes "
                    "do treinamento; as duas variantes não devem ser "
                    "misturadas no mesmo experimento."
                ),
                "",
            ]
        )

    for indice, (caminho, dados) in enumerate(
        dados_supplier.items(),
        start=2,
    ):
        linhas.extend(
            [
                f"### 2.{indice}. Auditoria de `{caminho.name}`",
                "",
                "#### Colunas, tipos, categorias e qualidade",
                "",
            ]
        )

        linhas.extend(
            tabela_markdown(
                [
                    "Coluna",
                    "Tipo",
                    "Categoria",
                    "Nulos",
                    "% nulos",
                    "Únicos",
                    "Orientação inicial",
                ],
                auditar_colunas(
                    dados,
                    classificar_coluna_supplier,
                    orientacao_supplier,
                ),
            )
        )

        linhas.extend(
            [
                "",
                "#### Estatísticas numéricas",
                "",
            ]
        )

        linhas.extend(
            tabela_markdown(
                [
                    "Coluna",
                    "Contagem",
                    "Média",
                    "Desvio-padrão",
                    "Mínimo",
                    "Mediana",
                    "Máximo",
                ],
                resumo_numerico(dados),
            )
        )
        linhas.append("")

    dados_supplier_referencia = max(
        dados_supplier.values(),
        key=lambda dados: len(dados.columns),
    )
    recomendacao_supplier = recomendacoes_supplier(
        dados_supplier_referencia
    )

    linhas.extend(
        [
            "### 2.4. Riscos de data leakage e uso indevido",
            "",
            (
                "`Risk_Level` representa uma classificação final de risco "
                "e não deve entrar como feature em um modelo não "
                "supervisionado. O campo deve ser reservado para análise "
                "exploratória, avaliação ou como possível target de um "
                "experimento supervisionado futuro. A mesma regra se aplica "
                "a eventuais campos como `Risk_Category`, `Risk_Class` ou "
                "classificações derivadas."
            ),
            "",
            (
                "`Delivery_Quality_Index` e `Supplier_Dependency_Score` "
                "podem ser úteis, mas são indicadores derivados. Suas "
                "fórmulas, dados de origem e disponibilidade temporal devem "
                "ser auditados antes do uso para evitar redundância ou "
                "vazamento indireto."
            ),
            "",
            (
                "`Supplier_ID` deve permanecer apenas como chave de "
                "rastreabilidade, agrupamento e separação dos dados. Seu "
                "valor nominal não deve ser apresentado diretamente ao "
                "modelo."
            ),
            "",
            "### 2.5. Recomendação inicial para o Supplier Risk Model",
            "",
            "#### Candidatos principais",
            "",
        ]
    )
    linhas.extend(
        lista_colunas_markdown(
            recomendacao_supplier["candidatos_principais"]
        )
    )
    linhas.extend(
        [
            "",
            "#### Contexto categórico sujeito a codificação",
            "",
        ]
    )
    linhas.extend(
        lista_colunas_markdown(
            recomendacao_supplier["contexto_categorico"]
        )
    )
    linhas.extend(
        [
            "",
            "#### Uso condicionado à auditoria da origem",
            "",
        ]
    )
    linhas.extend(
        lista_colunas_markdown(
            recomendacao_supplier["uso_condicionado"]
        )
    )
    linhas.extend(
        [
            "",
            "#### Exclusão inicial",
            "",
        ]
    )
    linhas.extend(
        lista_colunas_markdown(
            recomendacao_supplier["excluir"]
        )
    )
    linhas.extend(
        [
            "",
            (
                "Antes do treinamento futuro, recomenda-se remover ou "
                "investigar as linhas totalmente duplicadas, definir uma "
                "política de imputação ajustada somente no treino e decidir "
                "se a validação deve medir generalização para fornecedores "
                "já observados ou para fornecedores inéditos."
            ),
            "",
            "## 3. Purchase Orders Dataset",
            "",
            f"**Diretório:** `{PURCHASE_ORDERS_DIR.relative_to(PROJECT_ROOT).as_posix()}/`",
            "",
            "### 3.1. Arquivos e classificação das planilhas",
            "",
        ]
    )

    inventario_planilhas = []
    planilhas_transacionais = []

    for caminho, planilhas in workbooks_purchase.items():
        for nome_planilha, dados in planilhas.items():
            papel = classificar_planilha(nome_planilha, dados)
            qualidade = resumo_qualidade(dados)
            inventario_planilhas.append(
                [
                    f"`{caminho.name}`",
                    f"`{nome_planilha}`",
                    papel,
                    formatar_numero(qualidade["registros"], 0),
                    formatar_numero(qualidade["colunas"], 0),
                    formatar_numero(qualidade["nulos"], 0),
                    formatar_numero(qualidade["duplicadas"], 0),
                ]
            )

            if papel == "transacional":
                planilhas_transacionais.append(
                    (caminho, nome_planilha, dados)
                )

    linhas.extend(
        tabela_markdown(
            [
                "Arquivo",
                "Planilha",
                "Papel",
                "Registros",
                "Colunas",
                "Células nulas",
                "Linhas duplicadas",
            ],
            inventario_planilhas,
        )
    )

    linhas.extend(
        [
            "",
            (
                "Planilhas documentais são inventariadas, mas não entram "
                "na auditoria de variáveis para o modelo. Planilhas "
                "auxiliares, como calendários, podem apoiar transformações "
                "futuras, porém não constituem a tabela transacional."
            ),
            "",
        ]
    )

    if not planilhas_transacionais:
        raise ValueError(
            "Nenhuma planilha transacional foi identificada."
        )

    for indice, (caminho, nome_planilha, dados) in enumerate(
        planilhas_transacionais,
        start=2,
    ):
        qualidade = resumo_qualidade(dados)
        linhas.extend(
            [
                (
                    f"### 3.{indice}. Planilha transacional "
                    f"`{nome_planilha}`"
                ),
                "",
                (
                    f"Foram identificados "
                    f"{formatar_numero(qualidade['registros'], 0)} "
                    f"registros, {formatar_numero(qualidade['colunas'], 0)} "
                    f"colunas e "
                    f"{formatar_numero(qualidade['fornecedores'], 0)} "
                    "fornecedores."
                ),
                "",
                "#### Colunas, tipos, categorias e qualidade",
                "",
            ]
        )

        linhas.extend(
            tabela_markdown(
                [
                    "Coluna",
                    "Tipo",
                    "Categoria",
                    "Nulos",
                    "% nulos",
                    "Únicos",
                    "Orientação inicial",
                ],
                auditar_colunas(
                    dados,
                    classificar_coluna_purchase,
                    orientacao_purchase,
                ),
            )
        )

        linhas.extend(
            [
                "",
                "#### Estatísticas numéricas",
                "",
            ]
        )
        linhas.extend(
            tabela_markdown(
                [
                    "Coluna",
                    "Contagem",
                    "Média",
                    "Desvio-padrão",
                    "Mínimo",
                    "Mediana",
                    "Máximo",
                ],
                resumo_numerico(dados),
            )
        )
        linhas.append("")

    dados_purchase_referencia = planilhas_transacionais[0][2]
    recomendacao_purchase = recomendacoes_purchase(
        dados_purchase_referencia
    )

    linhas.extend(
        [
            "### 3.3. Riscos de data leakage e uso indevido",
            "",
            (
                "A definição do instante de scoring é obrigatória. Para um "
                "score calculado na criação ou aprovação do pedido, campos "
                "como `Actual Delivery`, `Days Late`, `On Time Delivery`, "
                "`Lead Time Days`, `Invoice Status`, `Payment Status` e "
                "`Invoice Match Type` ainda não estariam disponíveis e, "
                "portanto, causariam data leakage temporal."
            ),
            "",
            (
                "Classificações existentes como `Supplier Risk`, "
                "`Supplier Status`, `PO Status` e `Maverick Spend` não "
                "devem ser usadas diretamente na primeira versão. Elas "
                "podem representar regras ou resultados já consolidados e "
                "devem ser reservadas para avaliação exploratória até que "
                "sua origem seja compreendida."
            ),
            "",
            (
                "Identificadores e nomes não devem entrar diretamente no "
                "modelo. Datas em texto precisam de uma estratégia temporal "
                "explícita. Totais e valores derivados devem ser auditados "
                "para evitar redundância matemática com preço, quantidade, "
                "desconto, imposto e orçamento."
            ),
            "",
            (
                "Não foi encontrada uma coluna explícita de compliance na "
                "planilha transacional. `Supplier ESG Score` é o indicador "
                "mais próximo de qualidade ou conformidade do fornecedor, "
                "mas sua metodologia deve ser auditada antes do uso."
            ),
            "",
            "### 3.4. Recomendação inicial para o Purchase Risk Model",
            "",
            "#### Candidatos disponíveis no momento do pedido",
            "",
        ]
    )
    linhas.extend(
        lista_colunas_markdown(
            recomendacao_purchase["candidatos_principais"]
        )
    )
    linhas.extend(
        [
            "",
            "#### Variáveis pós-evento para análise separada",
            "",
        ]
    )
    linhas.extend(
        lista_colunas_markdown(
            recomendacao_purchase["uso_pos_evento"]
        )
    )
    linhas.extend(
        [
            "",
            "#### Uso condicionado à auditoria ou redundância",
            "",
        ]
    )
    linhas.extend(
        lista_colunas_markdown(
            recomendacao_purchase["uso_condicionado"]
        )
    )
    linhas.extend(
        [
            "",
            "#### Exclusão inicial",
            "",
        ]
    )
    linhas.extend(
        lista_colunas_markdown(
            recomendacao_purchase["excluir"]
        )
    )
    linhas.extend(
        [
            "",
            (
                "As futuras features derivadas podem representar desvio de "
                "orçamento, variação de preço, anomalia de lead time, "
                "concentração por fornecedor e risco de status. Essas "
                "transformações ainda não foram implementadas e deverão ser "
                "ajustadas exclusivamente no conjunto de treino."
            ),
            "",
            "## 4. Recomendação para os modelos futuros",
            "",
            "### 4.1. Supplier Risk Model",
            "",
            (
                "A primeira versão deve priorizar indicadores elementares "
                "financeiros, de qualidade, entrega, compliance e risco "
                "contextual. `Risk_Level` deve permanecer fora das features. "
                "O tratamento de nulos, duplicidades e variáveis categóricas "
                "deve ser aprendido apenas com o treino."
            ),
            "",
            "### 4.2. Purchase Risk Model",
            "",
            (
                "A primeira versão deve adotar um instante de decisão claro, "
                "preferencialmente a criação ou aprovação do pedido. Isso "
                "permite excluir resultados posteriores e construir um score "
                "operacional prospectivo. Uma análise pós-entrega poderá ser "
                "desenvolvida como camada separada."
            ),
            "",
            "### 4.3. Controles obrigatórios",
            "",
            "- preservar os datasets originais;",
            "- documentar a unidade de observação e o instante de scoring;",
            "- remover duplicidades somente em uma camada processada;",
            "- ajustar imputação e codificação exclusivamente no treino;",
            "- manter possíveis labels fora das features;",
            "- validar a origem de scores e índices derivados;",
            "- registrar features, parâmetros, métricas e versões;",
            "- manter `supplier_risk_score` e `purchase_risk_score` separados e auditáveis.",
            "",
            "## 5. Conclusão",
            "",
            (
                "Os dois datasets possuem variáveis relevantes para modelos "
                "especializados, mas exigem controles diferentes. Supplier "
                "Risk demanda tratamento de duplicidades, nulos e exclusão "
                "de classificações finais. Purchase Orders apresenta boa "
                "completude, mas requer uma separação rigorosa entre dados "
                "disponíveis no pedido e resultados observados posteriormente."
            ),
            "",
            (
                "A recomendação é iniciar cada modelo com um conjunto "
                "conservador de variáveis, manter indicadores derivados sob "
                "auditoria e comparar todas as evoluções contra uma baseline "
                "reproduzível."
            ),
            "",
        ]
    )

    return "\n".join(linhas)


# ============================================================
# SAÍDA NO TERMINAL
# ============================================================

def imprimir_resumo(dados_supplier, workbooks_purchase):
    print("=" * 70)
    print("AUDITORIA DOS DATASETS PARA MODELOS EXTERNOS")
    print("=" * 70)

    print("\nSUPPLIER RISK DATASET")
    print("-" * 70)
    print(f"Arquivos encontrados: {len(dados_supplier)}")

    for caminho, dados in dados_supplier.items():
        qualidade = resumo_qualidade(dados)
        print(f"\nArquivo: {caminho.name}")
        print(f"Registros: {qualidade['registros']:,}")
        print(f"Fornecedores: {qualidade['fornecedores']:,}")
        print(f"Colunas: {qualidade['colunas']}")
        print(f"Valores nulos: {qualidade['nulos']:,}")
        print(f"Linhas duplicadas: {qualidade['duplicadas']:,}")
        print("Categorias:")

        for categoria, colunas in colunas_por_categoria(
            dados,
            classificar_coluna_supplier,
        ).items():
            print(f"- {categoria}: {', '.join(colunas)}")

    print("\nPURCHASE ORDERS DATASET")
    print("-" * 70)
    print(f"Arquivos encontrados: {len(workbooks_purchase)}")

    for caminho, planilhas in workbooks_purchase.items():
        print(f"\nArquivo: {caminho.name}")

        for nome_planilha, dados in planilhas.items():
            papel = classificar_planilha(nome_planilha, dados)
            qualidade = resumo_qualidade(dados)
            print(
                f"- {nome_planilha}: {papel}; "
                f"{qualidade['registros']:,} linhas; "
                f"{qualidade['colunas']} colunas"
            )


# ============================================================
# EXECUÇÃO
# ============================================================

dados_supplier = carregar_supplier_risk()
workbooks_purchase = carregar_purchase_orders()

imprimir_resumo(
    dados_supplier,
    workbooks_purchase,
)

relatorio = gerar_relatorio(
    dados_supplier,
    workbooks_purchase,
)

REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
REPORT_PATH.write_text(
    relatorio,
    encoding="utf-8",
)

print("\n" + "=" * 70)
print("AUDITORIA CONCLUÍDA")
print("=" * 70)
print(f"Relatório salvo em: {REPORT_PATH}")
