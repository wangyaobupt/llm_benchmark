"""Build analysis and traceability Parquet datasets without source-data loss."""

from __future__ import annotations

from collections import Counter
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
from itertools import zip_longest
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Iterable, Iterator

import pyarrow as pa
import pyarrow.parquet as pq

from data_pipeline.event_pipeline.event_cleaning.source_catalog import SOURCE_BY_PATH


AGGREGATION_SCHEMA_VERSION = "event-aggregation/1.0.0"
SOURCE_RECORD_SCHEMA_VERSION = "event-source-record/1.0.0"
MANIFEST_SCHEMA_VERSION = "event-aggregation-manifest/1.0.0"
QUALITY_SCHEMA_VERSION = "event-aggregation-quality/1.0.0"

RAW_REF_RE = re.compile(
    r"^(?P<filename>[^#\\/]+)#L(?P<line>\d+)/"
    r"(?P<module>[A-Za-z0-9_]+)\.(?P<table>[A-Za-z0-9_]+)"
    r"\[(?P<index>\d+)\]$"
)

TEXT_FIELDS: dict[tuple[str, str], tuple[str, str]] = {
    ("mimic_iv_hosp", "labevents"): ("comments", "laboratory_comment"),
    ("mimic_iv_hosp", "microbiologyevents"): (
        "comments",
        "microbiology_comment",
    ),
    ("mimic_iv_ed", "triage"): ("chiefcomplaint", "chief_complaint"),
    ("mimic_iv_note", "radiology"): ("text", "radiology_report"),
    ("mimic_iv_note", "discharge"): ("text", "discharge_summary"),
}

REQUIRED_EVENT_COLUMNS = {
    "event_id",
    "subject_id",
    "hadm_id",
    "source_module",
    "source_table",
    "source_array_index",
    "jsonl_line_number",
    "raw_row_ref",
    "supporting_raw_row_refs",
}

SOURCE_RECORD_SCHEMA = pa.schema(
    [
        ("schema_version", pa.string()),
        ("source_record_id", pa.string()),
        ("subject_id", pa.string()),
        ("hadm_id", pa.string()),
        ("jsonl_line_number", pa.int64()),
        ("source_module", pa.string()),
        ("source_table", pa.string()),
        ("source_table_name", pa.string()),
        ("source_array_index", pa.int64()),
        ("raw_row_ref", pa.string()),
        ("source_role", pa.string()),
        ("source_origin", pa.string()),
        ("source_text_field", pa.string()),
        ("source_text_kind", pa.string()),
        ("source_text", pa.string()),
        ("source_text_sha256", pa.string()),
        ("clinical_readable_record_json", pa.string()),
        ("raw_record_json", pa.string()),
    ],
    metadata={b"schema": SOURCE_RECORD_SCHEMA_VERSION.encode("ascii")},
)

PROCESSED_EXTRA_FIELDS = (
    pa.field("aggregation_schema_version", pa.string()),
    pa.field("source_record_id", pa.string()),
    pa.field("source_text_field", pa.string()),
    pa.field("source_text_kind", pa.string()),
    pa.field("source_text", pa.string()),
    pa.field("source_text_sha256", pa.string()),
    pa.field("supporting_source_record_ids", pa.list_(pa.string())),
)

TRACEABLE_EXTRA_FIELDS = (
    pa.field("clinical_readable_record_json", pa.string()),
    pa.field("raw_record_json", pa.string()),
)


class AggregationError(ValueError):
    """Fail-closed aggregation error with a stable reason code."""

    def __init__(self, reason_code: str, message: str):
        super().__init__(f"{reason_code}: {message}")
        self.reason_code = reason_code


