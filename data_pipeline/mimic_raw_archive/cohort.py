"""Build stable external admission selections without changing raw records."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import duckdb

from data_pipeline.mimic_source_catalog import SOURCE_BY_KEY

from .config import RawArchiveConfig
from .selection import subject_bucket


CAD_CRITERIA = "ICD-9 410-414 / ICD-10 I20-I25"


def is_cad_code(code: object, version: object) -> bool:
    value = str(code or "").upper().replace(".", "")
    version_value = str(version or "")
    prefix = value[:3]
    return (version_value == "9" and "410" <= prefix <= "414") or (
        version_value == "10" and "I20" <= prefix <= "I25"
    )


def build_cad_selection(
    data_root: Path,
    output_path: Path,
    development_percent: int = 20,
) -> dict[str, Any]:
    diagnoses = (data_root / SOURCE_BY_KEY["diagnoses_icd"].relative_path).resolve()
    path_sql = diagnoses.as_posix().replace("'", "''")
    condition = (
        "((icd_version='9' AND substr(icd_code,1,3) BETWEEN '410' AND '414') "
        "OR (icd_version='10' AND substr(icd_code,1,3) BETWEEN 'I20' AND 'I25'))"
    )
    con = duckdb.connect(config={"threads": "4", "memory_limit": "8GB"})
    try:
        rows = con.execute(
            "SELECT DISTINCT subject_id, hadm_id "
            f"FROM read_csv_auto('{path_sql}', header=true, all_varchar=true) "
            f"WHERE {condition} AND subject_id IS NOT NULL AND hadm_id IS NOT NULL"
        ).fetchall()
    finally:
        con.close()
    ordered = sorted(
        ((str(subject_id), str(hadm_id)) for subject_id, hadm_id in rows),
        key=lambda row: hashlib.sha256(f"{row[0]}:{row[1]}".encode("ascii")).digest(),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".tmp")
    subjects: set[str] = set()
    development_subjects: set[str] = set()
    partition_counts = {"development": 0, "final_test": 0}
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for rank, (subject_id, hadm_id) in enumerate(ordered):
            partition = "development" if subject_bucket(subject_id) < development_percent else "final_test"
            subjects.add(subject_id)
            if partition == "development":
                development_subjects.add(subject_id)
            partition_counts[partition] += 1
            handle.write(json.dumps({
                "subject_id": subject_id, "hadm_id": hadm_id,
                "selection_rank": rank, "cohort": "coronary_disease_spectrum",
                "partition": partition,
            }, separators=(",", ":")) + "\n")
    temporary.replace(output_path)
    return {
        "criteria": CAD_CRITERIA, "admissions": len(ordered), "subjects": len(subjects),
        "development_subjects": len(development_subjects),
        "partition_admissions": partition_counts, "output": str(output_path),
    }


def main() -> None:
    defaults = RawArchiveConfig()
    parser = argparse.ArgumentParser(description="Build a coronary disease spectrum selection manifest")
    parser.add_argument("--data-root", type=Path, default=defaults.data_root)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--development-percent", type=int, default=20)
    args = parser.parse_args()
    report = build_cad_selection(args.data_root, args.output, args.development_percent)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
