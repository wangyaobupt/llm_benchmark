"""Emergency-department event transformers."""

from __future__ import annotations

from typing import Any

from ..models import AdmissionContext, SourceRow
from ..source_concepts import VITAL_CONCEPTS
from ..time_resolver import resolved_times
from .common import _clean, _event, _number

def _vital_event(
    source: SourceRow,
    component: str,
    value: Any,
    *,
    times: dict[str, str | None],
) -> dict[str, Any] | None:
    if value in (None, ""):
        return None
    concept_id, preferred_name, unit = VITAL_CONCEPTS[component]
    numeric = _number(value)
    return _event(
        source,
        component,
        "vital_measured",
        times=times,
        entity_type="vital_sign",
        source_label=preferred_name,
        concept_id=concept_id,
        preferred_name=preferred_name,
        value_numeric=numeric,
        value_text=None if numeric is not None else _clean(value),
        unit=unit,
    )


def _vital_events(
    source: SourceRow,
    *,
    times: dict[str, str | None],
) -> list[dict[str, Any]]:
    row = source.row
    events: list[dict[str, Any]] = []
    field_map = {
        "heart_rate": "heartrate",
        "temperature": "temperature",
        "respiratory_rate": "resprate",
        "oxygen_saturation": "o2sat",
        "pain_score": "pain",
    }
    for component, field in field_map.items():
        event = _vital_event(source, component, row.get(field), times=times)
        if event:
            events.append(event)
    systolic = _number(row.get("sbp"))
    diastolic = _number(row.get("dbp"))
    if systolic is not None or diastolic is not None:
        concept_id, preferred_name, unit = VITAL_CONCEPTS["blood_pressure"]
        events.append(
            _event(
                source,
                "blood_pressure",
                "vital_measured",
                times=times,
                entity_type="vital_sign",
                source_label=preferred_name,
                concept_id=concept_id,
                preferred_name=preferred_name,
                value_structured={"systolic": systolic, "diastolic": diastolic},
                unit=unit,
            )
        )
    return events


def transform_ed_triage(source: SourceRow, context: AdmissionContext) -> list[dict[str, Any]]:
    del context
    times = resolved_times()
    events = _vital_events(source, times=times)
    complaint = _clean(source.row.get("chiefcomplaint"))
    if complaint:
        events.insert(
            0,
            _event(
                source,
                "chiefcomplaint",
                "symptom_reported",
                times=times,
                entity_type="symptom",
                source_label=complaint,
                preferred_name=complaint,
                quality_flags=["TIME_UNAVAILABLE_IN_SOURCE"],
            ),
        )
    acuity = _number(source.row.get("acuity"))
    if acuity is not None:
        events.append(
            _event(
                source,
                "acuity",
                "triage_acuity_recorded",
                times=times,
                entity_type="triage_acuity",
                source_label="ED acuity",
                concept_id="triage:acuity",
                preferred_name="ED acuity",
                value_numeric=acuity,
                quality_flags=["TIME_UNAVAILABLE_IN_SOURCE"],
            )
        )
    return events


def transform_ed_vitals(source: SourceRow, context: AdmissionContext) -> list[dict[str, Any]]:
    del context
    return _vital_events(
        source,
        times=resolved_times(event_time=source.row.get("charttime")),
    )



def transform_ed_medrecon(source: SourceRow, context: AdmissionContext) -> list[dict[str, Any]]:
    del context
    row = source.row
    name = _clean(row.get("name"))
    return [
        _event(
            source,
            "medication",
            "medication_reconciled",
            times=resolved_times(event_time=row.get("charttime")),
            entity_type="medication",
            source_label=name,
            concept_id=f"ndc:{row['ndc']}" if _clean(row.get("ndc")) else None,
            preferred_name=name,
            quality_flags=["AVAILABLE_TIME_UNKNOWN"],
        )
    ]
def transform_ed_pyxis(source: SourceRow, context: AdmissionContext) -> list[dict[str, Any]]:
    del context
    row = source.row
    name = _clean(row.get("name"))
    return [
        _event(
            source,
            "dispense",
            "medication_dispensed",
            times=resolved_times(event_time=row.get("charttime")),
            entity_type="medication",
            source_label=name,
            concept_id=f"gsn:{row['gsn']}" if _clean(row.get("gsn")) else None,
            preferred_name=name,
            quality_flags=["AVAILABLE_TIME_UNKNOWN"],
        )
    ]
