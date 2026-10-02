"""Prepare masked human-review packets; no labels, fits, responses or holdout analysis."""

import argparse
import hashlib
import hmac
import json
import math
import platform
import secrets
import zipfile
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pandas as pd

from ml.scripts import diagnosticar_triagem_invoice as triage

OUTPUT = "ml/experiments/invoice_blind_review_v1"
COMPARISON = "ml/experiments/invoice_value_comparison_v1.json"
PROTOCOL = triage.PROJECT_ROOT / "docs/invoice_blind_review_protocol.md"
GUIDE = triage.PROJECT_ROOT / "docs/invoice_blind_review_reviewer_guide.md"
RAW_COLUMNS = ["invoice_id", "supplier_id", "department_id", "invoice_date", "invoice_amount",
               "currency", "payment_terms", "invoice_type", "submission_hour"]
DESCRIPTORS = ["amount_vs_supplier_mean", "amount_vs_department_mean", "supplier_frequency",
               "supplier_department_frequency"]
REVIEWERS = ("avaliador_01", "avaliador_02")
GROUPS = ("common", "if_only", "value_only", "neither")


def _seed(seed):
    if not isinstance(seed, str) or len(seed) != 64:
        raise ValueError("Seed deve ter 32 bytes em hexadecimal.")
    try:
        key = bytes.fromhex(seed)
    except ValueError as error:
        raise ValueError("Seed hexadecimal inválida.") from error
    if len(key) != 32:
        raise ValueError("Seed deve ter 32 bytes.")
    return key


