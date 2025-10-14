"""Pylinac-based CBCT analysis helpers."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from importlib import import_module
from typing import Any, Iterable, Protocol

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

    @classmethod
    def from_dir(cls, directory: str) -> "CatphanLike":
        ...

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


def run_catphan_analysis(inventory: StudyInventory, phantom_name: str) -> BatchAnalysis:
    """Run pylinac Catphan analysis on each study within ``inventory``."""

    catphan_cls = _load_catphan_class(phantom_name)
    results: list[StudyAnalysisResult] = []

    for study in inventory.studies:
        try:
            phantom = catphan_cls.from_dir(str(study.path))
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


__all__: Iterable[str] = [
    "BatchAnalysis",
    "CatphanAnalysisError",
    "PhantomNotAvailableError",
    "PylinacNotInstalledError",
    "StudyAnalysisResult",
    "run_catphan_analysis",
]

