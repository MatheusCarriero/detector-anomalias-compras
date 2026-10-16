"""Synthetic-only contracts for the development Invoice data adapter."""

import copy
import hashlib
import importlib
import json
from dataclasses import is_dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import IsolationForest

from ml.scripts import invoice_final_evaluation as executor
from ml.scripts.invoice_final_evaluation import FRAME_COLUMNS, PARAMETERS
from ml.scripts.treinar_modelo import FEATURES

ROOT = Path(__file__).resolve().parents[2]
HASHED_PATHS = (
    "data/processed/train_features.parquet",
    "data/processed/val_features.parquet",
    "ml/models/isolation_forest.joblib",
    "ml/models/model_metadata.json",
)
RAW_PATHS = ("data/raw/splits.parquet", "data/raw/labels.parquet", "data/raw/invoices.parquet")
SAFE_APIS = ("load_development_data", "inspect_development_files")
SYNTHETIC_API = "load_synthetic_development_data"
PUBLIC_APIS = (*SAFE_APIS, SYNTHETIC_API)


@pytest.fixture
def api():
    path = ROOT / "ml/scripts/invoice_data_adapter.py"
    assert path.is_file(), "Development Invoice adapter is not implemented yet"
    return importlib.import_module("ml.scripts.invoice_data_adapter")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def hashes(source):
    return {name: digest(source / name) for name in HASHED_PATHS}


def snapshot(source):
    return {str(path.relative_to(source)): digest(path) for path in source.rglob("*") if path.is_file()}


def synthetic_frame(split, count):
    values = np.random.default_rng(151 if split == "train" else 223).uniform(0, 5, (count, 19))
    frame = pd.DataFrame(values, columns=FEATURES)
    frame["invoice_amount"] = [(-1 if i % 3 == 0 else 1) * (i + 1) * 25.0 for i in range(count)]
    frame.insert(0, "fraud_type", [None if i % 2 == 0 else "synthetic_amount" for i in range(count)])
    frame.insert(0, "is_fraud", np.arange(count, dtype=np.int64) % 2)
    frame.insert(0, "split", split)
    frame.insert(0, "invoice_id", [f"synthetic-{split}-{i:03}" for i in range(count)])
    return frame


@pytest.fixture(scope="module")
def fitted_model():
    # The only fit in this suite uses this synthetic TRAIN fixture.
    return IsolationForest(**PARAMETERS).fit(synthetic_frame("train", 12)[FEATURES])


@pytest.fixture
def source(tmp_path, fitted_model):
    assert not tmp_path.resolve().is_relative_to(ROOT.resolve())
    for relative in ("data/raw", "data/processed", "ml/models"):
        (tmp_path / relative).mkdir(parents=True)
    train, val = synthetic_frame("train", 12), synthetic_frame("val", 6)
    for split, frame in (("train", train), ("val", val)):
        frame.iloc[::-1].to_parquet(tmp_path / f"data/processed/{split}_features.parquet", index=False)
    sentinel = synthetic_frame("test", 2)
    all_rows = pd.concat([train, val, sentinel], ignore_index=True)
    all_rows[["invoice_id", "split"]].iloc[::-1].to_parquet(tmp_path / RAW_PATHS[0], index=False)
    labels = all_rows[["invoice_id", "is_fraud", "fraud_type"]].copy()
    labels.loc[labels["invoice_id"].str.contains("-test-"), "is_fraud"] = 999
    labels.loc[labels["invoice_id"].str.contains("-test-"), "fraud_type"] = "__missing__"
    labels.iloc[::-1].to_parquet(tmp_path / RAW_PATHS[1], index=False)
    amounts = all_rows[["invoice_id", "invoice_amount"]].assign(currency="SYN")
    amounts.loc[amounts["invoice_id"].str.contains("-test-"), "currency"] = None
    amounts.iloc[::-1].to_parquet(tmp_path / RAW_PATHS[2], index=False)
    (tmp_path / "data/processed/test_features.parquet").write_bytes(b"TEST SENTINEL: NOT PARQUET")
    joblib.dump(fitted_model, tmp_path / HASHED_PATHS[2])
    (tmp_path / HASHED_PATHS[3]).write_text(json.dumps({
        "model_name": "synthetic_invoice_isolation_forest",
        "algorithm": "IsolationForest", "n_estimators": 200,
        "contamination": 0.22, "random_state": 42,
        "feature_count": 19, "features": FEATURES,
        "training_date": "2000-01-01T00:00:00",
    }), encoding="utf-8")
    return tmp_path


