"""Phase 4: Assemble JSON visit objects from aggregated data."""

from __future__ import annotations
import json
import logging
from typing import Any

from .ds_parser import parse_ds, select_ds

logger = logging.getLogger(__name__)


def assemble_visit(
    episode: dict[str, Any],
    patients: dict[int, dict],
    age: int,
    sex: str,
    ds_note: dict[str, Any] | None,
    lab_data: dict[str, list],
    dx_data: dict[str, dict],
    micro_data: dict[str, list],
    rad_data: dict[str, list],
    rx_data: dict[str, list],
    pharm_data: dict[str, list],
    emar_data: dict[str, list],
    proc_data: dict[str, list],
    ed_dx_data: dict[str, list],
    transfer_data: dict[str, list],
    icu_data: dict[str, list],
    drg_data: dict[str, list],
    triage_data: dict[str, dict],
    service_data: dict[str, list],
    medrecon_data: dict[str, list],
    omr_data: dict[str, list],
    hcpcs_data: dict[str, list],
    ed_vitals_data: dict[str, list] | None = None,
) -> dict[str, Any] | None:
    """Assemble a complete visit JSON object.

    Returns None if the visit fails validation (missing primary dx, CC, etc).
    """
    ep_id = str(episode["episode_id"])

    # Parse DS chapters
    ds_parsed = {"narrative": {}, "disposition": {}}
    ds_full_text = None
    if ds_note:
        ds_full_text = ds_note.get("text")
        if "_parsed" in ds_note:
            ds_parsed = ds_note["_parsed"]
        else:
            from .ds_parser import parse_ds
            if ds_full_text:
                ds_parsed = parse_ds(ds_full_text)

    # Check required: chief_complaint must be non-empty
    chief_complaint = ds_parsed.get("narrative", {}).get("chief_complaint")
    if not chief_complaint or not chief_complaint.strip():
        return None

    # Check required: primary diagnosis
    dx = dx_data.get(ep_id, {})
    primary_dx = dx.get("primary")
    if not primary_dx or not primary_dx.get("icd_code"):
        return None

    # Build identifiers
    visit = {
        "identifiers": {
            "subject_id": str(episode["subject_id"]),
            "hadm_id": str(episode["hadm_id"]),
        },
        "demographics": {
            "age_at_encounter": age,
            "sex": sex,
            "admission_type": episode.get("admission_type"),
            "baseline": _build_baseline(omr_data.get(ep_id, [])),
            "home_medications": medrecon_data.get(ep_id, []),
        },
        "vitals": _build_vitals(triage_data.get(ep_id, {}), ed_vitals_data or {}, ep_id),
        "narrative": _build_narrative(ds_parsed, ds_full_text),
        "investigations": {
            "laboratory": lab_data.get(ep_id, []),
            "microbiology": micro_data.get(ep_id, []),
            "radiology": rad_data.get(ep_id, []),
            "cardiology": [],
            "respiratory": [],
        },
        "diagnoses": {
            "primary": primary_dx,
            "other": dx.get("other", []),
            "ed_diagnoses": ed_dx_data.get(ep_id, []),
        },
        "treatments": {
            "medications": _clean_rx(rx_data.get(ep_id, [])),
            "pharmacy_orders": _clean_pharm(pharm_data.get(ep_id, [])),
            "medication_administrations": _clean_emar(emar_data.get(ep_id, [])),
            "procedures": _clean_proc(proc_data.get(ep_id, [])),
            "hcpcs": _clean_hcpcs(hcpcs_data.get(ep_id, [])),
        },
        "disposition": _build_disposition(
            episode, ds_parsed,
            transfer_data.get(ep_id, []),
            icu_data.get(ep_id, []),
            drg_data.get(ep_id, []),
            service_data.get(ep_id, []),
        ),
    }

    return visit


def _build_baseline(omr_items: list[dict]) -> dict[str, list]:
    """Build baseline from omr events."""
    baseline: dict[str, list] = {}
    for item in omr_items:
        rn = item.get("_concept_name") or ""
        val = item.get("raw_value") or item.get("_value")
        ct = item.get("_event_time", "")
        entry = {"chartdate": ct[:10] if ct else None, "value": val}

        rn_lower = rn.lower()
        if "blood pressure" in rn_lower:
            baseline.setdefault("blood_pressure", []).append(entry)
        elif "weight" in rn_lower:
            baseline.setdefault("weight_lbs", []).append(entry)
        elif "bmi" in rn_lower:
            baseline.setdefault("bmi", []).append(entry)
        elif "height" in rn_lower:
            baseline.setdefault("height_inches", []).append(entry)
        elif "egfr" in rn_lower:
            baseline.setdefault("egfr", []).append(entry)

    # Keep last 3 per group
    for k in baseline:
        baseline[k] = baseline[k][-3:]

    return baseline