class _BufferedWriter:
    def __init__(self, path: Path, schema: pa.Schema, batch_size: int):
        self.path = path
        self.schema = schema
        self.batch_size = batch_size
        self.rows: list[dict[str, Any]] = []
        self.writer = pq.ParquetWriter(
            path,
            schema,
            compression="zstd",
            compression_level=9,
            use_dictionary=True,
            write_statistics=True,
        )

    def append(self, row: dict[str, Any]) -> None:
        self.rows.append(row)
        if len(self.rows) >= self.batch_size:
            self.flush()

    def flush(self) -> None:
        if not self.rows:
            return
        self.writer.write_table(pa.Table.from_pylist(self.rows, schema=self.schema))
        self.rows.clear()

    def close(self) -> None:
        self.flush()
        self.writer.close()

    def __enter__(self) -> "_BufferedWriter":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.writer.close() if exc_type is not None else self.close()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _source_record_id(raw_row_ref: str) -> str:
    return f"srec:{_sha256_text(raw_row_ref)[:24]}"


def _table_path(module: str, table: str) -> str:
    prefix = {
        "mimic_iv_hosp": "hosp",
        "mimic_iv_icu": "icu",
        "mimic_iv_ed": "ed",
        "mimic_iv_note": "note",
    }.get(module)
    if prefix is None:
        raise AggregationError("SOURCE_MODULE_UNKNOWN", module)
    return f"{prefix}.{table}"


def _source_text(
    module: str, table: str, row: dict[str, Any]
) -> tuple[str | None, str | None, str | None, str | None]:
    definition = TEXT_FIELDS.get((module, table))
    if definition is None:
        return None, None, None, None
    field, kind = definition
    value = row.get(field)
    text = None if value is None else str(value)
    if text is not None and not text.strip():
        text = None
    return field, kind, text, _sha256_text(text) if text is not None else None


def _raw_ref_parts(raw_row_ref: str, expected_filename: str) -> tuple[int, str, str, int]:
    match = RAW_REF_RE.fullmatch(raw_row_ref)
    if match is None:
        raise AggregationError("RAW_ROW_REF_INVALID", raw_row_ref)
    if match.group("filename") != expected_filename:
        raise AggregationError(
            "RAW_ROW_REF_FILENAME_MISMATCH",
            f"{match.group('filename')} != {expected_filename}",
        )
    return (
        int(match.group("line")),
        match.group("module"),
        match.group("table"),
        int(match.group("index")),
    )


def _resolve_row(
    admission: dict[str, Any], module: str, table: str, index: int, raw_row_ref: str
) -> dict[str, Any]:
    module_value = admission.get(module)
    if not isinstance(module_value, dict):
        raise AggregationError("SOURCE_MODULE_MISSING", f"{raw_row_ref}: {module}")
    rows = module_value.get(table)
    if not isinstance(rows, list):
        raise AggregationError("SOURCE_TABLE_MISSING", f"{raw_row_ref}: {module}.{table}")
    if index < 0 or index >= len(rows):
        raise AggregationError(
            "SOURCE_ARRAY_INDEX_OUT_OF_RANGE",
            f"{raw_row_ref}: {index} >= {len(rows)}",
        )
    row = rows[index]
    if not isinstance(row, dict):
        raise AggregationError("SOURCE_ROW_NOT_OBJECT", raw_row_ref)
    return row


def _paired_admissions(
    source_path: Path, raw_path: Path
) -> Iterator[tuple[int, dict[str, Any], dict[str, Any]]]:
    with source_path.open("r", encoding="utf-8") as source_handle, raw_path.open(
        "r", encoding="utf-8"
    ) as raw_handle:
        for line_number, pair in enumerate(
            zip_longest(source_handle, raw_handle), start=1
        ):
            source_line, raw_line = pair
            if source_line is None or raw_line is None:
                raise AggregationError(
                    "SOURCE_JSONL_LINE_COUNT_MISMATCH", str(line_number)
                )
            if not source_line.strip() or not raw_line.strip():
                raise AggregationError("SOURCE_JSONL_EMPTY_LINE", str(line_number))
            try:
                source = json.loads(source_line)
                raw = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                raise AggregationError(
                    "SOURCE_JSONL_INVALID", f"line {line_number}: {exc}"
                ) from exc
            source_identity = (str(source.get("subject_id")), str(source.get("hadm_id")))
            raw_identity = (str(raw.get("subject_id")), str(raw.get("hadm_id")))
            if source_identity != raw_identity:
                raise AggregationError(
                    "SOURCE_JSONL_IDENTITY_MISMATCH",
                    f"line {line_number}: {source_identity} != {raw_identity}",
                )
            yield line_number, source, raw


