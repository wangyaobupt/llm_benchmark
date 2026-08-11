"""Decision snapshot contracts and future-information leakage validation."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable


QUESTION_TYPES = (
    "investigation_selection",
    "clinical_diagnosis",
    "treatment_management",
    "referral_specialty",
    "discharge_followup",
)


class FutureInformationLeakageError(ValueError):
    """Raised when a snapshot exposes information unavailable at its cutoff."""


def build_decision_snapshots(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Materialize five snapshots as evidence references and validate each one."""
    episode = record["episode"]
    clinical_end = episode["clinical_end_time"]
    outcomes = {
        "investigation_selection": _first_event(record["orders"]["provider_orders"]),
        "clinical_diagnosis": _first_event(record["diagnoses"]["ed_diagnoses"]),
        "treatment_management": _first_event(
            record["treatments"]["medications"]
            + record["treatments"]["pharmacy_orders"]
            + record["treatments"]["medication_administrations"]
        ),
        "referral_specialty": _first_event(record["care_path"]["services"]),
        "discharge_followup": {
            "outcome_id": record["presentation"]["discharge_summary_retrospective"].get("note_id"),
            "cutoff_time": clinical_end,
        },
    }
    definitions = (
        ("investigation_selection", ["presentation", "vitals", "demographics"]),
        ("clinical_diagnosis", ["presentation", "vitals", "investigations", "orders"]),
        ("treatment_management", ["presentation", "vitals", "investigations", "diagnoses.ed_diagnoses"]),
        ("referral_specialty", ["presentation", "vitals", "investigations", "treatments"]),
        ("discharge_followup", ["episode", "presentation", "investigations", "treatments", "care_path"]),
    )
    snapshots = []
    all_evidence = list(_evidence_references(record))
    for question_type, visible_paths in definitions:
        outcome = outcomes[question_type]
        cutoff = outcome.get("cutoff_time") if outcome else None
        evidence = _visible_at_cutoff(all_evidence, visible_paths, cutoff)
        snapshot = {
            "question_type": question_type,
            "cutoff_time": cutoff,
            "visible_paths": visible_paths,
            "forbidden_evidence_phases": ["post_hoc"],
            "hidden_outcome": outcome.get("outcome_id") if outcome else None,
            "source_event_ids": [item["event_id"] for item in evidence],
            "evidence": evidence,
            "status": "excluded_missing_outcome" if not outcome or cutoff is None else "ready",
        }
        if snapshot["status"] == "ready":
            validate_snapshot_evidence(snapshot, evidence)
        snapshots.append(snapshot)
    return snapshots


def validate_snapshot_evidence(
    snapshot: dict[str, Any], evidence: Iterable[dict[str, Any]]
) -> None:
    """Reject evidence that was unavailable at cutoff or is explicitly post-hoc."""
    cutoff = _parse_time(snapshot.get("cutoff_time"))
    if cutoff is None:
        raise FutureInformationLeakageError("snapshot cutoff_time is missing")
    forbidden = set(snapshot.get("forbidden_evidence_phases", []))
    for item in evidence:
        if item.get("evidence_phase") in forbidden:
            raise FutureInformationLeakageError(
                f"post-hoc evidence exposed: {item.get('event_id') or item.get('note_id')}"
            )
        available = _parse_time(item.get("available_time"))
        if available is None:
            raise FutureInformationLeakageError(
                f"evidence availability is unknown: {item.get('event_id') or item.get('note_id')}"
            )
        if available > cutoff:
            raise FutureInformationLeakageError(
                f"future evidence exposed: available_time={available.isoformat()} cutoff={cutoff.isoformat()}"
            )


def _parse_time(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _first_event(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = []
    for item in items:
        cutoff = _parse_time(item.get("event_time"))
        if cutoff is not None:
            candidates.append((cutoff, item))
    if not candidates:
        return None
    cutoff, item = min(candidates, key=lambda pair: pair[0])
    return {
        "outcome_id": item.get("event_id") or item.get("note_id"),
        "cutoff_time": cutoff.isoformat(sep=" "),
    }


def _evidence_references(record: dict[str, Any]) -> Iterable[dict[str, Any]]:
    roots = ("presentation", "vitals", "demographics", "orders", "investigations", "diagnoses", "treatments", "care_path")
    for root in roots:
        yield from _walk_evidence(record[root], root)


def _walk_evidence(value: Any, path: str) -> Iterable[dict[str, Any]]:
    if isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk_evidence(item, f"{path}[{index}]")
        return
    if not isinstance(value, dict):
        return
    event_id = value.get("event_id") or value.get("note_id")
    if event_id and "available_time" in value:
        yield {
            "event_id": str(event_id),
            "path": path,
            "available_time": value.get("available_time"),
            "evidence_phase": value.get("evidence_phase", "contemporaneous"),
        }
    for key, child in value.items():
        if isinstance(child, (dict, list)):
            yield from _walk_evidence(child, f"{path}.{key}")


def _visible_at_cutoff(
    evidence: list[dict[str, Any]], visible_paths: list[str], cutoff_value: Any
) -> list[dict[str, Any]]:
    cutoff = _parse_time(cutoff_value)
    if cutoff is None:
        return []
    visible = []
    seen = set()
    for item in evidence:
        if not any(item["path"].startswith(path) for path in visible_paths):
            continue
        if item.get("evidence_phase") == "post_hoc":
            continue
        available = _parse_time(item.get("available_time"))
        if available is None or available > cutoff:
            continue
        key = (item["event_id"], item["path"])
        if key not in seen:
            visible.append(item)
            seen.add(key)
    return visible
