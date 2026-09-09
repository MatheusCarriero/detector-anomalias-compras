"""Prepara a base pré-modelagem do Supplier Risk, preservando valores ausentes."""

import hashlib
import json
import platform
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SOURCE_PATH = (
    PROJECT_ROOT / "data" / "external" / "supplier_risk"
    / "supplier_risk_dataset.csv"
)
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "supplier_risk"
OUTPUT_PATH = OUTPUT_DIR / "supplier_features_base.parquet"
QUALITY_PATH = OUTPUT_DIR / "supplier_features_quality.parquet"
METADATA_PATH = OUTPUT_DIR / "supplier_features_base_metadata.json"
PIPELINE_VERSION = "2.0.0"

IDENTIFIER_COLUMN = "Supplier_ID"
RECORD_COUNT_FEATURE = "supplier_record_count"
RECORD_COUNT_DEFINITION = (
    "Quantidade de registros distintos da fonte associados ao fornecedor "
    "após a remoção das duplicatas exatas."
)
OUTPUT_NAMES = {
    "Financial_Stability_Score": "financial_stability_score",
    "On_Time_Delivery_Rate": "on_time_delivery_rate",
    "Defect_Rate": "defect_rate",
    "Geopolitical_Risk_Index": "geopolitical_risk_index",
    "Lead_Time_Days": "lead_time_days",
    "Alternative_Suppliers_Available": "alternative_suppliers_available",
    "Contract_Length_Months": "contract_length_months",
    "Environmental_Compliance": "environmental_compliance",
    "Previous_Disruptions": "previous_disruptions",
}
FEATURE_COLUMNS = list(OUTPUT_NAMES)
FINAL_FEATURE_COLUMNS = [*OUTPUT_NAMES.values(), RECORD_COUNT_FEATURE]
PROHIBITED_COLUMNS = ["Risk_Level", "Risk_Category", "Risk_Class"]
DERIVED_COLUMNS = ["Delivery_Quality_Index", "Supplier_Dependency_Score"]
CATEGORICAL_COLUMNS = ["Country", "Region", "Industry", "Supplier_Tier"]
EXCLUDED_COLUMNS = [
    *PROHIBITED_COLUMNS, IDENTIFIER_COLUMN,
    *DERIVED_COLUMNS, *CATEGORICAL_COLUMNS,
]


def calcular_hash(caminho):
    """Calcula SHA-256 sem carregar o arquivo inteiro na memória."""
    hash_sha256 = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            hash_sha256.update(bloco)
    return hash_sha256.hexdigest().upper()


def validar_entrada(dados):
    """Aceita nulos nas features, mas rejeita chaves e números inválidos."""
    if dados.empty:
        raise ValueError("Dataset de origem vazio; nenhum fornecedor disponível.")
    if IDENTIFIER_COLUMN not in dados:
        raise ValueError("Coluna obrigatória Supplier_ID não encontrada.")
    ausentes = sorted(set(FEATURE_COLUMNS) - set(dados.columns))
    if ausentes:
        raise ValueError("Features obrigatórias ausentes: " + ", ".join(ausentes))
    if dados[IDENTIFIER_COLUMN].isna().any():
        raise ValueError("Supplier_ID nulo: a consolidação não pode perder fornecedores.")
    if dados[IDENTIFIER_COLUMN].astype("string").str.strip().eq("").any():
        raise ValueError("Supplier_ID vazio ou composto apenas por espaços.")

    numericos = pd.DataFrame(index=dados.index)
    for coluna in FEATURE_COLUMNS:
        original = dados[coluna]
        convertido = pd.to_numeric(original, errors="coerce")
        invalidos = original.notna() & convertido.isna()
        if invalidos.any():
            raise ValueError(
                f"Feature {coluna}: {int(invalidos.sum())} valor(es) "
                "não pode(m) ser convertido(s) validamente para número."
            )
        if pd.api.types.is_complex_dtype(convertido.dtype):
            raise ValueError(f"Feature {coluna}: números complexos não são aceitos.")
        convertido = convertido.astype("float64")
        if np.isinf(convertido.to_numpy()).any():
            raise ValueError(f"Feature {coluna}: valores infinitos não são aceitos.")
        numericos[coluna] = convertido
    return numericos


