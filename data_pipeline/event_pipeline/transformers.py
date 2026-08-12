"""Clinical-domain transformations from source rows to atomic events."""

from __future__ import annotations

from typing import Any

from .ids import build_entity_id, build_event_id, canonical_json
from .models import AdmissionContext, SourceRow
from .terminology import VITAL_CONCEPTS
from .time_resolver import resolved_times


class KnownTransformationError(ValueError):
    def __init__(self, reason_code: str, message: str):
        super().__init__(message)
        self.reason_code = reason_code


def _clean(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value).strip()


def _number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _decoded_label(row: dict[str, Any], field: str = "itemid_decoded") -> str | None:
    decoded = row.get(field)
    if not isinstance(decoded, dict):
        return None
    for name in ("label", "long_title", "long_description", "short_description"):
        value = _clean(decoded.get(name))
        if value:
            return value
    return None


def _encounter_id(source: SourceRow) -> str:
    stay_id = _clean(source.row.get("stay_id"))
    if stay_id and source.spec.module == "mimic_iv_ed":
        return f"ed:{stay_id}"
    if stay_id and source.spec.module == "mimic_iv_icu":
        return f"icu:{stay_id}"
    return f"hadm:{source.hadm_id}"


def _event(
    source: SourceRow,
    component: str,
    event_kind: str,
    *,
    times: dict[str, str | None] | None = None,
    evidence_phase: str = "source_event",
    lifecycle_action: str | None = None,
    status: str | None = None,
    assertion: str = "present",
    entity_type: str | None = None,
    source_label: str | None = None,
    concept_id: str | None = None,
    preferred_name: str | None = None,
    content_specificity: str = "entity_specific",
    value_numeric: float | None = None,
    value_text: str | None = None,
    value_structured: Any = None,
    unit: str | None = None,
    abnormal_flag: str | None = None,
    source_action: str | None = None,
    quality_flags: list[str] | None = None,
    supporting_rows: list[SourceRow] | None = None,
) -> dict[str, Any]:
    event_id = build_event_id(source.source_row_id, component)
    event = {
        "schema_version": "1.0.0",
        "event_id": event_id,
        "entity_id": build_entity_id(event_id) if entity_type else None,
        "source_row_id": source.source_row_id,
        "subject_id": source.subject_id,
        "hadm_id": source.hadm_id,
        "encounter_id": _encounter_id(source),
        "event_kind": event_kind,
        "lifecycle_action": lifecycle_action,
        "status": status,
        "assertion": assertion,
        **(times or resolved_times()),
        "evidence_phase": evidence_phase,
        "source_concept_id": concept_id,
        "concept_id": None,
        "preferred_name": None,
        "source_label": source_label,
        "entity_type": entity_type,
        "normalization_status": None,
        "terminology_mapping_version": None,
        "content_specificity": content_specificity,
        "value_numeric": value_numeric,
        "value_text": value_text,
        "value_structured_json": (
            canonical_json(value_structured) if value_structured is not None else None
        ),
        "unit": unit,
        "abnormal_flag": abnormal_flag,
        "normalized_value_numeric": None,
        "normalized_value_text": None,
        "normalized_unit": None,
        "unit_normalization_status": None,
        "source_module": source.spec.module,
        "source_table": source.spec.source_table,
        "source_array_index": source.source_array_index,
        "jsonl_line_number": source.jsonl_line_number,
        "raw_row_ref": source.raw_row_ref,
        "source_action": source_action,
        "quality_flags": list(dict.fromkeys(quality_flags or [])),
        "supporting_source_row_ids": [
            row.source_row_id for row in (supporting_rows or [])
        ],
    }
    return event


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


POE_ACTIONS = {
    "New": "create",
    "Change": "change",
    "D/C": "discontinue",
}


def transform_poe_timeline(source: SourceRow, context: AdmissionContext) -> list[dict[str, Any]]:
    """Eventize the existing deterministic POE view without re-eventizing raw POE."""
    del context
    row = source.row
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
        )
    ]


