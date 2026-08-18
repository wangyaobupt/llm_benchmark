"""Construct source-native investigation episodes and a versioned catalog."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import json
from typing import Any, Iterable, Mapping


ORDER_CANCELLED = "ORDER_CANCELLED_OR_INACTIVE"
ORDER_CATEGORY_ONLY = "ORDER_CONTENT_CATEGORY_ONLY"
PANEL_UNREVIEWED = "PANEL_DEFINITION_UNREVIEWED"
PANEL_INCOMPLETE = "PANEL_INCOMPLETE"


def _time(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("episode event_time must be a non-empty ISO string")
    return datetime.fromisoformat(value)


def _hash(value: Any) -> str:
    body = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(body).hexdigest()[:24]


def _source_group(event: Mapping[str, Any]) -> str:
    group = event.get("source_group_id")
    if not isinstance(group, str) or not group:
        raise ValueError("episode event requires source_group_id")
    return group


@dataclass(frozen=True)
class EpisodeResult:
    episodes: list[dict[str, Any]]
    catalog: list[dict[str, Any]]
    exclusions: list[dict[str, Any]]
    metrics: dict[str, int]


def _track(event: Mapping[str, Any]) -> tuple[str, str]:
    if event.get("track_id") in {"imaging_order", "clinical_order", "generic_lab_order", "lab_result_proxy"}:
        return str(event["track_id"]), "explicit"
    source_table = str(event.get("source_table") or "")
    kind = str(event.get("event_kind") or "")
    if "labevents" in source_table or kind in {"laboratory_resulted", "microbiology_resulted"}:
        return "lab_result_proxy", "source"
    if kind.endswith("_ordered") and event.get("order_type") == "Lab":
        return "generic_lab_order", "category"
    if "imaging" in kind or event.get("entity_type") == "imaging_study":
        return "imaging_order", "source"
    if kind.endswith("_ordered"):
        return "clinical_order", "source"
    raise ValueError("event cannot be assigned to an investigation track")


def _candidate(event: Mapping[str, Any], track: str) -> tuple[str, str, str | None]:
    candidate_id = event.get("candidate_id")
    name = event.get("preferred_name") or event.get("source_label") or event.get("order_type")
    if not isinstance(name, str) or not name:
        raise ValueError("investigation event requires a source candidate name")
    level = str(event.get("candidate_level") or ("category" if track == "generic_lab_order" else "component"))
    if track == "generic_lab_order" and level not in {"category", "generic"}:
        level = "category"
    if not isinstance(candidate_id, str) or not candidate_id:
        candidate_id = f"candidate:{_hash([track, level, name.casefold()])}"
    return str(candidate_id), name, level


def _episode_id(track: str, candidate_id: str, group: str, time_value: datetime) -> str:
    return "episode:" + _hash([track, candidate_id, group, time_value.isoformat()])


def build_investigation_episodes(
    events: Iterable[Mapping[str, Any]], *, burst_minutes: int = 15
) -> EpisodeResult:
    """Build order/result episodes without linking generic orders to results."""
    if not isinstance(burst_minutes, int) or burst_minutes <= 0:
        raise ValueError("burst_minutes must be a positive integer")
    grouped: dict[tuple[str, str, str], list[Mapping[str, Any]]] = {}
    exclusions: list[dict[str, Any]] = []
    input_count = 0
    for index, event in enumerate(events):
        input_count += 1
        try:
            track, track_source = _track(event)
            candidate_id, candidate_name, candidate_level = _candidate(event, track)
            group = _source_group(event)
            event_time = _time(event.get("event_time") or event.get("available_time"))
        except (TypeError, ValueError) as error:
            exclusions.append({"row_index": index, "reason_codes": ["HYPOTHESIS_STRUCTURAL_INELIGIBLE"], "detail": str(error)})
            continue
        transaction = str(event.get("transaction_type") or event.get("lifecycle_action") or "New").casefold()
        if track.endswith("_order") and transaction in {"cancel", "discontinue", "cancelled", "discontinued"}:
            exclusions.append({"row_index": index, "reason_codes": [ORDER_CANCELLED], "source_group_id": group})
            continue
        key = (track, candidate_id, group)
        grouped.setdefault(key, []).append({**event, "_track_source": track_source, "_candidate_name": candidate_name, "_candidate_level": candidate_level, "_time": event_time})
    episodes: list[dict[str, Any]] = []
    for (track, candidate_id, group), values in sorted(grouped.items()):
        values.sort(key=lambda row: (row["_time"], str(row.get("event_id", ""))))
        bursts: list[list[Mapping[str, Any]]] = []
        for value in values:
            if not bursts or value["_time"] - bursts[-1][0]["_time"] > timedelta(minutes=burst_minutes):
                bursts.append([value])
            else:
                bursts[-1].append(value)
        for burst in bursts:
            first = burst[0]
            candidate_level = first["_candidate_level"]
            reasons: list[str] = []
            if track == "generic_lab_order" and candidate_level == "category":
                reasons.append(ORDER_CATEGORY_ONLY)
            if track == "lab_result_proxy" and first.get("panel_definition_status") == "unreviewed":
                reasons.append(PANEL_UNREVIEWED)
            observed = set(first.get("observed_components") or [])
            required = set(first.get("required_components") or [])
            completeness = "unknown"
            if required:
                completeness = "complete" if required <= observed else "partial"
                if completeness == "partial":
                    reasons.append(PANEL_INCOMPLETE)
            episode = {
                "episode_id": _episode_id(track, candidate_id, group, first["_time"]),
                "track_id": track,
                "candidate_id": candidate_id,
                "candidate_name": first["_candidate_name"],
                "candidate_level": candidate_level,
                "source_group_id": group,
                "source_event_ids": sorted(str(row.get("event_id")) for row in burst if row.get("event_id") is not None),
                "occurrence_time": first["_time"].isoformat(sep=" "),
                "available_time": max((_time(row.get("available_time") or row.get("storetime") or row.get("event_time")) for row in burst)),
                "panel_completeness": completeness,
                "status": "excluded" if reasons else "accepted",
                "reason_codes": sorted(set(reasons)),
            }
            if reasons:
                exclusions.append({"episode_id": episode["episode_id"], "reason_codes": episode["reason_codes"]})
            else:
                episodes.append(episode)
    episodes.sort(key=lambda row: row["episode_id"])
    catalog_map: dict[tuple[str, str, str], dict[str, Any]] = {}
    for episode in episodes:
        key = (episode["track_id"], episode["candidate_id"], episode["candidate_level"])
        catalog_map.setdefault(key, {
            "candidate_id": episode["candidate_id"],
            "candidate_name": episode["candidate_name"],
            "candidate_level": episode["candidate_level"],
            "track_id": episode["track_id"],
            "catalog_status": "exploratory_unreviewed",
        })
    catalog = sorted(catalog_map.values(), key=lambda row: (row["track_id"], row["candidate_id"]))
    return EpisodeResult(
        episodes=episodes,
        catalog=catalog,
        exclusions=exclusions,
        metrics={"input": input_count, "episodes": len(episodes), "catalog_candidates": len(catalog), "excluded": len(exclusions)},
    )

