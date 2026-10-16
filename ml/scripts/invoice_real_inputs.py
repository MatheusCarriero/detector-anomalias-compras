"""Explicit input consistency checks for an academic evaluation; no fit or scoring.

Calling file validation opens every supplied source. Development checks must use
synthetic fixtures, never the shared real sources or TEST.
"""

from pathlib import Path

import numpy as np
import pandas as pd

from ml.scripts import invoice_data_adapter as adapter
from ml.scripts import invoice_final_evaluation as executor


def validate_frames(*, frames, model, metadata, splits, labels, amounts, configuration):
    """Validate supplied in-memory partitions and their independent source tables."""
    executor._validate_configuration(configuration)
    if not isinstance(frames, dict) or set(frames) != {"train", "val", "test"}:
        raise ValueError("Exigidas as tres particoes separadas train/val/test")
    if configuration["split"] not in frames:
        raise ValueError("Particao configurada ausente dos inputs")
    for partition, frame in frames.items():
        adapter._processed_frame(frame, partition)
    adapter._metadata(executor._canonical(metadata), configuration["legacy_offset"])
    executor._model(model, configuration)
    frame, currency = _source_consistency(frames, splits, labels, amounts, configuration["split"])
    return adapter.AdaptedInvoice(frame, model, {
        "split": configuration["split"], "rows": {key: len(value) for key, value in frames.items()},
        "currency": currency, "source_rows_consistent": True, "source_reconciled": False,
        "model_fits": 0, "score_calls": 0,
    })


def validate_inputs(*, processed_paths, model_path, metadata_path, splits_path,
                    labels_path, amounts_path, configuration):
    """Load explicitly supplied files; trusted model files only (joblib is executable)."""
    executor._validate_configuration(configuration)
    if not isinstance(processed_paths, dict) or set(processed_paths) != {"train", "val", "test"}:
        raise ValueError("Exigidos caminhos explicitos train/val/test")
    if configuration["split"] not in processed_paths:
        raise ValueError("Particao configurada ausente dos inputs")
    metadata = executor._json(Path(metadata_path).read_bytes())
    adapter._metadata(executor._canonical(metadata), configuration["legacy_offset"])
    model = adapter._load_model(Path(model_path).read_bytes(), configuration["legacy_offset"])
    return validate_frames(
        frames={key: pd.read_parquet(path) for key, path in processed_paths.items()},
        model=model, metadata=metadata,
        splits=pd.read_parquet(splits_path, columns=["invoice_id", "split"]),
        labels=pd.read_parquet(labels_path, columns=["invoice_id", "is_fraud", "fraud_type"]),
        amounts=pd.read_parquet(amounts_path, columns=["invoice_id", "invoice_amount", "currency"]),
        configuration=configuration,
    )

def _source_consistency(frames, official, labels, amounts, split):
    """Current row agreement only; never certify the legacy training provenance."""
    adapter._schema(official, ["invoice_id", "split"], "splits oficiais")
    if not official["split"].isin(["train", "val", "test"]).all():
        raise ValueError("Particao oficial desconhecida")
    seen = set()
    for partition, frame in frames.items():
        ids = set(frame["invoice_id"])
        if seen & ids:
            raise ValueError("Sobreposicao de IDs entre particoes processadas")
        seen.update(ids)
        expected_ids = set(official.loc[official["split"].eq(partition), "invoice_id"])
        if ids != expected_ids:
            raise ValueError("Coorte processada diverge dos IDs/split oficiais")
    if seen != set(official["invoice_id"]):
        raise ValueError("Perda ou inclusao silenciosa de IDs oficiais")
    frame = frames[split].sort_values("invoice_id").reset_index(drop=True)
    ids = frame["invoice_id"].tolist()
    for source, columns, name in (
        (labels, ["invoice_id", "is_fraud", "fraud_type"], "labels"),
        (amounts, ["invoice_id", "invoice_amount", "currency"], "valores/moedas"),
    ):
        adapter._schema(source, columns, name)
        if set(source["invoice_id"]) != seen:
            raise ValueError("Cobertura de IDs da fonte diverge dos splits oficiais")
    labels = labels.set_index("invoice_id").loc[ids].reset_index()
    adapter.validate_target(labels)
    adapter._utf8(labels["fraud_type"])
    if not frame[["invoice_id", "is_fraud", "fraud_type"]].equals(labels):
        raise ValueError("Labels/fraud_type divergentes por ID; nenhuma correcao")
    amounts = amounts.set_index("invoice_id").loc[ids].reset_index()
    values = amounts["invoice_amount"]
    if (not pd.api.types.is_numeric_dtype(values.dtype)
            or pd.api.types.is_bool_dtype(values.dtype)
            or pd.api.types.is_complex_dtype(values.dtype) or values.isna().any()
            or not np.isfinite(values.to_numpy(dtype=float)).all()
            or not np.array_equal(values.to_numpy(), frame["invoice_amount"].to_numpy())):
        raise ValueError("Valores da fonte invalidos ou divergentes por ID")
    currency = amounts["currency"]
    if (not currency.map(lambda value: isinstance(value, str) and bool(value)
                         and value == value.strip()).all() or currency.nunique() != 1):
        raise ValueError("Exigida uma unica moeda nao nula, sem conversao")
    adapter._utf8(currency)
    return frame, str(currency.iloc[0])
