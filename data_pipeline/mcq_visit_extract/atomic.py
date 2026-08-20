"""Atomic writes and content hashes for checkpoint resume."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterable

from data_pipeline.mimic_raw_archive.manifest import (
    canonical_hash,
    file_sha256,
    read_manifest,
    write_manifest,
)

__all__ = [
    "atomic_write_bytes",
    "atomic_write_json",
    "atomic_write_jsonl",
    "canonical_hash",
    "file_sha256",
    "read_jsonl",
    "read_manifest",
    "remove_partial",
    "write_manifest",
]


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    with temporary.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def atomic_write_json(path: Path, value: Any, *, indent: int | None = 2) -> None:
    payload = json.dumps(value, ensure_ascii=False, indent=indent) + "\n"
    atomic_write_bytes(path, payload.encode("utf-8"))


def atomic_write_jsonl(path: Path, rows: Iterable[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(
                json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            )
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            text = line.strip()
            if text:
                rows.append(json.loads(text))
    return rows


def remove_partial(path: Path) -> None:
    temporary = path.with_name(path.name + ".partial")
    if temporary.exists():
        if not temporary.name.endswith(".partial"):
            raise RuntimeError(f"refusing to delete non-partial path: {temporary}")
        temporary.unlink()
