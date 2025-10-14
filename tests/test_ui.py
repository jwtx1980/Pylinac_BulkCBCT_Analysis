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


def test_invalid_root_shows_error(client):
    response = client.post(
        "/",
        data={"root": "/path/does/not/exist", "extensions": ".dcm"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"does not exist" in response.data


def test_successful_scan_renders_results(tmp_path: Path, client, app):
    study = tmp_path / "study1"
    study.mkdir()
    (study / "image1.dcm").write_bytes(b"data")
    (study / "image2.dcm").write_bytes(b"data")

    response = client.post(
        "/",
        data={"root": str(tmp_path), "extensions": ".dcm"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Scan completed successfully" in response.data
    assert b"study1" in response.data
    assert app.config["LAST_INVENTORY_JSON"]
