"""Frozen deterministic normalization, separate from source transformers."""

from __future__ import annotations

import re
from typing import Any


MAPPING_VERSION = "event-terminology/1.0.0"

REVIEWED_TEXT_MAPPINGS = {
    ("symptom", "chest pain"): ("symptom:chest_pain", "Chest pain", "reviewed-synonym"),
    ("imaging_study", "general xray"): (
        "investigation:general_xray",
        "General radiography",
        "reviewed-local-order-subtype",
    ),
}

VITAL_CONCEPTS = {
    "heart_rate": ("vital:heart_rate", "Heart rate", "/min"),
    "blood_pressure": ("vital:blood_pressure", "Blood pressure", "mmHg"),
    "temperature": ("vital:temperature", "Temperature", "°F"),
    "respiratory_rate": ("vital:respiratory_rate", "Respiratory rate", "/min"),
    "oxygen_saturation": ("vital:oxygen_saturation", "Oxygen saturation", "%"),
    "pain_score": ("vital:pain_score", "Pain score", None),
}

UNIT_ALIASES = {
    "/min": "/min",
    "mmhg": "mmHg",
    "%": "%",
    "g/dl": "g/dL",
    "mg/dl": "mg/dL",
    "meq/l": "mEq/L",
    "mmol/l": "mmol/L",
    "k/ul": "K/uL",
    "°f": "°F",
}


def normalized_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return re.sub(r"\s+", " ", str(value).strip()).casefold()


def resolve_term(
    entity_type: str | None,
    source_concept_id: str | None,
    source_label: str | None,
) -> dict[str, str | None]:
    raw_label = normalized_text(source_label)
    if source_concept_id:
        return {
            "concept_id": source_concept_id,
            "preferred_name": source_label or source_concept_id,
            "normalization_status": "mapped",
            "mapping_rule": "source-code",
        }
    reviewed = REVIEWED_TEXT_MAPPINGS.get((entity_type, raw_label))
    if reviewed:
        concept_id, preferred_name, mapping_rule = reviewed
        return {
            "concept_id": concept_id,
            "preferred_name": preferred_name,
            "normalization_status": "mapped",
            "mapping_rule": mapping_rule,
        }
    if entity_type is None:
        return {
            "concept_id": None,
            "preferred_name": None,
            "normalization_status": "not_applicable",
            "mapping_rule": "not-applicable",
        }
    return {
        "concept_id": None,
        "preferred_name": source_label,
        "normalization_status": "unresolved",
        "mapping_rule": "unresolved",
    }


def resolve_unit(unit: str | None) -> tuple[str | None, str]:
    if unit in (None, ""):
        return None, "not_applicable"
    mapped_unit = UNIT_ALIASES.get(normalized_text(unit))
    return mapped_unit, "mapped" if mapped_unit else "unresolved"


def normalize_event(event: dict[str, Any]) -> tuple[dict[str, Any], str]:
    resolution = resolve_term(
        event.get("entity_type"),
        event.get("source_concept_id"),
        event.get("source_label"),
    )
    event["concept_id"] = resolution["concept_id"]
    event["preferred_name"] = resolution["preferred_name"]
    event["normalization_status"] = resolution["normalization_status"]
    event["terminology_mapping_version"] = MAPPING_VERSION
    event["normalized_value_numeric"] = event.get("value_numeric")
    event["normalized_value_text"] = event.get("value_text")
    event["normalized_unit"], event["unit_normalization_status"] = resolve_unit(
        event.get("unit")
    )
    return event, str(resolution["mapping_rule"])
