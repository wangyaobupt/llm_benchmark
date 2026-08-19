"""Materialize one investigation-fact row per order or result component.

Generic events keep MIMIC grain (a radiology *report*, a lab *result row*, a
POE *order*).  This module is the only place that turns those events into the
investigation domain: one exam_name per imaging fact, one lab label per
resulted fact, and POE subtypes as separate order facts.  It does not join
orders to results.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Iterable, Mapping

import pyarrow as pa
import pyarrow.parquet as pq

from .fields import (
    candidate_name_of,
    candidate_specificity_of,
    lift_order_fields,
    _clean,
)
from .first_wave import (
    attach_radiology_exam_details,
    expand_imaging_report_events,
    is_first_wave_row,
    load_first_wave_policy,
)
from .source_grouping import attach_source_groups


SCHEMA_VERSION = "investigation-facts/1.0.0"

FACT_TYPE_ORDER = "order"
FACT_TYPE_RESULTED = "resulted"
FACT_TYPE_REPORTED = "reported"

DOMAIN_LAB = "lab"
DOMAIN_IMAGING = "imaging"
DOMAIN_MICROBIOLOGY = "microbiology"
DOMAIN_CARDIOLOGY = "cardiology"
DOMAIN_CLINICAL = "clinical"

OCCURRENCE_COLLECTION = "collection_time_proxy"
OCCURRENCE_EXAM = "exam_time_proxy"
OCCURRENCE_ORDER = "order_entry_time"

PUBLIC_COLUMNS = (
    "fact_id",
    "subject_id",
    "hadm_id",
    "domain",
    "fact_type",
    "investigation_name",
    "occurrence_time",
    "available_time",
    "occurrence_semantics",
    "group_id",
    "group_type",
    "group_id_status",
    "source_table",
    "source_event_id",
    "source_id",
    "raw_ref",
    "event_kind",
    "track_id",
    "candidate_specificity",
    "content_specificity",
    "order_type",
    "order_subtype",
    "lifecycle_action",
    "poe_id",
    "poe_seq",
    "chain_root_poe_id",
    "exam_name",
    "note_id",
    "specimen_id",
)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()[:24]


def _content_specificity(row: Mapping[str, Any], track_id: str | None) -> str:
    raw = row.get("content_specificity")
    if raw in {"entity_specific", "attribute_enriched", "subtype_only", "category_only"}:
        return str(raw)
    if track_id == "generic_lab_order":
        return "category_only"
    if row.get("order_subtype"):
        return "subtype_only"
    if track_id in {"lab_result_proxy", "imaging_result_proxy"}:
        return "entity_specific"
    return "category_only"


def is_investigation_event(event: Mapping[str, Any]) -> bool:
    kind = str(event.get("event_kind") or "")
    table = str(event.get("source_table") or "")
    return (
        kind.endswith("_ordered")
        or kind.endswith("_resulted")
        or kind == "imaging_reported"
        or table.endswith("poe_timeline")
        or table.endswith("poe")
        or table.endswith("labevents")
        or table.endswith("microbiologyevents")
        or table.endswith("radiology")
    )


def classify_investigation(row: Mapping[str, Any]) -> tuple[str, str] | None:
    """Return (domain, fact_type) or None when the row is not an investigation."""
    kind = str(row.get("event_kind") or "")
    table = str(row.get("source_table") or "")
    order_type = str(row.get("order_type") or "")
    if table.endswith("labevents") or kind == "laboratory_resulted":
        return DOMAIN_LAB, FACT_TYPE_RESULTED
    if table.endswith("microbiologyevents") or kind == "microbiology_resulted":
        return DOMAIN_MICROBIOLOGY, FACT_TYPE_RESULTED
    if kind == "imaging_reported" or (
        table.endswith("radiology") and not kind.endswith("_ordered")
    ):
        return DOMAIN_IMAGING, FACT_TYPE_REPORTED
    if kind == "imaging_ordered" or order_type == "Radiology":
        return DOMAIN_IMAGING, FACT_TYPE_ORDER
    if kind == "laboratory_ordered" or order_type == "Lab":
        return DOMAIN_LAB, FACT_TYPE_ORDER
    if order_type == "Cardiology":
        return DOMAIN_CARDIOLOGY, FACT_TYPE_ORDER
    if (
        kind.endswith("_ordered")
        or table.endswith("poe_timeline")
        or table.endswith("poe")
        or row.get("poe_id") is not None
        or row.get("chain_root_poe_id") is not None
    ):
        return DOMAIN_CLINICAL, FACT_TYPE_ORDER
    return None


def track_id_for(domain: str, fact_type: str) -> str | None:
    if fact_type == FACT_TYPE_RESULTED and domain in {DOMAIN_LAB, DOMAIN_MICROBIOLOGY}:
        return "lab_result_proxy"
    if fact_type == FACT_TYPE_REPORTED and domain == DOMAIN_IMAGING:
        return "imaging_result_proxy"
    if fact_type == FACT_TYPE_ORDER and domain == DOMAIN_IMAGING:
        return "imaging_order"
    if fact_type == FACT_TYPE_ORDER and domain == DOMAIN_LAB:
        return "generic_lab_order"
    if fact_type == FACT_TYPE_ORDER:
        return "clinical_order"
    return None


def occurrence_semantics_for(fact_type: str, domain: str) -> str:
    if fact_type == FACT_TYPE_RESULTED:
        return OCCURRENCE_COLLECTION
    if fact_type == FACT_TYPE_REPORTED:
        return OCCURRENCE_EXAM
    if fact_type == FACT_TYPE_ORDER:
        return OCCURRENCE_ORDER
    return OCCURRENCE_ORDER if domain else OCCURRENCE_COLLECTION


def load_specimen_sidecar(traceable_path: Any | None) -> dict[str, dict[str, Any]]:
    if traceable_path is None:
        return {}
    path = traceable_path
    if not hasattr(path, "is_file") or not path.is_file():
        return {}
    table = pq.read_table(
        path,
        columns=["event_id", "clinical_readable_record_json", "raw_record_json"],
        filters=[("event_kind", "in", ["laboratory_resulted", "microbiology_resulted"])],
    )
    extra: dict[str, dict[str, Any]] = {}
    for row in table.to_pylist():
        event_id = row.get("event_id")
        if event_id:
            extra[str(event_id)] = row
    return extra


def attach_specimen_ids(
    events: list[dict[str, Any]], sidecar: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    if not sidecar:
        return events
    merged = []
    for event in events:
        addon = sidecar.get(str(event.get("event_id")))
        if not addon:
            merged.append(event)
            continue
        row = dict(event)
        if addon.get("clinical_readable_record_json"):
            row["clinical_readable_record_json"] = addon["clinical_readable_record_json"]
        if addon.get("raw_record_json"):
            row["raw_record_json"] = addon["raw_record_json"]
        merged.append(row)
    return merged


def _source_id(row: Mapping[str, Any]) -> str | None:
    for key in ("poe_id", "labevent_id", "note_id", "source_row_id", "event_id"):
        cleaned = _clean(row.get(key))
        if cleaned:
            return cleaned
    return None


@dataclass(frozen=True)
class FactResult:
    facts: list[dict[str, Any]]
    exclusions: list[dict[str, Any]]
    metrics: dict[str, int]


def build_investigation_facts(
    events: Iterable[Mapping[str, Any]],
    *,
    radiology_sidecar: Mapping[str, list[Mapping[str, Any]]] | None = None,
    specimen_sidecar: Mapping[str, Mapping[str, Any]] | None = None,
    policy: Mapping[str, Any] | None = None,
) -> FactResult:
    """Lift buried exam_name / specimen keys and emit domain facts.

    One radiology report becomes one fact per ``exam_name``.  POE orders stay
    as ``fact_type=order`` and are never aligned to result rows by time.
    """
    wave_policy = policy or load_first_wave_policy()
    rows = [dict(event) for event in events]
    if specimen_sidecar:
        rows = attach_specimen_ids(rows, specimen_sidecar)
    if radiology_sidecar:
        rows = attach_radiology_exam_details(rows, radiology_sidecar)
    expanded = expand_imaging_report_events(rows, policy=wave_policy)
    grouped = attach_source_groups(lift_order_fields(event) for event in expanded)
    facts: list[dict[str, Any]] = []
    exclusions: list[dict[str, Any]] = list(grouped.exclusions)
    skipped = 0
    for row in grouped.rows:
        if not is_investigation_event(row):
            skipped += 1
            continue
        classified = classify_investigation(row)
        if classified is None:
            skipped += 1
            continue
        domain, fact_type = classified
        track_id = track_id_for(domain, fact_type)
        content_specificity = _content_specificity(row, track_id)
        try:
            investigation_name = (
                candidate_name_of(
                    row,
                    track_id=track_id or "unknown",
                    order_type=row.get("order_type"),
                    order_subtype=row.get("order_subtype"),
                )
                if track_id
                else None
            )
        except ValueError as error:
            exclusions.append({
                "event_id": row.get("event_id"),
                "reason_codes": ["CANDIDATE_UNRESOLVED"],
                "detail": str(error),
            })
            continue
        candidate_specificity = (
            candidate_specificity_of(
                content_specificity=content_specificity,
                order_subtype=row.get("order_subtype"),
                track_id=track_id,
            )
            if track_id
            else None
        )
        occurrence_time = row.get("event_time")
        available_time = row.get("available_time") or occurrence_time
        fact_id = "fact:" + _hash([
            row.get("event_id"),
            fact_type,
            investigation_name,
            occurrence_time,
        ])
        fact = dict(row)
        fact.update({
            "fact_id": fact_id,
            "domain": domain,
            "fact_type": fact_type,
            "investigation_name": investigation_name,
            "occurrence_time": occurrence_time,
            "available_time": available_time,
            "occurrence_semantics": occurrence_semantics_for(fact_type, domain),
            "group_id": row.get("source_group_id"),
            "group_type": row.get("source_group_type"),
            "group_id_status": row.get("source_group_id_status"),
            "source_event_id": row.get("event_id"),
            "source_id": _source_id(row),
            "raw_ref": row.get("raw_row_ref") or row.get("raw_ref"),
            "track_id": track_id,
            "content_specificity": content_specificity,
            "candidate_specificity": candidate_specificity,
            "candidate_name": investigation_name,
        })
        facts.append(fact)
    facts.sort(key=lambda row: (
        str(row.get("hadm_id") or ""),
        str(row.get("occurrence_time") or ""),
        str(row.get("poe_seq") or ""),
        str(row.get("investigation_name") or ""),
        str(row.get("event_id") or ""),
    ))
    return FactResult(
        facts=facts,
        exclusions=exclusions,
        metrics={
            "input_events": grouped.metrics["input"],
            "facts": len(facts),
            "skipped_non_investigation": skipped,
            "orders": sum(row["fact_type"] == FACT_TYPE_ORDER for row in facts),
            "resulted": sum(row["fact_type"] == FACT_TYPE_RESULTED for row in facts),
            "reported": sum(row["fact_type"] == FACT_TYPE_REPORTED for row in facts),
        },
    )


def public_fact_rows(facts: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Scalar columns for parquet.  Nested event payloads stay in memory only."""
    rows: list[dict[str, Any]] = []
    for fact in facts:
        rows.append({key: fact.get(key) for key in PUBLIC_COLUMNS})
    return rows


def first_wave_facts(
    facts: Iterable[Mapping[str, Any]],
    *,
    policy: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Result-layer facts only.  POE orders never enter the first-wave set."""
    selected: list[dict[str, Any]] = []
    for fact in facts:
        if not is_first_wave_row(fact, policy):
            continue
        if fact.get("occurrence_time") in (None, ""):
            continue
        selected.append(dict(fact))
    return selected


def write_facts_parquet(path: Any, facts: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = public_fact_rows(facts)
    table = pa.Table.from_pylist(rows) if rows else pa.table({})
    pq.write_table(table, path)
