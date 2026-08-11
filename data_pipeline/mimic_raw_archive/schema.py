"""Frozen observable Interface for one raw MIMIC admission record."""

from __future__ import annotations

import json
from typing import Any

from . import SCHEMA_NAME, SCHEMA_VERSION
from .catalog import MODULE_TABLES


TOP_LEVEL_FIELDS = (
    "schema",
    "subject_id",
    "hadm_id",
    "mimic_iv_hosp",
    "mimic_iv_icu",
    "mimic_iv_ed",
    "mimic_iv_note",
)


class RawArchiveValidationError(ValueError):
    pass


def empty_record(subject_id: str, hadm_id: str) -> dict[str, Any]:
    record: dict[str, Any] = {
        "schema": {"name": SCHEMA_NAME, "version": SCHEMA_VERSION},
        "subject_id": str(subject_id),
        "hadm_id": str(hadm_id),
    }
    for module, sources in MODULE_TABLES.items():
        record[module] = {source.output_key: [] for source in sources}
    return record


def build_record(
    subject_id: str,
    hadm_id: str,
    rows_by_source: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    record = empty_record(subject_id, hadm_id)
    for module, sources in MODULE_TABLES.items():
        for source in sources:
            rows = rows_by_source.get(source.key, [])
            rows.sort(key=canonical_row)
            record[module][source.output_key] = rows
    validate_record(record)
    return record


def validate_record(record: dict[str, Any]) -> None:
    if tuple(record) != TOP_LEVEL_FIELDS:
        raise RawArchiveValidationError("top-level schema drift")
    if record["schema"] != {"name": SCHEMA_NAME, "version": SCHEMA_VERSION}:
        raise RawArchiveValidationError("schema identity mismatch")
    subject_id = record["subject_id"]
    hadm_id = record["hadm_id"]
    if not subject_id or not hadm_id:
        raise RawArchiveValidationError("subject_id and hadm_id are required")

    for module, sources in MODULE_TABLES.items():
        expected_tables = tuple(source.output_key for source in sources)
        actual = record.get(module)
        if not isinstance(actual, dict) or tuple(actual) != expected_tables:
            raise RawArchiveValidationError(f"{module} table schema drift")
        for source in sources:
            rows = actual[source.output_key]
            if not isinstance(rows, list):
                raise RawArchiveValidationError(
                    f"{module}.{source.output_key} must be a list"
                )
            expected_fields = source.source.header
            for index, row in enumerate(rows):
                if not isinstance(row, dict) or tuple(row) != expected_fields:
                    raise RawArchiveValidationError(
                        f"{module}.{source.output_key}[{index}] raw field drift"
                    )
                if "subject_id" in row and row["subject_id"] != subject_id:
                    raise RawArchiveValidationError(
                        f"{module}.{source.output_key}[{index}] subject conflict"
                    )
                if "hadm_id" in row and row["hadm_id"] != hadm_id:
                    raise RawArchiveValidationError(
                        f"{module}.{source.output_key}[{index}] admission conflict"
                    )

    admissions = record["mimic_iv_hosp"]["admissions"]
    if len(admissions) != 1:
        raise RawArchiveValidationError("each archive record needs exactly one admission")
    if "chartevents" in record["mimic_iv_icu"]:
        raise RawArchiveValidationError("chartevents is forbidden")


def canonical_row(row: dict[str, Any]) -> str:
    return json.dumps(row, ensure_ascii=False, separators=(",", ":"))
