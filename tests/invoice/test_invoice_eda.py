"""Synthetic checks of the Invoice EDA cells; no project dataset is required."""

import hashlib
import io
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ml.scripts.treinar_modelo import FEATURES

NOTEBOOK = Path(__file__).resolve().parents[2] / "ml/notebooks/01_invoice_eda.ipynb"


def notebook_functions():
    assert NOTEBOOK.exists(), "O notebook EDA ainda não foi implementado."
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    cells = [
        cell for cell in notebook["cells"]
        if "eda-functions" in cell["metadata"].get("tags", [])
    ]
    assert len(cells) == 1
    scope = {"pd": pd, "np": np, "Path": Path, "hashlib": hashlib, "io": io,
             "FEATURES": FEATURES}
    # Executa apenas a célula local de funções, sem I/O na sua definição.
    exec(compile("".join(cells[0]["source"]), str(NOTEBOOK), "exec"), scope)  # noqa: S102
    return scope


@pytest.fixture
def frame():
    result = pd.DataFrame({name: [0.0, 1.0, 2.0, 3.0] for name in FEATURES})
    result.insert(0, "fraud_type", ["NONE", "NONE", "INFLATED", "INFLATED"])
    result.insert(0, "is_fraud", [0, 0, 1, 1])
    result.insert(0, "split", "train")
    result.insert(0, "invoice_id", ["a", "b", "c", "d"])
    return result


def write_train(tmp_path, frame):
    path = tmp_path / "data/processed/train_features.parquet"
    path.parent.mkdir(parents=True)
    frame.to_parquet(path, index=False)
    return path


def test_train_loader_returns_exact_features_without_mutation(tmp_path, frame):
    path = write_train(tmp_path, frame)
    raw = path.read_bytes()
    loaded, digest = notebook_functions()["load_train"](tmp_path)
    pd.testing.assert_frame_equal(loaded, frame)
    assert digest == hashlib.sha256(raw).hexdigest()
    assert path.read_bytes() == raw


@pytest.mark.parametrize("split", ["validation", "test", None, "TRAIN"])
def test_loader_rejects_non_train_rows(tmp_path, frame, split):
    frame.loc[1, "split"] = split
    write_train(tmp_path, frame)
    with pytest.raises(ValueError, match="TRAIN"):
        notebook_functions()["load_train"](tmp_path)


@pytest.mark.parametrize("problem", ["duplicate_id", "null_id", "empty_id",
    "missing_feature", "extra_column", "feature_order", "bad_target",
    "null_target", "string_feature", "infinite", "empty"])
def test_loader_rejects_invalid_contract(tmp_path, frame, problem):
    if problem == "duplicate_id":
        frame.loc[1, "invoice_id"] = "a"
    elif problem == "null_id":
        frame.loc[1, "invoice_id"] = None
    elif problem == "empty_id":
        frame.loc[1, "invoice_id"] = " "
    elif problem == "missing_feature":
        frame = frame.drop(columns=FEATURES[0])
    elif problem == "extra_column":
        frame["unexpected"] = 1
    elif problem == "feature_order":
        frame = frame[list(frame.columns[:4]) + FEATURES[::-1]]
    elif problem == "bad_target":
        frame.loc[1, "is_fraud"] = 2
    elif problem == "null_target":
        frame.loc[1, "is_fraud"] = np.nan
    elif problem == "string_feature":
        frame[FEATURES[0]] = "bad"
    elif problem == "infinite":
        frame.loc[1, FEATURES[0]] = np.inf
    else:
        frame = frame.iloc[:0]
    write_train(tmp_path, frame)
    with pytest.raises(ValueError):
        notebook_functions()["load_train"](tmp_path)


def test_loader_preserves_missing_features_for_audit(tmp_path, frame):
    frame.loc[1, FEATURES[0]] = np.nan
    write_train(tmp_path, frame)
    loaded, _ = notebook_functions()["load_train"](tmp_path)
    assert pd.isna(loaded.loc[1, FEATURES[0]])


def test_loader_does_not_fallback_to_other_splits(tmp_path, monkeypatch):
    def forbidden_read(*args, **kwargs):
        pytest.fail("Não pode buscar outro Parquet se TRAIN estiver ausente.")

    monkeypatch.setattr(pd, "read_parquet", forbidden_read)
    with pytest.raises(FileNotFoundError):
        notebook_functions()["load_train"](tmp_path)


