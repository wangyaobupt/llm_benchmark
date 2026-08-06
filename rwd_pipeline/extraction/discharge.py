from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Mapping, Optional, Sequence, Set, Tuple

import pandas as pd

from .common import (
    TEXT_CHUNK_SIZE,
    clean_id_series,
    clean_string,
    filter_candidate_rows,
    iter_csv_chunks,
    parse_datetime,
    parse_number,
    table_path,
    validate_subject_match,
)


KNOWN_HEADINGS = [
    "Chief Complaint",
    "History of Present Illness",
    "Past Medical History",
    "Social History",
    "Family History",
    "Physical Exam",
    "Pertinent Results",
    "Studies",
    "Brief Hospital Course",
    "Medications on Admission",
    "Discharge Medications",
    "Discharge Diagnosis",
    "Discharge Condition",
    "Discharge Instructions",
    "Follow-up Instructions",
    "Followup Instructions",
    "Follow Up Instructions",
]

SECTION_ALIASES = {
    "chief_complaint": ["Chief Complaint"],
    "history_of_present_illness": ["History of Present Illness"],
    "past_medical_history": ["Past Medical History"],
    "medications_on_admission": ["Medications on Admission"],
    "discharge_record": [
        "Follow-up Instructions",
        "Followup Instructions",
        "Follow Up Instructions",
    ],
}

_HEADING_PATTERN = re.compile(
    r"^[ \t]*(?P<title>"
    + "|".join(re.escape(title) for title in sorted(KNOWN_HEADINGS, key=len, reverse=True))
    + r")[ \t]*:?[ \t]*$",
    flags=re.IGNORECASE | re.MULTILINE,
)


def extract_section(text: str, aliases: Sequence[str]) -> Optional[str]:
    normalized_text = text.replace("\r\n", "\n").replace("\r", "\n")
    alias_set = {alias.casefold() for alias in aliases}
    headings = list(_HEADING_PATTERN.finditer(normalized_text))
    for index, heading in enumerate(headings):
        if heading.group("title").casefold() not in alias_set:
            continue
        end = headings[index + 1].start() if index + 1 < len(headings) else len(normalized_text)
        content = normalized_text[heading.end() : end].strip()
        if content:
            return content
    return None


def parse_discharge_sections(text: str) -> Dict[str, Optional[str]]:
    sections = {
        field: extract_section(text, aliases)
        for field, aliases in SECTION_ALIASES.items()
    }
    discharge_record = sections["discharge_record"]
    if discharge_record is not None:
        compact = re.sub(r"\s+", "", discharge_record)
        if re.fullmatch(r"_+", compact):
            sections["discharge_record"] = None
    return sections


def _descending_timestamp(value: object) -> int:
    timestamp = parse_datetime(value)
    return -(2**63) if pd.isna(timestamp) else int(timestamp.value)


def _selection_key(row: Mapping[str, object]) -> Tuple[float, int, int, int, str]:
    note_seq = parse_number(row["note_seq"])
    storetime = parse_datetime(row["storetime"])
    return (
        float("-inf") if note_seq is None else note_seq,
        _descending_timestamp(row["charttime"]),
        0 if pd.isna(storetime) else 1,
        _descending_timestamp(storetime),
        clean_string(row["note_id"]) or "",
    )


def extract_discharge_fields(
    data_root: Path,
    candidates: pd.DataFrame,
    eligible_hadm_ids: Set[str],
) -> Tuple[Set[str], Dict[str, Dict[str, Optional[str]]]]:
    candidate_ids = set(candidates["hadm_id"])
    admission_subjects = dict(zip(candidates["hadm_id"], candidates["subject_id"]))
    best: Dict[str, Tuple[Tuple[float, int, int, int, str], Dict[str, Optional[str]]]] = {}

    path = table_path(data_root, "note", "discharge.csv")
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
        validate_subject_match(filtered, admission_subjects, "discharge")
        filtered["note_type"] = filtered["note_type"].astype("string").str.strip()
        filtered = filtered.loc[
            filtered["hadm_id"].isin(eligible_hadm_ids)
            & filtered["note_type"].eq("DS")
            & filtered["text"].notna()
        ].copy()
        filtered["charttime"] = pd.to_datetime(filtered["charttime"], errors="coerce")
        filtered["storetime"] = pd.to_datetime(filtered["storetime"], errors="coerce")
        for row in filtered.to_dict("records"):
            text = clean_string(row["text"])
            if text is None:
                continue
            sections = parse_discharge_sections(text)
            if sections["chief_complaint"] is None:
                continue
            hadm_id = str(row["hadm_id"])
            key = _selection_key(row)
            if hadm_id not in best or key > best[hadm_id][0]:
                best[hadm_id] = (key, sections)

    selected_ids = set(best)
    return selected_ids, {hadm_id: value[1] for hadm_id, value in best.items()}
