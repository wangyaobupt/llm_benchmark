"""Audit exploratory Gold coverage, uniqueness, and timing leakage."""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timedelta
import json
from pathlib import Path
from typing import Any

import pyarrow.compute as pc
import pyarrow.dataset as ds


ORDER_KINDS = {"clinical_ordered", "laboratory_ordered", "imaging_ordered"}
RESULT_KINDS = {"laboratory_resulted", "microbiology_resulted", "imaging_reported"}
TARGET_KINDS = ORDER_KINDS | RESULT_KINDS


def parse_time(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def key_for(row: dict[str, Any]) -> str | None:
    for field in ("concept_id", "preferred_name", "source_label"):
        value = row.get(field)
        if value not in (None, ""):
            return f"{field}:{value}"
    return None


def empty_metric() -> dict[str, Any]:
    return {"eligible_rows": 0, "eligible_encounters": set(), "candidate_keys": defaultdict(set), "missing_candidate_key_rows": 0, "time_leakage_rows": 0, "unknown_available_time_rows": 0, "partially_resolved_rows": 0, "inactive_rows": 0, "discontinued_rows": 0}


def finalize(metric: dict[str, Any], boundary_count: int) -> dict[str, Any]:
    candidate_counts = [len(keys) for keys in metric["candidate_keys"].values()]
    eligible_encounters = len(metric["eligible_encounters"])
    return {
        "boundary_encounters": boundary_count,
        "eligible_rows": metric["eligible_rows"],
        "eligible_encounters": eligible_encounters,
        "coverage_rate": eligible_encounters / boundary_count if boundary_count else 0.0,
        "zero_candidate_encounters": boundary_count - eligible_encounters,
        "unique_candidate_encounters": sum(count == 1 for count in candidate_counts),
        "multi_candidate_encounters": sum(count > 1 for count in candidate_counts),
        "unique_candidate_rate_among_eligible": (sum(count == 1 for count in candidate_counts) / eligible_encounters) if eligible_encounters else 0.0,
        "missing_candidate_key_rows": metric["missing_candidate_key_rows"],
        "time_leakage_rows": metric["time_leakage_rows"],
        "unknown_available_time_rows": metric["unknown_available_time_rows"],
        "partially_resolved_rows": metric["partially_resolved_rows"],
        "inactive_rows": metric["inactive_rows"],
        "discontinued_rows": metric["discontinued_rows"],
    }


def audit(source_root: Path, *, window_hours: int = 24, batch_size: int = 100_000) -> dict[str, Any]:
    dataset = ds.dataset(source_root / "normalized_events.parquet", format="parquet")
    boundary: dict[str, tuple[str, datetime]] = {}
    boundary_scanner = dataset.scanner(columns=["subject_id", "encounter_id", "status", "event_time"], filter=(pc.field("event_kind") == "patient_transferred"), batch_size=batch_size)
    for batch in boundary_scanner.to_batches():
        data = batch.to_pydict()
        for index, status in enumerate(data["status"]):
            if status not in {"ED", "admit"}:
                continue
            encounter = data["encounter_id"][index]
            event_time = parse_time(data["event_time"][index])
            subject = data["subject_id"][index]
            if encounter in (None, "") or subject in (None, "") or event_time is None:
                continue
            prior = boundary.get(encounter)
            if prior is None or event_time < prior[1]:
                boundary[encounter] = (subject, event_time)
    metrics: dict[str, dict[str, Any]] = {}
    definitions = {
        "order_create_any_status": lambda row: row["event_kind"] in ORDER_KINDS and row["lifecycle_action"] == "create" and row["evidence_phase"] == "source_event" and row["time_resolution_status"] == "resolved",
        "order_create_active_only": lambda row: row["event_kind"] in ORDER_KINDS and row["lifecycle_action"] == "create" and row["status"] == "Active" and row["evidence_phase"] == "source_event" and row["time_resolution_status"] == "resolved",
        "normalized_result": lambda row: row["event_kind"] in RESULT_KINDS and row["normalization_status"] == "mapped" and row["evidence_phase"] == "source_event" and row["time_resolution_status"] == "resolved",
        "mapped_imaging_order": lambda row: row["event_kind"] == "imaging_ordered" and row["normalization_status"] == "mapped" and row["lifecycle_action"] == "create" and row["evidence_phase"] == "source_event" and row["time_resolution_status"] == "resolved",
    }
    for name in definitions:
        metrics[name] = empty_metric()
    columns = ["subject_id", "encounter_id", "event_kind", "lifecycle_action", "status", "evidence_phase", "normalization_status", "time_resolution_status", "event_time", "available_time", "concept_id", "preferred_name", "source_label"]
    target_filter = pc.field("event_kind").isin(sorted(TARGET_KINDS))
    scanner = dataset.scanner(columns=columns, filter=target_filter, batch_size=batch_size)
    for batch in scanner.to_batches():
        data = batch.to_pydict()
        size = len(data["encounter_id"])
        for index in range(size):
            encounter = data["encounter_id"][index]
            if encounter not in boundary:
                continue
            _, index_time = boundary[encounter]
            event_time = parse_time(data["event_time"][index])
            if event_time is None or event_time < index_time or event_time > index_time + timedelta(hours=window_hours):
                continue
            row = {field: data[field][index] for field in columns}
            candidate_key = key_for(row)
            available_time = parse_time(row["available_time"])
            for name, predicate in definitions.items():
                if not predicate(row):
                    continue
                metric = metrics[name]
                metric["eligible_rows"] += 1
                metric["eligible_encounters"].add(encounter)
                if candidate_key is None:
                    metric["missing_candidate_key_rows"] += 1
                else:
                    metric["candidate_keys"][encounter].add(candidate_key)
                if available_time is not None and available_time <= index_time:
                    metric["time_leakage_rows"] += 1
                if available_time is None:
                    metric["unknown_available_time_rows"] += 1
                if row["time_resolution_status"] == "partially_resolved":
                    metric["partially_resolved_rows"] += 1
                if row["status"] == "Inactive":
                    metric["inactive_rows"] += 1
                if row["lifecycle_action"] == "discontinue":
                    metric["discontinued_rows"] += 1
    return {
        "audit_schema": "exploratory-gold-coverage-audit/1.0.0",
        "source_root": source_root.as_posix(),
        "index_definition": "earliest patient_transferred status ED/admit event_time per encounter",
        "target_window_hours": window_hours,
        "boundary_encounters": len(boundary),
        "boundary_subjects": len({subject for subject, _ in boundary.values()}),
        "boundary_available_time_missing": True,
        "definitions": {name: finalize(metric, len(boundary)) for name, metric in metrics.items()},
        "formal_final_test": {"enabled": False, "reason": "exploratory_only_source_audit"},
    }


def write_report(result: dict[str, Any], json_path: Path, markdown_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# E3 EHR-observable Gold 覆盖与泄漏审计",
        "",
        "> 这是 encounter-level 探索性审计，不是 frozen protocol 或 official final-test。",
        "",
        f"- 探索性 index：每个 encounter 最早的 `patient_transferred`（`ED/admit`）`event_time`。",
        f"- target window：index 后 `{result['target_window_hours']}` 小时。",
        f"- 边界 encounter：`{result['boundary_encounters']:,}`；边界 `available_time` 缺失，因此未伪造该字段。",
        "",
        "| 定义 | eligible rows | encounter coverage | unique-answer rate | missing key | availability unknown | time leakage |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, metric in result["definitions"].items():
        lines.append(f"| `{name}` | {metric['eligible_rows']:,} | {metric['coverage_rate']:.3%} | {metric['unique_candidate_rate_among_eligible']:.3%} | {metric['missing_candidate_key_rows']:,} | {metric['unknown_available_time_rows']:,} | {metric['time_leakage_rows']:,} |")
    lines += [
        "",
        "## 解释边界",
        "",
        "- `order_create_any_status` 不能直接视为有效订单 Gold：当前数据中大量订单为 `Inactive`，需单独审核生命周期语义。",
        "- `order_create_active_only` 是严格定义，若覆盖过低应拒答，而不是回退到 Inactive。",
        "- `normalized_result` 是可观测结果定义，不等于 observed order；可作为敏感性 Gold，不得改名为订单 Gold。",
        "- `mapped_imaging_order` 的 100% unique-answer rate 是退化结果：E2 显示全局只有一个 normalized imaging concept，不能据此判定 Gold 合适。",
        "- 任一候选的 time leakage、missing key、multi-candidate 和 zero-candidate 都必须保留在 decision manifest。",
        "",
        "详细计数见同目录 JSON。",
    ]
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--batch-size", type=int, default=100_000)
    args = parser.parse_args()
    result = audit(args.source_root, window_hours=args.window_hours, batch_size=args.batch_size)
    write_report(result, args.json_output, args.markdown_output)
    print(json.dumps({"boundary_encounters": result["boundary_encounters"], "definitions": result["definitions"], "json_output": str(args.json_output), "markdown_output": str(args.markdown_output)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
