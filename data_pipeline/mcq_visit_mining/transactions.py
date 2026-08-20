"""Build one family's visit transactions. Forbidden fields never enter this structure."""

from __future__ import annotations

import hashlib
from datetime import timedelta
from typing import Any, Iterable

from data_pipeline.mcq_visit_standardize.text import collapse_ws, lookup_key
from data_pipeline.mcq_visit_timeline.clocks import hours_between, parse_datetime

from .families import FamilyContract, IsolationError, assert_isolated
from .features import presentation_features


def visit_key(subject_id: str, hadm_id: str) -> str:
    return hashlib.sha256(f"{subject_id}|{hadm_id}".encode("utf-8")).hexdigest()


def _sid(value: Any) -> str:
    return str(value or "").strip()


def _mapped(event: dict[str, Any]) -> bool:
    return str(event.get("mapping_status") or "").startswith("mapped")


def _outcome(outcome_id: str, name: str, *, grain: str, source_event_kind: str, category_only: bool = False) -> dict[str, Any]:
    return {
        "outcome_id": outcome_id,
        "outcome_name": name,
        "grain": grain,
        "source_event_kind": source_event_kind,
        "category_only": category_only,
    }


def _in_hours_window(
    event: dict[str, Any],
    *,
    origin: Any,
    hours: float,
    time_field: str,
    date_precision: bool,
) -> bool:
    origin_dt = parse_datetime(origin)
    stamp = event.get(time_field)
    event_dt = parse_datetime(stamp)
    if origin_dt is None or event_dt is None:
        return False
    if date_precision:
        last = (origin_dt + timedelta(hours=hours)).date()
        return origin_dt.date() <= event_dt.date() <= last
    delta = hours_between(origin_dt, event_dt)
    if delta is None:
        return False
    return 0 <= delta < hours


