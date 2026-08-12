"""Laboratory and microbiology event transformers."""

from __future__ import annotations

from typing import Any

from ..models import AdmissionContext, SourceRow
from ..time_resolver import resolved_times
from .common import KnownTransformationError, _clean, _decoded_label, _event, _number

def _lab_abnormal_flag(row: dict[str, Any]) -> str | None:
    raw_flag = _clean(row.get("flag"))
    if raw_flag:
        return raw_flag.casefold()
    value = _number(row.get("valuenum"))
    lower = _number(row.get("ref_range_lower"))
    upper = _number(row.get("ref_range_upper"))
    if value is None or (lower is None and upper is None):
        return None
    if lower is not None and value < lower:
        return "low"
    if upper is not None and value > upper:
        return "high"
    return "normal"


def transform_labevent(source: SourceRow, context: AdmissionContext) -> list[dict[str, Any]]:
    del context
    row = source.row
    itemid = _clean(row.get("itemid"))
    label = _decoded_label(row)
    if not itemid or not label:
        raise KnownTransformationError(
            "LAB_CONCEPT_MISSING", "labevents requires itemid and decoded label"
        )
    numeric = _number(row.get("valuenum"))
    value_text = _clean(row.get("value"))
    if numeric is not None and value_text == "___":
        value_text = None
    flags = []
    if row.get("storetime") in (None, ""):
        flags.append("AVAILABLE_TIME_UNKNOWN")
    return [
        _event(
            source,
            "result",
            "laboratory_resulted",
            times=resolved_times(
                event_time=row.get("charttime"),
                available_time=row.get("storetime"),
                recorded_time=row.get("storetime"),
            ),
            entity_type="laboratory_test",
            source_label=label,
            concept_id=f"lab:{itemid}",
            preferred_name=label,
            value_numeric=numeric,
            value_text=value_text,
            unit=_clean(row.get("valueuom")),
            abnormal_flag=_lab_abnormal_flag(row),
            quality_flags=flags,
        )
    ]

def transform_microbiology(source: SourceRow, context: AdmissionContext) -> list[dict[str, Any]]:
    del context
    row = source.row
    label = _clean(row.get("test_name")) or _clean(row.get("spec_type_desc"))
    concept_code = _clean(row.get("test_itemid")) or _clean(row.get("spec_itemid"))
    if not label:
        raise KnownTransformationError(
            "MICROBIOLOGY_CONCEPT_MISSING", "microbiology row has no test or specimen name"
        )
    return [
        _event(
            source,
            "result",
            "microbiology_resulted",
            times=resolved_times(
                event_time=row.get("charttime") or row.get("chartdate"),
                available_time=row.get("storetime"),
                recorded_time=row.get("storetime") or row.get("storedate"),
            ),
            entity_type="microbiology_test",
            source_label=label,
            concept_id=f"microbiology:{concept_code}" if concept_code else None,
            preferred_name=label,
            value_structured={
                "specimen": row.get("spec_type_desc"),
                "organism": row.get("org_name"),
                "antibiotic": row.get("ab_name"),
                "interpretation": row.get("interpretation"),
                "dilution": row.get("dilution_text"),
            },
            quality_flags=(
                ["AVAILABLE_TIME_UNKNOWN"]
                if row.get("storetime") in (None, "")
                else []
            ),
        )
    ]
