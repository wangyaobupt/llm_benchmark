"""Attach source-native episode grouping keys without inventing timestamps."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Iterable, Mapping


REASON_SPECIMEN_GROUP_MISSING = "SPECIMEN_GROUP_MISSING"
REASON_RECEIVED_TIME_UNAVAILABLE = "SPECIMEN_RECEIVED_TIME_SOURCE_INSUFFICIENT"


def _stable_group(prefix: str, value: Any) -> str:
    digest = hashlib.sha256(f"{prefix}\x00{value}".encode("utf-8")).hexdigest()[:24]
    return f"{prefix}:{digest}"


@dataclass(frozen=True)
class GroupingResult:
    rows: list[dict[str, Any]]
    exclusions: list[dict[str, Any]]
    metrics: dict[str, int]


def attach_source_groups(events: Iterable[Mapping[str, Any]]) -> GroupingResult:
    """Return copied rows with a stable source-native grouping key.

    ``charttime`` and ``storetime`` are preserved as supplied.  The result
    never emits ``specimen_received_time`` because MIMIC-IV does not provide
    that semantic for ordinary laboratory events.
    """
    rows: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    for index, event in enumerate(events):
        row = dict(event)
        source_table = str(row.get("source_table") or "")
        if source_table.endswith("labevents") or row.get("event_kind") == "laboratory_resulted":
            raw = row.get("specimen_id") or row.get("source_group_id")
            group_type = "lab_specimen"
        elif source_table.endswith("microbiologyevents") or row.get("event_kind") == "microbiology_resulted":
            raw = row.get("micro_specimen_id") or row.get("source_group_id")
            group_type = "micro_specimen"
        elif source_table.endswith("poe") or row.get("event_kind", "").endswith("_ordered"):
            raw = row.get("poe_id") or row.get("source_row_id")
            group_type = "poe_order"
        else:
            raw = row.get("source_row_id")
            group_type = "source_row"
        if raw in (None, ""):
            exclusions.append({
                "row_index": index,
                "source_row_id": row.get("source_row_id"),
                "reason_codes": [REASON_SPECIMEN_GROUP_MISSING],
            })
            continue
        row["source_group_id"] = _stable_group(group_type, raw)
        row["source_group_type"] = group_type
        row.pop("specimen_received_time", None)
        rows.append(row)
    return GroupingResult(
        rows=rows,
        exclusions=exclusions,
        metrics={"input": len(rows) + len(exclusions), "grouped": len(rows), "excluded": len(exclusions)},
    )

