"""Frozen contracts for candidate mentions and explicit text relations."""

from __future__ import annotations

import pyarrow as pa


SECTION_ANNOTATION_SCHEMA_VERSION = "section-annotation/1.0.0"
ENTITY_MENTION_SCHEMA_VERSION = "entity-mention/1.0.0"
TEXT_RELATION_SCHEMA_VERSION = "text-relation/1.0.0"
ANNOTATION_ALLOCATION_SCHEMA_VERSION = "annotation-allocation/1.0.0"
ANNOTATION_DECISION_SCHEMA_VERSION = "annotation-review-decision/1.0.0"
ANNOTATION_PROTOCOL_VERSION = "text-ner-annotation-protocol/1.1.0"

ENTITY_TYPES = (
    "symptom_or_sign",
    "clinical_problem",
    "imaging_finding",
    "anatomical_site",
    "procedure_or_test",
    "device",
    "medication_or_substance",
    "measurement",
    "temporal_expression",
)

ASSERTION_VALUES = ("present", "absent", "possible", "unknown")
TEMPORALITY_VALUES = (
    "current",
    "historical",
    "future_planned",
    "unclear",
)
EXPERIENCER_VALUES = ("patient", "family_member", "other", "unknown")
LATERALITY_VALUES = (
    "left",
    "right",
    "bilateral",
    "midline",
    "not_stated",
    "not_applicable",
)
SEVERITY_VALUES = (
    "mild",
    "moderate",
    "severe",
    "not_stated",
    "not_applicable",
)
TREND_VALUES = (
    "new",
    "increased",
    "decreased",
    "stable",
    "resolved",
    "not_stated",
    "not_applicable",
)
RELATION_TYPES = (
    "located_at",
    "has_measurement",
    "has_temporal_context",
    "compared_with",
    "suggestive_of",
    "device_positioned_at",
    "recommendation_for",
)
ANNOTATION_QUALITY_FLAGS = (
    "SPAN_AMBIGUOUS",
    "ENTITY_TYPE_AMBIGUOUS",
    "ASSERTION_AMBIGUOUS",
    "TEMPORALITY_AMBIGUOUS",
    "EXPERIENCER_AMBIGUOUS",
    "RELATION_AMBIGUOUS",
    "ABBREVIATION_UNRESOLVED",
    "COREFERENCE_UNRESOLVED",
)

ANNOTATION_ALLOCATION_ARROW_SCHEMA = pa.schema(
    [
        ("schema_version", pa.string()),
        ("allocation_id", pa.string()),
        ("document_id", pa.string()),
        ("subject_id", pa.string()),
        ("hadm_id", pa.string()),
        ("split_group_id", pa.string()),
        ("source_table", pa.string()),
        ("note_type", pa.string()),
        ("pilot_stratum", pa.string()),
        ("text_unit_count", pa.int64()),
        ("partition", pa.string()),
        ("partition_status", pa.string()),
        ("allocation_reason", pa.string()),
        ("allocation_rank", pa.int64()),
        ("input_manifest_sha256", pa.string()),
        ("annotation_protocol_version", pa.string()),
    ],
    metadata={b"schema": ANNOTATION_ALLOCATION_SCHEMA_VERSION.encode("ascii")},
)

ENTITY_MENTION_ARROW_SCHEMA = pa.schema(
    [
        ("schema_version", pa.string()),
        ("mention_id", pa.string()),
        ("manifest_row_id", pa.string()),
        ("document_id", pa.string()),
        ("section_id", pa.string()),
        ("subject_id", pa.string()),
        ("hadm_id", pa.string()),
        ("source_row_id", pa.string()),
        ("raw_row_ref", pa.string()),
        ("source_table", pa.string()),
        ("section_name", pa.string()),
        ("surface_text", pa.string()),
        ("section_span_start", pa.int64()),
        ("section_span_end", pa.int64()),
        ("document_span_start", pa.int64()),
        ("document_span_end", pa.int64()),
        ("entity_type", pa.string()),
        ("assertion", pa.string()),
        ("temporality", pa.string()),
        ("experiencer", pa.string()),
        ("laterality", pa.string()),
        ("severity", pa.string()),
        ("trend", pa.string()),
        ("normalization_status", pa.string()),
        ("concept_id", pa.string()),
        ("preferred_name", pa.string()),
        ("terminology", pa.string()),
        ("event_time", pa.string()),
        ("available_time", pa.string()),
        ("evidence_phase", pa.string()),
        ("extraction_method", pa.string()),
        ("extractor_name", pa.string()),
        ("extractor_version", pa.string()),
        ("input_sha256", pa.string()),
        ("prompt_sha256", pa.string()),
        ("review_status", pa.string()),
        ("quality_flags", pa.list_(pa.string())),
    ],
    metadata={b"schema": ENTITY_MENTION_SCHEMA_VERSION.encode("ascii")},
)

TEXT_RELATION_ARROW_SCHEMA = pa.schema(
    [
        ("schema_version", pa.string()),
        ("relation_id", pa.string()),
        ("manifest_row_id", pa.string()),
        ("document_id", pa.string()),
        ("section_id", pa.string()),
        ("subject_id", pa.string()),
        ("hadm_id", pa.string()),
        ("source_mention_id", pa.string()),
        ("target_mention_id", pa.string()),
        ("relation_type", pa.string()),
        ("evidence_text", pa.string()),
        ("section_evidence_start", pa.int64()),
        ("section_evidence_end", pa.int64()),
        ("document_evidence_start", pa.int64()),
        ("document_evidence_end", pa.int64()),
        ("relation_basis", pa.string()),
        ("extraction_method", pa.string()),
        ("extractor_name", pa.string()),
        ("extractor_version", pa.string()),
        ("input_sha256", pa.string()),
        ("prompt_sha256", pa.string()),
        ("review_status", pa.string()),
        ("quality_flags", pa.list_(pa.string())),
    ],
    metadata={b"schema": TEXT_RELATION_SCHEMA_VERSION.encode("ascii")},
)
