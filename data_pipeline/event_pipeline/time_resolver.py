"""Source-specific time semantics without guessed fallbacks."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def iso_time(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if len(text) == 10:
        datetime.strptime(text, "%Y-%m-%d")
        return text
    try:
        datetime.fromisoformat(text)
    except ValueError as error:
        raise ValueError(f"unsupported MIMIC time value: {text!r}") from error
    return text.replace(" ", "T", 1)


def resolved_times(
    *,
    event_time: Any = None,
    available_time: Any = None,
    recorded_time: Any = None,
) -> dict[str, str | None]:
    event = iso_time(event_time)
    available = iso_time(available_time)
    recorded = iso_time(recorded_time)
    if event is None and available is None and recorded is None:
        status = "unresolved"
    elif event is not None and available is not None:
        status = "resolved"
    else:
        status = "partially_resolved"
    precision = "unknown"
    for value in (event, available, recorded):
        if value is not None:
            if len(value) == 10:
                precision = "date"
            elif "." in value:
                precision = "subsecond"
            else:
                precision = "second"
            break
    return {
        "event_time": event,
        "available_time": available,
        "recorded_time": recorded,
        "time_resolution_status": status,
        "time_precision": precision,
    }
