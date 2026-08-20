"""Apply frozen maps to one visit. Original 45 columns are copied, never rewritten."""

from __future__ import annotations

from typing import Any

from data_pipeline.mcq_visit_extract.columns import RESULT_COLUMNS

from .mappings import (
    DRUG_INGREDIENTS,
    MAPPING_VERSION,
    RHYTHM_ALIASES,
    SERVICE_NAMES,
    UNIT_ALIAS_TABLE,
)
from .drugs import resolve_drug_ingredients
from .exams import standardize_exam_name
from .symptoms import allergy_concepts, complaint_concepts
from .text import collapse_ws, is_redacted, lookup_key

ReviewItem = dict[str, Any]


def fahrenheit_to_celsius(value: float) -> float:
    return round((value - 32.0) * 5.0 / 9.0, 1)


def celsius_to_fahrenheit(value: float) -> float:
    return round(value * 9.0 / 5.0 + 32.0, 1)


def _status_item(
    *,
    domain: str,
    field: str,
    source: str,
    status: str,
) -> ReviewItem | None:
    if status != "unresolved":
        return None
    return {"domain": domain, "field": field, "source": source, "status": status}


def _normalize_unit(
    raw: Any,
    extra_units: dict[str, tuple[str, str]] | None = None,
) -> tuple[str | None, str]:
    collapsed = collapse_ws(raw)
    if collapsed is None:
        return None, "not_applicable"
    key = lookup_key(collapsed)
    if key in {"n/a", "na", "none"}:
        return None, "not_applicable"
    if extra_units and key in extra_units:
        return extra_units[key][0], "mapped/exact"
    if key in UNIT_ALIAS_TABLE:
        return UNIT_ALIAS_TABLE[key], "mapped/exact"
    return collapsed, "unresolved"


def _map_name(raw: Any, table: dict[str, str]) -> tuple[str | None, str]:
    collapsed = collapse_ws(raw)
    if collapsed is None:
        return None, "not_applicable"
    mapped = table.get(lookup_key(collapsed) or "")
    if mapped:
        return mapped, "mapped/exact"
    return collapsed, "unresolved"


def _lab_item(
    item: dict[str, Any],
    reviews: list[ReviewItem],
    extra_units: dict[str, tuple[str, str]] | None = None,
) -> dict[str, Any]:
    label = collapse_ws(item.get("label"))
    fluid = collapse_ws(item.get("fluid"))
    if label and fluid:
        standard = f"{label}, {fluid}"
        status = "mapped/exact"
    elif label:
        standard = label
        status = "mapped/exact"
    else:
        standard = None
        status = "unresolved"
        reviews.append(
            {"domain": "lab", "field": "investigations.laboratory", "source": str(item.get("itemid")), "status": status}
        )
    results = []
    for row in item.get("results") or []:
        unit, unit_status = _normalize_unit(row.get("valueuom"), extra_units=extra_units)
        if unit_status == "unresolved" and row.get("valueuom"):
            reviews.append(
                {
                    "domain": "unit",
                    "field": "investigations.laboratory.valueuom",
                    "source": str(row.get("valueuom")),
                    "status": unit_status,
                }
            )
        results.append(
            {
                "charttime": row.get("charttime"),
                "storetime": row.get("storetime"),
                "valuenum": row.get("valuenum"),
                "source_unit": collapse_ws(row.get("valueuom")),
                "normalized_unit": unit,
                "unit_status": unit_status,
                "flag": row.get("flag"),
            }
        )
    return {
        "itemid": item.get("itemid"),
        "source_label": item.get("label"),
        "standard_test_name": standard,
        "fluid": item.get("fluid"),
        "status": status,
        "results": results,
    }


def _radiology_item(
    item: dict[str, Any],
    reviews: list[ReviewItem],
    extra_exams: dict[str, tuple[str, str]] | None = None,
) -> dict[str, Any]:
    source = collapse_ws(item.get("exam_name"))
    key = lookup_key(source)
    if extra_exams and key in extra_exams:
        standard, _concept_id = extra_exams[key]
        return {
            "source_exam_name": item.get("exam_name"),
            "standard_exam_name": standard,
            "status": "mapped/exact",
            "charttime": item.get("charttime"),
            "storetime": item.get("storetime"),
        }
    if not source or is_redacted(source):
        return {
            "source_exam_name": item.get("exam_name"),
            "standard_exam_name": None,
            "status": "not_applicable",
            "charttime": item.get("charttime"),
            "storetime": item.get("storetime"),
        }
    standard, status = standardize_exam_name(source)
    if status == "unresolved":
        reviews.append(
            {
                "domain": "radiology",
                "field": "radiology.exam_name",
                "source": source,
                "status": status,
            }
        )
    return {
        "source_exam_name": item.get("exam_name"),
        "standard_exam_name": standard,
        "status": status,
        "charttime": item.get("charttime"),
        "storetime": item.get("storetime"),
    }


