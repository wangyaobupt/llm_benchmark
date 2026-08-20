"""Frozen deliverable columns: results only, no lineage."""

from __future__ import annotations

RESULT_COLUMNS: tuple[str, ...] = (
    "subject_id",
    "hadm_id",
    "admittime",
    "dischtime",
    "deathtime",
    "age_at_encounter",
    "sex",
    "admission_type",
    "vitals_source",
    "temperature",
    "heartrate",
    "resprate",
    "o2sat",
    "sbp",
    "dbp",
    "acuity",
    "rhythm",
    "rhythm_charttime",
    "chief_complaint",
    "history_of_present_illness",
    "past_medical_history",
    "social_history",
    "medications_on_admission",
    "allergies",
    "physical_exam",
    "investigations",
    "primary_icd_code",
    "primary_diagnosis_name",
    "primary_icd_version",
    "other_diagnoses",
    "medications",
    "procedures",
    "primary_service",
    "admission_location",
    "discharge_location",
    "ed_disposition",
    "ed_intime",
    "ed_outtime",
    "edregtime",
    "edouttime",
    "brief_hospital_course",
    "discharge_medications",
    "discharge_condition",
    "discharge_record",
    "discharge_note_full",
    "discharge_diagnosis",
    "ed_chief_complaint",
    "ed_pain",
    "ed_diagnoses",
    "medrecon",
    "transfers",
    "service_path",
    "poe_lab_imaging",
)

NESTED_COLUMNS: frozenset[str] = frozenset(
    {
        "investigations",
        "other_diagnoses",
        "medications",
        "procedures",
        "ed_diagnoses",
        "medrecon",
        "transfers",
        "service_path",
        "poe_lab_imaging",
    }
)

REQUIRED_RESULT_COLUMNS: tuple[str, ...] = (
    "subject_id",
    "hadm_id",
    "age_at_encounter",
    "sex",
    "admission_type",
    "chief_complaint",
    "primary_icd_code",
    "primary_diagnosis_name",
    "primary_icd_version",
    "discharge_note_full",
)

FORBIDDEN_DELIVERABLE_KEYS: frozenset[str] = frozenset(
    {
        "schema",
        "lineage",
        "audit",
        "selection_rank",
        "subject_bucket",
        "sample_pool",
        "ds_note_id",
        "ds_note_seq",
        "ds_charttime",
        "ds_storetime",
        "followup_instructions_text",
        "followup_instructions_unusable",
        "source_table",
        "raw_record",
    }
)

EMPTY_INVESTIGATIONS: dict[str, list[object]] = {
    "laboratory": [],
    "radiology": [],
    "cardiology": [],
    "respiratory": [],
}

SCHEMA_NAME = "mcq_visit_extract"
SCHEMA_VERSION = "3.1.2"

MEDICATION_CORE_KEYS: tuple[str, ...] = (
    "drug",
    "prod_strength",
    "form_rx",
    "dose_val_rx",
    "dose_unit_rx",
    "route",
    "doses_per_24_hrs",
)
MEDICATION_ITEM_KEYS: tuple[str, ...] = MEDICATION_CORE_KEYS + (
    "starttime",
    "stoptime",
)
PROCEDURE_CORE_KEYS: tuple[str, ...] = (
    "procedure_name",
    "icd_code",
    "icd_version",
)
PROCEDURE_ITEM_KEYS: tuple[str, ...] = PROCEDURE_CORE_KEYS + ("chartdate",)
MEDRECON_CORE_KEYS: tuple[str, ...] = (
    "name",
    "gsn",
    "ndc",
    "etcdescription",
)
MEDRECON_ITEM_KEYS: tuple[str, ...] = MEDRECON_CORE_KEYS + ("charttime",)
LAB_RESULT_CORE_KEYS: tuple[str, ...] = (
    "charttime",
    "value",
    "valuenum",
    "valueuom",
    "ref_range_lower",
    "ref_range_upper",
    "flag",
    "comments",
)
RADIOLOGY_CORE_KEYS: tuple[str, ...] = ("exam_name", "charttime")
