"""Audit recoverable source information omitted from normalized events.

This script samples 50 admissions from a normalization parquet, resolves their
raw_row_ref pointers against the clinical-readable JSONL, and reports common
source fields/text that are not present in the normalized event schema.
It deliberately writes only audit metadata and field inventories, not raw
patient payloads.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any

import pyarrow.parquet as pq


RAW_REF_RE = re.compile(
    r"^(?P<filename>[^#/\\]+)#L(?P<line>\d+)/"
    r"(?P<module>[A-Za-z0-9_]+)\.(?P<table>[A-Za-z0-9_]+)\[(?P<index>\d+)\]$"
)

NORMALIZED_FIELDS = {
    "schema_version", "cleaning_status", "event_id", "entity_id", "source_row_id",
    "subject_id", "hadm_id", "encounter_id", "event_kind", "lifecycle_action",
    "status", "assertion", "event_time", "source_available_time", "available_time",
    "recorded_time", "time_resolution_status", "time_precision", "time_policy_id",
    "time_resolution_reasons", "evidence_phase", "source_concept_id", "concept_id",
    "preferred_name", "source_label", "entity_type", "normalization_status",
    "terminology_mapping_version", "content_specificity", "value_numeric", "value_text",
    "value_structured_json", "unit", "abnormal_flag", "normalized_value_numeric",
    "normalized_value_text", "normalized_unit", "unit_normalization_status", "source_module",
    "source_table", "source_array_index", "jsonl_line_number", "raw_row_ref",
    "source_action", "quality_flags", "supporting_source_row_ids", "supporting_raw_row_refs",
}

TEXT_FIELDS = {
    ("mimic_iv_hosp", "labevents"): ("comments", "laboratory_comment"),
    ("mimic_iv_hosp", "microbiologyevents"): ("comments", "microbiology_comment"),
    ("mimic_iv_ed", "triage"): ("chiefcomplaint", "chief_complaint"),
    ("mimic_iv_note", "radiology"): ("text", "radiology_report"),
    ("mimic_iv_note", "discharge"): ("text", "discharge_summary"),
}


def parse_ref(raw_row_ref: str) -> tuple[int, str, str, int]:
    match = RAW_REF_RE.fullmatch(raw_row_ref)
    if not match:
        raise ValueError(f"invalid raw_row_ref: {raw_row_ref}")
    return (
        int(match["line"]),
        match["module"],
        match["table"],
        int(match["index"]),
    )


def stable_sample(rows_by_hadm: dict[str, dict[str, Any]], limit: int) -> list[str]:
    """Select rare event/source coverage first, then fill by stable hash order."""
    selected: list[str] = []
    covered: set[str] = set()
    ordered = sorted(
        rows_by_hadm,
        key=lambda hadm: hashlib.sha256(hadm.encode("utf-8")).hexdigest(),
    )
    for hadm in ordered:
        coverage = rows_by_hadm[hadm]["coverage"]
        if coverage - covered:
            selected.append(hadm)
            covered.update(coverage)
        if len(selected) >= limit:
            return selected
    return selected + [hadm for hadm in ordered if hadm not in selected][: max(0, limit - len(selected))]


def scan_events(parquet_path: Path) -> tuple[dict[str, dict[str, Any]], list[str]]:
    by_hadm: dict[str, dict[str, Any]] = {}
    columns = ["hadm_id", "subject_id", "event_kind", "source_module", "source_table", "raw_row_ref"]
    for batch in pq.ParquetFile(parquet_path).iter_batches(columns=columns, batch_size=250_000):
        data = batch.to_pydict()
        for hadm, subject, kind, module, table, raw_ref in zip(
            data["hadm_id"], data["subject_id"], data["event_kind"],
            data["source_module"], data["source_table"], data["raw_row_ref"],
        ):
            hadm_key = str(hadm)
            item = by_hadm.setdefault(
                hadm_key,
                {"subject_id": str(subject), "event_count": 0, "coverage": set(), "raw_refs": []},
            )
            item["event_count"] += 1
            item["coverage"].add(f"event_kind:{kind}")
            item["coverage"].add(f"source_table:{module}.{table}")
            if raw_ref:
                item["raw_refs"].append(str(raw_ref))
    return by_hadm, stable_sample(by_hadm, 50)


def load_selected_lines(source_path: Path, selected_lines: set[int]) -> dict[int, dict[str, Any]]:
    rows: dict[int, dict[str, Any]] = {}
    with source_path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if line_no in selected_lines:
                rows[line_no] = json.loads(line)
            if len(rows) == len(selected_lines):
                break
    missing = selected_lines - rows.keys()
    if missing:
        raise ValueError(f"source JSONL lines missing: {sorted(missing)[:5]}")
    return rows


def flatten_source_records(admission: dict[str, Any]) -> dict[tuple[str, str, int], dict[str, Any]]:
    result: dict[tuple[str, str, int], dict[str, Any]] = {}
    for module_key, module in admission.items():
        if not module_key.startswith("mimic_iv_") or not isinstance(module, dict):
            continue
        for table, records in module.items():
            if not isinstance(records, list):
                continue
            for index, record in enumerate(records):
                if isinstance(record, dict):
                    result[(module_key, table, index)] = record
    return result


def audit(source_path: Path, parquet_path: Path, output_dir: Path) -> dict[str, Any]:
    rows_by_hadm, selected_hadm = scan_events(parquet_path)
    refs: dict[str, list[tuple[int, str, str, int]]] = defaultdict(list)
    for hadm in selected_hadm:
        for raw_ref in rows_by_hadm[hadm]["raw_refs"]:
            refs[hadm].append(parse_ref(raw_ref))
    selected_lines = {parts[0] for values in refs.values() for parts in values}
    admissions = load_selected_lines(source_path, selected_lines)

    table_report: dict[str, dict[str, Any]] = {}
    source_keys: dict[str, set[str]] = defaultdict(set)
    text_report: Counter[str] = Counter()
    text_nonempty: Counter[str] = Counter()
    nested_report: Counter[str] = Counter()
    event_ref_count = 0
    for hadm in selected_hadm:
        seen: set[tuple[int, str, str, int]] = set()
        for line, module, table, index in refs[hadm]:
            key = (line, module, table, index)
            if key in seen:
                continue
            seen.add(key)
            record = flatten_source_records(admissions[line]).get((module, table, index))
            if record is None:
                continue
            table_key = f"{module}.{table}"
            item = table_report.setdefault(table_key, {"source_rows": 0, "raw_field_counts": Counter()})
            item["source_rows"] += 1
            item["raw_field_counts"].update(record.keys())
            source_keys[table_key].update(record.keys())
            for key_name, value in record.items():
                if isinstance(value, (dict, list)):
                    nested_report[f"{table_key}.{key_name}"] += 1
            text_spec = TEXT_FIELDS.get((module, table))
            if text_spec:
                source_field, text_kind = text_spec
                text_key = f"{table_key}.{source_field} ({text_kind})"
                text_report[text_key] += 1
                if record.get(source_field):
                    text_nonempty[text_key] += 1
            event_ref_count += 1

    for table_key, item in table_report.items():
        item["raw_field_counts"] = dict(sorted(item["raw_field_counts"].items()))
        item["candidate_unrepresented_fields"] = sorted(
            key for key in source_keys[table_key]
            if key not in NORMALIZED_FIELDS and key not in {"subject_id", "hadm_id"}
        )

    result = {
        "schema_version": "normalization-loss-audit/1.0.0",
        "source": str(parquet_path),
        "clinical_readable_source": str(source_path),
        "sampling": {
            "method": "stable_sha256_with_coverage_first",
            "requested_admissions": 50,
            "selected_admissions": len(selected_hadm),
            "selected_hadm_ids": selected_hadm,
            "selected_subject_ids": sorted({rows_by_hadm[h]["subject_id"] for h in selected_hadm}),
        },
        "normalized_event_count": sum(rows_by_hadm[h]["event_count"] for h in selected_hadm),
        "resolved_source_reference_count": event_ref_count,
        "common_recoverable_categories": {
            "source_text": {
                "description": "源记录中存在但 normalized event 未直接保留的自由文本字段。",
                "fields": dict(sorted(text_report.items())),
                "nonempty_fields": dict(sorted(text_nonempty.items())),
            },
            "structured_or_nested_source_fields": {
                "description": "源记录中以 list/dict 保存、需要逐字段检查的结构化内容。",
                "fields": dict(sorted(nested_report.items())),
            },
        },
        "source_tables": table_report,
        "normalized_fields": sorted(NORMALIZED_FIELDS),
        "interpretation": [
            "candidate_unrepresented_fields 是按字段名初筛的候选，不等同于最终确认丢失；需结合字段语义和 raw_row_ref 回查。",
            "source_text 只统计来源中可恢复的文本，不代表当前 normalize 输出已经包含正文。",
            "所有患者级结果仅用于本地探索性验证，不进入 Git。",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-jsonl", type=Path, required=True)
    parser.add_argument("--normalized-parquet", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.source_jsonl, args.normalized_parquet, args.output_dir)
    print(json.dumps({
        "selected_admissions": result["sampling"]["selected_admissions"],
        "normalized_event_count": result["normalized_event_count"],
        "source_tables": len(result["source_tables"]),
        "output": str(args.output_dir / "report.json"),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
