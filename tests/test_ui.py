from __future__ import annotations

from pathlib import Path

import pytest

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


def test_invalid_root_shows_error(client):
    response = client.post(
        "/",
        data={
            "root": "/path/does/not/exist",
            "extensions": ".dcm",
            "phantom": "CatPhan503",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"does not exist" in response.data


def test_successful_scan_renders_results(tmp_path: Path, client, monkeypatch):
    study = tmp_path / "study1"
    study.mkdir()
    (study / "image1.dcm").write_bytes(b"data")
    (study / "image2.dcm").write_bytes(b"data")

    def fake_analysis(inventory, phantom):
        assert phantom == "CatPhan503"
        assert len(inventory.studies) == 1
        study_record = inventory.studies[0]

        class DummyResult:
            def __init__(self, study_record):
                self.study = study_record
                self.success = True
                self.summary = "All metrics within tolerance."
                self.error = None

        class DummyBatch:
            def __init__(self):
                from datetime import UTC, datetime

                self.phantom = phantom
                self.results = [DummyResult(study_record)]
                self.generated_at = datetime.now(UTC)

            @property
            def success_count(self):
                return 1

            @property
            def failure_count(self):
                return 0

        return DummyBatch()

    monkeypatch.setattr("pylinac_bulkcbct.ui.run_catphan_analysis", fake_analysis)

    response = client.post(
        "/",
        data={"root": str(tmp_path), "extensions": ".dcm", "phantom": "CatPhan503"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Scan completed successfully" in response.data
    assert b"study1" in response.data
    assert b"Pylinac analysis" in response.data
    assert b"status-pill success" in response.data


def test_analysis_error_is_reported(tmp_path: Path, client, monkeypatch):
    study = tmp_path / "study1"
    study.mkdir()
    (study / "image1.dcm").write_bytes(b"data")

    def failing_analysis(*args, **kwargs):
        raise RuntimeError("pylinac exploded")

    monkeypatch.setattr("pylinac_bulkcbct.ui.run_catphan_analysis", failing_analysis)

    response = client.post(
        "/",
        data={"root": str(tmp_path), "extensions": ".dcm", "phantom": "CatPhan503"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Failed to run Pylinac analysis" in response.data
