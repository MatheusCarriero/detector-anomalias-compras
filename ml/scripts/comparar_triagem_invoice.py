"""Historical IF/value comparison; filesystem runs require synthetic fixtures."""

import argparse
import json
import platform
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pandas as pd

from ml.scripts import diagnosticar_triagem_invoice as triage

OUTPUT = "ml/experiments/invoice_value_comparison_v1.json"
PROTOCOL = triage.PROJECT_ROOT / "docs/invoice_value_comparison_protocol.md"


def _group(frame):
    """Describe a selection without exporting invoice-level labels or IDs."""
    hits = int(frame["is_fraud"].sum())
    types = {}
    for name, group in frame.groupby(frame["fraud_type"].fillna("__missing__")):
        types[name] = {"rows": len(group), "known_positives": int(group["is_fraud"].sum())}
    concentration = {}
    for name, key, total in (("all", "rows", len(frame)), ("positive", "known_positives", hits)):
        if not total:
            concentration[name] = None
            continue
        largest = max(item[key] for item in types.values())
        concentration[name] = {
            "types": sorted(label for label, item in types.items() if item[key] == largest),
            "count": largest, "share": largest / total,
        }
    return {
        "rows": len(frame), "known_positives": hits, "reference_negatives": len(frame) - hits,
        "by_fraud_type": types, "concentration": concentration,
        "positive_type_count": sum(item["known_positives"] > 0 for item in types.values()),
        "ids_sha256": triage._fingerprint(sorted(frame["invoice_id"].tolist())),
    }


def compare_rankings(frame, scores):
    """Equal K, label-free ordering, and paired gross/net accounting."""
    forest = triage.rank_summary(frame, scores)
    value = triage.rank_summary(frame, frame["invoice_amount"])
    if_ranked = triage._rank(frame, scores)
    value_ranked = triage._rank(frame, frame["invoice_amount"])
    comparisons = []
    for if_budget, value_budget in zip(forest["budgets"], value["budgets"], strict=True):
        k = if_budget["k"]
        if_selected, value_selected = if_ranked.iloc[:k], value_ranked.iloc[:k]
        if_ids, value_ids = set(if_selected["invoice_id"]), set(value_selected["invoice_id"])
        common = _group(frame[frame["invoice_id"].isin(if_ids & value_ids)])
        if_only = _group(frame[frame["invoice_id"].isin(if_ids - value_ids)])
        value_only = _group(frame[frame["invoice_id"].isin(value_ids - if_ids)])
        union = _group(frame[frame["invoice_id"].isin(if_ids | value_ids)])
        net = if_only["known_positives"] - value_only["known_positives"]
        comparisons.append({
            "percent": if_budget["percent"], "k": k,
            "if_selected": _group(if_selected), "value_selected": _group(value_selected),
            "common": common, "if_only": if_only, "value_only": value_only, "union": union,
            "overlap_fraction": common["rows"] / k,
            "jaccard": common["rows"] / union["rows"],
            "gross_additional_if_positives": if_only["known_positives"],
            "value_positives_forgone": value_only["known_positives"],
            "net_additional_positives": net,
            "precision_delta": net / k,
            "capture_delta": net / forest["known_positives"] if forest["known_positives"] else None,
        })
    return {"isolation_forest": forest, "invoice_value": value, "comparisons": comparisons}


def _source_amounts(root, frame):
    root = triage.require_external_invoice_fixture(root)
    source = pd.read_parquet(
        root / "data/raw/invoices.parquet", columns=["invoice_id", "invoice_amount", "currency"],
        filters=[("invoice_id", "in", frame["invoice_id"].tolist())],
    )
    triage.validate_ids(source, "valores da fonte VALIDATION")
    if set(source["invoice_id"]) != set(frame["invoice_id"]):
        raise ValueError("Valores da fonte não cobrem exatamente VALIDATION.")
    source = source.set_index("invoice_id").loc[frame["invoice_id"]].reset_index()
    amounts = triage._vector(source["invoice_amount"], len(frame))
    if not np.array_equal(amounts, frame["invoice_amount"].to_numpy(dtype=float)):
        raise ValueError("invoice_amount diverge da fonte por invoice_id.")
    currencies = source["currency"]
    if (not currencies.map(lambda v: isinstance(v, str) and bool(v.strip()) and v == v.strip()).all()
            or currencies.nunique() != 1):
        raise ValueError("Comparação por valor exige uma única moeda não nula, sem conversão.")
    fingerprint = triage._fingerprint([
        [row.invoice_id, float(row.invoice_amount), row.currency] for row in source.itertuples()
    ])
    return str(currencies.iloc[0]), fingerprint


def _raw_stats(root):
    # Stat only: do not hash/read unfiltered shared sources containing other splits.
    return {name: {"bytes": (root / name).stat().st_size,
                   "mtime_ns": str((root / name).stat().st_mtime_ns)} for name in triage.RAW_INPUTS}


