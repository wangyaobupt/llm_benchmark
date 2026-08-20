"""Eligibility funnel with checkpointed n1 / n2 / eligible lists."""

from __future__ import annotations

import csv
import gzip
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterator

from data_pipeline.mimic_source_catalog import SOURCE_BY_KEY

from .atomic import atomic_write_json, atomic_write_jsonl, file_sha256, read_jsonl, remove_partial
from .config import VisitExtractConfig
from .ds_parser import select_ds
from .extract import ICD_VERSION_LABEL, age_at_encounter
from .progress import write_progress


class FunnelError(ValueError):
    pass


def _source_path(config: VisitExtractConfig, key: str) -> Path:
    return config.data_root / SOURCE_BY_KEY[key].relative_path


def _iter_csv(path: Path) -> Iterator[dict[str, str]]:
    with gzip.open(path, "rt", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            yield {key: ("" if value is None else str(value)) for key, value in row.items()}


def _complete_list(path: Path, rows: list[dict[str, Any]], manifest_entry: dict[str, Any]) -> dict[str, Any]:
    remove_partial(path)
    atomic_write_jsonl(path, rows)
    entry = {
        "status": "complete",
        "records": len(rows),
        "sha256": file_sha256(path),
    }
    manifest_entry.update(entry)
    return entry


def _reuse_list(path: Path, entry: dict[str, Any], label: str) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"{label} marked complete but missing: {path}")
    actual = file_sha256(path)
    if actual != entry.get("sha256"):
        raise FunnelError(f"{label} integrity failure")
    return read_jsonl(path)


def build_n1(config: VisitExtractConfig) -> tuple[list[dict[str, Any]], int, int]:
    patients: dict[str, dict[str, str]] = {}
    for row in _iter_csv(_source_path(config, "patients")):
        subject_id = row["subject_id"].strip()
        if subject_id:
            patients[subject_id] = row
    n1: list[dict[str, Any]] = []
    candidate_count = 0
    seen_hadm: set[str] = set()
    for row in _iter_csv(_source_path(config, "admissions")):
        candidate_count += 1
        subject_id = row["subject_id"].strip()
        hadm_id = row["hadm_id"].strip()
        if not subject_id or not hadm_id:
            raise FunnelError("admissions subject_id or hadm_id is empty")
        if hadm_id in seen_hadm:
            raise FunnelError(f"duplicate hadm_id in admissions: {hadm_id}")
        seen_hadm.add(hadm_id)
        patient = patients.get(subject_id)
        if patient is None:
            continue
        age = age_at_encounter(patient.get("anchor_age"), patient.get("anchor_year"), row.get("admittime"))
        sex = (patient.get("gender") or "").strip()
        admission_type = (row.get("admission_type") or "").strip()
        if age is None or age < 18 or sex not in {"M", "F"} or not admission_type:
            continue
        n1.append(
            {
                "subject_id": subject_id,
                "hadm_id": hadm_id,
                "age_at_encounter": age,
                "sex": sex,
                "admission_type": admission_type,
                "admission_location": (row.get("admission_location") or "").strip() or None,
                "discharge_location": (row.get("discharge_location") or "").strip() or None,
                "admittime": row.get("admittime") or "",
            }
        )
    return n1, candidate_count, candidate_count - len(n1)


