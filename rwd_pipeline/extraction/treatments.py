from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

import pandas as pd

from .common import (
    STRUCTURED_CHUNK_SIZE,
    clean_id_series,
    clean_string,
    exact_dictionary,
    filter_candidate_rows,
    iter_csv_chunks,
    json_scalar,
    normalize_name,
    number_ascending,
    parse_integer,
    string_ascending,
    table_path,
    time_ascending,
    validate_subject_match,
)


def extract_prescriptions(
    data_root: Path,
    candidates: pd.DataFrame,
    eligible_hadm_ids: Set[str],
) -> Dict[str, List[dict]]:
    candidate_ids = set(candidates["hadm_id"])
    admission_subjects = dict(zip(candidates["hadm_id"], candidates["subject_id"]))
    best: Dict[Tuple[str, str], Tuple[tuple, dict]] = {}

    path = table_path(data_root, "hosp", "prescriptions.csv")
    for chunk in iter_csv_chunks(
        path,
        [
            "subject_id",
            "hadm_id",
            "pharmacy_id",
            "poe_id",
            "poe_seq",
            "starttime",
            "drug_type",
            "drug",
            "prod_strength",
            "form_rx",
            "dose_val_rx",
            "dose_unit_rx",
            "route",
            "doses_per_24_hrs",
        ],
        STRUCTURED_CHUNK_SIZE,
        dtype={
            "subject_id": "string",
            "hadm_id": "string",
            "pharmacy_id": "string",
            "poe_id": "string",
            "poe_seq": "string",
            "starttime": "string",
            "drug_type": "string",
            "drug": "string",
            "prod_strength": "string",
            "form_rx": "string",
            "dose_val_rx": "string",
            "dose_unit_rx": "string",
            "route": "string",
        },
    ):
        filtered = filter_candidate_rows(chunk, candidate_ids)
        validate_subject_match(filtered, admission_subjects, "prescriptions")
        filtered["drug_type"] = filtered["drug_type"].astype("string").str.strip()
        filtered = filtered.loc[
            filtered["hadm_id"].isin(eligible_hadm_ids)
            & filtered["drug_type"].eq("MAIN")
        ].copy()
        filtered["drug"] = filtered["drug"].astype("string").str.strip().replace("", pd.NA)
        filtered["_normalized_drug"] = (
            filtered["drug"].str.replace(r"\s+", " ", regex=True).str.casefold()
        )
        filtered = filtered.dropna(subset=["_normalized_drug"])
        filtered["starttime"] = pd.to_datetime(filtered["starttime"], errors="coerce")
        filtered["_poe_seq_num"] = pd.to_numeric(filtered["poe_seq"], errors="coerce")
        filtered = filtered.sort_values(
            [
                "hadm_id",
                "_normalized_drug",
                "starttime",
                "pharmacy_id",
                "poe_id",
                "_poe_seq_num",
                "_source_row",
            ],
            kind="stable",
            na_position="last",
        ).drop_duplicates(["hadm_id", "_normalized_drug"], keep="first")
        for row in filtered.to_dict("records"):
            drug = clean_string(row["drug"])
            normalized = clean_string(row["_normalized_drug"])
            if drug is None or normalized is None:
                continue
            selection = (
                time_ascending(row["starttime"]),
                string_ascending(row["pharmacy_id"]),
                string_ascending(row["poe_id"]),
                number_ascending(row["poe_seq"]),
                int(row["_source_row"]),
            )
            output = {
                "drug": drug,
                "prod_strength": clean_string(row["prod_strength"]),
                "form_rx": clean_string(row["form_rx"]),
                "dose_val_rx": clean_string(row["dose_val_rx"]),
                "dose_unit_rx": clean_string(row["dose_unit_rx"]),
                "route": clean_string(row["route"]),
                "doses_per_24_hrs": json_scalar(row["doses_per_24_hrs"]),
            }
            key = (str(row["hadm_id"]), normalized)
            previous = best.get(key)
            if previous is None or selection < previous[0]:
                best[key] = (selection, output)

    grouped: Dict[str, List[Tuple[tuple, dict]]] = defaultdict(list)
    for (hadm_id, _), selected in best.items():
        grouped[hadm_id].append(selected)
    return {
        hadm_id: [item[1] for item in sorted(items, key=lambda item: item[0])]
        for hadm_id, items in grouped.items()
    }


def extract_procedures(
    data_root: Path,
    candidates: pd.DataFrame,
    eligible_hadm_ids: Set[str],
) -> Dict[str, List[dict]]:
    dictionary_path = table_path(data_root, "hosp", "d_icd_procedures.csv")
    dictionary_frame = pd.read_csv(
        dictionary_path,
        usecols=["icd_code", "icd_version", "long_title"],
        dtype={"icd_code": "string", "icd_version": "string", "long_title": "string"},
    )
    dictionary = exact_dictionary(
        dictionary_frame,
        ["icd_code", "icd_version"],
        "long_title",
    )

    candidate_ids = set(candidates["hadm_id"])
    admission_subjects = dict(zip(candidates["hadm_id"], candidates["subject_id"]))
    best: Dict[Tuple[str, str, str], Tuple[tuple, dict]] = {}
    path = table_path(data_root, "hosp", "procedures_icd.csv")
    for chunk in iter_csv_chunks(
        path,
        ["subject_id", "hadm_id", "seq_num", "chartdate", "icd_code", "icd_version"],
        STRUCTURED_CHUNK_SIZE,
        dtype={
            "subject_id": "string",
            "hadm_id": "string",
            "chartdate": "string",
            "icd_code": "string",
            "icd_version": "string",
        },
    ):
        filtered = filter_candidate_rows(chunk, candidate_ids)
        validate_subject_match(filtered, admission_subjects, "procedures_icd")
        filtered = filtered.loc[filtered["hadm_id"].isin(eligible_hadm_ids)].copy()
        filtered["icd_code"] = clean_id_series(filtered["icd_code"])
        filtered["icd_version"] = clean_id_series(filtered["icd_version"])
        for row in filtered.to_dict("records"):
            code = clean_string(row["icd_code"])
            version_text = clean_string(row["icd_version"])
            version = parse_integer(version_text)
            if code is None or version not in (9, 10):
                continue
            title = dictionary.get((code, version_text))
            if title is None:
                continue
            selection = (
                time_ascending(row["chartdate"]),
                number_ascending(row["seq_num"]),
                version,
                code,
                int(row["_source_row"]),
            )
            output = {
                "procedure_name": title.strip(),
                "icd_code": code,
                "icd_version": "ICD-9-PCS" if version == 9 else "ICD-10-PCS",
            }
            key = (str(row["hadm_id"]), code, version_text)
            previous = best.get(key)
            if previous is None or selection < previous[0]:
                best[key] = (selection, output)

    grouped: Dict[str, List[Tuple[tuple, dict]]] = defaultdict(list)
    for (hadm_id, _, _), selected in best.items():
        grouped[hadm_id].append(selected)
    return {
        hadm_id: [item[1] for item in sorted(items, key=lambda item: item[0])]
        for hadm_id, items in grouped.items()
    }