def validar_saida(base, ids_esperados):
    """Reconcilia conjuntos de IDs, schema e finitude; nulos são permitidos."""
    if base.empty:
        raise ValueError("Base consolidada vazia.")
    if base.columns.tolist() != ["supplier_id", *FINAL_FEATURE_COLUMNS]:
        raise ValueError("Schema da base diferente do contrato de features.")
    if base["supplier_id"].isna().any():
        raise ValueError("supplier_id nulo na base consolidada.")
    if base["supplier_id"].duplicated().any():
        raise ValueError("supplier_id duplicado após a consolidação.")

    ids_obtidos = set(base["supplier_id"])
    perdidos = set(ids_esperados) - ids_obtidos
    inesperados = ids_obtidos - set(ids_esperados)
    if perdidos or inesperados:
        raise ValueError(
            "Falha na reconciliação de Supplier_ID: "
            f"{len(perdidos)} perdido(s), {len(inesperados)} inesperado(s)."
        )
    for feature in FINAL_FEATURE_COLUMNS:
        if not pd.api.types.is_numeric_dtype(base[feature]):
            raise ValueError(f"Feature final não numérica: {feature}.")
        if np.isinf(base[feature].to_numpy(dtype=float)).any():
            raise ValueError(f"Feature final contém infinito: {feature}.")
    contagens = base[RECORD_COUNT_FEATURE]
    if contagens.isna().any() or (contagens < 1).any() or (contagens % 1 != 0).any():
        raise ValueError("supplier_record_count deve ser inteiro positivo.")
    return {
        "ids_antes": len(ids_esperados),
        "ids_apos": len(ids_obtidos),
        "ids_perdidos": len(perdidos),
        "ids_inesperados": len(inesperados),
        "ids_duplicados": int(base["supplier_id"].duplicated().sum()),
        "conjuntos_identicos": True,
    }


def preparar_base(dados):
    """Deduplica a fonte e consolida somente valores do próprio fornecedor."""
    numericos = validar_entrada(dados)
    ids_esperados = set(dados[IDENTIFIER_COLUMN])
    # Comparação exata de todas as colunas da fonte, antes da conversão.
    manter = ~dados.duplicated()
    distintos = numericos.loc[manter].copy()
    distintos[IDENTIFIER_COLUMN] = dados.loc[manter, IDENTIFIER_COLUMN]
    grupos = distintos.groupby(IDENTIFIER_COLUMN, sort=True)
    contagens = grupos.size().rename(RECORD_COUNT_FEATURE)

    # Mediana intrafornecedor: não aprende valores em outros fornecedores.
    # Se todos os valores da feature no grupo são nulos, ela continua nula.
    agregado = grupos[FEATURE_COLUMNS].median()
    if not agregado.isna().equals(grupos[FEATURE_COLUMNS].count().eq(0)):
        raise ValueError("A consolidação alterou indevidamente a ausência de valores.")
    base = (
        agregado.join(contagens, validate="one_to_one")
        .reset_index()
        .rename(columns={IDENTIFIER_COLUMN: "supplier_id", **OUTPUT_NAMES})
    )
    base = base[["supplier_id", *FINAL_FEATURE_COLUMNS]]
    reconciliacao = validar_saida(base, ids_esperados)
    if int(base[RECORD_COUNT_FEATURE].sum()) != int(manter.sum()):
        raise ValueError("A soma de supplier_record_count não reconcilia a deduplicação.")

    variacoes_validas = grupos[FEATURE_COLUMNS].nunique().gt(1)
    variacoes_com_nulos = grupos[FEATURE_COLUMNS].nunique(dropna=False).gt(1)
    registro = {
        "linhas_iniciais": len(dados),
        "duplicatas_exatas_removidas": int((~manter).sum()),
        "linhas_apos_deduplicacao": int(manter.sum()),
        "reconciliacao_ids": reconciliacao,
        "fornecedores_com_multiplos_registros": int(contagens.gt(1).sum()),
        "fornecedores_com_variacao_numerica_preenchida": int(
            variacoes_validas.any(axis=1).sum()
        ),
        "fornecedores_com_variacao_de_ausencia": int(
            (variacoes_com_nulos & ~variacoes_validas).any(axis=1).sum()
        ),
        "supplier_record_count_distribuicao": {
            str(valor): int(quantidade)
            for valor, quantidade in contagens.value_counts().sort_index().items()
        },
        "colunas_fonte": dados.columns.tolist(),
        "dtypes_fonte": dados.dtypes.astype(str).to_dict(),
    }
    return base, registro


