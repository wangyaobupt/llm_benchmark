"""Strip lineage and write the 10k-row csv/json deliverables."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any

from .atomic import file_sha256
from .columns import (
    FORBIDDEN_DELIVERABLE_KEYS,
    NESTED_COLUMNS,
    REQUIRED_RESULT_COLUMNS,
    RESULT_COLUMNS,
)


class DeliverableError(ValueError):
    pass


def project_result(record: dict[str, Any]) -> dict[str, Any]:
    projected = {key: record[key] for key in RESULT_COLUMNS}
    leaked = FORBIDDEN_DELIVERABLE_KEYS.intersection(projected)
    if leaked:
        raise DeliverableError(f"result columns include lineage keys: {sorted(leaked)}")
    return projected


def _cell(column: str, value: Any) -> str:
    if value is None:
        return ""
    if column in NESTED_COLUMNS:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(RESULT_COLUMNS),
            extrasaction="raise",
            quoting=csv.QUOTE_MINIMAL,
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({column: _cell(column, row[column]) for column in RESULT_COLUMNS})
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    return file_sha256(path)


def write_json_array(path: Path, rows: list[dict[str, Any]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("[\n")
        for index, row in enumerate(rows):
            payload = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
            handle.write(payload)
            handle.write(",\n" if index < len(rows) - 1 else "\n")
        handle.write("]\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    return file_sha256(path)


def assert_deliverable_record(record: dict[str, Any]) -> None:
    if tuple(record) != RESULT_COLUMNS:
        raise DeliverableError("deliverable key order drift")
    leaked = FORBIDDEN_DELIVERABLE_KEYS.intersection(record)
    if leaked:
        raise DeliverableError(f"deliverable contains lineage keys: {sorted(leaked)}")
    for key in REQUIRED_RESULT_COLUMNS:
        value = record[key]
        if value is None or value == "":
            raise DeliverableError(f"required field empty: {key}")