def _key(seed, *parts):
    payload = json.dumps(parts, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hmac.new(_seed(seed), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _rank(frame, values):
    triage.validate_ids(frame, "VALIDATION")
    vector = triage._vector(values, len(frame))
    return frame[["invoice_id"]].assign(value=vector).sort_values(
        ["value", "invoice_id"], ascending=[False, True],
    )["invoice_id"].tolist()


def draw_sample(frame, scores, seed):
    """Equal quotas, independent of input order and any label columns."""
    _seed(seed)
    forest, value = _rank(frame, scores), _rank(frame, frame["invoice_amount"])
    all_ids = set(forest)
    members, populations = [], []
    for budget in triage.BUDGETS:
        k = math.ceil(len(frame) * budget / 100)
        fi, va = set(forest[:k]), set(value[:k])
        pools = (fi & va, fi - va, va - fi, all_ids - (fi | va))
        for name, pool in zip(GROUPS, pools, strict=True):
            if len(pool) < 25:
                raise ValueError(f"Estrato {budget}/{name} com menos de 25; quota não será alterada.")
            selected = sorted(pool, key=lambda i: (_key(seed, "sample", budget, name, i), i))[:25]
            populations.append({"budget": budget, "group": name, "population": len(pool),
                                "sample_size": 25, "sample_ids_sha256": triage._fingerprint(selected)})
            members.extend({"budget": budget, "group": name, "invoice_id": i} for i in selected)
    return members, populations


def _text(value):
    if pd.isna(value):
        return "Não informado"
    if isinstance(value, (float, np.floating)):
        return str(float(value))
    # Markdown table safety; source data must never create headings or links.
    return str(value).replace("\n", " ").replace("\r", " ").replace("|", "\\|").replace("<", "&lt;").replace(
        ">", "&gt;").replace("[", "\\[").replace("]", "\\]")


def make_packets(context, members, seed, guide):
    triage.validate_ids(context, "contexto das fichas")
    _seed(seed)
    ids = sorted({m["invoice_id"] for m in members})
    if not set(ids) <= set(context["invoice_id"]):
        raise ValueError("Contexto não cobre os IDs sorteados.")
    context = context.set_index("invoice_id")
    packets, mappings = {}, {}
    for reviewer in REVIEWERS:
        ordered = sorted(ids, key=lambda i: (_key(seed, "order", reviewer, i), i))
        entries = [{"case_id": "C-" + _key(seed, "case", reviewer, i)[:16], "invoice_id": i}
                   for i in ordered]
        if len({e["case_id"] for e in entries}) != len(ids):
            raise ValueError("Colisão de pseudônimos de casos.")
        cards = ["# Fichas de revisão\n\nPreencha somente os campos de resposta.\n"]
        for entry in entries:
            row = context.loc[entry["invoice_id"]]
            date = pd.to_datetime(row["invoice_date"], errors="raise")
            fields = [
                ("Data da fatura", date.strftime("%Y-%m-%d") if pd.notna(date) else None),
                ("Valor", row["invoice_amount"]), ("Moeda", row["currency"]),
                ("Tipo", row["invoice_type"]), ("Condições de pagamento", row["payment_terms"]),
                ("Hora informada", row["submission_hour"]),
            ]
            for column, label, prefix in (("supplier_id", "Fornecedor", "F-"),
                                          ("department_id", "Departamento", "D-")):
                alias = None if pd.isna(row[column]) else prefix + _key(seed, column, reviewer, str(row[column]))[:16]
                fields.append((label, alias))
            for column, label in zip(DESCRIPTORS, (
                "Razão valor / média do fornecedor na referência",
                "Razão valor / média do departamento na referência",
                "Frequência do fornecedor na referência",
                "Frequência fornecedor/departamento na referência",
            ), strict=True):
                fields.append((label, row[column]))
            cards.append(f"\n## Caso {entry['case_id']}\n\n| Campo | Informação |\n|---|---|\n")
            cards.extend(f"| {label} | {_text(v)} |\n" for label, v in fields)
            cards.append("\n### Respostas\n\n- Relevância: \n- Motivo concreto: \n"
                         "- Evidência adicional necessária: \n- Facilidade de justificar: \n"
                         "- Esforço estimado: \n- Hipótese para estimar esforço: \n- Observações: \n")
        declaration = (
            "# Declaração individual\n\n- Nome/identificação: \n- Experiência pertinente: \n"
            "- Data de início: \n- Exposição prévia a informações deste estudo (descrever ou não): \n"
            "- Exposição comunicada à coordenação antes do início: \n"
            "- Confirma trabalho independente, sem consultar outros participantes ou fontes do estudo: \n"
            "- Todos os casos respondidos (sim/não): \n- Data de conclusão: \n"
            "- Confirmo que esta é minha versão final (nome e data): \n\n"
            "Preencha a conclusão somente após revisar todas as fichas.\n"
        )
        packets[reviewer] = {"LEIA_PRIMEIRO.md": guide, "FICHAS.md": "".join(cards),
                             "DECLARACAO.md": declaration}
        mappings[reviewer] = entries
    return packets, mappings


def _load_validation(root):
    root = triage.require_external_invoice_fixture(root)
    # Intentional projection: never use the older loader that also reads labels.
    frame = pd.read_parquet(root / triage.PRESERVED_INPUTS[1], columns=["invoice_id", "split", *triage.FEATURES])
    triage.validate_ids(frame, "VALIDATION")
    triage.validate_training_features(frame[triage.FEATURES])
    if not frame["split"].eq("val").all():
        raise ValueError("VALIDATION contém split indevido.")
    train = pd.read_parquet(root / triage.PRESERVED_INPUTS[0], columns=["invoice_id", "split"])
    triage.validate_ids(train, "TRAIN IDs")
    if not train["split"].eq("train").all() or set(train["invoice_id"]) & set(frame["invoice_id"]):
        raise ValueError("Separação TRAIN/VALIDATION inválida.")
    official = pd.read_parquet(root / "data/raw/splits.parquet", columns=["invoice_id", "split"],
                               filters=[("split", "in", ["train", "val"])])
    triage.validate_ids(official, "splits autorizados")
    for name, part in (("train", train), ("val", frame)):
        if set(part["invoice_id"]) != set(official.loc[official["split"].eq(name), "invoice_id"]):
            raise ValueError("IDs divergentes do split oficial.")
    return frame.sort_values("invoice_id").reset_index(drop=True)


def _context(root, frame, members):
    root = triage.require_external_invoice_fixture(root)
    ids = sorted({m["invoice_id"] for m in members})
    source = pd.read_parquet(root / "data/raw/invoices.parquet", columns=RAW_COLUMNS,
                             filters=[("invoice_id", "in", ids)])
    triage.validate_ids(source, "faturas sorteadas")
    if set(source["invoice_id"]) != set(ids):
        raise ValueError("Fonte não cobre exatamente a amostra.")
    source = source.set_index("invoice_id").loc[ids].reset_index()
    chosen = frame.set_index("invoice_id").loc[ids].reset_index()
    if not np.array_equal(triage._vector(source["invoice_amount"]), chosen["invoice_amount"].to_numpy()):
        raise ValueError("Valor original diverge do processado por ID.")
    if source["currency"].isna().any() or source["currency"].nunique() != 1:
        raise ValueError("Moeda ausente ou heterogênea na amostra.")
    for column, allowed in (("invoice_type", {"GOODS", "SERVICES"}),
                            ("payment_terms", {"NET30", "NET60", "NET90"})):
        if not source[column].dropna().isin(allowed).all():
            raise ValueError(f"Domínio inesperado: {column}; não adaptar fichas automaticamente.")
    hours = source["submission_hour"].dropna()
    if not pd.api.types.is_numeric_dtype(hours.dtype) or not hours.between(0, 23).all() or not hours.mod(1).eq(0).all():
        raise ValueError("Hora de submissão inválida.")
    for column in DESCRIPTORS:
        source[column] = chosen[column].to_numpy()
    return source


def _write_json(path, value):
    text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)


def _raw_stats(root):
    return {name: {"bytes": (root / name).stat().st_size,
                   "mtime_ns": str((root / name).stat().st_mtime_ns)}
            for name in ("data/raw/splits.parquet", "data/raw/invoices.parquet")}


def run(root=triage.PROJECT_ROOT, output=None, seed=None, split="val"):
    if split != "val":
        raise ValueError("Somente val; TEST permanece fechado.")
    root = triage.require_external_invoice_fixture(root)
    output = Path(output) if output is not None else root / OUTPUT
    if output.exists():
        raise FileExistsError("Preparação já iniciada/existente; não sobrescrever nem sortear novamente.")
    seed = secrets.token_hex(32) if seed is None else seed
    _seed(seed)
    paths = (*triage.PRESERVED_INPUTS, COMPARISON)
    hashes = {name: triage.sha256(root / name) for name in paths}
    code_paths = [Path(__file__), Path(triage.__file__), PROTOCOL, GUIDE,
                  triage.PROJECT_ROOT / "ml/scripts/avaliar_invoice.py",
                  triage.PROJECT_ROOT / "ml/scripts/treinar_modelo.py"]
    code_hashes = {str(p.relative_to(triage.PROJECT_ROOT).as_posix()): triage.sha256(p) for p in code_paths}
    reference = json.loads((root / COMPARISON).read_text(encoding="utf-8"))
    if reference.get("split") != "val" or reference.get("test_used") is not False or reference.get("budget_percentages") != [1, 5, 10]:
        raise ValueError("Referência não corresponde à comparação autorizada.")
    for name in triage.PRESERVED_INPUTS:
        if hashes[name] != reference["input_hashes_sha256"][name].lower():
            raise ValueError(f"Input alterado desde a comparação: {name}")
    raw_before = _raw_stats(root)
    output.mkdir(parents=True, exist_ok=False)
    coordinator = output / "coordinator"
    coordinator.mkdir()
    marker = output / "PREPARATION_INCOMPLETE"
    with marker.open("x", encoding="utf-8") as stream:
        stream.write("Não distribuir. Preparação ainda não concluída.\n")
    freeze = {"protocol_version": "invoice-blind-review-1.0", "seed_hex": seed,
              "frozen_at": datetime.now(timezone.utc).isoformat(), "split": "val",
              "budgets": [1, 5, 10], "per_stratum": 25, "reviewers": 2,
              "input_hashes_sha256": hashes, "code_and_protocol_sha256": code_hashes,
              "shared_raw_stats": raw_before, "labels_read": False, "test_used": False,
              "versions": {"python": platform.python_version(), **{n: version(n) for n in (
                  "numpy", "pandas", "pyarrow", "scikit-learn", "joblib")}}}
    _write_json(coordinator / "freeze.json", freeze)
    frame = _load_validation(root)
    if triage._fingerprint(frame["invoice_id"].tolist()) != reference["validation_ids_sha256"].lower():
        raise ValueError("Coorte diverge da comparação.")
    model = triage._load_model(root, {"parameters": reference["parameters"], "offset": reference["legacy_offset"]})
    scores = -model.score_samples(frame[triage.FEATURES])
    for strategy, values in (("isolation_forest", scores), ("invoice_value", frame["invoice_amount"])):
        ordered = _rank(frame, values)
        for prior, budget in zip(reference[strategy]["budgets"], triage.BUDGETS, strict=True):
            k = math.ceil(len(frame) * budget / 100)
            if (prior["percent"] != budget or prior["k"] != k
                    or triage._fingerprint(ordered[:k]) != prior["selected_ids_sha256"].lower()):
                raise ValueError("Seleções divergentes da comparação anterior.")
    members, populations = draw_sample(frame, scores, seed)
    context = _context(root, frame, members)
    packets, mappings = make_packets(context, members, seed, GUIDE.read_text(encoding="utf-8"))
    for name, digest in hashes.items():
        if triage.sha256(root / name) != digest:
            raise ValueError("Input alterado durante preparação.")
    for path in code_paths:
        if triage.sha256(path) != code_hashes[path.relative_to(triage.PROJECT_ROOT).as_posix()]:
            raise ValueError("Código/protocolo alterado durante preparação.")
    if _raw_stats(root) != raw_before:
        raise ValueError("Fonte compartilhada alterada durante preparação.")
    artifacts = {}
    for reviewer, files in packets.items():
        packet_path = output / f"{reviewer}.zip"
        with zipfile.ZipFile(packet_path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            for filename, content in files.items():
                entry = zipfile.ZipInfo(filename, date_time=(1980, 1, 1, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                data = content.encode("utf-8")
                archive.writestr(entry, data)
                artifacts[f"{reviewer}/{filename}"] = hashlib.sha256(data).hexdigest()
        artifacts[packet_path.name] = triage.sha256(packet_path)
    manifest = {"state": "awaiting_two_independent_reviews", "responses_frozen": False,
                "labels_revealed": False, "test_used": False, "real_model_fits": 0,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "freeze_sha256": triage.sha256(coordinator / "freeze.json"),
                "memberships": len(members), "unique_invoices": len(context),
                "populations": populations, "sample_memberships": members,
                "reviewer_mappings": mappings, "packet_hashes_sha256": artifacts,
                "context_sha256": hashlib.sha256(context.to_json(orient="records", date_format="iso", double_precision=15).encode("utf-8")).hexdigest()}
    _write_json(coordinator / "manifest.json", manifest)
    # Remove only our own successful-preparation marker, never user data.
    marker.unlink()
    return {k: manifest[k] for k in ("state", "responses_frozen", "labels_revealed", "memberships", "unique_invoices")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=["val"], default="val")
    args = parser.parse_args()
    print(json.dumps(run(split=args.split), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
