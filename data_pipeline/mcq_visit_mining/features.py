"""Presentation features and vital flags. No narrative text, no post-hoc fields unless allowed."""

from __future__ import annotations

from typing import Any

from data_pipeline.mcq_visit_standardize.text import collapse_ws, lookup_key

from .families import FamilyContract


def age_band(age: Any) -> str | None:
    try:
        years = int(age)
    except (TypeError, ValueError):
        return None
    if years < 18:
        return None
    if years < 40:
        return "18-39"
    if years < 50:
        return "40-49"
    if years < 60:
        return "50-59"
    if years < 70:
        return "60-69"
    if years < 80:
        return "70-79"
    return "80+"


def _feature(feature_id: str, feature_type: str, display_name: str) -> dict[str, str]:
    return {
        "feature_id": feature_id,
        "feature_type": feature_type,
        "display_name": display_name,
    }


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def vital_flag_features(facts: dict[str, Any], spec: dict[str, Any]) -> list[dict[str, str]]:
    flags: list[dict[str, str]] = []
    for name, rule in (spec.get("flags") or {}).items():
        field = str(rule.get("field"))
        op = str(rule.get("op"))
        threshold = float(rule.get("value"))
        measured = _numeric(facts.get(field))
        if measured is None:
            continue
        matched = measured >= threshold if op == ">=" else measured < threshold
        if matched:
            flags.append(_feature(f"physiologic_flag:{name}", "physiologic_flag", name.replace("_", " ")))
    return flags


def _mapped_concepts(items: Any, *, feature_type: str) -> list[dict[str, str]]:
    features: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in items or []:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "")
        polarity = str(item.get("polarity") or "asserted")
        if not status.startswith("mapped"):
            continue
        if polarity != "asserted":
            continue
        standard = collapse_ws(item.get("standard"))
        if not standard:
            continue
        key = lookup_key(standard) or standard.casefold()
        feature_id = f"{feature_type}:{key}"
        if feature_id in seen:
            continue
        seen.add(feature_id)
        features.append(_feature(feature_id, feature_type, standard))
    return features


def presentation_features(facts: dict[str, Any], vital_spec: dict[str, Any], contract: FamilyContract) -> list[dict[str, str]]:
    features: list[dict[str, str]] = []
    allowed = contract.allowed_feature_types
    if "age_band" in allowed:
        band = age_band(facts.get("age_at_encounter"))
        if band:
            features.append(_feature(f"age_band:{band}", "age_band", band))
    if "sex" in allowed:
        sex = collapse_ws(facts.get("sex"))
        if sex in {"M", "F"}:
            features.append(_feature(f"sex:{sex}", "sex", sex))
    if "admission_type" in allowed:
        admission = collapse_ws(facts.get("admission_type"))
        if admission:
            key = lookup_key(admission) or admission.casefold()
            features.append(_feature(f"admission_type:{key}", "admission_type", admission))
    if "symptom" in allowed:
        features.extend(_mapped_concepts(facts.get("chief_complaint_concepts"), feature_type="symptom"))
        features.extend(_mapped_concepts(facts.get("ed_chief_complaint_concepts"), feature_type="symptom"))
    if "physiologic_flag" in allowed:
        features.extend(vital_flag_features(facts, vital_spec))
    if "allergy" in allowed:
        features.extend(_mapped_concepts(facts.get("allergy_concepts"), feature_type="allergy"))
    if "diagnosis" in allowed:
        diagnosis = collapse_ws(facts.get("standard_diagnosis_name"))
        if diagnosis:
            key = lookup_key(diagnosis) or diagnosis.casefold()
            features.append(_feature(f"diagnosis:{key}", "diagnosis", diagnosis))
    dedup: dict[str, dict[str, str]] = {}
    for feature in features:
        dedup[feature["feature_id"]] = feature
    ordered = [dedup[key] for key in sorted(dedup)]
    return [item for item in ordered if item["feature_type"] in allowed]
