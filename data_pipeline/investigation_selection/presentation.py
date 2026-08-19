"""Attach ED chief complaints to encounter origin for presentation-to-order mining."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping

import pyarrow.parquet as pq


def _parse_time(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    return parsed


def split_complaint_labels(text: Any) -> list[str]:
    if not isinstance(text, str) or not text.strip():
        return []
    parts = []
    for raw in text.replace(";", ",").split(","):
        label = " ".join(raw.strip().split())
        if len(label) >= 3:
            parts.append(label)
    return parts or []


def hadm_origin_times(events: Iterable[Mapping[str, Any]]) -> dict[str, datetime]:
    origins: dict[str, datetime] = {}
    for event in events:
        hadm = event.get("hadm_id")
        if hadm in (None, ""):
            continue
        table = str(event.get("source_table") or "")
        kind = str(event.get("event_kind") or "")
        parsed = _parse_time(event.get("event_time"))
        if parsed is None:
            continue
        if table == "ed.vitalsign" or kind in {"vital_measured", "symptom_reported"}:
            current = origins.get(str(hadm))
            if current is None or parsed < current:
                origins[str(hadm)] = parsed
    if len(origins) == len({str(event.get("hadm_id")) for event in events if event.get("hadm_id")}):
        return origins
    for event in events:
        hadm = event.get("hadm_id")
        if hadm in (None, "") or str(hadm) in origins:
            continue
        parsed = _parse_time(event.get("event_time"))
        if parsed is None or event.get("time_resolution_status") != "resolved":
            continue
        current = origins.get(str(hadm))
        if current is None or parsed < current:
            origins[str(hadm)] = parsed
    return origins


def load_presentation_facts(events_path: Path) -> dict[str, list[dict[str, Any]]]:
    """Load ED complaints and bind them to a conservative encounter origin time."""
    table = pq.read_table(
        events_path,
        columns=[
            "hadm_id",
            "subject_id",
            "event_id",
            "event_kind",
            "event_time",
            "available_time",
            "source_table",
            "preferred_name",
            "source_label",
            "concept_id",
            "time_resolution_status",
            "time_policy_id",
        ],
    )
    rows = table.to_pylist()
    origins = hadm_origin_times(rows)
    by_hadm: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in rows:
        if event.get("event_kind") != "symptom_reported":
            continue
        hadm = str(event.get("hadm_id") or "")
        origin = origins.get(hadm)
        if origin is None:
            continue
        labels = split_complaint_labels(event.get("preferred_name") or event.get("source_label"))
        if not labels:
            continue
        stamp = origin.isoformat(sep=" ")
        for label in labels:
            by_hadm[hadm].append({
                "hadm_id": hadm,
                "event_id": event.get("event_id"),
                "event_kind": "symptom_reported",
                "concept_id": event.get("concept_id"),
                "preferred_name": label,
                "event_time": stamp,
                "available_time": stamp,
                "time_policy_id": "presentation_origin_v1",
            })
    return dict(by_hadm)


def stamp_presentation_events(
    events: Iterable[Mapping[str, Any]],
    origin: datetime | None,
) -> list[dict[str, Any]]:
    """Copy events and bind untimed ED complaints to encounter origin.

    This does not invent a source-table clock.  MIMIC ``ed.triage`` has no
    timestamp; the stamp is a conservative encounter-origin binding so the
    complaint can be visible at the first-wave investigation index.
    """
    origin_iso = origin.isoformat(sep=" ") if origin is not None else None
    stamped: list[dict[str, Any]] = []
    for event in events:
        row = dict(event)
        if row.get("event_kind") != "symptom_reported":
            stamped.append(row)
            continue
        has_event = _parse_time(row.get("event_time")) is not None
        has_available = _parse_time(row.get("available_time")) is not None
        if has_event and has_available:
            stamped.append(row)
            continue
        if origin_iso is None:
            stamped.append(row)
            continue
        if not has_event:
            row["event_time"] = origin_iso
        if not has_available:
            row["available_time"] = origin_iso
        row["time_policy_id"] = "presentation_origin_v1"
        stamped.append(row)
    return stamped
