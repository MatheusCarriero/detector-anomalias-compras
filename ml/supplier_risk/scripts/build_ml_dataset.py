"""Gera X/y alinhados, aprendendo somente a imputação mediana de TRAIN."""

import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed" / "supplier_risk"
OUTPUT_DIR = PROCESSED_DIR / "ml_ready"
INPUT_PATHS = {
    "features": PROCESSED_DIR / "supplier_features_base.parquet",
    "targets": PROCESSED_DIR / "supplier_targets.parquet",
    "split": PROCESSED_DIR / "supplier_split_assignments.parquet",
}
METADATA_PATH = OUTPUT_DIR / "preprocessing_metadata.json"
PIPELINE_VERSION = "1.0.0"
SPLITS = ("train", "validation", "test")
FEATURES = [
    "financial_stability_score",
    "on_time_delivery_rate",
    "defect_rate",
    "geopolitical_risk_index",
    "lead_time_days",
    "alternative_suppliers_available",
    "contract_length_months",
    "environmental_compliance",
    "previous_disruptions",
    "supplier_record_count",
]


def calcular_hash(caminho):
    with caminho.open("rb") as arquivo:
        return hashlib.file_digest(arquivo, "sha256").hexdigest().upper()


def hash_ordenacao(ids):
    """Fingerprint da lista ordenada, reconstruível pelo arquivo de split."""
    representacao = json.dumps(list(ids), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(representacao.encode("utf-8")).hexdigest().upper()


def validar_ids(dados, contexto):
    if dados.empty:
        raise ValueError(f"{contexto}: dataset vazio.")
    if "supplier_id" not in dados:
        raise ValueError(f"{contexto}: supplier_id ausente.")
    ids = dados["supplier_id"]
    if ids.isna().any():
        raise ValueError(f"{contexto}: supplier_id nulo.")
    if not ids.map(lambda valor: isinstance(valor, str)).all():
        raise ValueError(f"{contexto}: supplier_id deve ser textual, sem conversão implícita.")
    if ids.str.strip().eq("").any():
        raise ValueError(f"{contexto}: supplier_id vazio.")
    if ids.duplicated().any():
        raise ValueError(f"{contexto}: supplier_id duplicado ou atribuído a múltiplos splits.")
    return set(ids)


def validar_schema(dados, esperado, contexto):
    if dados.columns.duplicated().any():
        raise ValueError(f"{contexto}: nomes de colunas duplicados.")
    faltantes = sorted(set(esperado) - set(dados.columns))
    extras = sorted(set(dados.columns) - set(esperado))
    if faltantes or extras:
        raise ValueError(f"{contexto}: colunas ausentes {faltantes}; inesperadas {extras}.")


def validar_numericos(dados, contexto, permitir_nulos):
    for coluna in dados:
        dtype = dados[coluna].dtype
        if (
            not pd.api.types.is_numeric_dtype(dtype)
            or pd.api.types.is_bool_dtype(dtype)
            or pd.api.types.is_complex_dtype(dtype)
        ):
            raise ValueError(f"{contexto}: {coluna} deve ser numérica real, não {dtype}.")
    valores = dados.to_numpy(dtype="float64", na_value=np.nan)
    if np.isinf(valores).any():
        raise ValueError(f"{contexto}: valores infinitos não são aceitos.")
    if not permitir_nulos and np.isnan(valores).any():
        raise ValueError(f"{contexto}: valores nulos após imputação.")


def preparar_particoes(features, targets, split):
    """Reconcilia as chaves antes de joins; não decide ou recalcula o split."""
    ids_base = validar_ids(features, "Features")
    for nome, dados in (("Targets", targets), ("Split", split)):
        ids = validar_ids(dados, nome)
        perdidos, inesperados = ids_base - ids, ids - ids_base
        if perdidos or inesperados:
            raise ValueError(
                f"{nome}: IDs não correspondem à base; "
                f"{len(perdidos)} perdido(s), {len(inesperados)} inesperado(s)."
            )
    validar_schema(features, ["supplier_id", *FEATURES], "Features")
    validar_schema(targets, ["supplier_id", "risk_level"], "Targets")
    validar_schema(split, ["supplier_id", "split"], "Split")
    validar_numericos(features[FEATURES], "Features", permitir_nulos=True)
    validar_numericos(targets[["risk_level"]], "Targets", permitir_nulos=False)
    if not targets["risk_level"].isin([0, 1]).all():
        raise ValueError("Targets: risk_level deve pertencer a {0, 1}.")
    if split["split"].isna().any() or not split["split"].isin(SPLITS).all():
        raise ValueError("Split ausente ou inválido: usar train, validation ou test.")

    associados = (
        features.merge(targets, on="supplier_id", how="left", validate="one_to_one")
        .merge(split, on="supplier_id", how="left", validate="one_to_one")
        .sort_values("supplier_id")
        .reset_index(drop=True)
    )
    if len(associados) != len(features) or set(associados["supplier_id"]) != ids_base:
        raise ValueError("Perda ou inclusão inesperada de fornecedor durante o merge.")
    if associados[["risk_level", "split"]].isna().any().any():
        raise ValueError("Fornecedor sem target ou sem split após o merge.")

    particoes = {}
    for nome in SPLITS:
        grupo = associados.loc[associados["split"].eq(nome)].reset_index(drop=True)
        if grupo.empty:
            raise ValueError(f"Partição {nome} vazia; não é possível preparar os três conjuntos.")
        particoes[nome] = {
            "X": grupo[FEATURES].copy(),
            "y": grupo[["risk_level"]].astype("int8"),
            "supplier_ids": grupo["supplier_id"].tolist(),
        }
    if sum(len(parte["X"]) for parte in particoes.values()) != len(features):
        raise ValueError("As partições não cobrem todos os fornecedores.")
    conjuntos = {nome: set(parte["supplier_ids"]) for nome, parte in particoes.items()}
    overlap = {
        "train_validation": len(conjuntos["train"] & conjuntos["validation"]),
        "train_test": len(conjuntos["train"] & conjuntos["test"]),
        "validation_test": len(conjuntos["validation"] & conjuntos["test"]),
    }
    if any(overlap.values()):
        raise ValueError("Fornecedor presente em mais de uma partição.")
    return particoes, {
        "fornecedores_entrada": len(features),
        "fornecedores_apos_merge": len(associados),
        "ids_perdidos": 0,
        "ids_inesperados": 0,
        "ids_duplicados": 0,
        "conjuntos_ids_identicos": True,
        "overlap": overlap,
    }


def validar_saida(x, y, contexto):
    if x.empty or y.empty or len(x) != len(y):
        raise ValueError(f"{contexto}: X/y vazios ou com quantidades de linhas diferentes.")
    if x.columns.tolist() != FEATURES or y.columns.tolist() != ["risk_level"]:
        raise ValueError(f"{contexto}: schema/ordem das colunas diferente do contrato.")
    indice = pd.RangeIndex(len(x))
    if not x.index.equals(indice) or not y.index.equals(indice):
        raise ValueError(f"{contexto}: índices X/y não correspondem à ordem de saída.")
    if x.index.name is not None or y.index.name is not None:
        raise ValueError(f"{contexto}: identificadores não devem ser persistidos como índice.")
    validar_numericos(x, contexto, permitir_nulos=False)
    validar_numericos(y, contexto + " target", permitir_nulos=False)
    if not y["risk_level"].isin([0, 1]).all():
        raise ValueError(f"{contexto}: target não binário.")


def transformar_particoes(particoes):
    """Único aprendizado permitido: mediana de cada feature exclusivamente em TRAIN."""
    treino = particoes["train"]["X"]
    vazias = treino.columns[treino.isna().all()].tolist()
    if vazias:
        raise ValueError(
            "TRAIN contém features totalmente nulas, sem mediana disponível: "
            + ", ".join(vazias)
            + ". Não remover colunas nem buscar valores em validation/test."
        )
    imputador = SimpleImputer(strategy="median")
    transformados = {"train": imputador.fit_transform(treino)}
    for nome in ("validation", "test"):
        transformados[nome] = imputador.transform(particoes[nome]["X"])

    if imputador.feature_names_in_.tolist() != FEATURES:
        raise ValueError("Imputador ajustado com features diferentes do contrato.")
    if len(imputador.statistics_) != len(FEATURES) or not np.isfinite(imputador.statistics_).all():
        raise ValueError("Imputador não produziu dez medianas finitas aprendidas no treino.")
    saidas = {}
    for nome in SPLITS:
        original = particoes[nome]["X"].to_numpy(dtype="float64", na_value=np.nan)
        resultado = transformados[nome]
        if resultado.shape != original.shape:
            raise ValueError(f"{nome}: imputação alterou a quantidade de linhas/features.")
        conhecidos = ~np.isnan(original)
        if not np.array_equal(resultado[conhecidos], original[conhecidos]):
            raise ValueError(f"{nome}: um valor presente foi alterado pela transformação.")
        medianas = np.broadcast_to(imputador.statistics_, original.shape)
        if not np.array_equal(resultado[~conhecidos], medianas[~conhecidos]):
            raise ValueError(f"{nome}: imputação não utilizou exclusivamente as medianas de TRAIN.")
        x = pd.DataFrame(resultado, columns=FEATURES, dtype="float64")
        y = particoes[nome]["y"].copy()
        validar_saida(x, y, nome)
        saidas[nome] = {"X": x, "y": y}
    return saidas, imputador


def conferir_integridade(hashes):
    for caminho in INPUT_PATHS.values():
        relativo = caminho.relative_to(PROJECT_ROOT).as_posix()
        if calcular_hash(caminho) != hashes[relativo]:
            raise ValueError(f"Arquivo de entrada alterado durante o processamento: {relativo}.")


def main():
    faltantes = [str(caminho) for caminho in INPUT_PATHS.values() if not caminho.is_file()]
    if faltantes:
        raise FileNotFoundError("Entradas obrigatórias não encontradas: " + ", ".join(faltantes))
    hashes = {
        caminho.relative_to(PROJECT_ROOT).as_posix(): calcular_hash(caminho)
        for caminho in INPUT_PATHS.values()
    }
    entradas = {nome: pd.read_parquet(caminho) for nome, caminho in INPUT_PATHS.items()}
    particoes, reconciliacao = preparar_particoes(**entradas)
    saidas, imputador = transformar_particoes(particoes)
    conferir_integridade(hashes)

    metadata = {
        "pipeline_version": PIPELINE_VERSION,
        "data_geracao": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "nome_modelo_futuro": "Supplier Risk Model",
        "status": "ML-Ready validado; nenhum modelo preditivo treinado",
        "features_utilizadas": FEATURES,
        "quantidade_features": len(FEATURES),
        "features_removidas_da_matriz_X": ["supplier_id", "risk_level", "split"],
        "campos_proibidos_como_features": [
            "supplier_id", "Supplier_ID", "risk_level", "Risk_Level", "Risk_Category", "split",
        ],
        "metodo_imputacao": "SimpleImputer(strategy='median')",
        "imputador_ajustado_somente_no_treino": True,
        "operacoes": {"train": "fit_transform", "validation": "transform", "test": "transform"},
        "medianas_aprendidas_no_train": {
            feature: float(valor)
            for feature, valor in zip(FEATURES, imputador.statistics_, strict=True)
        },
        "politica_coluna_totalmente_nula_no_train": "interromper; não descartar nem imputar com holdout",
        "quantidade_registros_por_split": {
            nome: len(parte["X"]) for nome, parte in particoes.items()
        },
        "reconciliacao_ids": reconciliacao,
        "split_reutilizado_sem_recalculo": True,
        "target_utilizado_para_decidir_split_ou_imputacao": False,
        "ordenacao_linhas_X_y": "supplier_id textual em ordem crescente dentro de cada split",
        "rastreabilidade": (
            "Filtrar supplier_split_assignments.parquet pelo split e ordenar supplier_id. "
            "A posição nessa lista corresponde à linha de X e y, ambos com RangeIndex. "
            "Verificar o hash de entrada e o fingerprint da ordenação antes da associação."
        ),
        "hash_ordenacao_ids_sha256": {
            nome: hash_ordenacao(parte["supplier_ids"]) for nome, parte in particoes.items()
        },
        "formato_hash_ordenacao": "SHA-256 de JSON da lista de IDs, ensure_ascii=False, separators=(',', ':'), UTF-8",
        "schema_X": dict.fromkeys(FEATURES, "float64"),
        "schema_y": {"risk_level": "int8"},
        "nulos_antes_por_split": {
            nome: parte["X"].isna().sum().to_dict() for nome, parte in particoes.items()
        },
        "nulos_apos_por_split": {
            nome: parte["X"].isna().sum().to_dict() for nome, parte in saidas.items()
        },
        "infinitos_apos_por_split": dict.fromkeys(SPLITS, 0),
        "valores_presentes_preservados": True,
        "scaling": False,
        "encoding": False,
        "selecao_estatistica_de_features": False,
        "reducao_dimensionalidade": False,
        "modelo_preditivo_treinado": False,
        "versoes_bibliotecas": {
            "python": platform.python_version(),
            **{pacote: version(pacote) for pacote in ("pandas", "numpy", "pyarrow", "scikit-learn")},
        },
        "hashes_entradas_sha256": hashes,
        "hash_script_sha256": calcular_hash(Path(__file__).resolve()),
        "hashes_saidas_sha256": {},
    }
    # Publicar apenas depois de validar todas as entradas e transformações.
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for nome in SPLITS:
        for tipo in ("X", "y"):
            caminho = OUTPUT_DIR / f"{tipo}_{nome}.parquet"
            esperado = saidas[nome][tipo]
            esperado.to_parquet(caminho, index=False)
            recuperado = pd.read_parquet(caminho)
            pd.testing.assert_frame_equal(recuperado, esperado, check_exact=True)
            metadata["hashes_saidas_sha256"][caminho.relative_to(PROJECT_ROOT).as_posix()] = (
                calcular_hash(caminho)
            )
    conferir_integridade(hashes)
    # Metadata por último; consumidores devem conferir hashes de entradas/saídas.
    METADATA_PATH.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print("=" * 60)
    print("SUPPLIER RISK — DATASETS ML-READY")
    for nome, parte in saidas.items():
        nulos_antes = int(particoes[nome]["X"].isna().sum().sum())
        print(f"{nome}: X={parte['X'].shape}, y={parte['y'].shape}; nulos {nulos_antes} -> 0")
    print(f"Features finais: {len(FEATURES)}")
    print("SimpleImputer(median): fit_transform somente em TRAIN; transform em validation/test.")
    print("IDs reconciliados; overlap=0; nulos finais=0; infinitos finais=0.")
    print("Entradas preservadas. Sem scaling, encoding ou treinamento de modelo preditivo.")
    print(f"Saídas: {OUTPUT_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, AssertionError) as erro:
        print(f"ERRO: {erro}", file=sys.stderr)
        sys.exit(1)
