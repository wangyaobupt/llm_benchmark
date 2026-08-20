"""Original extract columns plus derived standardization columns."""

from __future__ import annotations

from data_pipeline.mcq_visit_extract.columns import (
    FORBIDDEN_DELIVERABLE_KEYS,
    NESTED_COLUMNS as EXTRACT_NESTED,
    RESULT_COLUMNS,
)

MAPPING_VERSION = "mcq-visit-standardize/1.0.8"
SCHEMA_NAME = "mcq_visit_standardized"
SCHEMA_VERSION = "1.0.0"

DERIVED_COLUMNS: tuple[str, ...] = (
    "chief_complaint_concepts",
    "ed_chief_complaint_concepts",
    "allergy_concepts",
    "standard_rhythm",
    "temperature_f",
    "temperature_c",
    "vitals_units",
    "investigations_normalized",
    "medications_normalized",
    "medrecon_normalized",
    "procedures_normalized",
    "standard_diagnosis_name",
    "other_diagnoses_normalized",
    "ed_diagnoses_normalized",
    "standard_service_name",
    "poe_lab_imaging_normalized",
    "mapping_version",
)

OUTPUT_COLUMNS: tuple[str, ...] = RESULT_COLUMNS + DERIVED_COLUMNS

NESTED_COLUMNS: frozenset[str] = EXTRACT_NESTED | frozenset(DERIVED_COLUMNS)

STATUS_VALUES: frozenset[str] = frozenset(
    {"mapped/exact", "mapped/converted", "unresolved", "not_applicable"}
)
