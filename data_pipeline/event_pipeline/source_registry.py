"""Frozen first-stage source registry and transformer routing."""

from __future__ import annotations

from .models import SourceSpec


def _event(module: str, table: str, keys: str, transformer: str) -> SourceSpec:
    return SourceSpec(module, table, "event", tuple(keys.split()), transformer)


SOURCE_REGISTRY: tuple[SourceSpec, ...] = (
    _event("mimic_iv_ed", "triage", "subject_id stay_id", "transform_ed_triage"),
    _event("mimic_iv_ed", "vitalsign", "subject_id stay_id charttime", "transform_ed_vitals"),
    _event("mimic_iv_hosp", "labevents", "labevent_id", "transform_labevent"),
    _event("mimic_iv_hosp", "microbiologyevents", "microevent_id", "transform_microbiology"),
    _event("mimic_iv_hosp", "poe_timeline", "subject_id poe_id poe_seq", "transform_poe_timeline"),
    _event("mimic_iv_hosp", "prescriptions", "", "transform_prescription"),
    _event("mimic_iv_hosp", "pharmacy", "pharmacy_id", "transform_pharmacy"),
    _event("mimic_iv_hosp", "emar", "subject_id emar_id emar_seq", "transform_emar"),
    _event("mimic_iv_hosp", "services", "subject_id hadm_id transfertime curr_service", "transform_service"),
    _event("mimic_iv_hosp", "transfers", "transfer_id", "transform_transfer"),
    _event("mimic_iv_hosp", "procedures_icd", "subject_id hadm_id seq_num", "transform_procedure_icd"),
    _event("mimic_iv_icu", "procedureevents", "subject_id stay_id orderid itemid starttime", "transform_icu_procedure"),
    _event("mimic_iv_note", "radiology", "subject_id note_id", "transform_radiology_note"),
    _event("mimic_iv_note", "discharge", "subject_id note_id", "transform_discharge_note"),
)

SOURCE_BY_PATH = {(spec.module, spec.table): spec for spec in SOURCE_REGISTRY}