def transform_prescription(source: SourceRow, context: AdmissionContext) -> list[dict[str, Any]]:
    row = source.row
    drug = _clean(row.get("drug"))
    if not drug:
        raise KnownTransformationError(
            "PRESCRIPTION_DRUG_MISSING", "prescription drug is empty"
        )
    poe_id = _clean(row.get("poe_id"))
    raw_poe = context.indexes["raw_poe_by_id"].get(poe_id)
    order_time = raw_poe.get("ordertime") if isinstance(raw_poe, dict) else None
    ndc = _clean(row.get("ndc"))
    gsn = _clean(row.get("gsn"))
    source_concept_id = f"ndc:{ndc}" if ndc else (f"gsn:{gsn}" if gsn else None)
    flags = [] if order_time else ["ORDER_TIME_UNRESOLVED"]
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
                "pharmacy_id": row.get("pharmacy_id"),
                "effective_start": row.get("starttime"),
                "effective_stop": row.get("stoptime"),
                "dose": row.get("dose_val_rx"),
                "dose_unit": row.get("dose_unit_rx"),
                "form": row.get("form_rx"),
                "route": row.get("route"),
            },
            quality_flags=flags,
        )
    ]


def transform_pharmacy(source: SourceRow, context: AdmissionContext) -> list[dict[str, Any]]:
    del context
    row = source.row
    medication = _clean(row.get("medication"))
    if not medication:
        raise KnownTransformationError(
            "PHARMACY_MEDICATION_MISSING", "pharmacy medication is empty"
        )
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
                "poe_id": row.get("poe_id"),
                "pharmacy_id": row.get("pharmacy_id"),
                "effective_start": row.get("starttime"),
                "effective_stop": row.get("stoptime"),
                "route": row.get("route"),
                "frequency": row.get("frequency"),
            },
            quality_flags=(
                ["AVAILABLE_TIME_UNKNOWN"] if row.get("entertime") in (None, "") else []
            ),
        )
    ]


def transform_poe(source: SourceRow, context: AdmissionContext) -> list[dict[str, Any]]:
    row = source.row
    poe_id = _clean(row.get("poe_id"))
    details: list[SourceRow] = context.indexes["poe_detail_by_poe"].get(poe_id, [])
    prescriptions: list[SourceRow] = context.indexes["prescriptions_by_poe"].get(poe_id, [])
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


def transform_emar(source: SourceRow, context: AdmissionContext) -> list[dict[str, Any]]:
    row = source.row
    del context
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
    medication = _clean(row.get("medication"))
    flags = []
    charttime = _clean(row.get("charttime"))
    storetime = _clean(row.get("storetime"))
    if charttime and storetime and storetime < charttime:
        flags.append("AVAILABLE_BEFORE_EVENT_TIME")
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
                "poe_id": _clean(row.get("poe_id")),
                "pharmacy_id": _clean(row.get("pharmacy_id")),
            },
            quality_flags=flags,
        )
    ]


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
    available_time = row.get("storetime")
    flags: list[str] = []
    if kind == "procedure_performed" and row.get("endtime") not in (None, ""):
        if available_time in (None, "") or str(available_time) < str(row.get("endtime")):
            available_time = row.get("endtime")
            flags.append("AVAILABLE_TIME_DERIVED_FROM_COMPLETION")
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
                available_time=available_time,
                recorded_time=row.get("storetime"),
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
            quality_flags=flags,
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


def transform_radiology_note(source: SourceRow, context: AdmissionContext) -> list[dict[str, Any]]:
    row = source.row
    del context
    note_id = _clean(row.get("note_id"))
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
            value_structured={"note_id": note_id, "note_seq": row.get("note_seq")},
        )
    ]


def transform_discharge_note(source: SourceRow, context: AdmissionContext) -> list[dict[str, Any]]:
    row = source.row
    del context
    note_id = _clean(row.get("note_id"))
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
            evidence_phase="administrative_end",
            entity_type="clinical_document",
            source_label="Discharge summary",
            concept_id="document:discharge_summary",
            preferred_name="Discharge summary",
            value_structured={"note_id": note_id, "note_seq": row.get("note_seq")},
        )
    ]


TRANSFORMERS = {
    name: value
    for name, value in globals().copy().items()
    if name.startswith("transform_") and callable(value)
}