def test_loader_rejects_redirect_before_open(tmp_path, frame, monkeypatch):
    path = write_train(tmp_path, frame)
    original_resolve = Path.resolve
    original_read = Path.read_bytes

    def redirected(self, *args, **kwargs):
        if self == path:
            return tmp_path / "data/raw/shared.parquet"
        return original_resolve(self, *args, **kwargs)

    def guarded_read(self, *args, **kwargs):
        if self.suffix == ".parquet":
            pytest.fail("Redirecionamento deve falhar antes da leitura.")
        return original_read(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", redirected)
    monkeypatch.setattr(Path, "read_bytes", guarded_read)
    with pytest.raises(ValueError, match="redirecion"):
        notebook_functions()["load_train"](tmp_path)


def test_descriptive_statistics_include_missing_zeros_and_do_not_mutate():
    frame = pd.DataFrame({"x": [0.0, 2.0, 4.0, np.nan], "constant": [1.0]*4})
    before = frame.copy(deep=True)
    result = notebook_functions()["describe_numeric"](frame)
    assert result.loc["x", "count"] == 3
    assert result.loc["x", "mean"] == 2
    assert result.loc["x", "median"] == 2
    assert result.loc["x", "std"] == 2
    assert result.loc["x", "Q1"] == 1
    assert result.loc["x", "Q3"] == 3
    assert result.loc["x", "null_count"] == 1
    assert result.loc["x", "null_percent"] == 25
    assert result.loc["x", "zero_count"] == 1
    pd.testing.assert_frame_equal(frame, before)


def test_target_correlations_signed_sorted_and_constant_undefined():
    x = pd.DataFrame({"inverse": [1, 1, 0, 0], "weak": [0, 1, 0, 1],
                      "positive": [0, 0, 1, 1], "constant": [1]*4})
    y = pd.Series([0, 0, 1, 1], name="is_fraud")
    result = notebook_functions()["target_correlations"](x, y)
    assert result.loc["inverse", "pearson"] == pytest.approx(-1)
    assert result.loc["positive", "spearman"] == pytest.approx(1)
    assert result.loc["weak", "pearson"] == pytest.approx(0)
    assert pd.isna(result.loc["constant", "pearson"])
    assert result.index[-1] == "constant"
    assert result["pearson"].dropna().abs().is_monotonic_decreasing


def test_correlation_rejects_misaligned_target():
    x = pd.DataFrame({"x": [0, 1, 2, 3]})
    y = pd.Series([0, 0, 1, 1], index=[3, 2, 1, 0])
    with pytest.raises(ValueError, match="alinh"):
        notebook_functions()["target_correlations"](x, y)


def test_correlation_pairs_exclude_diagonal_and_symmetric_duplicates():
    matrix = pd.DataFrame([[1, -.9, .1], [-.9, 1, .4], [.1, .4, 1]],
                          index=list("abc"), columns=list("abc"))
    result = notebook_functions()["correlation_pairs"](matrix)
    assert len(result) == 3
    assert result.iloc[0]["feature_a"] == "a"
    assert result.iloc[0]["feature_b"] == "b"
    assert result.iloc[0]["correlation"] == -.9


def test_class_summary_has_only_selected_features(frame):
    result = notebook_functions()["compare_classes"](frame[FEATURES], frame.is_fraud)
    assert list(result.columns.get_level_values(0).unique()) == FEATURES
    assert result.loc[0, (FEATURES[0], "count")] == 2
    assert result.loc[1, (FEATURES[0], "mean")] == 2.5


@pytest.mark.parametrize("dtype", ["float64", "Float64"])
def test_statistics_cell_preserves_entirely_missing_feature(dtype):
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    cell = next(cell for cell in notebook["cells"] if cell["id"] == "eda-9")
    frame = pd.DataFrame({"missing": pd.Series([np.nan]*4, dtype=dtype),
                          "present": [0.0, 1.0, 1.0, 2.0]})
    scope = notebook_functions()
    scope.update({"features_train": frame, "FEATURES": list(frame.columns),
                  "display": lambda value: None})
    # Executa somente estatísticas descritivas sobre uma fixture em memória.
    exec(compile("".join(cell["source"]), str(NOTEBOOK), "exec"), scope)  # noqa: S102
    assert scope["estatisticas_features"].loc["missing", "null_percent"] == 100
    assert pd.isna(scope["resumo_distribuicoes"].loc["missing", "frequencia_valor_mais_comum_percent"])
    assert scope["resumo_distribuicoes"].loc["present", "frequencia_valor_mais_comum_percent"] == 50
