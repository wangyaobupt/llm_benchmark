"""Validation and text access for the accepted event aggregation dataset."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Iterator

import pyarrow.parquet as pq


AGGREGATION_MANIFEST_VERSION = "event-aggregation-manifest/1.0.0"
AGGREGATION_SCHEMA_VERSION = "event-aggregation/1.0.0"
AGGREGATION_QUALITY_VERSION = "event-aggregation-quality/1.0.0"
SOURCE_RECORD_SCHEMA_VERSION = "event-source-record/1.0.0"
REQUIRED_OUTPUTS = (
    "processed_events.parquet",
    "raw_source_records.parquet",
    "traceable_events.parquet",
)


class AggregationInputError(ValueError):
    def __init__(self, reason_code: str, message: str):
        super().__init__(f"{reason_code}: {message}")
        self.reason_code = reason_code


@dataclass(frozen=True)
class ValidatedAggregation:
    directory: Path
    manifest_path: Path
    quality_path: Path
    raw_source_records_path: Path
    processed_events_path: Path
    traceable_events_path: Path
    manifest: dict[str, Any]
    quality: dict[str, Any]
    output_sha256: dict[str, str]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _load_json(path: Path, reason_code: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AggregationInputError(reason_code, f"{path}: {error}") from error
    if not isinstance(value, dict):
        raise AggregationInputError(reason_code, f"{path}: root is not an object")
    return value


def _schema_metadata(path: Path) -> str | None:
    metadata = pq.ParquetFile(path).schema_arrow.metadata or {}
    value = metadata.get(b"schema")
    return value.decode("ascii") if value is not None else None


def validate_aggregation_directory(directory: Path) -> ValidatedAggregation:
    """Fail closed unless the complete aggregation package passes its own contract."""

    directory = Path(directory).resolve()
    manifest_path = directory / "aggregation_manifest.json"
    quality_path = directory / "quality_report.json"
    if not manifest_path.is_file() or not quality_path.is_file():
        raise AggregationInputError("AGGREGATION_PACKAGE_INCOMPLETE", str(directory))
    manifest = _load_json(manifest_path, "AGGREGATION_MANIFEST_INVALID")
    quality = _load_json(quality_path, "AGGREGATION_QUALITY_REPORT_INVALID")
    if manifest.get("schema_version") != AGGREGATION_MANIFEST_VERSION:
        raise AggregationInputError(
            "AGGREGATION_MANIFEST_VERSION_INVALID", str(manifest.get("schema_version"))
        )
    if manifest.get("aggregation_schema_version") != AGGREGATION_SCHEMA_VERSION:
        raise AggregationInputError(
            "AGGREGATION_SCHEMA_VERSION_INVALID",
            str(manifest.get("aggregation_schema_version")),
        )
    if quality.get("schema_version") != AGGREGATION_QUALITY_VERSION:
        raise AggregationInputError(
            "AGGREGATION_QUALITY_VERSION_INVALID", str(quality.get("schema_version"))
        )
    checks = quality.get("checks")
    failed_checks = (
        sorted(name for name, passed in checks.items() if passed is not True)
        if isinstance(checks, dict)
        else ["checks_missing"]
    )
    if (
        manifest.get("quality_status") != "passed"
        or quality.get("status") != "passed"
        or failed_checks
    ):
        raise AggregationInputError(
            "AGGREGATION_QUALITY_NOT_PASSED", ",".join(failed_checks)
        )

    outputs = manifest.get("outputs")
    if not isinstance(outputs, dict):
        raise AggregationInputError("AGGREGATION_OUTPUTS_MISSING", str(manifest_path))
    output_sha256: dict[str, str] = {}
    for name in REQUIRED_OUTPUTS:
        declaration = outputs.get(name)
        path = directory / name
        if not isinstance(declaration, dict) or not path.is_file():
            raise AggregationInputError("AGGREGATION_OUTPUT_MISSING", name)
        parquet = pq.ParquetFile(path)
        if parquet.metadata.num_rows != declaration.get("rows"):
            raise AggregationInputError("AGGREGATION_OUTPUT_ROW_COUNT_MISMATCH", name)
        if path.stat().st_size != declaration.get("bytes"):
            raise AggregationInputError("AGGREGATION_OUTPUT_SIZE_MISMATCH", name)
        observed_hash = sha256_file(path)
        if observed_hash != declaration.get("sha256"):
            raise AggregationInputError("AGGREGATION_OUTPUT_HASH_MISMATCH", name)
        output_sha256[name] = observed_hash

    raw_path = directory / "raw_source_records.parquet"
    processed_path = directory / "processed_events.parquet"
    traceable_path = directory / "traceable_events.parquet"
    if _schema_metadata(raw_path) != SOURCE_RECORD_SCHEMA_VERSION:
        raise AggregationInputError(
            "AGGREGATION_SOURCE_RECORD_SCHEMA_INVALID", str(_schema_metadata(raw_path))
        )
    for path in (processed_path, traceable_path):
        if _schema_metadata(path) != AGGREGATION_SCHEMA_VERSION:
            raise AggregationInputError(
                "AGGREGATION_EVENT_SCHEMA_INVALID", f"{path.name}: {_schema_metadata(path)}"
            )
    expected = quality.get("expected", {})
    observed = quality.get("observed", {})
    try:
        expected_admissions = int(expected["admissions"])
        expected_events = int(expected["events"])
        expected_source_records = int(expected["all_source_records"])
        observed_source_records = int(observed["source_records"])
    except (KeyError, TypeError, ValueError) as error:
        raise AggregationInputError("AGGREGATION_COUNTS_INVALID", str(expected)) from error
    if min(expected_admissions, expected_events, expected_source_records) <= 0:
        raise AggregationInputError("AGGREGATION_COUNTS_INVALID", str(expected))
    raw_rows = pq.ParquetFile(raw_path).metadata.num_rows
    processed_rows = pq.ParquetFile(processed_path).metadata.num_rows
    traceable_rows = pq.ParquetFile(traceable_path).metadata.num_rows
    if raw_rows != expected_source_records or raw_rows != observed_source_records:
        raise AggregationInputError(
            "AGGREGATION_SOURCE_RECORD_COUNT_MISMATCH",
            f"parquet={raw_rows}; expected={expected_source_records}; observed={observed_source_records}",
        )
    if processed_rows != expected_events or traceable_rows != expected_events:
        raise AggregationInputError(
            "AGGREGATION_EVENT_COUNT_MISMATCH",
            f"processed={processed_rows}; traceable={traceable_rows}; expected={expected_events}",
        )
    admissions: set[tuple[str, str]] = set()
    for batch in pq.ParquetFile(raw_path).iter_batches(
        columns=["subject_id", "hadm_id"], batch_size=20000
    ):
        subjects = batch.column(0).to_pylist()
        encounters = batch.column(1).to_pylist()
        admissions.update((str(subject), str(encounter)) for subject, encounter in zip(subjects, encounters))
    if len(admissions) != expected_admissions:
        raise AggregationInputError(
            "AGGREGATION_ADMISSION_COUNT_MISMATCH",
            f"parquet={len(admissions)}; expected={expected_admissions}",
        )
    return ValidatedAggregation(
        directory=directory,
        manifest_path=manifest_path,
        quality_path=quality_path,
        raw_source_records_path=raw_path,
        processed_events_path=processed_path,
        traceable_events_path=traceable_path,
        manifest=manifest,
        quality=quality,
        output_sha256=output_sha256,
    )


def aggregation_text_fields(aggregation: ValidatedAggregation) -> set[tuple[str, str, str, str]]:
    fields = aggregation.manifest.get("text_fields")
    if not isinstance(fields, list):
        raise AggregationInputError(
            "AGGREGATION_TEXT_FIELDS_MISSING", str(aggregation.manifest_path)
        )
    result: set[tuple[str, str, str, str]] = set()
    for field in fields:
        try:
            key = (
                str(field["source_module"]),
                str(field["source_table"]),
                str(field["source_text_field"]),
                str(field["source_text_kind"]),
            )
        except (KeyError, TypeError) as error:
            raise AggregationInputError(
                "AGGREGATION_TEXT_FIELD_INVALID", repr(field)
            ) from error
        if key in result:
            raise AggregationInputError("AGGREGATION_TEXT_FIELD_DUPLICATE", repr(key))
        result.add(key)
    return result


SOURCE_TEXT_COLUMNS = (
    "source_record_id",
    "subject_id",
    "hadm_id",
    "jsonl_line_number",
    "source_module",
    "source_table",
    "source_table_name",
    "source_array_index",
    "raw_row_ref",
    "source_text_field",
    "source_text_kind",
    "source_text",
    "source_text_sha256",
    "clinical_readable_record_json",
)


def iter_source_text_records(
    aggregation: ValidatedAggregation, *, batch_size: int = 10000
) -> Iterator[dict[str, Any]]:
    """Yield each non-empty free-text source record once and validate its hash."""

    parquet = pq.ParquetFile(aggregation.raw_source_records_path)
    missing = set(SOURCE_TEXT_COLUMNS) - set(parquet.schema_arrow.names)
    if missing:
        raise AggregationInputError(
            "AGGREGATION_SOURCE_COLUMNS_MISSING", ",".join(sorted(missing))
        )
    seen_ids: set[str] = set()
    seen_refs: set[str] = set()
    declared = aggregation_text_fields(aggregation)
    for batch in parquet.iter_batches(columns=list(SOURCE_TEXT_COLUMNS), batch_size=batch_size):
        for row in batch.to_pylist():
            text = row["source_text"]
            if text is None:
                continue
            if not isinstance(text, str) or not text.strip():
                raise AggregationInputError(
                    "AGGREGATION_SOURCE_TEXT_INVALID", str(row["source_record_id"])
                )
            key = (
                row["source_module"],
                row["source_table"],
                row["source_text_field"],
                row["source_text_kind"],
            )
            if key not in declared:
                raise AggregationInputError(
                    "AGGREGATION_UNDECLARED_TEXT_FIELD", repr(key)
                )
            if sha256_text(text) != row["source_text_sha256"]:
                raise AggregationInputError(
                    "AGGREGATION_SOURCE_TEXT_HASH_MISMATCH", str(row["source_record_id"])
                )
            if row["source_record_id"] in seen_ids or row["raw_row_ref"] in seen_refs:
                raise AggregationInputError(
                    "AGGREGATION_SOURCE_TEXT_DUPLICATE", str(row["raw_row_ref"])
                )
            seen_ids.add(row["source_record_id"])
            seen_refs.add(row["raw_row_ref"])
            yield row


def source_text_key(row: dict[str, Any]) -> tuple[int, str, str, int, str]:
    return (
        int(row["jsonl_line_number"]),
        str(row["source_module"]),
        str(row["source_table"]),
        int(row["source_array_index"]),
        str(row["source_text_field"]),
    )


def load_required_source_texts(
    aggregation: ValidatedAggregation,
    required_keys: Iterable[tuple[int, str, str, int, str]],
) -> dict[tuple[int, str, str, int, str], str]:
    required = set(required_keys)
    result: dict[tuple[int, str, str, int, str], str] = {}
    for row in iter_source_text_records(aggregation):
        key = source_text_key(row)
        if key in required:
            result[key] = row["source_text"]
    missing = required - set(result)
    if missing:
        raise AggregationInputError(
            "AGGREGATION_REQUIRED_TEXT_MISSING", repr(sorted(missing)[:3])
        )
    return result
