"""Audit the normalization source for exploratory EHR-observable Gold design.

The audit is read-only with respect to the source parquet files. It records
coverage and ambiguity; it does not create a formal split or a clinical gold.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq


ORDER_KINDS = {"clinical_ordered", "laboratory_ordered", "imaging_ordered"}
RESULT_KINDS = {"laboratory_resulted", "microbiology_resulted", "imaging_reported"}
TARGET_KINDS = ORDER_KINDS | RESULT_KINDS
COUNT_FIELDS = ("event_kind", "lifecycle_action", "status", "evidence_phase", "normalization_status", "unit_normalization_status", "time_resolution_status", "entity_type", "source_module", "source_table")


def _value(value: Any) -> str:
    return "<NULL>" if value in (None, "") else str(value)


def _parse(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value)
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit(source_root: Path, *, batch_size: int = 100_000) -> dict[str, Any]:
    parquet = source_root / "normalized_events.parquet"
    manifest_path = source_root / "normalization_manifest.json"
    if not parquet.is_file() or not manifest_path.is_file():
        raise FileNotFoundError(f"normalization source is incomplete: {source_root}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    columns = ["subject_id", "hadm_id", "encounter_id", *COUNT_FIELDS, "event_time", "available_time", "source_available_time", "recorded_time", "concept_id", "preferred_name"]
    counters = {field: Counter() for field in COUNT_FIELDS}
    unique = {"subject_id": set(), "hadm_id": set(), "encounter_id": set()}
    kind_metrics: dict[str, dict[str, Any]] = defaultdict(lambda: {"rows": 0, "mapped_rows": 0, "source_event_rows": 0, "post_hoc_rows": 0, "resolved_time_rows": 0, "event_time_rows": 0, "available_time_rows": 0, "available_before_or_at_event_rows": 0, "concept_rows": 0, "concept_ids": set(), "subject_ids": set()})
    rows = 0
    for batch in pq.ParquetFile(parquet).iter_batches(batch_size=batch_size, columns=columns):
        data = batch.to_pydict()
        size = len(data["subject_id"])
        rows += size
        for index in range(size):
            for field in ("subject_id", "hadm_id", "encounter_id"):
                value = data[field][index]
                if value not in (None, ""):
                    unique[field].add(value)
            for field in COUNT_FIELDS:
                counters[field][_value(data[field][index])] += 1
            kind = _value(data["event_kind"][index])
            metric = kind_metrics[kind]
            metric["rows"] += 1
            if data["normalization_status"][index] == "mapped":
                metric["mapped_rows"] += 1
            if data["evidence_phase"][index] == "source_event":
                metric["source_event_rows"] += 1
            if data["evidence_phase"][index] == "post_hoc":
                metric["post_hoc_rows"] += 1
            if data["time_resolution_status"][index] == "resolved":
                metric["resolved_time_rows"] += 1
            event_time = _parse(data["event_time"][index])
            available_time = _parse(data["available_time"][index])
            if event_time is not None:
                metric["event_time_rows"] += 1
            if available_time is not None:
                metric["available_time_rows"] += 1
            if event_time is not None and available_time is not None and available_time <= event_time:
                metric["available_before_or_at_event_rows"] += 1
            if kind in TARGET_KINDS:
                subject = data["subject_id"][index]
                concept = data["concept_id"][index]
                if concept not in (None, ""):
                    metric["concept_rows"] += 1
                    metric["concept_ids"].add(concept)
                if subject not in (None, ""):
                    metric["subject_ids"].add(subject)
    for metric in kind_metrics.values():
        metric["concept_ids"] = len(metric["concept_ids"])
        metric["subject_ids"] = len(metric["subject_ids"])
    def top(counter: Counter[str], limit: int = 100) -> list[dict[str, Any]]:
        return [{"value": value, "rows": count} for value, count in counter.most_common(limit)]
    output = {
        "audit_schema": "exploratory-normalization-source-audit/1.0.0",
        "source_root": source_root.as_posix(),
        "source_manifest": manifest,
        "source_sha256": _sha256(parquet),
        "row_count": rows,
        "unique_subjects": len(unique["subject_id"]),
        "unique_hadm": len(unique["hadm_id"]),
        "unique_encounters": len(unique["encounter_id"]),
        "counts": {field: top(counter) for field, counter in counters.items()},
        "event_kind_metrics": {kind: metric for kind, metric in sorted(kind_metrics.items())},
        "target_kind_groups": {"order_kinds": sorted(ORDER_KINDS), "result_kinds": sorted(RESULT_KINDS)},
        "formal_final_test": {"enabled": False, "reason": "exploratory_only_source_audit"},
    }
    return output


def write_report(output: dict[str, Any], json_path: Path, markdown_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    counts = output["counts"]
    kinds = output["event_kind_metrics"]
    lines = [
        "# E1 normalization 数据源探索性审计",
        "",
        "> 本报告只用于 EHR-observable Gold 方法学探索，不是 official final-test，也不产生临床 gold。",
        "",
        "## 数据规模",
        "",
        f"- 事件行：`{output['row_count']:,}`",
        f"- 主体：`{output['unique_subjects']:,}`；hadm：`{output['unique_hadm']:,}`；encounter：`{output['unique_encounters']:,}`",
        f"- normalized_events SHA-256：`{output['source_sha256']}`",
        "",
        "## Gold 候选相关事件",
        "",
        "| event_kind | rows | mapped | source_event | post_hoc | resolved time | concept 数 | subject 数 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for kind in sorted(ORDER_KINDS | RESULT_KINDS):
        metric = kinds.get(kind, {})
        lines.append(f"| `{kind}` | {metric.get('rows', 0):,} | {metric.get('mapped_rows', 0):,} | {metric.get('source_event_rows', 0):,} | {metric.get('post_hoc_rows', 0):,} | {metric.get('resolved_time_rows', 0):,} | {metric.get('concept_ids', 0):,} | {metric.get('subject_ids', 0):,} |")
    lines += [
        "",
        "## 初步门禁结论",
        "",
        "1. `post_hoc` 事件不能进入 query evidence；只能作为后验审计信息。",
        "2. `normalization_status=unresolved` 不能静默转为可答候选；需要拒答或进入 review queue。",
        "3. order 与 result 必须分开定义，不能用结果行替代订单行为 Gold。",
        "4. 下一阶段需在 decision-level 构造候选 Gold，检查唯一性、target/evidence overlap、取消/无效订单和同主体重复。",
        "",
        "详细计数见同目录 JSON 审计产物。",
    ]
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=100_000)
    args = parser.parse_args()
    result = audit(args.source_root, batch_size=args.batch_size)
    write_report(result, args.json_output, args.markdown_output)
    print(json.dumps({"row_count": result["row_count"], "unique_subjects": result["unique_subjects"], "unique_hadm": result["unique_hadm"], "unique_encounters": result["unique_encounters"], "json_output": str(args.json_output), "markdown_output": str(args.markdown_output)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
