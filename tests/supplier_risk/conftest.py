"""Fixtures sem Kaggle; todos os caminhos de I/O apontam para tmp_path."""

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
APPROVED_FEATURES = [
    "financial_stability_score", "on_time_delivery_rate", "defect_rate",
    "geopolitical_risk_index", "lead_time_days", "alternative_suppliers_available",
    "contract_length_months", "environmental_compliance", "previous_disruptions",
    "supplier_record_count",
]


def load_script(name):
    path = REPOSITORY_ROOT / "ml" / "supplier_risk" / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"supplier_test_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def feature_module():
    return load_script("prepare_features")


@pytest.fixture(scope="session")
def target_module():
    return load_script("prepare_target_and_split")


@pytest.fixture(scope="session")
def ml_module():
    return load_script("build_ml_dataset")


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path, monkeypatch, feature_module, target_module, ml_module):
    output = tmp_path / "processed"
    source = tmp_path / "source.csv"
    base = output / "supplier_features_base.parquet"
    targets = output / "supplier_targets.parquet"
    splits = output / "supplier_split_assignments.parquet"
    for module in (feature_module, target_module, ml_module):
        monkeypatch.setattr(module, "PROJECT_ROOT", tmp_path)
    for module in (feature_module, target_module):
        monkeypatch.setattr(module, "SOURCE_PATH", source)
        monkeypatch.setattr(module, "OUTPUT_DIR", output)
    monkeypatch.setattr(feature_module, "OUTPUT_PATH", base)
    monkeypatch.setattr(feature_module, "QUALITY_PATH", output / "quality.parquet")
    monkeypatch.setattr(feature_module, "METADATA_PATH", output / "base_metadata.json")
    monkeypatch.setattr(target_module, "BASE_PATH", base)
    monkeypatch.setattr(target_module, "TARGETS_PATH", targets)
    monkeypatch.setattr(target_module, "SPLIT_PATH", splits)
    monkeypatch.setattr(target_module, "AUDIT_PATH", output / "audit.json")
    monkeypatch.setattr(target_module, "METADATA_PATH", output / "split_metadata.json")
    monkeypatch.setattr(ml_module, "PROCESSED_DIR", output)
    monkeypatch.setattr(ml_module, "INPUT_PATHS", {
        "features": base, "targets": targets, "split": splits,
    })
    monkeypatch.setattr(ml_module, "OUTPUT_DIR", output / "ml_ready")
    monkeypatch.setattr(ml_module, "METADATA_PATH", output / "ml_ready" / "metadata.json")


@pytest.fixture
def approved_features():
    return APPROVED_FEATURES.copy()


@pytest.fixture
def source_frame():
    row = {
        "Supplier_ID": "A", "Financial_Stability_Score": 10.0,
        "On_Time_Delivery_Rate": np.nan, "Defect_Rate": 2.0,
        "Geopolitical_Risk_Index": 31.0, "Lead_Time_Days": 0.0,
        "Alternative_Suppliers_Available": 3.0, "Contract_Length_Months": 19.0,
        "Environmental_Compliance": 100.95, "Previous_Disruptions": 1.0,
        "Risk_Level": 0, "Risk_Category": "label", "Country": "BR",
        "Delivery_Quality_Index": 123.0, "Supplier_Dependency_Score": 0.25,
    }
    return pd.DataFrame([
        row, row.copy(),
        {**row, "On_Time_Delivery_Rate": 80.0},
        {**row, "Supplier_ID": "B", "Financial_Stability_Score": np.nan,
         "On_Time_Delivery_Rate": 50.0, "Risk_Level": 1},
        {**row, "Supplier_ID": "C", "Financial_Stability_Score": 90.0,
         "On_Time_Delivery_Rate": 20.0, "Lead_Time_Days": -1.0},
    ])


@pytest.fixture
def ml_inputs(approved_features):
    ids = list("ABCDEFG")
    values = [1.0, 2.0, np.nan, 1000.0, np.nan, 2000.0, np.nan]
    features = pd.DataFrame({"supplier_id": ids, **dict.fromkeys(approved_features, values)})
    targets = pd.DataFrame({"supplier_id": ids, "risk_level": [0, 1, 0, 1, 0, 1, 0]})
    split = pd.DataFrame({
        "supplier_id": ids,
        "split": ["train"] * 3 + ["validation"] * 2 + ["test"] * 2,
    })
    return {"features": features, "targets": targets, "split": split}


@pytest.fixture
def write_ml_inputs(ml_module, ml_inputs):
    def write():
        for name, frame in ml_inputs.items():
            path = ml_module.INPUT_PATHS[name]
            path.parent.mkdir(parents=True, exist_ok=True)
            frame.to_parquet(path, index=False)
    return write
