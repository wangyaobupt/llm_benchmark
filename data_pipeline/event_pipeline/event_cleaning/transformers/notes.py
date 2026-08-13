"""Radiology and discharge document-metadata event transformers."""

from __future__ import annotations

from typing import Any

from ..models import AdmissionContext, SourceRow
from ..time_resolver import resolved_times
from .common import _clean, _event

def transform_radiology_note(source: SourceRow, context: AdmissionContext) -> list[dict[str, Any]]:
    row = source.row
    note_id = _clean(row.get("note_id"))
    details = list(context.indexes["radiology_details_by_note_id"].get(note_id, []))
    label = _clean(row.get("note_type")) or "Radiology report"
    return [
        _event(
            source,
            "report",
            "imaging_reported",
            times=resolved_times(
                event_time=row.get("charttime"),
                available_time=row.get("storetime"),
                recorded_time=row.get("storetime"),
            ),
            entity_type="imaging_report",
            source_label=label,
            value_structured={
                "note_id": note_id,
                "note_seq": row.get("note_seq"),
                "details": [detail.row for detail in details],
            },
            supporting_rows=details,
        )
    ]
def transform_discharge_note(source: SourceRow, context: AdmissionContext) -> list[dict[str, Any]]:
    row = source.row
    note_id = _clean(row.get("note_id"))
    details = list(context.indexes["discharge_details_by_note_id"].get(note_id, []))
    return [
        _event(
            source,
            "document",
            "document_recorded",
            times=resolved_times(
                event_time=row.get("charttime"),
                available_time=row.get("storetime"),
                recorded_time=row.get("storetime"),
            ),
            evidence_phase="post_hoc",
            entity_type="clinical_document",
            source_label="Discharge summary",
            concept_id="document:discharge_summary",
            preferred_name="Discharge summary",
            value_structured={
                "note_id": note_id,
                "note_seq": row.get("note_seq"),
                "details": [detail.row for detail in details],
            },
            supporting_rows=details,
        )
    ]