def load(api, source, fitted_model, *, split="val", method="load_development_data", **kwargs):
    return getattr(api, method)(source, split=split,
                               expected_hashes=(kwargs["expected_hashes"] if "expected_hashes" in kwargs
                                                else hashes(source)),
                               expected_offset=kwargs.get("expected_offset", float(fitted_model.offset_)))


def forbid_operation(*args, **kwargs):
    raise AssertionError("The adapter must not fit, infer, read forbidden data, or write files")


@pytest.mark.parametrize("method", SAFE_APIS)
@pytest.mark.parametrize("split", ["train", "val"])
def test_safe_loader_never_touches_mixed_raw_files(api, source, fitted_model, monkeypatch, method, split):
    expected_hashes = hashes(source)
    forbidden_paths = {source / name for name in RAW_PATHS}
    forbidden_paths.add(source / "data/processed/test_features.parquet")
    parquet = pd.read_parquet

    def guard_path_operation(operation):
        def checked(path, *args, **kwargs):
            assert path not in forbidden_paths, "Safe loading must not touch mixed raw or TEST files"
            return operation(path, *args, **kwargs)
        return checked

    for name in ("resolve", "stat", "open", "read_bytes", "read_text"):
        monkeypatch.setattr(Path, name, guard_path_operation(getattr(Path, name)))

    def only_separate_parquet(path, **kwargs):
        if isinstance(path, (str, Path)):
            assert Path(path).relative_to(source).as_posix() in HASHED_PATHS[:2]
        return parquet(path, **kwargs)

    monkeypatch.setattr(pd, "read_parquet", only_separate_parquet)
    result = load(api, source, fitted_model, method=method, split=split, expected_hashes=expected_hashes)
    pd.testing.assert_frame_equal(result.frame, synthetic_frame(split, 12 if split == "train" else 6))
    assert result.technical_record["source_reconciled"] is False
    assert result.technical_record["protocol_version"] == "invoice-academic-evaluation-1.1"
    assert result.technical_record["accessed_files"] == list(HASHED_PATHS)


@pytest.mark.parametrize("method", PUBLIC_APIS)
@pytest.mark.parametrize("split", ["test", "TEST", "Train", "validation", "../test", "", None, 1, []])
def test_rejected_split_fails_before_any_read(api, tmp_path, monkeypatch, split, method):
    def forbidden(*args, **kwargs):
        raise AssertionError("A rejected split must fail before filesystem access")

    for name in ("open", "resolve", "stat", "read_bytes", "read_text"):
        monkeypatch.setattr(Path, name, forbidden)
    monkeypatch.setattr(pd, "read_parquet", forbidden)
    monkeypatch.setattr(joblib, "load", forbidden)
    with pytest.raises((ValueError, TypeError)):
        getattr(api, method)(
            tmp_path, split=split, expected_hashes={}, expected_offset=-0.5
        )


@pytest.mark.parametrize("split", ["train", "val"])
@pytest.mark.parametrize("method", PUBLIC_APIS)
def test_load_preserves_schema_dtypes_signed_amounts_without_inference_or_writes(
    api, source, fitted_model, monkeypatch, split, method
):
    before = snapshot(source)
    expected = synthetic_frame(split, 12 if split == "train" else 6)
    deserialize = joblib.load
    loaded_models = []

    def capture_loaded_model(*args, **kwargs):
        model = deserialize(*args, **kwargs)
        loaded_models.append((model, joblib.hash(model)))
        return model

    monkeypatch.setattr(joblib, "load", capture_loaded_model)
    for operation in ("fit", "predict", "score_samples", "decision_function"):
        monkeypatch.setattr(IsolationForest, operation, forbid_operation)
    result = load(api, source, fitted_model, split=split, method=method)
    assert is_dataclass(result)
    assert list(result.frame.columns) == FRAME_COLUMNS
    pd.testing.assert_frame_equal(result.frame, expected)
    assert isinstance(result.model, IsolationForest)
    assert len(loaded_models) == 1
    assert result.model is loaded_models[0][0]
    assert joblib.hash(result.model) == loaded_models[0][1]
    assert result.technical_record["source_reconciled"] is (method == SYNTHETIC_API)
    assert snapshot(source) == before