def _validate_table_pair(
    module: str,
    table: str,
    source_rows: list[Any],
    raw_admission: dict[str, Any],
    line_number: int,
) -> list[Any] | None:
    spec = SOURCE_BY_PATH.get((module, table))
    if spec is None:
        raise AggregationError(
            "SOURCE_TABLE_NOT_REGISTERED", f"line {line_number}: {module}.{table}"
        )
    raw_module = raw_admission.get(module, {})
    raw_rows = raw_module.get(table) if isinstance(raw_module, dict) else None
    if spec.origin == "derived":
        if raw_rows not in (None, []):
            raise AggregationError(
                "DERIVED_TABLE_PRESENT_IN_RAW_SOURCE",
                f"line {line_number}: {module}.{table}",
            )
        return None
    if not isinstance(raw_rows, list):
        raise AggregationError(
            "RAW_SOURCE_TABLE_MISSING", f"line {line_number}: {module}.{table}"
        )
    if len(source_rows) != len(raw_rows):
        raise AggregationError(
            "RAW_SOURCE_TABLE_COUNT_MISMATCH",
            f"line {line_number}: {module}.{table} {len(source_rows)} != {len(raw_rows)}",
        )
    return raw_rows


def _extract_source_records(
    source_path: Path,
    raw_path: Path,
    output_path: Path,
    batch_size: int,
) -> dict[str, Any]:
    table_counts: Counter[str] = Counter()
    text_counts: Counter[str] = Counter()
    text_characters: Counter[str] = Counter()
    role_counts: Counter[str] = Counter()
    origin_counts: Counter[str] = Counter()
    source_rows_total = 0
    admissions = 0
    with _BufferedWriter(output_path, SOURCE_RECORD_SCHEMA, batch_size) as writer:
        for line_number, source_admission, raw_admission in _paired_admissions(
            source_path, raw_path
        ):
            admissions += 1
            subject_id = str(source_admission["subject_id"])
            hadm_id = str(source_admission["hadm_id"])
            for module, module_value in source_admission.items():
                if not module.startswith("mimic_iv_"):
                    continue
                if not isinstance(module_value, dict):
                    raise AggregationError(
                        "SOURCE_MODULE_NOT_OBJECT", f"line {line_number}: {module}"
                    )
                for table, rows in module_value.items():
                    if not isinstance(rows, list):
                        raise AggregationError(
                            "SOURCE_TABLE_NOT_ARRAY",
                            f"line {line_number}: {module}.{table}",
                        )
                    raw_rows = _validate_table_pair(
                        module, table, rows, raw_admission, line_number
                    )
                    spec = SOURCE_BY_PATH[(module, table)]
                    table_path = _table_path(module, table)
                    for index, source_row in enumerate(rows):
                        if not isinstance(source_row, dict):
                            raise AggregationError(
                                "SOURCE_ROW_NOT_OBJECT",
                                f"line {line_number}: {module}.{table}[{index}]",
                            )
                        raw_row_ref = (
                            f"{source_path.name}#L{line_number}/"
                            f"{module}.{table}[{index}]"
                        )
                        field, kind, text, text_sha256 = _source_text(
                            module, table, source_row
                        )
                        raw_row = raw_rows[index] if raw_rows is not None else None
                        writer.append(
                            {
                                "schema_version": SOURCE_RECORD_SCHEMA_VERSION,
                                "source_record_id": _source_record_id(raw_row_ref),
                                "subject_id": subject_id,
                                "hadm_id": hadm_id,
                                "jsonl_line_number": line_number,
                                "source_module": module,
                                "source_table": table_path,
                                "source_table_name": table,
                                "source_array_index": index,
                                "raw_row_ref": raw_row_ref,
                                "source_role": spec.role,
                                "source_origin": spec.origin,
                                "source_text_field": field,
                                "source_text_kind": kind,
                                "source_text": text,
                                "source_text_sha256": text_sha256,
                                "clinical_readable_record_json": _canonical_json(
                                    source_row
                                ),
                                "raw_record_json": (
                                    _canonical_json(raw_row)
                                    if raw_row is not None
                                    else None
                                ),
                            }
                        )
                        source_rows_total += 1
                        table_counts[table_path] += 1
                        role_counts[spec.role] += 1
                        origin_counts[spec.origin] += 1
                        if text is not None:
                            text_counts[table_path] += 1
                            text_characters[table_path] += len(text)
    return {
        "admissions": admissions,
        "source_records": source_rows_total,
        "source_table_counts": dict(sorted(table_counts.items())),
        "source_role_counts": dict(sorted(role_counts.items())),
        "source_origin_counts": dict(sorted(origin_counts.items())),
        "source_text_record_counts": dict(sorted(text_counts.items())),
        "source_text_character_counts": dict(sorted(text_characters.items())),
    }


