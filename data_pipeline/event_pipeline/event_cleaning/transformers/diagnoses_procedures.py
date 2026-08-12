"""Services, transfers, diagnoses, and coded-procedure transformers."""

from __future__ import annotations

from typing import Any

from ..models import AdmissionContext, SourceRow
from ..time_resolver import resolved_times
from .common import KnownTransformationError, _clean, _decoded_label, _event

def transform_service(source: SourceRow, context: AdmissionContext) -> list[dict[str, Any]]:
    del context
    row = source.row
    current = _clean(row.get("curr_service"))
    return [
        _event(
            source,
            "service",
            "service_changed",
            times=resolved_times(
                event_time=row.get("transfertime"), available_time=row.get("transfertime")
            ),
            entity_type="clinical_service",
            source_label=current,
            preferred_name=current,
            value_structured={"previous_service": row.get("prev_service")},
        )
    ]


def transform_transfer(source: SourceRow, context: AdmissionContext) -> list[dict[str, Any]]:
    del context
    row = source.row
    careunit = _clean(row.get("careunit"))
    return [
        _event(
            source,
            "transfer",
            "patient_transferred",
            times=resolved_times(event_time=row.get("intime")),
            status=_clean(row.get("eventtype")),
            entity_type="care_unit" if careunit else None,
            source_label=careunit,
            preferred_name=careunit,
            value_structured={"outtime": _clean(row.get("outtime"))},
            quality_flags=["AVAILABLE_TIME_UNKNOWN"],
        )
    ]


def _coded_event(
    source: SourceRow,
    *,
    component: str,
    event_kind: str,
    code_system: str,
    code: Any,
    label: str | None,
    event_time: Any = None,
    evidence_phase: str = "post_hoc",
) -> list[dict[str, Any]]:
    clean_code = _clean(code)
    if not clean_code:
        raise KnownTransformationError("CODE_MISSING", f"{source.spec.source_table} code missing")
    return [
        _event(
            source,
            component,
            event_kind,
            times=resolved_times(event_time=event_time),
            evidence_phase=evidence_phase,
            entity_type="coded_clinical_concept",
            source_label=label or clean_code,
            concept_id=f"{code_system}:{clean_code}",
            preferred_name=label or clean_code,
            quality_flags=["AVAILABLE_TIME_UNKNOWN"],
        )
    ]


def transform_diagnosis(source: SourceRow, context: AdmissionContext) -> list[dict[str, Any]]:
    del context
    row = source.row
    version = _clean(row.get("icd_version")) or "unknown"
    return _coded_event(
        source,
        component="diagnosis",
        event_kind="condition_recorded_post_hoc",
        code_system=f"icd{version}",
        code=row.get("icd_code"),
        label=_decoded_label(row, "icd_decoded"),
    )
def transform_ed_diagnosis(source: SourceRow, context: AdmissionContext) -> list[dict[str, Any]]:
    del context
    row = source.row
    version = _clean(row.get("icd_version")) or "unknown"
    return _coded_event(
        source,
        component="diagnosis",
        event_kind="condition_recorded_post_hoc",
        code_system=f"icd{version}",
        code=row.get("icd_code"),
        label=_clean(row.get("icd_title")),
    )


def transform_procedure_icd(source: SourceRow, context: AdmissionContext) -> list[dict[str, Any]]:
    del context
    row = source.row
    version = _clean(row.get("icd_version")) or "unknown"
    return _coded_event(
        source,
        component="procedure",
        event_kind="procedure_recorded_post_hoc",
        code_system=f"icd{version}",
        code=row.get("icd_code"),
        label=_decoded_label(row, "icd_decoded"),
        event_time=row.get("chartdate"),
    )


def transform_hcpcs(source: SourceRow, context: AdmissionContext) -> list[dict[str, Any]]:
    del context
    row = source.row
    return _coded_event(
        source,
        component="hcpcs",
        event_kind="procedure_recorded_post_hoc",
        code_system="hcpcs",
        code=row.get("hcpcs_cd"),
        label=_decoded_label(row, "hcpcs_cd_decoded") or _clean(row.get("short_description")),
        event_time=row.get("chartdate"),
    )


def transform_drg(source: SourceRow, context: AdmissionContext) -> list[dict[str, Any]]:
    del context
    row = source.row
    return _coded_event(
        source,
        component="drg",
        event_kind="administrative_group_recorded",
        code_system=f"drg-{_clean(row.get('drg_type')) or 'unknown'}",
        code=row.get("drg_code"),
        label=_clean(row.get("description")),
        evidence_phase="administrative_end",
    )
