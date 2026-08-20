"""Deterministic string folding for lookup keys only."""

from __future__ import annotations

import re
from typing import Any

_SPACE = re.compile(r"\s+")


def collapse_ws(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return _SPACE.sub(" ", text)


def lookup_key(value: Any) -> str | None:
    collapsed = collapse_ws(value)
    if collapsed is None:
        return None
    return collapsed.casefold()


def is_redacted(value: Any) -> bool:
    collapsed = collapse_ws(value)
    if collapsed is None:
        return False
    return bool(re.fullmatch(r"(_+\s*)+", collapsed))
