import importlib.util
import json
from datetime import datetime as RealDatetime
from datetime import timedelta, timezone
from pathlib import Path
from uuid import uuid4

import joblib
import numpy as np
import pandas as pd
import pytest
import sklearn.ensemble

MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "ml" / "scripts" / "treinar_modelo.py"
)

EXPECTED_FEATURES = [
    "invoice_amount",
    "log_invoice_amount",
    "supplier_age_days",
    "supplier_frequency",
    "country_frequency",
    "amount_vs_supplier_mean",
    "supplier_amount_zscore",
    "department_frequency",
    "amount_vs_department_mean",
    "supplier_department_frequency",
    "payment_terms_days",
    "invoice_type_encoded",
    "submission_hour_sin",
    "submission_hour_cos",
    "day_of_week_sin",
    "day_of_week_cos",
    "month_sin",
    "month_cos",
    "is_weekend",
]


def load_training_module():
    module_name = f"invoice_training_{uuid4().hex}"
    spec = importlib.util.spec_from_file_location(module_name, MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def training_module():
    return load_training_module()


def valid_frame(row_count=3):
    return pd.DataFrame(1.0, index=range(row_count), columns=EXPECTED_FEATURES)


def fail_if_called(*args, **kwargs):
    del args, kwargs
    raise AssertionError("importing the training module caused a side effect")


def test_import_does_not_read_fit_or_write(monkeypatch):
    class FailingEstimator:
        fit = fail_if_called

    monkeypatch.setattr(pd, "read_parquet", fail_if_called)
    monkeypatch.setattr(joblib, "dump", fail_if_called)
    monkeypatch.setattr(
        sklearn.ensemble,
        "IsolationForest",
        lambda **kwargs: FailingEstimator(),
    )

    module = load_training_module()

    assert callable(module.validate_training_features)
    assert callable(module.main)


def test_validation_accepts_real_numeric_features_without_mutating_frame(
    training_module,
):
    frame = valid_frame()
    frame["supplier_age_days"] = frame["supplier_age_days"].astype("int64")
    original = frame.copy(deep=True)

    result = training_module.validate_training_features(frame)

    assert result is None
    pd.testing.assert_frame_equal(frame, original)


def test_validation_rejects_non_dataframe(training_module):
    with pytest.raises(TypeError):
        training_module.validate_training_features([[1.0] * 19])


def test_validation_rejects_empty_frame(training_module):
    with pytest.raises(ValueError, match="vazio"):
        training_module.validate_training_features(valid_frame(row_count=0))


@pytest.mark.parametrize(
    "columns",
    [
        EXPECTED_FEATURES[:-1],
        [*EXPECTED_FEATURES, "is_fraud"],
        [EXPECTED_FEATURES[1], EXPECTED_FEATURES[0], *EXPECTED_FEATURES[2:]],
    ],
    ids=["missing", "extra", "reordered"],
)
def test_validation_rejects_schema_different_from_ordered_features(
    training_module,
    columns,
):
    frame = pd.DataFrame(1.0, index=range(3), columns=columns)

    with pytest.raises(ValueError, match="colunas"):
        training_module.validate_training_features(frame)


@pytest.mark.parametrize(
    "invalid_value",
    ["not-a-number", 1 + 2j, True],
    ids=["string", "complex", "boolean"],
)
def test_validation_rejects_non_real_numeric_types(
    training_module,
    invalid_value,
):
    frame = valid_frame()
    frame["invoice_amount"] = invalid_value

    with pytest.raises(ValueError):
        training_module.validate_training_features(frame)


@pytest.mark.parametrize(
    ("invalid_value", "message"),
    [
        (np.nan, "nulos"),
        (np.inf, "infinitos"),
        (-np.inf, "infinitos"),
    ],
    ids=["null", "positive-infinity", "negative-infinity"],
)
def test_validation_rejects_null_and_infinite_values(
    training_module,
    invalid_value,
    message,
):
    frame = valid_frame()
    frame.loc[0, "invoice_amount"] = invalid_value

    with pytest.raises(ValueError, match=message):
        training_module.validate_training_features(frame)


def test_main_trains_from_selected_train_features_and_writes_metadata(
    training_module,
    monkeypatch,
    tmp_path,
):
    training_path = tmp_path / "train_features.parquet"
    training_path.touch()
    models_dir = tmp_path / "models"
    model_path = models_dir / "isolation_forest.joblib"
    metadata_path = models_dir / "model_metadata.json"
    training_frame = valid_frame()
    calls = {"read": [], "factory": [], "fit": [], "dump": []}

    def fake_read_parquet(path, *, columns):
        calls["read"].append((path, columns))
        return training_frame.copy(deep=True)

    class FakeEstimator:
        def fit(self, frame):
            calls["fit"].append(frame.copy(deep=True))
            return self

    estimator = FakeEstimator()

    def fake_factory(**parameters):
        calls["factory"].append(parameters)
        return estimator

    def fake_dump(model, path):
        calls["dump"].append((model, path))

    class FrozenDatetime:
        @classmethod
        def now(cls):
            local_timezone = timezone(timedelta(hours=-3))
            return RealDatetime(
                2026,
                9,
                17,
                12,
                34,
                56,
                tzinfo=local_timezone,
            )

    monkeypatch.setattr(training_module, "TRAIN_DATA_PATH", training_path)
    monkeypatch.setattr(training_module, "MODELS_DIR", models_dir)
    monkeypatch.setattr(training_module, "MODEL_PATH", model_path)
    monkeypatch.setattr(training_module, "METADATA_PATH", metadata_path)
    monkeypatch.setattr(training_module.pd, "read_parquet", fake_read_parquet)
    monkeypatch.setattr(training_module, "IsolationForest", fake_factory)
    monkeypatch.setattr(training_module.joblib, "dump", fake_dump)
    monkeypatch.setattr(training_module, "datetime", FrozenDatetime)

    result = training_module.main()

    assert result is None
    assert calls["read"] == [(training_path, EXPECTED_FEATURES)]
    assert calls["factory"] == [
        {
            "n_estimators": 200,
            "contamination": 0.22,
            "random_state": 42,
            "n_jobs": -1,
        }
    ]
    assert len(calls["fit"]) == 1
    pd.testing.assert_frame_equal(calls["fit"][0], training_frame)
    assert calls["dump"] == [(estimator, model_path)]

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata == {
        "model_name": "Detector Inteligente de Anomalias em Compras",
        "algorithm": "IsolationForest",
        "n_estimators": 200,
        "contamination": 0.22,
        "random_state": 42,
        "feature_count": 19,
        "features": EXPECTED_FEATURES,
        "training_date": "2026-09-17T12:34:56-03:00",
    }
