"""Time-point queries: what was ordered now, and what was already visible."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Iterable, Mapping

from .actions import project_investigation_actions
from .eligibility import ELIGIBLE
from .episodes import build_investigation_episodes


RESULT_LIKE = {
    "laboratory_resulted",
    "microbiology_resulted",
    "imaging_reported",
}

RECENCY_BASIS = {
    "laboratory_resulted": "available_time",
    "imaging_reported": "available_time",
    "microbiology_resulted": "available_time",
    "vital_measured": "event_time",
    "imaging_ordered": "available_time",
    "laboratory_ordered": "available_time",
    "clinical_ordered": "available_time",
    "symptom_reported": "event_time",
    "triage_acuity_recorded": "event_time",
}


def _parse_time(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        raise TypeError(f"unsupported time type: {type(value).__name__}")
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    return parsed


def _require_time(value: Any, name: str) -> datetime:
    parsed = _parse_time(value)
    if parsed is None:
        raise ValueError(f"{name} is required")
    return parsed


def recency_clock(event: Mapping[str, Any]) -> tuple[datetime | None, str]:
    kind = str(event.get("event_kind") or event.get("track_id") or "")
    basis = RECENCY_BASIS.get(kind, "event_time")
    if basis == "available_time":
        return _parse_time(event.get("available_time")), "available_time"
    return _parse_time(event.get("event_time")), "event_time"


def visibility_decision(
    event: Mapping[str, Any],
    *,
    index_time: datetime,
    query_start: datetime | None,
) -> tuple[bool, str]:
    event_time = _parse_time(event.get("event_time"))
    if event_time is None:
        return False, "EVENT_TIME_UNKNOWN"
    presentation_bound = event.get("time_policy_id") == "presentation_origin_v1"
    # Bound chief complaints are known from encounter origin.  They stay visible
    # at the first-wave index even when that origin equals the first order time.
    if presentation_bound:
        if event_time > index_time:
            return False, "EVENT_NOT_PREINDEX"
    elif event_time >= index_time:
        return False, "EVENT_NOT_PREINDEX"
    available_time = _parse_time(event.get("available_time"))
    if available_time is None:
        return False, "AVAILABLE_TIME_UNKNOWN"
    if available_time > index_time:
        return False, "NOT_YET_AVAILABLE"
    phase = event.get("evidence_phase")
    if phase == "post_hoc":
        return False, "POST_HOC"
    if phase == "administrative_end":
        return False, "ADMINISTRATIVE_END"
    recency_time, _basis = recency_clock(event)
    if recency_time is None:
        return False, "RECENCY_TIME_UNKNOWN"
    if query_start is not None and recency_time < query_start:
        kind = str(event.get("event_kind") or "")
        if kind in RESULT_LIKE:
            if available_time < query_start or available_time > index_time:
                return False, "RECENCY_WINDOW_EXPIRED"
        else:
            return False, "RECENCY_WINDOW_EXPIRED"
    return True, "INCLUDED_PRESENTATION_ORIGIN" if presentation_bound else "INCLUDED"


@dataclass(frozen=True)
class InvestigationAtTime:
    hadm_id: str
    index_time: str
    investigations: list[dict[str, Any]]
    review_required: list[dict[str, Any]]
    metrics: dict[str, int]


@dataclass(frozen=True)
class VisibleFactsAtTime:
    hadm_id: str
    index_time: str
    query_start: str | None
    included: list[dict[str, Any]]
    excluded: list[dict[str, Any]]
    metrics: dict[str, int]


def list_investigations_at(
    events: Iterable[Mapping[str, Any]],
    *,
    hadm_id: str,
    index_time: str | datetime,
    burst_minutes: int = 15,
    include_review_required: bool = False,
) -> InvestigationAtTime:
    """Return eligible investigation orders at an index time.

    The index is an observed ordering action.  Same-class orders inside the
    burst window are included.  Later Inactive / cancel does not remove a
    create that already happened.
    """
    index = _require_time(index_time, "index_time")
    window_end = index + timedelta(minutes=burst_minutes)
    actions = project_investigation_actions(events).actions
    first_candidate: dict[str, tuple[Any, Any]] = {}
    for action in actions:
        group = action.get("source_group_id")
        if group and group not in first_candidate and action.get("action") == "create":
            first_candidate[str(group)] = (action.get("candidate_id"), action.get("candidate_name"))
    matched: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []
    for action in actions:
        if str(action.get("hadm_id")) != str(hadm_id):
            continue
        if action.get("track_id") == "lab_result_proxy":
            continue
        if action.get("action") not in {"create", "change"}:
            continue
        action_time = _parse_time(action.get("event_time"))
        if action_time is None or action_time < index or action_time > window_end:
            continue
        if action.get("action") == "change":
            prior = first_candidate.get(str(action.get("source_group_id")))
            if prior == (action.get("candidate_id"), action.get("candidate_name")):
                continue
        row = dict(action)
        if action.get("eligibility") == ELIGIBLE and action.get("track_id"):
            matched.append(row)
        elif action.get("eligibility") == "review_required":
            review_rows.append(row)
    matched.sort(key=lambda row: (str(row.get("event_time")), str(row.get("event_id"))))
    review_rows.sort(key=lambda row: (str(row.get("event_time")), str(row.get("event_id"))))
    return InvestigationAtTime(
        hadm_id=str(hadm_id),
        index_time=index.isoformat(sep=" "),
        investigations=matched,
        review_required=review_rows,
        metrics={
            "investigations": len(matched),
            "review_required": len(review_rows),
            "burst_minutes": burst_minutes,
        },
    )


def list_visible_facts(
    events: Iterable[Mapping[str, Any]],
    *,
    hadm_id: str,
    index_time: str | datetime,
    query_start: str | datetime | None = None,
) -> VisibleFactsAtTime:
    index = _require_time(index_time, "index_time")
    start = _parse_time(query_start) if query_start is not None else None
    included: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for event in events:
        if str(event.get("hadm_id")) != str(hadm_id):
            continue
        visible, reason = visibility_decision(event, index_time=index, query_start=start)
        recency_time, basis = recency_clock(event)
        record = {
            "event_id": event.get("event_id"),
            "event_kind": event.get("event_kind"),
            "event_time": event.get("event_time"),
            "available_time": event.get("available_time"),
            "recency_time": recency_time.isoformat(sep=" ") if recency_time else None,
            "recency_time_semantics": basis,
            "concept_id": event.get("concept_id"),
            "preferred_name": event.get("preferred_name") or event.get("source_label"),
            "included": visible,
            "reason_code": reason,
        }
        if visible:
            included.append(record)
        else:
            excluded.append(record)
    included.sort(key=lambda row: (str(row.get("event_time") or ""), str(row.get("event_id") or "")))
    excluded.sort(key=lambda row: (str(row.get("event_id") or ""),))
    return VisibleFactsAtTime(
        hadm_id=str(hadm_id),
        index_time=index.isoformat(sep=" "),
        query_start=start.isoformat(sep=" ") if start else None,
        included=included,
        excluded=excluded,
        metrics={
            "included": len(included),
            "excluded": len(excluded),
            "excluded_available_unknown": sum(row["reason_code"] == "AVAILABLE_TIME_UNKNOWN" for row in excluded),
            "excluded_not_yet_available": sum(row["reason_code"] == "NOT_YET_AVAILABLE" for row in excluded),
            "excluded_recency": sum(row["reason_code"] == "RECENCY_WINDOW_EXPIRED" for row in excluded),
            "excluded_posthoc": sum(row["reason_code"] == "POST_HOC" for row in excluded),
        },
    )


def build_timepoint_trace(
    events: Iterable[Mapping[str, Any]],
    *,
    hadm_id: str,
    index_time: str | datetime,
    query_hours: int = 4,
    burst_minutes: int = 15,
) -> dict[str, Any]:
    rows = list(events)
    index = _require_time(index_time, "index_time")
    query_start = index - timedelta(hours=query_hours)
    investigations = list_investigations_at(
        rows, hadm_id=hadm_id, index_time=index, burst_minutes=burst_minutes
    )
    visible = list_visible_facts(
        rows, hadm_id=hadm_id, index_time=index, query_start=query_start
    )
    episodes = build_investigation_episodes(rows)
    target_ids = {row.get("source_group_id") for row in investigations.investigations}
    targets = [
        episode
        for episode in episodes.episodes
        if episode.get("source_group_id") in target_ids and str(episode.get("hadm_id")) == str(hadm_id)
    ]
    return {
        "hadm_id": str(hadm_id),
        "index_time": index.isoformat(sep=" "),
        "query_start": query_start.isoformat(sep=" "),
        "investigations_at_index": investigations.investigations,
        "review_required_at_index": investigations.review_required,
        "included_evidence": visible.included,
        "excluded_preindex_evidence": visible.excluded,
        "targets": targets,
        "metrics": {
            **investigations.metrics,
            **{f"visible_{key}": value for key, value in visible.metrics.items()},
        },
    }
