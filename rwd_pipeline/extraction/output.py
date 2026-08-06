from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Set

import pandas as pd

from .common import OUTPUT_COLUMNS, ExtractionError, compact_json


def build_output_frame(
    cohort: pd.DataFrame,
    eligible_hadm_ids: Set[str],
    diagnoses: Mapping[str, Mapping[str, object]],
    discharge: Mapping[str, Mapping[str, Optional[str]]],
    orders: Mapping[str, List[dict]],
    labs: Mapping[str, List[dict]],
    radiology: Mapping[str, List[dict]],
    prescriptions: Mapping[str, List[dict]],
    procedures: Mapping[str, List[dict]],
) -> pd.DataFrame:
    selected = cohort.loc[cohort["hadm_id"].isin(eligible_hadm_ids)].sort_values(
        "_source_order", kind="stable"
    )
    rows = []
    for visit in selected.to_dict("records"):
        hadm_id = str(visit["hadm_id"])
        diagnosis = diagnoses[hadm_id]
        note = discharge[hadm_id]
        rows.append(
            {
                "subject_id": str(visit["subject_id"]),
                "hadm_id": hadm_id,
                "age_at_encounter": int(visit["age_at_encounter"]),
                "sex": str(visit["sex"]),
                "chief_complaint": note["chief_complaint"],
                "history_of_present_illness": note["history_of_present_illness"] or "",
                "past_medical_history": note["past_medical_history"] or "",
                "medications_on_admission": note["medications_on_admission"] or "",
                "investigation_orders": compact_json(orders.get(hadm_id, [])),
                "investigation_reports": compact_json(
                    {
                        "laboratory": labs.get(hadm_id, []),
                        "radiology": radiology.get(hadm_id, []),
                    }
                ),
                "primary_icd_code": diagnosis["primary_icd_code"],
                "primary_diagnosis_name": diagnosis["primary_diagnosis_name"],
                "primary_icd_version": diagnosis["primary_icd_version"],
                "other_diagnoses": compact_json(diagnosis["other_diagnoses"]),
                "medication_prescriptions": compact_json(prescriptions.get(hadm_id, [])),
                "procedures": compact_json(procedures.get(hadm_id, [])),
                "discharge_record": note["discharge_record"] or "",
            }
        )
    return pd.DataFrame(rows, columns=OUTPUT_COLUMNS)


def validate_output(frame: pd.DataFrame, candidate_order: Mapping[str, int]) -> None:
    if list(frame.columns) != OUTPUT_COLUMNS:
        raise ExtractionError("Output columns do not match the required 17-column schema")
    if frame["hadm_id"].isna().any() or frame["hadm_id"].duplicated().any():
        raise ExtractionError("Output hadm_id values must be non-empty and unique")

    required = [
        "subject_id",
        "hadm_id",
        "age_at_encounter",
        "sex",
        "chief_complaint",
        "primary_icd_code",
        "primary_diagnosis_name",
        "primary_icd_version",
    ]
    for column in required:
        invalid = frame[column].isna() | frame[column].astype(str).str.strip().eq("")
        if invalid.any():
            raise ExtractionError(f"Output contains an empty required field: {column}")
    if not frame["age_at_encounter"].ge(18).all():
        raise ExtractionError("Output contains an age below 18")
    if not frame["sex"].isin(["M", "F"]).all():
        raise ExtractionError("Output contains an invalid sex value")

    positions = [candidate_order.get(str(hadm_id), -1) for hadm_id in frame["hadm_id"]]
    if any(position < 0 for position in positions) or positions != sorted(positions):
        raise ExtractionError("Output visits do not preserve candidate admissions order")

    for row in frame.to_dict("records"):
        other = json.loads(row["other_diagnoses"])
        orders = json.loads(row["investigation_orders"])
        prescriptions = json.loads(row["medication_prescriptions"])
        procedures = json.loads(row["procedures"])
        reports = json.loads(row["investigation_reports"])
        if not all(isinstance(value, list) for value in [other, orders, prescriptions, procedures]):
            raise ExtractionError("An output JSON array field has the wrong type")
        if set(reports) != {"laboratory", "radiology"}:
            raise ExtractionError("investigation_reports must contain laboratory and radiology")
        if not isinstance(reports["laboratory"], list) or not isinstance(reports["radiology"], list):
            raise ExtractionError("investigation_reports members must be arrays")
        if not all(isinstance(item, str) for item in other):
            raise ExtractionError("other_diagnoses must contain only strings")
        if not all(set(item) == {"order_type", "order_subtype", "poe_detail"} for item in orders):
            raise ExtractionError("An investigation order has the wrong fixed attributes")
        if not all(
            set(detail) == {"field_name", "field_value"}
            for item in orders
            for detail in item["poe_detail"]
        ):
            raise ExtractionError("A POE detail object has the wrong fixed attributes")
        if not all(
            set(item) == {"d_labitems", "labevents"}
            and set(item["d_labitems"]) == {"itemid", "label", "fluid", "category"}
            and set(item["labevents"])
            == {"value", "valuenum", "valueuom", "ref_range_lower", "ref_range_upper", "flag", "comments"}
            for item in reports["laboratory"]
        ):
            raise ExtractionError("A laboratory result has the wrong fixed attributes")
        if not all(
            set(item) == {"radiology", "radiology_detail"}
            and set(item["radiology"]) == {"text"}
            for item in reports["radiology"]
        ):
            raise ExtractionError("A radiology result has the wrong fixed attributes")
        if not all(
            set(detail) == {"field_name", "field_value", "field_ordinal"}
            for item in reports["radiology"]
            for detail in item["radiology_detail"]
        ):
            raise ExtractionError("A radiology detail object has the wrong fixed attributes")
        if not all(
            set(item)
            == {"drug", "prod_strength", "form_rx", "dose_val_rx", "dose_unit_rx", "route", "doses_per_24_hrs"}
            for item in prescriptions
        ):
            raise ExtractionError("A prescription has the wrong fixed attributes")
        if not all(set(item) == {"procedure_name", "icd_code", "icd_version"} for item in procedures):
            raise ExtractionError("A procedure has the wrong fixed attributes")


def write_output(frame: pd.DataFrame, output: Path) -> None:
    parent = output.parent
    if not parent.exists():
        raise FileNotFoundError(f"Output directory does not exist: {parent}")
    frame.to_csv(output, index=False, encoding="utf-8", lineterminator="\n")
