"""JSON Schema locations and stable Arrow output schemas."""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa


SCHEMA_DIRECTORY = Path(__file__).resolve().parent / "schemas"
EVENT_JSON_SCHEMA_PATH = SCHEMA_DIRECTORY / "clinical-event.schema.json"

QUALITY_FLAG_CODES: tuple[str, ...] = (
    "AMBIGUOUS_MEDICATION_PAIRING",
    "AVAILABLE_BEFORE_EVENT_TIME",
    "AVAILABLE_TIME_DERIVED_FROM_COMPLETION",
    "AVAILABLE_TIME_UNKNOWN",
    "CATEGORY_ONLY_NO_SPECIFIC_ORDER_CONTENT",
    "CHANGE_WITHOUT_OBSERVABLE_DELTA",
    "MISSING_TRANSACTION_TYPE",
    "NONRECIPROCAL_PREDECESSOR_LINK",
    "NONRECIPROCAL_SUCCESSOR_LINK",
    "OFFICIAL_TRANSACTION_SEMANTICS_UNRESOLVED",
    "ORDER_TIME_UNRESOLVED",
    "PHARMACY_POE_ID_CONFLICT",
    "POE_ACTION_UNINTERPRETED",
    "POE_ID_FORMAT_MISMATCH",
    "PREDECESSOR_CATEGORY_MISMATCH",
    "PREDECESSOR_TIME_AFTER_CURRENT_EVENT",
    "RELATION_CYCLE",
    "SUCCESSOR_CATEGORY_MISMATCH",
    "SUCCESSOR_TIME_BEFORE_CURRENT_EVENT",
    "TIME_UNAVAILABLE_IN_SOURCE",
    "UNKNOWN_TRANSACTION_TYPE",
    "UNMAPPED_DETAIL_FIELD",
    "UNRESOLVED_PHARMACY_ID",
    "UNRESOLVED_PREDECESSOR",
    "UNRESOLVED_SUCCESSOR",
)

EVENT_ARROW_SCHEMA = pa.schema(
    [
        ("schema_version", pa.string()),
        ("cleaning_status", pa.string()),
        ("event_id", pa.string()),
        ("entity_id", pa.string()),
        ("source_row_id", pa.string()),
        ("subject_id", pa.string()),
        ("hadm_id", pa.string()),
        ("encounter_id", pa.string()),
        ("event_kind", pa.string()),
        ("lifecycle_action", pa.string()),
        ("status", pa.string()),
        ("assertion", pa.string()),
        ("event_time", pa.string()),
        ("available_time", pa.string()),
        ("recorded_time", pa.string()),
        ("time_resolution_status", pa.string()),
        ("time_precision", pa.string()),
        ("evidence_phase", pa.string()),
        ("source_concept_id", pa.string()),
        ("concept_id", pa.string()),
        ("preferred_name", pa.string()),
        ("source_label", pa.string()),
        ("entity_type", pa.string()),
        ("normalization_status", pa.string()),
        ("terminology_mapping_version", pa.string()),
        ("content_specificity", pa.string()),
        ("value_numeric", pa.float64()),
        ("value_text", pa.string()),
        ("value_structured_json", pa.string()),
        ("unit", pa.string()),
        ("abnormal_flag", pa.string()),
        ("normalized_value_numeric", pa.float64()),
        ("normalized_value_text", pa.string()),
        ("normalized_unit", pa.string()),
        ("unit_normalization_status", pa.string()),
        ("source_module", pa.string()),
        ("source_table", pa.string()),
        ("source_array_index", pa.int64()),
        ("jsonl_line_number", pa.int64()),
        ("raw_row_ref", pa.string()),
        ("source_action", pa.string()),
        ("quality_flags", pa.list_(pa.string())),
        ("supporting_source_row_ids", pa.list_(pa.string())),
        ("supporting_raw_row_refs", pa.list_(pa.string())),
    ],
    metadata={b"schema": b"clinical_event/1.1.0"},
)

ENCOUNTER_ARROW_SCHEMA = pa.schema(
    [
        ("schema_version", pa.string()),
        ("subject_id", pa.string()),
        ("hadm_id", pa.string()),
        ("jsonl_line_number", pa.int64()),
        ("source_row_count", pa.int64()),
        ("derived_row_count", pa.int64()),
        ("event_count", pa.int64()),
        ("rejected_count", pa.int64()),
    ],
    metadata={b"schema": b"encounter_manifest/1.0.0"},
)

REJECTED_ARROW_SCHEMA = pa.schema(
    [
        ("schema_version", pa.string()),
        ("cleaning_status", pa.string()),
        ("subject_id", pa.string()),
        ("hadm_id", pa.string()),
        ("source_row_id", pa.string()),
        ("raw_row_ref", pa.string()),
        ("source_table", pa.string()),
        ("reason_code", pa.string()),
        ("message", pa.string()),
    ],
    metadata={b"schema": b"rejected_event/1.1.0"},
)

REVIEW_ARROW_SCHEMA = pa.schema(
    [
        ("schema_version", pa.string()),
        ("entity_type", pa.string()),
        ("source_concept_id", pa.string()),
        ("normalized_source_label", pa.string()),
        ("source_label_example", pa.string()),
        ("unit", pa.string()),
        ("normalized_unit", pa.string()),
        ("unit_normalization_status", pa.string()),
        ("review_reason", pa.string()),
        ("event_count", pa.int64()),
        ("first_event_id", pa.string()),
        ("mapping_version", pa.string()),
    ],
    metadata={b"schema": b"normalization_review_queue/1.0.0"},
)

TERM_INVENTORY_ARROW_SCHEMA = pa.schema(
    [
        ("schema_version", pa.string()),
        ("entity_type", pa.string()),
        ("source_concept_id", pa.string()),
        ("normalized_source_label", pa.string()),
        ("source_label_example", pa.string()),
        ("unit", pa.string()),
        ("event_count", pa.int64()),
        ("first_event_id", pa.string()),
    ],
    metadata={b"schema": b"term_inventory/1.0.0"},
)

MAPPING_ARROW_SCHEMA = pa.schema(
    [
        ("schema_version", pa.string()),
        ("entity_type", pa.string()),
        ("source_concept_id", pa.string()),
        ("normalized_source_label", pa.string()),
        ("source_label_example", pa.string()),
        ("concept_id", pa.string()),
        ("preferred_name", pa.string()),
        ("normalization_status", pa.string()),
        ("source_unit", pa.string()),
        ("normalized_unit", pa.string()),
        ("unit_normalization_status", pa.string()),
        ("mapping_rule", pa.string()),
        ("mapping_version", pa.string()),
        ("event_count", pa.int64()),
    ],
    metadata={b"schema": b"normalization_mappings/1.0.0"},
)
