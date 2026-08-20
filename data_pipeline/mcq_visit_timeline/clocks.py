"""Parse visit clocks. Do not coalesce ED and hospital times into one field."""

from __future__ import annotations

from datetime import datetime
from typing import Any


class ClockError(ValueError):
    pass


def parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("T", " ").replace("Z", "")
    if "+" in text[10:]:
        text = text.split("+", 1)[0].strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(str(value).strip())
    except ValueError:
        return None


def format_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.strftime("%Y-%m-%d %H:%M:%S")


def hours_between(start: datetime | None, end: datetime | None) -> float | None:
    if start is None or end is None:
        return None
    return (end - start).total_seconds() / 3600.0


def presentation_origin(timed: dict[str, Any]) -> tuple[datetime | None, str | None, str | None]:
    ed_in = parse_datetime(timed.get("ed_intime"))
    admit = parse_datetime(timed.get("admittime"))
    if ed_in is not None:
        return ed_in, format_datetime(ed_in), "ed_intime"
    if admit is not None:
        return admit, format_datetime(admit), "admittime"
    return None, None, None