@pytest.mark.parametrize("split", ["train", "val"])
def test_raw_reads_are_projected_and_filtered_to_official_authorized_ids(
    api, source, fitted_model, monkeypatch, split
):
    parquet = pd.read_parquet
    path_open = Path.open
    expected_ids = synthetic_frame(split, 12 if split == "train" else 6)["invoice_id"].tolist()
    seen = []

    def checked_read(path, **kwargs):
        if not isinstance(path, (str, Path)):
            return parquet(path, **kwargs)
        relative = Path(path).relative_to(source).as_posix()
        assert relative in {*HASHED_PATHS[:2], *RAW_PATHS}
        seen.append(relative)
        if relative == RAW_PATHS[0]:
            assert kwargs["columns"] == ["invoice_id", "split"]
            assert kwargs["filters"] == [("split", "in", ["train", "val"])]
        elif relative in RAW_PATHS[1:]:
            expected_columns = (["invoice_id", "is_fraud", "fraud_type"] if relative == RAW_PATHS[1]
                                else ["invoice_id", "invoice_amount", "currency"])
            assert kwargs["columns"] == expected_columns
            assert kwargs["filters"] == [("invoice_id", "in", expected_ids)]
        return parquet(path, **kwargs)

    def no_whole_raw_open(path, *args, **kwargs):
        assert path not in {source / name for name in RAW_PATHS}, "Mixed raw files must not be fully read or hashed"
        assert path != source / "data/processed/test_features.parquet"
        return path_open(path, *args, **kwargs)

    monkeypatch.setattr(pd, "read_parquet", checked_read)
    monkeypatch.setattr(Path, "open", no_whole_raw_open)
    result = load(api, source, fitted_model, split=split, method=SYNTHETIC_API)
    assert result.frame["invoice_id"].tolist() == expected_ids
    assert all(relative in seen for relative in RAW_PATHS)


@pytest.mark.parametrize("method", SAFE_APIS)
def test_safe_apis_need_no_mixed_raw_files(api, source, fitted_model, monkeypatch, method):
    for name in RAW_PATHS:
        (source / name).unlink()
    parquet = pd.read_parquet

    def only_development_parquet(path, **kwargs):
        if isinstance(path, (str, Path)):
            assert Path(path).relative_to(source).as_posix() in HASHED_PATHS[:2]
        return parquet(path, **kwargs)

    monkeypatch.setattr(pd, "read_parquet", only_development_parquet)
    result = load(api, source, fitted_model, method=method)
    assert result.technical_record["source_reconciled"] is False
    assert len(result.frame) == 6


def block_fixture_readers(api, monkeypatch):
    for name in ("_paths", "_stats", "_processed"):
        monkeypatch.setattr(api, name, forbid_operation)
    for name in ("open", "read_bytes", "read_text"):
        monkeypatch.setattr(Path, name, forbid_operation)
    monkeypatch.setattr(pd, "read_parquet", forbid_operation)
    monkeypatch.setattr(joblib, "load", forbid_operation)


@pytest.mark.parametrize("relative", [".", "ml", "ml/scripts"])
def test_synthetic_api_rejects_project_root_and_descendants_before_readers(api, monkeypatch, relative):
    root = executor.PROJECT_ROOT / relative
    block_fixture_readers(api, monkeypatch)
    with pytest.raises(ValueError):
        api.load_synthetic_development_data(
            root, split="val", expected_hashes={name: "0" * 64 for name in HASHED_PATHS},
            expected_offset=-0.5,
        )


@pytest.mark.parametrize("relative", [".", "ml"])
def test_synthetic_api_rejects_mock_resolved_project_alias_before_readers(api, tmp_path, monkeypatch, relative):
    root = tmp_path / "fixture-alias"
    resolved_target = (executor.PROJECT_ROOT / relative).resolve()
    resolve = Path.resolve

    def resolve_alias(path, *args, **kwargs):
        if path == root:
            return resolved_target
        return resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve_alias)
    block_fixture_readers(api, monkeypatch)
    with pytest.raises(ValueError):
        api.load_synthetic_development_data(
            root, split="val", expected_hashes={name: "0" * 64 for name in HASHED_PATHS},
            expected_offset=-0.5,
        )


