"""Read-only Invoice development adapter. No TEST, fitting, scoring or publication.

Real development loading never opens shared raw sources: logical Parquet
filters do not physically isolate TEST. Raw reconciliation is fixture-only.
Only a trusted local model whose expected hash is supplied may be deserialized.
"""

import hashlib
import warnings
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.exceptions import InconsistentVersionWarning
from sklearn.utils.validation import check_is_fitted

from ml.scripts.avaliar_invoice import (
    validate_ids,
    validate_target,
    validate_training_features,
)
from ml.scripts.invoice_final_evaluation import (
    FRAME_COLUMNS,
    ORDERED_FEATURES,
    PARAMETERS,
    _canonical,
    _digest,
    _external,
    _json,
    _versions,
    configuration_contract,
    sha256,
)

PROCESSED = {name: f"data/processed/{name}_features.parquet" for name in ("train", "val")}
MODEL = "ml/models/isolation_forest.joblib"
METADATA = "ml/models/model_metadata.json"
HASHED_INPUTS = (*PROCESSED.values(), MODEL, METADATA)
RAW_SPLITS = "data/raw/splits.parquet"
RAW_LABELS = "data/raw/labels.parquet"
RAW_AMOUNTS = "data/raw/invoices.parquet"
RAW_INPUTS = (RAW_SPLITS, RAW_LABELS, RAW_AMOUNTS)


@dataclass
class AdaptedInvoice:
    """Validated in-memory inputs, not scores or a final-evaluation artifact."""

    frame: pd.DataFrame
    model: IsolationForest
    technical_record: dict


def _request(split, expected_hashes, expected_offset):
    # This gate must run before even resolving/stat-ing a caller's root.
    if not isinstance(split, str) or split not in {"train", "val"}:
        raise ValueError("Somente train e val autorizados; TEST bloqueado antes de I/O")
    if not isinstance(expected_hashes, dict) or set(expected_hashes) != set(HASHED_INPUTS):
        raise ValueError("Exigidos hashes externos dos quatro arquivos separados")
    hashes = {name: _digest(value) for name, value in expected_hashes.items()}
    offset = configuration_contract(expected_offset)["legacy_offset"]
    return hashes, offset


def _paths(root, names):
    root = Path(root).resolve(strict=True)
    result = {}
    for name in names:
        candidate = root / name
        resolved = candidate.resolve(strict=True)
        if resolved != candidate or not resolved.is_file():
            raise ValueError("Entrada fora do caminho exato autorizado ou nao regular")
        result[name] = resolved
    return result


def _schema(frame, columns, label):
    if not isinstance(frame, pd.DataFrame) or list(frame.columns) != list(columns):
        raise ValueError(f"Schema/ordem de colunas invalido: {label}")
    validate_ids(frame, label)
    _utf8(frame["invoice_id"])


def _utf8(values):
    for value in values.dropna():
        try:
            value.encode("utf-8")
        except (AttributeError, UnicodeError) as error:
            raise ValueError("Texto invalido no contrato Invoice") from error


def _processed_frame(frame, split):
    _schema(frame, FRAME_COLUMNS, split)
    if not frame["split"].eq(split).all():
        raise ValueError("Arquivo processado contem particao nao autorizada")
    validate_target(frame)
    _utf8(frame["fraud_type"])
    validate_training_features(frame[list(ORDERED_FEATURES)])
    if frame["supplier_frequency"].lt(0).any():
        raise ValueError("supplier_frequency negativa")


def _metadata(content):
    value = _json(content)
    required = {"algorithm": "IsolationForest", "feature_count": 19,
                "features": list(ORDERED_FEATURES),
                **{k: PARAMETERS[k] for k in ("n_estimators", "contamination", "random_state")}}
    if not isinstance(value, dict):
        raise TypeError("Metadata legado deve ser um objeto JSON")
    # The legacy metadata stores these fields at top level, not under parameters.
    for key, expected in required.items():
        if key not in value or _canonical(value[key]) != _canonical(expected):
            raise ValueError("Metadata legado diverge do contrato Invoice")
    for key in PARAMETERS.keys() & value.keys():
        if _canonical(value[key]) != _canonical(PARAMETERS[key]):
            raise ValueError("Parametro do metadata diverge do protocolo")


