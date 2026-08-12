"""Stable event-cleaning identifiers derived from native MIMIC keys."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .models import SourceSpec


ID_VERSION = "clinical-event-id/1.0.0"


class SourceIdentityError(ValueError):
    def __init__(self, reason_code: str, message: str):
        super().__init__(f"{reason_code}: {message}")
        self.reason_code = reason_code


def _digest(*parts: str, length: int = 24) -> str:
    payload = "\x1f".join((ID_VERSION, *parts)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:length]


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build_source_row_id(
    spec: SourceSpec,
    row: dict[str, Any],
    *,
    duplicate_occurrence_ordinal: int = 0,
) -> str:
    if duplicate_occurrence_ordinal < 0:
        raise SourceIdentityError(
            "SOURCE_IDENTITY_OCCURRENCE_INVALID", spec.source_table
        )
    if spec.identity_strategy == "canonical_row_hash_with_occurrence":
        identity = canonical_json(row)
        # Preserve the historical identifier for the first/only row. Exact
        # duplicates receive explicit ordinals instead of colliding silently.
        if duplicate_occurrence_ordinal:
            identity = f"{identity}|duplicate_occurrence={duplicate_occurrence_ordinal}"
    else:
        if duplicate_occurrence_ordinal:
            raise SourceIdentityError(
                "SOURCE_IDENTITY_OCCURRENCE_UNEXPECTED", spec.source_table
            )
        key_values = []
        for field in spec.native_key_fields:
            value = row.get(field)
            if value in (None, ""):
                raise SourceIdentityError(
                    "SOURCE_IDENTITY_KEY_MISSING",
                    f"{spec.source_table}.{field}",
                )
            key_values.append(f"{field}={value}")
        identity = "|".join(key_values)
    return f"src:{_digest(spec.module, spec.table, identity)}"


def build_event_id(source_row_id: str, component: str) -> str:
    return f"evt:{_digest(source_row_id, component)}"


def build_entity_id(event_id: str) -> str:
    return f"ent:{_digest(event_id, 'primary-entity')}"
