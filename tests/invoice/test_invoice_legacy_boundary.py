"""Historical raw-reading routes must fail closed on the real checkout."""

from pathlib import Path

import pytest

from ml.scripts import avaliar_invoice as evaluation
from ml.scripts import comparar_triagem_invoice as comparison
from ml.scripts import diagnosticar_triagem_invoice as triage
from ml.scripts import preparar_revisao_cega_invoice as blind

ROOT = Path(__file__).resolve().parents[2]


def forbidden(*args, **kwargs):
    raise AssertionError("Boundary must reject before input reads, hashes or inference")


@pytest.mark.parametrize("api", [evaluation, triage, comparison, blind])
@pytest.mark.parametrize("root", [ROOT, ROOT / "data"])
def test_historical_runner_rejects_checkout_even_with_fresh_output(api, root, tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(evaluation.pd, "read_parquet", forbidden)
    monkeypatch.setattr(evaluation, "sha256", forbidden)
    monkeypatch.setattr(triage, "sha256", forbidden)
    with pytest.raises(PermissionError):
        api.run(root=root, output=tmp_path / "never-created.json")
    assert not (tmp_path / "never-created.json").exists()


@pytest.mark.parametrize("loader,args", [
    (evaluation.load_validation, ()), (triage._load_frames, ()),
    (comparison._source_amounts, (None,)), (blind._load_validation, ()),
    (blind._context, (None, [])),
])
def test_direct_historical_loader_cannot_bypass_real_boundary(loader, args, monkeypatch):
    monkeypatch.setattr(Path, "open", forbidden)
    monkeypatch.setattr(evaluation.pd, "read_parquet", forbidden)
    with pytest.raises(PermissionError):
        loader(ROOT, *args)


def test_external_fixture_root_is_preserved_without_reading_inputs(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "open", forbidden)
    assert evaluation.require_external_invoice_fixture(tmp_path) == tmp_path.resolve()


def test_checkout_alias_is_rejected_before_input_inspection(tmp_path, monkeypatch):
    original = Path.resolve

    def redirected(path, *args, **kwargs):
        if path == tmp_path:
            return ROOT
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", redirected)
    monkeypatch.setattr(Path, "open", forbidden)
    with pytest.raises(PermissionError):
        evaluation.require_external_invoice_fixture(tmp_path)


@pytest.mark.parametrize("name", [
    "data/raw/splits.parquet", "data/raw/labels.parquet", "data/raw/invoices.parquet",
    "data/processed/train_features.parquet", "data/processed/val_features.parquet",
    "ml/models/isolation_forest.joblib", "ml/models/model_metadata.json",
])
def test_external_root_cannot_redirect_a_protected_input(tmp_path, monkeypatch, name):
    original = Path.resolve

    def redirected(path, *args, **kwargs):
        if path == tmp_path / name:
            # Simulate the resolved destination, without stat/read of real data.
            return ROOT / name
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", redirected)
    monkeypatch.setattr(Path, "open", forbidden)
    with pytest.raises(PermissionError):
        evaluation.require_external_invoice_fixture(tmp_path)


def test_external_fixture_symlink_is_rejected_before_content_read(tmp_path, monkeypatch):
    fixture = tmp_path / "fixture"
    (fixture / "data/raw").mkdir(parents=True)
    target = tmp_path / "generated.txt"
    target.write_text("synthetic only", encoding="utf-8")
    try:
        (fixture / "data/raw/invoices.parquet").symlink_to(target)
    except OSError:
        pytest.skip("Windows requires symlink privileges")
    monkeypatch.setattr(Path, "open", forbidden)
    with pytest.raises(PermissionError):
        evaluation.require_external_invoice_fixture(fixture)
