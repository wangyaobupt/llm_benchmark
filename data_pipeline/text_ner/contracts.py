"""Frozen contracts for the model-free text NER input manifest."""

from __future__ import annotations

import pyarrow as pa


MANIFEST_SCHEMA_VERSION = "text-ner-input-manifest/1.0.0"
MANIFEST_LOGIC_VERSION = "text-ner-input-preparation/1.0.0"

MANIFEST_ARROW_SCHEMA = pa.schema(
    [
        ("schema_version", pa.string()),
        ("manifest_row_id", pa.string()),
        ("document_id", pa.string()),
        ("section_id", pa.string()),
        ("subject_id", pa.string()),
        ("hadm_id", pa.string()),
        ("split_group_id", pa.string()),
        ("source_module", pa.string()),
        ("source_table", pa.string()),
        ("source_row_id", pa.string()),
        ("source_array_index", pa.int64()),
        ("jsonl_line_number", pa.int64()),
        ("raw_row_ref", pa.string()),
        ("text_field", pa.string()),
        ("note_id", pa.string()),
        ("note_type", pa.string()),
        ("parent_note_id", pa.string()),
        ("addendum_note_ids", pa.list_(pa.string())),
        ("event_time", pa.string()),
        ("source_available_time", pa.string()),
        ("available_time", pa.string()),
        ("recorded_time", pa.string()),
        ("time_resolution_status", pa.string()),
        ("time_policy_id", pa.string()),
        ("time_resolution_reasons", pa.list_(pa.string())),
        ("evidence_phase", pa.string()),
        ("quality_flags", pa.list_(pa.string())),
        ("section_name", pa.string()),
        ("section_ordinal", pa.int64()),
        ("span_start", pa.int64()),
        ("span_end", pa.int64()),
        ("source_text_character_count", pa.int64()),
        ("span_character_count", pa.int64()),
        ("source_text_sha256", pa.string()),
        ("span_sha256", pa.string()),
        ("inclusion_status", pa.string()),
        ("reason_code", pa.string()),
        ("pilot_document_selected", pa.bool_()),
        ("pilot_selection_rank", pa.int64()),
        ("pilot_stratum", pa.string()),
    ],
    metadata={b"schema": MANIFEST_SCHEMA_VERSION.encode("ascii")},
)

RAW_TEXT_COLUMNS = frozenset(
    {"text", "content", "section_text", "surface_text", "chiefcomplaint"}
)
