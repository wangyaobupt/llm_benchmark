"""Deterministic eligible-visit sampling. Resume must reuse a written list."""

from __future__ import annotations

import heapq
from typing import Any

from data_pipeline.mimic_raw_archive.selection import subject_bucket


def admission_score(subject_id: str, hadm_id: str) -> str:
    import hashlib

    return hashlib.sha256(f"{subject_id}:{hadm_id}".encode("ascii")).hexdigest()


def in_sample_pool(
    subject_id: str,
    *,
    development_percent: int,
    sample_pool: str,
) -> bool:
    if sample_pool == "all":
        return True
    return subject_bucket(subject_id) < development_percent


def select_eligible(
    eligible: list[dict[str, Any]],
    *,
    sample_size: int,
    development_percent: int,
    sample_pool: str,
) -> list[dict[str, Any]]:
    pool: list[tuple[str, str, str, int]] = []
    for row in eligible:
        subject_id = str(row["subject_id"])
        hadm_id = str(row["hadm_id"])
        if not in_sample_pool(
            subject_id,
            development_percent=development_percent,
            sample_pool=sample_pool,
        ):
            continue
        bucket = subject_bucket(subject_id)
        pool.append((admission_score(subject_id, hadm_id), subject_id, hadm_id, bucket))
    if len(pool) < sample_size:
        raise ValueError(
            f"eligible {sample_pool} pool {len(pool)} < requested sample {sample_size}"
        )
    chosen = heapq.nsmallest(sample_size, pool, key=lambda item: item[0])
    return [
        {
            "subject_id": subject_id,
            "hadm_id": hadm_id,
            "selection_rank": rank,
            "subject_bucket": bucket,
            "sample_pool": sample_pool,
        }
        for rank, (_, subject_id, hadm_id, bucket) in enumerate(chosen)
    ]
