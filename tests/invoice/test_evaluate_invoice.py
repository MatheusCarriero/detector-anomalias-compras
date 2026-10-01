import importlib.util
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.ensemble import IsolationForest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


@pytest.fixture
def api():
    path = ROOT / "ml/scripts/avaliar_invoice.py"
    assert path.exists(), "Avaliador Invoice ainda ausente"
    spec = importlib.util.spec_from_file_location("invoice_eval_tests", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def source(api, tmp_path):
    from ml.scripts.treinar_modelo import FEATURES
    train = pd.DataFrame(np.arange(8 * 19).reshape(8, 19) / 10, columns=FEATURES)
    val = train.iloc[:4].copy()
    for frame, prefix, split in ((train, "t", "train"), (val, "v", "val")):
        frame.insert(0, "fraud_type", ["normal", "normal", "amount", "amount"] * (len(frame)//4))
        frame.insert(0, "is_fraud", [0, 0, 1, 1] * (len(frame)//4))
        frame.insert(0, "split", split)
        frame.insert(0, "invoice_id", [f"{prefix}{i}" for i in range(len(frame))])
    raw = tmp_path / "data/raw"
    processed = tmp_path / "data/processed"
    models = tmp_path / "ml/models"
    for path in (raw, processed, models):
        path.mkdir(parents=True)
    train.to_parquet(processed / "train_features.parquet", index=False)
    val.to_parquet(processed / "val_features.parquet", index=False)
    pd.concat([train, val])[["invoice_id", "split"]].to_parquet(raw / "splits.parquet", index=False)
    val[["invoice_id", "is_fraud", "fraud_type"]].iloc[::-1].to_parquet(raw / "labels.parquet", index=False)
    model = IsolationForest(n_estimators=200, contamination=.22, random_state=42, n_jobs=-1).fit(train[FEATURES])
    joblib.dump(model, models / "isolation_forest.joblib")
    (models / "model_metadata.json").write_text(json.dumps({
        "algorithm":"IsolationForest", "n_estimators":200, "contamination":.22,
        "random_state":42, "feature_count":19, "features":FEATURES,
    }), encoding="utf-8")
    return tmp_path


def test_metrics_hand_checked(api):
    result = api.summarize([0,0,1,1], [0,1,0,1], [.1,.8,.4,.9])
    assert result["confusion_matrix"] == [[1,1],[1,1]]
    assert result["f1_macro"] == .5
    assert result["balanced_accuracy"] == .5
    assert result["roc_auc"] == .75
    assert result["average_precision"] == pytest.approx(5/6)


@pytest.mark.parametrize("split", ["test", "train", "validation", "../test"])
def test_forbidden_split_before_io(api, tmp_path, split):
    with pytest.raises(ValueError, match="val"):
        api.load_validation(tmp_path, split)


def test_source_order_is_not_alignment(api, source):
    frame = api.load_validation(source)
    assert frame["invoice_id"].tolist() == ["v0","v1","v2","v3"]


@pytest.mark.parametrize("fault", ["duplicate", "wrong_split", "bad_label", "null", "infinite", "text", "missing_id"])
def test_invalid_validation_rejected(api, source, fault):
    path = source / "data/processed/val_features.parquet"
    frame = pd.read_parquet(path)
    if fault == "duplicate":
        frame.loc[1, "invoice_id"] = frame.loc[0, "invoice_id"]
    elif fault == "wrong_split":
        frame.loc[0, "split"] = "test"
    elif fault == "bad_label":
        frame.loc[0, "is_fraud"] = 2
    elif fault == "missing_id":
        frame.loc[0, "invoice_id"] = None
    else:
        feature = api.FEATURES[0]
        if fault == "text":
            frame[feature] = "bad"
        frame.loc[0,feature] = {"null":np.nan,"infinite":np.inf,"text":"bad"}[fault]
    frame.to_parquet(path, index=False)
    with pytest.raises((ValueError, TypeError)):
        api.load_validation(source)


def test_label_tampering_rejected(api, source):
    path = source / "data/processed/val_features.parquet"
    frame = pd.read_parquet(path)
    frame.loc[0, "is_fraud"] = 1
    frame.to_parquet(path, index=False)
    with pytest.raises(ValueError, match="(?i)label"):
        api.load_validation(source)


def test_missing_supplier_group_and_score_direction(api):
    frame = pd.DataFrame(1.0,index=range(4),columns=api.FEATURES)
    frame["is_fraud"] = [0,0,1,1]
    frame["fraud_type"] = ["normal","normal","amount","amount"]

    class FixedScore:
        offset_ = -.5
        def score_samples(self, x):
            assert list(x.columns) == api.FEATURES
            return np.array([-.1,-.8,-.4,-.9])
        def decision_function(self, x):
            return self.score_samples(x) - self.offset_
        def predict(self, x):
            return np.array([1,-1,1,-1])

    result = api.evaluate_frame(FixedScore(),frame)
    assert result["model"]["average_precision"] == pytest.approx(5/6)
    assert result["by_fraud_type"]["amount"]["recall_fraud"] == .5
    assert result["by_supplier_seen"]["unseen"]["count"] == 0
    assert result["by_supplier_seen"]["unseen"]["recall_fraud"] is None
    assert result["baseline_no_alert"]["recall_1"] == 0


def test_end_to_end_without_real_data_and_without_refit(api, source, monkeypatch):
    def no_fit(*args, **kwargs):
        raise AssertionError("Não ajustar modelo durante avaliação")
    monkeypatch.setattr(IsolationForest,"fit",no_fit)
    out = source / "result.json"
    result = api.run(source, out)
    assert result["split"] == "val"
    assert result["rows"] == 4
    assert result["real_model_fits"] == 0
    assert json.loads(out.read_text(encoding="utf-8")) == result
    original = out.read_bytes()
    with pytest.raises(FileExistsError):
        api.run(source, out)
    assert out.read_bytes() == original


def test_wrong_model_rejected(api, source):
    joblib.dump({"not":"model"}, source / "ml/models/isolation_forest.joblib")
    with pytest.raises(TypeError, match="modelo"):
        api.run(source, source / "result.json")
    assert not (source / "result.json").exists()


def test_overlap_rejected_before_label_read(api, source):
    path = source / "data/processed/train_features.parquet"
    train = pd.read_parquet(path)
    train.loc[0, "invoice_id"] = "v0"
    train.to_parquet(path, index=False)
    with pytest.raises(ValueError, match="Overlap"):
        api.load_validation(source)


def test_official_split_coverage_required(api, source):
    path = source / "data/raw/splits.parquet"
    frame = pd.read_parquet(path)
    frame.iloc[:-1].to_parquet(path, index=False)
    with pytest.raises(ValueError, match="reconciliam"):
        api.load_validation(source)


def test_single_class_metrics_are_not_fabricated(api):
    result = api.summarize([0,0], [0,1], [.1,.8])
    assert result["roc_auc"] is None
    assert result["average_precision"] is None
    assert result["balanced_accuracy"] is None


def test_zero_decision_is_normal(api):
    frame = pd.DataFrame(1.0,index=range(2),columns=api.FEATURES)
    frame["is_fraud"] = [0,1]
    frame["fraud_type"] = [None,"amount"]
    class AtThreshold:
        offset_ = -.5
        def score_samples(self, x):
            return np.array([-.5,-.6])
        def decision_function(self, x):
            return np.array([0.,-.1])
        def predict(self, x):
            return np.array([1,-1])
    result = api.evaluate_frame(AtThreshold(),frame)
    assert result["model"]["confusion_matrix"] == [[1,0],[0,1]]
    assert result["by_fraud_type"]["__missing__"]["false_positive_rate"] == 0


def test_real_reader_never_loads_test_or_unfiltered_labels(api, source, monkeypatch):
    original = pd.read_parquet
    def guarded(path, **kwargs):
        assert Path(path).name not in ("test_features.parquet","X_test.parquet","y_test.parquet")
        if Path(path).name == "labels.parquet":
            assert kwargs["filters"] == [("invoice_id","in",["v0","v1","v2","v3"])]
        if Path(path).name == "splits.parquet":
            assert kwargs["filters"] == [("split","in",["train","val"])]
        return original(path, **kwargs)
    monkeypatch.setattr(pd, "read_parquet", guarded)
    assert len(api.load_validation(source)) == 4


def test_changed_model_parameter_rejected(api, source):
    path = source / "ml/models/isolation_forest.joblib"
    model = joblib.load(path)
    model.set_params(contamination=.1)
    joblib.dump(model,path)
    with pytest.raises(ValueError, match="Configuração"):
        api.run(source,source/"result.json")
    assert not (source/"result.json").exists()


def test_changed_input_during_scoring_not_published(api, source, monkeypatch):
    original = api.evaluate_frame
    def mutated(model, frame):
        result = original(model,frame)
        path = source / "ml/models/model_metadata.json"
        path.write_text("{}",encoding="utf-8")
        return result
    monkeypatch.setattr(api,"evaluate_frame",mutated)
    with pytest.raises(ValueError, match="Input alterado"):
        api.run(source, source/"result.json")
    assert not (source/"result.json").exists()
