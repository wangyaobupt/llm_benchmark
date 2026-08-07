"""Phase 0-1: Load patients and determine eligible episodes."""

from __future__ import annotations
import gzip
import csv
import logging
from typing import Any

import duckdb
from .config import Config

logger = logging.getLogger(__name__)


def load_patients(config: Config) -> dict[int, dict[str, Any]]:
    """Load patients.csv.gz into a memory dict keyed by subject_id."""
    patients: dict[int, dict[str, Any]] = {}
    with gzip.open(config.patients_path, "rt", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sid = int(row["subject_id"])
            patients[sid] = {
                "anchor_age": int(row["anchor_age"]),
                "anchor_year": int(row["anchor_year"]),
                "gender": row["gender"].strip(),
            }
    logger.info("Loaded %d patients", len(patients))
    return patients


def find_eligible_episodes(
    con: duckdb.DuckDBPyConnection,
    config: Config,
) -> list[dict[str, Any]]:
    """Find eligible hospital episodes with valid primary diagnosis and DS."""

    base = str(config.parquet_dir) + "/"

    # Step 1: episodes with diagnosis_code events
    con.execute(f"""
        CREATE TEMP TABLE has_dx AS
        SELECT DISTINCT te.episode_id
        FROM '{base}timeline_events.parquet' te
        WHERE te.event_type = 'diagnosis_code'
          AND te.episode_id IN (
            SELECT episode_id FROM '{base}episode_index.parquet'
            WHERE episode_type = 'hospital' AND hadm_id IS NOT NULL
          )
    """)

    # Step 2: episodes with valid DS document
    con.execute(f"""
        CREATE TEMP TABLE has_ds AS
        SELECT DISTINCT episode_id
        FROM '{base}documents.parquet'
        WHERE note_type = 'DS' AND length(text) > 0
    """)

    # Step 3: eligible = hospital + hadm_id + has_dx + has_ds
    rows = con.execute(f"""
        SELECT ei.episode_id, ei.hadm_id, ei.subject_id,
               ei.admission_type, ei.admission_location,
               ei.discharge_location, ei.outcome_type,
               ei.episode_start_time, ei.clinical_end_time,
               ei.hospital_expire_flag
        FROM '{base}episode_index.parquet' ei
        WHERE ei.episode_type = 'hospital'
          AND ei.hadm_id IS NOT NULL
          AND ei.episode_id IN (SELECT episode_id FROM has_dx)
          AND ei.episode_id IN (SELECT episode_id FROM has_ds)
        ORDER BY ei.hadm_id
    """).fetchall()

    cols = [
        "episode_id", "hadm_id", "subject_id",
        "admission_type", "admission_location",
        "discharge_location", "outcome_type",
        "episode_start_time", "clinical_end_time",
        "hospital_expire_flag",
    ]
    episodes = [dict(zip(cols, r)) for r in rows]

    if config.limit > 0:
        episodes = episodes[: config.limit]
        logger.info("Limited to %d episodes", len(episodes))

    logger.info("Found %d candidate episodes (pre age/sex filter)", len(episodes))
    return episodes


def compute_age(patients: dict[int, dict[str, Any]], subject_id: int, admittime) -> int | None:
    """Compute age at encounter from patients dict."""
    p = patients.get(subject_id)
    if p is None:
        return None
    try:
        adm_year = admittime.year if hasattr(admittime, "year") else int(str(admittime)[:4])
        return p["anchor_age"] + adm_year - p["anchor_year"]
    except Exception:
        return None
