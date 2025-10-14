from __future__ import annotations

import json
from pathlib import Path

import pytest

from pylinac_bulkcbct.inventory import build_inventory


def create_dicom_file(path: Path) -> None:
    path.write_bytes(b"DICM")


def test_build_inventory_discovers_directories(tmp_path: Path) -> None:
    study_a = tmp_path / "patient_a" / "study1"
    study_a.mkdir(parents=True)
    create_dicom_file(study_a / "slice1.dcm")
    create_dicom_file(study_a / "slice2.dcm")

    study_b = tmp_path / "patient_b"
    study_b.mkdir()
    create_dicom_file(study_b / "image1.IMA")

    nested = study_a / "nested"
    nested.mkdir()
    create_dicom_file(nested / "extra.dcm")

    inventory = build_inventory(tmp_path)

    assert inventory.root == tmp_path.resolve()
    assert inventory.generated_at is not None
    assert len(inventory.studies) == 2

    study_paths = {record.relative_path for record in inventory.studies}
    assert study_paths == {Path("patient_a/study1"), Path("patient_b")}

    first = next(record for record in inventory.studies if record.relative_path == Path("patient_a/study1"))
    assert first.file_count == 2
    assert first.extensions == {".dcm"}


def test_inventory_serializes_to_json(tmp_path: Path) -> None:
    study = tmp_path / "study"
    study.mkdir()
    create_dicom_file(study / "slice1.dcm")

    inventory = build_inventory(tmp_path)
    payload = json.loads(inventory.to_json(indent=None))

    assert payload["root"].endswith("study") is False
    assert payload["study_count"] == 1
    assert payload["studies"][0]["relative_path"] == "study"