@pytest.mark.parametrize("relative", [".", "ml"])
def test_synthetic_root_symlink_into_project_is_rejected_before_readers(api, tmp_path, monkeypatch, relative):
    root = tmp_path / "project-alias"
    try:
        root.symlink_to(executor.PROJECT_ROOT / relative, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symlinks requires Windows privilege on this host")
    block_fixture_readers(api, monkeypatch)
    with pytest.raises(ValueError):
        api.load_synthetic_development_data(
            root, split="val", expected_hashes={name: "0" * 64 for name in HASHED_PATHS},
            expected_offset=-0.5,
        )


@pytest.mark.parametrize("path", HASHED_PATHS)
def test_hash_mismatch_rejected_before_model_deserialization(api, source, fitted_model, monkeypatch, path):
    expected = hashes(source)
    expected[path] = "0" * 64
    monkeypatch.setattr(joblib, "load", forbid_operation)
    with pytest.raises(ValueError):
        load(api, source, fitted_model, expected_hashes=expected)


@pytest.mark.parametrize("fault", ["missing", "extra", "invalid", "not_mapping"])
def test_expected_hashes_require_exact_four_path_contract(api, source, fitted_model, monkeypatch, fault):
    expected = hashes(source)
    if fault == "missing":
        expected.pop(HASHED_PATHS[0])
    elif fault == "extra":
        expected[RAW_PATHS[0]] = "0" * 64
    elif fault == "invalid":
        expected[HASHED_PATHS[0]] = "not-a-sha256"
    else:
        expected = []
    monkeypatch.setattr(pd, "read_parquet", forbid_operation)
    monkeypatch.setattr(joblib, "load", forbid_operation)
    with pytest.raises((ValueError, TypeError)):
        load(api, source, fitted_model, expected_hashes=expected)


def test_sha256_is_case_insensitive(api, source, fitted_model):
    expected = {name: value.upper() for name, value in hashes(source).items()}
    assert len(load(api, source, fitted_model, expected_hashes=expected).frame) == 6


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True, "-0.5", None, [-0.5]])
@pytest.mark.parametrize("method", PUBLIC_APIS)
def test_expected_offset_is_explicit_finite_scalar_before_io(api, tmp_path, monkeypatch, value, method):
    monkeypatch.setattr(pd, "read_parquet", forbid_operation)
    monkeypatch.setattr(joblib, "load", forbid_operation)
    monkeypatch.setattr(Path, "open", forbid_operation)
    with pytest.raises((ValueError, TypeError)):
        getattr(api, method)(tmp_path, split="val", expected_hashes={name: "0" * 64 for name in HASHED_PATHS},
                             expected_offset=value)


@pytest.mark.parametrize("fault", [
    "order", "missing_feature", "extra_feature", "empty", "null_id", "duplicate_id",
    "wrong_split", "null_feature", "infinite_feature", "text_feature", "bool_feature",
    "nonbinary_label", "float_label", "bool_label", "null_label", "reserved_fraud_type",
])
@pytest.mark.parametrize("split", ["train", "val"])
def test_each_processed_cohort_is_validated_in_full(api, source, fitted_model, split, fault):
    path = source / f"data/processed/{split}_features.parquet"
    frame = pd.read_parquet(path)
    if fault == "order":
        frame = frame[[*FRAME_COLUMNS[:4], *FEATURES[::-1]]]
    elif fault == "missing_feature":
        frame = frame.drop(columns=[FEATURES[-1]])
    elif fault == "extra_feature":
        frame["unexpected"] = 1.0
    elif fault == "empty":
        frame = frame.iloc[:0]
    elif fault == "null_id":
        frame.loc[0, "invoice_id"] = None
    elif fault == "duplicate_id":
        frame.loc[0, "invoice_id"] = frame.loc[1, "invoice_id"]
    elif fault == "wrong_split":
        frame.loc[0, "split"] = "test"
    elif fault == "null_feature":
        frame.loc[0, FEATURES[0]] = np.nan
    elif fault == "infinite_feature":
        frame.loc[0, FEATURES[0]] = np.inf
    elif fault == "text_feature":
        frame[FEATURES[0]] = "not-numeric"
    elif fault == "bool_feature":
        frame[FEATURES[0]] = True
    elif fault == "nonbinary_label":
        frame.loc[0, "is_fraud"] = 2
    elif fault == "float_label":
        frame["is_fraud"] = frame["is_fraud"].astype(float)
    elif fault == "bool_label":
        frame["is_fraud"] = frame["is_fraud"].astype(bool)
    elif fault == "null_label":
        frame["is_fraud"] = frame["is_fraud"].astype("Int64")
        frame.loc[0, "is_fraud"] = pd.NA
    else:
        frame.loc[0, "fraud_type"] = "__missing__"
    frame.to_parquet(path, index=False)
    with pytest.raises((ValueError, TypeError)):
        load(api, source, fitted_model)