def build_n2(config: VisitExtractConfig, n1: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    wanted = {row["hadm_id"]: row for row in n1}
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in _iter_csv(_source_path(config, "diagnoses_icd")):
        hadm_id = row["hadm_id"].strip()
        if hadm_id in wanted:
            if row["subject_id"].strip() != wanted[hadm_id]["subject_id"]:
                raise FunnelError(f"diagnoses_icd subject_id conflict for hadm_id={hadm_id}")
            grouped[hadm_id].append(row)
    dictionary: dict[tuple[str, str], str] = {}
    for row in _iter_csv(_source_path(config, "d_icd_diagnoses")):
        code = row["icd_code"].strip()
        version = row["icd_version"].strip()
        title = (row.get("long_title") or "").strip()
        if code and version and title:
            dictionary[(code, version)] = title
    n2: list[dict[str, Any]] = []
    for row in n1:
        records = grouped.get(row["hadm_id"], [])
        primaries = [item for item in records if item.get("seq_num", "").strip() in {"1", "1.0"}]
        if len(primaries) != 1:
            continue
        primary = primaries[0]
        code = primary["icd_code"].strip()
        version = primary["icd_version"].strip()
        name = dictionary.get((code, version))
        if not code or version not in ICD_VERSION_LABEL or not name:
            continue
        n2.append(row)
    return n2, len(n1) - len(n2)


def _discharge_by_hadm(config: VisitExtractConfig, wanted: dict[str, dict[str, Any]]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in _iter_csv(_source_path(config, "discharge")):
        hadm_id = row["hadm_id"].strip()
        if hadm_id not in wanted:
            continue
        if row["subject_id"].strip() != wanted[hadm_id]["subject_id"]:
            raise FunnelError(f"discharge subject_id conflict for hadm_id={hadm_id}")
        grouped[hadm_id].append(row)
    return grouped


def build_eligible_shard(
    n2_shard: list[dict[str, Any]],
    notes_by_hadm: dict[str, list[dict[str, str]]],
) -> list[dict[str, Any]]:
    eligible: list[dict[str, Any]] = []
    for row in n2_shard:
        selected = select_ds(notes_by_hadm.get(row["hadm_id"], []))
        if selected is None:
            continue
        eligible.append(row)
    return eligible


def run_funnel(
    config: VisitExtractConfig,
    manifest: dict[str, Any],
    manifest_path: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    from .atomic import write_manifest

    funnel_dir = config.output_dir / "funnel"
    funnel_dir.mkdir(parents=True, exist_ok=True)
    n1_path = funnel_dir / "n1.jsonl"
    n2_path = funnel_dir / "n2.jsonl"
    eligible_path = config.output_dir / "eligible.jsonl"
    state = manifest.setdefault("funnel", {})

    if state.get("n1", {}).get("status") == "complete":
        n1 = _reuse_list(n1_path, state["n1"], "n1")
        candidate_count = state.get("counts", {}).get("candidate_count", len(n1))
        excluded_stage1 = state.get("counts", {}).get("excluded_stage1", 0)
    else:
        write_progress(config.output_dir, phase="funnel_n1")
        remove_partial(n1_path)
        n1, candidate_count, excluded_stage1 = build_n1(config)
        state["n1"] = _complete_list(n1_path, n1, {})
        state["counts"] = {
            "candidate_count": candidate_count,
            "excluded_stage1": excluded_stage1,
        }
        write_manifest(manifest_path, manifest)

    if state.get("n2", {}).get("status") == "complete":
        n2 = _reuse_list(n2_path, state["n2"], "n2")
        excluded_stage2 = state.get("counts", {}).get("excluded_stage2", 0)
    else:
        write_progress(config.output_dir, phase="funnel_n2")
        remove_partial(n2_path)
        n2, excluded_stage2 = build_n2(config, n1)
        state["n2"] = _complete_list(n2_path, n2, {})
        state.setdefault("counts", {})
        state["counts"]["excluded_stage2"] = excluded_stage2
        write_manifest(manifest_path, manifest)

    if state.get("eligible", {}).get("status") == "complete":
        eligible = _reuse_list(eligible_path, state["eligible"], "eligible")
        excluded_stage3 = state.get("counts", {}).get("excluded_stage3", 0)
    else:
        wanted = {row["hadm_id"]: row for row in n2}
        notes = _discharge_by_hadm(config, wanted)
        shard_size = config.funnel_shard_size
        shard_dir = funnel_dir / "eligible_shards"
        shard_dir.mkdir(parents=True, exist_ok=True)
        shards_state = state.setdefault("eligible_shards", {})
        eligible = []
        shard_count = max(1, (len(n2) + shard_size - 1) // shard_size) if n2 else 0
        for shard_id in range(shard_count):
            key = str(shard_id)
            path = shard_dir / f"part-{shard_id:05d}.jsonl"
            entry = shards_state.get(key, {})
            if entry.get("status") == "complete":
                shard_rows = _reuse_list(path, entry, f"eligible shard {shard_id}")
            else:
                write_progress(
                    config.output_dir,
                    phase="funnel_ds",
                    detail=f"{shard_id + 1}/{shard_count}",
                )
                start = shard_id * shard_size
                chunk = n2[start : start + shard_size]
                shard_rows = build_eligible_shard(chunk, notes)
                remove_partial(path)
                shards_state[key] = _complete_list(path, shard_rows, {})
                write_manifest(manifest_path, manifest)
            eligible.extend(shard_rows)
        excluded_stage3 = len(n2) - len(eligible)
        remove_partial(eligible_path)
        state["eligible"] = _complete_list(eligible_path, eligible, {})
        state.setdefault("counts", {})
        state["counts"]["excluded_stage3"] = excluded_stage3
        state["counts"]["eligible_count"] = len(eligible)
        write_manifest(manifest_path, manifest)

    counts = {
        "candidate_count": state.get("counts", {}).get("candidate_count", 0),
        "excluded_stage1": state.get("counts", {}).get("excluded_stage1", 0),
        "excluded_stage2": state.get("counts", {}).get("excluded_stage2", 0),
        "excluded_stage3": state.get("counts", {}).get("excluded_stage3", 0),
        "eligible_count": len(eligible),
    }
    atomic_write_json(config.output_dir / "funnel.json", counts)
    return eligible, counts
