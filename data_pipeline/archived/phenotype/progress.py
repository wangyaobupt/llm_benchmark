"""Atomic progress-file writer for the real-time HTML monitor.

Each long-running task writes a small JSON snapshot to
``data/phenotype/progress/<task>.json``; the HTML page polls it. Atomic
(temp + replace) so the reader never sees a half-written file.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROGRESS_DIR = Path(__file__).resolve().parents[3] / "data" / "phenotype" / "progress"


def write_progress(task: str, data: dict[str, Any]) -> None:
    PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
    path = PROGRESS_DIR / f"{task}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    tmp.replace(path)
