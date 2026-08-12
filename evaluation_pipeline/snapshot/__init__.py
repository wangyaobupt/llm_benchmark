"""Deterministic, fail-closed decision-snapshot construction."""

from .visibility import (
    SNAPSHOT_REASON_CODES,
    SnapshotConfigurationError,
    SnapshotInputError,
    SnapshotPolicy,
    build_snapshot,
)

__all__ = [
    "SNAPSHOT_REASON_CODES",
    "SnapshotConfigurationError",
    "SnapshotInputError",
    "SnapshotPolicy",
    "build_snapshot",
]