class _AdmissionCursor:
    def __init__(self, source_path: Path, raw_path: Path):
        self._iterator = _paired_admissions(source_path, raw_path)
        self.line_number = 0
        self.source: dict[str, Any] | None = None
        self.raw: dict[str, Any] | None = None

    def get(self, target_line: int) -> tuple[dict[str, Any], dict[str, Any]]:
        if target_line < self.line_number:
            raise AggregationError(
                "NORMALIZED_EVENTS_NOT_SOURCE_ORDERED",
                f"{target_line} after {self.line_number}",
            )
        while self.line_number < target_line:
            try:
                self.line_number, self.source, self.raw = next(self._iterator)
            except StopIteration as exc:
                raise AggregationError(
                    "NORMALIZED_EVENT_LINE_NOT_FOUND", str(target_line)
                ) from exc
        assert self.source is not None and self.raw is not None
        return self.source, self.raw


def _raw_counterpart(
    raw_admission: dict[str, Any], module: str, table: str, index: int
) -> dict[str, Any] | None:
    spec = SOURCE_BY_PATH.get((module, table))
    if spec is None:
        raise AggregationError("SOURCE_TABLE_NOT_REGISTERED", f"{module}.{table}")
    if spec.origin == "derived":
        return None
    raw_module = raw_admission.get(module)
    if not isinstance(raw_module, dict):
        raise AggregationError("RAW_SOURCE_MODULE_MISSING", module)
    raw_rows = raw_module.get(table)
    if not isinstance(raw_rows, list) or index >= len(raw_rows):
        raise AggregationError(
            "RAW_SOURCE_ROW_NOT_FOUND", f"{module}.{table}[{index}]"
        )
    raw_row = raw_rows[index]
    if not isinstance(raw_row, dict):
        raise AggregationError(
            "RAW_SOURCE_ROW_NOT_OBJECT", f"{module}.{table}[{index}]"
        )
    return raw_row