def _order_item(item: dict[str, Any]) -> dict[str, Any]:
    subtype = collapse_ws(item.get("order_subtype"))
    return {
        "source_order_subtype": item.get("order_subtype"),
        "standard_order_name": subtype,
        "status": "mapped/exact" if subtype else "not_applicable",
        "ordertime": item.get("ordertime"),
    }


def _drug_item(
    name: Any,
    field: str,
    reviews: list[ReviewItem],
    extra_drugs: dict[str, tuple[str, str]] | None = None,
) -> dict[str, Any]:
    source = collapse_ws(name)
    if source is None:
        return {
            "source_drug": name,
            "standard_ingredients": [],
            "status": "not_applicable",
        }
    key = lookup_key(source) or ""
    if extra_drugs and key in extra_drugs:
        standard = extra_drugs[key][0]
        ingredients = tuple(part.strip() for part in str(standard).split("|") if part.strip())
        return {
            "source_drug": source,
            "standard_ingredients": list(ingredients),
            "status": "mapped/exact",
        }
    mapped = DRUG_INGREDIENTS.get(key)
    if mapped:
        return {
            "source_drug": source,
            "standard_ingredients": list(mapped),
            "status": "mapped/exact",
        }
    resolved = resolve_drug_ingredients(source)
    if resolved and lookup_key(resolved[0]) != key:
        return {
            "source_drug": source,
            "standard_ingredients": list(resolved),
            "status": "mapped/exact",
        }
    reviews.append({"domain": "drug", "field": field, "source": source, "status": "unresolved"})
    return {
        "source_drug": source,
        "standard_ingredients": [],
        "status": "unresolved",
    }


