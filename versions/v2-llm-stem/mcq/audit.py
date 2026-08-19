"""Atomic artifact IO and cache-key derivation (design doc §15-16).

Major JSON/JSONL artifacts are written via temp-file + atomic replace so an
interrupted run never leaves a half-written file. CSV artifacts use UTF-8-SIG.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable


def _atomic_write(path: Path, content: str, encoding: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=path.name)
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as fh:
            fh.write(content)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def write_json(path: Path, obj: Any) -> None:
    _atomic_write(path, json.dumps(obj, ensure_ascii=False, indent=2), "utf-8")


def write_jsonl(path: Path, objs: Iterable[dict]) -> None:
    content = "".join(
        json.dumps(obj, ensure_ascii=False) + "\n" for obj in objs
    )
    _atomic_write(path, content, "utf-8")


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def write_csv_utf8sig(path: Path, header: list[str], rows: Iterable[list[Any]]) -> None:
    import csv
    import io

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    for row in rows:
        writer.writerow(row)
    _atomic_write(path, buf.getvalue(), "utf-8-sig")


def cache_key(*, task_type: str, model: str, prompt_version: str,
              schema_version: str, system_prompt: str, payload: dict,
              response_model: str, params: dict) -> str:
    """Content-addressed cache key covering every request-affecting input (§9.3)."""
    data = json.dumps(
        {
            "task_type": task_type,
            "model": model,
            "prompt_version": prompt_version,
            "schema_version": schema_version,
            "system_prompt": system_prompt,
            "payload": payload,
            "response_model": response_model,
            "params": params,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(data.encode("utf-8")).hexdigest()
