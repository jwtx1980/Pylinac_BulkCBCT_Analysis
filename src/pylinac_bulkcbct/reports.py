"""Helpers for exporting CBCT analysis reports."""
from __future__ import annotations

from pathlib import Path
from typing import Protocol


class _CBCTProtocol(Protocol):
    """Protocol describing the subset of the CBCT API we depend on."""

    def publish_pdf(self, filename: str) -> None:  # pragma: no cover - typing only
        """Write a PDF report for the analysis to ``filename``."""


def publish_cbct_pdf(
    cbct: _CBCTProtocol,
    xml_result_path: Path | str,
    *,
    pdf_filename: str | None = None,
) -> Path:
    """Export the CBCT PDF report alongside the XML output.

    Parameters
    ----------
    cbct:
        Analysed CBCT object offering a :py:meth:`publish_pdf` method.
    xml_result_path:
        Path to the XML file that summarises the scan results.
    pdf_filename:
        Optional filename for the generated PDF. Defaults to ``<xml stem>.pdf``.

    Returns
    -------
    Path
        The filesystem path to the written PDF report.
    """

    xml_path = Path(xml_result_path)
    report_dir = xml_path.parent / xml_path.stem
    report_dir.mkdir(parents=True, exist_ok=True)

    if pdf_filename is None:
        pdf_filename = f"{xml_path.stem}.pdf"

    pdf_path = report_dir / pdf_filename
    cbct.publish_pdf(str(pdf_path))
    return pdf_path


__all__ = ["publish_cbct_pdf"]
