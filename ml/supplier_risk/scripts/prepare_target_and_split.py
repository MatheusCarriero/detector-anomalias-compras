"""Audita targets e particiona fornecedores sem transformar a base de features."""

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SOURCE_PATH = (
    PROJECT_ROOT / "data" / "external" / "supplier_risk"
    / "supplier_risk_dataset.csv"
)
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed" / "supplier_risk"
BASE_PATH = OUTPUT_DIR / "supplier_features_base.parquet"
TARGETS_PATH = OUTPUT_DIR / "supplier_targets.parquet"
SPLIT_PATH = OUTPUT_DIR / "supplier_split_assignments.parquet"
AUDIT_PATH = OUTPUT_DIR / "supplier_target_audit.json"
METADATA_PATH = OUTPUT_DIR / "supplier_split_metadata.json"
PROTOCOL_VERSION = "1.0.0"
SPLITS = ("train", "validation", "test")
HASH_SPACE = 1 << 256
TRAIN_LIMIT = HASH_SPACE * 70 // 100
VALIDATION_LIMIT = HASH_SPACE * 85 // 100


def calcular_hash(caminho):
    """SHA-256 dos bytes do arquivo, sem modificar a entrada."""
    with caminho.open("rb") as arquivo:
        return hashlib.file_digest(arquivo, "sha256").hexdigest().upper()


def salvar_json(caminho, dados):
    """Não permite NaN/Infinity, incompatíveis com JSON estrito."""
    caminho.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def validar_ids(dados, coluna, contexto, exigir_unicos=True):
    """Preserva a grafia dos IDs; não corrige nem descarta chaves inválidas."""
    if dados.empty:
        raise ValueError(f"{contexto}: dataset vazio.")
    if coluna not in dados:
        raise ValueError(f"{contexto}: coluna {coluna} ausente.")
    ids = dados[coluna]
    if ids.isna().any():
        raise ValueError(f"{contexto}: {coluna} nulo.")
    if not ids.map(lambda valor: isinstance(valor, str)).all():
        raise ValueError(f"{contexto}: {coluna} deve conter identificadores textuais.")
    if ids.str.strip().eq("").any():
        raise ValueError(f"{contexto}: {coluna} vazio ou composto apenas por espaços.")
    if exigir_unicos and ids.duplicated().any():
        raise ValueError(f"{contexto}: {coluna} duplicado ou atribuído mais de uma vez.")
    return set(ids)


def reconciliar_ids(esperados, obtidos, contexto):
    """Compara conjuntos completos, não apenas suas quantidades."""
    perdidos = set(esperados) - set(obtidos)
    inesperados = set(obtidos) - set(esperados)
    if perdidos or inesperados:
        raise ValueError(
            f"{contexto}: {len(perdidos)} fornecedor(es) perdido(s) "
            f"e {len(inesperados)} inesperado(s). "
            f"Exemplos perdidos: {sorted(perdidos)[:5]}; "
            f"inesperados: {sorted(inesperados)[:5]}."
        )
    return {
        "ids_esperados": len(esperados),
        "ids_obtidos": len(obtidos),
        "ids_perdidos": 0,
        "ids_inesperados": 0,
        "conjuntos_identicos": True,
    }


