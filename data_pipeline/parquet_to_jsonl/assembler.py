"""Deep Module: assemble one frozen visit archive from source Adapter results."""

from __future__ import annotations

from typing import Any

from .partitioning import assign_subject_partition
from .schema import SCHEMA_NAME, SCHEMA_VERSION, validate_visit_archive
from .snapshots import build_decision_snapshots


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
    order_data: dict[str, list] | None = None,
    encounter_context: dict[str, dict] | None = None,
    longitudinal_data: dict[str, list] | None = None,
) -> dict[str, Any] | None:
    """Public Interface: one episode in, one validated archive record out."""
    ep_id = str(episode["episode_id"])
    context = (encounter_context or {}).get(ep_id, {})
    triage = triage_data.get(ep_id, {})
    parsed = (ds_note or {}).get("_parsed") or {"narrative": {}, "disposition": {}}
    ds_narrative = parsed.get("narrative", {})
    ds_disposition = parsed.get("disposition", {})

    triage_cc = triage.get("chief_complaint")
    retrospective_cc = ds_narrative.get("chief_complaint")
    if not _has_text(triage_cc) and not _has_text(retrospective_cc):
        return None

    diagnoses = dx_data.get(ep_id, {})
    if not diagnoses.get("primary"):
        return None

    orders = (order_data or {}).get(ep_id, [])
    laboratory = lab_data.get(ep_id, [])
    microbiology = micro_data.get(ep_id, [])
    radiology = rad_data.get(ep_id, [])
    medications = _clean_rx(rx_data.get(ep_id, []))
    pharmacy = _clean_pharm(pharm_data.get(ep_id, []))
    administrations = _clean_emar(emar_data.get(ep_id, []))
    procedures = _clean_proc(proc_data.get(ep_id, []))
    services = service_data.get(ep_id, [])

    record: dict[str, Any] = {
        "metadata": {
            "schema_name": SCHEMA_NAME,
            "schema_version": SCHEMA_VERSION,
            "source_versions": episode.get("source_versions"),
            "archive_semantics": "retrospective_episode_with_timed_evidence",
        },
        "identifiers": {
            "episode_id": ep_id,
            "subject_id": str(episode["subject_id"]),
            "hadm_id": str(episode["hadm_id"]) if episode.get("hadm_id") is not None else None,
        },
        "episode": {
            "episode_type": episode.get("episode_type", "hospital"),
            "episode_start_time": _text(episode.get("episode_start_time")),
            "ed_start_time": context.get("ed_start_time"),
            "ed_end_time": context.get("ed_end_time"),
            "clinical_end_time": _text(episode.get("clinical_end_time")),
            "administrative_end_time": _text(episode.get("administrative_end_time")),
            "outcome_type": episode.get("outcome_type"),
            "outcome_evidence_phase": "post_hoc",
        },
        "demographics": {
            "age_at_encounter": age,
            "sex": sex,
            "admission_type": episode.get("admission_type"),
            "baseline": _build_baseline(omr_data.get(ep_id, [])),
            "home_medications": medrecon_data.get(ep_id, []),
        },
        "presentation": {
            "triage_chief_complaint": {
                "text": triage_cc,
                "event_id": triage.get("event_id"),
                "event_time": triage.get("event_time"),
                "available_time": triage.get("available_time"),
                "recorded_time": triage.get("recorded_time"),
                "source": "ed_triage",
                "evidence_phase": "contemporaneous",
            },
            "arrival_transport": context.get("arrival_transport"),
            "discharge_summary_retrospective": {
                "note_id": (ds_note or {}).get("note_id"),
                "event_time": _text((ds_note or {}).get("event_time")),
                "available_time": _text((ds_note or {}).get("available_time")),
                "recorded_time": _text((ds_note or {}).get("recorded_time")),
                "chief_complaint": retrospective_cc,
                "history_of_present_illness": ds_narrative.get("history_of_present_illness"),
                "past_medical_history": ds_narrative.get("past_medical_history"),
                "social_history": ds_narrative.get("social_history"),
                "medications_on_admission": ds_narrative.get("medications_on_admission"),
                "allergies": ds_narrative.get("allergies"),
                "physical_exam": ds_narrative.get("physical_exam"),
                "full_text": (ds_note or {}).get("text"),
                "evidence_phase": "post_hoc",
            },
        },
        "vitals": {
            "initial": _build_initial_vitals(triage),
            "ed_series": (ed_vitals_data or {}).get(ep_id, []),
        },
        "orders": {"provider_orders": orders},
        "investigations": {
            "laboratory": laboratory,
            "microbiology": microbiology,
            "radiology": radiology,
            "cardiology": _specialty_evidence("cardiology", orders, radiology, procedures),
            "respiratory": _specialty_evidence("respiratory", orders, radiology, procedures),
        },
        "diagnoses": {
            "ed_diagnoses": ed_dx_data.get(ep_id, []),
            "coded_diagnoses": diagnoses.get("coded_diagnoses", []),
            "primary_coded_diagnosis": diagnoses.get("primary"),
        },
        "treatments": {
            "medications": medications,
            "pharmacy_orders": pharmacy,
            "medication_administrations": administrations,
            "procedures": procedures,
            "hcpcs": _clean_hcpcs(hcpcs_data.get(ep_id, [])),
        },
        "care_path": {
            "ed": {
                "start_time": context.get("ed_start_time"),
                "end_time": context.get("ed_end_time"),
                "disposition": context.get("ed_disposition"),
            },
            "transfers": transfer_data.get(ep_id, []),
            "icu_stays": icu_data.get(ep_id, []),
            "services": services,
        },
        "discharge": {
            "admission_location": episode.get("admission_location"),
            "discharge_location": episode.get("discharge_location"),
            "brief_hospital_course": ds_disposition.get("brief_hospital_course"),
            "discharge_medications": ds_disposition.get("discharge_medications"),
            "discharge_condition": ds_disposition.get("discharge_condition"),
            "discharge_instructions": ds_disposition.get("discharge_record"),
            "drg": _build_drg(drg_data.get(ep_id, [])),
            "evidence_phase": "post_hoc",
        },
        "longitudinal_refs": (longitudinal_data or {}).get(ep_id, []),
        "partition": assign_subject_partition(episode["subject_id"]),
        "decision_snapshots": [],
    }
    record["decision_snapshots"] = build_decision_snapshots(record)
    validate_visit_archive(record)
    return record


