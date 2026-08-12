"""Independent acceptance audit for cleaned clinical-event Parquet output.

The audit reads the immutable admission JSONL and derived Parquet files. It does
not call the event transformers, normalization code, or an external model.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import argparse
import hashlib
import json
from pathlib import Path
import random
import re
from typing import Any

import pyarrow.parquet as pq

from data_pipeline.event_pipeline.ids import build_source_row_id
from data_pipeline.event_pipeline.schemas import QUALITY_FLAG_CODES
from data_pipeline.event_pipeline.source_registry import SOURCE_REGISTRY


RAW_REF_RE = re.compile(
    r"(?P<filename>[^#]+)#L(?P<line>\d+)/"
    r"(?P<module>[^.]+)\.(?P<table>[^[]+)\[(?P<index>\d+)\]"
)
SOURCE_SPECS = {spec.source_table: spec for spec in SOURCE_REGISTRY}
EXPECTED_KINDS = {
    "ed.triage": {"symptom_reported", "vital_measured", "triage_acuity_recorded"},
    "ed.vitalsign": {"vital_measured"},
    "hosp.labevents": {"laboratory_resulted"},
    "hosp.microbiologyevents": {"microbiology_resulted"},
    "hosp.poe_timeline": {"laboratory_ordered", "imaging_ordered", "clinical_ordered"},
    "hosp.prescriptions": {"medication_ordered"},
    "hosp.pharmacy": {"medication_order_status_recorded"},
    "hosp.emar": {
        "medication_administered",
        "medication_not_administered",
        "medication_administration_documented",
    },
    "hosp.services": {"service_changed"},
    "hosp.transfers": {"patient_transferred"},
    "hosp.procedures_icd": {"procedure_recorded_post_hoc"},
    "icu.procedureevents": {"procedure_performed"},
    "note.radiology": {"imaging_reported"},
    "note.discharge": {"document_recorded"},
}
REQUESTED_FIELDS = {
    "event_id": ["event_id"],
    "subject_id": ["subject_id"],
    "hadm_id": ["hadm_id"],
    "source_module": ["source_module"],
    "source_table": ["source_table"],
    "source_row_id": ["source_row_id"],
    "raw_row_ref": ["raw_row_ref"],
    "event_kind": ["event_kind"],
    "event_time": ["event_time"],
    "available_time": ["available_time"],
    "recorded_time": ["recorded_time"],
    "evidence_phase": ["evidence_phase"],
    "raw_concept_code": ["source_concept_id"],
    "raw_concept_term": ["source_label"],
    "parsed_value": ["value_numeric", "value_text", "value_structured_json"],
    "quality_flags": ["quality_flags"],
    "cleaning_status": [],
    "supporting_raw_row_refs": ["supporting_raw_row_refs"],
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _iso(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text if len(text) == 10 else text.replace(" ", "T", 1)


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clean(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value).strip()


def _decoded_label(row: dict[str, Any], field: str = "itemid_decoded") -> str | None:
    decoded = row.get(field)
    if not isinstance(decoded, dict):
        return None
    for key in ("label", "long_title", "long_description", "short_description"):
        value = _clean(decoded.get(key))
        if value:
            return value
    return None


def _read_jsonl(path: Path) -> dict[int, dict[str, Any]]:
    records: dict[int, dict[str, Any]] = {}
    with path.open("rb") as handle:
        for line_number, raw_line in enumerate(handle, 1):
            if raw_line.strip():
                records[line_number] = json.loads(raw_line)
    return records


def _without_enrichment(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _without_enrichment(item)
            for key, item in value.items()
            if not key.endswith("_decoded") and key != "poe_timeline"
        }
    if isinstance(value, list):
        return [_without_enrichment(item) for item in value]
    return value


def _raw_row(
    raw_ref: str,
    records: dict[int, dict[str, Any]],
    expected_filename: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    match = RAW_REF_RE.fullmatch(raw_ref)
    if match is None:
        raise ValueError("raw_row_ref_format")
    parts = match.groupdict()
    if parts["filename"] != expected_filename:
        raise ValueError("raw_row_ref_filename")
    line_number = int(parts["line"])
    admission = records.get(line_number)
    if admission is None:
        raise ValueError("raw_row_ref_line")
    module = admission.get(parts["module"])
    if not isinstance(module, dict):
        raise ValueError("raw_row_ref_module")
    rows = module.get(parts["table"])
    if not isinstance(rows, list):
        raise ValueError("raw_row_ref_table")
    index = int(parts["index"])
    if index >= len(rows) or not isinstance(rows[index], dict):
        raise ValueError("raw_row_ref_index")
    return admission, rows[index], parts


def _expected_times(
    source_table: str,
    row: dict[str, Any],
    admission: dict[str, Any],
) -> tuple[str | None, str | None, str | None]:
    if source_table == "ed.triage":
        return None, None, None
    if source_table == "ed.vitalsign":
        return _iso(row.get("charttime")), None, None
    if source_table == "hosp.labevents":
        return _iso(row.get("charttime")), _iso(row.get("storetime")), _iso(row.get("storetime"))
    if source_table == "hosp.microbiologyevents":
        return (
            _iso(row.get("charttime") or row.get("chartdate")),
            _iso(row.get("storetime")),
            _iso(row.get("storetime") or row.get("storedate")),
        )
    if source_table == "hosp.poe_timeline":
        value = _iso(row.get("event_time"))
        return value, value, None
    if source_table == "hosp.prescriptions":
        poe_id = _clean(row.get("poe_id"))
        raw_poe = next(
            (
                item
                for item in admission["mimic_iv_hosp"].get("poe", [])
                if _clean(item.get("poe_id")) == poe_id
            ),
            None,
        )
        ordertime = _iso(raw_poe.get("ordertime")) if isinstance(raw_poe, dict) else None
        return ordertime, ordertime, None
    if source_table == "hosp.pharmacy":
        return _iso(row.get("entertime")), _iso(row.get("entertime")), _iso(row.get("verifiedtime"))
    if source_table == "hosp.emar":
        return _iso(row.get("charttime")), _iso(row.get("storetime")), _iso(row.get("storetime"))
    if source_table == "hosp.services":
        value = _iso(row.get("transfertime"))
        return value, value, None
    if source_table == "hosp.transfers":
        return _iso(row.get("intime")), None, None
    if source_table == "hosp.procedures_icd":
        return _iso(row.get("chartdate")), None, None
    if source_table == "icu.procedureevents":
        available = _iso(row.get("storetime"))
        endtime = _iso(row.get("endtime"))
        if endtime and (available is None or available < endtime):
            available = endtime
        return _iso(row.get("starttime")), available, _iso(row.get("storetime"))
    if source_table in {"note.radiology", "note.discharge"}:
        return _iso(row.get("charttime")), _iso(row.get("storetime")), _iso(row.get("storetime"))
    raise KeyError(source_table)


def _expected_event_count(source_table: str, row: dict[str, Any]) -> int:
    if source_table not in {"ed.triage", "ed.vitalsign"}:
        return 1
    count = sum(row.get(field) not in (None, "") for field in ("heartrate", "temperature", "resprate", "o2sat", "pain"))
    if _number(row.get("sbp")) is not None or _number(row.get("dbp")) is not None:
        count += 1
    if source_table == "ed.triage":
        count += int(_clean(row.get("chiefcomplaint")) is not None)
        count += int(_number(row.get("acuity")) is not None)
    return count


def _add_issue(
    counts: Counter[str], examples: dict[str, list[str]], issue: str, example: str
) -> None:
    counts[issue] += 1
    if len(examples[issue]) < 5:
        examples[issue].append(example)


def audit(
    cleaned_path: Path,
    rejected_path: Path,
    source_path: Path,
    raw_source_path: Path,
    reconciliation_path: Path,
    manifest_path: Path,
    *,
    sample_seed: int = 20260812,
    samples_per_table: int = 3,
) -> dict[str, Any]:
    cleaned_file = pq.ParquetFile(cleaned_path)
    rejected_file = pq.ParquetFile(rejected_path)
    cleaned_table = cleaned_file.read()
    rejected_table = rejected_file.read()
    events = cleaned_table.to_pylist()
    rejected = rejected_table.to_pylist()
    records = _read_jsonl(source_path)
    raw_records = _read_jsonl(raw_source_path)
    reconciliation = json.loads(reconciliation_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    issue_counts: Counter[str] = Counter()
    issue_examples: dict[str, list[str]] = defaultdict(list)
    event_ids = [row["event_id"] for row in events]
    accepted_ids: dict[str, set[str]] = defaultdict(set)
    rejected_ids: dict[str, set[str]] = defaultdict(set)
    source_event_counts: Counter[tuple[str, str]] = Counter()
    table_kind_counts: Counter[tuple[str, str]] = Counter()
    table_time_counts: dict[str, Counter[str]] = defaultdict(Counter)
    table_phase_counts: Counter[tuple[str, str]] = Counter()
    quality_flag_counts: Counter[str] = Counter()
    table_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for event in events:
        event_id = event["event_id"]
        source_table = event["source_table"]
        table_rows[source_table].append(event)
        table_kind_counts[(source_table, event["event_kind"])] += 1
        table_phase_counts[(source_table, event["evidence_phase"])] += 1
        accepted_ids[source_table].add(event["source_row_id"])
        source_event_counts[(source_table, event["source_row_id"])] += 1
        for field in ("event_time", "available_time", "recorded_time"):
            table_time_counts[source_table][f"{field}_null"] += int(event[field] is None)
        flags = event["quality_flags"]
        for flag in flags:
            quality_flag_counts[flag] += 1
            if re.fullmatch(r"[A-Z][A-Z0-9_]*", flag) is None:
                _add_issue(
                    issue_counts,
                    issue_examples,
                    "quality_flag_not_canonical",
                    event_id,
                )
            if flag not in QUALITY_FLAG_CODES:
                _add_issue(
                    issue_counts,
                    issue_examples,
                    "quality_flag_not_in_frozen_enum",
                    event_id,
                )
        if len({flag.casefold() for flag in flags}) != len(flags):
            _add_issue(
                issue_counts,
                issue_examples,
                "quality_flag_case_collision",
                event_id,
            )
        if event["event_kind"] not in EXPECTED_KINDS.get(source_table, set()):
            _add_issue(issue_counts, issue_examples, "unexpected_event_kind", event_id)
        if event.get("cleaning_status") != "accepted":
            _add_issue(issue_counts, issue_examples, "cleaning_status_not_accepted", event_id)
        try:
            admission, raw, parts = _raw_row(event["raw_row_ref"], records, source_path.name)
        except ValueError as error:
            _add_issue(issue_counts, issue_examples, str(error), event_id)
            continue
        spec = SOURCE_SPECS[source_table]
        if parts["module"] != spec.module or parts["table"] != spec.table:
            _add_issue(issue_counts, issue_examples, "raw_ref_source_mismatch", event_id)
        if event["jsonl_line_number"] != int(parts["line"]):
            _add_issue(issue_counts, issue_examples, "raw_ref_line_column_mismatch", event_id)
        if event["source_array_index"] != int(parts["index"]):
            _add_issue(issue_counts, issue_examples, "raw_ref_index_column_mismatch", event_id)
        if event["source_module"] != spec.module:
            _add_issue(issue_counts, issue_examples, "source_module_mismatch", event_id)
        if event["subject_id"] != str(admission["subject_id"]) or event["hadm_id"] != str(admission["hadm_id"]):
            _add_issue(issue_counts, issue_examples, "admission_identity_mismatch", event_id)
        for key in ("subject_id", "hadm_id"):
            if raw.get(key) not in (None, "") and str(raw[key]) != event[key]:
                _add_issue(issue_counts, issue_examples, f"raw_{key}_mismatch", event_id)
        if build_source_row_id(spec, raw) != event["source_row_id"]:
            _add_issue(issue_counts, issue_examples, "source_row_id_mismatch", event_id)
        support_ids = event.get("supporting_source_row_ids") or []
        support_refs = event.get("supporting_raw_row_refs") or []
        if len(support_ids) != len(support_refs):
            _add_issue(
                issue_counts,
                issue_examples,
                "supporting_lineage_length_mismatch",
                event_id,
            )
        support_rows: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
        for support_id, support_ref in zip(support_ids, support_refs):
            try:
                support_admission, support_raw, support_parts = _raw_row(
                    support_ref, records, source_path.name
                )
            except ValueError as error:
                _add_issue(
                    issue_counts,
                    issue_examples,
                    f"supporting_{error}",
                    event_id,
                )
                continue
            support_spec = next(
                (
                    candidate
                    for candidate in SOURCE_REGISTRY
                    if candidate.module == support_parts["module"]
                    and candidate.table == support_parts["table"]
                ),
                None,
            )
            if support_spec is None or build_source_row_id(support_spec, support_raw) != support_id:
                _add_issue(
                    issue_counts,
                    issue_examples,
                    "supporting_source_row_id_mismatch",
                    event_id,
                )
            if (
                str(support_admission.get("subject_id")) != event["subject_id"]
                or str(support_admission.get("hadm_id")) != event["hadm_id"]
            ):
                _add_issue(
                    issue_counts,
                    issue_examples,
                    "supporting_admission_identity_mismatch",
                    event_id,
                )
            support_rows.append((support_admission, support_raw, support_parts))
        expected_times = _expected_times(source_table, raw, admission)
        actual_times = tuple(event[field] for field in ("event_time", "available_time", "recorded_time"))
        if actual_times != expected_times:
            _add_issue(issue_counts, issue_examples, "time_semantics_mismatch", event_id)
        if source_table == "hosp.procedures_icd" and event["evidence_phase"] != "post_hoc":
            _add_issue(issue_counts, issue_examples, "procedure_phase_mismatch", event_id)
        if source_table == "note.discharge" and event["evidence_phase"] != "post_hoc":
            _add_issue(issue_counts, issue_examples, "discharge_not_post_hoc", event_id)
        if source_table == "hosp.prescriptions" and event["event_time"] is not None:
            matching_support = [
                support_raw
                for _, support_raw, support_parts in support_rows
                if support_parts["module"] == "mimic_iv_hosp"
                and support_parts["table"] == "poe_timeline"
                and _clean(support_raw.get("poe_id")) == _clean(raw.get("poe_id"))
                and _iso(support_raw.get("event_time")) == event["event_time"]
            ]
            if len(matching_support) != 1:
                _add_issue(
                    issue_counts,
                    issue_examples,
                    "prescription_order_time_missing_supporting_lineage",
                    event_id,
                )
        if source_table == "hosp.labevents":
            expected_label = _decoded_label(raw)
            expected_numeric = _number(raw.get("valuenum"))
            expected_text = _clean(raw.get("value"))
            if expected_numeric is not None and expected_text == "___":
                expected_text = None
            expected_code = f"lab:{_clean(raw.get('itemid'))}"
            if (
                event["source_label"] != expected_label
                or event["source_concept_id"] != expected_code
                or event["value_numeric"] != expected_numeric
                or event["value_text"] != expected_text
                or event["unit"] != _clean(raw.get("valueuom"))
            ):
                _add_issue(issue_counts, issue_examples, "laboratory_value_mismatch", event_id)
        elif source_table == "hosp.prescriptions" and event["source_label"] != _clean(raw.get("drug")):
            _add_issue(issue_counts, issue_examples, "prescription_label_mismatch", event_id)
        elif source_table == "hosp.pharmacy" and event["source_label"] != _clean(raw.get("medication")):
            _add_issue(issue_counts, issue_examples, "pharmacy_label_mismatch", event_id)
        elif source_table == "hosp.emar" and event["source_label"] != _clean(raw.get("medication")):
            _add_issue(issue_counts, issue_examples, "emar_label_mismatch", event_id)
        elif source_table == "hosp.services" and event["source_label"] != _clean(raw.get("curr_service")):
            _add_issue(issue_counts, issue_examples, "service_label_mismatch", event_id)
        elif source_table == "note.radiology":
            label = _clean(raw.get("note_type")) or "Radiology report"
            if event["source_label"] != label or event["value_text"] is not None:
                _add_issue(issue_counts, issue_examples, "radiology_metadata_mismatch", event_id)
        elif source_table == "note.discharge" and event["value_text"] is not None:
            _add_issue(issue_counts, issue_examples, "discharge_text_copied_to_event", event_id)

    if len(event_ids) != len(set(event_ids)):
        issue_counts["duplicate_event_id"] = len(event_ids) - len(set(event_ids))
    issue_counts["null_event_id"] = sum(value is None for value in event_ids)

    for row in rejected:
        source_table = row["source_table"]
        rejected_ids[source_table].add(row["source_row_id"])
        if row.get("cleaning_status") != "rejected":
            _add_issue(
                issue_counts,
                issue_examples,
                "rejected_cleaning_status_invalid",
                row["source_row_id"],
            )
        try:
            admission, raw, _ = _raw_row(row["raw_row_ref"], records, source_path.name)
        except ValueError as error:
            _add_issue(issue_counts, issue_examples, f"rejected_{error}", row["source_row_id"])
            continue
        spec = SOURCE_SPECS[source_table]
        if build_source_row_id(spec, raw) != row["source_row_id"]:
            _add_issue(issue_counts, issue_examples, "rejected_source_row_id_mismatch", row["source_row_id"])
        if row["subject_id"] != str(admission["subject_id"]) or row["hadm_id"] != str(admission["hadm_id"]):
            _add_issue(issue_counts, issue_examples, "rejected_identity_mismatch", row["source_row_id"])
        if not (
            source_table == "hosp.pharmacy"
            and row["reason_code"] == "PHARMACY_MEDICATION_MISSING"
            and _clean(raw.get("medication")) is None
        ):
            _add_issue(issue_counts, issue_examples, "rejected_reason_not_reproduced", row["source_row_id"])

    raw_ids: dict[str, set[str]] = defaultdict(set)
    expected_source_counts: Counter[str] = Counter()
    for admission in records.values():
        for spec in SOURCE_REGISTRY:
            rows = admission[spec.module].get(spec.table, [])
            for raw in rows:
                source_id = build_source_row_id(spec, raw)
                raw_ids[spec.source_table].add(source_id)
                expected_source_counts[spec.source_table] += 1
                classified = int(source_id in accepted_ids[spec.source_table]) + int(source_id in rejected_ids[spec.source_table])
                if classified != 1:
                    _add_issue(issue_counts, issue_examples, "source_row_classification_mismatch", f"{spec.source_table}:{source_id}")
                if source_id in accepted_ids[spec.source_table]:
                    expected_events = _expected_event_count(spec.source_table, raw)
                    actual_events = source_event_counts[(spec.source_table, source_id)]
                    if actual_events != expected_events:
                        _add_issue(issue_counts, issue_examples, "source_row_event_count_mismatch", f"{spec.source_table}:{source_id}")

    reconciliation_differences: list[dict[str, Any]] = []
    reconciliation_by_table = {row["source_table"]: row for row in reconciliation["tables"]}
    for spec in SOURCE_REGISTRY:
        source_table = spec.source_table
        observed = {
            "input_rows": expected_source_counts[source_table],
            "accepted_source_rows": len(accepted_ids[source_table]),
            "rejected_source_rows": len(rejected_ids[source_table]),
            "events": sum(count for (table, _), count in table_kind_counts.items() if table == source_table),
        }
        declared = {key: reconciliation_by_table[source_table][key] for key in observed}
        if observed != declared:
            reconciliation_differences.append({"source_table": source_table, "observed": observed, "declared": declared})

    rng = random.Random(sample_seed)
    samples: list[dict[str, Any]] = []
    for source_table in sorted(table_rows):
        rows = table_rows[source_table]
        for row in rng.sample(rows, min(samples_per_table, len(rows))):
            samples.append(
                {
                    "event_id": row["event_id"],
                    "source_table": source_table,
                    "event_kind": row["event_kind"],
                    "raw_row_ref": row["raw_row_ref"],
                    "source_row_id": row["source_row_id"],
                }
            )

    columns = set(cleaned_table.column_names)
    field_contract = {
        requested: {
            "exact_present": requested in columns,
            "equivalent_columns": equivalents,
            "equivalents_present": bool(equivalents)
            and all(name in columns for name in equivalents),
        }
        for requested, equivalents in REQUESTED_FIELDS.items()
    }
    if not field_contract["cleaning_status"]["exact_present"]:
        _add_issue(
            issue_counts,
            issue_examples,
            "cleaning_status_missing",
            "cleaned_events.parquet",
        )
    event_distribution = [
        {"source_table": table, "event_kind": kind, "events": count}
        for (table, kind), count in sorted(table_kind_counts.items())
    ]
    source_reconciliation = []
    for spec in SOURCE_REGISTRY:
        table = spec.source_table
        source_reconciliation.append(
            {
                "source_table": table,
                "input_rows": expected_source_counts[table],
                "accepted_source_rows": len(accepted_ids[table]),
                "rejected_source_rows": len(rejected_ids[table]),
                "events": sum(value for (name, _), value in table_kind_counts.items() if name == table),
                "balanced": expected_source_counts[table] == len(accepted_ids[table]) + len(rejected_ids[table]),
            }
        )

    hashes = {
        "raw_source": _sha256(raw_source_path),
        "input": _sha256(source_path),
        "cleaned_events.parquet": _sha256(cleaned_path),
        "cleaning_rejected.parquet": _sha256(rejected_path),
    }
    hash_matches_manifest = {
        "input": hashes["input"] == manifest["input"]["sha256"],
        "cleaned_events.parquet": hashes["cleaned_events.parquet"] == manifest["output_sha256"]["cleaned_events.parquet"],
        "cleaning_rejected.parquet": hashes["cleaning_rejected.parquet"] == manifest["output_sha256"]["cleaning_rejected.parquet"],
    }

    material_issues = {
        key: value
        for key, value in issue_counts.items()
        if value and key != "null_event_id"
    }
    raw_identity_matches = 0
    raw_content_matches = 0
    raw_difference_lines: list[int] = []
    all_line_numbers = sorted(set(records) | set(raw_records))
    for line_number in all_line_numbers:
        enriched = records.get(line_number)
        raw = raw_records.get(line_number)
        if enriched is None or raw is None:
            raw_difference_lines.append(line_number)
            continue
        raw_identity_matches += int(
            (str(raw.get("subject_id")), str(raw.get("hadm_id")))
            == (str(enriched.get("subject_id")), str(enriched.get("hadm_id")))
        )
        content_matches = _without_enrichment(raw) == _without_enrichment(enriched)
        raw_content_matches += int(content_matches)
        if not content_matches and len(raw_difference_lines) < 20:
            raw_difference_lines.append(line_number)
    if raw_content_matches != len(all_line_numbers):
        issue_counts["raw_content_changed_by_enrichment"] = len(all_line_numbers) - raw_content_matches
        material_issues["raw_content_changed_by_enrichment"] = len(all_line_numbers) - raw_content_matches
    return {
        "audit_schema": "cleaned_events_acceptance_audit/1.0.0",
        "inputs": {
            "raw_source_jsonl": str(raw_source_path),
            "source_jsonl": str(source_path),
            "cleaned_events": str(cleaned_path),
            "cleaning_rejected": str(rejected_path),
            "manifest": str(manifest_path),
            "source_reconciliation": str(reconciliation_path),
        },
        "parquet": {
            "bytes": cleaned_path.stat().st_size,
            "rows": cleaned_file.metadata.num_rows,
            "row_groups": cleaned_file.metadata.num_row_groups,
            "row_group_rows": [
                cleaned_file.metadata.row_group(index).num_rows
                for index in range(cleaned_file.metadata.num_row_groups)
            ],
            "compression": sorted(
                {
                    cleaned_file.metadata.row_group(row_group).column(column).compression
                    for row_group in range(cleaned_file.metadata.num_row_groups)
                    for column in range(cleaned_file.metadata.num_columns)
                }
            ),
            "format_version": cleaned_file.metadata.format_version,
            "created_by": cleaned_file.metadata.created_by,
            "arrow_schema_metadata": {
                key.decode(): value.decode()
                for key, value in (cleaned_table.schema.metadata or {}).items()
            },
            "columns": [
                {"name": field.name, "type": str(field.type), "nullable": field.nullable}
                for field in cleaned_table.schema
            ],
        },
        "requested_field_contract": field_contract,
        "identity": {
            "event_rows": len(events),
            "event_id_unique": len(event_ids) == len(set(event_ids)),
            "event_id_nulls": sum(value is None for value in event_ids),
            "accepted_unique_source_rows": sum(len(values) for values in accepted_ids.values()),
            "rejected_unique_source_rows": sum(len(values) for values in rejected_ids.values()),
        },
        "event_distribution": event_distribution,
        "evidence_phase_distribution": [
            {"source_table": table, "evidence_phase": phase, "events": count}
            for (table, phase), count in sorted(table_phase_counts.items())
        ],
        "time_null_counts": {table: dict(sorted(counts.items())) for table, counts in sorted(table_time_counts.items())},
        "quality_flag_counts": dict(sorted(quality_flag_counts.items())),
        "source_reconciliation": source_reconciliation,
        "source_reconciliation_differences": reconciliation_differences,
        "hashes": hashes,
        "hash_matches_manifest": hash_matches_manifest,
        "full_event_lineage_checks": len(events),
        "full_rejected_lineage_checks": len(rejected),
        "upstream_raw_equivalence": {
            "lines": len(all_line_numbers),
            "identity_matches": raw_identity_matches,
            "raw_content_matches_after_dropping_decoded_fields_and_poe_timeline": raw_content_matches,
            "difference_lines": raw_difference_lines,
        },
        "random_sample": {"seed": sample_seed, "samples_per_table": samples_per_table, "events": samples},
        "issues": {
            "counts": dict(sorted(material_issues.items())),
            "examples": {key: values for key, values in sorted(issue_examples.items()) if issue_counts[key]},
        },
        "acceptance": {
            "can_start_normalization": not material_issues
            and all(hash_matches_manifest.values())
            and not reconciliation_differences
            and field_contract["cleaning_status"]["exact_present"],
            "blocking_issue_codes": sorted(material_issues),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cleaned", type=Path, required=True)
    parser.add_argument("--rejected", type=Path, required=True)
    parser.add_argument("--source-jsonl", type=Path, required=True)
    parser.add_argument("--raw-source-jsonl", type=Path, required=True)
    parser.add_argument("--reconciliation", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args()
    result = audit(
        args.cleaned.resolve(),
        args.rejected.resolve(),
        args.source_jsonl.resolve(),
        args.raw_source_jsonl.resolve(),
        args.reconciliation.resolve(),
        args.manifest.resolve(),
    )
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result["acceptance"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
