"""Tests for report export helpers."""
from __future__ import annotations

from pathlib import Path

from pylinac_bulkcbct.reports import publish_cbct_pdf


class DummyCBCT:
    """Simple stand-in for a Pylinac CBCT object."""

    def __init__(self) -> None:
        self.published_to: str | None = None

    def publish_pdf(self, filename: str) -> None:
        self.published_to = filename
        Path(filename).write_text("dummy pdf content")


def test_publish_cbct_pdf_creates_directory_and_writes_pdf(tmp_path):
    xml_path = tmp_path / "results" / "scan.xml"
    xml_path.parent.mkdir()
    cbct = DummyCBCT()

    pdf_path = publish_cbct_pdf(cbct, xml_path, pdf_filename="mycbct.pdf")

    expected_dir = xml_path.parent / "scan"
    assert pdf_path == expected_dir / "mycbct.pdf"
    assert expected_dir.is_dir()
    assert pdf_path.read_text() == "dummy pdf content"
    assert cbct.published_to == str(pdf_path)


def test_publish_cbct_pdf_default_filename(tmp_path):
    xml_path = tmp_path / "output.xml"
    cbct = DummyCBCT()

    pdf_path = publish_cbct_pdf(cbct, xml_path)

    assert pdf_path.name == "output.pdf"
    assert pdf_path.parent == tmp_path / "output"
