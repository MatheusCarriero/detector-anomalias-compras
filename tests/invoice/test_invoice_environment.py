"""Dependency bindings must fail closed before any real input access."""

from importlib.metadata import PackageNotFoundError

import pytest
import test_invoice_authorization as shared

from ml.scripts import invoice_final_evaluation as executor

documents = shared.documents
no_input_access = shared.no_input_access
pytestmark = pytest.mark.usefixtures("no_input_access")

DESCRIPTORS = ("requirements.txt", "requirements-dev.txt", ".python-version")
PINNED = {
    "python": "3.14.3", "pandas": "2.3.3", "numpy": "2.5.2", "pyarrow": "25.0.1",
    "scikit-learn": "1.9.0", "joblib": "1.6.0", "openpyxl": "3.1.5",
    "python-dateutil": "2.9.0.post0", "pytz": "2026.2", "tzdata": "2025.3",
    "six": "1.17.0", "et-xmlfile": "2.0.0", "scipy": "1.18.1",
    "threadpoolctl": "3.6.0", "narwhals": "2.21.2", "cloudpickle": "3.1.2",
    "pytest": "9.1.1", "ruff": "0.16.5", "colorama": "0.4.6", "iniconfig": "2.3.0",
    "packaging": "26.0", "pluggy": "1.6.0", "pygments": "2.20.0",
}


def test_every_active_pinned_distribution_is_recorded():
    assert executor._versions() == PINNED


@pytest.mark.parametrize("descriptor", DESCRIPTORS)
@pytest.mark.parametrize("change", ["missing", "digest"])
def test_dependency_descriptor_binding_required_before_claim(documents, descriptor, change):
    sources = documents[0]["source_sha256"]
    if change == "missing":
        sources.pop(descriptor, None)
    else:
        sources[descriptor] = "0" * 64
    pins = shared.seal(documents)
    with pytest.raises(ValueError):
        shared.claim(documents, pins)
    shared.assert_unclaimed(documents)


def test_legacy_portable_environment_contract_cannot_claim(documents):
    documents[0]["schema"] = "invoice-portable-freeze/1.0"
    pins = shared.seal(documents)
    with pytest.raises(ValueError):
        shared.claim(documents, pins)
    shared.assert_unclaimed(documents)


@pytest.mark.parametrize("distribution", [name for name in PINNED if name != "python"])
def test_repinned_installed_version_must_still_match_requirement(documents, monkeypatch, distribution):
    installed_version = executor.version
    monkeypatch.setattr(executor, "version", lambda name: "0.0.0" if name == distribution
                        else installed_version(name))
    documents[0]["versions"][distribution] = "0.0.0"
    pins = shared.seal(documents)
    with pytest.raises(ValueError, match="Ambiente|dependencia|versao"):
        shared.claim(documents, pins)
    shared.assert_unclaimed(documents)


@pytest.mark.parametrize("distribution", ["scipy", "openpyxl", "pytest", "ruff"])
def test_missing_pinned_distribution_rejects_before_claim(documents, monkeypatch, distribution):
    installed_version = executor.version

    def installed(name):
        if name == distribution:
            raise PackageNotFoundError(name)
        return installed_version(name)

    monkeypatch.setattr(executor, "version", installed)
    pins = shared.seal(documents)
    with pytest.raises(ValueError, match="Ambiente|dependencia|versao"):
        shared.claim(documents, pins)
    shared.assert_unclaimed(documents)


def test_repinned_python_version_must_match_python_descriptor(documents, monkeypatch):
    monkeypatch.setattr(executor.platform, "python_version", lambda: "0.0.0")
    documents[0]["versions"]["python"] = "0.0.0"
    pins = shared.seal(documents)
    with pytest.raises(ValueError, match="Ambiente|dependencia|versao"):
        shared.claim(documents, pins)
    shared.assert_unclaimed(documents)


@pytest.mark.parametrize("descriptor", DESCRIPTORS)
def test_dependency_file_bytes_are_checked_before_environment_interpretation(
        documents, tmp_path, monkeypatch, descriptor):
    root = tmp_path / "descriptor-project"
    root.mkdir()
    hashes = {}
    for name in DESCRIPTORS:
        path = root / name
        path.write_bytes((executor.PROJECT_ROOT / name).read_bytes())
        hashes[name] = executor.sha256(path)
    (root / descriptor).write_bytes(b"invalid dependency descriptor\n")
    freeze = {"source_sha256": hashes, "versions": documents[0]["versions"]}
    monkeypatch.setattr(executor, "PROJECT_ROOT", root)
    with pytest.raises(ValueError, match="Codigo/protocolo"):
        executor._check_sources(freeze)


@pytest.mark.parametrize("line", [
    "joblib>=1.6.0", "joblib==1.*", "joblib @ https://example.invalid/joblib.whl",
    "joblib[extra]==1.6.0", "joblib==1.6.0\njoblib==1.6.0", "-r other.txt",
])
def test_nonexact_or_ambiguous_requirement_contract_is_rejected(tmp_path, monkeypatch, line):
    (tmp_path / "requirements.txt").write_text(line + "\n", encoding="utf-8")
    (tmp_path / "requirements-dev.txt").write_text("-r requirements.txt\n", encoding="utf-8")
    (tmp_path / ".python-version").write_text("3.14.3\n", encoding="utf-8")
    monkeypatch.setattr(executor, "PROJECT_ROOT", tmp_path)
    with pytest.raises(ValueError):
        executor._versions()


def test_inactive_platform_pin_does_not_require_an_installed_distribution(tmp_path, monkeypatch):
    (tmp_path / "requirements.txt").write_text("joblib==1.6.0\n", encoding="utf-8")
    (tmp_path / "requirements-dev.txt").write_text(
        '-r requirements.txt\nabsent-example==1.0; sys_platform == "never-active"\n',
        encoding="utf-8",
    )
    (tmp_path / ".python-version").write_text("3.14.3\n", encoding="utf-8")
    monkeypatch.setattr(executor, "PROJECT_ROOT", tmp_path)
    assert executor._versions() == {"python": "3.14.3", "joblib": "1.6.0"}
