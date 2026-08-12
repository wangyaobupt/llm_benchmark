"""Source-specific cleaning-time semantics without guessed fallbacks."""

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
    completion_time: Any = None,
) -> dict[str, Any]:
    event = iso_time(event_time)
    source_available = iso_time(available_time)
    available = source_available
    recorded = iso_time(recorded_time)
    completion = iso_time(completion_time)
    reasons: list[str] = []
    quality_flags: list[str] = []

    if (
        source_available is not None
        and event is not None
        and datetime.fromisoformat(source_available) < datetime.fromisoformat(event)
    ):
        reasons.append("source_available_precedes_event_time")
        quality_flags.append("AVAILABLE_BEFORE_EVENT_TIME")

    if completion is not None and (
        available is None
        or datetime.fromisoformat(available) < datetime.fromisoformat(completion)
    ):
        available = completion
        reasons.append("completion_time_lower_bound")
        quality_flags.append("AVAILABLE_TIME_DERIVED_FROM_COMPLETION")

    if event is not None and available is not None and (
        datetime.fromisoformat(available) < datetime.fromisoformat(event)
    ):
        available = event
        reasons.append("event_time_lower_bound")
        quality_flags.append("AVAILABLE_TIME_CLAMPED_TO_EVENT_TIME")

    if available is None:
        quality_flags.append("AVAILABLE_TIME_UNKNOWN")

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
        "source_available_time": source_available,
        "available_time": available,
        "recorded_time": recorded,
        "time_resolution_status": status,
        "time_precision": precision,
        "time_resolution_reasons": reasons,
        "time_quality_flags": quality_flags,
    }