def standardize_visit(
    visit: dict[str, Any],
    extra_symptoms: dict[str, tuple[str, str]] | None = None,
    extra_exams: dict[str, tuple[str, str]] | None = None,
    extra_drugs: dict[str, tuple[str, str]] | None = None,
    extra_allergies: dict[str, tuple[str, str]] | None = None,
    extra_units: dict[str, tuple[str, str]] | None = None,
    extra_rhythms: dict[str, tuple[str, str]] | None = None,
) -> tuple[dict[str, Any], list[ReviewItem]]:
    missing = [key for key in RESULT_COLUMNS if key not in visit]
    if missing:
        raise ValueError(f"visit missing extract columns: {missing}")
    original = {key: visit[key] for key in RESULT_COLUMNS}
    reviews: list[ReviewItem] = []

    cc = complaint_concepts(original.get("chief_complaint"), extra_aliases=extra_symptoms)
    ed_cc = complaint_concepts(original.get("ed_chief_complaint"), extra_aliases=extra_symptoms)
    for concept in cc:
        item = _status_item(
            domain="symptom",
            field="chief_complaint",
            source=str(concept["source"]),
            status=concept["status"],
        )
        if item:
            reviews.append(item)
    for concept in ed_cc:
        item = _status_item(
            domain="symptom",
            field="ed_chief_complaint",
            source=str(concept["source"]),
            status=concept["status"],
        )
        if item:
            reviews.append(item)

    allergies = allergy_concepts(original.get("allergies"), extra_aliases=extra_allergies)
    for concept in allergies:
        item = _status_item(
            domain="allergy", field="allergies", source=str(concept["source"]), status=concept["status"]
        )
        if item:
            reviews.append(item)

    rhythm_table = dict(RHYTHM_ALIASES)
    if extra_rhythms:
        rhythm_table.update({key: value[0] for key, value in extra_rhythms.items()})
    rhythm_standard, rhythm_status = _map_name(original.get("rhythm"), rhythm_table)
    if rhythm_status == "unresolved" and original.get("rhythm"):
        reviews.append(
            {"domain": "rhythm", "field": "rhythm", "source": str(original.get("rhythm")), "status": "unresolved"}
        )

    temperature = original.get("temperature")
    temperature_c = None
    temperature_status = "not_applicable"
    if isinstance(temperature, (int, float)):
        temperature_c = fahrenheit_to_celsius(float(temperature))
        temperature_status = "mapped/converted"

    investigations = original.get("investigations") or {}
    investigations_normalized = {
        "laboratory": [
            _lab_item(item, reviews, extra_units=extra_units) for item in investigations.get("laboratory") or []
        ],
        "radiology": [
            _radiology_item(item, reviews, extra_exams=extra_exams)
            for item in investigations.get("radiology") or []
        ],
        "cardiology": [_order_item(item) for item in investigations.get("cardiology") or []],
        "respiratory": [_order_item(item) for item in investigations.get("respiratory") or []],
    }

    meds = []
    for item in original.get("medications") or []:
        payload = _drug_item(
            item.get("drug"), "medications", reviews, extra_drugs=extra_drugs
        )
        payload["starttime"] = item.get("starttime")
        payload["stoptime"] = item.get("stoptime")
        meds.append(payload)
    medrecon = []
    for item in original.get("medrecon") or []:
        payload = _drug_item(
            item.get("name"), "medrecon", reviews, extra_drugs=extra_drugs
        )
        payload["charttime"] = item.get("charttime")
        medrecon.append(payload)

    procedures = []
    for item in original.get("procedures") or []:
        name = collapse_ws(item.get("procedure_name"))
        procedures.append(
            {
                "source_name": item.get("procedure_name"),
                "icd_code": item.get("icd_code"),
                "icd_version": item.get("icd_version"),
                "chartdate": item.get("chartdate"),
                "standard_procedure_name": name,
                "status": "mapped/exact" if name else "unresolved",
            }
        )

    diagnosis = collapse_ws(original.get("primary_diagnosis_name"))
    other = []
    for name in original.get("other_diagnoses") or []:
        collapsed = collapse_ws(name)
        other.append(
            {
                "source": name,
                "standard": collapsed,
                "status": "mapped/exact" if collapsed else "unresolved",
            }
        )
    ed_dx = []
    for item in original.get("ed_diagnoses") or []:
        title = collapse_ws(item.get("icd_title"))
        ed_dx.append(
            {
                "source": item.get("icd_title"),
                "icd_code": item.get("icd_code"),
                "standard": title,
                "status": "mapped/exact" if title else "unresolved",
            }
        )

    service_standard, service_status = _map_name(original.get("primary_service"), SERVICE_NAMES)
    if service_status == "unresolved" and original.get("primary_service"):
        reviews.append(
            {
                "domain": "service",
                "field": "primary_service",
                "source": str(original.get("primary_service")),
                "status": "unresolved",
            }
        )

    poe = []
    for item in original.get("poe_lab_imaging") or []:
        poe.append(
            {
                "order_type": item.get("order_type"),
                "source_order_subtype": item.get("order_subtype"),
                "standard_order_name": collapse_ws(item.get("order_subtype")),
                "status": "mapped/exact" if collapse_ws(item.get("order_subtype")) else "not_applicable",
            }
        )

    derived = {
        "chief_complaint_concepts": cc,
        "ed_chief_complaint_concepts": ed_cc,
        "allergy_concepts": allergies,
        "standard_rhythm": {
            "source": original.get("rhythm"),
            "standard": rhythm_standard,
            "status": rhythm_status if original.get("rhythm") else "not_applicable",
        },
        "temperature_f": temperature if isinstance(temperature, (int, float)) else None,
        "temperature_c": temperature_c,
        "vitals_units": {
            "temperature": "°C" if temperature_status == "mapped/converted" else None,
            "temperature_source": "°F" if temperature_status == "mapped/converted" else None,
            "heartrate": "bpm" if original.get("heartrate") is not None else None,
            "resprate": "/min" if original.get("resprate") is not None else None,
            "o2sat": "%" if original.get("o2sat") is not None else None,
            "sbp": "mmHg" if original.get("sbp") is not None else None,
            "dbp": "mmHg" if original.get("dbp") is not None else None,
        },
        "investigations_normalized": investigations_normalized,
        "medications_normalized": meds,
        "medrecon_normalized": medrecon,
        "procedures_normalized": procedures,
        "standard_diagnosis_name": {
            "source": original.get("primary_diagnosis_name"),
            "standard": diagnosis,
            "icd_code": original.get("primary_icd_code"),
            "icd_version": original.get("primary_icd_version"),
            "status": "mapped/exact" if diagnosis else "unresolved",
        },
        "other_diagnoses_normalized": other,
        "ed_diagnoses_normalized": ed_dx,
        "standard_service_name": {
            "source": original.get("primary_service"),
            "standard": service_standard if service_status == "mapped/exact" else None,
            "status": service_status if original.get("primary_service") else "not_applicable",
        },
        "poe_lab_imaging_normalized": poe,
        "mapping_version": MAPPING_VERSION,
    }
    return {**original, **derived}, reviews