def type1_outcomes(
    events: Iterable[dict[str, Any]],
    *,
    origin: Any,
    hours: float,
    high_signal_itemids: set[str],
    skip_poe_category_only: bool,
) -> list[dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.get("time_missing"):
            continue
        kind = str(event.get("event_kind") or "")
        if kind == "poe_lab_imaging":
            if skip_poe_category_only or event.get("category_only"):
                continue
            continue
        if not _in_hours_window(
            event, origin=origin, hours=hours, time_field="occurrence_time", date_precision=False
        ):
            continue
        if kind == "radiology_reported" and _mapped(event) and event.get("standard_name"):
            name = str(event["standard_name"])
            oid = f"imaging:{lookup_key(name) or name.casefold()}"
            found[oid] = _outcome(oid, name, grain="exam", source_event_kind=kind)
        elif kind in {"cardiology_ordered", "respiratory_ordered"} and event.get("standard_name"):
            name = str(event["standard_name"])
            oid = f"order:{lookup_key(name) or name.casefold()}"
            found[oid] = _outcome(oid, name, grain="order", source_event_kind=kind)
        elif kind == "lab_resulted":
            itemid = _sid(event.get("itemid"))
            if itemid not in high_signal_itemids:
                continue
            if not _mapped(event) and not event.get("standard_name"):
                continue
            name = str(event.get("standard_name") or itemid)
            oid = f"lab:{itemid}"
            found[oid] = _outcome(oid, name, grain="high_signal_lab", source_event_kind=kind)
        elif kind in {"medication_prescribed", "procedure_recorded", "service_transfer", "transfer"}:
            continue
    return [found[key] for key in sorted(found)]


def type2_result_flags(
    events: Iterable[dict[str, Any]],
    *,
    origin: Any,
    hours: float,
) -> list[dict[str, str]]:
    flags: dict[str, dict[str, str]] = {}
    for event in events:
        if str(event.get("event_kind") or "") != "lab_resulted":
            continue
        if not event.get("available_time"):
            continue
        if not _in_hours_window(
            event, origin=origin, hours=hours, time_field="available_time", date_precision=False
        ):
            continue
        flag = lookup_key(event.get("flag"))
        if not flag:
            continue
        name = collapse_ws(event.get("standard_name")) or _sid(event.get("itemid"))
        feature_id = f"investigation_result_flag:{flag}:{lookup_key(name) or name.casefold()}"
        flags[feature_id] = {
            "feature_id": feature_id,
            "feature_type": "investigation_result_flag",
            "display_name": f"{name} {flag}",
        }
    return [flags[key] for key in sorted(flags)]


def type3_medication_outcomes(
    events: Iterable[dict[str, Any]],
    *,
    origin: Any,
    hours: float,
) -> list[dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for event in events:
        if str(event.get("event_kind") or "") != "medication_prescribed":
            continue
        if event.get("time_missing") or not _mapped(event):
            continue
        if not _in_hours_window(
            event, origin=origin, hours=hours, time_field="occurrence_time", date_precision=False
        ):
            continue
        raw = str(event.get("standard_name") or "")
        ingredients = [part.strip() for part in raw.split("|") if part.strip()]
        for ingredient in ingredients:
            oid = f"drug:{lookup_key(ingredient) or ingredient.casefold()}"
            found[oid] = _outcome(
                oid, ingredient, grain="ingredient", source_event_kind="medication_prescribed"
            )
    return [found[key] for key in sorted(found)]


def type3_procedure_outcomes(
    events: Iterable[dict[str, Any]],
    *,
    origin: Any,
    hours: float,
) -> list[dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for event in events:
        if str(event.get("event_kind") or "") != "procedure_recorded":
            continue
        if event.get("time_missing") or not event.get("standard_name"):
            continue
        if not _in_hours_window(
            event, origin=origin, hours=hours, time_field="occurrence_time", date_precision=True
        ):
            continue
        name = str(event["standard_name"])
        oid = f"procedure:{lookup_key(name) or name.casefold()}"
        found[oid] = _outcome(oid, name, grain="procedure", source_event_kind="procedure_recorded")
    return [found[key] for key in sorted(found)]


def build_transaction(
    facts: dict[str, Any],
    events: list[dict[str, Any]],
    *,
    contract: FamilyContract,
    window: dict[str, Any],
    vital_spec: dict[str, Any],
    high_signal_itemids: set[str],
    skip_poe_category_only: bool,
) -> dict[str, Any]:
    family = contract.family
    origin = facts.get("presentation_origin")
    hours = window.get("hours")
    features = presentation_features(facts, vital_spec, contract)
    if family == "type2_diagnosis" and hours is not None:
        features.extend(type2_result_flags(events, origin=origin, hours=float(hours)))
        features = [item for item in {row["feature_id"]: row for row in features}.values()]
        features.sort(key=lambda row: row["feature_id"])
    if family == "type1_investigation":
        outcomes = type1_outcomes(
            events,
            origin=origin,
            hours=float(hours),
            high_signal_itemids=high_signal_itemids,
            skip_poe_category_only=skip_poe_category_only,
        )
    elif family == "type2_diagnosis":
        diagnosis = collapse_ws(facts.get("standard_diagnosis_name"))
        outcomes = []
        if diagnosis:
            oid = f"dx:{lookup_key(diagnosis) or diagnosis.casefold()}"
            outcomes = [_outcome(oid, diagnosis, grain="discharge_icd", source_event_kind="visit")]
    elif family == "type3_medication":
        outcomes = type3_medication_outcomes(events, origin=origin, hours=float(hours))
    elif family == "type3_procedure":
        outcomes = type3_procedure_outcomes(events, origin=origin, hours=float(hours))
    elif family == "type4_service":
        service = collapse_ws(facts.get("standard_service_name")) or collapse_ws(facts.get("primary_service"))
        outcomes = []
        if service:
            oid = f"service:{lookup_key(service) or service.casefold()}"
            outcomes = [_outcome(oid, service, grain="primary_service", source_event_kind="visit")]
    elif family == "type5_disposition":
        location = collapse_ws(facts.get("discharge_location"))
        outcomes = []
        if location:
            oid = f"disposition:{lookup_key(location) or location.casefold()}"
            outcomes = [_outcome(oid, location, grain="discharge_location", source_event_kind="visit")]
    else:
        raise IsolationError(f"no outcome builder for {family}")

    assert_isolated(features, contract, outcomes=outcomes)
    hadm_id = _sid(facts.get("hadm_id"))
    subject_id = _sid(facts.get("subject_id"))
    return {
        "visit_key": visit_key(subject_id, hadm_id),
        "hadm_id": hadm_id,
        "family": family,
        "window_id": window.get("window_id"),
        "features": features,
        "outcomes": outcomes,
        "posthoc_flags": list(contract.posthoc_flags),
    }