def _references(root, hashes):
    previous = json.loads((root / triage.PREVIOUS).read_text(encoding="utf-8"))
    prior_triage = json.loads((root / triage.OUTPUT).read_text(encoding="utf-8"))
    for reference in (previous, prior_triage):
        if reference.get("split") != "val" or reference.get("test_used") is not False:
            raise ValueError("Evidência anterior não corresponde à VALIDATION.")
        for name in triage.PRESERVED_INPUTS:
            if hashes[name] != reference["input_hashes_sha256"][name].lower():
                raise ValueError(f"Input diverge da evidência anterior: {name}")
    if (prior_triage.get("budget_percentages") != list(triage.BUDGETS)
            or hashes[triage.PREVIOUS] != prior_triage["input_hashes_sha256"][triage.PREVIOUS].lower()):
        raise ValueError("Protocolo/referência anterior diverge da triagem.")
    return previous, prior_triage


def run(root=triage.PROJECT_ROOT, output=None, split="val"):
    if split != "val":
        raise ValueError("Somente val autorizado; TEST permanece fechado.")
    root = triage.require_external_invoice_fixture(root)
    output = Path(output) if output is not None else root / OUTPUT
    if output.exists():
        raise FileExistsError(f"Saída já existe; não sobrescrever: {output}")
    if output.suffix != ".json":
        raise ValueError("Saída deve ser JSON.")
    names = (*triage.PRESERVED_INPUTS, triage.PREVIOUS, triage.OUTPUT)
    hashes = {name: triage.sha256(root / name) for name in names}
    code_paths = [Path(__file__), Path(triage.__file__), PROTOCOL,
                  triage.PROJECT_ROOT / "ml/scripts/avaliar_invoice.py",
                  triage.PROJECT_ROOT / "ml/scripts/treinar_modelo.py"]
    code_hashes = {p.relative_to(triage.PROJECT_ROOT).as_posix(): triage.sha256(p) for p in code_paths}
    raw_before = _raw_stats(root)
    previous, prior_triage = _references(root, hashes)
    frame = triage.load_validation(root, split)
    ids_hash = triage._fingerprint(frame["invoice_id"].tolist())
    if (previous["rows"] != len(frame)
            or ids_hash != prior_triage["validation_ids_sha256"].lower()):
        raise ValueError("IDs/coorte divergentes da triagem anterior.")
    currency, amount_hash = _source_amounts(root, frame)
    model = triage._load_model(root, previous)
    result = compare_rankings(frame, -model.score_samples(frame[triage.FEATURES]))
    if result["isolation_forest"] != prior_triage["validation"]:
        raise ValueError("Resumo/seleções IF divergentes da triagem anterior; não publicar.")
    for name, expected in hashes.items():
        if triage.sha256(root / name) != expected:
            raise ValueError(f"Input alterado durante comparação: {name}")
    for path in code_paths:
        if triage.sha256(path) != code_hashes[path.relative_to(triage.PROJECT_ROOT).as_posix()]:
            raise ValueError("Código/protocolo alterado durante comparação.")
    if _raw_stats(root) != raw_before:
        raise ValueError("Fonte compartilhada alterada durante comparação.")
    result.update({
        "protocol_version": "invoice-value-comparison-1.0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "split": "val", "real_model_fits": 0, "test_used": False,
        "threshold_selected": False, "budget_selected": False,
        "budget_percentages": list(triage.BUDGETS),
        "score_definitions": {"isolation_forest": "-score_samples; not a probability",
                              "invoice_value": "invoice_amount; descending; not absolute value"},
        "tie_break": "ranking value descending, invoice_id ascending; no labels",
        "currency": currency, "features": triage.FEATURES,
        "parameters": model.get_params(), "legacy_offset": float(model.offset_),
        "input_hashes_sha256": hashes, "code_and_protocol_sha256": code_hashes,
        "shared_raw_stat_before_after": raw_before,
        "authorized_source_amounts_sha256": amount_hash,
        "validation_ids_sha256": ids_hash, "previous_triage_reconciled": True,
        "versions": {"python": platform.python_version(), **{
            name: version(name) for name in ("numpy", "pandas", "scikit-learn", "joblib", "pyarrow")
        }},
        "limits": [
            "is_fraud is an unverified secondary reference, not business ground truth",
            "fraud_type inconsistency preserved; concentration is descriptive, not validated mechanisms",
            "incremental positive labels do not establish causal or financial business benefit",
            "union bookkeeping uses extra capacity; it is not an equal-budget third strategy",
            "VALIDATION has already been explored; no independent generalization or significance claim",
            "legacy fit provenance is not retrospectively certified; existing temporal/context limits remain",
            "shared raw Parquets filtered by authorized IDs/splits; physical row groups may be shared",
        ],
    })
    serialized = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        stream.write(serialized + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=["val"], default="val")
    args = parser.parse_args()
    result = run(split=args.split)
    print(json.dumps(result["comparisons"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