@pytest.mark.parametrize("fault", ["overlap", "official_missing", "official_extra", "official_duplicate"])
def test_invalid_cohort_is_rejected_before_reading_labels_or_invoices(api, source, fitted_model, monkeypatch, fault):
    if fault == "overlap":
        path = source / HASHED_PATHS[0]
        frame = pd.read_parquet(path)
        frame.loc[0, "invoice_id"] = "synthetic-val-000"
    else:
        path = source / RAW_PATHS[0]
        frame = pd.read_parquet(path)
        if fault == "official_missing":
            frame = frame.loc[frame["invoice_id"] != "synthetic-val-000"]
        elif fault == "official_extra":
            frame = pd.concat([frame, pd.DataFrame({"invoice_id": ["extra-val"], "split": ["val"]})])
        else:
            frame = pd.concat([frame, frame.loc[frame["invoice_id"] == "synthetic-val-000"]])
    frame.to_parquet(path, index=False)
    parquet = pd.read_parquet

    def no_raw_values(path, **kwargs):
        if isinstance(path, (str, Path)):
            assert Path(path).name not in {"labels.parquet", "invoices.parquet"}
        return parquet(path, **kwargs)

    monkeypatch.setattr(pd, "read_parquet", no_raw_values)
    with pytest.raises((ValueError, TypeError)):
        load(api, source, fitted_model, method=SYNTHETIC_API)


@pytest.mark.parametrize("raw_name", RAW_PATHS)
def test_reader_returning_unauthorized_rows_is_rejected(api, source, fitted_model, monkeypatch, raw_name):
    parquet = pd.read_parquet

    def ignore_filter(path, **kwargs):
        if isinstance(path, (str, Path)) and Path(path) == source / raw_name:
            kwargs.pop("filters", None)
        return parquet(path, **kwargs)

    monkeypatch.setattr(pd, "read_parquet", ignore_filter)
    with pytest.raises((ValueError, TypeError)):
        load(api, source, fitted_model, method=SYNTHETIC_API)


@pytest.mark.parametrize("fault", ["label", "fraud_type", "missing", "duplicate", "float_label", "reserved_type"])
def test_selected_source_labels_are_reconciled_by_id(api, source, fitted_model, fault):
    path = source / RAW_PATHS[1]
    frame = pd.read_parquet(path)
    selected = frame["invoice_id"] == "synthetic-val-001"
    if fault == "label":
        frame.loc[selected, "is_fraud"] = 0
    elif fault == "fraud_type":
        frame.loc[selected, "fraud_type"] = "different_type"
    elif fault == "missing":
        frame = frame.loc[~selected]
    elif fault == "duplicate":
        frame = pd.concat([frame, frame.loc[selected]])
    elif fault == "float_label":
        frame["is_fraud"] = frame["is_fraud"].astype(float)
    else:
        frame.loc[selected, "fraud_type"] = "__missing__"
    frame.to_parquet(path, index=False)
    with pytest.raises((ValueError, TypeError)):
        load(api, source, fitted_model, method=SYNTHETIC_API)


@pytest.mark.parametrize("fault", ["absolute_amount", "amount", "null_amount", "infinite_amount", "null_currency", "mixed_currency", "missing", "duplicate"])
def test_signed_source_amounts_and_single_currency_are_required(api, source, fitted_model, fault):
    path = source / RAW_PATHS[2]
    frame = pd.read_parquet(path)
    selected = frame["invoice_id"] == "synthetic-val-000"
    if fault == "absolute_amount":
        frame.loc[selected, "invoice_amount"] = frame.loc[selected, "invoice_amount"].abs()
    elif fault == "amount":
        frame.loc[selected, "invoice_amount"] += 0.01
    elif fault == "null_amount":
        frame.loc[selected, "invoice_amount"] = np.nan
    elif fault == "infinite_amount":
        frame.loc[selected, "invoice_amount"] = np.inf
    elif fault == "null_currency":
        frame.loc[selected, "currency"] = None
    elif fault == "mixed_currency":
        frame.loc[selected, "currency"] = "OTHER"
    elif fault == "missing":
        frame = frame.loc[~selected]
    else:
        frame = pd.concat([frame, frame.loc[selected]])
    frame.to_parquet(path, index=False)
    with pytest.raises((ValueError, TypeError)):
        load(api, source, fitted_model, method=SYNTHETIC_API)