def _build_vitals(triage: dict, ed_vitals_data: dict[str, list], ep_id: str) -> dict[str, Any]:
    """Build vitals from triage data, supplement rhythm from ED vital signs."""
    vitals = {
        "source": None,
        "temperature": None,
        "heartrate": None,
        "resprate": None,
        "o2sat": None,
        "sbp": None,
        "dbp": None,
        "acuity": None,
        "rhythm": None,
    }
    for k in ("temperature", "heartrate", "resprate", "o2sat", "sbp", "dbp", "acuity", "pain"):
        if k in triage:
            vitals[k] = triage[k]

    # Set source if any vital present
    has_any = any(vitals[k] is not None for k in ("temperature", "heartrate", "resprate", "o2sat", "sbp", "dbp", "acuity"))
    vitals["source"] = "triage" if has_any else None

    # Supplement rhythm from ED vital signs if triage has none
    if vitals["rhythm"] is None and ep_id in ed_vitals_data:
        for vs in ed_vitals_data[ep_id]:
            rhythm = vs.get("rhythm")
            if rhythm:
                vitals["rhythm"] = rhythm
                break

    return vitals


def _build_narrative(ds_parsed: dict, ds_full: str | None) -> dict[str, Any]:
    """Build narrative section from parsed DS."""
    narr = ds_parsed.get("narrative", {})
    return {
        "chief_complaint": narr.get("chief_complaint"),
        "history_of_present_illness": narr.get("history_of_present_illness"),
        "past_medical_history": narr.get("past_medical_history"),
        "social_history": narr.get("social_history"),
        "medications_on_admission": narr.get("medications_on_admission"),
        "allergies": narr.get("allergies"),
        "physical_exam": narr.get("physical_exam"),
        "discharge_note_full": ds_full,
    }


def _build_disposition(
    episode: dict,
    ds_parsed: dict,
    transfers: list,
    icu_stays: list,
    drg_list: list,
    services: list,
) -> dict[str, Any]:
    """Build disposition section."""
    disp = ds_parsed.get("disposition", {})

    # Primary service: last service_transfer
    primary_service = None
    if services:
        last = services[-1]
        primary_service = last.get("_event_subtype")

    # DRG: take first
    drg = None
    if drg_list:
        d = drg_list[0]
        drg = {
            "drg_type": d.get("_event_subtype"),
            "drg_code": d.get("drg_code"),
            "description": d.get("description"),
            "drg_severity": d.get("drg_severity"),
            "drg_mortality": d.get("drg_mortality"),
        }

    return {
        "primary_service": primary_service,
        "admission_location": episode.get("admission_location"),
        "discharge_location": episode.get("discharge_location"),
        "ed_disposition": None,
        "brief_hospital_course": disp.get("brief_hospital_course"),
        "discharge_medications": disp.get("discharge_medications"),
        "discharge_condition": disp.get("discharge_condition"),
        "discharge_record": disp.get("discharge_record"),
        "transfer_path": transfers,
        "icu_stays": icu_stays,
        "drg": drg,
    }


def _clean_rx(items: list[dict]) -> list[dict]:
    """Clean prescription items."""
    result = []
    for item in items:
        result.append({
            "drug": item.get("drug"),
            "prod_strength": item.get("prod_strength"),
            "form_rx": item.get("form_rx"),
            "dose_val_rx": item.get("dose_val_rx"),
            "dose_unit_rx": item.get("dose_unit_rx"),
            "route": item.get("route"),
            "doses_per_24_hrs": _safe_int(item.get("doses_per_24_hrs")),
            "starttime": item.get("starttime"),
        })
    return result


def _clean_pharm(items: list[dict]) -> list[dict]:
    """Clean pharmacy items."""
    result = []
    for item in items:
        result.append({
            "medication": item.get("medication"),
            "starttime": item.get("starttime"),
            "stoptime": item.get("stoptime"),
            "route": item.get("route"),
            "frequency": item.get("frequency"),
            "status": item.get("status"),
            "doses_per_24_hrs": _safe_int(item.get("doses_per_24_hrs")),
        })
    return result


def _clean_emar(items: list[dict]) -> list[dict]:
    """Clean emar items."""
    result = []
    for item in items:
        result.append({
            "medication": item.get("medication"),
            "charttime": item.get("charttime") or item.get("_event_time"),
            "event_txt": item.get("event_txt"),
            "scheduletime": item.get("scheduletime"),
            "detail": None,
        })
    return result


def _clean_proc(items: list[dict]) -> list[dict]:
    """Clean procedure items."""
    result = []
    for item in items:
        result.append({
            "procedure_name": item.get("_concept_name"),
            "icd_code": item.get("icd_code"),
            "icd_version": item.get("icd_version"),
        })
    return result


def _clean_hcpcs(items: list[dict]) -> list[dict]:
    """Clean hcpcs items."""
    result = []
    for item in items:
        result.append({
            "hcpcs_cd": item.get("hcpcs_cd"),
            "short_description": item.get("short_description") or item.get("_concept_name"),
            "chartdate": item.get("chartdate") or item.get("_event_time"),
        })
    return result


def _safe_int(v) -> int | None:
    try:
        if v is None or v == "":
            return None
        return int(float(v))
    except (ValueError, TypeError):
        return None
