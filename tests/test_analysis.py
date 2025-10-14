from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from pylinac_bulkcbct import analysis
from pylinac_bulkcbct.analysis import (
    PhantomNotAvailableError,
    PylinacNotInstalledError,
    run_catphan_analysis,
)
from pylinac_bulkcbct.inventory import StudyInventory, StudyRecord


def _build_inventory(tmp_path: Path) -> StudyInventory:
    record = StudyRecord(
        path=tmp_path,
        relative_path=Path("study"),
        file_count=3,
        extensions={".dcm"},
    )
    return StudyInventory(root=tmp_path, generated_at=datetime.now(UTC), studies=[record])


def test_run_catphan_analysis_success(monkeypatch, tmp_path: Path):
    inventory = _build_inventory(tmp_path)

    class FakeCatphan:
        def __init__(self, directory: str):
            self.directory = directory
            self._results_data = {"value": 1, "timestamp": datetime.now(UTC)}

        def analyze(self) -> None:
            return None

        def results(self) -> str:
            return "Analysis completed"

        def results_data(self) -> dict:
            return self._results_data

    monkeypatch.setattr(analysis, "_load_catphan_class", lambda name: FakeCatphan)

    batch = run_catphan_analysis(inventory, "CatPhan503")

    assert batch.phantom == "CatPhan503"
    assert batch.success_count == 1
    assert batch.failure_count == 0
    result = batch.results[0]
    assert result.success is True
    assert result.summary == "Analysis completed"
    assert isinstance(result.metrics["timestamp"], str)


def test_run_catphan_analysis_failure(monkeypatch, tmp_path: Path):
    inventory = _build_inventory(tmp_path)

    class FailingCatphan:
        def __init__(self, directory: str):
            raise RuntimeError("boom")

    monkeypatch.setattr(analysis, "_load_catphan_class", lambda name: FailingCatphan)

    batch = run_catphan_analysis(inventory, "CatPhan503")

    assert batch.success_count == 0
    assert batch.failure_count == 1
    assert batch.results[0].success is False
    assert "boom" in batch.results[0].error


def test_run_catphan_analysis_uses_from_dir_when_available(monkeypatch, tmp_path: Path):
    inventory = _build_inventory(tmp_path)

    class FactoryCatphan:
        def __init__(self, directory: str):
            raise AssertionError("__init__ should not be called when from_dir exists")

        @classmethod
        def from_dir(cls, directory: str):
            class Instance:
                def analyze(self) -> None:
                    return None

                def results(self) -> str:
                    return "factory"

                def results_data(self) -> dict:
                    return {"value": 2}

            return Instance()

    monkeypatch.setattr(analysis, "_load_catphan_class", lambda name: FactoryCatphan)

    batch = run_catphan_analysis(inventory, "CatPhan503")

    assert batch.success_count == 1
    assert batch.results[0].summary == "factory"


def test_load_catphan_class_without_pylinac(monkeypatch):
    def fake_import(name: str):
        raise ModuleNotFoundError("pylinac")

    monkeypatch.setattr(analysis, "import_module", fake_import)

    with pytest.raises(PylinacNotInstalledError):
        analysis._load_catphan_class("CatPhan503")


def test_load_catphan_class_missing_phantom(monkeypatch):
    class DummyModule:
        pass

    monkeypatch.setattr(analysis, "import_module", lambda name: DummyModule())

    with pytest.raises(PhantomNotAvailableError):
        analysis._load_catphan_class("CatPhan999")

