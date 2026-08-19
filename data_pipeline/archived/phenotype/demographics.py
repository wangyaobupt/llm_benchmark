"""P1 — demographics sidecar (age_band, sex) from the raw admission archive.

Streams one raw-archive JSONL line per admission and extracts the embedded
``mimic_iv_hosp.patients[0]`` fields (gender, anchor_age, anchor_year,
anchor_year_group) plus the admission year from ``admissions[0].admittime`` to
compute ``age_at_encounter = anchor_age + (admit_year - anchor_year)``.

Output is a deterministic, hash-manifested Parquet keyed by ``hadm_id`` so the
phenotype layer joins it against ``normalized_events`` by admission.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

# Adopted age bands (18-39 / 40-64 / 65-79 / 80+). <18 kept as an explicit
# fallback band for any under-18 MIMIC rows; revisit if the distribution shows
# a material under-18 tail.
AGE_BANDS = ("<18", "18-39", "40-64", "65-79", "80+")


def age_band(age: int) -> str:
    if age < 18:
        return "<18"
    if age < 40:
        return "18-39"
    if age < 65:
        return "40-64"
    if age < 80:
        return "65-79"
    return "80+"


def _admit_year(admittime: str | None) -> int | None:
    if not admittime or len(str(admittime)) < 4:
        return None
    return int(str(admittime)[:4])


def parse_admission(record: dict) -> dict | None:
    """Extract one demographics row from one raw-archive JSON line.

    Returns None when the line is missing the patients/admissions modules (the
    caller decides whether that is an error or a skip).
    """
    hosp = record.get("mimic_iv_hosp")
    if not isinstance(hosp, dict):
        return None
    patients = hosp.get("patients")
    admissions = hosp.get("admissions")
    if not isinstance(patients, list) or not patients or not isinstance(admissions, list) or not admissions:
        return None
    pat = patients[0]
    adm = admissions[0]
    anchor_age = pat.get("anchor_age")
    anchor_year = pat.get("anchor_year")
    admit_time = adm.get("admittime")
    try:
        anchor_age_int = int(anchor_age)
        anchor_year_int = int(anchor_year)
        admit_year_int = _admit_year(admit_time)
    except (TypeError, ValueError):
        return None
    age = None
    if admit_year_int is not None and anchor_year_int is not None:
        age = anchor_age_int + (admit_year_int - anchor_year_int)
    return {
        "subject_id": str(record.get("subject_id") or pat.get("subject_id")),
        "hadm_id": str(record.get("hadm_id")),
        "gender": pat.get("gender"),
        "anchor_age": anchor_age_int,
        "anchor_year": anchor_year_int,
        "anchor_year_group": pat.get("anchor_year_group"),
        "age_at_encounter": age,
        "age_band": age_band(age) if age is not None else None,
    }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def extract_demographics(
    raw_archive_path: Path,
    out_path: Path,
    *,
    max_lines: int | None = None,
) -> dict:
    """Stream the raw archive, write ``hadm_demographics.parquet`` + manifest.

    Returns a summary with counts and input/output hashes. Deterministic:
    rows are sorted by hadm_id before writing.
    """
    raw_archive_path = Path(raw_archive_path)
    out_path = Path(out_path)
    rows: list[dict] = []
    n_read = 0
    n_parsed = 0
    with raw_archive_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            n_read += 1
            if max_lines is not None and n_read > max_lines:
                break
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            row = parse_admission(record)
            if row is not None:
                rows.append(row)
                n_parsed += 1

    rows.sort(key=lambda r: r["hadm_id"])
    table = pa.Table.from_pylist(rows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, out_path)

    input_sha = _sha256_file(raw_archive_path)
    output_sha = _sha256_file(out_path)
    manifest = {
        "schema_version": "phenotype-demographics-manifest/1.0.0",
        "input": {"path": str(raw_archive_path), "sha256": input_sha},
        "output": {"path": str(out_path), "sha256": output_sha},
        "counts": {"records_read": n_read, "parsed": n_parsed,
                   "subjects": len({r["subject_id"] for r in rows}),
                   "admissions": len({r["hadm_id"] for r in rows})},
        "age_bands": list(AGE_BANDS),
    }
    manifest_path = out_path.with_suffix(".manifest.json")
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest
