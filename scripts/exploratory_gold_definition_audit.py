"""Compare EHR-observable Gold definition ingredients in exploratory data."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq


ORDER_KINDS = {"clinical_ordered", "laboratory_ordered", "imaging_ordered"}
RESULT_KINDS = {"laboratory_resulted", "microbiology_resulted", "imaging_reported"}
TARGET_KINDS = ORDER_KINDS | RESULT_KINDS


def label(value: Any) -> str:
    return "<NULL>" if value in (None, "") else str(value)


def audit(source_root: Path, *, batch_size: int = 100_000) -> dict[str, Any]:
    path = source_root / "normalized_events.parquet"
    if not path.is_file():
        raise FileNotFoundError(path)
    columns = ["event_kind", "lifecycle_action", "status", "evidence_phase", "normalization_status", "unit_normalization_status", "time_resolution_status", "source_table", "entity_type", "source_label", "preferred_name", "concept_id"]
    kind_counts = Counter()
    dimensions: dict[str, Counter[str]] = defaultdict(Counter)
    labels: dict[str, Counter[str]] = defaultdict(Counter)
    concepts: dict[str, Counter[str]] = defaultdict(Counter)
    rows = 0
    for batch in pq.ParquetFile(path).iter_batches(batch_size=batch_size, columns=columns):
        data = batch.to_pydict()
        size = len(data["event_kind"])
        rows += size
        for index in range(size):
            kind = label(data["event_kind"][index])
            if kind not in TARGET_KINDS:
                continue
            kind_counts[kind] += 1
            for field in ("lifecycle_action", "status", "evidence_phase", "normalization_status", "unit_normalization_status", "time_resolution_status", "source_table", "entity_type"):
                dimensions[f"{kind}.{field}"][label(data[field][index])] += 1
            source_label = data["source_label"][index]
            preferred_name = data["preferred_name"][index]
            concept = data["concept_id"][index]
            labels[kind][label(preferred_name if preferred_name not in (None, "") else source_label)] += 1
            if concept not in (None, ""):
                concepts[kind][str(concept)] += 1
    definitions = {
        "observed_order_category": {
            "include": "event_kind in clinical_ordered/laboratory_ordered/imaging_ordered; source_event; resolved time",
            "answer_granularity": "category only unless source label is clinically reviewed",
            "known_blockers": ["clinical_ordered and laboratory_ordered have no normalized concept in E1", "lifecycle cancellation must be excluded"],
        },
        "normalized_result_observation": {
            "include": "event_kind in laboratory_resulted/microbiology_resulted/imaging_reported; mapped; resolved time; source_event",
            "answer_granularity": "normalized result/test concept",
            "known_blockers": ["result is not an order and cannot be used as a behavioral order gold", "result availability must not enter pre-index evidence"],
        },
        "order_with_result_confirmation": {
            "include": "an eligible order linked to a later same-group result within target window",
            "answer_granularity": "requires stable order-result grouping key not yet proven by this audit",
            "known_blockers": ["must not invent specimen_received_time", "requires source grouping and target/evidence overlap audit"],
        },
    }
    return {
        "audit_schema": "exploratory-gold-definition-audit/1.0.0",
        "source_root": source_root.as_posix(),
        "source_row_count": rows,
        "target_kind_counts": dict(sorted(kind_counts.items())),
        "dimensions": {key: [{"value": value, "rows": count} for value, count in counter.most_common(100)] for key, counter in sorted(dimensions.items())},
        "top_labels": {key: [{"value": value, "rows": count} for value, count in counter.most_common(100)] for key, counter in sorted(labels.items())},
        "top_concepts": {key: [{"value": value, "rows": count} for value, count in counter.most_common(100)] for key, counter in sorted(concepts.items())},
        "candidate_definitions": definitions,
        "formal_final_test": {"enabled": False, "reason": "exploratory_only_source_audit"},
    }


def write_report(result: dict[str, Any], json_path: Path, markdown_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# E2 EHR-observable Gold 候选定义审计",
        "",
        "> 本阶段只比较 EHR 可观测定义，不发布 formal gold。",
        "",
        "## 候选定义",
        "",
        "| 候选 | 可观测单位 | 当前主要门禁 |",
        "|---|---|---|",
        "| `observed_order_category` | order event/category | clinical/laboratory order 缺少 normalized concept；取消和无效生命周期需排除 |",
        "| `normalized_result_observation` | mapped result/test concept | 结果不是订单；结果可用时间不能进入 index 前 evidence |",
        "| `order_with_result_confirmation` | order + later result | 需要稳定 grouping key；不能虚构 specimen received time |",
        "",
        "## 目标事件规模",
        "",
    ]
    for kind, count in result["target_kind_counts"].items():
        lines.append(f"- `{kind}`：`{count:,}` 行")
    lines += [
        "",
        "## 初步选择原则",
        "",
        "1. 行为 Gold 优先使用 source event 的有效订单，不用结果行替代订单；",
        "2. 细粒度答案必须有稳定 concept 或经过人工冻结的 source label；",
        "3. 取消、discontinue、inactive 订单不能直接算有效 target；",
        "4. 结果确认可作为独立敏感性定义，但不能与 order Gold 混称；",
        "5. 下一阶段按 decision/encounter 构造唯一 target，评估覆盖、拒答和 evidence 泄漏。",
        "",
        "详细生命周期、标签和 concept 计数见同目录 JSON。",
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
    print(json.dumps({"target_kind_counts": result["target_kind_counts"], "json_output": str(args.json_output), "markdown_output": str(args.markdown_output)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
