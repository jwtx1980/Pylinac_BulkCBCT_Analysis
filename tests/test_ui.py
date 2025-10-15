from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

pytest.importorskip("flask")

from pylinac_bulkcbct.analysis import BatchAnalysis, StudyAnalysisResult
from pylinac_bulkcbct.inventory import StudyInventory, StudyRecord
from pylinac_bulkcbct.ui import create_app


@pytest.fixture()
def app():
    app = create_app()
    app.config.update(TESTING=True)
    yield app


@pytest.fixture()
def client(app):
    return app.test_client()


def test_index_page_loads(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"CBCT Inventory Scanner" in response.data
    assert b"Catphan 503" in response.data
    assert b"Pull CBCTs" in response.data
    assert b"Run Catphan Analysis" in response.data


def test_invalid_root_shows_error(client):
    response = client.post(
        "/",
        data={
            "root": "/path/does/not/exist",
            "extensions": ".dcm",
            "phantom": "CatPhan503",
            "action": "inventory",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"does not exist" in response.data


def test_successful_scan_without_analysis(tmp_path: Path, client, monkeypatch):
    study = tmp_path / "study1"
    study.mkdir()
    (study / "image1.dcm").write_bytes(b"data")
    (study / "image2.dcm").write_bytes(b"data")

    def fail_if_called(*args, **kwargs):  # pragma: no cover - defensive helper
        raise AssertionError("Analysis should not run during inventory-only scans")

    monkeypatch.setattr("pylinac_bulkcbct.ui.run_catphan_analysis", fail_if_called)

    response = client.post(
        "/",
        data={
            "root": str(tmp_path),
            "extensions": ".dcm",
            "phantom": "CatPhan503",
            "action": "inventory",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Scan completed successfully" in response.data
    assert b"study1" in response.data
    assert b"Pylinac analysis" not in response.data


def test_analysis_runs_when_requested(tmp_path: Path, client, monkeypatch):
    study = tmp_path / "study1"
    study.mkdir()
    (study / "image1.dcm").write_bytes(b"data")
    (study / "image2.dcm").write_bytes(b"data")

    def fake_analysis(inventory, phantom):
        assert phantom == "CatPhan503"
        assert len(inventory.studies) == 1
        study_record = inventory.studies[0]

        result = StudyAnalysisResult(
            study=study_record,
            success=True,
            summary="All metrics within tolerance.",
            metrics={"value": 1},
        )
        return BatchAnalysis(
            phantom=phantom,
            generated_at=datetime.now(UTC),
            results=[result],
        )

    monkeypatch.setattr("pylinac_bulkcbct.ui.run_catphan_analysis", fake_analysis)

    response = client.post(
        "/",
        data={
            "root": str(tmp_path),
            "extensions": ".dcm",
            "phantom": "CatPhan503",
            "action": "analyze",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Scan completed successfully" in response.data
    assert b"Pylinac analysis" in response.data
    assert b"status-pill success" in response.data
    assert b"Export pass results to XML" in response.data


def test_analysis_error_is_reported(tmp_path: Path, client, monkeypatch):
    study = tmp_path / "study1"
    study.mkdir()
    (study / "image1.dcm").write_bytes(b"data")

    def failing_analysis(*args, **kwargs):
        raise RuntimeError("pylinac exploded")

    monkeypatch.setattr("pylinac_bulkcbct.ui.run_catphan_analysis", failing_analysis)

    response = client.post(
        "/",
        data={
            "root": str(tmp_path),
            "extensions": ".dcm",
            "phantom": "CatPhan503",
            "action": "analyze",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Failed to run Pylinac analysis" in response.data


def test_export_pass_results(tmp_path: Path, client, monkeypatch):
    study_success = StudyRecord(
        path=tmp_path / "study_success",
        relative_path=Path("study_success"),
        file_count=1,
        extensions={".dcm"},
    )
    study_failure = StudyRecord(
        path=tmp_path / "study_failure",
        relative_path=Path("study_failure"),
        file_count=1,
        extensions={".dcm"},
    )
    inventory = StudyInventory(
        root=tmp_path,
        generated_at=datetime.now(UTC),
        studies=[study_success, study_failure],
    )
    success_result = StudyAnalysisResult(
        study=study_success,
        success=True,
        summary="ok",
        metrics={"value": 1},
    )
    failure_result = StudyAnalysisResult(
        study=study_failure,
        success=False,
        error="boom",
    )
    batch = BatchAnalysis(
        phantom="CatPhan503",
        generated_at=inventory.generated_at,
        results=[success_result, failure_result],
    )

    inventory_payload = inventory.to_json(indent=None)
    analysis_payload = json.dumps(batch.to_dict(), separators=(",", ":"))

    captured = {}

    def fake_export(result_batch, destination):
        captured["batch"] = result_batch
        captured["destination"] = destination
        return (1, 0)

    monkeypatch.setattr(
        "pylinac_bulkcbct.ui.export_pass_results_to_xml", fake_export
    )

    response = client.post(
        "/",
        data={
            "root": str(tmp_path),
            "extensions": ".dcm",
            "phantom": "CatPhan503",
            "action": "export",
            "inventory_payload": inventory_payload,
            "analysis_payload": analysis_payload,
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Exported 1 successful analyses" in response.data
    assert b"status-pill success" not in response.data
    assert b"status-pill failure" in response.data
    assert captured["destination"].name == "catphan_results.xml"
    assert captured["batch"].success_count == 1


def test_export_without_analysis_shows_error(client):
    response = client.post(
        "/",
        data={
            "root": "/tmp",
            "extensions": ".dcm",
            "phantom": "CatPhan503",
            "action": "export",
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Run a Catphan analysis before exporting" in response.data
