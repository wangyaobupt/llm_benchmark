"""1,000-admission style audits for order subtypes and lifecycle folding."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

from .fields import lift_order_fields


def poe_subtype_audit(actions: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[tuple[str, str, str, str, str], Counter[str]] = {}
    subjects: dict[tuple[str, str, str, str, str], set[str]] = {}
    for action in actions:
        if action.get("track_id") == "lab_result_proxy":
            continue
        key = (
            str(action.get("order_type") or ""),
            str(action.get("order_subtype") or ""),
            str(action.get("event_kind") or ""),
            str(action.get("eligibility") or ""),
            str(action.get("candidate_specificity") or ""),
        )
        bucket = counts.setdefault(key, Counter())
        bucket["count"] += 1
        subject = action.get("subject_id")
        if subject not in (None, ""):
            subjects.setdefault(key, set()).add(str(subject))
    rows = []
    for key, bucket in sorted(counts.items()):
        order_type, order_subtype, event_kind, eligibility, specificity = key
        rows.append({
            "order_type": order_type or None,
            "order_subtype": order_subtype or None,
            "event_kind": event_kind,
            "count": bucket["count"],
            "subject_count": len(subjects.get(key, ())),
            "eligibility": eligibility,
            "candidate_specificity": specificity or None,
            "review_status": "draft_unreviewed",
        })
    return rows


def poe_lifecycle_audit(actions: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for action in actions:
        group = action.get("source_group_id")
        if not group:
            continue
        groups.setdefault(str(group), []).append(action)
    rows = []
    for group_id, values in sorted(groups.items()):
        poe_ids = {str(row.get("poe_id")) for row in values if row.get("poe_id")}
        rows.append({
            "source_group_id": group_id,
            "hadm_id": values[0].get("hadm_id"),
            "action_count": len(values),
            "poe_id_count": len(poe_ids),
            "has_change": any(row.get("action") == "change" for row in values),
            "has_cancel": any(row.get("action") == "cancel" for row in values),
            "has_discontinue": any(row.get("action") == "discontinue" for row in values),
            "terminal_status": values[-1].get("status"),
            "historical_create_retained": any(row.get("action") == "create" for row in values),
        })
    return rows


def audit_poe_subtypes_from_parquet(path: Path) -> list[dict[str, Any]]:
    """Count order_type x subtype from a processed/normalized events parquet."""
    import pyarrow.parquet as pq

    table = pq.read_table(
        path,
        columns=[
            "hadm_id",
            "subject_id",
            "event_kind",
            "source_table",
            "source_label",
            "preferred_name",
            "content_specificity",
            "value_structured_json",
        ],
        filters=[("event_kind", "in", ["laboratory_ordered", "imaging_ordered", "clinical_ordered", "medication_ordered"])],
    )
    counts: dict[tuple[str, str, str, str], dict[str, set[str] | int]] = {}
    for row in table.to_pylist():
        lifted = lift_order_fields(row)
        key = (
            str(lifted.get("order_type") or ""),
            str(lifted.get("order_subtype") or ""),
            str(row.get("event_kind") or ""),
            str(row.get("content_specificity") or ""),
        )
        bucket = counts.get(key)
        if bucket is None:
            bucket = {"count": 0, "hadm": set(), "subject": set()}
            counts[key] = bucket
        bucket["count"] = int(bucket["count"]) + 1
        if row.get("hadm_id"):
            bucket["hadm"].add(str(row["hadm_id"]))  # type: ignore[union-attr]
        if row.get("subject_id"):
            bucket["subject"].add(str(row["subject_id"]))  # type: ignore[union-attr]
    rows = []
    for key, bucket in sorted(counts.items()):
        order_type, order_subtype, event_kind, specificity = key
        rows.append({
            "order_type": order_type or None,
            "order_subtype": order_subtype or None,
            "event_kind": event_kind,
            "content_specificity": specificity or None,
            "count": int(bucket["count"]),
            "hadm_count": len(bucket["hadm"]),  # type: ignore[arg-type]
            "subject_count": len(bucket["subject"]),  # type: ignore[arg-type]
        })
    return rows
