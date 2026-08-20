"""Load timeline facts/events without pulling other families' artifacts."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from data_pipeline.mcq_visit_extract.atomic import read_jsonl


def load_facts(timeline_dir: Path) -> list[dict[str, Any]]:
    path = timeline_dir / "presentation_facts.jsonl"
    if not path.is_file():
        raise FileNotFoundError(f"missing presentation_facts.jsonl in {timeline_dir}")
    return read_jsonl(path)


def load_events_by_hadm(timeline_dir: Path, columns: list[str] | None = None) -> dict[str, list[dict[str, Any]]]:
    path = timeline_dir / "visit_events.parquet"
    if not path.is_file():
        raise FileNotFoundError(f"missing visit_events.parquet in {timeline_dir}")
    table = pq.read_table(path, columns=columns)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in table.to_pylist():
        hadm_id = str(row.get("hadm_id") or "").strip()
        if hadm_id:
            grouped[hadm_id].append(row)
    return dict(grouped)
