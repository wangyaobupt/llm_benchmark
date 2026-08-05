from __future__ import annotations

from pathlib import Path
from typing import Dict, Mapping, Set, Tuple

import pandas as pd

from .common import (
    STRUCTURED_CHUNK_SIZE,
    ExtractionError,
    clean_id_series,
    clean_string,
    exact_dictionary,
    filter_candidate_rows,
    iter_csv_chunks,
    normalize_name,
    parse_integer,
    table_path,
    validate_subject_match,
)


def load_candidates(data_root: Path, limit: int) -> pd.DataFrame:
    if limit <= 0:
        raise ValueError("--limit must be greater than zero")

    path = table_path(data_root, "hosp", "admissions.csv")
    admissions = pd.read_csv(
        path,
        usecols=["subject_id", "hadm_id", "admittime"],
        dtype={"subject_id": "string", "hadm_id": "string", "admittime": "string"},
    )
    admissions["subject_id"] = clean_id_series(admissions["subject_id"])
    admissions["hadm_id"] = clean_id_series(admissions["hadm_id"])

    if admissions["subject_id"].isna().any() or admissions["hadm_id"].isna().any():
        raise ExtractionError("admissions contains an empty subject_id or hadm_id")
    duplicates = admissions["hadm_id"].duplicated(keep=False)
    if duplicates.any():
        duplicate = admissions.loc[duplicates, "hadm_id"].iloc[0]
        raise ExtractionError(f"admissions contains duplicate hadm_id={duplicate}")

    candidates = admissions.head(limit).copy()
    candidates["_source_order"] = range(len(candidates))
    return candidates


def admission_subject_map(candidates: pd.DataFrame) -> Dict[str, str]:
    return dict(zip(candidates["hadm_id"], candidates["subject_id"]))


def apply_demographics(data_root: Path, candidates: pd.DataFrame) -> pd.DataFrame:
    path = table_path(data_root, "hosp", "patients.csv")
    patients = pd.read_csv(
        path,
        usecols=["subject_id", "gender", "anchor_age", "anchor_year"],
        dtype={"subject_id": "string", "gender": "string"},
    )
    patients["subject_id"] = clean_id_series(patients["subject_id"])
    candidate_subjects = set(candidates["subject_id"])
    patients = patients.loc[patients["subject_id"].isin(candidate_subjects)].copy()

    counts = patients.groupby("subject_id", dropna=False).size()
    unique_subjects = set(counts[counts.eq(1)].index)
    patients = patients.loc[patients["subject_id"].isin(unique_subjects)].copy()
    patients["sex"] = patients["gender"].astype("string").str.strip()
    patients["anchor_age"] = pd.to_numeric(patients["anchor_age"], errors="coerce")
    patients["anchor_year"] = pd.to_numeric(patients["anchor_year"], errors="coerce")

    merged = candidates.merge(
        patients[["subject_id", "sex", "anchor_age", "anchor_year"]],
        on="subject_id",
        how="left",
        validate="many_to_one",
    )
    admitted = pd.to_datetime(merged["admittime"], errors="coerce")
    age = merged["anchor_age"] + admitted.dt.year - merged["anchor_year"]
    valid_integer_age = age.notna() & age.mod(1).eq(0)
    merged["age_at_encounter"] = age.where(valid_integer_age).astype("Int64")

    valid = (
        merged["age_at_encounter"].ge(18)
        & merged["sex"].isin(["M", "F"])
        & merged["anchor_age"].notna()
        & merged["anchor_year"].notna()
        & admitted.notna()
    )
    return merged.loc[valid, candidates.columns.tolist() + ["age_at_encounter", "sex"]].copy()


def extract_diagnoses(
    data_root: Path,
    candidates: pd.DataFrame,
    demographic_hadm_ids: Set[str],
) -> Tuple[Set[str], Dict[str, Dict[str, object]]]:
    dictionary_path = table_path(data_root, "hosp", "d_icd_diagnoses.csv")
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
    subjects = admission_subject_map(candidates)
    retained = []
    path = table_path(data_root, "hosp", "diagnoses_icd.csv")
    for chunk in iter_csv_chunks(
        path,
        ["subject_id", "hadm_id", "seq_num", "icd_code", "icd_version"],
        STRUCTURED_CHUNK_SIZE,
        dtype={
            "subject_id": "string",
            "hadm_id": "string",
            "icd_code": "string",
            "icd_version": "string",
        },
    ):
        filtered = filter_candidate_rows(chunk, candidate_ids)
        validate_subject_match(filtered, subjects, "diagnoses_icd")
        if not filtered.empty:
            retained.append(filtered)

    if retained:
        diagnoses = pd.concat(retained, ignore_index=True)
    else:
        diagnoses = pd.DataFrame(
            columns=["subject_id", "hadm_id", "seq_num", "icd_code", "icd_version", "_source_row"]
        )
    diagnoses["icd_code"] = clean_id_series(diagnoses["icd_code"])
    diagnoses["icd_version"] = clean_id_series(diagnoses["icd_version"])
    diagnoses["_seq"] = pd.to_numeric(diagnoses["seq_num"], errors="coerce")
    diagnoses["_version_num"] = pd.to_numeric(diagnoses["icd_version"], errors="coerce")
    diagnoses["_dict_key"] = list(zip(diagnoses["icd_code"], diagnoses["icd_version"]))
    diagnoses["_title"] = diagnoses["_dict_key"].map(dictionary)
    diagnoses["_valid"] = (
        diagnoses["icd_code"].notna()
        & diagnoses["_version_num"].isin([9, 10])
        & diagnoses["_title"].notna()
    )

    eligible: Set[str] = set()
    results: Dict[str, Dict[str, object]] = {}
    demographic_diagnoses = diagnoses.loc[
        diagnoses["hadm_id"].isin(demographic_hadm_ids)
    ]
    for hadm_id, group in demographic_diagnoses.groupby("hadm_id", sort=False):
        group = group.copy()
        valid_group = group.loc[group["_valid"]].copy()
        primary_rows = group.loc[group["_seq"].eq(1)]
        if valid_group.empty or len(primary_rows) != 1:
            continue
        primary = primary_rows.iloc[0]
        if not bool(primary["_valid"]):
            continue

        primary_name = str(primary["_title"]).strip()
        other = valid_group.loc[valid_group["_seq"].gt(1)].copy()
        other = other.sort_values(
            ["_seq", "_version_num", "icd_code", "_source_row"],
            kind="stable",
            na_position="last",
        )
        primary_normalized = normalize_name(primary_name)
        seen = set()
        other_names = []
        for row in other.to_dict("records"):
            name = clean_string(row["_title"])
            normalized = normalize_name(name)
            if name is None or normalized is None or normalized == primary_normalized or normalized in seen:
                continue
            seen.add(normalized)
            other_names.append(name)

        version = parse_integer(primary["_version_num"])
        results[hadm_id] = {
            "primary_icd_code": str(primary["icd_code"]),
            "primary_diagnosis_name": primary_name,
            "primary_icd_version": "ICD-9-CM" if version == 9 else "ICD-10-CM",
            "other_diagnoses": other_names,
        }
        eligible.add(hadm_id)

    return eligible, results
