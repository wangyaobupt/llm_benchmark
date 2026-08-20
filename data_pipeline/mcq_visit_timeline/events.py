"""Project one timed visit + one standardized visit into a sorted event list."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from data_pipeline.mcq_visit_standardize.text import collapse_ws, lookup_key
from data_pipeline.mcq_visit_standardize.transform import fahrenheit_to_celsius

from .clocks import format_datetime, hours_between, parse_datetime, presentation_origin
from .join_names import (
    lab_name_index,
    medication_index,
    order_index,
    procedure_index,
    radiology_index,
    take_medication,
    take_order,
    take_radiology,
)
from .schema import EVENT_COLUMNS, EVENT_KINDS


def _sid(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _event_id(
    hadm_id: str,
    event_kind: str,
    occurrence_time: str | None,
    source_field: str,
    business_key: list[Any],
) -> str:
    payload = [hadm_id, event_kind, occurrence_time or "", source_field, *[_sid(part) for part in business_key]]
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return digest[:24]


def _mapped_status(item: dict[str, Any] | None, fallback: str = "unresolved") -> str:
    if not item:
        return fallback
    status = item.get("status")
    if isinstance(status, str) and status:
        return status
    return fallback


def _name_from(item: dict[str, Any] | None, *keys: str) -> str | None:
    if not item:
        return None
    for key in keys:
        value = collapse_ws(item.get(key))
        if value:
            return value
    return None


def _finish(
    *,
    subject_id: str,
    hadm_id: str,
    event_kind: str,
    domain: str,
    fact_type: str,
    occurrence: Any,
    occurrence_basis: str | None,
    available: Any,
    available_basis: str | None,
    admit_dt,
    origin_dt,
    precision: str,
    standard_name: str | None,
    source_name: str | None,
    mapping_status: str,
    itemid: Any = None,
    source_field: str,
    category_only: bool = False,
    valuenum: Any = None,
    flag: Any = None,
    business_key: list[Any],
) -> dict[str, Any]:
    occ_dt = parse_datetime(occurrence)
    avail_dt = parse_datetime(available)
    occ_text = format_datetime(occ_dt) if occ_dt else (collapse_ws(occurrence))
    avail_text = format_datetime(avail_dt) if avail_dt else (collapse_ws(available))
    time_missing = occ_dt is None
    event = {
        "event_id": _event_id(hadm_id, event_kind, occ_text, source_field, business_key),
        "subject_id": subject_id,
        "hadm_id": hadm_id,
        "event_kind": event_kind,
        "domain": domain,
        "fact_type": fact_type,
        "occurrence_time": occ_text,
        "occurrence_basis": occurrence_basis,
        "available_time": avail_text,
        "available_basis": available_basis,
        "hours_from_admit": hours_between(admit_dt, occ_dt),
        "hours_from_presentation": hours_between(origin_dt, occ_dt),
        "time_precision": precision,
        "time_missing": time_missing,
        "standard_name": standard_name,
        "source_name": source_name,
        "mapping_status": mapping_status,
        "itemid": _sid(itemid) or None,
        "source_field": source_field,
        "category_only": bool(category_only),
        "valuenum": float(valuenum) if isinstance(valuenum, (int, float)) else None,
        "flag": collapse_ws(flag),
    }
    if event_kind not in EVENT_KINDS:
        raise ValueError(f"unknown event_kind {event_kind}")
    return {key: event.get(key) for key in EVENT_COLUMNS}


def _clock_event(
    *,
    subject_id: str,
    hadm_id: str,
    event_kind: str,
    domain: str,
    occurrence: Any,
    basis: str,
    admit_dt,
    origin_dt,
    source_field: str,
    standard_name: str,
    precision: str = "datetime",
) -> dict[str, Any] | None:
    if parse_datetime(occurrence) is None and not collapse_ws(occurrence):
        return None
    return _finish(
        subject_id=subject_id,
        hadm_id=hadm_id,
        event_kind=event_kind,
        domain=domain,
        fact_type="clock",
        occurrence=occurrence,
        occurrence_basis=basis,
        available=occurrence,
        available_basis=basis,
        admit_dt=admit_dt,
        origin_dt=origin_dt,
        precision=precision,
        standard_name=standard_name,
        source_name=standard_name,
        mapping_status="mapped/exact",
        source_field=source_field,
        business_key=[basis],
    )


def _temperature_c(timed: dict[str, Any], named: dict[str, Any]) -> float | None:
    named_c = named.get("temperature_c")
    if isinstance(named_c, (int, float)):
        return float(named_c)
    raw = timed.get("temperature")
    if isinstance(raw, (int, float)):
        return fahrenheit_to_celsius(float(raw))
    return None


def presentation_facts(timed: dict[str, Any], named: dict[str, Any]) -> dict[str, Any]:
    origin_dt, origin_text, origin_basis = presentation_origin(timed)
    return {
        "subject_id": _sid(timed.get("subject_id")),
        "hadm_id": _sid(timed.get("hadm_id")),
        "age_at_encounter": timed.get("age_at_encounter"),
        "sex": timed.get("sex"),
        "admission_type": timed.get("admission_type"),
        "admittime": collapse_ws(timed.get("admittime")),
        "dischtime": collapse_ws(timed.get("dischtime")),
        "deathtime": collapse_ws(timed.get("deathtime")),
        "ed_intime": collapse_ws(timed.get("ed_intime")),
        "presentation_origin": origin_text,
        "presentation_origin_basis": origin_basis,
        "vitals_source": timed.get("vitals_source"),
        "temperature": timed.get("temperature"),
        "temperature_c": _temperature_c(timed, named),
        "heartrate": timed.get("heartrate"),
        "resprate": timed.get("resprate"),
        "o2sat": timed.get("o2sat"),
        "sbp": timed.get("sbp"),
        "dbp": timed.get("dbp"),
        "acuity": timed.get("acuity"),
        "standard_rhythm": named.get("standard_rhythm"),
        "chief_complaint_concepts": named.get("chief_complaint_concepts") or [],
        "ed_chief_complaint_concepts": named.get("ed_chief_complaint_concepts") or [],
        "allergy_concepts": named.get("allergy_concepts") or [],
        "standard_diagnosis_name": named.get("standard_diagnosis_name"),
        "primary_icd_code": timed.get("primary_icd_code"),
        "primary_icd_version": timed.get("primary_icd_version"),
        "standard_service_name": named.get("standard_service_name"),
        "primary_service": timed.get("primary_service"),
        "discharge_location": timed.get("discharge_location"),
        "mapping_version": named.get("mapping_version"),
    }


def merge_visit(timed: dict[str, Any], named: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    hadm_id = _sid(timed.get("hadm_id"))
    named_hadm = _sid(named.get("hadm_id"))
    if not hadm_id or hadm_id != named_hadm:
        raise ValueError(f"hadm_id mismatch times={hadm_id!r} standardized={named_hadm!r}")
    subject_id = _sid(timed.get("subject_id"))
    admit_dt = parse_datetime(timed.get("admittime"))
    origin_dt, origin_text, origin_basis = presentation_origin(timed)
    facts = presentation_facts(timed, named)
    events: list[dict[str, Any]] = []

    labs = lab_name_index(named)
    rads = radiology_index(named)
    cardio = order_index(named, "cardiology")
    resp = order_index(named, "respiratory")
    meds = medication_index(named, "medications_normalized")
    recon = medication_index(named, "medrecon_normalized")
    procs = procedure_index(named)

    for kind, field, label, basis in (
        ("encounter_admit", "admittime", "Hospital admission", "admittime"),
        ("encounter_discharge", "dischtime", "Hospital discharge", "dischtime"),
        ("encounter_ed_in", "ed_intime", "ED arrival", "ed_intime"),
        ("encounter_ed_out", "ed_outtime", "ED departure", "ed_outtime"),
    ):
        event = _clock_event(
            subject_id=subject_id,
            hadm_id=hadm_id,
            event_kind=kind,
            domain="encounter",
            occurrence=timed.get(field),
            basis=basis,
            admit_dt=admit_dt,
            origin_dt=origin_dt,
            source_field=field,
            standard_name=label,
        )
        if event:
            events.append(event)

    investigations = timed.get("investigations") or {}
    for item in investigations.get("laboratory") or []:
        itemid = item.get("itemid")
        named_lab = labs.get(_sid(itemid))
        standard = _name_from(named_lab, "standard_test_name") or collapse_ws(item.get("label"))
        status = _mapped_status(named_lab, "mapped/exact" if standard else "unresolved")
        source_label = collapse_ws(item.get("label"))
        for row in item.get("results") or []:
            events.append(
                _finish(
                    subject_id=subject_id,
                    hadm_id=hadm_id,
                    event_kind="lab_resulted",
                    domain="lab",
                    fact_type="resulted",
                    occurrence=row.get("charttime"),
                    occurrence_basis="charttime",
                    available=row.get("storetime"),
                    available_basis="storetime",
                    admit_dt=admit_dt,
                    origin_dt=origin_dt,
                    precision="datetime",
                    standard_name=standard,
                    source_name=source_label,
                    mapping_status=status,
                    itemid=itemid,
                    source_field="investigations.laboratory",
                    valuenum=row.get("valuenum"),
                    flag=row.get("flag"),
                    business_key=[itemid, row.get("charttime"), row.get("value"), row.get("valuenum")],
                )
            )

    for item in investigations.get("radiology") or []:
        named_rad = take_radiology(rads, item.get("exam_name"), item.get("charttime"))
        events.append(
            _finish(
                subject_id=subject_id,
                hadm_id=hadm_id,
                event_kind="radiology_reported",
                domain="imaging",
                fact_type="reported",
                occurrence=item.get("charttime"),
                occurrence_basis="charttime",
                available=item.get("storetime"),
                available_basis="storetime",
                admit_dt=admit_dt,
                origin_dt=origin_dt,
                precision="datetime",
                standard_name=_name_from(named_rad, "standard_exam_name") or collapse_ws(item.get("exam_name")),
                source_name=collapse_ws(item.get("exam_name")),
                mapping_status=_mapped_status(named_rad, "unresolved"),
                source_field="investigations.radiology",
                business_key=[item.get("exam_name"), item.get("charttime")],
            )
        )

    for section, kind in (("cardiology", "cardiology_ordered"), ("respiratory", "respiratory_ordered")):
        buckets = cardio if section == "cardiology" else resp
        for item in investigations.get(section) or []:
            named_order = take_order(buckets, item.get("order_subtype"), item.get("ordertime"))
            events.append(
                _finish(
                    subject_id=subject_id,
                    hadm_id=hadm_id,
                    event_kind=kind,
                    domain=section,
                    fact_type="order",
                    occurrence=item.get("ordertime"),
                    occurrence_basis="ordertime",
                    available=item.get("ordertime"),
                    available_basis="ordertime",
                    admit_dt=admit_dt,
                    origin_dt=origin_dt,
                    precision="datetime",
                    standard_name=_name_from(named_order, "standard_order_name")
                    or collapse_ws(item.get("order_subtype")),
                    source_name=collapse_ws(item.get("order_subtype")),
                    mapping_status=_mapped_status(named_order, "unresolved"),
                    source_field=f"investigations.{section}",
                    business_key=[item.get("order_subtype"), item.get("ordertime")],
                )
            )

    for item in timed.get("poe_lab_imaging") or []:
        order_type = collapse_ws(item.get("order_type")) or ""
        subtype = collapse_ws(item.get("order_subtype"))
        category_only = lookup_key(order_type) in {"lab", "imaging"} and not subtype
        events.append(
            _finish(
                subject_id=subject_id,
                hadm_id=hadm_id,
                event_kind="poe_lab_imaging",
                domain="order",
                fact_type="order",
                occurrence=item.get("ordertime"),
                occurrence_basis="ordertime",
                available=item.get("ordertime"),
                available_basis="ordertime",
                admit_dt=admit_dt,
                origin_dt=origin_dt,
                precision="datetime",
                standard_name=subtype or order_type,
                source_name=order_type,
                mapping_status="not_applicable" if category_only else ("mapped/exact" if subtype else "unresolved"),
                source_field="poe_lab_imaging",
                category_only=category_only,
                business_key=[order_type, subtype, item.get("ordertime")],
            )
        )

    for item in timed.get("medications") or []:
        named_med = take_medication(meds, item)
        ingredients = named_med.get("standard_ingredients") if named_med else None
        if isinstance(ingredients, list) and ingredients:
            standard = "|".join(str(part) for part in ingredients)
            status = _mapped_status(named_med)
        else:
            standard = collapse_ws(item.get("drug"))
            status = _mapped_status(named_med, "unresolved")
        events.append(
            _finish(
                subject_id=subject_id,
                hadm_id=hadm_id,
                event_kind="medication_prescribed",
                domain="medication",
                fact_type="prescribed",
                occurrence=item.get("starttime"),
                occurrence_basis="starttime",
                available=item.get("starttime"),
                available_basis="starttime",
                admit_dt=admit_dt,
                origin_dt=origin_dt,
                precision="datetime",
                standard_name=standard,
                source_name=collapse_ws(item.get("drug")),
                mapping_status=status,
                source_field="medications",
                business_key=[item.get(key) for key in ("drug", "prod_strength", "route", "starttime")],
            )
        )

    for item in timed.get("procedures") or []:
        key = (_sid(item.get("icd_code")), _sid(item.get("icd_version")))
        named_proc = procs.get(key)
        events.append(
            _finish(
                subject_id=subject_id,
                hadm_id=hadm_id,
                event_kind="procedure_recorded",
                domain="procedure",
                fact_type="recorded",
                occurrence=item.get("chartdate"),
                occurrence_basis="chartdate",
                available=item.get("chartdate"),
                available_basis="chartdate",
                admit_dt=admit_dt,
                origin_dt=origin_dt,
                precision="date",
                standard_name=_name_from(named_proc, "standard_procedure_name")
                or collapse_ws(item.get("procedure_name")),
                source_name=collapse_ws(item.get("procedure_name")),
                mapping_status=_mapped_status(named_proc, "unresolved"),
                source_field="procedures",
                business_key=[item.get("icd_code"), item.get("icd_version"), item.get("chartdate")],
            )
        )

    for item in timed.get("medrecon") or []:
        named_med = take_medication(recon, {"drug": item.get("name"), **item})
        ingredients = named_med.get("standard_ingredients") if named_med else None
        standard = (
            "|".join(str(part) for part in ingredients)
            if isinstance(ingredients, list) and ingredients
            else collapse_ws(item.get("name"))
        )
        events.append(
            _finish(
                subject_id=subject_id,
                hadm_id=hadm_id,
                event_kind="medrecon",
                domain="medication",
                fact_type="recon",
                occurrence=item.get("charttime"),
                occurrence_basis="charttime",
                available=item.get("charttime"),
                available_basis="charttime",
                admit_dt=admit_dt,
                origin_dt=origin_dt,
                precision="datetime",
                standard_name=standard,
                source_name=collapse_ws(item.get("name")),
                mapping_status=_mapped_status(named_med, "unresolved"),
                source_field="medrecon",
                business_key=[item.get("name"), item.get("charttime")],
            )
        )

    for item in timed.get("transfers") or []:
        events.append(
            _finish(
                subject_id=subject_id,
                hadm_id=hadm_id,
                event_kind="transfer",
                domain="disposition",
                fact_type="transfer",
                occurrence=item.get("intime"),
                occurrence_basis="intime",
                available=item.get("intime"),
                available_basis="intime",
                admit_dt=admit_dt,
                origin_dt=origin_dt,
                precision="datetime",
                standard_name=collapse_ws(item.get("careunit")) or collapse_ws(item.get("eventtype")),
                source_name=collapse_ws(item.get("eventtype")),
                mapping_status="mapped/exact" if item.get("intime") else "unresolved",
                source_field="transfers",
                business_key=[item.get("eventtype"), item.get("careunit"), item.get("intime")],
            )
        )

    for item in timed.get("service_path") or []:
        events.append(
            _finish(
                subject_id=subject_id,
                hadm_id=hadm_id,
                event_kind="service_transfer",
                domain="disposition",
                fact_type="transfer",
                occurrence=item.get("transfertime"),
                occurrence_basis="transfertime",
                available=item.get("transfertime"),
                available_basis="transfertime",
                admit_dt=admit_dt,
                origin_dt=origin_dt,
                precision="datetime",
                standard_name=collapse_ws(item.get("curr_service")),
                source_name=collapse_ws(item.get("curr_service")),
                mapping_status="mapped/exact" if item.get("curr_service") else "unresolved",
                source_field="service_path",
                business_key=[item.get("prev_service"), item.get("curr_service"), item.get("transfertime")],
            )
        )

    if timed.get("rhythm") and timed.get("rhythm_charttime"):
        events.append(
            _finish(
                subject_id=subject_id,
                hadm_id=hadm_id,
                event_kind="rhythm_charted",
                domain="presentation",
                fact_type="vital",
                occurrence=timed.get("rhythm_charttime"),
                occurrence_basis="rhythm_charttime",
                available=timed.get("rhythm_charttime"),
                available_basis="rhythm_charttime",
                admit_dt=admit_dt,
                origin_dt=origin_dt,
                precision="datetime",
                standard_name=collapse_ws(named.get("standard_rhythm")) or collapse_ws(timed.get("rhythm")),
                source_name=collapse_ws(timed.get("rhythm")),
                mapping_status="mapped/exact" if named.get("standard_rhythm") else "unresolved",
                source_field="rhythm",
                business_key=[timed.get("rhythm"), timed.get("rhythm_charttime")],
            )
        )

    if origin_dt is not None and any(
        timed.get(key) is not None for key in ("temperature", "heartrate", "resprate", "o2sat", "sbp", "dbp", "acuity")
    ):
        events.append(
            _finish(
                subject_id=subject_id,
                hadm_id=hadm_id,
                event_kind="vitals_triage",
                domain="presentation",
                fact_type="vital",
                occurrence=origin_text,
                occurrence_basis=origin_basis,
                available=origin_text,
                available_basis=origin_basis,
                admit_dt=admit_dt,
                origin_dt=origin_dt,
                precision="bound",
                standard_name="Triage vitals",
                source_name=collapse_ws(timed.get("vitals_source")) or "vitals",
                mapping_status="mapped/exact",
                source_field="vitals",
                business_key=["vitals_triage", origin_basis],
            )
        )

    for field, concepts in (
        ("chief_complaint", named.get("chief_complaint_concepts") or []),
        ("ed_chief_complaint", named.get("ed_chief_complaint_concepts") or []),
    ):
        for concept in concepts:
            if not isinstance(concept, dict):
                continue
            events.append(
                _finish(
                    subject_id=subject_id,
                    hadm_id=hadm_id,
                    event_kind="complaint_bound",
                    domain="presentation",
                    fact_type="bound",
                    occurrence=origin_text,
                    occurrence_basis=origin_basis or "admittime",
                    available=origin_text,
                    available_basis=origin_basis or "admittime",
                    admit_dt=admit_dt,
                    origin_dt=origin_dt,
                    precision="bound",
                    standard_name=collapse_ws(concept.get("standard")),
                    source_name=collapse_ws(concept.get("source")),
                    mapping_status=str(concept.get("status") or "unresolved"),
                    source_field=field,
                    business_key=[field, concept.get("concept_id") or concept.get("standard")],
                )
            )

    events.sort(
        key=lambda row: (
            row.get("occurrence_time") or "",
            row.get("event_kind") or "",
            row.get("event_id") or "",
        )
    )
    header = {
        "subject_id": subject_id,
        "hadm_id": hadm_id,
        "admittime": collapse_ws(timed.get("admittime")),
        "dischtime": collapse_ws(timed.get("dischtime")),
        "deathtime": collapse_ws(timed.get("deathtime")),
        "presentation_origin": origin_text,
        "presentation_origin_basis": origin_basis,
        "event_count": len(events),
    }
    return header, events, facts
