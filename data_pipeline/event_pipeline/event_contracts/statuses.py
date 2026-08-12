"""Frozen status values used at event-stage boundaries."""

CLEANING_STATUSES = frozenset({"accepted", "rejected"})
NORMALIZATION_STATUSES = frozenset({"mapped", "unresolved", "not_applicable"})
UNIT_NORMALIZATION_STATUSES = frozenset(
    {"mapped", "unresolved", "not_applicable"}
)

__all__ = [
    "CLEANING_STATUSES",
    "NORMALIZATION_STATUSES",
    "UNIT_NORMALIZATION_STATUSES",
]