def _build_initial_vitals(triage: dict[str, Any]) -> dict[str, Any]:
    result = {
        "source": "triage" if triage else None,
        "event_id": triage.get("event_id"),
        "event_time": triage.get("event_time"),
        "available_time": triage.get("available_time"),
        "recorded_time": triage.get("recorded_time"),
        "temperature": None, "heartrate": None, "resprate": None,
        "o2sat": None, "sbp": None, "dbp": None, "acuity": None,
        "pain": None, "rhythm": None,
    }
    for key in ("temperature", "heartrate", "resprate", "o2sat", "sbp", "dbp", "acuity", "pain", "rhythm"):
        result[key] = triage.get(key)
    return result


def _build_baseline(items: list[dict]) -> dict[str, list]:
    baseline = {"blood_pressure": [], "weight_lbs": [], "bmi": [], "height_inches": [], "egfr": []}
    for item in items:
        name = str(item.get("_concept_name") or item.get("result_name") or "").lower()
        entry = {
            "event_time": item.get("event_time") or item.get("_event_time"),
            "available_time": item.get("available_time") or item.get("_event_time"),
            "recorded_time": item.get("recorded_time") or item.get("_event_time"),
            "value": item.get("raw_value") or item.get("result_value") or item.get("_value"),
        }
        if "blood pressure" in name:
            baseline["blood_pressure"].append(entry)
        elif "weight" in name:
            baseline["weight_lbs"].append(entry)
        elif "bmi" in name:
            baseline["bmi"].append(entry)
        elif "height" in name:
            baseline["height_inches"].append(entry)
        elif "egfr" in name:
            baseline["egfr"].append(entry)
    return {key: values[-3:] for key, values in baseline.items()}


def _specialty_evidence(kind: str, orders: list[dict], radiology: list[dict], procedures: list[dict]) -> list[dict]:
    terms = {
        "cardiology": ("ecg", "ekg", "electrocard", "echo", "cardiac", "coronary", "troponin"),
        "respiratory": ("pulmonary", "respir", "spirom", "chest", "oxygen", "ventilat"),
    }[kind]
    evidence = []
    for source_name, values in (("provider_order", orders), ("radiology", radiology), ("procedure", procedures)):
        for item in values:
            searchable = " ".join(str(value) for value in item.values() if value is not None).lower()
            if any(term in searchable for term in terms):
                evidence.append({"source": source_name, "source_event_id": item.get("event_id") or item.get("note_id"), **item})
    return evidence


def _clean_rx(items: list[dict]) -> list[dict]:
    return [_copy_timed(item, ("drug", "prod_strength", "form_rx", "dose_val_rx", "dose_unit_rx", "route", "doses_per_24_hrs", "starttime")) for item in items]


def _clean_pharm(items: list[dict]) -> list[dict]:
    return [_copy_timed(item, ("medication", "starttime", "stoptime", "route", "frequency", "status", "doses_per_24_hrs")) for item in items]


def _clean_emar(items: list[dict]) -> list[dict]:
    return [_copy_timed(item, ("medication", "charttime", "event_txt", "scheduletime", "details")) for item in items]


def _clean_proc(items: list[dict]) -> list[dict]:
    return [_copy_timed(item, ("icd_code", "icd_version", "_concept_name"), {"procedure_name": item.get("_concept_name")}) for item in items]


def _clean_hcpcs(items: list[dict]) -> list[dict]:
    return [_copy_timed(item, ("hcpcs_cd", "short_description", "chartdate")) for item in items]


def _copy_timed(item: dict, fields: tuple[str, ...], extra: dict | None = None) -> dict:
    result = {key: item.get(key) for key in ("event_id", "event_time", "available_time", "recorded_time")}
    result.update({field: item.get(field) for field in fields})
    if extra:
        result.update(extra)
    return result


def _build_drg(items: list[dict]) -> dict | None:
    if not items:
        return None
    item = items[0]
    return {
        "drg_type": item.get("_event_subtype"),
        "drg_code": item.get("drg_code"),
        "description": item.get("description"),
        "drg_severity": item.get("drg_severity"),
        "drg_mortality": item.get("drg_mortality"),
        "evidence_phase": "post_hoc",
    }


def _text(value: Any) -> str | None:
    return str(value) if value is not None else None


def _has_text(value: Any) -> bool:
    return bool(value and str(value).strip())