def auditar_target(dados):
    """Deduplica todas as colunas antes de auditar; nunca resolve conflitos."""
    distintos = dados.drop_duplicates().copy()
    auditoria = {
        "linhas_iniciais": len(dados),
        "duplicatas_exatas_removidas": len(dados) - len(distintos),
        "linhas_apos_deduplicacao": len(distintos),
        "deduplicacao": "somente linhas exatas, considerando todas as colunas da fonte",
        "dtypes_fonte": dados.dtypes.astype(str).to_dict(),
        "erros": [],
    }
    erros = auditoria["erros"]
    if dados.empty:
        erros.append("Dataset de origem vazio.")
    faltantes = sorted({"Supplier_ID", "Risk_Level"} - set(dados.columns))
    if faltantes:
        erros.append("Colunas obrigatórias ausentes: " + ", ".join(faltantes))
        auditoria["status"] = "bloqueado"
        return distintos, auditoria

    ids = distintos["Supplier_ID"]
    original = distintos["Risk_Level"]
    numerico = pd.to_numeric(original, errors="coerce")
    problemas_tipo = original.notna() & numerico.isna()
    # Booleanos/complexos não são classes binárias declaradas pela fonte.
    problemas_tipo |= original.map(lambda valor: isinstance(valor, (bool, complex)))
    fora_dominio = numerico.notna() & ~numerico.isin([0, 1])
    ids_nulos = int(ids.isna().sum())
    ids_vazios = int(ids.astype("string").str.strip().eq("").sum())
    ids_tipo_invalido = int(
        (ids.notna() & ~ids.map(lambda valor: isinstance(valor, str))).sum()
    )
    nulos = int(original.isna().sum())
    # Valores originais: a auditoria não esconde categorias inválidas por coerção.
    quantidades = distintos.groupby("Supplier_ID")["Risk_Level"].nunique()
    conflitos = sorted(quantidades[quantidades.gt(1)].index.astype(str).tolist())
    ids_zero = set(ids[numerico.eq(0)].dropna())
    ids_um = set(ids[numerico.eq(1)].dropna())
    total = int(ids.nunique())
    auditoria.update({
        "quantidade_fornecedores": total,
        "fornecedores_com_um_valor_distinto": int(quantidades.eq(1).sum()),
        "fornecedores_sem_valor_preenchido": int(quantidades.eq(0).sum()),
        "fornecedores_com_mais_de_um_valor_distinto": len(conflitos),
        "fornecedores_com_0_e_1": len(ids_zero & ids_um),
        "quantidade_conflitos": len(conflitos),
        "percentual_conflitos": 100 * len(conflitos) / total if total else 0.0,
        "supplier_ids_conflitantes": conflitos,
        "exemplos_conflitos": conflitos[:20],
        "supplier_id_nulos": ids_nulos,
        "supplier_id_vazios": ids_vazios,
        "supplier_id_tipos_invalidos": ids_tipo_invalido,
        "risk_level_nulos": nulos,
        "risk_level_problemas_tipo": int(problemas_tipo.sum()),
        "risk_level_fora_de_0_1": int(fora_dominio.sum()),
        "exemplos_targets_invalidos": original[
            problemas_tipo | fora_dominio
        ].astype(str).drop_duplicates().head(20).tolist(),
        "contagens_distintas_desconsideram_nulos": True,
        "nulos_sao_validados_separadamente_e_bloqueiam": True,
        "resolucao_automatica_de_conflitos": False,
    })
    for quantidade, mensagem in (
        (ids_nulos, "Supplier_ID nulo"),
        (ids_vazios, "Supplier_ID vazio"),
        (ids_tipo_invalido, "Supplier_ID com tipo não textual"),
        (nulos, "Risk_Level nulo"),
        (int(problemas_tipo.sum()), "Risk_Level com problema de tipo"),
        (int(fora_dominio.sum()), "Risk_Level diferente de 0 ou 1"),
        (len(conflitos), "fornecedor com Risk_Level conflitante; decisão metodológica necessária"),
    ):
        if quantidade:
            erros.append(f"{quantidade} ocorrência(s): {mensagem}.")
    auditoria["status"] = "bloqueado" if erros else "aprovado"
    return distintos, auditoria


def consolidar_targets(dados, ids_base):
    """Somente reduz pares id/target comprovadamente únicos, sem agregação."""
    distintos, auditoria = auditar_target(dados)
    if auditoria["erros"]:
        raise ValueError("Auditoria do target bloqueada: " + " ".join(auditoria["erros"]))
    targets = pd.DataFrame({
        "supplier_id": distintos["Supplier_ID"].astype("string"),
        "risk_level": pd.to_numeric(distintos["Risk_Level"]).astype("int8"),
    })
    targets = targets.drop_duplicates().sort_values("supplier_id").reset_index(drop=True)
    validar_targets(targets, ids_base)
    return targets


def validar_targets(targets, ids_base):
    if targets.columns.tolist() != ["supplier_id", "risk_level"]:
        raise ValueError("Targets: schema deve conter somente supplier_id e risk_level.")
    ids = validar_ids(targets, "supplier_id", "Targets")
    if targets["risk_level"].isna().any():
        raise ValueError("Targets: Risk_Level nulo.")
    if not targets["risk_level"].isin([0, 1]).all():
        raise ValueError("Targets: Risk_Level diferente de 0 ou 1.")
    return reconciliar_ids(ids_base, ids, "Targets/base")


def particao_por_id(supplier_id):
    """Hash do ID exato em UTF-8; limiares inteiros, sem aleatoriedade ou target."""
    valor = int.from_bytes(hashlib.sha256(supplier_id.encode("utf-8")).digest(), "big")
    if valor < TRAIN_LIMIT:
        return "train"
    if valor < VALIDATION_LIMIT:
        return "validation"
    return "test"


