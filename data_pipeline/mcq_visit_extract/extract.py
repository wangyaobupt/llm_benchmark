"""Project one visit's source rows into the 45 result fields plus lineage."""

from __future__ import annotations

from typing import Any

from .columns import (
    EMPTY_INVESTIGATIONS,
    MEDICATION_CORE_KEYS,
    MEDICATION_ITEM_KEYS,
    MEDRECON_ITEM_KEYS,
    PROCEDURE_CORE_KEYS,
    PROCEDURE_ITEM_KEYS,
    RESULT_COLUMNS,
)
from .ds_parser import select_ds

ICD_VERSION_LABEL = {"9": "ICD-9-CM", "10": "ICD-10-CM"}


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _or_none(value: Any) -> str | None:
    text = _text(value)
    return text or None


def _parse_float(value: Any) -> float | None:
    text = _text(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_int(value: Any) -> int | None:
    text = _text(value)
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def age_at_encounter(anchor_age: Any, anchor_year: Any, admittime: Any) -> int | None:
    try:
        age = int(str(anchor_age).strip())
        year = int(str(anchor_year).strip())
        admit_year = int(str(admittime).strip()[:4])
    except (TypeError, ValueError):
        return None
    return age + admit_year - year


def _latest_edstay(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    return max(rows, key=lambda row: (_text(row.get("intime")), _text(row.get("stay_id"))))


def _lab_items(
    rows: list[dict[str, Any]],
    dictionary: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not (_text(row.get("value")) or _text(row.get("valuenum")) or _text(row.get("comments"))):
            continue
        itemid = _text(row.get("itemid"))
        if not itemid:
            continue
        item = grouped.get(itemid)
        if item is None:
            meta = dictionary.get(itemid, {})
            item = {
                "itemid": _parse_int(itemid) if _parse_int(itemid) is not None else itemid,
                "label": _or_none(meta.get("label")),
                "fluid": _or_none(meta.get("fluid")),
                "category": _or_none(meta.get("category")),
                "results": [],
            }
            grouped[itemid] = item
        valuenum = _parse_float(row.get("valuenum"))
        item["results"].append(
            {
                "charttime": _or_none(row.get("charttime")),
                "storetime": _or_none(row.get("storetime")),
                "value": _or_none(row.get("value")),
                "valuenum": valuenum,
                "valueuom": _or_none(row.get("valueuom")),
                "ref_range_lower": _parse_float(row.get("ref_range_lower")),
                "ref_range_upper": _parse_float(row.get("ref_range_upper")),
                "flag": _or_none(row.get("flag")),
                "comments": _or_none(row.get("comments")),
            }
        )
    items = []
    for item in grouped.values():
        item["results"].sort(
            key=lambda result: (
                result["charttime"] or "",
                result["comments"] or "",
            )
        )
        items.append(item)
    items.sort(key=lambda item: str(item["itemid"]))
    return items


def _radiology(
    notes: list[dict[str, Any]],
    details: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_note: dict[str, list[dict[str, Any]]] = {}
    for row in details:
        by_note.setdefault(_text(row.get("note_id")), []).append(row)
    earliest: dict[str, dict[str, Any]] = {}
    for note in notes:
        if _text(note.get("note_type")).upper() != "RR":
            continue
        note_id = _text(note.get("note_id"))
        detail_rows = sorted(
            by_note.get(note_id, []),
            key=lambda row: (_parse_int(row.get("field_ordinal")) or 0, _text(row.get("field_name"))),
        )
        exam_name = None
        for row in detail_rows:
            if _text(row.get("field_name")).lower() == "exam_name":
                exam_name = _or_none(row.get("field_value"))
                break
        payload = {
            "exam_name": exam_name,
            "charttime": _or_none(note.get("charttime")),
            "storetime": _or_none(note.get("storetime")),
            "text": note.get("text") if note.get("text") not in (None, "") else None,
            "details": [
                {
                    "field_name": _or_none(row.get("field_name")),
                    "field_value": _or_none(row.get("field_value")),
                    "field_ordinal": _parse_int(row.get("field_ordinal")),
                }
                for row in detail_rows
            ],
        }
        key = exam_name or note_id
        previous = earliest.get(key)
        if previous is None or _text(payload["charttime"]) < _text(previous["charttime"]):
            earliest[key] = payload
    items = list(earliest.values())
    items.sort(key=lambda item: (item["charttime"] or "", item["exam_name"] or ""))
    return items


def _poe_orders(
    poe_rows: list[dict[str, Any]],
    detail_rows: list[dict[str, Any]],
    order_types: set[str],
) -> list[dict[str, Any]]:
    details_by: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in detail_rows:
        key = (_text(row.get("poe_id")), _text(row.get("poe_seq")))
        details_by.setdefault(key, []).append(
            {
                "field_name": _or_none(row.get("field_name")),
                "field_value": _or_none(row.get("field_value")),
            }
        )
    seen: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in poe_rows:
        if _text(row.get("transaction_type")) != "New":
            continue
        order_type = _text(row.get("order_type"))
        if order_type not in order_types:
            continue
        poe_id = _text(row.get("poe_id"))
        poe_seq = _text(row.get("poe_seq"))
        detail = sorted(
            details_by.get((poe_id, poe_seq), []),
            key=lambda item: (item["field_name"] or "", item["field_value"] or ""),
        )
        payload = {
            "order_subtype": _or_none(row.get("order_subtype")),
            "ordertime": _or_none(row.get("ordertime")),
            "poe_detail": detail,
        }
        if order_type in {"Lab", "Imaging"}:
            payload = {
                "order_type": order_type,
                **payload,
            }
        dedupe = (
            order_type,
            payload.get("order_subtype"),
            tuple((item["field_name"], item["field_value"]) for item in detail),
        )
        previous = seen.get(dedupe)
        if previous is None or _text(payload["ordertime"]) < _text(previous["ordertime"]):
            seen[dedupe] = payload
    items = list(seen.values())
    items.sort(key=lambda item: item.get("ordertime") or "")
    return items


def medication_core(item: dict[str, Any]) -> dict[str, Any]:
    return {key: item.get(key) for key in MEDICATION_CORE_KEYS}


def _medications(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items = []
    for row in rows:
        if _text(row.get("drug_type")).upper() != "MAIN":
            continue
        drug = _or_none(row.get("drug"))
        if not drug:
            continue
        starttime = _or_none(row.get("starttime"))
        items.append(
            {
                "drug": drug,
                "prod_strength": _or_none(row.get("prod_strength")),
                "form_rx": _or_none(row.get("form_rx")),
                "dose_val_rx": _or_none(row.get("dose_val_rx")),
                "dose_unit_rx": _or_none(row.get("dose_unit_rx")),
                "route": _or_none(row.get("route")),
                "doses_per_24_hrs": _parse_float(row.get("doses_per_24_hrs")),
                "starttime": starttime,
                "stoptime": _or_none(row.get("stoptime")),
                "_sort_starttime": starttime or "",
            }
        )
    items.sort(key=lambda item: item["_sort_starttime"])
    ordered: list[dict[str, Any]] = []
    for item in items:
        item.pop("_sort_starttime", None)
        ordered.append({key: item.get(key) for key in MEDICATION_ITEM_KEYS})
    return ordered


def _procedures(
    rows: list[dict[str, Any]],
    dictionary: dict[tuple[str, str], str],
) -> list[dict[str, Any]]:
    earliest: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        code = _text(row.get("icd_code"))
        version = _text(row.get("icd_version"))
        if not code or version not in {"9", "10"}:
            continue
        name = dictionary.get((code, version))
        if not name:
            continue
        key = (code, version)
        payload = {
            "procedure_name": name,
            "icd_code": code,
            "icd_version": int(version),
            "chartdate": _or_none(row.get("chartdate")),
            "_sort_date": _text(row.get("chartdate")),
            "_seq": _parse_int(row.get("seq_num")) or 0,
        }
        previous = earliest.get(key)
        if previous is None or (payload["_sort_date"], payload["_seq"]) < (
            previous["_sort_date"],
            previous["_seq"],
        ):
            earliest[key] = payload
    items = list(earliest.values())
    items.sort(
        key=lambda item: (
            item["_sort_date"],
            item["_seq"],
            item["icd_version"],
            item["icd_code"],
        )
    )
    ordered: list[dict[str, Any]] = []
    for item in items:
        item.pop("_sort_date", None)
        item.pop("_seq", None)
        ordered.append({key: item.get(key) for key in PROCEDURE_ITEM_KEYS})
    return ordered


def procedure_core(item: dict[str, Any]) -> dict[str, Any]:
    return {key: item.get(key) for key in PROCEDURE_CORE_KEYS}


def _diagnoses(
    rows: list[dict[str, Any]],
    dictionary: dict[tuple[str, str], str],
) -> tuple[dict[str, Any] | None, list[str]]:
    primaries = [row for row in rows if _parse_int(row.get("seq_num")) == 1]
    if len(primaries) != 1:
        return None, []
    primary_row = primaries[0]
    code = _text(primary_row.get("icd_code"))
    version = _text(primary_row.get("icd_version"))
    name = dictionary.get((code, version))
    if not code or version not in ICD_VERSION_LABEL or not name:
        return None, []
    primary = {
        "icd_code": code,
        "diagnosis_name": name,
        "icd_version": ICD_VERSION_LABEL[version],
    }
    others: list[tuple[int, str]] = []
    seen = {name.casefold()}
    rest = [row for row in rows if _parse_int(row.get("seq_num")) != 1]
    rest.sort(key=lambda row: _parse_int(row.get("seq_num")) or 10**9)
    for row in rest:
        other_code = _text(row.get("icd_code"))
        other_version = _text(row.get("icd_version"))
        other_name = dictionary.get((other_code, other_version))
        if not other_name:
            continue
        folded = " ".join(other_name.casefold().split())
        if folded in seen:
            continue
        seen.add(folded)
        others.append((_parse_int(row.get("seq_num")) or 10**9, other_name))
    return primary, [name for _, name in others]


def build_visit(
    *,
    selection_row: dict[str, Any],
    tables: dict[str, list[dict[str, Any]]],
    dictionaries: dict[str, Any],
) -> dict[str, Any] | None:
    admissions = tables.get("admissions") or []
    patients = tables.get("patients") or []
    if len(admissions) != 1 or not patients:
        return None
    admission = admissions[0]
    patient = patients[0]
    if _text(admission.get("subject_id")) != _text(selection_row["subject_id"]):
        raise ValueError("subject_id conflict with admissions")
    age = age_at_encounter(
        patient.get("anchor_age"),
        patient.get("anchor_year"),
        admission.get("admittime"),
    )
    sex = _text(patient.get("gender"))
    admission_type = _or_none(admission.get("admission_type"))
    if age is None or age < 18 or sex not in {"M", "F"} or not admission_type:
        return None

    selected = select_ds(tables.get("discharge") or [])
    if selected is None or not selected.sections.get("chief_complaint"):
        return None

    primary, other = _diagnoses(
        tables.get("diagnoses_icd") or [],
        dictionaries["d_icd_diagnoses"],
    )
    if primary is None:
        return None

    edstay = _latest_edstay(tables.get("edstays") or [])
    stay_id = _text(edstay.get("stay_id")) if edstay else ""
    triage_rows = [
        row for row in tables.get("triage") or [] if not stay_id or _text(row.get("stay_id")) == stay_id
    ]
    triage = triage_rows[0] if triage_rows else {}
    vitalsign_rows = [
        row
        for row in tables.get("vitalsign") or []
        if not stay_id or _text(row.get("stay_id")) == stay_id
    ]
    vitalsign_rows.sort(key=lambda row: _text(row.get("charttime")))
    rhythm = None
    rhythm_charttime = None
    for row in vitalsign_rows:
        rhythm = _or_none(row.get("rhythm"))
        if rhythm:
            rhythm_charttime = _or_none(row.get("charttime"))
            break
    vital_values = {
        "temperature": _parse_float(triage.get("temperature")),
        "heartrate": _parse_float(triage.get("heartrate")),
        "resprate": _parse_float(triage.get("resprate")),
        "o2sat": _parse_float(triage.get("o2sat")),
        "sbp": _parse_float(triage.get("sbp")),
        "dbp": _parse_float(triage.get("dbp")),
        "acuity": _parse_int(triage.get("acuity")),
        "rhythm": rhythm,
    }
    vitals_source = "triage" if any(value is not None for value in vital_values.values()) else None

    services = sorted(tables.get("services") or [], key=lambda row: _text(row.get("transfertime")))
    primary_service = _or_none(services[-1].get("curr_service")) if services else None
    service_path = [
        {
            "transfertime": _or_none(row.get("transfertime")),
            "prev_service": _or_none(row.get("prev_service")),
            "curr_service": _or_none(row.get("curr_service")),
        }
        for row in services
    ]
    transfers = sorted(tables.get("transfers") or [], key=lambda row: _text(row.get("intime")))
    transfer_items = [
        {
            "eventtype": _or_none(row.get("eventtype")),
            "careunit": _or_none(row.get("careunit")),
            "intime": _or_none(row.get("intime")),
            "outtime": _or_none(row.get("outtime")),
        }
        for row in transfers
    ]
    ed_diagnoses = sorted(
        tables.get("ed_diagnosis") or [],
        key=lambda row: _parse_int(row.get("seq_num")) or 0,
    )
    ed_diagnosis_items = [
        {
            "seq_num": _parse_int(row.get("seq_num")),
            "icd_code": _or_none(row.get("icd_code")),
            "icd_version": _or_none(row.get("icd_version")),
            "icd_title": _or_none(row.get("icd_title")),
        }
        for row in ed_diagnoses
        if not stay_id or _text(row.get("stay_id")) == stay_id
    ]
    medrecon_items = []
    for row in tables.get("medrecon") or []:
        if stay_id and _text(row.get("stay_id")) != stay_id:
            continue
        medrecon_items.append(
            {
                "name": _or_none(row.get("name")),
                "gsn": _or_none(row.get("gsn")),
                "ndc": _or_none(row.get("ndc")),
                "etcdescription": _or_none(row.get("etcdescription")),
                "charttime": _or_none(row.get("charttime")),
            }
        )
    medrecon_items.sort(key=lambda item: (item.get("charttime") or "", item.get("name") or ""))
    medrecon_items = [
        {key: item.get(key) for key in MEDRECON_ITEM_KEYS} for item in medrecon_items
    ]

    cardiology = _poe_orders(tables.get("poe") or [], tables.get("poe_detail") or [], {"Cardiology"})
    respiratory = _poe_orders(
        tables.get("poe") or [], tables.get("poe_detail") or [], {"Respiratory"}
    )
    poe_lab_imaging = _poe_orders(
        tables.get("poe") or [], tables.get("poe_detail") or [], {"Lab", "Imaging"}
    )

    investigations = {
        "laboratory": _lab_items(tables.get("labevents") or [], dictionaries["d_labitems"]),
        "radiology": _radiology(tables.get("radiology") or [], tables.get("radiology_detail") or []),
        "cardiology": cardiology,
        "respiratory": respiratory,
    }
    if not investigations["laboratory"] and not investigations["radiology"] and not cardiology and not respiratory:
        investigations = {
            "laboratory": [],
            "radiology": [],
            "cardiology": [],
            "respiratory": [],
        }

    sections = selected.sections
    result: dict[str, Any] = {
        "subject_id": str(selection_row["subject_id"]),
        "hadm_id": str(selection_row["hadm_id"]),
        "admittime": _or_none(admission.get("admittime")),
        "dischtime": _or_none(admission.get("dischtime")),
        "deathtime": _or_none(admission.get("deathtime")),
        "age_at_encounter": age,
        "sex": sex,
        "admission_type": admission_type,
        "vitals_source": vitals_source,
        **vital_values,
        "rhythm_charttime": rhythm_charttime,
        "chief_complaint": sections.get("chief_complaint"),
        "history_of_present_illness": sections.get("history_of_present_illness"),
        "past_medical_history": sections.get("past_medical_history"),
        "social_history": sections.get("social_history"),
        "medications_on_admission": sections.get("medications_on_admission"),
        "allergies": sections.get("allergies"),
        "physical_exam": sections.get("physical_exam"),
        "investigations": investigations or dict(EMPTY_INVESTIGATIONS),
        "primary_icd_code": primary["icd_code"],
        "primary_diagnosis_name": primary["diagnosis_name"],
        "primary_icd_version": primary["icd_version"],
        "other_diagnoses": other,
        "medications": _medications(tables.get("prescriptions") or []),
        "procedures": _procedures(
            tables.get("procedures_icd") or [], dictionaries["d_icd_procedures"]
        ),
        "primary_service": primary_service,
        "admission_location": _or_none(admission.get("admission_location")),
        "discharge_location": _or_none(admission.get("discharge_location")),
        "ed_disposition": _or_none(edstay.get("disposition")) if edstay else None,
        "ed_intime": _or_none(edstay.get("intime")) if edstay else None,
        "ed_outtime": _or_none(edstay.get("outtime")) if edstay else None,
        "edregtime": _or_none(admission.get("edregtime")),
        "edouttime": _or_none(admission.get("edouttime")),
        "brief_hospital_course": sections.get("brief_hospital_course"),
        "discharge_medications": sections.get("discharge_medications"),
        "discharge_condition": sections.get("discharge_condition"),
        "discharge_record": sections.get("discharge_record"),
        "discharge_note_full": selected.text,
        "discharge_diagnosis": sections.get("discharge_diagnosis"),
        "ed_chief_complaint": _or_none(triage.get("chiefcomplaint")),
        "ed_pain": _or_none(triage.get("pain")),
        "ed_diagnoses": ed_diagnosis_items,
        "medrecon": medrecon_items,
        "transfers": transfer_items,
        "service_path": service_path,
        "poe_lab_imaging": poe_lab_imaging,
        "lineage": {
            "selection_rank": selection_row["selection_rank"],
            "subject_bucket": selection_row["subject_bucket"],
            "sample_pool": selection_row["sample_pool"],
            "ds_note_id": selected.note_id,
            "ds_note_seq": selected.note_seq,
            "ds_charttime": selected.charttime,
            "ds_storetime": selected.storetime,
        },
        "audit": {"followup_instructions_unusable": selected.followup_unusable},
    }
    missing = [key for key in RESULT_COLUMNS if key not in result]
    if missing:
        raise ValueError(f"visit missing result keys: {missing}")
    return result
