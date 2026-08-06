from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Mapping, Set, Tuple

import pandas as pd

from .common import (
    STRUCTURED_CHUNK_SIZE,
    ExtractionError,
    clean_id_series,
    clean_string,
    filter_candidate_rows,
    is_missing,
    iter_csv_chunks,
    json_scalar,
    number_ascending,
    parse_integer,
    string_ascending,
    table_path,
    time_ascending,
    validate_subject_match,
)


def extract_investigation_orders(
    data_root: Path,
    candidates: pd.DataFrame,
    eligible_hadm_ids: Set[str],
) -> Dict[str, List[dict]]:
    candidate_ids = set(candidates["hadm_id"])
    admission_subjects = dict(zip(candidates["hadm_id"], candidates["subject_id"]))
    retained = []
    path = table_path(data_root, "hosp", "poe.csv")
    for chunk in iter_csv_chunks(
        path,
        [
            "poe_id",
            "poe_seq",
            "subject_id",
            "hadm_id",
            "ordertime",
            "order_type",
            "order_subtype",
            "transaction_type",
        ],
        STRUCTURED_CHUNK_SIZE,
        dtype={
            "poe_id": "string",
            "poe_seq": "string",
            "subject_id": "string",
            "hadm_id": "string",
            "ordertime": "string",
            "order_type": "string",
            "order_subtype": "string",
            "transaction_type": "string",
        },
    ):
        filtered = filter_candidate_rows(chunk, candidate_ids)
        validate_subject_match(filtered, admission_subjects, "poe")
        filtered["transaction_type"] = filtered["transaction_type"].astype("string").str.strip()
        filtered["order_type"] = filtered["order_type"].astype("string").str.strip()
        filtered = filtered.loc[
            filtered["hadm_id"].isin(eligible_hadm_ids)
            & filtered["transaction_type"].eq("New")
            & filtered["order_type"].isin(["Lab", "Imaging"])
        ].copy()
        if not filtered.empty:
            filtered["poe_id"] = clean_id_series(filtered["poe_id"])
            filtered["poe_seq"] = clean_id_series(filtered["poe_seq"])
            filtered = filtered.dropna(subset=["poe_id", "poe_seq"])
            retained.append(filtered)

    if not retained:
        return {}
    orders = pd.concat(retained, ignore_index=True)
    orders["ordertime"] = pd.to_datetime(orders["ordertime"], errors="coerce")
    orders["_key"] = list(zip(orders["poe_id"], orders["poe_seq"]))

    parent_subjects: Dict[Tuple[str, str], str] = {}
    for row in orders.to_dict("records"):
        key = row["_key"]
        subject = str(row["subject_id"])
        existing = parent_subjects.get(key)
        if existing is not None and existing != subject:
            raise ExtractionError(f"poe key {key} belongs to multiple subjects")
        parent_subjects[key] = subject

    details: Dict[Tuple[str, str], List[dict]] = defaultdict(list)
    detail_path = table_path(data_root, "hosp", "poe_detail.csv")
    parent_keys = set(parent_subjects)
    for chunk in iter_csv_chunks(
        detail_path,
        ["poe_id", "poe_seq", "subject_id", "field_name", "field_value"],
        STRUCTURED_CHUNK_SIZE,
        dtype={
            "poe_id": "string",
            "poe_seq": "string",
            "subject_id": "string",
            "field_name": "string",
            "field_value": "string",
        },
    ):
        chunk["poe_id"] = clean_id_series(chunk["poe_id"])
        chunk["poe_seq"] = clean_id_series(chunk["poe_seq"])
        chunk["subject_id"] = clean_id_series(chunk["subject_id"])
        chunk["_key"] = list(zip(chunk["poe_id"], chunk["poe_seq"]))
        filtered = chunk.loc[chunk["_key"].isin(parent_keys)]
        for row in filtered.to_dict("records"):
            key = row["_key"]
            if row["subject_id"] != parent_subjects[key]:
                raise ExtractionError(
                    f"poe_detail subject conflict at source row {int(row['_source_row'])} for key {key}"
                )
            details[key].append(
                {
                    "field_name": clean_string(row["field_name"]),
                    "field_value": clean_string(row["field_value"]),
                    "_source_row": int(row["_source_row"]),
                }
            )

    best_by_visit: Dict[str, Dict[tuple, Tuple[tuple, dict]]] = defaultdict(dict)
    for row in orders.to_dict("records"):
        key = row["_key"]
        sorted_details = sorted(
            details.get(key, []),
            key=lambda item: (string_ascending(item["field_name"]), item["_source_row"]),
        )
        output_details = [
            {"field_name": item["field_name"], "field_value": item["field_value"]}
            for item in sorted_details
        ]
        order_type = clean_string(row["order_type"])
        order_subtype = clean_string(row["order_subtype"])
        identity = (
            order_type,
            order_subtype,
            tuple((item["field_name"], item["field_value"]) for item in output_details),
        )
        selection = (
            time_ascending(row["ordertime"]),
            string_ascending(row["poe_id"]),
            number_ascending(row["poe_seq"]),
            int(row["_source_row"]),
        )
        output = {
            "order_type": order_type,
            "order_subtype": order_subtype,
            "poe_detail": output_details,
        }
        hadm_id = str(row["hadm_id"])
        previous = best_by_visit[hadm_id].get(identity)
        if previous is None or selection < previous[0]:
            best_by_visit[hadm_id][identity] = (selection, output)

    return {
        hadm_id: [item[1] for item in sorted(values.values(), key=lambda item: item[0])]
        for hadm_id, values in best_by_visit.items()
    }


