"""Stream validation for the frozen visit archive without emitting patient data."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .schema import validate_visit_archive
from .snapshots import QUESTION_TYPES, validate_snapshot_evidence


def validate_archive(path: Path) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    snapshot_ready: Counter[str] = Counter()
    snapshot_evidence: Counter[str] = Counter()
    subject_partitions: dict[str, str] = {}
    partition_conflicts = 0
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for raw_line in handle:
            digest.update(raw_line)
            counts["records"] += 1
            try:
                record = json.loads(raw_line)
                validate_visit_archive(record)
            except Exception:
                counts["invalid_records"] += 1
                continue

            subject_id = record["identifiers"]["subject_id"]
            partition = record["partition"]["name"]
            prior = subject_partitions.setdefault(subject_id, partition)
            if prior != partition:
                partition_conflicts += 1

            _count_repairs(record, counts)
            for snapshot in record["decision_snapshots"]:
                question_type = snapshot["question_type"]
                if snapshot["status"] == "ready":
                    validate_snapshot_evidence(snapshot, snapshot.get("evidence", []))
                    snapshot_ready[question_type] += 1
                    snapshot_evidence[question_type] += len(snapshot.get("evidence", []))

    return {
        "file": path.name,
        "sha256": digest.hexdigest().upper(),
        "records": counts["records"],
        "invalid_records": counts["invalid_records"],
        "patient_partition_conflicts": partition_conflicts,
        "coverage": {key: counts[key] for key in (
            "triage_chief_complaint", "retrospective_chief_complaint",
            "provider_orders", "provider_order_details", "emar_details",
            "baseline", "ed_disposition", "icu_metadata",
            "cardiology", "respiratory",
        )},
        "snapshot_ready": {kind: snapshot_ready[kind] for kind in QUESTION_TYPES},
        "snapshot_evidence_refs": {kind: snapshot_evidence[kind] for kind in QUESTION_TYPES},
    }


def _count_repairs(record: dict[str, Any], counts: Counter[str]) -> None:
    if record["presentation"]["triage_chief_complaint"].get("text"):
        counts["triage_chief_complaint"] += 1
    if record["presentation"]["discharge_summary_retrospective"].get("chief_complaint"):
        counts["retrospective_chief_complaint"] += 1
    orders = record["orders"]["provider_orders"]
    if orders:
        counts["provider_orders"] += 1
    if any(item.get("details") for item in orders):
        counts["provider_order_details"] += 1
    if any(item.get("details") for item in record["treatments"]["medication_administrations"]):
        counts["emar_details"] += 1
    if any(record["demographics"]["baseline"].values()):
        counts["baseline"] += 1
    if record["care_path"]["ed"].get("disposition"):
        counts["ed_disposition"] += 1
    if any(item.get("first_careunit") or item.get("last_careunit") or item.get("los") is not None
           for item in record["care_path"]["icu_stays"]):
        counts["icu_metadata"] += 1
    if record["investigations"]["cardiology"]:
        counts["cardiology"] += 1
    if record["investigations"]["respiratory"]:
        counts["respiratory"] += 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate frozen visit archive JSONL")
    parser.add_argument("path", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = validate_archive(args.path)
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload + "\n", encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