def gerar_qualidade(base):
    """Produz auditoria separada da matriz; não transforma as features."""
    registros = []
    for feature in FINAL_FEATURE_COLUMNS:
        serie = base[feature]
        presentes = int(serie.notna().sum())
        negativos = int(serie.lt(0).sum())
        observacoes = []
        if negativos:
            observacoes.append(
                "Valores negativos: significado de domínio pendente de confirmação."
            )
        if feature == "environmental_compliance":
            observacoes.append(
                "Valores > 100: possível inconsistência de domínio "
                "pendente de confirmação da escala original; sem clipping."
            )
        if feature == "lead_time_days":
            observacoes.append(
                "O significado de lead time igual a zero precisa ser confirmado; "
                "zeros preservados."
            )
        if feature == "geopolitical_risk_index":
            observacoes.append("Feature provisória sujeita à validação da origem.")
        if feature == RECORD_COUNT_FEATURE:
            observacoes.append(
                "Contagem de registros distintos da fonte, sem histórico temporal "
                "comprovado; experimento futuro COM e SEM a feature."
            )
        acima = serie[serie > 100] if feature == "environmental_compliance" else None
        registros.append({
            "feature": feature,
            "dtype": str(serie.dtype),
            "quantidade_fornecedores": len(base),
            "valores_presentes": presentes,
            "valores_ausentes": int(serie.isna().sum()),
            "cobertura_percentual": 100 * presentes / len(base),
            "minimo": float(serie.min()) if presentes else None,
            "maximo": float(serie.max()) if presentes else None,
            "quantidade_zeros": int(serie.eq(0).sum()),
            "quantidade_negativos": negativos,
            "quantidade_acima_100": len(acima) if acima is not None else None,
            "minimo_acima_100": (
                float(acima.min()) if acima is not None and not acima.empty else None
            ),
            "maximo_acima_100": (
                float(acima.max()) if acima is not None and not acima.empty else None
            ),
            "observacoes_dominio": " ".join(observacoes),
        })
    return pd.DataFrame(registros)


def versoes_dependencias():
    versoes = {"Python": platform.python_version()}
    for pacote in ["pandas", "numpy", "pyarrow", "scikit-learn"]:
        try:
            versoes[pacote] = version(pacote)
        except PackageNotFoundError:
            versoes[pacote] = "não disponível"
    return versoes


def criar_metadata(base, qualidade, registro, hash_fonte):
    # to_json representa ausências da auditoria como null, nunca NaN no JSON.
    dominio = json.loads(qualidade.to_json(orient="records", double_precision=15))
    return {
        "pipeline_version": PIPELINE_VERSION,
        "nome_modelo": "Supplier Risk Model",
        "data_geracao": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset_origem": SOURCE_PATH.relative_to(PROJECT_ROOT).as_posix(),
        "hash_dataset_origem_sha256": hash_fonte,
        "dataset_base": OUTPUT_PATH.relative_to(PROJECT_ROOT).as_posix(),
        "dataset_qualidade": QUALITY_PATH.relative_to(PROJECT_ROOT).as_posix(),
        "status": "base pré-modelagem; não passar diretamente ao fit()",
        "unidade_analise": "fornecedor",
        "quantidade_final_fornecedores": len(base),
        "quantidade_final_features": len(FINAL_FEATURE_COLUMNS),
        "features": FINAL_FEATURE_COLUMNS,
        "coluna_rastreabilidade": "supplier_id",
        "uso_identificador": ["rastreabilidade", "split", "associação futura do score"],
        "dtypes_base": base.dtypes.astype(str).to_dict(),
        "colunas_excluidas": sorted(
            set(registro["colunas_fonte"]) - set(FEATURE_COLUMNS)
        ),
        "exclusoes_previstas": EXCLUDED_COLUMNS,
        "features_provisorias": {
            "geopolitical_risk_index": {
                "status": "feature provisória sujeita à validação da origem",
                "decisao": "manter temporariamente o valor da fonte principal",
                "nao_comprovados": [
                    "fonte original do índice", "fórmula de enriquecimento",
                    "data de referência", "periodicidade",
                    "metodologia do mapeamento por país",
                ],
            },
        },
        "tratamento_duplicidades": (
            "remoção somente de linhas exatas considerando todas as colunas "
            "da fonte, antes da conversão numérica"
        ),
        "estrategia_consolidacao": (
            "mediana intrafornecedor dos valores presentes de cada feature; "
            "grupos sem valor conhecido permanecem nulos"
        ),
        "supplier_record_count": {
            "definicao": RECORD_COUNT_DEFINITION,
            "historico_temporal_comprovado": False,
            "avaliacao_futura": "experimento COM e SEM supplier_record_count",
            "interpretacao": (
                "Na auditoria da fonte atual, os valores numéricos preenchidos "
                "não variam por fornecedor; diferenças parecem relacionadas "
                "principalmente a preenchimento/incompletude. Conferir os "
                "contadores desta execução em validacoes_estruturais."
            ),
        },
        "nulos_por_feature": {
            feature: int(base[feature].isna().sum())
            for feature in FINAL_FEATURE_COLUMNS
        },
        "cobertura_por_feature": {
            linha["feature"]: linha["cobertura_percentual"] for linha in dominio
        },
        "validacoes_dominio": dominio,
        "validacoes_estruturais": registro,
        "imputacao_aplicada": False,
        "scaling_aplicado": False,
        "normalizacao_aplicada": False,
        "padronizacao_aplicada": False,
        "encoding_aplicado": False,
        "clipping_aplicado": False,
        "outliers_estatisticos": (
            "não classificados nem tratados nesta etapa; os alertas de domínio "
            "não constituem detecção estatística de anomalias"
        ),
        "observacoes_data_leakage": [
            "Realizar o split antes de aprender parâmetros de imputação ou encoding.",
            "Validação e teste somente aplicam os transformadores aprendidos no treino.",
            "Risk_Level e classificações equivalentes nunca são features.",
            "Labels podem ser alvos supervisionados ou referências de avaliação futuras.",
            "supplier_id e o dataset de qualidade não pertencem à matriz de features.",
            "Categóricas e indicadores derivados permanecem fora da baseline.",
            "Não usar o legado com imputação global para futuras métricas.",
        ],
        "dependencias": versoes_dependencias(),
    }


