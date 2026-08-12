"""Normalization-owned deterministic output and publication helpers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq


PARQUET_ROW_GROUP_SIZE = 5000


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
        self._writer.write_table(pa.Table.from_pylist(self._buffer, schema=self._schema))
        self._buffer.clear()

    def close(self) -> None:
        self.flush()
        self._writer.close()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def remove_temporary(directory: Path, expected_parent: Path) -> None:
    resolved = directory.resolve()
    parent = expected_parent.resolve()
    if resolved.parent != parent or not resolved.name.startswith("."):
        raise ValueError(f"refusing to remove unexpected temporary directory: {resolved}")
    shutil.rmtree(resolved)


__all__ = [
    "BufferedParquetWriter",
    "PARQUET_ROW_GROUP_SIZE",
    "remove_temporary",
    "sha256_file",
    "write_json",
]
