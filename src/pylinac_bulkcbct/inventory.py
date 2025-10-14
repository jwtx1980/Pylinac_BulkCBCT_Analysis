"""Utilities for discovering CBCT studies on disk."""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable, List, Sequence, Set

logger = logging.getLogger(__name__)


DEFAULT_EXTENSIONS: Sequence[str] = (".dcm", ".ima")
"""File extensions that indicate CT image slices."""


@dataclass
class StudyRecord:
    """Represents a single discovered CBCT study directory."""

    path: Path
    """Absolute path to the study directory."""

    relative_path: Path
    """Path to the study directory relative to the scan root."""

    file_count: int
    """Number of image files discovered in the directory."""

    extensions: Set[str] = field(default_factory=set)
    """Unique set of extensions discovered in the directory."""

    def to_dict(self) -> dict:
        """Convert the record to a JSON-serialisable dictionary."""

        return {
            "path": str(self.path),
            "relative_path": str(self.relative_path),
            "file_count": self.file_count,
            "extensions": sorted(self.extensions),
        }


@dataclass
class StudyInventory:
    """Collection of all studies discovered during a scan."""

    root: Path
    generated_at: datetime
    studies: List[StudyRecord] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert the inventory to a JSON-serialisable dictionary."""

        return {
            "root": str(self.root),
            "generated_at": self.generated_at.isoformat(),
            "study_count": len(self.studies),
            "studies": [record.to_dict() for record in self.studies],
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        """Render the inventory as JSON."""

        return json.dumps(self.to_dict(), indent=indent)


def build_inventory(
    root: Path | str,
    *,
    extensions: Sequence[str] = DEFAULT_EXTENSIONS,
    follow_symlinks: bool = False,
) -> StudyInventory:
    """Scan ``root`` for CBCT studies and return a populated inventory."""

    root_path = Path(root).expanduser().resolve()
    if not root_path.exists():
        raise FileNotFoundError(f"Root directory does not exist: {root_path}")
    if not root_path.is_dir():
        raise NotADirectoryError(f"Root path is not a directory: {root_path}")

    logger.info("Scanning for CBCT studies in %s", root_path)
    normalised_extensions = {ext.lower() for ext in extensions}
    studies: List[StudyRecord] = []

    for current_dir, dirnames, filenames in os.walk(root_path, followlinks=follow_symlinks):
        current_path = Path(current_dir)
        matching_files = _filter_files(filenames, normalised_extensions)
        if not matching_files:
            continue

        logger.debug(
            "Found candidate study directory %s containing %d files", current_path, len(matching_files)
        )
        record = StudyRecord(
            path=current_path,
            relative_path=current_path.relative_to(root_path),
            file_count=len(matching_files),
            extensions={Path(name).suffix.lower() for name in matching_files},
        )
        studies.append(record)

        # Do not descend further once a study directory has been identified; this prevents
        # nested folders with the same data from being treated as separate studies.
        dirnames[:] = []

    logger.info("Discovered %d study directories", len(studies))
    return StudyInventory(root=root_path, generated_at=datetime.now(UTC), studies=studies)


def _filter_files(filenames: Iterable[str], extensions: Set[str]) -> List[str]:
    """Return filenames that match the allowed extensions."""

    return [name for name in filenames if Path(name).suffix.lower() in extensions]


__all__ = [
    "DEFAULT_EXTENSIONS",
    "StudyInventory",
    "StudyRecord",
    "build_inventory",
]
