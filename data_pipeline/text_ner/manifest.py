"""Build a deterministic, model-free text NER input manifest."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any, Iterable

import pyarrow as pa
import pyarrow.parquet as pq

from data_pipeline.event_pipeline.event_cleaning.ids import build_source_row_id
from data_pipeline.event_pipeline.event_cleaning.source_catalog import SOURCE_BY_PATH
from data_pipeline.event_pipeline.event_cleaning.time_resolver import resolved_times
from .contracts import (
    MANIFEST_ARROW_SCHEMA,
    MANIFEST_LOGIC_VERSION,
    MANIFEST_SCHEMA_VERSION,
)
from .sections import TextSection, split_radiology_sections


DEFAULT_PILOT_SIZE = 200
DEFAULT_PILOT_SEED = "text-ner-pilot/1.0.0"
ACCEPTED_INPUT_SCHEMAS = {
    ("mimic_admission_raw", "1.0.0"),
    ("mimic_admission_clinical_readable", "1.0.0"),
}


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _stable_id(prefix: str, *parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts)
    return f"{prefix}:{_sha256_text(payload)[:24]}"


def _json_dump(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _clean(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


def _source_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _validate_text_input_admission(admission: Any, line_number: int) -> None:
    if not isinstance(admission, dict):
        raise ValueError(f"ADMISSION_NOT_OBJECT: line {line_number}")
    schema = admission.get("schema")
    identity = (
        schema.get("name") if isinstance(schema, dict) else None,
        schema.get("version") if isinstance(schema, dict) else None,
    )
    if identity not in ACCEPTED_INPUT_SCHEMAS:
        raise ValueError(f"INPUT_SCHEMA_UNSUPPORTED: line {line_number}: {schema!r}")
    for field in ("subject_id", "hadm_id"):
        if admission.get(field) in (None, ""):
            raise ValueError(f"ADMISSION_ID_MISSING: line {line_number}: {field}")
    required_modules = (
        "mimic_iv_hosp",
        "mimic_iv_icu",
        "mimic_iv_ed",
        "mimic_iv_note",
    )
    for module in required_modules:
        if not isinstance(admission.get(module), dict):
            raise ValueError(f"SOURCE_MODULE_INVALID: line {line_number}: {module}")
    for module, table in (
        ("mimic_iv_ed", "triage"),
        ("mimic_iv_note", "radiology"),
        ("mimic_iv_note", "radiology_detail"),
        ("mimic_iv_note", "discharge"),
    ):
        if not isinstance(admission[module].get(table), list):
            raise ValueError(
                f"TEXT_SOURCE_TABLE_INVALID: line {line_number}: {module}.{table}"
            )


def _raw_row_ref(
    input_name: str,
    line_number: int,
    module: str,
    table: str,
    array_index: int,
) -> str:
    return f"{input_name}#L{line_number}/{module}.{table}[{array_index}]"


def _source_row_id(module: str, table: str, row: dict[str, Any]) -> str:
    spec = SOURCE_BY_PATH[(module, table)]
    return build_source_row_id(spec, row)


@dataclass
class Document:
    subject_id: str
    hadm_id: str
    source_module: str
    source_table: str
    source_row_id: str
    source_array_index: int
    jsonl_line_number: int
    raw_row_ref: str
    text_field: str
    note_id: str | None
    note_type: str | None
    parent_note_id: str | None
    addendum_note_ids: list[str]
    text: str
    event_time: str | None
    source_available_time: str | None
    available_time: str | None
    recorded_time: str | None
    time_resolution_status: str
    time_policy_id: str
    time_resolution_reasons: list[str]
    evidence_phase: str
    quality_flags: list[str]
    inclusion_status: str
    reason_code: str
    sections: list[TextSection]
    document_id: str
    pilot_stratum: str
    pilot_document_selected: bool = False
    pilot_selection_rank: int | None = None


def _length_bucket(length: int) -> str:
    if length < 256:
        return "lt256"
    if length < 768:
        return "256_767"
    if length < 2048:
        return "768_2047"
    return "ge2048"


def _radiology_relationships(note_detail: list[dict[str, Any]]) -> tuple[dict[str, str], dict[str, list[str]]]:
    parent_by_note: dict[str, str] = {}
    addenda_by_note: dict[str, list[str]] = defaultdict(list)
    for row in note_detail:
        note_id = _clean(row.get("note_id"))
        field_name = _clean(row.get("field_name"))
        field_value = _clean(row.get("field_value"))
        if not note_id or not field_value:
            continue
        if field_name == "parent_note_id":
            parent_by_note[note_id] = field_value
        elif field_name == "addendum_note_id":
            addenda_by_note[note_id].append(field_value)
    return parent_by_note, {
        note_id: sorted(set(values)) for note_id, values in addenda_by_note.items()
    }


def _document_common(
    *,
    admission: dict[str, Any],
    row: dict[str, Any],
    module: str,
    table: str,
    array_index: int,
    line_number: int,
    input_name: str,
    text_field: str,
    text: str,
    note_id: str | None,
) -> dict[str, Any]:
    source_id = _source_row_id(module, table, row)
    return {
        "subject_id": str(admission["subject_id"]),
        "hadm_id": str(admission["hadm_id"]),
        "source_module": module,
        "source_table": SOURCE_BY_PATH[(module, table)].source_table,
        "source_row_id": source_id,
        "source_array_index": array_index,
        "jsonl_line_number": line_number,
        "raw_row_ref": _raw_row_ref(
            input_name, line_number, module, table, array_index
        ),
        "text_field": text_field,
        "note_id": note_id,
        "text": text,
        "document_id": _stable_id("doc", source_id, text_field),
    }


def _documents_for_admission(
    admission: dict[str, Any], *, line_number: int, input_name: str
) -> list[Document]:
    documents: list[Document] = []
    ed = admission["mimic_iv_ed"]
    note = admission["mimic_iv_note"]

    for index, row in enumerate(ed.get("triage", [])):
        text = _source_text(row.get("chiefcomplaint"))
        common = _document_common(
            admission=admission,
            row=row,
            module="mimic_iv_ed",
            table="triage",
            array_index=index,
            line_number=line_number,
            input_name=input_name,
            text_field="chiefcomplaint",
            text=text,
            note_id=None,
        )
        included = bool(text.strip())
        documents.append(
            Document(
                **common,
                note_type="ED_CHIEF_COMPLAINT",
                parent_note_id=None,
                addendum_note_ids=[],
                event_time=None,
                source_available_time=None,
                available_time=None,
                recorded_time=None,
                time_resolution_status="unresolved",
                time_policy_id="triage_no_time_v1",
                time_resolution_reasons=["time_unavailable_in_source"],
                evidence_phase="source_event",
                quality_flags=["AVAILABLE_TIME_UNKNOWN", "TIME_UNAVAILABLE_IN_SOURCE"],
                inclusion_status="included" if included else "excluded",
                reason_code="NER_ELIGIBLE_ED_CHIEF_COMPLAINT" if included else "EMPTY_TEXT",
                sections=[TextSection("chief_complaint", 0, 0, len(text))] if included else [],
                pilot_stratum="ed:chief_complaint",
            )
        )

    parent_by_note, addenda_by_note = _radiology_relationships(
        note.get("radiology_detail", [])
    )
    for index, row in enumerate(note.get("radiology", [])):
        text = _source_text(row.get("text"))
        note_id = _clean(row.get("note_id"))
        times = resolved_times(
            event_time=row.get("charttime"),
            available_time=row.get("storetime"),
            recorded_time=row.get("storetime"),
        )
        sections = split_radiology_sections(text)
        included = bool(text.strip() and sections)
        note_type = _clean(row.get("note_type")) or "RR"
        profile = "sectioned" if len(sections) > 1 else "full_report"
        common = _document_common(
            admission=admission,
            row=row,
            module="mimic_iv_note",
            table="radiology",
            array_index=index,
            line_number=line_number,
            input_name=input_name,
            text_field="text",
            text=text,
            note_id=note_id,
        )
        documents.append(
            Document(
                **common,
                note_type=note_type,
                parent_note_id=parent_by_note.get(note_id or ""),
                addendum_note_ids=addenda_by_note.get(note_id or "", []),
                event_time=times["event_time"],
                source_available_time=times["source_available_time"],
                available_time=times["available_time"],
                recorded_time=times["recorded_time"],
                time_resolution_status=times["time_resolution_status"],
                time_policy_id="radiology_chart_store_v2",
                time_resolution_reasons=list(times["time_resolution_reasons"]),
                evidence_phase="source_event",
                quality_flags=list(times["time_quality_flags"]),
                inclusion_status="included" if included else "excluded",
                reason_code="NER_ELIGIBLE_RADIOLOGY" if included else "EMPTY_TEXT",
                sections=sections,
                pilot_stratum=(
                    f"radiology:{note_type}:{_length_bucket(len(text))}:{profile}"
                ),
            )
        )

    for index, row in enumerate(note.get("discharge", [])):
        text = _source_text(row.get("text"))
        note_id = _clean(row.get("note_id"))
        times = resolved_times(
            event_time=row.get("charttime"),
            available_time=row.get("storetime"),
            recorded_time=row.get("storetime"),
        )
        common = _document_common(
            admission=admission,
            row=row,
            module="mimic_iv_note",
            table="discharge",
            array_index=index,
            line_number=line_number,
            input_name=input_name,
            text_field="text",
            text=text,
            note_id=note_id,
        )
        documents.append(
            Document(
                **common,
                note_type=_clean(row.get("note_type")) or "DS",
                parent_note_id=None,
                addendum_note_ids=[],
                event_time=times["event_time"],
                source_available_time=times["source_available_time"],
                available_time=times["available_time"],
                recorded_time=times["recorded_time"],
                time_resolution_status=times["time_resolution_status"],
                time_policy_id="discharge_post_hoc_v2",
                time_resolution_reasons=list(times["time_resolution_reasons"]),
                evidence_phase="post_hoc",
                quality_flags=list(times["time_quality_flags"]),
                inclusion_status="excluded",
                reason_code="POST_HOC_DISCHARGE",
                sections=[],
                pilot_stratum="excluded:discharge",
            )
        )
    return documents


def _rank_key(document: Document, seed: str) -> tuple[str, str]:
    return (_sha256_text(f"{seed}\x1f{document.document_id}"), document.document_id)


def _stratified_select(
    documents: Iterable[Document], target: int, seed: str
) -> list[Document]:
    groups: dict[str, list[Document]] = defaultdict(list)
    for document in documents:
        groups[document.pilot_stratum].append(document)
    for values in groups.values():
        values.sort(key=lambda item: _rank_key(item, seed))
    selected: list[Document] = []
    strata = sorted(groups)
    while len(selected) < target:
        progressed = False
        for stratum in strata:
            if groups[stratum] and len(selected) < target:
                selected.append(groups[stratum].pop(0))
                progressed = True
        if not progressed:
            break
    return selected


def _select_pilot(documents: list[Document], pilot_size: int, seed: str) -> None:
    eligible = [item for item in documents if item.inclusion_status == "included"]
    if len(eligible) < pilot_size:
        raise ValueError(
            f"PILOT_SIZE_EXCEEDS_ELIGIBLE_DOCUMENTS: {pilot_size} > {len(eligible)}"
        )
    ed = [item for item in eligible if item.source_table == "ed.triage"]
    radiology = [item for item in eligible if item.source_table == "note.radiology"]
    ed_target = min(len(ed), pilot_size // 2)
    radiology_target = pilot_size - ed_target
    if len(radiology) < radiology_target:
        radiology_target = len(radiology)
        ed_target = pilot_size - radiology_target
    if len(ed) < ed_target:
        raise ValueError("PILOT_SOURCE_BALANCE_UNSATISFIABLE")

    selected_ed = sorted(ed, key=lambda item: _rank_key(item, seed))[:ed_target]
    selected_radiology = _stratified_select(radiology, radiology_target, seed)
    selected = selected_ed + selected_radiology
    if len(selected) != pilot_size:
        raise ValueError("PILOT_SELECTION_INCOMPLETE")
    for rank, document in enumerate(selected, start=1):
        document.pilot_document_selected = True
        document.pilot_selection_rank = rank


def _rows(documents: list[Document]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for document in documents:
        source_hash = _sha256_text(document.text)
        sections: list[TextSection | None] = (
            list(document.sections) if document.inclusion_status == "included" else [None]
        )
        for section in sections:
            if section is None:
                section_id = None
                span_start = None
                span_end = None
                span_hash = None
                span_length = None
                section_name = None
                section_ordinal = None
                row_id = _stable_id("mrow", document.document_id, "excluded")
            else:
                section_id = _stable_id(
                    "sec",
                    document.document_id,
                    section.ordinal,
                    section.name,
                    section.start,
                    section.end,
                )
                span = document.text[section.start : section.end]
                span_start = section.start
                span_end = section.end
                span_hash = _sha256_text(span)
                span_length = len(span)
                section_name = section.name
                section_ordinal = section.ordinal
                row_id = _stable_id("mrow", document.document_id, section_id)
            result.append(
                {
                    "schema_version": MANIFEST_SCHEMA_VERSION,
                    "manifest_row_id": row_id,
                    "document_id": document.document_id,
                    "section_id": section_id,
                    "subject_id": document.subject_id,
                    "hadm_id": document.hadm_id,
                    "split_group_id": document.subject_id,
                    "source_module": document.source_module,
                    "source_table": document.source_table,
                    "source_row_id": document.source_row_id,
                    "source_array_index": document.source_array_index,
                    "jsonl_line_number": document.jsonl_line_number,
                    "raw_row_ref": document.raw_row_ref,
                    "text_field": document.text_field,
                    "note_id": document.note_id,
                    "note_type": document.note_type,
                    "parent_note_id": document.parent_note_id,
                    "addendum_note_ids": document.addendum_note_ids,
                    "event_time": document.event_time,
                    "source_available_time": document.source_available_time,
                    "available_time": document.available_time,
                    "recorded_time": document.recorded_time,
                    "time_resolution_status": document.time_resolution_status,
                    "time_policy_id": document.time_policy_id,
                    "time_resolution_reasons": document.time_resolution_reasons,
                    "evidence_phase": document.evidence_phase,
                    "quality_flags": document.quality_flags,
                    "section_name": section_name,
                    "section_ordinal": section_ordinal,
                    "span_start": span_start,
                    "span_end": span_end,
                    "source_text_character_count": len(document.text),
                    "span_character_count": span_length,
                    "source_text_sha256": source_hash,
                    "span_sha256": span_hash,
                    "inclusion_status": document.inclusion_status,
                    "reason_code": document.reason_code,
                    "pilot_document_selected": document.pilot_document_selected,
                    "pilot_selection_rank": document.pilot_selection_rank,
                    "pilot_stratum": document.pilot_stratum,
                }
            )
    return sorted(result, key=lambda row: row["manifest_row_id"])


def build_manifest_rows(
    input_path: Path, *, pilot_size: int = DEFAULT_PILOT_SIZE, pilot_seed: str = DEFAULT_PILOT_SEED
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    input_path = Path(input_path)
    documents: list[Document] = []
    admissions = 0
    with input_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            admission = json.loads(line)
            _validate_text_input_admission(admission, line_number)
            admissions += 1
            documents.extend(
                _documents_for_admission(
                    admission, line_number=line_number, input_name=input_path.name
                )
            )
    _select_pilot(documents, pilot_size, pilot_seed)
    rows = _rows(documents)
    document_counts = Counter(
        (item.source_table, item.inclusion_status) for item in documents
    )
    pilot_documents = [item for item in documents if item.pilot_document_selected]
    summary = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "logic_version": MANIFEST_LOGIC_VERSION,
        "admissions": admissions,
        "subjects": len({item.subject_id for item in documents}),
        "documents": len(documents),
        "manifest_rows": len(rows),
        "included_documents": sum(item.inclusion_status == "included" for item in documents),
        "excluded_documents": sum(item.inclusion_status == "excluded" for item in documents),
        "included_text_units": sum(row["inclusion_status"] == "included" for row in rows),
        "document_counts": {
            f"{source_table}:{status}": count
            for (source_table, status), count in sorted(document_counts.items())
        },
        "reason_counts": dict(sorted(Counter(item.reason_code for item in documents).items())),
        "pilot": {
            "requested_documents": pilot_size,
            "selected_documents": len(pilot_documents),
            "selected_text_units": sum(
                row["pilot_document_selected"] and row["inclusion_status"] == "included"
                for row in rows
            ),
            "subjects": len({item.subject_id for item in pilot_documents}),
            "source_counts": dict(
                sorted(Counter(item.source_table for item in pilot_documents).items())
            ),
            "stratum_counts": dict(
                sorted(Counter(item.pilot_stratum for item in pilot_documents).items())
            ),
            "seed": pilot_seed,
            "data_split_created": False,
            "split_group_field": "subject_id",
        },
        "model_calls": 0,
    }
    return rows, summary


def prepare_manifest(
    input_path: Path,
    output_directory: Path,
    *,
    pilot_size: int = DEFAULT_PILOT_SIZE,
    pilot_seed: str = DEFAULT_PILOT_SEED,
) -> dict[str, Any]:
    """Atomically publish a deterministic manifest and run metadata."""
    input_path = Path(input_path).resolve()
    output_directory = Path(output_directory).resolve()
    if output_directory.exists():
        raise FileExistsError(f"output directory already exists: {output_directory}")
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{output_directory.name}.", dir=output_directory.parent
        )
    )
    try:
        rows, summary = build_manifest_rows(
            input_path, pilot_size=pilot_size, pilot_seed=pilot_seed
        )
        table = pa.Table.from_pylist(rows, schema=MANIFEST_ARROW_SCHEMA)
        manifest_path = temporary / "text_ner_input_manifest.parquet"
        pq.write_table(
            table,
            manifest_path,
            compression="zstd",
            use_dictionary=True,
            write_statistics=True,
            row_group_size=5000,
        )
        summary_path = temporary / "text_ner_input_manifest_summary.json"
        _json_dump(summary_path, summary)
        input_sha256 = _sha256_file(input_path)
        config = {
            "pilot_size": pilot_size,
            "pilot_seed": pilot_seed,
            "model_execution": "disabled",
        }
        run_id = _stable_id(
            "run",
            input_sha256,
            MANIFEST_LOGIC_VERSION,
            json.dumps(config, sort_keys=True),
        )
        run_manifest = {
            "schema": {"name": "text_ner_input_run", "version": "1.0.0"},
            "run_id": run_id,
            "logic_version": MANIFEST_LOGIC_VERSION,
            "input": {
                "filename": input_path.name,
                "sha256": input_sha256,
                "bytes": input_path.stat().st_size,
            },
            "configuration": config,
            "outputs": {
                "text_ner_input_manifest.parquet": _sha256_file(manifest_path),
                "text_ner_input_manifest_summary.json": _sha256_file(summary_path),
            },
            "model": {
                "calls": 0,
                "provider": None,
                "name": None,
            },
        }
        _json_dump(temporary / "run_manifest.json", run_manifest)
        temporary.replace(output_directory)
        return run_manifest
    except Exception:
        resolved_temporary = temporary.resolve()
        if output_directory.parent.resolve() in resolved_temporary.parents:
            shutil.rmtree(resolved_temporary, ignore_errors=True)
        raise
