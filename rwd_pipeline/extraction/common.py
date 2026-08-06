from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


STRUCTURED_CHUNK_SIZE = 200_000
TEXT_CHUNK_SIZE = 5_000

OUTPUT_COLUMNS = [
    "subject_id",
    "hadm_id",
    "age_at_encounter",
    "sex",
    "chief_complaint",
    "history_of_present_illness",
    "past_medical_history",
    "medications_on_admission",
    "investigation_orders",
    "investigation_reports",
    "primary_icd_code",
    "primary_diagnosis_name",
    "primary_icd_version",
    "other_diagnoses",
    "medication_prescriptions",
    "procedures",
    "discharge_record",
]


class ExtractionError(RuntimeError):
    pass


@dataclass(frozen=True)
class RunConfig:
    data_root: Path
    output: Path
    limit: int


@dataclass(frozen=True)
class RunSummary:
    candidate_count: int
    eligible_count: int
    output_path: Path
    elapsed_seconds: float


def table_path(data_root: Path, module: str, filename: str) -> Path:
    path = data_root / module / filename
    if not path.is_file():
        raise FileNotFoundError(f"Required source file does not exist: {path}")
    return path


def iter_csv_chunks(
    path: Path,
    usecols: Sequence[str],
    chunksize: int,
    dtype: Optional[Mapping[str, str]] = None,
) -> Iterator[pd.DataFrame]:
    offset = 0
    reader = pd.read_csv(
        path,
        usecols=list(usecols),
        dtype=dict(dtype or {}),
        chunksize=chunksize,
        keep_default_na=True,
    )
    try:
        for chunk in reader:
            chunk["_source_row"] = np.arange(offset, offset + len(chunk), dtype=np.int64)
            offset += len(chunk)
            yield chunk
    finally:
        reader.close()


def clean_string(value: Any) -> Optional[str]:
    if is_missing(value):
        return None
    text = str(value).strip()
    return text or None


def clean_id_series(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip().replace("", pd.NA)


def normalize_name(value: Any) -> Optional[str]:
    text = clean_string(value)
    if text is None:
        return None
    return re.sub(r"\s+", " ", text).casefold()


def is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        result = pd.isna(value)
    except (TypeError, ValueError):
        return False
    return bool(result) if isinstance(result, (bool, np.bool_)) else False


def json_scalar(value: Any) -> Any:
    if is_missing(value):
        return None
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def parse_datetime(value: Any) -> pd.Timestamp:
    if is_missing(value):
        return pd.NaT
    if isinstance(value, pd.Timestamp):
        return value
    return pd.to_datetime(value, errors="coerce")


def parse_number(value: Any) -> Optional[float]:
    if is_missing(value):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def parse_integer(value: Any) -> Optional[int]:
    number = parse_number(value)
    if number is None or not number.is_integer():
        return None
    return int(number)


def time_ascending(value: Any) -> Tuple[int, int]:
    timestamp = parse_datetime(value)
    if pd.isna(timestamp):
        return (1, 0)
    return (0, int(timestamp.value))


def number_ascending(value: Any) -> Tuple[int, float]:
    number = parse_number(value)
    return (1, 0.0) if number is None else (0, number)


def string_ascending(value: Any) -> Tuple[int, str]:
    text = clean_string(value)
    return (1, "") if text is None else (0, text)


def validate_subject_match(
    frame: pd.DataFrame,
    admission_subjects: Mapping[str, str],
    source_name: str,
) -> None:
    if frame.empty:
        return
    expected = frame["hadm_id"].map(admission_subjects)
    actual = clean_id_series(frame["subject_id"])
    mismatch = actual.isna() | expected.isna() | actual.ne(expected)
    if mismatch.any():
        row = frame.loc[mismatch].iloc[0]
        raise ExtractionError(
            f"{source_name} subject/hadm conflict at source row "
            f"{int(row['_source_row'])}: subject_id={row['subject_id']!r}, "
            f"hadm_id={row['hadm_id']!r}"
        )


def filter_candidate_rows(
    frame: pd.DataFrame,
    candidate_hadm_ids: Iterable[str],
) -> pd.DataFrame:
    frame = frame.copy()
    frame["hadm_id"] = clean_id_series(frame["hadm_id"])
    frame["subject_id"] = clean_id_series(frame["subject_id"])
    return frame.loc[frame["hadm_id"].isin(candidate_hadm_ids)].copy()


def exact_dictionary(
    frame: pd.DataFrame,
    key_columns: Sequence[str],
    value_column: str,
) -> Dict[Tuple[str, ...], str]:
    work = frame.copy()
    for column in key_columns:
        work[column] = clean_id_series(work[column])
    work[value_column] = work[value_column].map(clean_string)
    work = work.dropna(subset=[*key_columns, value_column])
    counts = work.groupby(list(key_columns), dropna=False).size()
    unique_keys = set(counts[counts.eq(1)].index.tolist())
    result: Dict[Tuple[str, ...], str] = {}
    for row in work.itertuples(index=False):
        values = row._asdict()
        key = tuple(str(values[column]) for column in key_columns)
        if key in unique_keys:
            result[key] = str(values[value_column])
    return result