def criar_split(ids_base):
    """Recebe exclusivamente IDs. Nem features nem targets decidem a partição."""
    split = pd.DataFrame({"supplier_id": sorted(ids_base)}, dtype="string")
    validar_ids(split, "supplier_id", "Entrada do split")
    split = pd.DataFrame({
        "supplier_id": split["supplier_id"],
        "split": split["supplier_id"].map(particao_por_id).astype("string"),
    })
    validar_split(split, set(ids_base))
    return split


def validar_split(atribuicoes, ids_base):
    if atribuicoes.columns.tolist() != ["supplier_id", "split"]:
        raise ValueError("Split: schema deve conter somente supplier_id e split.")
    ids = validar_ids(atribuicoes, "supplier_id", "Split")
    if atribuicoes["split"].isna().any():
        raise ValueError("Fornecedor sem split atribuído.")
    if not atribuicoes["split"].isin(SPLITS).all():
        raise ValueError("Split inválido: utilizar somente train, validation ou test.")
    reconciliacao = reconciliar_ids(ids_base, ids, "Split/base")
    conjuntos = {
        nome: set(atribuicoes.loc[atribuicoes["split"].eq(nome), "supplier_id"])
        for nome in SPLITS
    }
    overlap = {
        "train_validation": len(conjuntos["train"] & conjuntos["validation"]),
        "train_test": len(conjuntos["train"] & conjuntos["test"]),
        "validation_test": len(conjuntos["validation"] & conjuntos["test"]),
    }
    if any(overlap.values()):
        raise ValueError("Fornecedor atribuído a mais de uma partição.")
    return {
        "reconciliacao_ids": reconciliacao,
        "overlap": overlap,
        "ausencia_de_overlap": True,
        "quantidade_fornecedores_por_split": {
            nome: len(conjunto) for nome, conjunto in conjuntos.items()
        },
        "proporcoes_obtidas": {
            nome: len(conjunto) / len(ids) for nome, conjunto in conjuntos.items()
        },
    }