def main():
    print("=" * 70)
    print("SUPPLIER RISK — BASE PRÉ-MODELAGEM")
    print("=" * 70)
    if not SOURCE_PATH.is_file():
        raise FileNotFoundError(f"Dataset não encontrado: {SOURCE_PATH}")
    hash_antes = calcular_hash(SOURCE_PATH)
    try:
        dados = pd.read_csv(SOURCE_PATH, dtype={IDENTIFIER_COLUMN: "string"})
    except pd.errors.EmptyDataError as erro:
        raise ValueError("Dataset de origem vazio ou sem cabeçalho.") from erro

    base, registro = preparar_base(dados)
    qualidade = gerar_qualidade(base)
    metadata = criar_metadata(base, qualidade, registro, hash_antes)
    if calcular_hash(SOURCE_PATH) != hash_antes:
        raise RuntimeError("A fonte foi alterada durante o processamento; saída cancelada.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    base.to_parquet(OUTPUT_PATH, index=False)
    qualidade.to_parquet(QUALITY_PATH, index=False)
    metadata["hash_dataset_base_sha256"] = calcular_hash(OUTPUT_PATH)
    metadata["hash_dataset_qualidade_sha256"] = calcular_hash(QUALITY_PATH)
    with METADATA_PATH.open("w", encoding="utf-8") as arquivo:
        json.dump(metadata, arquivo, ensure_ascii=False, indent=2, allow_nan=False)
        arquivo.write("\n")

    print(f"Fonte: {SOURCE_PATH}")
    print(f"Linhas iniciais: {registro['linhas_iniciais']}")
    print(f"Duplicatas exatas removidas: {registro['duplicatas_exatas_removidas']}")
    print(f"Linhas após deduplicação: {registro['linhas_apos_deduplicacao']}")
    print(f"Reconciliação de IDs: {registro['reconciliacao_ids']}")
    print(f"Fornecedores finais: {len(base)}")
    print(f"Features: {len(FINAL_FEATURE_COLUMNS)}")
    print(f"Nulos preservados: {int(base[FINAL_FEATURE_COLUMNS].isna().sum().sum())}")
    print(f"Distribuição de registros: {registro['supplier_record_count_distribuicao']}")
    print("\nCobertura e domínio (auditoria; não são features adicionais):")
    print(qualidade.drop(columns="observacoes_dominio").to_string(index=False))
    print("\nSem imputação, scaling, encoding, clipping, EDA ou treinamento.")
    print(f"Base: {OUTPUT_PATH}")
    print(f"Qualidade: {QUALITY_PATH}")
    print(f"Metadata: {METADATA_PATH}")
    print(f"Hash da fonte preservado: {hash_antes}")
    print("=" * 70)


if __name__ == "__main__":
    main()