def _append_event_outputs(
    normalized_path: Path,
    source_path: Path,
    raw_path: Path,
    processed_path: Path,
    traceable_path: Path,
    batch_size: int,
) -> dict[str, Any]:
    parquet = pq.ParquetFile(normalized_path)
    normalized_schema = parquet.schema_arrow
    missing = REQUIRED_EVENT_COLUMNS - set(normalized_schema.names)
    if missing:
        raise AggregationError(
            "NORMALIZED_EVENT_COLUMNS_MISSING", ",".join(sorted(missing))
        )
    processed_schema = pa.schema(
        [*normalized_schema, *PROCESSED_EXTRA_FIELDS],
        metadata={b"schema": AGGREGATION_SCHEMA_VERSION.encode("ascii")},
    )
    traceable_schema = pa.schema(
        [*processed_schema, *TRACEABLE_EXTRA_FIELDS],
        metadata={b"schema": AGGREGATION_SCHEMA_VERSION.encode("ascii")},
    )
    cursor = _AdmissionCursor(source_path, raw_path)
    event_count = 0
    subjects: set[str] = set()
    admissions: set[tuple[str, str]] = set()
    source_refs: set[str] = set()
    text_event_counts: Counter[str] = Counter()
    with ExitStack() as stack:
        processed_writer = stack.enter_context(
            _BufferedWriter(processed_path, processed_schema, batch_size)
        )
        traceable_writer = stack.enter_context(
            _BufferedWriter(traceable_path, traceable_schema, batch_size)
        )
        for batch in parquet.iter_batches(batch_size=batch_size):
            for event in batch.to_pylist():
                raw_row_ref = event["raw_row_ref"]
                line_number, module, table, index = _raw_ref_parts(
                    raw_row_ref, source_path.name
                )
                expected = (
                    int(event["jsonl_line_number"]),
                    event["source_module"],
                    event["source_table"].split(".", 1)[-1],
                    int(event["source_array_index"]),
                )
                observed = (line_number, module, table, index)
                if observed != expected:
                    raise AggregationError(
                        "NORMALIZED_EVENT_LINEAGE_MISMATCH",
                        f"{event['event_id']}: {observed} != {expected}",
                    )
                source_admission, raw_admission = cursor.get(line_number)
                source_row = _resolve_row(
                    source_admission, module, table, index, raw_row_ref
                )
                if str(source_admission.get("subject_id")) != str(event["subject_id"]):
                    raise AggregationError(
                        "NORMALIZED_EVENT_SUBJECT_MISMATCH", event["event_id"]
                    )
                if str(source_admission.get("hadm_id")) != str(event["hadm_id"]):
                    raise AggregationError(
                        "NORMALIZED_EVENT_ADMISSION_MISMATCH", event["event_id"]
                    )
                raw_row = _raw_counterpart(raw_admission, module, table, index)
                field, kind, text, text_sha256 = _source_text(
                    module, table, source_row
                )
                supporting_ids: list[str] = []
                for supporting_ref in event["supporting_raw_row_refs"] or []:
                    support_line, support_module, support_table, support_index = (
                        _raw_ref_parts(supporting_ref, source_path.name)
                    )
                    if support_line != line_number:
                        raise AggregationError(
                            "SUPPORTING_SOURCE_CROSSES_ADMISSION",
                            f"{event['event_id']}: {supporting_ref}",
                        )
                    _resolve_row(
                        source_admission,
                        support_module,
                        support_table,
                        support_index,
                        supporting_ref,
                    )
                    supporting_ids.append(_source_record_id(supporting_ref))
                enriched = {
                    **event,
                    "aggregation_schema_version": AGGREGATION_SCHEMA_VERSION,
                    "source_record_id": _source_record_id(raw_row_ref),
                    "source_text_field": field,
                    "source_text_kind": kind,
                    "source_text": text,
                    "source_text_sha256": text_sha256,
                    "supporting_source_record_ids": supporting_ids,
                }
                processed_writer.append(enriched)
                traceable_writer.append(
                    {
                        **enriched,
                        "clinical_readable_record_json": _canonical_json(source_row),
                        "raw_record_json": (
                            _canonical_json(raw_row) if raw_row is not None else None
                        ),
                    }
                )
                event_count += 1
                subjects.add(str(event["subject_id"]))
                admissions.add((str(event["subject_id"]), str(event["hadm_id"])))
                source_refs.add(raw_row_ref)
                if text is not None:
                    text_event_counts[event["source_table"]] += 1
    return {
        "events": event_count,
        "subjects": len(subjects),
        "admissions": len(admissions),
        "event_source_records": len(source_refs),
        "source_text_event_counts": dict(sorted(text_event_counts.items())),
        "processed_schema": processed_schema,
        "traceable_schema": traceable_schema,
    }


def _iter_batches(path: Path, columns: Iterable[str], batch_size: int) -> Iterator[pa.RecordBatch]:
    yield from pq.ParquetFile(path).iter_batches(
        columns=list(columns), batch_size=batch_size
    )