def observar_distribuicao(atribuicoes, targets):
    """Consulta posterior; não modifica nem devolve novas atribuições de split."""
    ids = validar_ids(atribuicoes, "supplier_id", "Split para observação")
    validar_split(atribuicoes, ids)
    validar_targets(targets, ids)
    observacao = atribuicoes.merge(targets, on="supplier_id", validate="one_to_one")
    distribuicao = {}
    for nome in SPLITS:
        classes = observacao.loc[observacao["split"].eq(nome), "risk_level"]
        distribuicao[nome] = {
            "total": len(classes),
            "quantidade_0": int(classes.eq(0).sum()),
            "quantidade_1": int(classes.eq(1).sum()),
            "percentual_0": 100 * int(classes.eq(0).sum()) / len(classes) if len(classes) else None,
            "percentual_1": 100 * int(classes.eq(1).sum()) / len(classes) if len(classes) else None,
        }
    return distribuicao


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    auditoria = {
        "protocol_version": PROTOCOL_VERSION,
        "data_geracao": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "em_validacao",
    }
    try:
        hashes = {
            caminho.relative_to(PROJECT_ROOT).as_posix(): calcular_hash(caminho)
            for caminho in (SOURCE_PATH, BASE_PATH)
        }
        auditoria["hashes_entradas_sha256"] = hashes
        base = pd.read_parquet(BASE_PATH)
        ids_base = validar_ids(base, "supplier_id", "Base de features")
        dados = pd.read_csv(SOURCE_PATH, dtype={"Supplier_ID": "string"})
        _, resultado = auditar_target(dados)
        auditoria.update(resultado)
        if resultado["erros"]:
            raise ValueError("Auditoria do target bloqueada: " + " ".join(resultado["erros"]))

        targets = consolidar_targets(dados, ids_base)
        reconciliacao = validar_targets(targets, ids_base)
        # Atribuições congeladas antes de qualquer associação às classes.
        atribuicoes = criar_split(ids_base)
        validacao_split = validar_split(atribuicoes, ids_base)
        distribuicao = observar_distribuicao(atribuicoes, targets)
        for caminho in (SOURCE_PATH, BASE_PATH):
            relativo = caminho.relative_to(PROJECT_ROOT).as_posix()
            if calcular_hash(caminho) != hashes[relativo]:
                raise ValueError(f"Entrada alterada durante o processamento: {relativo}.")

        metadata = {
            "protocol_version": PROTOCOL_VERSION,
            "pipeline_version": PROTOCOL_VERSION,
            "data_geracao": auditoria["data_geracao"],
            "nome_modelo": "Supplier Risk Model",
            "status": "validado; sem imputação ou treinamento",
            "metodo_split": "hash determinístico exclusivamente de supplier_id",
            "algoritmo_hash": "SHA-256",
            "representacao_id": "texto exato, UTF-8, sem strip/casefold/salt/normalização",
            "conversao_hash": "digest completo de 256 bits como inteiro sem sinal, big-endian",
            "regra_particao": (
                "h < floor(2**256 * 70/100): train; "
                "senão h < floor(2**256 * 85/100): validation; senão test"
            ),
            "limiares_inteiros_decimais": {
                "train_exclusivo": str(TRAIN_LIMIT),
                "validation_exclusivo": str(VALIDATION_LIMIT),
            },
            "proporcoes_planejadas": {"train": 0.70, "validation": 0.15, "test": 0.15},
            "quantidade_total_fornecedores": len(ids_base),
            **validacao_split,
            "reconciliacao_targets_base": reconciliacao,
            "risk_level_utilizado_para_construir_split": False,
            "estratificacao": False,
            "rebalanceamento_apos_observacao": False,
            "distribuicao_risk_level_apos_split": distribuicao,
            "hashes_entradas_sha256": hashes,
            "auditoria_target": AUDIT_PATH.relative_to(PROJECT_ROOT).as_posix(),
            "quantidade_conflitos_target": resultado["quantidade_conflitos"],
            "consolidacao_target": "pares id/target distintos somente após comprovar unicidade",
            "schema_targets": {"supplier_id": "string", "risk_level": "int8"},
            "schema_split": {"supplier_id": "string", "split": "string"},
            "risk_level_e_supplier_id_sao_features": False,
            "nulos_features_preservados": base.drop(columns="supplier_id").isna().sum().to_dict(),
            "imputacao": False,
            "medianas_de_imputacao_calculadas": False,
            "scaling": False,
            "encoding": False,
            "treinamento": False,
            "supplier_record_count": {
                "status": "feature candidata; experimento futuro com e sem a feature",
                "definicao": (
                    "Quantidade de registros distintos da fonte associados ao fornecedor "
                    "após a remoção de duplicatas exatas."
                ),
                "historico_temporal_comprovado": False,
            },
        }
        # Nenhum artefato definitivo é escrito antes de todas as validações.
        targets.to_parquet(TARGETS_PATH, index=False)
        atribuicoes.to_parquet(SPLIT_PATH, index=False)
        metadata["hashes_saidas_sha256"] = {
            caminho.relative_to(PROJECT_ROOT).as_posix(): calcular_hash(caminho)
            for caminho in (TARGETS_PATH, SPLIT_PATH)
        }
        auditoria["reconciliacao_targets_base"] = reconciliacao
        auditoria["status"] = "aprovado"
        salvar_json(AUDIT_PATH, auditoria)
        metadata["hash_auditoria_sha256"] = calcular_hash(AUDIT_PATH)
        # Metadata publicado por último: confirmação da execução bem-sucedida.
        salvar_json(METADATA_PATH, metadata)
    except (ValueError, OSError, pd.errors.ParserError) as erro:
        auditoria["status"] = "bloqueado"
        auditoria["motivo_bloqueio"] = str(erro)
        auditoria["artefatos_anteriores_nao_revalidados"] = True
        salvar_json(AUDIT_PATH, auditoria)
        raise

    print("=" * 60)
    print("SUPPLIER RISK — AUDITORIA DO TARGET E SPLIT")
    print(f"Fornecedores: {len(ids_base):,}")
    print(f"Duplicatas exatas removidas: {resultado['duplicatas_exatas_removidas']:,}")
    print(f"Conflitos de Risk_Level: {resultado['quantidade_conflitos']}")
    print("Reconciliação de IDs: exata. Overlap: 0 em todos os pares.")
    for nome, classes in distribuicao.items():
        percentual = validacao_split["proporcoes_obtidas"][nome] * 100
        print(f"{nome}: {classes['total']:,} fornecedores ({percentual:.4f}%)")
        print(f"  Risk_Level 0: {classes['quantidade_0']}; 1: {classes['quantidade_1']}")
    print("Base de features intacta; nulos preservados. Sem imputação ou treinamento.")
    for caminho in (TARGETS_PATH, SPLIT_PATH, AUDIT_PATH, METADATA_PATH):
        print(f"Criado: {caminho.relative_to(PROJECT_ROOT).as_posix()}")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, pd.errors.ParserError) as erro:
        print(f"ERRO: {erro}", file=sys.stderr)
        sys.exit(1)
