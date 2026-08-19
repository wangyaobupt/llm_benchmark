"""Attach source-native episode grouping keys without inventing timestamps."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .fields import (
    chain_root_poe_id,
    lift_order_fields,
    micro_specimen_id_of,
    specimen_id_of,
    structured_payload,
)


REASON_SPECIMEN_GROUP_MISSING = "SPECIMEN_GROUP_MISSING"
REASON_RECEIVED_TIME_UNAVAILABLE = "SPECIMEN_RECEIVED_TIME_SOURCE_INSUFFICIENT"
REASON_CHAIN_ROOT_MISSING = "ORDER_CHAIN_INCOMPLETE"


def _stable_group(prefix: str, *parts: Any) -> str:
    payload = "\x00".join("" if part is None else str(part) for part in parts)
    digest = hashlib.sha256(f"{prefix}\x00{payload}".encode("utf-8")).hexdigest()[:24]
    return f"{prefix}:{digest}"


@dataclass(frozen=True)
class GroupingResult:
    rows: list[dict[str, Any]]
    exclusions: list[dict[str, Any]]
    metrics: dict[str, int]


def _is_lab_result(event: Mapping[str, Any]) -> bool:
    source_table = str(event.get("source_table") or "")
    kind = str(event.get("event_kind") or "")
    return source_table.endswith("labevents") or kind == "laboratory_resulted"


def _is_micro_result(event: Mapping[str, Any]) -> bool:
    source_table = str(event.get("source_table") or "")
    kind = str(event.get("event_kind") or "")
    return source_table.endswith("microbiologyevents") or kind == "microbiology_resulted"


def _is_imaging_report(event: Mapping[str, Any]) -> bool:
    kind = str(event.get("event_kind") or "")
    table = str(event.get("source_table") or "")
    return kind == "imaging_reported" or (
        table.endswith("radiology") and not kind.endswith("_ordered")
    )


def _is_poe_order(event: Mapping[str, Any]) -> bool:
    source_table = str(event.get("source_table") or "")
    kind = str(event.get("event_kind") or "")
    return (
        source_table.endswith("poe")
        or source_table.endswith("poe_timeline")
        or kind.endswith("_ordered")
        or event.get("poe_id") is not None
        or event.get("chain_root_poe_id") is not None
    )


def attach_source_groups(events: Iterable[Mapping[str, Any]]) -> GroupingResult:
    """Return copied rows with a stable source-native grouping key.

    Lab rows use the real ``specimen_id``.  POE rows use ``chain_root_poe_id``.
    Missing keys are marked, never inferred by time proximity.  The result
    never emits ``specimen_received_time``.
    """
    rows: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    for index, event in enumerate(events):
        row = lift_order_fields(event)
        row.pop("specimen_received_time", None)
        hadm_id = row.get("hadm_id")
        if _is_lab_result(row):
            raw = specimen_id_of(row)
            group_type = "lab_specimen"
            source_key_name = "specimen_id"
            missing_reason = REASON_SPECIMEN_GROUP_MISSING
        elif _is_micro_result(row):
            raw = micro_specimen_id_of(row)
            group_type = "micro_specimen"
            source_key_name = "micro_specimen_id"
            missing_reason = REASON_SPECIMEN_GROUP_MISSING
        elif _is_imaging_report(row):
            note_id = row.get("note_id") or structured_payload(row).get("note_id")
            exam_name = row.get("exam_name") or row.get("preferred_name")
            raw = None if not note_id or not exam_name else f"{note_id}|{exam_name}"
            group_type = "radiology_exam"
            source_key_name = "note_id_exam_name"
            missing_reason = REASON_SPECIMEN_GROUP_MISSING
        elif _is_poe_order(row):
            raw = chain_root_poe_id(row)
            group_type = "poe_lifecycle_chain"
            source_key_name = "chain_root_poe_id"
            missing_reason = REASON_CHAIN_ROOT_MISSING
        else:
            raw = row.get("source_row_id") or row.get("event_id")
            group_type = "source_row"
            source_key_name = "source_row_id"
            missing_reason = REASON_SPECIMEN_GROUP_MISSING

        row["source_group_type"] = group_type
        row["source_group_source_key"] = source_key_name
        caller_group = event.get("source_group_id")
        if raw in (None, ""):
            if caller_group not in (None, ""):
                row["source_group_id"] = caller_group
                row["source_group_id_status"] = "caller_supplied"
                rows.append(row)
                continue
            row["source_group_id"] = None
            row["source_group_id_status"] = "missing_in_source"
            exclusions.append({
                "row_index": index,
                "source_row_id": row.get("source_row_id"),
                "event_id": row.get("event_id"),
                "reason_codes": [missing_reason],
            })
            rows.append(row)
            continue
        row["source_group_id"] = _stable_group(group_type, hadm_id, raw)
        row["source_group_id_status"] = (
            "derived_from_poe_relation" if group_type == "poe_lifecycle_chain" else "observed"
        )
        rows.append(row)
    return GroupingResult(
        rows=rows,
        exclusions=exclusions,
        metrics={
            "input": len(rows),
            "grouped": sum(row.get("source_group_id") is not None for row in rows),
            "excluded": len(exclusions),
        },
    )