def _load_model(content, offset):
    with warnings.catch_warnings():
        warnings.simplefilter("error", InconsistentVersionWarning)
        model = joblib.load(BytesIO(content))
    if type(model) is not IsolationForest:
        raise TypeError("Modelo deve ser o IsolationForest local confiavel")
    check_is_fitted(model)
    if (getattr(model, "n_features_in_", None) != 19
            or list(getattr(model, "feature_names_in_", [])) != list(ORDERED_FEATURES)
            or len(model.estimators_) != 200):
        raise ValueError("Features, ordem ou arvores do modelo divergentes")
    if _canonical(model.get_params()) != _canonical(PARAMETERS):
        raise ValueError("Parametros do IsolationForest divergem do protocolo")
    if not np.isfinite(model.offset_) or float(model.offset_) != offset:
        raise ValueError("Offset diverge da referencia congelada")
    return model


def _check_hashes(paths, expected):
    for name, digest in expected.items():
        if sha256(paths[name]) != digest:
            raise ValueError("Arquivo separado alterado durante a validacao")


def _processed(root, split, expected_hashes, expected_offset):
    hashes, offset = _request(split, expected_hashes, expected_offset)
    paths = _paths(root, HASHED_INPUTS)
    content = {}
    for name, path in paths.items():
        content[name] = path.read_bytes()
        if hashlib.sha256(content[name]).hexdigest() != hashes[name]:
            raise ValueError("SHA-256 diverge da referencia; entrada nao sera desserializada")
    frames = {name: pd.read_parquet(BytesIO(content[path])) for name, path in PROCESSED.items()}
    for name, frame in frames.items():
        _processed_frame(frame, name)
    if set(frames["train"]["invoice_id"]) & set(frames["val"]["invoice_id"]):
        raise ValueError("Sobreposicao de IDs entre TRAIN e VALIDATION")
    _metadata(content[METADATA])
    model = _load_model(content[MODEL], offset)
    _check_hashes(paths, hashes)
    record = {
        "schema": "invoice-development-adapter/1.0",
        "protocol_version": "invoice-academic-evaluation-1.0",
        "scientific_evidence": False, "final_evaluation": False,
        "test_used": False, "test_authorized": False,
        "source_reconciled": False, "model_fits": 0, "score_calls": 0,
        "source_access_policy": "Separate TRAIN/VAL only; shared raw forbidden",
        "split": split, "rows": {name: len(frame) for name, frame in frames.items()},
        "features": list(ORDERED_FEATURES), "feature_count": 19,
        "parameters": PARAMETERS.copy(), "legacy_offset": offset,
        "input_hashes_sha256": hashes, "versions": _versions(),
        "accessed_files": list(HASHED_INPUTS),
        "training_provenance": "Legacy fit inputs are not retrospectively certified",
    }
    return frames, model, record, paths


def inspect_development_files(root, *, split, expected_hashes, expected_offset):
    """Validate only separate TRAIN/VAL and model files; never open shared raw."""
    frames, model, record, _ = _processed(root, split, expected_hashes, expected_offset)
    frame = frames[split].sort_values("invoice_id").reset_index(drop=True)
    return AdaptedInvoice(frame, model, record)


def load_development_data(root, *, split, expected_hashes, expected_offset):
    """Load authorized separate TRAIN/VAL inputs, without claiming raw provenance."""
    return inspect_development_files(root, split=split, expected_hashes=expected_hashes,
                                     expected_offset=expected_offset)


def _stats(paths):
    return {name: {"bytes": path.stat().st_size, "mtime_ns": str(path.stat().st_mtime_ns)}
            for name, path in paths.items()}


def _table_digest(frame):
    """Logical authorized rows, NOT a hash of the complete shared Parquet file."""
    frame = frame.sort_values("invoice_id").reset_index(drop=True)
    values = [[None if pd.isna(value) else value for value in row]
              for row in frame.itertuples(index=False, name=None)]
    payload = {"columns": list(frame.columns), "dtypes": [str(t) for t in frame.dtypes],
               "rows": values}
    return hashlib.sha256(_canonical(payload)).hexdigest()


