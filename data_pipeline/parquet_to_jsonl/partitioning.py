"""Stable subject-level development/test isolation."""

from __future__ import annotations

import hashlib


SPLIT_NAME = "subject_hash_v1"


def assign_subject_partition(subject_id: str | int, development_percent: int = 20) -> dict:
    """Assign every episode for one patient to exactly one stable partition."""
    if not 1 <= development_percent <= 99:
        raise ValueError("development_percent must be between 1 and 99")
    token = str(subject_id).encode("ascii")
    bucket = int.from_bytes(hashlib.sha256(token).digest()[:8], "big") % 100
    name = "development" if bucket < development_percent else "final_test"
    return {
        "name": name,
        "split_name": SPLIT_NAME,
        "subject_bucket": bucket,
        "development_percent": development_percent,
    }
