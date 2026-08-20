"""Discharge-summary section parser. One selected DS feeds every chapter field."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

DS_SECTION_TITLES: tuple[str, ...] = (
    "Chief Complaint",
    "Major Surgical or Invasive Procedure",
    "History of Present Illness",
    "Past Medical History",
    "Social History",
    "Family History",
    "Allergies",
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
)

DS_FIELDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("chief_complaint", ("Chief Complaint",)),
    ("history_of_present_illness", ("History of Present Illness",)),
    ("past_medical_history", ("Past Medical History",)),
    ("social_history", ("Social History",)),
    ("medications_on_admission", ("Medications on Admission",)),
    ("allergies", ("Allergies",)),
    ("physical_exam", ("Physical Exam",)),
    ("brief_hospital_course", ("Brief Hospital Course",)),
    ("discharge_medications", ("Discharge Medications",)),
    ("discharge_condition", ("Discharge Condition",)),
    ("discharge_record", ("Discharge Instructions",)),
    ("discharge_diagnosis", ("Discharge Diagnosis",)),
    (
        "followup_instructions",
        ("Follow-up Instructions", "Followup Instructions", "Follow Up Instructions"),
    ),
)

_TITLE_RE = re.compile(
    r"^\s*(" + "|".join(re.escape(title) for title in DS_SECTION_TITLES) + r")\s*:?\s*$",
    re.MULTILINE | re.IGNORECASE,
)
_UNUSABLE_FOLLOWUP_RE = re.compile(r"^(_+\s*)+$")


def normalize_text(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def parse_ds_sections(text: str) -> dict[str, str | None]:
    normalized = normalize_text(text)
    matches = list(_TITLE_RE.finditer(normalized))
    spans: dict[str, tuple[int, int]] = {}
    for index, match in enumerate(matches):
        title = match.group(1).lower()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
        if title not in spans:
            spans[title] = (start, end)

    parsed: dict[str, str | None] = {}
    for field, variants in DS_FIELDS:
        parsed[field] = None
        for variant in variants:
            span = spans.get(variant.lower())
            if span is None:
                continue
            content = normalized[span[0] : span[1]].strip()
            parsed[field] = content or None
            break
    return parsed


def followup_unusable(text: str | None) -> bool:
    if text is None:
        return True
    stripped = text.strip()
    if not stripped:
        return True
    return _UNUSABLE_FOLLOWUP_RE.fullmatch(stripped) is not None


@dataclass(frozen=True)
class SelectedDischarge:
    note_id: str
    note_seq: str
    charttime: str | None
    storetime: str | None
    text: str
    sections: dict[str, str | None]
    followup_unusable: bool


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def select_ds(notes: list[dict[str, Any]]) -> SelectedDischarge | None:
    candidates: list[tuple[tuple[Any, ...], dict[str, Any], dict[str, str | None]]] = []
    for note in notes:
        if str(note.get("note_type") or "").strip().upper() != "DS":
            continue
        text = note.get("text") or ""
        if not str(text).strip():
            continue
        sections = parse_ds_sections(str(text))
        chief = sections.get("chief_complaint")
        if not chief:
            continue
        note_seq = _as_int(note.get("note_seq"))
        charttime = str(note.get("charttime") or "").strip()
        storetime = str(note.get("storetime") or "").strip()
        note_id = str(note.get("note_id") or "")
        sort_key = (note_seq, charttime, storetime, note_id)
        candidates.append((sort_key, note, sections))
    if not candidates:
        return None
    _, note, sections = max(candidates, key=lambda item: item[0])
    text = normalize_text(str(note.get("text") or ""))
    return SelectedDischarge(
        note_id=str(note.get("note_id") or ""),
        note_seq=str(note.get("note_seq") or "").strip(),
        charttime=str(note.get("charttime") or "").strip() or None,
        storetime=str(note.get("storetime") or "").strip() or None,
        text=text,
        sections=sections,
        followup_unusable=followup_unusable(sections.get("followup_instructions")),
    )
