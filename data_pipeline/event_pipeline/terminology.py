"""Frozen deterministic normalization, separate from source transformers."""

from __future__ import annotations

import re
from typing import Any


MAPPING_VERSION = "event-terminology/1.1.0"

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
    "#/hpf": "#/hpf",
    "#/lpf": "#/lpf",
    "#/ul": "#/uL",
    "%": "%",
    "/hpf": "/hpf",
    "day": "day",
    "fl": "fL",
    "g/dl": "g/dL",
    "grams": "g",
    "hour": "h",
    "iu/l": "IU/L",
    "iu/ml": "IU/mL",
    "mg/dl": "mg/dL",
    "mg/l": "mg/L",
    "mg/mg": "mg/mg",
    "mg/24hr": "mg/24 h",
    "mg": "mg",
    "min": "min",
    "m/ul": "m/uL",
    "mcg": "mcg",
    "meq/l": "mEq/L",
    "meq": "mEq",
    "meq.": "mEq",
    "ml": "mL",
    "mm hg": "mmHg",
    "mm/hr": "mm/h",
    "mmhg": "mmHg",
    "mmol": "mmol",
    "mmol/l": "mmol/L",
    "mosm/kg": "mOsm/kg",
    "ng/dl": "ng/dL",
    "ng/ml": "ng/mL",
    "ng/ml feu": "ng/mL FEU",
    "pg": "pg",
    "pg/ml": "pg/mL",
    "ratio": "ratio",
    "sec": "s",
    "uiu/ml": "uIU/mL",
    "units": "units",
    "ug/dl": "ug/dL",
    "ug/ml": "ug/mL",
    "k/ul": "K/uL",
    "l": "L",
    "l/min": "L/min",
    "log10 iu/ml": "log10 IU/mL",
    "°f": "°F",
}
NON_UNIT_VALUES = {"n/a"}


def normalized_text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return re.sub(r"\s+", " ", str(value).strip()).casefold()


def _source_code_is_usable(source_concept_id: str) -> bool:
    vocabulary, separator, code = source_concept_id.partition(":")
    if not separator or not code:
        return False
    if vocabulary == "ndc":
        return bool(re.fullmatch(r"\d{11}", code)) and set(code) != {"0"}
    if vocabulary == "gsn":
        return bool(re.fullmatch(r"\d{6}", code))
    return True


def resolve_term(
    entity_type: str | None,
    source_concept_id: str | None,
    source_label: str | None,
) -> dict[str, str | None]:
    raw_label = normalized_text(source_label)
    if source_concept_id and _source_code_is_usable(source_concept_id):
        return {
            "concept_id": source_concept_id,
            "preferred_name": source_label or source_concept_id,
            "normalization_status": "mapped",
            "mapping_rule": "source-code",
        }
    if source_concept_id:
        return {
            "concept_id": None,
            "preferred_name": source_label,
            "normalization_status": "unresolved",
            "mapping_rule": "invalid-source-code",
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
    normalized = normalized_text(unit)
    if normalized in NON_UNIT_VALUES:
        return None, "not_applicable"
    mapped_unit = UNIT_ALIASES.get(normalized)
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
