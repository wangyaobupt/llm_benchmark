"""Stable identifiers derived from native MIMIC keys."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from .models import SourceSpec


ID_VERSION = "clinical-event-id/1.0.0"


def _digest(*parts: str, length: int = 24) -> str:
    payload = "\x1f".join((ID_VERSION, *parts)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:length]


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build_source_row_id(spec: SourceSpec, row: dict[str, Any]) -> str:
    key_values = []
    complete = bool(spec.native_key_fields)
    for field in spec.native_key_fields:
        value = row.get(field)
        if value in (None, ""):
            complete = False
            break
        key_values.append(f"{field}={value}")
    identity = "|".join(key_values) if complete else canonical_json(row)
    return f"src:{_digest(spec.module, spec.table, identity)}"


def build_event_id(source_row_id: str, component: str) -> str:
    return f"evt:{_digest(source_row_id, component)}"


def build_entity_id(event_id: str) -> str:
    return f"ent:{_digest(event_id, 'primary-entity')}"