@pytest.mark.parametrize("parameter,value", [
    ("n_estimators", 199), ("contamination", 0.1), ("random_state", 43), ("n_jobs", 1),
    ("max_samples", 10), ("max_features", 0.5), ("bootstrap", True),
    ("warm_start", True), ("verbose", 1),
])
def test_every_model_parameter_is_frozen(api, source, fitted_model, parameter, value):
    model = copy.deepcopy(fitted_model).set_params(**{parameter: value})
    joblib.dump(model, source / HASHED_PATHS[2])
    with pytest.raises((ValueError, TypeError)):
        load(api, source, fitted_model)


@pytest.mark.parametrize("fault", ["wrong_type", "unfitted", "feature_order", "feature_count", "offset", "nan_offset", "missing_tree"])
def test_model_identity_fitted_state_and_prior_offset_are_required(api, source, fitted_model, fault):
    model = copy.deepcopy(fitted_model)
    if fault == "wrong_type":
        model = {"not": "a model"}
    elif fault == "unfitted":
        model = IsolationForest(**PARAMETERS)
    elif fault == "feature_order":
        model.feature_names_in_ = np.array(FEATURES[::-1])
    elif fault == "feature_count":
        model.n_features_in_ = 18
    elif fault == "offset":
        model.offset_ += 0.01
    elif fault == "nan_offset":
        model.offset_ = np.nan
    else:
        model.estimators_ = model.estimators_[:-1]
    joblib.dump(model, source / HASHED_PATHS[2])
    with pytest.raises((ValueError, TypeError)):
        load(api, source, fitted_model)


@pytest.mark.parametrize("key,value", [
    ("features", FEATURES[::-1]), ("feature_count", 18), ("n_estimators", 199),
    ("algorithm", "OtherAlgorithm"), ("n_jobs", 1),
    ("parameters", {"n_estimators": 199}), ("offset", 999.0),
])
def test_legacy_metadata_and_present_optional_parameters_must_match(api, source, fitted_model, key, value):
    path = source / HASHED_PATHS[3]
    metadata = json.loads(path.read_text(encoding="utf-8"))
    metadata[key] = value
    path.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises((ValueError, TypeError)):
        load(api, source, fitted_model)


@pytest.mark.parametrize("changed_path", HASHED_PATHS)
def test_changed_allowed_file_during_read_is_detected(api, source, fitted_model, monkeypatch, changed_path):
    expected = hashes(source)
    parquet = pd.read_parquet
    mutated = False

    def read_then_mutate(path, **kwargs):
        nonlocal mutated
        result = parquet(path, **kwargs)
        if isinstance(path, (str, Path)) and Path(path).name == "invoices.parquet" and not mutated:
            target = source / changed_path
            target.write_bytes(target.read_bytes() + b"changed-after-validation")
            mutated = True
        return result

    monkeypatch.setattr(pd, "read_parquet", read_then_mutate)
    with pytest.raises(ValueError):
        load(api, source, fitted_model, method=SYNTHETIC_API, expected_hashes=expected)
    assert mutated


@pytest.mark.parametrize("method", PUBLIC_APIS)
def test_symlink_escape_is_rejected_before_opening_target(api, source, fitted_model, tmp_path, monkeypatch, method):
    expected = hashes(source)
    target = tmp_path.parent / f"{tmp_path.name}-outside-model.joblib"
    model_path = source / HASHED_PATHS[2]
    target.write_bytes(model_path.read_bytes())
    model_path.unlink()
    try:
        model_path.symlink_to(target)
    except OSError:
        pytest.skip("Creating symlinks requires Windows privilege on this host")
    path_open = Path.open

    def no_target_read(path, *args, **kwargs):
        assert path != target and path != model_path
        return path_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", no_target_read)
    with pytest.raises(ValueError):
        load(api, source, fitted_model, method=method, expected_hashes=expected)
