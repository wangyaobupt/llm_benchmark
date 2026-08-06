from __future__ import annotations

import csv
import gzip
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DatasetPaths:
    data_root: Path
    patients: Path
    admissions: Path
    discharge: Path
    discharge_detail: Path
    radiology: Path
    radiology_detail: Path
    edstays: Path
    triage: Path

    @classmethod
    def from_root(cls, data_root: Path) -> "DatasetPaths":
        root = data_root.resolve()
        return cls(
            data_root=root,
            patients=root / "mimic-iv-3.1" / "hosp" / "patients.csv.gz",
            admissions=root / "mimic-iv-3.1" / "hosp" / "admissions.csv.gz",
            discharge=root / "mimic-iv-note-2.2" / "note" / "discharge.csv.gz",
            discharge_detail=root / "mimic-iv-note-2.2" / "note" / "discharge_detail.csv.gz",
            radiology=root / "mimic-iv-note-2.2" / "note" / "radiology.csv.gz",
            radiology_detail=root / "mimic-iv-note-2.2" / "note" / "radiology_detail.csv.gz",
            edstays=root / "mimic-iv-ed" / "ed" / "edstays.csv.gz",
            triage=root / "mimic-iv-ed" / "ed" / "triage.csv.gz",
        )

    def required_files(self) -> tuple[Path, ...]:
        return (
            self.patients,
            self.admissions,
            self.discharge,
            self.discharge_detail,
            self.radiology,
            self.radiology_detail,
            self.edstays,
            self.triage,
        )

    def required_schemas(self) -> tuple[tuple[Path, tuple[str, ...]], ...]:
        note_header = (
            "note_id", "subject_id", "hadm_id", "note_type",
            "note_seq", "charttime", "storetime", "text",
        )
        detail_header = (
            "note_id", "subject_id", "field_name", "field_value", "field_ordinal",
        )
        return (
            (
                self.patients,
                ("subject_id", "gender", "anchor_age", "anchor_year", "anchor_year_group", "dod"),
            ),
            (
                self.admissions,
                (
                    "subject_id", "hadm_id", "admittime", "dischtime", "deathtime",
                    "admission_type", "admit_provider_id", "admission_location",
                    "discharge_location", "insurance", "language", "marital_status",
                    "race", "edregtime", "edouttime", "hospital_expire_flag",
                ),
            ),
            (self.discharge, note_header),
            (self.discharge_detail, detail_header),
            (self.radiology, note_header),
            (self.radiology_detail, detail_header),
            (
                self.edstays,
                (
                    "subject_id", "hadm_id", "stay_id", "intime", "outtime", "gender",
                    "race", "arrival_transport", "disposition",
                ),
            ),
            (
                self.triage,
                (
                    "subject_id", "stay_id", "temperature", "heartrate", "resprate",
                    "o2sat", "sbp", "dbp", "pain", "acuity", "chiefcomplaint",
                ),
            ),
        )

    def validate(self) -> None:
        missing = [path for path in self.required_files() if not path.is_file()]
        if missing:
            details = "\n".join(f"- {path}" for path in missing)
            raise FileNotFoundError(f"缺少第一阶段必需文件：\n{details}")

        schema_errors: list[str] = []
        for path, expected in self.required_schemas():
            with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as handle:
                reader = csv.reader(handle)
                actual = tuple(next(reader, ()))
            if actual != expected:
                schema_errors.append(
                    f"- {path}: 预期 {list(expected)}，实际 {list(actual)}"
                )
        if schema_errors:
            details = "\n".join(schema_errors)
            raise ValueError(f"第一阶段 CSV 表头不符合锁定 schema：\n{details}")
