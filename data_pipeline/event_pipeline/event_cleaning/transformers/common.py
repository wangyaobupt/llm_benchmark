"""Shared primitives for source-specific event transformers."""

from __future__ import annotations

import re
from typing import Any

from ..ids import build_entity_id, build_event_id, canonical_json
from ..models import SourceRow
from ...event_contracts.schemas import QUALITY_FLAG_CODES
from ..time_resolver import resolved_times

class KnownTransformationError(ValueError):
    def __init__(self, reason_code: str, message: str):
        super().__init__(message)
        self.reason_code = reason_code


def _canonical_quality_flags(values: list[str] | None) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        code = re.sub(r"[^A-Z0-9]+", "_", str(value).strip().upper()).strip("_")
        if not code:
            raise ValueError("quality flag cannot be empty")
        if code not in QUALITY_FLAG_CODES:
            raise ValueError(f"unknown quality flag: {code}")
        if code not in seen:
            seen.add(code)
            result.append(code)
    return result


def _clean(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value).strip()


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _decoded_label(row: dict[str, Any], field: str = "itemid_decoded") -> str | None:
    decoded = row.get(field)
    if not isinstance(decoded, dict):
        return None
    for name in ("label", "long_title", "long_description", "short_description"):
        value = _clean(decoded.get(name))
        if value:
            return value
    return None


def _encounter_id(source: SourceRow) -> str:
    stay_id = _clean(source.row.get("stay_id"))
    if stay_id and source.spec.module == "mimic_iv_ed":
        return f"ed:{stay_id}"
    if stay_id and source.spec.module == "mimic_iv_icu":
        return f"icu:{stay_id}"
    return f"hadm:{source.hadm_id}"


def _event(
    source: SourceRow,
    component: str,
    event_kind: str,
    *,
    times: dict[str, str | None] | None = None,
    evidence_phase: str = "source_event",
    lifecycle_action: str | None = None,
    status: str | None = None,
    assertion: str = "present",
    entity_type: str | None = None,
    source_label: str | None = None,
    concept_id: str | None = None,
    preferred_name: str | None = None,
    content_specificity: str = "entity_specific",
    value_numeric: float | None = None,
    value_text: str | None = None,
    value_structured: Any = None,
    unit: str | None = None,
    abnormal_flag: str | None = None,
    source_action: str | None = None,
    quality_flags: list[str] | None = None,
    supporting_rows: list[SourceRow] | None = None,
) -> dict[str, Any]:
    event_id = build_event_id(source.source_row_id, component)
    support = supporting_rows or []
    resolved = dict(times or resolved_times())
    time_quality_flags = list(resolved.pop("time_quality_flags", []))
    event = {
        "schema_version": "1.2.0",
        "cleaning_status": "accepted",
        "event_id": event_id,
        "entity_id": build_entity_id(event_id) if entity_type else None,
        "source_row_id": source.source_row_id,
        "subject_id": source.subject_id,
        "hadm_id": source.hadm_id,
        "encounter_id": _encounter_id(source),
        "event_kind": event_kind,
        "lifecycle_action": lifecycle_action,
        "status": status,
        "assertion": assertion,
        **resolved,
        "time_policy_id": source.spec.time_policy,
        "evidence_phase": evidence_phase,
        "source_concept_id": concept_id,
        "concept_id": None,
        "preferred_name": None,
        "source_label": source_label,
        "entity_type": entity_type,
        "normalization_status": None,
        "terminology_mapping_version": None,
        "content_specificity": content_specificity,
        "value_numeric": value_numeric,
        "value_text": value_text,
        "value_structured_json": (
            canonical_json(value_structured) if value_structured is not None else None
        ),
        "unit": unit,
        "abnormal_flag": abnormal_flag,
        "normalized_value_numeric": None,
        "normalized_value_text": None,
        "normalized_unit": None,
        "unit_normalization_status": None,
        "source_module": source.spec.module,
        "source_table": source.spec.source_table,
        "source_array_index": source.source_array_index,
        "jsonl_line_number": source.jsonl_line_number,
        "raw_row_ref": source.raw_row_ref,
        "source_action": source_action,
        "quality_flags": _canonical_quality_flags(
            [*(quality_flags or []), *time_quality_flags]
        ),
        "supporting_source_row_ids": [
            row.source_row_id for row in support
        ],
        "supporting_raw_row_refs": [row.raw_row_ref for row in support],
    }
    return event
