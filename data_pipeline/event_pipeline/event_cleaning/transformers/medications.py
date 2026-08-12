"""Medication order, pharmacy, and eMAR event transformers."""

from __future__ import annotations

from typing import Any

from ..models import AdmissionContext, SourceRow
from ..time_resolver import resolved_times
from .common import KnownTransformationError, _clean, _event

ADMINISTERED_EMAR = {
    "Administered",
    "Administered in Other Location",
    "Delayed Administered",
    "Partial Administered",
    "Applied",
    "Started",
    "Started in Other Location",
    "Restarted",
}
NOT_ADMINISTERED_EMAR = {
    "Not Given",
    "Not Given per Sliding Scale",
    "Hold Dose",
    "Not Started",
    "Not Applied",
}

def _indexed_rows(
    context: AdmissionContext,
    index_name: str,
    key: Any,
) -> list[SourceRow]:
    if key in (None, ""):
        return []
    return list(context.indexes[index_name].get(key, []))


def _deduplicated_support(*groups: list[SourceRow]) -> list[SourceRow]:
    result: list[SourceRow] = []
    seen: set[str] = set()
    for group in groups:
        for source in group:
            if source.source_row_id not in seen:
                seen.add(source.source_row_id)
                result.append(source)
    return result


def _distinct_labels(rows: list[SourceRow], field: str) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for source in rows:
        label = _clean(source.row.get(field))
        key = label.casefold() if label else None
        if label and key not in seen:
            seen.add(key)
            result.append(label)
    return result


def _linked_poe_ids(rows: list[SourceRow]) -> set[str]:
    return {
        poe_id
        for source in rows
        if (poe_id := _clean(source.row.get("poe_id"))) is not None
    }


def _link_status(key: Any, matches: list[SourceRow]) -> str:
    if key in (None, ""):
        return "key_missing"
    if not matches:
        return "unresolved"
    if len(matches) == 1:
        return "linked"
    return "ambiguous"


def transform_prescription(source: SourceRow, context: AdmissionContext) -> list[dict[str, Any]]:
    row = source.row
    drug = _clean(row.get("drug"))
    if not drug:
        raise KnownTransformationError(
            "PRESCRIPTION_DRUG_MISSING", "prescription drug is empty"
        )
    poe_id = _clean(row.get("poe_id"))
    poe_seq = _clean(row.get("poe_seq"))
    poe_pair = (poe_id, poe_seq) if poe_id and poe_seq else None
    poe_sources = _indexed_rows(context, "poe_timeline_by_pair", poe_pair)
    pharmacy_id = _clean(row.get("pharmacy_id"))
    pharmacy_sources = _indexed_rows(context, "pharmacy_by_id", pharmacy_id)
    order_time = (
        poe_sources[0].row.get("event_time")
        if len(poe_sources) == 1
        else None
    )
    ndc = _clean(row.get("ndc"))
    gsn = _clean(row.get("gsn"))
    source_concept_id = f"ndc:{ndc}" if ndc else (f"gsn:{gsn}" if gsn else None)
    flags = [] if order_time else ["ORDER_TIME_UNRESOLVED"]
    if len(pharmacy_sources) != 1:
        flags.append("UNRESOLVED_PHARMACY_ID")
        if len(pharmacy_sources) > 1:
            flags.append("AMBIGUOUS_MEDICATION_PAIRING")
    if (
        poe_id
        and pharmacy_sources
        and (pharmacy_poe_id := _clean(pharmacy_sources[0].row.get("poe_id")))
        and pharmacy_poe_id != poe_id
    ):
        flags.append("PHARMACY_POE_ID_CONFLICT")
    return [
        _event(
            source,
            "prescription",
            "medication_ordered",
            times=resolved_times(event_time=order_time, available_time=order_time),
            lifecycle_action="create",
            entity_type="medication",
            source_label=drug,
            concept_id=source_concept_id,
            preferred_name=drug,
            value_structured={
                "poe_id": poe_id,
                "poe_seq": poe_seq,
                "pharmacy_id": pharmacy_id,
                "effective_start": row.get("starttime"),
                "effective_stop": row.get("stoptime"),
                "dose": row.get("dose_val_rx"),
                "dose_unit": row.get("dose_unit_rx"),
                "form": row.get("form_rx"),
                "route": row.get("route"),
                "linkage": {
                    "poe_pair_status": _link_status(poe_pair, poe_sources),
                    "pharmacy_id_status": _link_status(
                        pharmacy_id, pharmacy_sources
                    ),
                },
            },
            quality_flags=flags,
            supporting_rows=_deduplicated_support(
                poe_sources, pharmacy_sources
            ),
        )
    ]