def _assert_event_columns_unchanged(
    normalized_path: Path, output_path: Path, batch_size: int
) -> None:
    columns = pq.ParquetFile(normalized_path).schema_arrow.names
    original_batches = _iter_batches(normalized_path, columns, batch_size)
    output_batches = _iter_batches(output_path, columns, batch_size)
    for batch_number, pair in enumerate(
        zip_longest(original_batches, output_batches), start=1
    ):
        original, output = pair
        if original is None or output is None or not original.equals(output):
            raise AggregationError(
                "NORMALIZED_EVENT_FIELDS_CHANGED",
                f"{output_path.name}: batch {batch_number}",
            )


def _resolve_inputs(input_directory: Path) -> dict[str, Any]:
    input_directory = input_directory.resolve()
    event_output = input_directory / "event_pipeline_output"
    workflow_path = event_output / "workflow_manifest.json"
    normalized_path = event_output / "normalization" / "normalized_events.parquet"
    if not workflow_path.is_file() or not normalized_path.is_file():
        raise AggregationError("EVENT_OUTPUT_INCOMPLETE", str(event_output))
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    acceptance = workflow.get("acceptance", {})
    if not all(
        acceptance.get(key)
        for key in ("cleaning", "normalization", "reproducible")
    ):
        raise AggregationError("EVENT_OUTPUT_NOT_ACCEPTED", str(workflow_path))
    source_name = workflow.get("inputs", {}).get("source_jsonl")
    raw_name = workflow.get("inputs", {}).get("raw_source_jsonl")
    if not source_name or not raw_name:
        raise AggregationError("WORKFLOW_SOURCE_PATH_MISSING", str(workflow_path))
    source_path = input_directory / source_name
    raw_path = input_directory / raw_name
    for path in (source_path, raw_path):
        if not path.is_file():
            raise AggregationError("SOURCE_JSONL_NOT_FOUND", str(path))
    hashes = {
        "source_jsonl": _sha256_file(source_path),
        "raw_source_jsonl": _sha256_file(raw_path),
        "normalized_events": _sha256_file(normalized_path),
    }
    expected_hashes = {
        "source_jsonl": workflow["inputs"].get("source_jsonl_sha256"),
        "raw_source_jsonl": workflow["inputs"].get("raw_source_jsonl_sha256"),
        "normalized_events": workflow["stages"]["normalization"]["output_sha256"].get(
            "normalized_events.parquet"
        ),
    }
    for name, expected in expected_hashes.items():
        if not expected or hashes[name] != expected:
            raise AggregationError(
                "INPUT_HASH_MISMATCH", f"{name}: {hashes[name]} != {expected}"
            )
    return {
        "input_directory": input_directory,
        "event_output": event_output,
        "workflow_path": workflow_path,
        "workflow": workflow,
        "source_path": source_path,
        "raw_path": raw_path,
        "normalized_path": normalized_path,
        "hashes": hashes,
    }


def _safe_remove_temporary(path: Path, parent: Path) -> None:
    resolved = path.resolve()
    if resolved.parent != parent.resolve() or not resolved.name.startswith(".aggregation-"):
        raise RuntimeError(f"refusing to remove unexpected temporary path: {resolved}")
    if resolved.exists():
        shutil.rmtree(resolved)


