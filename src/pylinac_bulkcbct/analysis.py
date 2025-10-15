"""Pylinac-based CBCT analysis helpers."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol
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


class CatphanLike(Protocol):
    """Protocol describing the pylinac Catphan API we rely on."""

    def analyze(self) -> None:
        ...

    def results(self) -> str:
        ...

    def results_data(self) -> dict[str, Any]:
        ...


def _serialise_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    """Ensure ``metrics`` can be serialised by normalising non-JSON types."""

    return json.loads(json.dumps(metrics, default=str))


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
            from_dir = getattr(catphan_cls, "from_dir", None)
            if callable(from_dir):
                phantom = from_dir(str(study.path))
            else:
                phantom = catphan_cls(str(study.path))
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


def _append_value(parent: ET.Element, key: str, value: Any) -> None:
    """Append ``value`` as an XML element under ``parent``."""

    if isinstance(value, dict):
        container = ET.SubElement(parent, key)
        for child_key, child_value in value.items():
            _append_value(container, str(child_key), child_value)
    elif isinstance(value, list):
        container = ET.SubElement(parent, key)
        for item in value:
            _append_value(container, "Item", item)
    else:
        element = ET.SubElement(parent, key)
        if value is not None:
            element.text = str(value)


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
        if result.summary:
            ET.SubElement(study_el, "Summary").text = result.summary

        metrics_el = ET.SubElement(study_el, "Metrics")
        for metric_key, metric_value in result.metrics.items():
            _append_value(metrics_el, str(metric_key), metric_value)

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