def _load_lab_dictionary(data_root: Path) -> Dict[str, dict]:
    path = table_path(data_root, "hosp", "d_labitems.csv")
    frame = pd.read_csv(
        path,
        usecols=["itemid", "label", "fluid", "category"],
        dtype={"itemid": "string", "label": "string", "fluid": "string", "category": "string"},
    )
    frame["itemid"] = clean_id_series(frame["itemid"])
    counts = frame.dropna(subset=["itemid"]).groupby("itemid").size()
    unique = set(counts[counts.eq(1)].index)
    result = {}
    for row in frame.loc[frame["itemid"].isin(unique)].to_dict("records"):
        result[str(row["itemid"])] = {
            "itemid": parse_integer(row["itemid"]),
            "label": clean_string(row["label"]),
            "fluid": clean_string(row["fluid"]),
            "category": clean_string(row["category"]),
        }
    return result


def extract_laboratory_results(
    data_root: Path,
    candidates: pd.DataFrame,
    eligible_hadm_ids: Set[str],
) -> Dict[str, List[dict]]:
    lab_dictionary = _load_lab_dictionary(data_root)
    candidate_ids = set(candidates["hadm_id"])
    admission_subjects = dict(zip(candidates["hadm_id"], candidates["subject_id"]))
    best: Dict[Tuple[str, str], Tuple[tuple, dict]] = {}

    path = table_path(data_root, "hosp", "labevents.csv")
    for chunk in iter_csv_chunks(
        path,
        [
            "labevent_id",
            "subject_id",
            "hadm_id",
            "itemid",
            "charttime",
            "storetime",
            "value",
            "valuenum",
            "valueuom",
            "ref_range_lower",
            "ref_range_upper",
            "flag",
            "comments",
        ],
        STRUCTURED_CHUNK_SIZE,
        dtype={
            "subject_id": "string",
            "hadm_id": "string",
            "itemid": "string",
            "charttime": "string",
            "storetime": "string",
            "value": "string",
            "valueuom": "string",
            "flag": "string",
            "comments": "string",
        },
    ):
        filtered = filter_candidate_rows(chunk, candidate_ids)
        validate_subject_match(filtered, admission_subjects, "labevents")
        filtered = filtered.loc[filtered["hadm_id"].isin(eligible_hadm_ids)].copy()
        filtered["itemid"] = clean_id_series(filtered["itemid"])
        filtered = filtered.loc[filtered["itemid"].isin(lab_dictionary)]
        filtered["_value_clean"] = filtered["value"].astype("string").str.strip().replace("", pd.NA)
        filtered["_comments_clean"] = filtered["comments"].astype("string").str.strip().replace("", pd.NA)
        filtered = filtered.loc[
            filtered["_value_clean"].notna()
            | filtered["valuenum"].notna()
            | filtered["_comments_clean"].notna()
        ].copy()
        filtered["charttime"] = pd.to_datetime(filtered["charttime"], errors="coerce")
        filtered["storetime"] = pd.to_datetime(filtered["storetime"], errors="coerce")
        filtered["_labevent_num"] = pd.to_numeric(filtered["labevent_id"], errors="coerce")
        filtered = filtered.sort_values(
            ["hadm_id", "itemid", "charttime", "storetime", "_labevent_num", "_source_row"],
            kind="stable",
            na_position="last",
        ).drop_duplicates(["hadm_id", "itemid"], keep="first")
        for row in filtered.to_dict("records"):
            value = clean_string(row["_value_clean"])
            comments = clean_string(row["_comments_clean"])
            key = (str(row["hadm_id"]), str(row["itemid"]))
            selection = (
                time_ascending(row["charttime"]),
                time_ascending(row["storetime"]),
                number_ascending(row["labevent_id"]),
                int(row["_source_row"]),
            )
            output = {
                "d_labitems": dict(lab_dictionary[str(row["itemid"])]),
                "labevents": {
                    "value": value,
                    "valuenum": json_scalar(row["valuenum"]),
                    "valueuom": clean_string(row["valueuom"]),
                    "ref_range_lower": json_scalar(row["ref_range_lower"]),
                    "ref_range_upper": json_scalar(row["ref_range_upper"]),
                    "flag": clean_string(row["flag"]),
                    "comments": comments,
                },
            }
            previous = best.get(key)
            if previous is None or selection < previous[0]:
                best[key] = (selection, output)

    grouped: Dict[str, List[Tuple[tuple, str, dict]]] = defaultdict(list)
    for (hadm_id, itemid), (selection, output) in best.items():
        grouped[hadm_id].append((selection, itemid, output))
    return {
        hadm_id: [item[2] for item in sorted(items, key=lambda item: (item[0], item[1]))]
        for hadm_id, items in grouped.items()
    }