def load_synthetic_development_data(root, *, split, expected_hashes, expected_offset):
    """Reconcile test-created fixtures outside the checkout; never real sources.

    A path guard prevents accidental checkout access, not disguised real copies.
    Only fixtures generated by tests may be supplied. Filters do not isolate
    physical row groups. There is no flag authorizing real shared raw access.
    """
    _request(split, expected_hashes, expected_offset)
    root = _external(root)
    raw_paths = _paths(root, RAW_INPUTS)
    raw_before = _stats(raw_paths)
    frames, model, record, paths = _processed(root, split, expected_hashes, expected_offset)
    official = pd.read_parquet(raw_paths[RAW_SPLITS], columns=["invoice_id", "split"],
                               filters=[("split", "in", ["train", "val"])])
    _schema(official, ["invoice_id", "split"], "splits oficiais")
    if not official["split"].isin(["train", "val"]).all():
        raise ValueError("Leitura de splits retornou particao nao autorizada")
    for name, frame in frames.items():
        expected_ids = set(official.loc[official["split"].eq(name), "invoice_id"])
        if set(frame["invoice_id"]) != expected_ids:
            raise ValueError("IDs processados divergem da particao oficial")

    frame = frames[split].sort_values("invoice_id").reset_index(drop=True)
    ids = frame["invoice_id"].tolist()
    # Source IDs come from the reconciled official partition, never arbitrary input.
    selection = [("invoice_id", "in", ids)]
    labels = pd.read_parquet(raw_paths[RAW_LABELS],
                             columns=["invoice_id", "is_fraud", "fraud_type"], filters=selection)
    amounts = pd.read_parquet(raw_paths[RAW_AMOUNTS],
                              columns=["invoice_id", "invoice_amount", "currency"], filters=selection)
    _schema(labels, ["invoice_id", "is_fraud", "fraud_type"], "labels da fonte")
    _schema(amounts, ["invoice_id", "invoice_amount", "currency"], "valores da fonte")
    for source in (labels, amounts):
        if set(source["invoice_id"]) != set(ids):
            raise ValueError("Fonte nao cobre exatamente os IDs autorizados")
    validate_target(labels)
    _utf8(labels["fraud_type"])
    aligned_labels = labels.set_index("invoice_id").loc[ids].reset_index()
    if not frame[["invoice_id", "is_fraud", "fraud_type"]].equals(aligned_labels):
        raise ValueError("Labels/fraud_type divergentes por ID; nenhuma correcao automatica")
    amounts = amounts.set_index("invoice_id").loc[ids].reset_index()
    value = amounts["invoice_amount"]
    if (not pd.api.types.is_numeric_dtype(value.dtype) or pd.api.types.is_bool_dtype(value.dtype)
            or pd.api.types.is_complex_dtype(value.dtype) or value.isna().any()
            or not np.isfinite(value.to_numpy(dtype=float)).all()
            or not np.array_equal(value.to_numpy(), frame["invoice_amount"].to_numpy())):
        raise ValueError("Valor original da fonte invalido ou divergente por ID")
    currency = amounts["currency"]
    if (not currency.map(lambda x: isinstance(x, str) and bool(x) and x == x.strip()).all()
            or currency.nunique() != 1):
        raise ValueError("Exigida uma unica moeda nao nula, sem conversao")
    _utf8(currency)
    _check_hashes(paths, record["input_hashes_sha256"])
    if _stats(raw_paths) != raw_before:
        raise ValueError("Fonte compartilhada alterada durante a validacao")
    record.update({
        "synthetic": True,
        "source_reconciled": True, "currency": str(currency.iloc[0]),
        "accessed_files": [*HASHED_INPUTS, *RAW_INPUTS],
        "authorized_subsets_sha256": {RAW_SPLITS: _table_digest(official),
                                      RAW_LABELS: _table_digest(aligned_labels),
                                      RAW_AMOUNTS: _table_digest(amounts)},
        "shared_raw_stat_before_after": raw_before,
        "source_access_policy": "split in [train,val]; labels/amounts by reconciled IDs only",
        "physical_isolation": "Parquet filters do not guarantee disjoint physical row groups",
    })
    return AdaptedInvoice(frame, model, record)