def transform_pharmacy(source: SourceRow, context: AdmissionContext) -> list[dict[str, Any]]:
    row = source.row
    pharmacy_id = _clean(row.get("pharmacy_id"))
    prescriptions = _indexed_rows(
        context, "prescriptions_by_pharmacy_id", pharmacy_id
    )
    medication_raw = _clean(row.get("medication"))
    medication = medication_raw
    flags: list[str] = []
    medication_resolution = "pharmacy.medication"
    if not medication:
        candidates = _distinct_labels(prescriptions, "drug")
        if len(candidates) == 1:
            medication = candidates[0]
            medication_resolution = "prescriptions.drug_by_pharmacy_id"
            flags.append("MEDICATION_LABEL_RESOLVED_FROM_LINKED_SOURCE")
        elif len(candidates) > 1:
            raise KnownTransformationError(
                "PHARMACY_MEDICATION_AMBIGUOUS",
                f"pharmacy_id {pharmacy_id} maps to {len(candidates)} prescription drugs",
            )
        else:
            raise KnownTransformationError(
                "PHARMACY_MEDICATION_UNRESOLVED",
                f"pharmacy_id {pharmacy_id} has no medication or linked prescription drug",
            )

    poe_id_raw = _clean(row.get("poe_id"))
    prescription_poe_ids = _linked_poe_ids(prescriptions)
    if poe_id_raw and any(value != poe_id_raw for value in prescription_poe_ids):
        flags.append("PHARMACY_POE_ID_CONFLICT")
    resolved_poe_id = poe_id_raw
    poe_resolution = "pharmacy.poe_id" if poe_id_raw else "unresolved"
    if resolved_poe_id is None and len(prescription_poe_ids) == 1:
        resolved_poe_id = next(iter(prescription_poe_ids))
        poe_resolution = "prescriptions.poe_id_by_pharmacy_id"
    elif resolved_poe_id is None and len(prescription_poe_ids) > 1:
        flags.extend(["UNRESOLVED_POE_ID", "AMBIGUOUS_MEDICATION_PAIRING"])
    poe_sources = _indexed_rows(context, "poe_timeline_by_id", resolved_poe_id)
    if resolved_poe_id is None or len(poe_sources) != 1:
        if "UNRESOLVED_POE_ID" not in flags:
            flags.append("UNRESOLVED_POE_ID")
        if len(poe_sources) > 1 and "AMBIGUOUS_MEDICATION_PAIRING" not in flags:
            flags.append("AMBIGUOUS_MEDICATION_PAIRING")
    return [
        _event(
            source,
            "pharmacy_order",
            "medication_order_status_recorded",
            times=resolved_times(
                event_time=row.get("entertime"),
                available_time=row.get("entertime"),
                recorded_time=row.get("verifiedtime"),
            ),
            status=_clean(row.get("status")),
            entity_type="medication",
            source_label=medication,
            preferred_name=medication,
            value_structured={
                "poe_id": poe_id_raw,
                "resolved_poe_id": resolved_poe_id,
                "poe_resolution": poe_resolution,
                "pharmacy_id": pharmacy_id,
                "medication_raw": medication_raw,
                "medication_resolution": medication_resolution,
                "linked_prescription_count": len(prescriptions),
                "effective_start": row.get("starttime"),
                "effective_stop": row.get("stoptime"),
                "route": row.get("route"),
                "frequency": row.get("frequency"),
            },
            quality_flags=(
                [*flags, "AVAILABLE_TIME_UNKNOWN"]
                if row.get("entertime") in (None, "")
                else flags
            ),
            supporting_rows=_deduplicated_support(poe_sources, prescriptions),
        )
    ]



