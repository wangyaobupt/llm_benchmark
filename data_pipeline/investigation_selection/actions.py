"""Project eligibility / candidate ids onto investigation facts.

Identity, clocks, exam_name explode, and grouping live in ``facts.py``.
This module only stamps the frozen-protocol eligibility fields that
episodes and time-point queries still need.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Iterable, Mapping

from .eligibility import (
    ELIGIBLE,
    EligibilityPolicy,
    load_eligibility_policy,
    track_for,
)
from .facts import FactResult, build_investigation_facts
from .fields import candidate_specificity_of


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()[:24]


def _time_semantics(track_id: str | None, event_kind: str | None, fact_type: str | None) -> str:
    if fact_type == "resulted" or (track_id == "lab_result_proxy") or str(event_kind or "").endswith("_resulted"):
        return "collection_time_proxy"
    if fact_type == "order" or str(event_kind or "").endswith("_ordered") or track_id in {
        "imaging_order",
        "clinical_order",
        "generic_lab_order",
    }:
        return "order_entry_time"
    if fact_type == "reported" or str(event_kind or "") == "imaging_reported":
        return "result_availability_time"
    return "occurrence_time"


@dataclass(frozen=True)
class ActionResult:
    actions: list[dict[str, Any]]
    exclusions: list[dict[str, Any]]
    metrics: dict[str, int]


def project_actions_from_facts(
    facts: FactResult | Iterable[Mapping[str, Any]],
    *,
    policy: EligibilityPolicy | None = None,
) -> ActionResult:
    """Stamp eligibility onto already-built investigation facts."""
    eligibility = policy or load_eligibility_policy()
    if isinstance(facts, FactResult):
        rows = facts.facts
        exclusions: list[dict[str, Any]] = list(facts.exclusions)
        input_events = facts.metrics.get("input_events", len(rows))
    else:
        rows = [dict(row) for row in facts]
        exclusions = []
        input_events = len(rows)
    actions: list[dict[str, Any]] = []
    for row in rows:
        kind = str(row.get("event_kind") or "")
        fact_type = row.get("fact_type")
        order_type = row.get("order_type")
        order_subtype = row.get("order_subtype")
        eligibility_status = eligibility.classify(
            None if fact_type in {"resulted", "reported"} or kind.endswith("_resulted") else order_type,
            None if fact_type in {"resulted", "reported"} or kind.endswith("_resulted") else order_subtype,
        )
        if fact_type in {"resulted", "reported"} or kind.endswith("_resulted") or kind == "imaging_reported":
            eligibility_status = ELIGIBLE
        track_id = track_for(
            event_kind=kind,
            order_type=order_type,
            eligibility=eligibility_status,
            source_table=row.get("source_table"),
        )
        if fact_type in {"resulted", "reported"} and row.get("track_id"):
            track_id = row.get("track_id")
        content_specificity = row.get("content_specificity") or "category_only"
        candidate_name = row.get("investigation_name") or row.get("candidate_name")
        if track_id and not candidate_name:
            exclusions.append({
                "event_id": row.get("event_id"),
                "reason_codes": ["CANDIDATE_UNRESOLVED"],
                "detail": "investigation fact is missing investigation_name",
            })
            continue
        candidate_specificity = row.get("candidate_specificity") or (
            candidate_specificity_of(
                content_specificity=str(content_specificity),
                order_subtype=order_subtype,
                track_id=track_id,
            )
            if track_id
            else None
        )
        candidate_id = None
        if track_id and candidate_name:
            candidate_id = "candidate:" + _hash([track_id, candidate_specificity, candidate_name.casefold()])
        action = {
            "action_id": "action:" + _hash([
                row.get("event_id"),
                row.get("poe_id"),
                row.get("event_time") or row.get("occurrence_time"),
                row.get("lifecycle_action"),
                candidate_name,
            ]),
            "fact_id": row.get("fact_id"),
            "event_id": row.get("event_id"),
            "subject_id": row.get("subject_id"),
            "hadm_id": row.get("hadm_id"),
            "event_time": row.get("event_time") or row.get("occurrence_time"),
            "available_time": row.get("available_time") or row.get("event_time") or row.get("occurrence_time"),
            "occurrence_time": row.get("occurrence_time") or row.get("event_time"),
            "time_semantics": _time_semantics(track_id, kind, None if fact_type is None else str(fact_type)),
            "occurrence_semantics": row.get("occurrence_semantics"),
            "poe_id": row.get("poe_id"),
            "poe_seq": row.get("poe_seq"),
            "chain_root_poe_id": row.get("chain_root_poe_id"),
            "source_group_id": row.get("source_group_id") or row.get("group_id"),
            "source_group_type": row.get("source_group_type") or row.get("group_type"),
            "source_group_id_status": row.get("source_group_id_status") or row.get("group_id_status"),
            "action": (
                "create"
                if (fact_type in {"resulted", "reported"} or kind.endswith("_resulted") or kind == "imaging_reported")
                and row.get("lifecycle_action") in {None, "", "uninterpreted"}
                else row.get("lifecycle_action")
            ),
            "status": row.get("status"),
            "order_type": order_type,
            "order_subtype": order_subtype,
            "content_specificity": content_specificity,
            "candidate_specificity": candidate_specificity,
            "eligibility": eligibility_status,
            "track_id": track_id,
            "candidate_id": candidate_id,
            "candidate_name": candidate_name,
            "investigation_name": candidate_name,
            "domain": row.get("domain"),
            "fact_type": fact_type,
            "event_kind": kind,
            "source_table": row.get("source_table"),
            "lineage_visibility_scope": "retrospective_only",
            "source_event_id": row.get("source_event_id") or row.get("event_id"),
            "observed_components": row.get("observed_components"),
            "required_components": row.get("required_components"),
            "panel_definition_status": row.get("panel_definition_status"),
            "evidence_phase": row.get("evidence_phase"),
        }
        actions.append(action)
    actions.sort(key=lambda row: (
        str(row.get("hadm_id") or ""),
        str(row.get("event_time") or ""),
        str(row.get("poe_seq") or ""),
        str(row.get("candidate_name") or ""),
        str(row.get("event_id") or ""),
    ))
    return ActionResult(
        actions=actions,
        exclusions=exclusions,
        metrics={
            "input_events": input_events,
            "actions": len(actions),
            "eligible": sum(
                row["eligibility"] == ELIGIBLE and row["track_id"] != "lab_result_proxy"
                for row in actions
            ),
            "excluded_non_investigation": sum(
                row["eligibility"] == "excluded_non_investigation" for row in actions
            ),
            "review_required": sum(row["eligibility"] == "review_required" for row in actions),
            "monitoring_only": sum(row["eligibility"] == "monitoring_only" for row in actions),
            "result_proxy": sum(row["track_id"] == "lab_result_proxy" for row in actions),
        },
    )


def project_investigation_actions(
    events: Iterable[Mapping[str, Any]],
    *,
    policy: EligibilityPolicy | None = None,
    radiology_sidecar: Mapping[str, list[Mapping[str, Any]]] | None = None,
    specimen_sidecar: Mapping[str, Mapping[str, Any]] | None = None,
) -> ActionResult:
    """Build facts from events, then stamp eligibility."""
    fact_result = build_investigation_facts(
        events,
        radiology_sidecar=radiology_sidecar,
        specimen_sidecar=specimen_sidecar,
    )
    return project_actions_from_facts(fact_result, policy=policy)
