"""Pylinac-based CBCT analysis helpers."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol, Sequence
from xml.etree import ElementTree as ET

from .inventory import StudyInventory, StudyRecord


class CatphanAnalysisError(RuntimeError):
    """Base error raised when Catphan analysis cannot be performed."""


class PylinacNotInstalledError(CatphanAnalysisError):
    """Raised when the pylinac package cannot be imported."""


class PhantomNotAvailableError(CatphanAnalysisError):
    """Raised when the requested Catphan phantom class is not present."""


def _load_catphan_class(phantom_name: str) -> type[CatphanLike]:
    """Return the pylinac Catphan class matching ``phantom_name``."""

    try:
        module = import_module("pylinac.ct")
    except ModuleNotFoundError as exc:  # pragma: no cover - requires pylinac runtime
        raise PylinacNotInstalledError(
            "The pylinac package is required to run Catphan analysis."
        ) from exc

    try:
        catphan_cls = getattr(module, phantom_name)
    except AttributeError as exc:  # pragma: no cover - defensive
        raise PhantomNotAvailableError(
            f"Catphan phantom '{phantom_name}' is not available in pylinac."
        ) from exc

    return catphan_cls


def _create_catphan_instance(
    catphan_cls: type[CatphanLike], study_path: Path | str
) -> CatphanLike:
    """Instantiate ``catphan_cls`` for ``study_path`` respecting ``from_dir``."""

    from_dir = getattr(catphan_cls, "from_dir", None)
    if callable(from_dir):
        return from_dir(str(study_path))
    return catphan_cls(str(study_path))


class CatphanLike(Protocol):
    """Protocol describing the pylinac Catphan API we rely on."""

    def analyze(self) -> None:
        ...

    def results(self) -> str:
        ...

    def results_data(self) -> dict[str, Any]:
        ...

    def publish_pdf(self, destination: str) -> None:
        ...


def _serialise_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    """Ensure ``metrics`` can be serialised by normalising non-JSON types."""

    return json.loads(json.dumps(metrics, default=str))


def _flatten_metrics(payload: Any, prefix: str = "") -> list[tuple[str, Any]]:
    """Return a flattened list of metric key/value pairs."""

    flattened: list[tuple[str, Any]] = []

    if isinstance(payload, Mapping):
        for key, value in payload.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            flattened.extend(_flatten_metrics(value, child_prefix))
    elif isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        for index, value in enumerate(payload):
            child_prefix = f"{prefix}[{index}]" if prefix else f"[{index}]"
            flattened.extend(_flatten_metrics(value, child_prefix))
    else:
        flattened.append((prefix, payload))

    return flattened


def _normalise_summary(summary: str) -> list[str]:
    """Collapse wrapped summary lines into a list of logical entries."""

    normalised = summary.replace("\r\n", "\n").replace("\r", "\n")
    raw_lines = [line.strip() for line in normalised.split("\n") if line.strip()]

    merged: list[str] = []
    buffer = ""

    for line in raw_lines:
        if buffer:
            buffer = f"{buffer} {line}"
        else:
            buffer = line

        if line.endswith(":") or line.endswith(","):
            continue

        merged.append(buffer.strip())
        buffer = ""

    if buffer:
        merged.append(buffer.strip())

    return merged


def _looks_like_value(token: str) -> bool:
    """Return ``True`` if ``token`` resembles a scalar value."""

    cleaned = token.strip()
    if not cleaned:
        return False

    lowered = cleaned.lower()
    if lowered in {"true", "false", "yes", "no", "pass", "fail"}:
        return True

    try:
        float(cleaned.replace(",", ""))
    except ValueError:
        return False

    return True


def _emit_summary(summary_el: ET.Element, summary: str) -> None:
    """Populate ``summary_el`` with structured content from ``summary``."""

    for entry in _normalise_summary(summary):
        stripped = entry.strip()

        if stripped.startswith("-") and stripped.endswith("-") and stripped.strip("-").strip():
            section_text = stripped.strip("-").strip()
            section_el = ET.SubElement(summary_el, "Section")
            section_el.text = section_text
            continue

        key: str | None = None
        value: str | None = None

        if ":" in stripped:
            potential_key, potential_value = stripped.split(":", 1)
            key = potential_key.strip()
            value = potential_value.strip() or None
        else:
            pieces = stripped.rsplit(" ", 1)
            if len(pieces) == 2 and _looks_like_value(pieces[1]):
                potential_key, potential_value = pieces
                key = potential_key.strip()
                value = potential_value.strip() or None

        if key:
            item_el = ET.SubElement(summary_el, "Item", {"name": key})
            if value:
                item_el.text = value
        else:
            note_el = ET.SubElement(summary_el, "Note")
            note_el.text = stripped


@dataclass
class StudyAnalysisResult:
    """Outcome of running Catphan analysis against a single study."""

    study: StudyRecord
    success: bool
    summary: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "study": self.study.to_dict(),
            "success": self.success,
            "summary": self.summary,
            "metrics": self.metrics,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> StudyAnalysisResult:
        """Reconstruct a result from :meth:`to_dict` data."""

        metrics_payload = payload.get("metrics") or {}
        if not isinstance(metrics_payload, dict):
            metrics_payload = {}

        return cls(
            study=StudyRecord.from_dict(payload["study"]),
            success=bool(payload.get("success", False)),
            summary=payload.get("summary"),
            metrics=dict(metrics_payload),
            error=payload.get("error"),
        )


@dataclass
class BatchAnalysis:
    """Aggregated Catphan analysis output for an inventory run."""

    phantom: str
    generated_at: datetime
    results: list[StudyAnalysisResult] = field(default_factory=list)

    @property
    def success_count(self) -> int:
        return sum(1 for result in self.results if result.success)

    @property
    def failure_count(self) -> int:
        return sum(1 for result in self.results if not result.success)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phantom": self.phantom,
            "generated_at": self.generated_at.isoformat(),
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "results": [result.to_dict() for result in self.results],
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> BatchAnalysis:
        """Reconstruct a batch analysis from :meth:`to_dict` data."""

        return cls(
            phantom=str(payload["phantom"]),
            generated_at=datetime.fromisoformat(payload["generated_at"]),
            results=[
                StudyAnalysisResult.from_dict(result)
                for result in payload.get("results", [])
            ],
        )

    def successful_results(self) -> list[StudyAnalysisResult]:
        """Return all successfully analysed studies."""

        return [result for result in self.results if result.success]


def run_catphan_analysis(inventory: StudyInventory, phantom_name: str) -> BatchAnalysis:
    """Run pylinac Catphan analysis on each study within ``inventory``."""

    catphan_cls = _load_catphan_class(phantom_name)
    results: list[StudyAnalysisResult] = []

    for study in inventory.studies:
        try:
            phantom = _create_catphan_instance(catphan_cls, study.path)
            phantom.analyze()
            summary = phantom.results()
            metrics = _serialise_metrics(phantom.results_data())
            results.append(
                StudyAnalysisResult(
                    study=study,
                    success=True,
                    summary=summary,
                    metrics=metrics,
                )
            )
        except Exception as exc:  # pragma: no cover - exercised with real data
            results.append(
                StudyAnalysisResult(
                    study=study,
                    success=False,
                    error=str(exc),
                )
            )

    return BatchAnalysis(phantom=phantom_name, generated_at=datetime.now(UTC), results=results)


def _report_filename(study_id: str, phantom: str) -> str:
    """Return a filesystem-safe PDF filename for ``study_id`` and ``phantom``."""

    safe_study = re.sub(
        r"[^A-Za-z0-9_.-]+",
        "_",
        study_id.replace("\\", "_").replace("/", "_"),
    )
    safe_phantom = re.sub(r"[^A-Za-z0-9_.-]+", "_", phantom)
    safe_study = safe_study.strip("_") or "study"
    safe_phantom = safe_phantom.strip("_") or "catphan"
    return f"{safe_study}_{safe_phantom}.pdf"


def export_pass_results_to_xml(batch: BatchAnalysis, destination: Path) -> tuple[int, int]:
    """Append successful study analyses from ``batch`` to an XML file.

    Parameters
    ----------
    batch:
        The batch analysis containing results to export.
    destination:
        The XML file that should be created or appended to.

    Returns
    -------
    tuple[int, int]
        A tuple containing the number of exported studies and the number of
        successes skipped because they already existed in the file.
    """

    successes = batch.successful_results()
    if not successes:
        return (0, 0)

    destination = destination.expanduser().resolve()
    reports_dir = destination.parent / f"{destination.stem}_reports"

    catphan_cls = _load_catphan_class(batch.phantom)

    if destination.exists():
        tree = ET.parse(destination)
        root = tree.getroot()
    else:
        root = ET.Element("CBCTAnalysisResults")
        tree = ET.ElementTree(root)

    existing_keys = {
        (element.get("id"), element.get("phantom"))
        for element in root.findall("Study")
    }

    exported = 0
    skipped = 0

    for result in successes:
        study_id = str(result.study.relative_path)
        key = (study_id, batch.phantom)
        if key in existing_keys:
            skipped += 1
            continue

        study_el = ET.SubElement(
            root,
            "Study",
            {
                "id": study_id,
                "phantom": batch.phantom,
                "exported_at": datetime.now(UTC).isoformat(),
            },
        )
        ET.SubElement(study_el, "AbsolutePath").text = str(result.study.path)

        report_path: Path | None = None
        try:
            phantom = _create_catphan_instance(catphan_cls, result.study.path)
            phantom.analyze()
            reports_dir.mkdir(parents=True, exist_ok=True)
            report_path = reports_dir / _report_filename(study_id, batch.phantom)
            phantom.publish_pdf(str(report_path))
        except Exception:
            report_path = None

        if report_path is not None:
            ET.SubElement(study_el, "Report").text = str(report_path)

        if result.summary:
            summary_el = ET.SubElement(study_el, "Summary")
            _emit_summary(summary_el, result.summary)

        flattened_metrics = _flatten_metrics(result.metrics)
        if flattened_metrics:
            metrics_el = ET.SubElement(study_el, "Metrics")
            for metric_key, metric_value in flattened_metrics:
                attrs = {"name": metric_key} if metric_key else {}
                metric_el = ET.SubElement(metrics_el, "Metric", attrs)
                if metric_value is not None:
                    metric_el.text = str(metric_value)

        existing_keys.add(key)
        exported += 1

    if exported:
        destination.parent.mkdir(parents=True, exist_ok=True)
        tree.write(destination, encoding="utf-8", xml_declaration=True)

    return (exported, skipped)


__all__: Iterable[str] = [
    "BatchAnalysis",
    "CatphanAnalysisError",
    "PhantomNotAvailableError",
    "PylinacNotInstalledError",
    "StudyAnalysisResult",
    "export_pass_results_to_xml",
    "run_catphan_analysis",
]

