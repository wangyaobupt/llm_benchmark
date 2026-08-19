"""Lift POE / specimen keys out of event payloads without inventing facts."""

from __future__ import annotations

import json
from typing import Any, Mapping


RETROSPECTIVE_ONLY_FIELDS = (
    "successor_poe_id",
    "chain_complete",
    "predecessor_poe_id",
    "discontinued_by_poe_id",
)


def structured_payload(event: Mapping[str, Any]) -> dict[str, Any]:
    raw = event.get("value_structured_json")
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _parse_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _clean(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


def relations_of(event: Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(event.get("relations"), Mapping):
        return dict(event["relations"])
    payload = structured_payload(event)
    relations = payload.get("relations")
    return dict(relations) if isinstance(relations, Mapping) else {}


def chain_root_poe_id(event: Mapping[str, Any]) -> str | None:
    for candidate in (
        event.get("chain_root_poe_id"),
        event.get("poe_chain_root_id"),
        relations_of(event).get("chain_root_poe_id"),
        structured_payload(event).get("chain_root_poe_id"),
    ):
        cleaned = _clean(candidate)
        if cleaned:
            return cleaned
    return None


def specimen_id_of(event: Mapping[str, Any]) -> str | None:
    for candidate in (
        event.get("specimen_id"),
        structured_payload(event).get("specimen_id"),
    ):
        cleaned = _clean(candidate)
        if cleaned:
            return cleaned
    for field in ("raw_record_json", "clinical_readable_record_json"):
        parsed = _parse_json_object(event.get(field))
        cleaned = _clean(parsed.get("specimen_id"))
        if cleaned:
            return cleaned
    return None


def micro_specimen_id_of(event: Mapping[str, Any]) -> str | None:
    for candidate in (
        event.get("micro_specimen_id"),
        structured_payload(event).get("micro_specimen_id"),
    ):
        cleaned = _clean(candidate)
        if cleaned:
            return cleaned
    for field in ("raw_record_json", "clinical_readable_record_json"):
        parsed = _parse_json_object(event.get(field))
        cleaned = _clean(parsed.get("micro_specimen_id"))
        if cleaned:
            return cleaned
    return None


def order_type_of(event: Mapping[str, Any]) -> str | None:
    category = event.get("clinical_category")
    if isinstance(category, Mapping):
        cleaned = _clean(category.get("raw"))
        if cleaned:
            return cleaned
    for candidate in (
        event.get("order_type"),
        structured_payload(event).get("order_type"),
    ):
        cleaned = _clean(candidate)
        if cleaned:
            return cleaned
    kind = _clean(event.get("event_kind"))
    if kind == "laboratory_ordered":
        return "Lab"
    if kind == "imaging_ordered":
        return "Radiology"
    if kind == "medication_ordered":
        return "Medications"
    return None


def order_subtype_of(event: Mapping[str, Any]) -> str | None:
    category = event.get("clinical_category")
    if isinstance(category, Mapping):
        cleaned = _clean(category.get("subtype_raw"))
        if cleaned:
            return cleaned
    for candidate in (
        event.get("order_subtype"),
        structured_payload(event).get("order_subtype"),
        event.get("source_label"),
        event.get("preferred_name"),
    ):
        cleaned = _clean(candidate)
        if cleaned:
            return cleaned
    return None


def lifecycle_action_of(event: Mapping[str, Any]) -> str:
    raw = (
        event.get("lifecycle_action")
        or event.get("action")
        or event.get("transaction_type")
        or event.get("source_action")
        or "uninterpreted"
    )
    normalized = str(raw).strip().casefold()
    mapping = {
        "new": "create",
        "create": "create",
        "change": "change",
        "d/c": "discontinue",
        "discontinue": "discontinue",
        "discontinued": "discontinue",
        "cancel": "cancel",
        "cancelled": "cancel",
    }
    return mapping.get(normalized, "uninterpreted")


def candidate_specificity_of(
    *,
    content_specificity: str | None,
    order_subtype: str | None,
    track_id: str | None,
) -> str:
    if content_specificity in {"entity_specific", "attribute_enriched", "subtype_only", "category_only"}:
        if content_specificity == "entity_specific":
            return "entity"
        if content_specificity == "subtype_only":
            return "subtype"
        if content_specificity == "category_only":
            return "category"
        return "subtype"
    if track_id == "generic_lab_order":
        return "category"
    if track_id in {"lab_result_proxy", "imaging_result_proxy"}:
        return "entity"
    if order_subtype:
        return "subtype"
    return "category"


def candidate_name_of(event: Mapping[str, Any], *, track_id: str, order_type: str | None, order_subtype: str | None) -> str:
    if track_id == "generic_lab_order":
        return order_type or "Lab"
    if track_id == "imaging_result_proxy":
        for candidate in (event.get("exam_name"), event.get("preferred_name"), event.get("source_label")):
            cleaned = _clean(candidate)
            if cleaned and cleaned.casefold() not in {"rr", "radiology report"}:
                return cleaned
        raise ValueError("imaging report requires radiology_detail.exam_name")
    for candidate in (
        order_subtype,
        event.get("preferred_name"),
        event.get("source_label"),
        order_type,
    ):
        cleaned = _clean(candidate)
        if cleaned:
            return cleaned
    raise ValueError("investigation event requires a source candidate name")


def lift_order_fields(event: Mapping[str, Any]) -> dict[str, Any]:
    """Return a shallow copy with POE / specimen keys at the top level."""
    payload = structured_payload(event)
    relations = relations_of(event)
    row = dict(event)
    row["poe_id"] = _clean(event.get("poe_id") or payload.get("poe_id"))
    row["poe_seq"] = _clean(event.get("poe_seq") or payload.get("poe_seq"))
    row["chain_root_poe_id"] = chain_root_poe_id(event)
    row["order_type"] = order_type_of(event)
    row["order_subtype"] = order_subtype_of(event)
    row["specimen_id"] = specimen_id_of(event)
    row["micro_specimen_id"] = micro_specimen_id_of(event)
    row["lifecycle_action"] = lifecycle_action_of(event)
    row["relations"] = relations
    row["lineage_visibility_scope"] = "retrospective_only"
    for field in RETROSPECTIVE_ONLY_FIELDS:
        if field in relations:
            row[f"retrospective_{field}"] = relations.get(field)
    return row
