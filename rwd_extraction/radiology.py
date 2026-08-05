from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

import pandas as pd

from .common import (
    STRUCTURED_CHUNK_SIZE,
    TEXT_CHUNK_SIZE,
    ExtractionError,
    clean_id_series,
    clean_string,
    filter_candidate_rows,
    iter_csv_chunks,
    json_scalar,
    normalize_name,
    number_ascending,
    string_ascending,
    table_path,
    time_ascending,
    validate_subject_match,
)


def extract_radiology_reports(
    data_root: Path,
    candidates: pd.DataFrame,
    eligible_hadm_ids: Set[str],
) -> Dict[str, List[dict]]:
    candidate_ids = set(candidates["hadm_id"])
    admission_subjects = dict(zip(candidates["hadm_id"], candidates["subject_id"]))
    notes: Dict[str, dict] = {}

    path = table_path(data_root, "note", "radiology.csv")
    for chunk in iter_csv_chunks(
        path,
        ["note_id", "subject_id", "hadm_id", "note_type", "note_seq", "charttime", "storetime", "text"],
        TEXT_CHUNK_SIZE,
        dtype={
            "note_id": "string",
            "subject_id": "string",
            "hadm_id": "string",
            "note_type": "string",
            "charttime": "string",
            "storetime": "string",
            "text": "string",
        },
    ):
        filtered = filter_candidate_rows(chunk, candidate_ids)
        validate_subject_match(filtered, admission_subjects, "radiology")
        filtered["note_type"] = filtered["note_type"].astype("string").str.strip()
        filtered["note_id"] = clean_id_series(filtered["note_id"])
        filtered = filtered.loc[
            filtered["hadm_id"].isin(eligible_hadm_ids)
            & filtered["note_type"].eq("RR")
            & filtered["note_id"].notna()
        ].copy()
        filtered["charttime"] = pd.to_datetime(filtered["charttime"], errors="coerce")
        filtered["storetime"] = pd.to_datetime(filtered["storetime"], errors="coerce")
        for row in filtered.to_dict("records"):
            note_id = str(row["note_id"])
            if note_id in notes:
                raise ExtractionError(f"radiology contains duplicate note_id={note_id}")
            notes[note_id] = row

    if not notes:
        return {}

    details: Dict[str, List[dict]] = defaultdict(list)
    exam_names: Dict[str, Set[str]] = defaultdict(set)
    detail_path = table_path(data_root, "note", "radiology_detail.csv")
    note_ids = set(notes)
    for chunk in iter_csv_chunks(
        detail_path,
        ["note_id", "subject_id", "field_name", "field_value", "field_ordinal"],
        STRUCTURED_CHUNK_SIZE,
        dtype={
            "note_id": "string",
            "subject_id": "string",
            "field_name": "string",
            "field_value": "string",
        },
    ):
        chunk["note_id"] = clean_id_series(chunk["note_id"])
        chunk["subject_id"] = clean_id_series(chunk["subject_id"])
        filtered = chunk.loc[chunk["note_id"].isin(note_ids)]
        for row in filtered.to_dict("records"):
            note_id = str(row["note_id"])
            if row["subject_id"] != notes[note_id]["subject_id"]:
                raise ExtractionError(
                    f"radiology_detail subject conflict at source row {int(row['_source_row'])} "
                    f"for note_id={note_id}"
                )
            field_name = clean_string(row["field_name"])
            field_value = clean_string(row["field_value"])
            details[note_id].append(
                {
                    "field_name": field_name,
                    "field_value": field_value,
                    "field_ordinal": json_scalar(row["field_ordinal"]),
                    "_source_row": int(row["_source_row"]),
                }
            )
            if field_name == "exam_name" and field_value is not None:
                normalized = normalize_name(field_value)
                if normalized is not None:
                    exam_names[note_id].add(normalized)

    best_by_exam: Dict[Tuple[str, str], Tuple[tuple, str]] = {}
    note_selection: Dict[str, tuple] = {}
    for note_id, note in notes.items():
        selection = (
            time_ascending(note["charttime"]),
            time_ascending(note["storetime"]),
            number_ascending(note["note_seq"]),
            string_ascending(note_id),
        )
        note_selection[note_id] = selection
        hadm_id = str(note["hadm_id"])
        for exam_name in exam_names.get(note_id, set()):
            key = (hadm_id, exam_name)
            previous = best_by_exam.get(key)
            if previous is None or selection < previous[0]:
                best_by_exam[key] = (selection, note_id)

    selected_by_visit: Dict[str, Set[str]] = defaultdict(set)
    for (hadm_id, _), (_, note_id) in best_by_exam.items():
        selected_by_visit[hadm_id].add(note_id)

    result: Dict[str, List[dict]] = {}
    for hadm_id, selected_note_ids in selected_by_visit.items():
        ordered_notes = sorted(selected_note_ids, key=lambda note_id: note_selection[note_id])
        output = []
        for note_id in ordered_notes:
            ordered_details = sorted(
                details.get(note_id, []),
                key=lambda item: (
                    number_ascending(item["field_ordinal"]),
                    string_ascending(item["field_name"]),
                    item["_source_row"],
                ),
            )
            output.append(
                {
                    "radiology": {"text": clean_string(notes[note_id]["text"])},
                    "radiology_detail": [
                        {
                            "field_name": item["field_name"],
                            "field_value": item["field_value"],
                            "field_ordinal": item["field_ordinal"],
                        }
                        for item in ordered_details
                    ],
                }
            )
        result[hadm_id] = output
    return result
