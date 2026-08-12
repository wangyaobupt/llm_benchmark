"""Independent acceptance audit for cleaned clinical-event Parquet output.

The audit reads the immutable admission JSONL and derived Parquet files. It does
not call the event transformers, normalization code, or an external model.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import random
import re
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from ..event_cleaning.ids import build_source_row_id, canonical_json
from ..event_cleaning.pipeline import CLEANING_LOGIC_VERSION, OUTPUT_SCHEMA
from ..event_contracts.schemas import (
    EVENT_ARROW_SCHEMA,
    QUALITY_FLAG_CODES,
    REJECTED_ARROW_SCHEMA,
)
from ..event_cleaning.source_catalog import (
    EVENT_SOURCE_REGISTRY,
    SOURCE_BY_PATH,
    SOURCE_CATALOG,
    SOURCE_CATALOG_SHA256,
    SOURCE_CATALOG_VERSION,
)


RAW_REF_RE = re.compile(
    r"(?P<filename>[^#]+)#L(?P<line>\d+)/"
    r"(?P<module>[^.]+)\.(?P<table>[^[]+)\[(?P<index>\d+)\]"
)
SOURCE_SPECS = {spec.source_table: spec for spec in EVENT_SOURCE_REGISTRY}
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
    "hosp.diagnoses_icd": {"condition_recorded_post_hoc"},
    "hosp.hcpcsevents": {"procedure_recorded_post_hoc"},
    "ed.diagnosis": {"condition_recorded_post_hoc"},
    "ed.medrecon": {"medication_reconciled"},
    "ed.pyxis": {"medication_dispensed"},
    "icu.inputevents": {"input_administered"},
    "icu.outputevents": {"output_measured"},
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
    "source_available_time": ["source_available_time"],
    "available_time": ["available_time"],
    "recorded_time": ["recorded_time"],
    "time_policy_id": ["time_policy_id"],
    "time_resolution_reasons": ["time_resolution_reasons"],
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


def _source_identity_index(
    records: dict[int, dict[str, Any]],
    input_name: str,
) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    source_id_by_ref: dict[str, str] = {}
    raw_by_ref: dict[str, dict[str, Any]] = {}
    for line_number, admission in records.items():
        for spec in SOURCE_CATALOG:
            occurrences: Counter[str] = Counter()
            rows = admission[spec.module][spec.table]
            for index, row in enumerate(rows):
                ordinal = 0
                if spec.identity_strategy == "canonical_row_hash_with_occurrence":
                    identity = canonical_json(row)
                    ordinal = occurrences[identity]
                    occurrences[identity] += 1
                source_id = build_source_row_id(
                    spec,
                    row,
                    duplicate_occurrence_ordinal=ordinal,
                )
                raw_ref = (
                    f"{input_name}#L{line_number}/"
                    f"{spec.module}.{spec.table}[{index}]"
                )
                source_id_by_ref[raw_ref] = source_id
                raw_by_ref[raw_ref] = row
    return source_id_by_ref, raw_by_ref


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


def _restore_raw_record(value: dict[str, Any]) -> dict[str, Any]:
    """Reverse the clinical-readable wrapper before raw-content comparison."""
    restored = _without_enrichment(value)
    schema = restored.get("schema")
    if schema != {
        "name": "mimic_admission_clinical_readable",
        "version": "1.0.0",
    }:
        return restored
    source_schema = restored.pop("source_schema", None)
    if not isinstance(source_schema, dict):
        return restored
    return {
        "schema": source_schema,
        **{key: item for key, item in restored.items() if key != "schema"},
    }


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


def _earlier(left: str | None, right: str | None) -> bool:
    return bool(
        left
        and right
        and datetime.fromisoformat(left) < datetime.fromisoformat(right)
    )


def _resolved_time_contract(
    *,
    event_time: Any = None,
    source_available_time: Any = None,
    recorded_time: Any = None,
    completion_time: Any = None,
) -> dict[str, Any]:
    event = _iso(event_time)
    source_available = _iso(source_available_time)
    available = source_available
    recorded = _iso(recorded_time)
    completion = _iso(completion_time)
    reasons: list[str] = []
    flags: list[str] = []
    if _earlier(source_available, event):
        reasons.append("source_available_precedes_event_time")
        flags.append("AVAILABLE_BEFORE_EVENT_TIME")
    if completion and (available is None or _earlier(available, completion)):
        available = completion
        reasons.append("completion_time_lower_bound")
        flags.append("AVAILABLE_TIME_DERIVED_FROM_COMPLETION")
    if _earlier(available, event):
        available = event
        reasons.append("event_time_lower_bound")
        flags.append("AVAILABLE_TIME_CLAMPED_TO_EVENT_TIME")
    if available is None:
        flags.append("AVAILABLE_TIME_UNKNOWN")
    if event is None and available is None and recorded is None:
        status = "unresolved"
    elif event is not None and available is not None:
        status = "resolved"
    else:
        status = "partially_resolved"
    precision = "unknown"
    for value in (event, available, recorded):
        if value is not None:
            if len(value) == 10:
                precision = "date"
            elif "." in value:
                precision = "subsecond"
            else:
                precision = "second"
            break
    return {
        "event_time": event,
        "source_available_time": source_available,
        "available_time": available,
        "recorded_time": recorded,
        "time_resolution_status": status,
        "time_precision": precision,
        "time_resolution_reasons": reasons,
        "time_quality_flags": flags,
    }


def _expected_times(
    source_table: str,
    row: dict[str, Any],
    admission: dict[str, Any],
) -> dict[str, Any]:
    if source_table == "ed.triage":
        return _resolved_time_contract()
    if source_table in {"ed.vitalsign", "ed.medrecon", "ed.pyxis"}:
        return _resolved_time_contract(event_time=row.get("charttime"))
    if source_table == "hosp.labevents":
        return _resolved_time_contract(
            event_time=row.get("charttime"),
            source_available_time=row.get("storetime"),
            recorded_time=row.get("storetime"),
        )
    if source_table == "hosp.microbiologyevents":
        return _resolved_time_contract(
            event_time=row.get("charttime") or row.get("chartdate"),
            source_available_time=row.get("storetime"),
            recorded_time=row.get("storetime") or row.get("storedate"),
        )
    if source_table == "hosp.poe_timeline":
        value = row.get("event_time")
        return _resolved_time_contract(
            event_time=value,
            source_available_time=value,
        )
    if source_table == "hosp.prescriptions":
        poe_id = _clean(row.get("poe_id"))
        poe_seq = _clean(row.get("poe_seq"))
        timeline = [
            item
            for item in admission["mimic_iv_hosp"].get("poe_timeline", [])
            if _clean(item.get("poe_id")) == poe_id
            and _clean(item.get("poe_seq")) == poe_seq
        ]
        ordertime = timeline[0].get("event_time") if len(timeline) == 1 else None
        return _resolved_time_contract(
            event_time=ordertime,
            source_available_time=ordertime,
        )
    if source_table == "hosp.pharmacy":
        return _resolved_time_contract(
            event_time=row.get("entertime"),
            source_available_time=row.get("entertime"),
            recorded_time=row.get("verifiedtime"),
        )
    if source_table == "hosp.emar":
        return _resolved_time_contract(
            event_time=row.get("charttime"),
            source_available_time=row.get("storetime"),
            recorded_time=row.get("storetime"),
        )
    if source_table == "hosp.services":
        value = row.get("transfertime")
        return _resolved_time_contract(
            event_time=value,
            source_available_time=value,
        )
    if source_table == "hosp.transfers":
        return _resolved_time_contract(event_time=row.get("intime"))
    if source_table in {"hosp.procedures_icd", "hosp.hcpcsevents"}:
        return _resolved_time_contract(event_time=row.get("chartdate"))
    if source_table in {"hosp.diagnoses_icd", "ed.diagnosis"}:
        return _resolved_time_contract()
    if source_table in {"icu.inputevents", "icu.procedureevents"}:
        return _resolved_time_contract(
            event_time=row.get("starttime"),
            source_available_time=row.get("storetime"),
            recorded_time=row.get("storetime"),
            completion_time=row.get("endtime"),
        )
    if source_table == "icu.outputevents":
        return _resolved_time_contract(
            event_time=row.get("charttime"),
            source_available_time=row.get("storetime"),
            recorded_time=row.get("storetime"),
        )
    if source_table in {"note.radiology", "note.discharge"}:
        return _resolved_time_contract(
            event_time=row.get("charttime"),
            source_available_time=row.get("storetime"),
            recorded_time=row.get("storetime"),
        )
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


def _distinct(values: list[str | None]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value.casefold() not in seen:
            seen.add(value.casefold())
            result.append(value)
    return result


def _prescriptions_by_pharmacy_id(
    admission: dict[str, Any], pharmacy_id: str | None
) -> list[dict[str, Any]]:
    if pharmacy_id is None:
        return []
    return [
        row
        for row in admission["mimic_iv_hosp"]["prescriptions"]
        if _clean(row.get("pharmacy_id")) == pharmacy_id
    ]


def _expected_pharmacy_label(
    row: dict[str, Any], admission: dict[str, Any]
) -> str | None:
    raw_label = _clean(row.get("medication"))
    if raw_label:
        return raw_label
    candidates = _distinct(
        [
            _clean(item.get("drug"))
            for item in _prescriptions_by_pharmacy_id(
                admission, _clean(row.get("pharmacy_id"))
            )
        ]
    )
    return candidates[0] if len(candidates) == 1 else None


def _expected_emar_label(
    row: dict[str, Any], admission: dict[str, Any]
) -> str | None:
    raw_label = _clean(row.get("medication"))
    if raw_label:
        return raw_label
    pharmacy_id = _clean(row.get("pharmacy_id"))
    pharmacy_labels = [
        _clean(item.get("medication"))
        for item in admission["mimic_iv_hosp"]["pharmacy"]
        if pharmacy_id and _clean(item.get("pharmacy_id")) == pharmacy_id
    ]
    prescription_labels = [
        _clean(item.get("drug"))
        for item in _prescriptions_by_pharmacy_id(admission, pharmacy_id)
    ]
    candidates = _distinct([*pharmacy_labels, *prescription_labels])
    return candidates[0] if len(candidates) == 1 else None


def _expected_rejection_reason(
    source_table: str,
    row: dict[str, Any],
    admission: dict[str, Any],
) -> str | None:
    if source_table in {"ed.triage", "ed.vitalsign"}:
        if _expected_event_count(source_table, row) == 0:
            return "NO_EVENT_GENERATED"
    if source_table == "hosp.labevents":
        if not _clean(row.get("itemid")) or not _decoded_label(row):
            return "LAB_CONCEPT_MISSING"
    elif source_table == "hosp.microbiologyevents":
        if not (_clean(row.get("test_name")) or _clean(row.get("spec_type_desc"))):
            return "MICROBIOLOGY_CONCEPT_MISSING"
    elif source_table == "hosp.prescriptions":
        if not _clean(row.get("drug")):
            return "PRESCRIPTION_DRUG_MISSING"
    elif source_table == "hosp.pharmacy" and not _clean(row.get("medication")):
        candidates = _distinct(
            [
                _clean(item.get("drug"))
                for item in _prescriptions_by_pharmacy_id(
                    admission, _clean(row.get("pharmacy_id"))
                )
            ]
        )
        if len(candidates) > 1:
            return "PHARMACY_MEDICATION_AMBIGUOUS"
        if not candidates:
            return "PHARMACY_MEDICATION_UNRESOLVED"
    elif source_table in {
        "hosp.diagnoses_icd",
        "ed.diagnosis",
        "hosp.procedures_icd",
    }:
        if not _clean(row.get("icd_code")):
            return "CODE_MISSING"
    elif source_table == "hosp.hcpcsevents" and not _clean(row.get("hcpcs_cd")):
        return "CODE_MISSING"
    elif source_table in {
        "icu.inputevents",
        "icu.outputevents",
        "icu.procedureevents",
    }:
        if not _clean(row.get("itemid")) or not _decoded_label(row):
            return "ICU_CONCEPT_MISSING"
    return None


def _add_issue(
    counts: Counter[str], examples: dict[str, list[str]], issue: str, example: str
) -> None:
    counts[issue] += 1
    if len(examples[issue]) < 5:
        examples[issue].append(example)


def _arrow_type_contract(data_type: pa.DataType) -> Any:
    if pa.types.is_list(data_type) or pa.types.is_large_list(data_type):
        return (str(data_type.id), _arrow_type_contract(data_type.value_type))
    return str(data_type)


def _arrow_schema_matches(actual: pa.Schema, expected: pa.Schema) -> bool:
    if len(actual) != len(expected) or actual.metadata != expected.metadata:
        return False
    return all(
        actual_field.name == expected_field.name
        and actual_field.nullable == expected_field.nullable
        and _arrow_type_contract(actual_field.type)
        == _arrow_type_contract(expected_field.type)
        for actual_field, expected_field in zip(actual, expected)
    )


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
    source_id_by_ref, _ = _source_identity_index(records, source_path.name)
    reconciliation = json.loads(reconciliation_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    issue_counts: Counter[str] = Counter()
    issue_examples: dict[str, list[str]] = defaultdict(list)
    columns = set(cleaned_table.column_names)
    required_exact_fields = {
        "event_id",
        "subject_id",
        "hadm_id",
        "source_module",
        "source_table",
        "source_row_id",
        "raw_row_ref",
        "event_kind",
        "event_time",
        "source_available_time",
        "available_time",
        "recorded_time",
        "time_policy_id",
        "time_resolution_reasons",
        "evidence_phase",
        "quality_flags",
        "cleaning_status",
        "supporting_raw_row_refs",
    }
    for field in sorted(required_exact_fields - columns):
        _add_issue(
            issue_counts,
            issue_examples,
            "required_event_field_missing",
            field,
        )
    missing_event_schema_fields = set(EVENT_ARROW_SCHEMA.names) - columns
    event_structure_valid = not missing_event_schema_fields
    for field in sorted(missing_event_schema_fields - required_exact_fields):
        _add_issue(
            issue_counts,
            issue_examples,
            "event_schema_field_missing",
            field,
        )
    rejected_columns = set(rejected_table.column_names)
    missing_rejected_schema_fields = set(REJECTED_ARROW_SCHEMA.names) - rejected_columns
    rejected_structure_valid = not missing_rejected_schema_fields
    for field in sorted(missing_rejected_schema_fields):
        _add_issue(
            issue_counts,
            issue_examples,
            "rejected_schema_field_missing",
            field,
        )
    event_ids = [row.get("event_id") for row in events]
    accepted_ids: dict[str, set[str]] = defaultdict(set)
    rejected_ids: dict[str, set[str]] = defaultdict(set)
    source_event_counts: Counter[tuple[str, str]] = Counter()
    table_kind_counts: Counter[tuple[str, str]] = Counter()
    table_time_counts: dict[str, Counter[str]] = defaultdict(Counter)
    table_phase_counts: Counter[tuple[str, str]] = Counter()
    quality_flag_counts: Counter[str] = Counter()
    table_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for event in events:
        if not event_structure_valid:
            continue
        event_id = event["event_id"]
        source_table = event["source_table"]
        table_rows[source_table].append(event)
        table_kind_counts[(source_table, event["event_kind"])] += 1
        table_phase_counts[(source_table, event["evidence_phase"])] += 1
        accepted_ids[source_table].add(event["source_row_id"])
        source_event_counts[(source_table, event["source_row_id"])] += 1
        for field in ("event_time", "available_time", "recorded_time"):
            table_time_counts[source_table][f"{field}_null"] += int(event[field] is None)
        if event.get("schema_version") != OUTPUT_SCHEMA["version"]:
            _add_issue(issue_counts, issue_examples, "event_schema_version_mismatch", event_id)
        spec = SOURCE_SPECS.get(source_table)
        if spec is None:
            _add_issue(issue_counts, issue_examples, "event_source_not_registered", event_id)
            continue
        if event.get("time_policy_id") != spec.time_policy:
            _add_issue(issue_counts, issue_examples, "time_policy_mismatch", event_id)
        if event.get("evidence_phase") != spec.evidence_phase:
            _add_issue(issue_counts, issue_examples, "evidence_phase_mismatch", event_id)
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
        if source_id_by_ref.get(event["raw_row_ref"]) != event["source_row_id"]:
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
            support_spec = SOURCE_BY_PATH.get(
                (support_parts["module"], support_parts["table"])
            )
            if (
                support_spec is None
                or source_id_by_ref.get(support_ref) != support_id
            ):
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
        actual_times = {
            field: event[field]
            for field in (
                "event_time",
                "source_available_time",
                "available_time",
                "recorded_time",
                "time_resolution_status",
                "time_precision",
                "time_resolution_reasons",
            )
        }
        expected_values = {
            field: expected_times[field]
            for field in actual_times
        }
        if actual_times != expected_values:
            _add_issue(issue_counts, issue_examples, "time_semantics_mismatch", event_id)
        time_flag_codes = {
            "AVAILABLE_BEFORE_EVENT_TIME",
            "AVAILABLE_TIME_DERIVED_FROM_COMPLETION",
            "AVAILABLE_TIME_CLAMPED_TO_EVENT_TIME",
            "AVAILABLE_TIME_UNKNOWN",
        }
        actual_time_flags = {flag for flag in flags if flag in time_flag_codes}
        expected_time_flags = set(expected_times["time_quality_flags"])
        if actual_time_flags != expected_time_flags:
            _add_issue(
                issue_counts,
                issue_examples,
                "time_quality_flags_mismatch",
                event_id,
            )
        if _earlier(event.get("available_time"), event.get("event_time")):
            _add_issue(issue_counts, issue_examples, "effective_time_inversion", event_id)
        if source_table == "hosp.prescriptions" and event["event_time"] is not None:
            matching_support = [
                support_raw
                for _, support_raw, support_parts in support_rows
                if support_parts["module"] == "mimic_iv_hosp"
                and support_parts["table"] == "poe_timeline"
                and _clean(support_raw.get("poe_id")) == _clean(raw.get("poe_id"))
                and _clean(support_raw.get("poe_seq")) == _clean(raw.get("poe_seq"))
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
        elif source_table == "hosp.pharmacy" and event["source_label"] != _expected_pharmacy_label(raw, admission):
            _add_issue(issue_counts, issue_examples, "pharmacy_label_mismatch", event_id)
        elif source_table == "hosp.emar" and event["source_label"] != _expected_emar_label(raw, admission):
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
        if not rejected_structure_valid:
            continue
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
        spec = SOURCE_SPECS.get(source_table)
        if spec is None:
            _add_issue(issue_counts, issue_examples, "rejected_source_not_registered", row["source_row_id"])
            continue
        if source_id_by_ref.get(row["raw_row_ref"]) != row["source_row_id"]:
            _add_issue(issue_counts, issue_examples, "rejected_source_row_id_mismatch", row["source_row_id"])
        if row["subject_id"] != str(admission["subject_id"]) or row["hadm_id"] != str(admission["hadm_id"]):
            _add_issue(issue_counts, issue_examples, "rejected_identity_mismatch", row["source_row_id"])
        expected_reason = _expected_rejection_reason(source_table, raw, admission)
        if row["reason_code"] != expected_reason:
            _add_issue(issue_counts, issue_examples, "rejected_reason_not_reproduced", row["source_row_id"])

    raw_ids: dict[str, set[str]] = defaultdict(set)
    expected_source_counts: Counter[str] = Counter()
    for line_number, admission in records.items():
        for spec in EVENT_SOURCE_REGISTRY:
            rows = admission[spec.module].get(spec.table, [])
            for array_index, raw in enumerate(rows):
                raw_ref = (
                    f"{source_path.name}#L{line_number}/"
                    f"{spec.module}.{spec.table}[{array_index}]"
                )
                source_id = source_id_by_ref[raw_ref]
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
    for spec in EVENT_SOURCE_REGISTRY:
        source_table = spec.source_table
        observed = {
            "input_rows": expected_source_counts[source_table],
            "accepted_source_rows": len(accepted_ids[source_table]),
            "rejected_source_rows": len(rejected_ids[source_table]),
            "events": sum(count for (table, _), count in table_kind_counts.items() if table == source_table),
        }
        declared_row = reconciliation_by_table.get(source_table)
        if declared_row is None:
            reconciliation_differences.append(
                {
                    "source_table": source_table,
                    "observed": observed,
                    "declared": None,
                }
            )
            _add_issue(
                issue_counts,
                issue_examples,
                "source_reconciliation_missing_table",
                source_table,
            )
            continue
        declared = {key: declared_row.get(key) for key in observed}
        if observed != declared:
            reconciliation_differences.append({"source_table": source_table, "observed": observed, "declared": declared})
            _add_issue(
                issue_counts,
                issue_examples,
                "source_reconciliation_mismatch",
                source_table,
            )

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
    for spec in EVENT_SOURCE_REGISTRY:
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
    for key, matched in hash_matches_manifest.items():
        if not matched:
            _add_issue(issue_counts, issue_examples, "manifest_hash_mismatch", key)
    contract_matches_manifest = {
        "output_schema": manifest.get("output_schema") == OUTPUT_SCHEMA,
        "cleaning_logic_version": manifest.get("cleaning_logic_version")
        == CLEANING_LOGIC_VERSION,
        "source_catalog_version": manifest.get("source_catalog", {}).get("version")
        == SOURCE_CATALOG_VERSION,
        "source_catalog_sha256": manifest.get("source_catalog", {}).get("sha256")
        == SOURCE_CATALOG_SHA256,
        "source_catalog_sources": manifest.get("source_catalog", {}).get("sources")
        == len(SOURCE_CATALOG),
        "source_catalog_event_sources": manifest.get("source_catalog", {}).get("event_sources")
        == len(EVENT_SOURCE_REGISTRY),
        "arrow_schema_metadata": (cleaned_table.schema.metadata or {}).get(b"schema")
        == b"clinical_event/1.2.0",
        "event_arrow_schema": _arrow_schema_matches(
            cleaned_table.schema, EVENT_ARROW_SCHEMA
        ),
        "rejected_arrow_schema": _arrow_schema_matches(
            rejected_table.schema, REJECTED_ARROW_SCHEMA
        ),
        "manifest_admissions": manifest.get("counts", {}).get("admissions")
        == len(records),
        "manifest_source_rows": manifest.get("counts", {}).get("source_rows")
        == sum(expected_source_counts.values()),
        "manifest_events": manifest.get("counts", {}).get("events") == len(events),
        "manifest_rejected": manifest.get("counts", {}).get("rejected")
        == len(rejected),
    }
    for key, matched in contract_matches_manifest.items():
        if not matched:
            _add_issue(issue_counts, issue_examples, "manifest_contract_mismatch", key)

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
        content_matches = raw == _restore_raw_record(enriched)
        raw_content_matches += int(content_matches)
        if not content_matches and len(raw_difference_lines) < 20:
            raw_difference_lines.append(line_number)
    if raw_content_matches != len(all_line_numbers):
        issue_counts["raw_content_changed_by_enrichment"] = len(all_line_numbers) - raw_content_matches
    material_issues = {
        key: value
        for key, value in issue_counts.items()
        if value and key != "null_event_id"
    }
    return {
        "audit_schema": "cleaned_events_acceptance_audit/2.0.0",
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
        "contract_matches_manifest": contract_matches_manifest,
        "full_event_lineage_checks": len(events),
        "full_rejected_lineage_checks": len(rejected),
        "upstream_raw_equivalence": {
            "lines": len(all_line_numbers),
            "identity_matches": raw_identity_matches,
            "raw_content_matches_after_reversing_enrichment": raw_content_matches,
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
            and all(contract_matches_manifest.values())
            and not reconciliation_differences
            and required_exact_fields.issubset(columns),
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
    return 0 if result["acceptance"]["can_start_normalization"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
