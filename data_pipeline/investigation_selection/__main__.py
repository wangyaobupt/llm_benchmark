"""Project time-point investigation actions from an existing event extract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .actions import project_actions_from_facts
from .audit import poe_lifecycle_audit, poe_subtype_audit
from .episodes import build_investigation_episodes
from .facts import build_investigation_facts, public_fact_rows
from .io import infer_hadm_id, load_events
from .query import build_timepoint_trace, list_investigations_at


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Lift POE chain / eligibility fields and list investigations at a "
            "time point. Reads an existing event extract; does not rerun event_pipeline."
        )
    )
    parser.add_argument("input", type=Path, help="Event extract JSON (events or event_groups)")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--hadm-id")
    parser.add_argument("--index-time", help="ISO time for a single time-point trace")
    parser.add_argument("--query-hours", type=int, default=4)
    parser.add_argument("--burst-minutes", type=int, default=15)
    return parser


def main() -> int:
    args = _parser().parse_args()
    events = load_events(args.input)
    hadm_id = infer_hadm_id(events, args.hadm_id)
    fact_result = build_investigation_facts(events)
    action_result = project_actions_from_facts(fact_result)
    episode_result = build_investigation_episodes(action_result.actions)
    output = Path(args.output_dir)
    _write_json(output / "investigation_facts.json", {
        "hadm_id": hadm_id,
        "schema_version": "investigation-facts/1.0.0",
        "metrics": fact_result.metrics,
        "facts": public_fact_rows(fact_result.facts),
        "exclusions": fact_result.exclusions,
    })
    _write_json(output / "investigation_actions.json", {
        "hadm_id": hadm_id,
        "metrics": action_result.metrics,
        "actions": action_result.actions,
        "exclusions": action_result.exclusions,
    })
    _write_json(output / "investigation_episodes.json", {
        "hadm_id": hadm_id,
        "metrics": episode_result.metrics,
        "episodes": episode_result.episodes,
        "catalog": episode_result.catalog,
        "exclusions": episode_result.exclusions,
    })
    _write_json(output / "poe-subtype-audit.json", poe_subtype_audit(action_result.actions))
    _write_json(output / "poe-lifecycle-audit.json", poe_lifecycle_audit(action_result.actions))
    if args.index_time:
        trace = build_timepoint_trace(
            events,
            hadm_id=hadm_id,
            index_time=args.index_time,
            query_hours=args.query_hours,
            burst_minutes=args.burst_minutes,
        )
        _write_json(output / "timepoint-trace.json", trace)
    else:
        creates = [
            row
            for row in action_result.actions
            if row.get("eligibility") == "eligible_investigation"
            and row.get("action") == "create"
            and row.get("track_id") != "lab_result_proxy"
            and row.get("event_time")
        ]
        traces = []
        for row in creates[:20]:
            traces.append(
                build_timepoint_trace(
                    events,
                    hadm_id=hadm_id,
                    index_time=str(row["event_time"]),
                    query_hours=args.query_hours,
                    burst_minutes=args.burst_minutes,
                )
            )
        _write_json(output / "timepoint-traces.json", traces)
        first = creates[0] if creates else None
        if first:
            at = list_investigations_at(
                events,
                hadm_id=hadm_id,
                index_time=str(first["event_time"]),
                burst_minutes=args.burst_minutes,
            )
            _write_json(output / "investigations-at-first-create.json", {
                "index_time": at.index_time,
                "investigations": at.investigations,
                "review_required": at.review_required,
                "metrics": at.metrics,
            })
    _write_json(output / "manifest.json", {
        "schema_version": "investigation-timepoint-extract/0.1.0",
        "input": str(args.input),
        "hadm_id": hadm_id,
        "action_metrics": action_result.metrics,
        "episode_metrics": episode_result.metrics,
        "fact_metrics": fact_result.metrics,
    })
    print(json.dumps({
        "output_dir": str(output),
        "hadm_id": hadm_id,
        **action_result.metrics,
        "facts": fact_result.metrics["facts"],
        "episodes": episode_result.metrics["episodes"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
