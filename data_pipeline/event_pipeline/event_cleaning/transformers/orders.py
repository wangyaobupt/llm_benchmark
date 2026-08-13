"""POE order event transformers."""

from __future__ import annotations

from typing import Any

from ..models import AdmissionContext, SourceRow
from ..time_resolver import resolved_times
from .common import _clean, _event

POE_ACTIONS = {
    "New": "create",
    "Change": "change",
    "D/C": "discontinue",
}

def transform_poe_timeline(source: SourceRow, context: AdmissionContext) -> list[dict[str, Any]]:
    """Eventize the existing deterministic POE view without re-eventizing raw POE."""
    row = source.row
    poe_id = _clean(row.get("poe_id"))
    poe_seq = _clean(row.get("poe_seq"))
    pair = (poe_id, poe_seq) if poe_id and poe_seq else None
    raw_poe = list(context.indexes["poe_by_pair"].get(pair, []))
    details = list(context.indexes["poe_details_by_pair"].get(pair, []))
    category = row.get("clinical_category") or {}
    order_type = _clean(category.get("raw")) if isinstance(category, dict) else None
    subtype = _clean(category.get("subtype_raw")) if isinstance(category, dict) else None
    order_content = row.get("order_content") if isinstance(row.get("order_content"), dict) else {}
    medications = order_content.get("medications", []) if isinstance(order_content, dict) else []
    medication_labels = [
        _clean(item.get("drug"))
        for item in medications
        if isinstance(item, dict) and _clean(item.get("drug"))
    ]
    event_kind = {
        "Lab": "laboratory_ordered",
        "Radiology": "imaging_ordered",
    }.get(order_type, "clinical_ordered")
    entity_type = {
        "Lab": "laboratory_test",
        "Radiology": "imaging_study",
        "Medications": "medication_order_category",
    }.get(order_type, "clinical_order")
    label = medication_labels[0] if len(medication_labels) == 1 else subtype
    specificity = _clean(row.get("content_specificity")) or "category_only"
    flags = list(row.get("quality_flags") or [])
    if specificity == "category_only" and "CATEGORY_ONLY_NO_SPECIFIC_ORDER_CONTENT" not in flags:
        flags.append("CATEGORY_ONLY_NO_SPECIFIC_ORDER_CONTENT")
    action = _clean(row.get("action")) or "uninterpreted"
    return [
        _event(
            source,
            "order_lifecycle",
            event_kind,
            times=resolved_times(
                event_time=row.get("event_time"), available_time=row.get("event_time")
            ),
            lifecycle_action=action,
            status=_clean(row.get("order_status_raw")),
            entity_type=entity_type,
            source_label=label,
            content_specificity=specificity,
            value_structured={
                "poe_id": row.get("poe_id"),
                "poe_seq": row.get("poe_seq"),
                "order_type": order_type,
                "order_subtype": subtype,
                "medication_labels": medication_labels,
                "relations": row.get("relations"),
            },
            source_action=action,
            quality_flags=flags,
            supporting_rows=[*raw_poe, *details],
        )
    ]


def transform_poe(source: SourceRow, context: AdmissionContext) -> list[dict[str, Any]]:
    row = source.row
    poe_id = _clean(row.get("poe_id"))
    details: list[SourceRow] = context.indexes["poe_details_by_id"].get(poe_id, [])
    prescriptions: list[SourceRow] = context.indexes["prescriptions_by_poe_id"].get(poe_id, [])
    pharmacies: list[SourceRow] = []
    for prescription in prescriptions:
        pharmacy_id = _clean(prescription.row.get("pharmacy_id"))
        pharmacies.extend(context.indexes["pharmacy_by_id"].get(pharmacy_id, []))
    support_by_id = {
        support_row.source_row_id: support_row
        for support_row in [*details, *prescriptions, *pharmacies]
    }
    support = list(support_by_id.values())
    order_type = _clean(row.get("order_type"))
    event_kind = {
        "Lab": "laboratory_ordered",
        "Radiology": "imaging_ordered",
        "Medications": "medication_ordered",
    }.get(order_type, "clinical_ordered")
    entity_type = {
        "Lab": "laboratory_test",
        "Radiology": "imaging_study",
        "Medications": "medication",
    }.get(order_type, "clinical_order")
    medications = []
    for prescription in prescriptions:
        drug = _clean(prescription.row.get("drug"))
        if drug:
            medications.append(
                {
                    "drug": drug,
                    "ndc": _clean(prescription.row.get("ndc")),
                    "gsn": _clean(prescription.row.get("gsn")),
                    "dose": _clean(prescription.row.get("dose_val_rx")),
                    "dose_unit": _clean(prescription.row.get("dose_unit_rx")),
                    "route": _clean(prescription.row.get("route")),
                }
            )
    subtype = _clean(row.get("order_subtype"))
    label = medications[0]["drug"] if len(medications) == 1 else subtype
    concept_id = None
    if len(medications) == 1:
        ndc = medications[0]["ndc"]
        gsn = medications[0]["gsn"]
        concept_id = f"ndc:{ndc}" if ndc else (f"gsn:{gsn}" if gsn else None)
    specificity = "category_only"
    if medications:
        specificity = "entity_specific" if len(medications) == 1 else "attribute_enriched"
    elif subtype:
        specificity = "subtype_only"
    flags = []
    if specificity == "category_only":
        flags.append("CATEGORY_ONLY_NO_SPECIFIC_ORDER_CONTENT")
    action_raw = _clean(row.get("transaction_type"))
    lifecycle_action = POE_ACTIONS.get(action_raw, "uninterpreted")
    if lifecycle_action == "uninterpreted":
        flags.append("POE_ACTION_UNINTERPRETED")
    return [
        _event(
            source,
            "order",
            event_kind,
            times=resolved_times(
                event_time=row.get("ordertime"),
                available_time=row.get("ordertime"),
            ),
            lifecycle_action=lifecycle_action,
            status=_clean(row.get("order_status")),
            entity_type=entity_type,
            source_label=label,
            concept_id=concept_id,
            preferred_name=label,
            content_specificity=specificity,
            value_structured={
                "order_type": order_type,
                "order_subtype": subtype,
                "details": [detail.row for detail in details],
                "medications": medications,
            },
            source_action=lifecycle_action,
            quality_flags=flags,
            supporting_rows=support,
        )
    ]
