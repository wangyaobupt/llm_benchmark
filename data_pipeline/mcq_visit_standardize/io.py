"""JSON-array streaming and atomic CSV/JSON writes."""

from __future__ import annotations

import csv
import json
import os
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from data_pipeline.mcq_visit_extract.atomic import file_sha256

from .columns import NESTED_COLUMNS, OUTPUT_COLUMNS


def iter_json_array(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        first = handle.readline()
        if first.strip() != "[":
            raise ValueError(f"expected JSON array start in {path}")
        for line in handle:
            text = line.strip()
            if text == "]":
                return
            if text.endswith(","):
                text = text[:-1]
            if not text:
                continue
            payload = json.loads(text)
            if not isinstance(payload, dict):
                raise ValueError("visit array elements must be objects")
            yield payload


def write_json_array(path: Path, rows: Iterable[dict[str, Any]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    count = 0
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("[\n")
        first = True
        for row in rows:
            if not first:
                handle.write(",\n")
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
            first = False
            count += 1
        handle.write("\n]\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    if count == 0:
        raise ValueError(f"refusing to publish empty JSON array: {path}")
    return file_sha256(path)


def _cell(column: str, value: Any) -> str:
    if value is None:
        return ""
    if column in NESTED_COLUMNS or isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def write_csv(path: Path, rows: list[dict[str, Any]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    csv.field_size_limit(32 * 1024 * 1024)
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(OUTPUT_COLUMNS),
            extrasaction="ignore",
            quoting=csv.QUOTE_MINIMAL,
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({column: _cell(column, row.get(column)) for column in OUTPUT_COLUMNS})
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    return file_sha256(path)
