"""Load event lists from the extract JSON shapes already in this repo."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_events(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return events_from_payload(payload)


def events_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        raise ValueError("event extract must be a list or object")
    if isinstance(payload.get("events"), list):
        return [row for row in payload["events"] if isinstance(row, dict)]
    groups = payload.get("event_groups")
    if isinstance(groups, dict):
        rows: list[dict[str, Any]] = []
        for group in groups.values():
            if isinstance(group, dict) and isinstance(group.get("events"), list):
                rows.extend(row for row in group["events"] if isinstance(row, dict))
        return rows
    raise ValueError("event extract has no events or event_groups")


def infer_hadm_id(events: list[dict[str, Any]], fallback: str | None = None) -> str:
    for event in events:
        hadm = event.get("hadm_id")
        if hadm not in (None, ""):
            return str(hadm)
    if fallback:
        return fallback
    raise ValueError("hadm_id is missing from events")
