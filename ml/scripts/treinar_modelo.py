import json
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

# ============================================================
# CAMINHOS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
MODELS_DIR = PROJECT_ROOT / "ml" / "models"

TRAIN_DATA_PATH = PROCESSED_DIR / "train_features.parquet"
MODEL_PATH = MODELS_DIR / "isolation_forest.joblib"
METADATA_PATH = MODELS_DIR / "model_metadata.json"


# ============================================================
# FEATURES DO MODELO
# ============================================================

FEATURES = [
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

EXPECTED_FEATURE_COUNT = 19


# ============================================================
# CARREGAMENTO E VALIDAÇÃO
# ============================================================


def validate_training_features(frame):
    """Validate the exact numeric feature matrix expected by the model."""
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("As features de treino devem ser um DataFrame.")

    if frame.empty:
        raise ValueError("O dataset de treino está vazio.")

    if list(frame.columns) != FEATURES:
        raise ValueError(
            "As colunas do dataset de treino devem corresponder exatamente "
            "às features esperadas, na ordem definida."
        )

    invalid_type_columns = [
        column
        for column in FEATURES
        if (
            not pd.api.types.is_numeric_dtype(frame[column].dtype)
            or pd.api.types.is_bool_dtype(frame[column].dtype)
            or pd.api.types.is_complex_dtype(frame[column].dtype)
        )
    ]
    if invalid_type_columns:
        raise ValueError(
            "Todas as features devem ter tipos numéricos reais. "
            f"Colunas inválidas: {invalid_type_columns}"
        )

    null_count = int(frame.isnull().sum().sum())
    if null_count != 0:
        raise ValueError(f"O dataset de treino contém {null_count} valores nulos.")

    infinite_count = int(np.isinf(frame.to_numpy(dtype=float)).sum())
    if infinite_count != 0:
        raise ValueError(
            f"O dataset de treino contém {infinite_count} valores infinitos."
        )


def main():
    """Train and persist the Invoice anomaly model from the TRAIN features."""
    print("=" * 70)
    print("TREINAMENTO MODELO")
    print("=" * 70)

    if not TRAIN_DATA_PATH.exists():
        raise FileNotFoundError(f"Dataset de treino não encontrado: {TRAIN_DATA_PATH}")

    # A leitura seletiva impede que labels e campos de avaliação sejam
    # carregados ou utilizados durante o treinamento.
    train_features = pd.read_parquet(
        TRAIN_DATA_PATH,
        columns=FEATURES,
    )
    validate_training_features(train_features)

    record_count = len(train_features)
    feature_count = len(train_features.columns)
    null_count = int(train_features.isnull().sum().sum())
    infinite_count = int(np.isinf(train_features.to_numpy()).sum())

    print("\nDataset:")
    print(f"Quantidade de registros: {record_count:,}")
    print(f"Quantidade de features: {feature_count}")
    print(f"Valores nulos: {null_count}")
    print(f"Valores infinitos: {infinite_count}")

    print("\nModelo:")
    print("Isolation Forest")
    print("Árvores: 200")
    print("Contamination: 0.22")
    print("Random state: 42")

    model = IsolationForest(
        n_estimators=200,
        contamination=0.22,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(train_features)

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_PATH)

    metadata = {
        "model_name": "Detector Inteligente de Anomalias em Compras",
        "algorithm": "IsolationForest",
        "n_estimators": 200,
        "contamination": 0.22,
        "random_state": 42,
        "feature_count": feature_count,
        "features": FEATURES,
        "training_date": datetime.now().astimezone().isoformat(timespec="seconds"),
    }

    with METADATA_PATH.open("w", encoding="utf-8") as metadata_file:
        json.dump(
            metadata,
            metadata_file,
            ensure_ascii=False,
            indent=2,
        )
        metadata_file.write("\n")

    print("\nTreinamento concluído.")
    print("\nModelo salvo em:")
    print(MODEL_PATH)
    print("\nMetadados salvos em:")
    print(METADATA_PATH)
    print("=" * 70)


if __name__ == "__main__":
    main()