def build_event_aggregation(
    input_directory: Path,
    output_directory: Path,
    *,
    batch_size: int = 5000,
) -> dict[str, Any]:
    """Create processed, deduplicated-source, and traceable event datasets."""

    if batch_size <= 0:
        raise AggregationError("BATCH_SIZE_INVALID", str(batch_size))
    inputs = _resolve_inputs(Path(input_directory))
    output_directory = Path(output_directory).resolve()
    if output_directory.exists():
        raise FileExistsError(f"output directory already exists: {output_directory}")
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=".aggregation-", dir=output_directory.parent)
    ).resolve()
    try:
        source_summary = _extract_source_records(
            inputs["source_path"],
            inputs["raw_path"],
            temporary / "raw_source_records.parquet",
            batch_size,
        )
        event_summary = _append_event_outputs(
            inputs["normalized_path"],
            inputs["source_path"],
            inputs["raw_path"],
            temporary / "processed_events.parquet",
            temporary / "traceable_events.parquet",
            batch_size,
        )
        workflow = inputs["workflow"]
        expected_events = int(workflow["stages"]["normalization"]["counts"]["events"])
        expected_admissions = int(workflow["stages"]["cleaning"]["counts"]["admissions"])
        expected_workflow_source_rows = int(
            workflow["stages"]["cleaning"]["counts"]["source_rows"]
        )
        all_source_rows = source_summary["source_records"]
        checks = {
            "event_count_matches_workflow": event_summary["events"] == expected_events,
            "event_admission_count_matches_workflow": event_summary["admissions"]
            == expected_admissions,
            "source_admission_count_matches_workflow": source_summary["admissions"]
            == expected_admissions,
            "workflow_event_source_record_count_matches": source_summary[
                "source_role_counts"
            ].get("event", 0)
            == expected_workflow_source_rows,
            "processed_event_rows_match": pq.ParquetFile(
                temporary / "processed_events.parquet"
            ).metadata.num_rows
            == expected_events,
            "traceable_event_rows_match": pq.ParquetFile(
                temporary / "traceable_events.parquet"
            ).metadata.num_rows
            == expected_events,
            "raw_source_record_rows_match": pq.ParquetFile(
                temporary / "raw_source_records.parquet"
            ).metadata.num_rows
            == all_source_rows,
        }
        failed = [name for name, passed in checks.items() if not passed]
        if failed:
            raise AggregationError("AGGREGATION_QUALITY_CHECK_FAILED", ",".join(failed))
        _assert_event_columns_unchanged(
            inputs["normalized_path"], temporary / "processed_events.parquet", batch_size
        )
        _assert_event_columns_unchanged(
            inputs["normalized_path"], temporary / "traceable_events.parquet", batch_size
        )
        checks["processed_normalized_fields_unchanged"] = True
        checks["traceable_normalized_fields_unchanged"] = True
        output_names = (
            "processed_events.parquet",
            "raw_source_records.parquet",
            "traceable_events.parquet",
        )
        output_hashes = {
            name: _sha256_file(temporary / name) for name in output_names
        }
        output_bytes = {
            name: (temporary / name).stat().st_size for name in output_names
        }
        quality = {
            "schema_version": QUALITY_SCHEMA_VERSION,
            "status": "passed",
            "checks": checks,
            "expected": {
                "events": expected_events,
                "admissions": expected_admissions,
                "workflow_event_source_records": expected_workflow_source_rows,
                "all_source_records": all_source_rows,
            },
            "observed": {
                **source_summary,
                **{
                    key: value
                    for key, value in event_summary.items()
                    if key not in {"processed_schema", "traceable_schema"}
                },
            },
        }
        _write_json(temporary / "quality_report.json", quality)
        manifest = {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "aggregation_schema_version": AGGREGATION_SCHEMA_VERSION,
            "batch_size": batch_size,
            "inputs": {
                "workflow_manifest": str(inputs["workflow_path"]),
                "source_jsonl": str(inputs["source_path"]),
                "raw_source_jsonl": str(inputs["raw_path"]),
                "normalized_events": str(inputs["normalized_path"]),
                "sha256": inputs["hashes"],
            },
            "text_fields": [
                {
                    "source_module": module,
                    "source_table": _table_path(module, table),
                    "source_text_field": field,
                    "source_text_kind": kind,
                }
                for (module, table), (field, kind) in sorted(TEXT_FIELDS.items())
            ],
            "outputs": {
                name: {
                    "sha256": output_hashes[name],
                    "bytes": output_bytes[name],
                    "rows": pq.ParquetFile(temporary / name).metadata.num_rows,
                }
                for name in output_names
            },
            "quality_report": "quality_report.json",
            "quality_status": "passed",
        }
        _write_json(temporary / "aggregation_manifest.json", manifest)
        os.replace(temporary, output_directory)
        return manifest
    except Exception:
        _safe_remove_temporary(temporary, output_directory.parent)
        raise
