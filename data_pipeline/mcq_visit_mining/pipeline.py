"""Mine one family at a time. Never mix families in one feature/outcome table."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from data_pipeline.mcq_visit_extract.atomic import (
    atomic_write_json,
    atomic_write_jsonl,
    canonical_hash,
    file_sha256,
    read_manifest,
    write_manifest,
)

from .catalog import load_config
from .families import FAMILY_IDS, IsolationError, contract_for
from .io import load_events_by_hadm, load_facts
from .mine import mine_family
from .report import write_family_report
from .transactions import build_transaction

EVENT_COLUMNS = [
    "hadm_id",
    "event_kind",
    "occurrence_time",
    "available_time",
    "time_missing",
    "standard_name",
    "mapping_status",
    "itemid",
    "category_only",
    "flag",
    "source_field",
]

FAMILIES_NEEDING_EVENTS = {
    "type1_investigation",
    "type2_diagnosis",
    "type3_medication",
    "type3_procedure",
}


class MiningError(ValueError):
    pass


def _assert_output_dir(output_dir: Path, timeline_dir: Path) -> Path:
    output_dir = output_dir.resolve()
    timeline_dir = timeline_dir.resolve()
    if output_dir == timeline_dir or timeline_dir in output_dir.parents:
        raise MiningError("refusing to write into the timeline directory")
    return output_dir


def _timeline_fingerprint(timeline_dir: Path) -> dict[str, str]:
    summary = timeline_dir / "summary.json"
    manifest = timeline_dir / "manifest.json"
    payload = {}
    if summary.is_file():
        payload["summary_sha256"] = file_sha256(summary)
    if manifest.is_file():
        payload["manifest_sha256"] = file_sha256(manifest)
    events = timeline_dir / "visit_events.parquet"
    facts = timeline_dir / "presentation_facts.jsonl"
    if events.is_file():
        payload["events_sha256"] = file_sha256(events)
    if facts.is_file():
        payload["facts_sha256"] = file_sha256(facts)
    return payload


def run_family(
    *,
    timeline_dir: Path,
    output_dir: Path,
    config_dir: Path,
    family: str,
    profile: str,
    expected_count: int,
    allow_posthoc_diagnosis: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    if family not in FAMILY_IDS:
        raise MiningError(f"unknown family {family}")
    if profile not in {"strict", "exploratory"}:
        raise MiningError("profile must be strict or exploratory")
    output_dir = _assert_output_dir(output_dir, timeline_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    config = load_config(config_dir)
    thresholds = (config["thresholds"].get("profiles") or {}).get(profile)
    if not isinstance(thresholds, dict):
        raise MiningError(f"missing thresholds profile {profile}")
    windows = (config["windows"].get("families") or {}).get(family)
    if not isinstance(windows, dict):
        raise MiningError(f"missing window config for {family}")

    contract = contract_for(family, allow_posthoc_diagnosis=allow_posthoc_diagnosis)
    identity = {
        "family": family,
        "profile": profile,
        "expected_count": expected_count,
        "limit": limit,
        "allow_posthoc_diagnosis": allow_posthoc_diagnosis,
        "timeline": _timeline_fingerprint(timeline_dir),
        "config_sha256": config["sha256"],
        "window_id": windows.get("window_id"),
    }
    identity_sha = canonical_hash(identity)
    manifest_path = output_dir / "mining_manifest.json"
    existing = read_manifest(manifest_path)
    if existing is not None and existing.get("identity_sha256") != identity_sha:
        raise MiningError("manifest identity mismatch; refusing to mix family/profile/input")
    if existing is not None and existing.get("status") == "complete":
        return existing

    facts = load_facts(timeline_dir)
    if limit is not None:
        facts = facts[:limit]
    target = limit if limit is not None else expected_count
    if len(facts) != target:
        raise MiningError(f"facts {len(facts)} != expected {target}")

    events_by_hadm: dict[str, list[dict[str, Any]]] = {}
    if family in FAMILIES_NEEDING_EVENTS:
        events_by_hadm = load_events_by_hadm(timeline_dir, columns=EVENT_COLUMNS)

    transactions: list[dict[str, Any]] = []
    for row in facts:
        hadm_id = str(row.get("hadm_id") or "").strip()
        events = events_by_hadm.get(hadm_id, []) if family in FAMILIES_NEEDING_EVENTS else []
        transactions.append(
            build_transaction(
                row,
                events,
                contract=contract,
                window=windows,
                vital_spec=config["vitals"],
                high_signal_itemids=config["high_signal_itemids"],
                skip_poe_category_only=bool(config["catalog"].get("skip_poe_category_only", True)),
            )
        )

    accepted, rejected, summary = mine_family(
        transactions,
        family=family,
        window_id=str(windows.get("window_id")),
        profile=profile,
        thresholds=thresholds,
        catalog_sha256=config["sha256"]["catalog"],
        posthoc_flags=list(contract.posthoc_flags),
    )
    atomic_write_jsonl(output_dir / "visit_transactions.jsonl", transactions)
    atomic_write_jsonl(output_dir / "conditional_rules.jsonl", accepted)
    atomic_write_jsonl(output_dir / "conditional_rules_rejected.jsonl", rejected)
    catalog_snapshot = {
        "family": family,
        "allowed_feature_types": sorted(contract.allowed_feature_types),
        "forbidden_feature_types": sorted(contract.forbidden_feature_types),
        "posthoc_flags": list(contract.posthoc_flags),
        "window": windows,
        "high_signal_itemids": sorted(config["high_signal_itemids"]),
    }
    atomic_write_json(output_dir / "catalog_snapshot.json", catalog_snapshot)
    summary.update(
        {
            "gold": 0,
            "status": "exploratory_unreviewed",
            "isolation": catalog_snapshot,
            "transactions_sha256": file_sha256(output_dir / "visit_transactions.jsonl"),
            "accepted_sha256": file_sha256(output_dir / "conditional_rules.jsonl"),
            "rejected_sha256": file_sha256(output_dir / "conditional_rules_rejected.jsonl"),
        }
    )
    atomic_write_json(output_dir / "summary.json", summary)
    write_family_report(output_dir / "report.html", summary, accepted)
    manifest = {
        "identity": identity,
        "identity_sha256": identity_sha,
        "status": "complete",
        "summary": summary,
        "gold": 0,
        "evaluation_status": "exploratory_unreviewed",
    }
    write_manifest(manifest_path, manifest)
    return manifest


def run_all(**kwargs: Any) -> dict[str, Any]:
    output_root: Path = kwargs.pop("output_dir")
    families = list(FAMILY_IDS)
    results: dict[str, Any] = {"families": {}}
    for family in families:
        family_dir = output_root / family
        print(f"mcq_visit_mining family={family} -> {family_dir}")
        results["families"][family] = run_family(output_dir=family_dir, family=family, **kwargs)
    results["status"] = "complete"
    results["gold"] = 0
    atomic_write_json(output_root / "all_families_summary.json", {
        family: (payload.get("summary") or {})
        for family, payload in results["families"].items()
    })
    return results


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Mine one MCQ family from a visit timeline. Run families separately; no leakage."
    )
    parser.add_argument("--timeline-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--config-dir", type=Path, default=Path("config/mcq_visit_mining"))
    parser.add_argument("--family", required=True, help="one of the six families, or all")
    parser.add_argument("--profile", choices=("strict", "exploratory"), default="strict")
    parser.add_argument("--expected-count", type=int, required=True)
    parser.add_argument(
        "--allow-posthoc-diagnosis",
        action="store_true",
        help="type3/4/5 only; adds discharge ICD into X and tags uses_posthoc_diagnosis",
    )
    parser.add_argument("--limit", type=int, help="smoke: first N facts")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    kwargs = {
        "timeline_dir": args.timeline_dir,
        "output_dir": args.output_dir,
        "config_dir": args.config_dir,
        "profile": args.profile,
        "expected_count": args.expected_count,
        "allow_posthoc_diagnosis": args.allow_posthoc_diagnosis,
        "limit": args.limit,
    }
    try:
        if args.family == "all":
            if args.allow_posthoc_diagnosis:
                raise MiningError("--allow-posthoc-diagnosis is not valid with --family all; run type3/4/5 separately")
            result = run_all(**kwargs)
            for family, payload in (result.get("families") or {}).items():
                summary = payload.get("summary") or {}
                print(
                    f"{family}: accepted={summary.get('accepted')} "
                    f"rejected={summary.get('rejected')} tested={summary.get('tested_pairs')}"
                )
            return 0
        manifest = run_family(family=args.family, **kwargs)
    except (MiningError, IsolationError, ValueError, FileNotFoundError) as exc:
        print(f"mcq_visit_mining failed: {exc}")
        return 1
    summary = manifest.get("summary") or {}
    print(
        f"complete family={args.family} accepted={summary.get('accepted')} "
        f"rejected={summary.get('rejected')} output={args.output_dir}"
    )
    return 0
