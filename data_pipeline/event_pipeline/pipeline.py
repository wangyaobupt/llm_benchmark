"""Streaming admission JSONL to validated one-event-per-row Parquet."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from .ids import SourceIdentityError, build_source_row_id, canonical_json
from .models import AdmissionContext, SourceRow, SourceSpec
from .schemas import (
    ENCOUNTER_ARROW_SCHEMA,
    EVENT_ARROW_SCHEMA,
    REJECTED_ARROW_SCHEMA,
    TERM_INVENTORY_ARROW_SCHEMA,
)
from .source_registry import (
    EVENT_SOURCE_REGISTRY,
    SOURCE_CATALOG,
    SOURCE_CATALOG_SHA256,
    SOURCE_CATALOG_VERSION,
)
from .terminology import normalized_text
from .transformers import KnownTransformationError, TRANSFORMERS
from .validation import (
    EventPipelineError,
    EventValidator,
    crosscheck_poe_timeline,
    validate_admission_shell,
)


OUTPUT_SCHEMA = {"name": "mimic_cleaned_events", "version": "1.1.0"}
PARQUET_ROW_GROUP_SIZE = 5000
REJECTABLE_EVENT_VALIDATION_ERRORS = frozenset({"AVAILABLE_BEFORE_EVENT_TIME"})


class BufferedParquetWriter:
    def __init__(self, path: Path, schema: pa.Schema, batch_size: int):
        self._schema = schema
        self._batch_size = batch_size
        self._buffer: list[dict[str, Any]] = []
        self._writer = pq.ParquetWriter(
            path,
            schema,
            compression="zstd",
            use_dictionary=True,
            write_statistics=True,
        )

    def write(self, row: dict[str, Any]) -> None:
        self._buffer.append(row)
        if len(self._buffer) >= self._batch_size:
            self.flush()

    def flush(self) -> None:
        if not self._buffer:
            return
        table = pa.Table.from_pylist(self._buffer, schema=self._schema)
        self._writer.write_table(table)
        self._buffer.clear()

    def close(self) -> None:
        self.flush()
        self._writer.close()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_dump(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _source_rows_for_admission(
    admission: dict[str, Any],
    *,
    line_number: int,
    input_name: str,
) -> dict[tuple[str, str], list[SourceRow]]:
    subject_id = str(admission["subject_id"])
    hadm_id = str(admission["hadm_id"])
    result: dict[tuple[str, str], list[SourceRow]] = {}
    for spec in SOURCE_CATALOG:
        rows = admission[spec.module].get(spec.table, [])
        if not isinstance(rows, list):
            raise EventPipelineError(
                "SOURCE_TABLE_NOT_ARRAY",
                f"line {line_number}: {spec.module}.{spec.table}",
            )
        source_rows: list[SourceRow] = []
        seen_ids: set[str] = set()
        row_occurrences: Counter[str] = Counter()
        for array_index, row in enumerate(rows):
            if not isinstance(row, dict):
                raise EventPipelineError(
                    "SOURCE_ROW_NOT_OBJECT",
                    f"line {line_number}: {spec.module}.{spec.table}[{array_index}]",
                )
            occurrence_ordinal = 0
            if spec.identity_strategy == "canonical_row_hash_with_occurrence":
                row_identity = canonical_json(row)
                occurrence_ordinal = row_occurrences[row_identity]
                row_occurrences[row_identity] += 1
            try:
                source_row_id = build_source_row_id(
                    spec,
                    row,
                    duplicate_occurrence_ordinal=occurrence_ordinal,
                )
            except SourceIdentityError as error:
                raise EventPipelineError(
                    error.reason_code,
                    f"line {line_number}: {error}",
                ) from error
            if source_row_id in seen_ids:
                raise EventPipelineError(
                    "DUPLICATE_SOURCE_ROW_ID",
                    f"line {line_number}: {spec.source_table}: {source_row_id}",
                )
            seen_ids.add(source_row_id)
            source_rows.append(
                SourceRow(
                    spec=spec,
                    row=row,
                    jsonl_line_number=line_number,
                    source_array_index=array_index,
                    subject_id=subject_id,
                    hadm_id=hadm_id,
                    input_name=input_name,
                    source_row_id=source_row_id,
                )
            )
        result[(spec.module, spec.table)] = source_rows
    return result


def _clean(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value).strip()


def _build_context(
    admission: dict[str, Any], source_rows: dict[tuple[str, str], list[SourceRow]]
) -> AdmissionContext:
    indexes = {
        "poe_timeline_source_by_id": {
            _clean(source.row.get("poe_id")): source
            for source in source_rows.get(("mimic_iv_hosp", "poe_timeline"), [])
            if _clean(source.row.get("poe_id"))
        },
    }
    return AdmissionContext(admission=admission, source_rows=source_rows, indexes=indexes)


def _empty_source_metrics(spec: SourceSpec) -> dict[str, Any]:
    return {
        "source_module": spec.module,
        "source_table": spec.source_table,
        "role": spec.role,
        "input_rows": 0,
        "accepted_source_rows": 0,
        "events": 0,
        "rejected_source_rows": 0,
    }


def _safe_remove_temporary(directory: Path, parent: Path) -> None:
    resolved_directory = directory.resolve()
    resolved_parent = parent.resolve()
    if resolved_parent not in resolved_directory.parents:
        raise RuntimeError(f"temporary output escaped parent: {resolved_directory}")
    shutil.rmtree(resolved_directory, ignore_errors=True)


def run_cleaning(
    input_path: Path,
    output_directory: Path,
    *,
    batch_size: int = 5000,
    limit: int | None = None,
) -> dict[str, Any]:
    """Build validated event Parquet files from an admission-level JSONL."""
    input_path = Path(input_path).resolve()
    output_directory = Path(output_directory).resolve()
    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    if output_directory.exists():
        raise EventPipelineError(
            "OUTPUT_ALREADY_EXISTS", str(output_directory)
        )
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{output_directory.name}.tmp-", dir=output_directory.parent
        )
    )

    event_writer = BufferedParquetWriter(
        temporary / "cleaned_events.parquet", EVENT_ARROW_SCHEMA, PARQUET_ROW_GROUP_SIZE
    )
    encounter_writer = BufferedParquetWriter(
        temporary / "encounter_manifest.parquet", ENCOUNTER_ARROW_SCHEMA, PARQUET_ROW_GROUP_SIZE
    )
    rejected_writer = BufferedParquetWriter(
        temporary / "cleaning_rejected.parquet", REJECTED_ARROW_SCHEMA, PARQUET_ROW_GROUP_SIZE
    )
    validator = EventValidator()
    source_metrics = {
        spec.source_table: _empty_source_metrics(spec)
        for spec in EVENT_SOURCE_REGISTRY
    }
    event_kind_counts: Counter[str] = Counter()
    evidence_phase_counts: Counter[str] = Counter()
    term_inventory: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    global_event_ids: set[str] = set()
    admissions = events_total = rejected_total = source_rows_total = 0
    poe_crosschecked_total = 0
    input_hash = _sha256(input_path)

    try:
        with input_path.open("rb") as handle:
            for line_number, raw_line in enumerate(handle, 1):
                if limit is not None and admissions >= limit:
                    break
                if not raw_line.strip():
                    raise EventPipelineError(
                        "BLANK_JSONL_LINE", f"line {line_number}"
                    )
                try:
                    admission = json.loads(raw_line)
                except (UnicodeDecodeError, json.JSONDecodeError) as error:
                    raise EventPipelineError(
                        "JSONL_PARSE_ERROR", f"line {line_number}: {error}"
                    ) from error
                validate_admission_shell(admission, line_number)
                poe_crosschecked_total += crosscheck_poe_timeline(admission, line_number)
                source_rows = _source_rows_for_admission(
                    admission,
                    line_number=line_number,
                    input_name=input_path.name,
                )
                context = _build_context(admission, source_rows)
                known_source_ids = {
                    row.source_row_id
                    for table_rows in source_rows.values()
                    for row in table_rows
                }
                admission_event_count = admission_rejected_count = 0
                admission_source_rows = 0

                for spec in EVENT_SOURCE_REGISTRY:
                    rows = source_rows[(spec.module, spec.table)]
                    metrics = source_metrics[spec.source_table]
                    metrics["input_rows"] += len(rows)
                    admission_source_rows += len(rows)
                    source_rows_total += len(rows)
                    transformer = TRANSFORMERS.get(spec.transformer_name or "")
                    if transformer is None:
                        raise EventPipelineError(
                            "TRANSFORMER_NOT_FOUND", spec.transformer_name or "<missing>"
                        )
                    for source_row in rows:
                        try:
                            generated = transformer(source_row, context)
                            if not generated:
                                raise KnownTransformationError(
                                    "NO_EVENT_GENERATED", "accepted source row produced no event"
                                )
                            generated_event_ids: set[str] = set()
                            for event in generated:
                                validator.validate(event, known_source_ids)
                                if (
                                    event["event_id"] in global_event_ids
                                    or event["event_id"] in generated_event_ids
                                ):
                                    raise EventPipelineError(
                                        "DUPLICATE_EVENT_ID", event["event_id"]
                                    )
                                generated_event_ids.add(event["event_id"])
                            for event in generated:
                                global_event_ids.add(event["event_id"])
                                event_writer.write(event)
                                admission_event_count += 1
                                events_total += 1
                                metrics["events"] += 1
                                event_kind_counts[event["event_kind"]] += 1
                                evidence_phase_counts[event["evidence_phase"]] += 1
                                if event["entity_type"] is not None:
                                    key = (
                                        event["entity_type"] or "<none>",
                                        event["source_concept_id"] or "<none>",
                                        normalized_text(event["source_label"]) or "<missing>",
                                        event["unit"] or "<none>",
                                    )
                                    inventory = term_inventory.setdefault(
                                        key,
                                        {
                                            "schema_version": "1.0.0",
                                            "entity_type": key[0],
                                            "source_concept_id": None if key[1] == "<none>" else key[1],
                                            "normalized_source_label": key[2],
                                            "source_label_example": event["source_label"] or "<missing>",
                                            "unit": None if key[3] == "<none>" else key[3],
                                            "event_count": 0,
                                            "first_event_id": event["event_id"],
                                        },
                                    )
                                    inventory["event_count"] += 1
                            metrics["accepted_source_rows"] += 1
                        except (KnownTransformationError, EventPipelineError) as error:
                            if (
                                isinstance(error, EventPipelineError)
                                and error.reason_code
                                not in REJECTABLE_EVENT_VALIDATION_ERRORS
                            ):
                                raise
                            rejected_writer.write(
                                {
                                    "schema_version": "1.1.0",
                                    "cleaning_status": "rejected",
                                    "subject_id": source_row.subject_id,
                                    "hadm_id": source_row.hadm_id,
                                    "source_row_id": source_row.source_row_id,
                                    "raw_row_ref": source_row.raw_row_ref,
                                    "source_table": source_row.spec.source_table,
                                    "reason_code": error.reason_code,
                                    "message": str(error),
                                }
                            )
                            admission_rejected_count += 1
                            rejected_total += 1
                            metrics["rejected_source_rows"] += 1

                encounter_writer.write(
                    {
                        "schema_version": "1.0.0",
                        "subject_id": str(admission["subject_id"]),
                        "hadm_id": str(admission["hadm_id"]),
                        "jsonl_line_number": line_number,
                        "source_row_count": admission_source_rows,
                        "derived_row_count": 0,
                        "event_count": admission_event_count,
                        "rejected_count": admission_rejected_count,
                    }
                )
                admissions += 1

        event_writer.close()
        encounter_writer.close()
        rejected_writer.close()
        inventory_writer = BufferedParquetWriter(
            temporary / "term_inventory.parquet",
            TERM_INVENTORY_ARROW_SCHEMA,
            PARQUET_ROW_GROUP_SIZE,
        )
        for row in sorted(
            term_inventory.values(),
            key=lambda value: (-value["event_count"], value["entity_type"], value["normalized_source_label"]),
        ):
            inventory_writer.write(row)
        inventory_writer.close()

        classified_source_rows = sum(
            metrics["accepted_source_rows"]
            + metrics["rejected_source_rows"]
            for metrics in source_metrics.values()
        )
        if classified_source_rows != source_rows_total:
            raise EventPipelineError(
                "SOURCE_RECONCILIATION_FAILED",
                f"source_rows={source_rows_total}, classified={classified_source_rows}",
            )
        reconciliation = {
            "schema": {"name": "source_reconciliation", "version": "1.0.0"},
            "source_rows": source_rows_total,
            "classified_source_rows": classified_source_rows,
            "poe_timeline_rows_crosschecked": poe_crosschecked_total,
            "tables": [
                source_metrics[spec.source_table] for spec in EVENT_SOURCE_REGISTRY
            ],
        }
        _json_dump(temporary / "source_reconciliation.json", reconciliation)
        output_files = (
            "cleaned_events.parquet",
            "encounter_manifest.parquet",
            "cleaning_rejected.parquet",
            "term_inventory.parquet",
            "source_reconciliation.json",
        )
        output_hashes = {name: _sha256(temporary / name) for name in output_files}
        manifest = {
            "schema": {"name": "event_pipeline_run_manifest", "version": "1.0.0"},
            "output_schema": OUTPUT_SCHEMA,
            "source_catalog": {
                "version": SOURCE_CATALOG_VERSION,
                "sha256": SOURCE_CATALOG_SHA256,
                "sources": len(SOURCE_CATALOG),
                "event_sources": len(EVENT_SOURCE_REGISTRY),
            },
            "run_id": hashlib.sha256(
                (
                    f"{input_hash}|cleaning/1.1.0|"
                    f"{SOURCE_CATALOG_SHA256}|{limit}"
                ).encode("utf-8")
            ).hexdigest()[:24],
            "input": {
                "filename": input_path.name,
                "bytes": input_path.stat().st_size,
                "sha256": input_hash,
                "limit": limit,
            },
            "counts": {
                "admissions": admissions,
                "source_rows": source_rows_total,
                "events": events_total,
                "rejected": rejected_total,
                "term_inventory_rows": len(term_inventory),
            },
            "event_kind_counts": dict(sorted(event_kind_counts.items())),
            "evidence_phase_counts": dict(sorted(evidence_phase_counts.items())),
            "output_sha256": output_hashes,
        }
        _json_dump(temporary / "run_manifest.json", manifest)
        os.replace(temporary, output_directory)
        return manifest
    except Exception:
        for writer in (event_writer, encounter_writer, rejected_writer):
            try:
                writer.close()
            except Exception:
                pass
        if temporary.exists():
            _safe_remove_temporary(temporary, output_directory.parent)
        raise
