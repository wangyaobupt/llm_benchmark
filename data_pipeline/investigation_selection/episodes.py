"""Fold investigation actions into source-native episodes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import Any, Iterable, Mapping

from .actions import project_investigation_actions
from .eligibility import ELIGIBLE


ORDER_CATEGORY_ONLY = "ORDER_CONTENT_CATEGORY_ONLY"
ORDER_CHANGE_NO_DELTA = "ORDER_CHANGE_NO_OBSERVABLE_DELTA"
ORDER_CANCELLED_AFTER_CREATE = "ORDER_CANCELLED_AFTER_CREATE"
PANEL_UNREVIEWED = "PANEL_DEFINITION_UNREVIEWED"
PANEL_INCOMPLETE = "PANEL_INCOMPLETE"


def _time(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value:
        raise ValueError("episode event_time must be a non-empty ISO string")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _iso(value: datetime) -> str:
    return value.isoformat(sep=" ")


def _hash(value: Any) -> str:
    body = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(body).hexdigest()[:24]


def _episode_id(track: str, candidate_id: str, group: str, time_value: datetime) -> str:
    return "episode:" + _hash([track, candidate_id, group, time_value.isoformat()])


def _candidate_key(row: Mapping[str, Any]) -> tuple[str | None, str | None, str | None]:
    return (
        row.get("track_id"),
        row.get("candidate_id"),
        row.get("candidate_name"),
    )


@dataclass(frozen=True)
class EpisodeResult:
    episodes: list[dict[str, Any]]
    catalog: list[dict[str, Any]]
    exclusions: list[dict[str, Any]]
    metrics: dict[str, int]


def _as_action_rows(events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows = [dict(row) for row in events]
    if rows and all(row.get("track_id") and row.get("source_group_id") for row in rows):
        for row in rows:
            row.setdefault("action", row.get("lifecycle_action") or "create")
            row.setdefault("eligibility", ELIGIBLE)
            row.setdefault("candidate_name", row.get("preferred_name") or row.get("candidate_id"))
            row.setdefault("candidate_specificity", row.get("candidate_level") or "category")
        return rows
    if rows and all(row.get("action") and row.get("eligibility") for row in rows):
        return rows
    return project_investigation_actions(rows).actions


def build_investigation_episodes(
    events: Iterable[Mapping[str, Any]], *, burst_minutes: int = 15
) -> EpisodeResult:
    """Build order/result episodes without linking generic orders to results.

    ``burst_minutes`` is accepted for compatibility.  Order lifecycles are
    folded by ``chain_root`` / ``source_group_id``, not by a time burst.
    Cancel or later Inactive status never deletes a historical create.
    """
    del burst_minutes
    actions = _as_action_rows(events)
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    exclusions: list[dict[str, Any]] = []
    skipped = 0
    for action in actions:
        track = action.get("track_id")
        group = action.get("source_group_id")
        if not track:
            skipped += 1
            continue
        if action.get("eligibility") == "excluded_non_investigation":
            exclusions.append({
                "event_id": action.get("event_id"),
                "reason_codes": ["ORDER_NON_INVESTIGATION"],
                "order_type": action.get("order_type"),
                "order_subtype": action.get("order_subtype"),
            })
            continue
        if not group:
            exclusions.append({
                "event_id": action.get("event_id"),
                "reason_codes": ["ORDER_CHAIN_INCOMPLETE"] if track != "lab_result_proxy" else ["SPECIMEN_GROUP_MISSING"],
            })
            continue
        grouped.setdefault((str(track), str(group)), []).append(action)

    episodes: list[dict[str, Any]] = []
    split_groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for (track, group), values in grouped.items():
        if track in {"lab_result_proxy", "imaging_result_proxy"}:
            for action in values:
                component = str(
                    action.get("candidate_id")
                    or action.get("candidate_name")
                    or action.get("preferred_name")
                    or action.get("event_id")
                    or "unknown"
                )
                split_groups.setdefault((track, group, component), []).append(action)
        else:
            split_groups.setdefault((track, group, ""), []).extend(values)

    for (track, group, _component), values in sorted(split_groups.items()):
        values.sort(key=lambda row: (
            _time(row.get("event_time") or row.get("available_time")),
            str(row.get("poe_seq") or ""),
            str(row.get("event_id") or ""),
        ))
        creates = [row for row in values if row.get("action") == "create"]
        anchor = creates[0] if creates else values[0]
        try:
            first_time = _time(anchor.get("event_time") or anchor.get("available_time"))
            last_time = max(_time(row.get("event_time") or row.get("available_time")) for row in values)
        except ValueError as error:
            exclusions.append({"source_group_id": group, "reason_codes": ["HYPOTHESIS_STRUCTURAL_INELIGIBLE"], "detail": str(error)})
            continue

        candidate_id = anchor.get("candidate_id")
        candidate_name = anchor.get("candidate_name")
        candidate_specificity = anchor.get("candidate_specificity")
        if not candidate_id or not candidate_name:
            exclusions.append({"source_group_id": group, "reason_codes": ["CANDIDATE_UNRESOLVED"]})
            continue

        observable_changes = []
        silent_changes = 0
        for row in values:
            if row.get("action") != "change":
                continue
            if _candidate_key(row) != _candidate_key(anchor):
                observable_changes.append(row)
            else:
                silent_changes += 1

        later_cancel = any(
            row.get("action") in {"cancel", "discontinue"}
            and _time(row.get("event_time") or row.get("available_time")) >= first_time
            for row in values
        )
        reasons: list[str] = []
        if track == "generic_lab_order" and candidate_specificity == "category":
            reasons.append(ORDER_CATEGORY_ONLY)
        if silent_changes:
            reasons.append(ORDER_CHANGE_NO_DELTA)
        if later_cancel:
            reasons.append(ORDER_CANCELLED_AFTER_CREATE)
        if track == "lab_result_proxy" and anchor.get("panel_definition_status") == "unreviewed":
            reasons.append(PANEL_UNREVIEWED)
        observed = set(anchor.get("observed_components") or [])
        required = set(anchor.get("required_components") or [])
        completeness = "unknown"
        if required:
            completeness = "complete" if required <= observed else "partial"
            if completeness == "partial":
                reasons.append(PANEL_INCOMPLETE)

        episode = {
            "episode_id": _episode_id(track, str(candidate_id), group, first_time),
            "track_id": track,
            "domain": anchor.get("domain"),
            "fact_type": anchor.get("fact_type"),
            "investigation_name": anchor.get("investigation_name") or candidate_name,
            "occurrence_semantics": anchor.get("occurrence_semantics"),
            "candidate_id": candidate_id,
            "candidate_name": candidate_name,
            "candidate_level": candidate_specificity,
            "candidate_specificity": candidate_specificity,
            "source_group_id": group,
            "chain_root_poe_id": anchor.get("chain_root_poe_id"),
            "subject_id": anchor.get("subject_id"),
            "hadm_id": anchor.get("hadm_id"),
            "source_event_ids": [str(row.get("event_id")) for row in values if row.get("event_id") is not None],
            "source_action_ids": [str(row.get("action_id")) for row in values if row.get("action_id") is not None],
            "occurrence_time": _iso(first_time),
            "initial_order_time": _iso(first_time),
            "first_visible_time": _iso(first_time),
            "last_action_time": _iso(last_time),
            "available_time": _iso(max(_time(row.get("available_time") or row.get("event_time")) for row in values)),
            "terminal_action": values[-1].get("action"),
            "terminal_status": values[-1].get("status"),
            "was_changed": any(row.get("action") == "change" for row in values),
            "was_later_cancelled": later_cancel,
            "action_count": len(values),
            "eligibility": anchor.get("eligibility") or ELIGIBLE,
            "panel_completeness": completeness,
            "status": "accepted",
            "reason_codes": sorted(set(reasons)),
        }
        episodes.append(episode)
        for change in observable_changes:
            change_time = _time(change.get("event_time") or change.get("available_time"))
            change_candidate = change.get("candidate_id") or candidate_id
            episodes.append({
                **episode,
                "episode_id": _episode_id(track, str(change_candidate), group, change_time),
                "candidate_id": change_candidate,
                "candidate_name": change.get("candidate_name") or candidate_name,
                "candidate_specificity": change.get("candidate_specificity") or candidate_specificity,
                "candidate_level": change.get("candidate_specificity") or candidate_specificity,
                "occurrence_time": _iso(change_time),
                "initial_order_time": _iso(change_time),
                "source_event_ids": [str(change.get("event_id"))] if change.get("event_id") else [],
                "reason_codes": sorted(set(reasons) - {ORDER_CHANGE_NO_DELTA}),
            })

    episodes.sort(key=lambda row: (str(row.get("hadm_id") or ""), row["initial_order_time"], row["episode_id"]))
    catalog_map: dict[tuple[str, str, str], dict[str, Any]] = {}
    for episode in episodes:
        key = (episode["track_id"], episode["candidate_id"], str(episode["candidate_specificity"]))
        catalog_map.setdefault(key, {
            "candidate_id": episode["candidate_id"],
            "candidate_name": episode["candidate_name"],
            "candidate_level": episode["candidate_specificity"],
            "candidate_specificity": episode["candidate_specificity"],
            "track_id": episode["track_id"],
            "catalog_status": "exploratory_unreviewed",
        })
    catalog = sorted(catalog_map.values(), key=lambda row: (row["track_id"], row["candidate_id"]))
    return EpisodeResult(
        episodes=episodes,
        catalog=catalog,
        exclusions=exclusions,
        metrics={
            "input": len(actions),
            "episodes": len(episodes),
            "catalog_candidates": len(catalog),
            "excluded": len(exclusions),
            "skipped_untracked": skipped,
        },
    )
