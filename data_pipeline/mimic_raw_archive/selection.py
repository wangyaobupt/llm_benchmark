"""Deterministic development-only admission selection outside patient records."""

from __future__ import annotations

import csv
import gzip
import hashlib
import heapq
from pathlib import Path


def subject_bucket(subject_id: str) -> int:
    digest = hashlib.sha256(str(subject_id).encode("ascii")).digest()
    return int.from_bytes(digest[:8], "big") % 100


def select_admissions(
    admissions_path: Path,
    sample_size: int,
    development_percent: int,
) -> list[dict[str, str | int]]:
    """Select stable admissions from development subjects without changing records."""
    candidates: list[tuple[str, str, str]] = []
    with gzip.open(admissions_path, "rt", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            subject_id = row["subject_id"]
            hadm_id = row["hadm_id"]
            if subject_bucket(subject_id) >= development_percent:
                continue
            score = hashlib.sha256(f"{subject_id}:{hadm_id}".encode("ascii")).hexdigest()
            candidates.append((score, subject_id, hadm_id))
    if len(candidates) < sample_size:
        raise ValueError(
            f"development admissions {len(candidates)} < requested sample {sample_size}"
        )
    chosen = heapq.nsmallest(sample_size, candidates, key=lambda item: item[0])
    return [
        {"subject_id": subject_id, "hadm_id": hadm_id, "selection_rank": rank}
        for rank, (_, subject_id, hadm_id) in enumerate(chosen)
    ]
