"""Build a methodology decision corpus from the 1,000-admission aggregation."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping

import pyarrow as pa
import pyarrow.parquet as pq

from .actions import project_actions_from_facts
from .audit import poe_lifecycle_audit, poe_subtype_audit
from .episodes import build_investigation_episodes
from .facts import (
    build_investigation_facts,
    load_specimen_sidecar,
    write_facts_parquet,
)
from .first_wave import (
    evidence_exclude_event_kinds,
    first_wave_tracks,
    is_first_wave_row,
    load_first_wave_policy,
    load_radiology_exam_sidecar,
)
from .presentation import stamp_presentation_events
from .query import build_timepoint_trace, visibility_decision


ORDER_TRACKS = ("imaging_order", "clinical_order", "generic_lab_order")
FIRST_WAVE_POLICY = load_first_wave_policy()
FIRST_WAVE_TRACKS = first_wave_tracks(FIRST_WAVE_POLICY)
FIRST_WAVE_EVIDENCE_EXCLUDE = evidence_exclude_event_kinds(FIRST_WAVE_POLICY)
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EVENTS = (
    REPO_ROOT
    / "data/test_1000_0812/event_pipeline_output/aggregation/processed_events.parquet"
)
DEFAULT_TRACEABLE = (
    REPO_ROOT
    / "data/test_1000_0812/event_pipeline_output/aggregation/traceable_events.parquet"
)
DEFAULT_RAW_SOURCE = (
    REPO_ROOT
    / "data/test_1000_0812/event_pipeline_output/aggregation/raw_source_records.parquet"
)
DEFAULT_SPLIT = (
    REPO_ROOT
    / "versions/v1-template-stem/artifacts/investigation_selection/output/split/subject_split.parquet"
)
DEFAULT_OUTPUT = REPO_ROOT / "data/derived/investigation_timepoint/corpus_1000"
PROTOCOL_LOCK = REPO_ROOT / "config/investigation-selection/protocol-lock.json"
CATALOG_LOCK = REPO_ROOT / "config/investigation-selection/catalog-lock.json"


def _parse_time(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    return parsed


def _iso(value: datetime) -> str:
    return value.isoformat(sep=" ")


def _hash(value: Any) -> str:
    body = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(body).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_split_roles(path: Path | None) -> dict[str, str]:
    if path is None or not path.is_file():
        return {}
    table = pq.read_table(path, columns=["subject_id", "role"])
    return {
        str(subject): str(role)
        for subject, role in zip(table.column("subject_id").to_pylist(), table.column("role").to_pylist())
    }


def encounter_origin(events: Iterable[Mapping[str, Any]]) -> datetime | None:
    preferred: list[datetime] = []
    fallback: list[datetime] = []
    for event in events:
        parsed = _parse_time(event.get("event_time"))
        if parsed is None:
            continue
        kind = str(event.get("event_kind") or "")
        if kind in {"symptom_reported", "triage_acuity_recorded", "vital_measured"}:
            preferred.append(parsed)
        elif event.get("time_resolution_status") == "resolved":
            fallback.append(parsed)
    pool = preferred or fallback
    return min(pool) if pool else None


def wave_time(episode: Mapping[str, Any]) -> datetime | None:
    """Place a first-wave episode on the result-table occurrence clock.

    Labs and imaging reports use charttime (collection / exam).  POE ordertime
    is not a first-wave index.  storetime is recorded as available_time on the
    target row, not as the freeze.
    """
    if episode.get("track_id") in FIRST_WAVE_TRACKS:
        return _parse_time(episode.get("occurrence_time") or episode.get("event_time"))
    return _parse_time(episode.get("initial_order_time"))


def enumerate_first_wave_decisions(
    episodes: Iterable[Mapping[str, Any]], *, burst_minutes: int
) -> list[dict[str, Any]]:
    """One first-stage freeze: earliest result-table test of the stay.

    Index is the earliest lab/imaging charttime, not a POE order.  Same-class
    result episodes inside the burst are the first-batch targets.  POE
    Radiology subtypes (CT Scan / General Xray) are not first-wave candidates.
    """
    eligible = [
        dict(row)
        for row in episodes
        if is_first_wave_row(row)
        and row.get("eligibility") == "eligible_investigation"
        and wave_time(row) is not None
    ]
    if not eligible:
        return []
    index = min(wave_time(row) for row in eligible)
    assert index is not None
    window_end = index + timedelta(minutes=burst_minutes)
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in eligible:
        stamp = wave_time(row)
        if stamp is None or stamp < index or stamp > window_end:
            continue
        by_key[(str(row["track_id"]), str(row.get("candidate_specificity") or "category"))].append(row)
    decisions: list[dict[str, Any]] = []
    for (track_id, specificity), cluster in sorted(by_key.items()):
        cluster.sort(key=lambda row: (str(wave_time(row)), str(row.get("episode_id"))))
        decisions.append({
            "track_id": track_id,
            "candidate_class": f"{track_id}:{specificity}",
            "index_time": index,
            "target_episode_ids": [str(item["episode_id"]) for item in cluster],
            "decision_trigger_type": "first_wave_investigation",
            "decision_stage": "first_wave",
            "decision_semantics": "conditional_order_choice",
        })
    return decisions


def enumerate_order_decisions(
    episodes: Iterable[Mapping[str, Any]], *, burst_minutes: int
) -> list[dict[str, Any]]:
    eligible = [
        dict(row)
        for row in episodes
        if row.get("track_id") in ORDER_TRACKS
        and row.get("eligibility") == "eligible_investigation"
        and row.get("initial_order_time")
    ]
    eligible.sort(key=lambda row: (str(row["track_id"]), str(row["initial_order_time"]), str(row["episode_id"])))
    consumed: set[str] = set()
    decisions: list[dict[str, Any]] = []
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in eligible:
        by_key[(str(row["track_id"]), str(row.get("candidate_specificity") or "category"))].append(row)
    for (track_id, specificity), rows in by_key.items():
        for row in rows:
            episode_id = str(row["episode_id"])
            if episode_id in consumed:
                continue
            index = _parse_time(row["initial_order_time"])
            if index is None:
                continue
            window_end = index + timedelta(minutes=burst_minutes)
            cluster = []
            for other in rows:
                other_time = _parse_time(other["initial_order_time"])
                if other_time is None or other_time < index or other_time > window_end:
                    continue
                cluster.append(other)
                consumed.add(str(other["episode_id"]))
            decisions.append({
                "track_id": track_id,
                "candidate_class": f"{track_id}:{specificity}",
                "index_time": index,
                "target_episode_ids": [str(item["episode_id"]) for item in cluster],
                "decision_trigger_type": "investigation_order_create",
                "decision_semantics": "conditional_order_choice",
            })
    return decisions


def enumerate_result_proxy_decision(
    episodes: Iterable[Mapping[str, Any]],
    *,
    origin: datetime | None,
    query_hours: int,
    target_hours: int,
) -> list[dict[str, Any]]:
    if origin is None:
        return []
    index = origin + timedelta(hours=query_hours)
    target_end = index + timedelta(hours=target_hours)
    targets = []
    for row in episodes:
        if row.get("track_id") != "lab_result_proxy":
            continue
        available = _parse_time(row.get("available_time"))
        if available is None or available <= index or available > target_end:
            continue
        targets.append(str(row["episode_id"]))
    return [{
        "track_id": "lab_result_proxy",
        "candidate_class": "lab_result_proxy:entity",
        "index_time": index,
        "target_episode_ids": sorted(targets),
        "decision_trigger_type": "result_proxy_query_window",
        "decision_semantics": "conditional_order_choice",
    }]


def _decision_id(hadm_id: str, track_id: str, index_time: datetime, candidate_class: str) -> str:
    return "decision:" + _hash([hadm_id, track_id, _iso(index_time), candidate_class])[:24]


def build_admission_corpus(
    events: list[dict[str, Any]],
    *,
    hadm_id: str,
    split_role: str,
    query_hours: int = 4,
    target_hours: int = 24,
    burst_minutes: int = 15,
    protocol_lock_sha256: str | None = None,
    catalog_lock_sha256: str | None = None,
    radiology_sidecar: Mapping[str, list[Mapping[str, Any]]] | None = None,
    specimen_sidecar: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    del query_hours, target_hours
    fact_result = build_investigation_facts(
        events,
        radiology_sidecar=radiology_sidecar,
        specimen_sidecar=specimen_sidecar,
    )
    action_result = project_actions_from_facts(fact_result)
    episode_result = build_investigation_episodes(action_result.actions)
    origin = encounter_origin(events)
    nodes = enumerate_first_wave_decisions(episode_result.episodes, burst_minutes=burst_minutes)
    first_index = nodes[0]["index_time"] if nodes else None
    # Complaints have no native clock.  Bind them at origin, but never after the
    # first-wave freeze, or they would be hidden at the decision they explain.
    bind_time = origin
    if first_index is not None and (bind_time is None or bind_time > first_index):
        bind_time = first_index
    visible_events = stamp_presentation_events(events, bind_time)
    episode_by_id = {row["episode_id"]: row for row in episode_result.episodes}
    documents: list[dict[str, Any]] = []
    evidence_rows: list[dict[str, Any]] = []
    target_rows: list[dict[str, Any]] = []
    subject_id = next((str(row.get("subject_id")) for row in events if row.get("subject_id")), "")
    for node in nodes:
        index = node["index_time"]
        query_start = bind_time
        decision_id = _decision_id(hadm_id, node["track_id"], index, node["candidate_class"])
        target_ids = list(node["target_episode_ids"])
        target_event_ids = {
            event_id
            for episode_id in target_ids
            for event_id in (episode_by_id.get(episode_id, {}).get("source_event_ids") or [])
        }
        included = 0
        for event in visible_events:
            if str(event.get("event_kind") or "") in FIRST_WAVE_EVIDENCE_EXCLUDE:
                continue
            visible, reason = visibility_decision(event, index_time=index, query_start=query_start)
            if not visible:
                continue
            event_id = event.get("event_id")
            if event_id in target_event_ids:
                continue
            evidence_rows.append({
                "decision_id": decision_id,
                "event_id": event_id,
                "event_kind": event.get("event_kind"),
                "concept_id": event.get("concept_id"),
                "preferred_name": event.get("preferred_name") or event.get("source_label"),
                "event_time": event.get("event_time"),
                "available_time": event.get("available_time"),
                "visibility_reason": reason,
            })
            included += 1
        documents.append({
            "decision_id": decision_id,
            "subject_id": subject_id,
            "hadm_id": str(hadm_id),
            "journey_id": f"hadm:{hadm_id}",
            "split_role": split_role,
            "track_id": node["track_id"],
            "candidate_class": node["candidate_class"],
            "decision_semantics": node["decision_semantics"],
            "decision_trigger_type": node["decision_trigger_type"],
            "decision_stage": node.get("decision_stage") or "first_wave",
            "index_time": _iso(index),
            "query_start": _iso(query_start) if query_start is not None else None,
            "query_end": _iso(index),
            "target_start": _iso(index),
            "target_end": _iso(index + timedelta(minutes=burst_minutes)),
            "zero_target_semantics": "no_eligible_same_class_target" if not target_ids else None,
            "zero_candidate_observed": not target_ids,
            "included_evidence_count": included,
            "protocol_lock_sha256": protocol_lock_sha256,
            "catalog_lock_sha256": catalog_lock_sha256,
        })
        for episode_id in target_ids:
            episode = episode_by_id[episode_id]
            target_rows.append({
                "decision_id": decision_id,
                "episode_id": episode_id,
                "candidate_id": episode.get("candidate_id"),
                "candidate_name": episode.get("candidate_name"),
                "candidate_class": node["candidate_class"],
                "candidate_specificity": episode.get("candidate_specificity"),
                "target_time": episode.get("available_time") if node["track_id"] in FIRST_WAVE_TRACKS else episode.get("initial_order_time"),
                "target_occurrence_time": episode.get("occurrence_time"),
                "target_available_time": episode.get("available_time"),
                "target_semantics": episode.get("track_id"),
                "is_primary_target": True,
            })
    return {
        "hadm_id": str(hadm_id),
        "subject_id": subject_id,
        "split_role": split_role,
        "facts": fact_result.facts,
        "actions": action_result.actions,
        "episodes": episode_result.episodes,
        "documents": documents,
        "evidence": evidence_rows,
        "targets": target_rows,
        "fact_metrics": fact_result.metrics,
        "action_metrics": action_result.metrics,
        "episode_metrics": episode_result.metrics,
        "origin_time": _iso(origin) if origin else None,
        "presentation_bind_time": _iso(bind_time) if bind_time else None,
    }


def _write_parquet(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        table = pa.table({})
    else:
        table = pa.Table.from_pylist(rows)
    pq.write_table(table, path)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@dataclass(frozen=True)
class CorpusBuildResult:
    output_dir: Path
    manifest: dict[str, Any]


def build_corpus_from_parquet(
    events_path: Path,
    output_dir: Path,
    *,
    traceable_path: Path | None = None,
    raw_source_path: Path | None = None,
    split_path: Path | None = None,
    query_hours: int = 4,
    target_hours: int = 24,
    burst_minutes: int = 15,
    max_hadms: int | None = None,
) -> CorpusBuildResult:
    roles = load_split_roles(split_path)
    specimen_sidecar = load_specimen_sidecar(traceable_path)
    radiology_sidecar = load_radiology_exam_sidecar(raw_source_path)
    protocol_lock_sha256 = None
    catalog_lock_sha256 = None
    if PROTOCOL_LOCK.is_file():
        protocol_lock_sha256 = json.loads(PROTOCOL_LOCK.read_text(encoding="utf-8")).get("protocol_lock_sha256")
    if CATALOG_LOCK.is_file():
        catalog_lock_sha256 = json.loads(CATALOG_LOCK.read_text(encoding="utf-8")).get("catalog_lock_sha256")

    table = pq.read_table(events_path)
    hadms = sorted({str(value) for value in table.column("hadm_id").to_pylist() if value not in (None, "")})
    if max_hadms is not None:
        hadms = hadms[:max_hadms]
    grouped: dict[str, list[dict[str, Any]]] = {hadm: [] for hadm in hadms}
    for row in table.to_pylist():
        hadm = row.get("hadm_id")
        if str(hadm) in grouped:
            grouped[str(hadm)].append(row)

    documents: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    targets: list[dict[str, Any]] = []
    episodes: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    facts: list[dict[str, Any]] = []
    traces: list[dict[str, Any]] = []
    admission_metrics: list[dict[str, Any]] = []

    for hadm_id in hadms:
        events = grouped[hadm_id]
        subject_id = next((str(row.get("subject_id")) for row in events if row.get("subject_id")), "")
        split_role = roles.get(subject_id, "unknown")
        result = build_admission_corpus(
            events,
            hadm_id=hadm_id,
            split_role=split_role,
            query_hours=query_hours,
            target_hours=target_hours,
            burst_minutes=burst_minutes,
            protocol_lock_sha256=protocol_lock_sha256,
            catalog_lock_sha256=catalog_lock_sha256,
            radiology_sidecar=radiology_sidecar,
            specimen_sidecar=specimen_sidecar,
        )
        documents.extend(result["documents"])
        evidence.extend(result["evidence"])
        targets.extend(result["targets"])
        episodes.extend(result["episodes"])
        facts.extend(result["facts"])
        actions.extend(
            row
            for row in result["actions"]
            if row.get("track_id") in {*ORDER_TRACKS, *FIRST_WAVE_TRACKS}
        )
        admission_metrics.append({
            "hadm_id": hadm_id,
            "subject_id": subject_id,
            "split_role": split_role,
            "events": len(events),
            "documents": len(result["documents"]),
            "episodes": len(result["episodes"]),
            "origin_time": result["origin_time"],
        })
        if len(traces) < 20 and result["documents"]:
            traces.append(
                build_timepoint_trace(
                    stamp_presentation_events(events, _parse_time(result["presentation_bind_time"])),
                    hadm_id=hadm_id,
                    index_time=result["documents"][0]["index_time"],
                    query_hours=query_hours,
                    burst_minutes=burst_minutes,
                )
            )

    output_dir.mkdir(parents=True, exist_ok=True)
    write_facts_parquet(output_dir / "investigation_facts.parquet", facts)
    _write_parquet(output_dir / "decision_documents.parquet", documents)
    _write_parquet(output_dir / "decision_evidence.parquet", evidence)
    _write_parquet(output_dir / "decision_targets.parquet", targets)
    _write_parquet(output_dir / "investigation_episodes.parquet", episodes)
    _write_parquet(output_dir / "investigation_actions.parquet", actions)
    _write_parquet(output_dir / "admission_metrics.parquet", admission_metrics)
    _write_json(output_dir / "poe-subtype-audit.json", poe_subtype_audit(actions))
    _write_json(output_dir / "poe-lifecycle-audit.json", poe_lifecycle_audit(actions))
    _write_json(output_dir / "timepoint-traces.json", traces)
    counts = {
        "hadms": len(hadms),
        "documents": len(documents),
        "evidence": len(evidence),
        "targets": len(targets),
        "facts": len(facts),
        "episodes": len(episodes),
        "actions": len(actions),
        "development_documents": sum(row["split_role"] == "development" for row in documents),
        "validation_documents": sum(row["split_role"] == "validation" for row in documents),
        "final_test_documents": sum(row["split_role"] == "final_test" for row in documents),
        "order_documents": sum(row["track_id"] != "lab_result_proxy" for row in documents),
        "result_proxy_documents": sum(row["track_id"] == "lab_result_proxy" for row in documents),
        "first_wave_documents": sum(row.get("decision_stage") == "first_wave" for row in documents),
        "zero_target_documents": sum(row["zero_candidate_observed"] for row in documents),
    }
    content = {
        "schema_version": "investigation-decision-corpus/1.2.0",
        "corpus_status": "methodology_unreviewed",
        "gold_count": 0,
        "decision_stage": "first_wave",
        "index_time_policy": "earliest_result_table_charttime_of_stay",
        "observation_window": "encounter_origin_to_index",
        "query_hours": query_hours,
        "target_hours": target_hours,
        "burst_minutes": burst_minutes,
        "events_path": str(events_path),
        "events_sha256": _file_sha256(events_path),
        "protocol_lock_sha256": protocol_lock_sha256,
        "catalog_lock_sha256": catalog_lock_sha256,
        "counts": counts,
        "mining_note": (
            "First-stage documents freeze at the earliest labevents/radiology "
            "charttime of the stay. Candidates are specific lab labels and "
            "radiology exam_name values, not POE CT Scan / Lab. Not gold."
        ),
    }
    content_hash = _hash({key: value for key, value in content.items() if key != "content_sha256"})
    content["content_sha256"] = content_hash
    _write_json(output_dir / "content_manifest.json", content)
    _write_json(output_dir / "corpus_manifest.json", {
        **content,
        "output_dir": str(output_dir),
        "trace_count": len(traces),
    })
    return CorpusBuildResult(output_dir, content)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build the 1,000-admission methodology decision corpus.")
    parser.add_argument("--events", type=Path, default=DEFAULT_EVENTS)
    parser.add_argument("--traceable", type=Path, default=DEFAULT_TRACEABLE)
    parser.add_argument("--raw-source", type=Path, default=DEFAULT_RAW_SOURCE)
    parser.add_argument("--split", type=Path, default=DEFAULT_SPLIT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--max-hadms", type=int)
    return parser


def main() -> int:
    args = _parser().parse_args()
    result = build_corpus_from_parquet(
        args.events,
        args.output_dir,
        traceable_path=args.traceable if args.traceable.is_file() else None,
        raw_source_path=args.raw_source if args.raw_source.is_file() else None,
        split_path=args.split if args.split.is_file() else None,
        max_hadms=args.max_hadms,
    )
    print(json.dumps(result.manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