def transform_emar(source: SourceRow, context: AdmissionContext) -> list[dict[str, Any]]:
    row = source.row
    event_text = _clean(row.get("event_txt"))
    if event_text in ADMINISTERED_EMAR:
        kind = "medication_administered"
        assertion = "present"
    elif event_text in NOT_ADMINISTERED_EMAR or (event_text or "").startswith("Not "):
        kind = "medication_not_administered"
        assertion = "absent"
    else:
        kind = "medication_administration_documented"
        assertion = "unknown"
    pharmacy_id = _clean(row.get("pharmacy_id"))
    poe_id_raw = _clean(row.get("poe_id"))
    pharmacy_sources = _indexed_rows(context, "pharmacy_by_id", pharmacy_id)
    prescriptions = _indexed_rows(
        context, "prescriptions_by_pharmacy_id", pharmacy_id
    )
    detail_key = (
        _clean(row.get("subject_id")),
        _clean(row.get("emar_id")),
        _clean(row.get("emar_seq")),
    )
    details = _indexed_rows(context, "emar_details_by_parent", detail_key)

    flags: list[str] = []
    if len(pharmacy_sources) != 1:
        flags.append("UNRESOLVED_PHARMACY_ID")
        if len(pharmacy_sources) > 1:
            flags.append("AMBIGUOUS_MEDICATION_PAIRING")

    linked_medication_rows = _deduplicated_support(
        pharmacy_sources, prescriptions
    )
    linked_poe_ids = _linked_poe_ids(linked_medication_rows)
    if poe_id_raw and any(value != poe_id_raw for value in linked_poe_ids):
        flags.append("PHARMACY_POE_ID_CONFLICT")

    resolved_poe_id = poe_id_raw
    poe_resolution = "emar.poe_id" if poe_id_raw else "unresolved"
    if resolved_poe_id is None and len(linked_poe_ids) == 1:
        resolved_poe_id = next(iter(linked_poe_ids))
        poe_resolution = "pharmacy_chain_by_pharmacy_id"
    elif resolved_poe_id is None and len(linked_poe_ids) > 1:
        flags.extend(["UNRESOLVED_POE_ID", "AMBIGUOUS_MEDICATION_PAIRING"])
    poe_sources = _indexed_rows(context, "poe_timeline_by_id", resolved_poe_id)
    if resolved_poe_id is None or len(poe_sources) != 1:
        if "UNRESOLVED_POE_ID" not in flags:
            flags.append("UNRESOLVED_POE_ID")
        if len(poe_sources) > 1 and "AMBIGUOUS_MEDICATION_PAIRING" not in flags:
            flags.append("AMBIGUOUS_MEDICATION_PAIRING")

    medication_raw = _clean(row.get("medication"))
    medication = medication_raw
    medication_resolution = "emar.medication" if medication_raw else "unresolved"
    if medication is None:
        linked_labels = [
            *_distinct_labels(pharmacy_sources, "medication"),
            *_distinct_labels(prescriptions, "drug"),
        ]
        candidates: list[str] = []
        seen_candidate_keys: set[str] = set()
        for label in linked_labels:
            key = label.casefold()
            if key not in seen_candidate_keys:
                seen_candidate_keys.add(key)
                candidates.append(label)
        if len(candidates) == 1:
            medication = candidates[0]
            medication_resolution = "linked_source_by_pharmacy_id"
            flags.append("MEDICATION_LABEL_RESOLVED_FROM_LINKED_SOURCE")
        elif len(candidates) > 1:
            medication_resolution = "ambiguous_linked_sources"
            flags.append("AMBIGUOUS_MEDICATION_PAIRING")

    return [
        _event(
            source,
            "administration",
            kind,
            times=resolved_times(
                event_time=row.get("charttime"),
                available_time=row.get("storetime"),
                recorded_time=row.get("storetime"),
            ),
            status=event_text,
            assertion=assertion,
            entity_type="medication",
            source_label=medication,
            preferred_name=medication,
            value_structured={
                "scheduled_time": _clean(row.get("scheduletime")),
                "poe_id": poe_id_raw,
                "resolved_poe_id": resolved_poe_id,
                "poe_resolution": poe_resolution,
                "pharmacy_id": pharmacy_id,
                "medication_raw": medication_raw,
                "medication_resolution": medication_resolution,
                "linked_prescription_count": len(prescriptions),
                "linked_emar_detail_count": len(details),
            },
            quality_flags=flags,
            supporting_rows=_deduplicated_support(
                poe_sources,
                pharmacy_sources,
                prescriptions,
                details,
            ),
        )
    ]
