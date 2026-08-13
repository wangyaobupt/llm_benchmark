"""Deterministic, fail-closed decision-snapshot construction."""

from .from_boundary import (
    AuthenticatedBoundaryContext,
    BoundarySnapshotError,
    authenticate_boundary_context,
    audit_authenticated_snapshot,
    build_snapshot_from_boundary,
)

from .visibility import (
    SNAPSHOT_REASON_CODES,
    SnapshotConfigurationError,
    SnapshotInputError,
    SnapshotPolicy,
    build_snapshot,
)

__all__ = [
    "SNAPSHOT_REASON_CODES",
    "BoundarySnapshotError",
    "AuthenticatedBoundaryContext",
    "authenticate_boundary_context",
    "audit_authenticated_snapshot",
    "SnapshotConfigurationError",
    "SnapshotInputError",
    "SnapshotPolicy",
    "build_snapshot",
    "build_snapshot_from_boundary",
]
