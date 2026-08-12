"""ICU input, output, and procedure event transformers."""

from __future__ import annotations

from typing import Any

from ..models import AdmissionContext, SourceRow
from ..time_resolver import resolved_times
from .common import KnownTransformationError, _clean, _decoded_label, _event, _number

def _icu_item_event(
    source: SourceRow,
    *,
    component: str,
    kind: str,
    event_field: str,
    value_field: str,
) -> list[dict[str, Any]]:
    row = source.row
    itemid = _clean(row.get("itemid"))
    label = _decoded_label(row)
    if not itemid or not label:
        raise KnownTransformationError(
            "ICU_CONCEPT_MISSING", f"{source.spec.source_table} itemid decoding missing"
        )
    numeric = _number(row.get(value_field))
    completion_time = (
        row.get("endtime")
        if kind in {"input_administered", "procedure_performed"}
        else None
    )
    unit = _clean(row.get("valueuom")) or _clean(row.get("amountuom"))
    if unit == "None":
        unit = None
    return [
        _event(
            source,
            component,
            kind,
            times=resolved_times(
                event_time=row.get(event_field),
                available_time=row.get("storetime"),
                recorded_time=row.get("storetime"),
                completion_time=completion_time,
            ),
            status=_clean(row.get("statusdescription")),
            entity_type="icu_item",
            source_label=label,
            concept_id=f"mimic-item:{itemid}",
            preferred_name=label,
            value_numeric=numeric,
            value_text=None if numeric is not None else _clean(row.get(value_field)),
            unit=unit,
            value_structured={
                "endtime": _clean(row.get("endtime")),
                "rate": _clean(row.get("rate")),
                "rate_unit": _clean(row.get("rateuom")),
            },
        )
    ]


def transform_icu_datetime(source: SourceRow, context: AdmissionContext) -> list[dict[str, Any]]:
    del context
    return _icu_item_event(source, component="datetime", kind="clinical_datetime_recorded", event_field="charttime", value_field="value")


def transform_icu_ingredient(source: SourceRow, context: AdmissionContext) -> list[dict[str, Any]]:
    del context
    return _icu_item_event(source, component="ingredient", kind="medication_ingredient_administered", event_field="starttime", value_field="amount")


def transform_icu_input(source: SourceRow, context: AdmissionContext) -> list[dict[str, Any]]:
    del context
    return _icu_item_event(source, component="input", kind="input_administered", event_field="starttime", value_field="amount")


def transform_icu_output(source: SourceRow, context: AdmissionContext) -> list[dict[str, Any]]:
    del context
    return _icu_item_event(source, component="output", kind="output_measured", event_field="charttime", value_field="value")


def transform_icu_procedure(source: SourceRow, context: AdmissionContext) -> list[dict[str, Any]]:
    del context
    return _icu_item_event(source, component="procedure", kind="procedure_performed", event_field="starttime", value_field="value")
