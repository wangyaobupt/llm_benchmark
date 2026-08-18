"""Build a deterministic encounter clock without coalescing clinical times."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping


REASON_ORIGIN_MISSING = "ENCOUNTER_ORIGIN_MISSING"
REASON_ORIGIN_AMBIGUOUS = "ENCOUNTER_ORIGIN_AMBIGUOUS"
REASON_TIME_INVERTED = "ENCOUNTER_TIME_INVERTED"


def _time(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise ValueError(f"unsupported encounter time type: {type(value).__name__}")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _iso(value: datetime | None) -> str | None:
    return value.isoformat(sep=" ") if value is not None else None


def _ref(row: Mapping[str, Any], table: str, index: int) -> str:
    return str(row.get("source_ref") or f"{table}[{index}]")


@dataclass(frozen=True)
class EncounterClockResult:
    rows: list[dict[str, Any]]
    exclusions: list[dict[str, Any]]
    metrics: dict[str, int]


def _row_times(row: Mapping[str, Any], table: str, index: int) -> dict[str, Any]:
    return {
        "ed_arrival_time": _iso(_time(row.get("intime"))) if table == "edstays" else None,
        "ed_departure_time": _iso(_time(row.get("outtime"))) if table == "edstays" else None,
        "ed_registration_time": None,
        "hospital_admit_time": _iso(_time(row.get("admittime"))) if table == "admissions" else None,
        "hospital_discharge_time": _iso(_time(row.get("dischtime"))) if table == "admissions" else None,
        "ed_source_ref": _ref(row, table, index) if table == "edstays" else None,
        "admission_source_ref": _ref(row, table, index) if table == "admissions" else None,
    }


def build_encounter_clock(
    admissions: Iterable[Mapping[str, Any]],
    edstays: Iterable[Mapping[str, Any]],
) -> EncounterClockResult:
    """Build one row per admission and fail closed on ambiguous origins.

    The input rows are intentionally mappings rather than a DataFrame so that
    callers must provide the source contract explicitly.  ED ``intime`` and
    admission ``edregtime`` remain separate fields; no fallback is applied.
    """
    admission_rows = list(admissions)
    ed_rows = list(edstays)
    ed_by_hadm: dict[str, list[tuple[int, Mapping[str, Any]]]] = {}
    for index, row in enumerate(ed_rows):
        hadm = row.get("hadm_id")
        if hadm not in (None, ""):
            ed_by_hadm.setdefault(str(hadm), []).append((index, row))

    rows: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = []
    for index, admission in enumerate(admission_rows):
        hadm_id = admission.get("hadm_id")
        if hadm_id in (None, ""):
            exclusions.append({"source_ref": _ref(admission, "admissions", index), "reason_codes": [REASON_ORIGIN_MISSING]})
            continue
        hadm_key = str(hadm_id)
        ed_matches = ed_by_hadm.get(hadm_key, [])
        admission_times = _row_times(admission, "admissions", index)
        for field, source_field in (
            ("ed_registration_time", "edregtime"),
        ):
            admission_times[field] = _iso(_time(admission.get(source_field)))
        reasons: list[str] = []
        if len(ed_matches) > 1:
            reasons.append(REASON_ORIGIN_AMBIGUOUS)
        if len(ed_matches) == 1:
            ed_index, ed = ed_matches[0]
            ed_times = _row_times(ed, "edstays", ed_index)
            admission_times.update({key: value for key, value in ed_times.items() if value is not None})
            origin_type = "ed_arrival"
            origin_time = _time(ed.get("intime"))
            if origin_time is None:
                reasons.append(REASON_ORIGIN_MISSING)
        else:
            origin_type = "hospital_admit"
            origin_time = _time(admission.get("admittime"))
            if origin_time is None:
                reasons.append(REASON_ORIGIN_MISSING)
        admit_time = _time(admission.get("admittime"))
        discharge_time = _time(admission.get("dischtime"))
        if admit_time is not None and discharge_time is not None and discharge_time < admit_time:
            reasons.append(REASON_TIME_INVERTED)
        ed_arrival = _time(admission_times.get("ed_arrival_time"))
        ed_departure = _time(admission_times.get("ed_departure_time"))
        if ed_arrival is not None and ed_departure is not None and ed_departure < ed_arrival:
            reasons.append(REASON_TIME_INVERTED)
        output = {
            "admission_ref": hadm_key,
            "journey_id": f"hadm:{hadm_key}",
            "ed_stay_ref": admission_times.get("ed_source_ref"),
            "origin_type": origin_type,
            "origin_time": _iso(origin_time),
            **admission_times,
            "status": "excluded" if reasons else "accepted",
            "reason_codes": sorted(set(reasons)),
        }
        if reasons:
            exclusions.append(output)
        else:
            rows.append(output)
    metrics = {
        "admissions_input": len(admission_rows),
        "accepted": len(rows),
        "excluded": len(exclusions),
        "origin_ed_arrival": sum(row["origin_type"] == "ed_arrival" for row in rows),
        "origin_hospital_admit": sum(row["origin_type"] == "hospital_admit" for row in rows),
    }
    return EncounterClockResult(rows=rows, exclusions=exclusions, metrics=metrics)
