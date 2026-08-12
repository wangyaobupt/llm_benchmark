"""Generate a deterministic, human-reviewable normalization package."""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
import hashlib
import heapq
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from ..event_cleaning.validation import EventPipelineError
from ..event_normalization.io import remove_temporary, sha256_file, write_json
from ..event_normalization.terminology import normalized_text


REVIEW_CODE_VERSION = "normalization-human-review/1.0.0"
PARQUET_ROW_GROUP_SIZE = 5000
SANITY_ISSUE_CODES = (
    "event_mapping_missing",
    "mapped_event_missing_concept_id",
    "unresolved_event_has_concept_id",
    "category_only_event_mapped",
    "unresolved_unit_has_normalized_unit",
    "normalized_numeric_value_changed",
    "normalized_text_value_changed",
    "review_target_event_missing",
)

DECISION_SCHEMA = pa.schema(
    [
        ("review_id", pa.string()),
        ("priority_rank", pa.int32()),
        ("review_scope", pa.string()),
        ("review_reasons", pa.list_(pa.string())),
        ("entity_type", pa.string()),
        ("source_concept_id", pa.string()),
        ("normalized_source_label", pa.string()),
        ("source_label_example", pa.string()),
        ("concept_id", pa.string()),
        ("preferred_name", pa.string()),
        ("normalization_status", pa.string()),
        ("source_unit", pa.string()),
        ("normalized_unit", pa.string()),
        ("unit_normalization_status", pa.string()),
        ("mapping_rule", pa.string()),
        ("mapping_version", pa.string()),
        ("event_count", pa.int64()),
        ("first_event_id", pa.string()),
        ("review_status", pa.string()),
        ("decision", pa.string()),
        ("corrected_concept_id", pa.string()),
        ("corrected_preferred_name", pa.string()),
        ("reviewer", pa.string()),
        ("review_comment", pa.string()),
    ],
    metadata={b"schema": b"normalization_review_decisions/1.0.0"},
)

SAMPLE_SCHEMA = pa.schema(
    [
        ("review_sample_id", pa.string()),
        ("sample_reasons", pa.list_(pa.string())),
        ("event_id", pa.string()),
        ("subject_id", pa.string()),
        ("hadm_id", pa.string()),
        ("source_table", pa.string()),
        ("event_kind", pa.string()),
        ("entity_type", pa.string()),
        ("raw_row_ref", pa.string()),
        ("source_concept_id", pa.string()),
        ("source_label", pa.string()),
        ("concept_id", pa.string()),
        ("preferred_name", pa.string()),
        ("normalization_status", pa.string()),
        ("mapping_rule", pa.string()),
        ("content_specificity", pa.string()),
        ("value_numeric", pa.float64()),
        ("value_text", pa.string()),
        ("unit", pa.string()),
        ("normalized_value_numeric", pa.float64()),
        ("normalized_value_text", pa.string()),
        ("normalized_unit", pa.string()),
        ("unit_normalization_status", pa.string()),
        ("event_time", pa.string()),
        ("available_time", pa.string()),
        ("evidence_phase", pa.string()),
        ("quality_flags", pa.list_(pa.string())),
    ],
    metadata={b"schema": b"normalization_review_samples/1.0.0"},
)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _term_key(row: dict[str, Any], *, unit_field: str) -> tuple[str, str, str, str]:
    return (
        row.get("entity_type") or "<none>",
        row.get("source_concept_id") or "<none>",
        normalized_text(
            row.get("source_label") or row.get("source_label_example")
        )
        or "<missing>",
        row.get(unit_field) or "<none>",
    )


def _stable_id(prefix: str, value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return prefix + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _same_value(left: Any, right: Any) -> bool:
    if isinstance(left, float) and isinstance(right, float):
        if math.isnan(left) and math.isnan(right):
            return True
    return left == right


def _event_projection(
    event: dict[str, Any], mapping: dict[str, Any] | None
) -> dict[str, Any]:
    return {
        "review_sample_id": _stable_id("sample-", event["event_id"]),
        "sample_reasons": [],
        "event_id": event["event_id"],
        "subject_id": event.get("subject_id"),
        "hadm_id": event.get("hadm_id"),
        "source_table": event.get("source_table"),
        "event_kind": event.get("event_kind"),
        "entity_type": event.get("entity_type"),
        "raw_row_ref": event.get("raw_row_ref"),
        "source_concept_id": event.get("source_concept_id"),
        "source_label": event.get("source_label"),
        "concept_id": event.get("concept_id"),
        "preferred_name": event.get("preferred_name"),
        "normalization_status": event.get("normalization_status"),
        "mapping_rule": mapping.get("mapping_rule") if mapping else None,
        "content_specificity": event.get("content_specificity"),
        "value_numeric": event.get("value_numeric"),
        "value_text": event.get("value_text"),
        "unit": event.get("unit"),
        "normalized_value_numeric": event.get("normalized_value_numeric"),
        "normalized_value_text": event.get("normalized_value_text"),
        "normalized_unit": event.get("normalized_unit"),
        "unit_normalization_status": event.get("unit_normalization_status"),
        "event_time": event.get("event_time"),
        "available_time": event.get("available_time"),
        "evidence_phase": event.get("evidence_phase"),
        "quality_flags": event.get("quality_flags") or [],
    }


def _write_parquet(path: Path, rows: list[dict[str, Any]], schema: pa.Schema) -> None:
    pq.write_table(
        pa.Table.from_pylist(rows, schema=schema),
        path,
        compression="zstd",
        use_dictionary=True,
        write_statistics=True,
        row_group_size=PARQUET_ROW_GROUP_SIZE,
    )


def _write_decision_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [field.name for field in DECISION_SCHEMA]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            output = dict(row)
            output["review_reasons"] = "+".join(output["review_reasons"])
            writer.writerow(output)


def _checklist(summary: dict[str, Any]) -> str:
    counts = summary["counts"]
    return f"""# 归一化人工审阅清单

本目录由 `{REVIEW_CODE_VERSION}` 生成。自动硬门禁已经绑定当前 Parquet 的 SHA-256；它不能替代临床语义人工确认。

## 当前状态

- 自动审阅通过：`{str(summary['acceptance']['automated_review_passed']).lower()}`
- 人工审阅完成：`false`
- 归一化事件：{counts['normalized_events']:,}
- 映射术语：{counts['mapping_rows']:,}
- 必审术语：{counts['required_review_rows']:,}
- 高频抽审术语：{counts['sampled_review_rows']:,}
- 事件样本：{counts['event_samples']:,}

## 审阅顺序

1. 打开 `normalization_review_decisions.csv`，先按 `priority_rank`、`event_count` 升序/降序组合检查。
2. `priority_rank=0` 是无原生代码的文本规则映射，必须确认没有过度推断。
3. `priority_rank=1` 是术语或单位未解决项，决定保留 unresolved、纠正映射或拒绝。
4. `priority_rank=2` 是每类高频映射抽样，用于验证源代码、名称和单位。
5. 在 `normalization_review_samples.parquet` 找到对应 `first_event_id` 或事件样本，通过 `raw_row_ref` 回查源 JSONL。

## 决策填写规则

`decision` 只允许填写：

- `accepted`：当前映射或 unresolved 状态正确；
- `rejected`：当前映射错误，且暂不提供替代概念；
- `corrected`：填写 `corrected_concept_id` 和 `corrected_preferred_name`；
- `needs_evidence`：需要字典、术语库或临床专家补充证据。

同时填写 `reviewer` 和 `review_comment`。不要直接修改 cleaning、normalization 或 quality 目录中的原始产物。

## 硬性失败条件

- normalized 与 cleaned 的事件集合或不可变临床事实不一致；
- manifest 或质量报告 SHA-256 与当前文件不一致；
- `category_only` 被映射到具体概念；
- mapped 事件缺少 concept_id，或 unresolved 事件反而带有 concept_id；
- 数值或文本在仅做单位别名归一化时发生变化；
- raw_row_ref 无法回查。
"""


def generate_review_package(
    event_directory: Path,
    output_directory: Path | None = None,
    *,
    samples_per_stratum: int = 3,
    top_mappings_per_entity: int = 10,
) -> dict[str, Any]:
    """Build deterministic automated checks and human-review artifacts."""
    event_directory = Path(event_directory).resolve()
    output_directory = (
        Path(output_directory).resolve()
        if output_directory is not None
        else event_directory / "review"
    )
    if samples_per_stratum <= 0 or top_mappings_per_entity <= 0:
        raise EventPipelineError(
            "INVALID_REVIEW_SAMPLE_SIZE",
            "samples_per_stratum and top_mappings_per_entity must be positive",
        )
    if output_directory.exists():
        raise EventPipelineError("OUTPUT_ALREADY_EXISTS", str(output_directory))

    paths = {
        "cleaned_events.parquet": event_directory
        / "cleaning"
        / "cleaned_events.parquet",
        "term_inventory.parquet": event_directory
        / "cleaning"
        / "term_inventory.parquet",
        "normalized_events.parquet": event_directory
        / "normalization"
        / "normalized_events.parquet",
        "normalization_mappings.parquet": event_directory
        / "normalization"
        / "normalization_mappings.parquet",
        "normalization_review_queue.parquet": event_directory
        / "normalization"
        / "normalization_review_queue.parquet",
        "normalization_manifest.json": event_directory
        / "normalization"
        / "normalization_manifest.json",
        "normalization_audit.json": event_directory
        / "quality"
        / "normalized-events-acceptance-audit.json",
        "workflow_manifest.json": event_directory / "workflow_manifest.json",
    }
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise EventPipelineError(
            "NORMALIZATION_REVIEW_INPUT_MISSING", ",".join(sorted(missing))
        )

    manifest = _load_json(paths["normalization_manifest.json"])
    audit = _load_json(paths["normalization_audit.json"])
    workflow = _load_json(paths["workflow_manifest.json"])
    data_names = [
        "cleaned_events.parquet",
        "term_inventory.parquet",
        "normalized_events.parquet",
        "normalization_mappings.parquet",
        "normalization_review_queue.parquet",
    ]
    live_hashes = {name: sha256_file(paths[name]) for name in data_names}
    manifest_hashes = {
        "cleaned_events.parquet": manifest.get("inputs", {}).get(
            "cleaned_events_sha256"
        ),
        "term_inventory.parquet": manifest.get("inputs", {}).get(
            "term_inventory_sha256"
        ),
        **manifest.get("output_sha256", {}),
    }
    audit_hashes = audit.get("hashes", {})
    hard_gates = {
        "workflow_all_stages_accepted": all(
            workflow.get("acceptance", {}).get(name) is True
            for name in ("cleaning", "normalization", "reproducible")
        ),
        "normalization_audit_accepted": audit.get("acceptance", {}).get(
            "can_publish_normalization"
        )
        is True,
        "normalization_audit_has_no_issues": not audit.get("issues", {}).get(
            "counts"
        ),
        "live_hashes_match_manifest": all(
            live_hashes[name] == manifest_hashes.get(name) for name in data_names
        ),
        "live_hashes_match_normalization_audit": all(
            live_hashes[name] == audit_hashes.get(name) for name in data_names
        ),
        "event_row_count_equal": audit.get("event_invariants", {}).get(
            "same_row_count"
        )
        is True,
        "event_id_sequence_equal": audit.get("event_invariants", {}).get(
            "event_id_sequence_equal"
        )
        is True,
    }
    failed_before_sampling = [name for name, passed in hard_gates.items() if not passed]
    if failed_before_sampling:
        raise EventPipelineError(
            "NORMALIZATION_REVIEW_GATE_FAILED", ",".join(failed_before_sampling)
        )

    inventory = pq.read_table(paths["term_inventory.parquet"]).to_pylist()
    mappings = pq.read_table(paths["normalization_mappings.parquet"]).to_pylist()
    review_queue = pq.read_table(
        paths["normalization_review_queue.parquet"]
    ).to_pylist()
    inventory_by_key = {
        _term_key(row, unit_field="unit"): row for row in inventory
    }
    mappings_by_key = {
        _term_key(row, unit_field="source_unit"): row for row in mappings
    }
    review_by_key = {
        _term_key(row, unit_field="unit"): row for row in review_queue
    }

    mappings_by_entity: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for mapping in mappings:
        mappings_by_entity[mapping.get("entity_type") or "<none>"].append(mapping)
    high_impact_keys: set[tuple[str, str, str, str]] = set()
    for entity_mappings in mappings_by_entity.values():
        ranked = sorted(
            entity_mappings,
            key=lambda row: (
                -int(row.get("event_count") or 0),
                row.get("normalized_source_label") or "",
                row.get("source_concept_id") or "",
                row.get("source_unit") or "",
            ),
        )
        for mapping in ranked[:top_mappings_per_entity]:
            high_impact_keys.add(_term_key(mapping, unit_field="source_unit"))

    decisions: list[dict[str, Any]] = []
    targeted_event_reasons: dict[str, set[str]] = defaultdict(set)
    for mapping in mappings:
        key = _term_key(mapping, unit_field="source_unit")
        inventory_row = inventory_by_key.get(key)
        queue_row = review_by_key.get(key)
        reasons: list[str] = []
        if mapping.get("mapping_rule", "").startswith("reviewed-"):
            reasons.append("REVIEWED_TEXT_RULE")
        if mapping.get("normalization_status") == "unresolved":
            reasons.append("TERM_UNRESOLVED")
        if mapping.get("unit_normalization_status") == "unresolved":
            reasons.append("UNIT_UNRESOLVED")
        if mapping.get("mapping_rule") == "invalid-source-code":
            reasons.append("INVALID_SOURCE_CODE")
        if key in high_impact_keys and not reasons:
            reasons.append("HIGH_EVENT_COUNT_SAMPLE")
        if "REVIEWED_TEXT_RULE" in reasons:
            priority_rank = 0
            review_scope = "required"
        elif queue_row is not None:
            priority_rank = 1
            review_scope = "required"
        elif key in high_impact_keys:
            priority_rank = 2
            review_scope = "sampled"
        else:
            priority_rank = 3
            review_scope = "optional"
        first_event_id = (
            inventory_row.get("first_event_id") if inventory_row else None
        )
        if first_event_id and review_scope != "optional":
            for reason in reasons:
                targeted_event_reasons[first_event_id].add(reason)
        review_id = _stable_id(
            "mapping-",
            {
                "key": key,
                "mapping_version": mapping.get("mapping_version"),
            },
        )
        decisions.append(
            {
                "review_id": review_id,
                "priority_rank": priority_rank,
                "review_scope": review_scope,
                "review_reasons": sorted(set(reasons)),
                "entity_type": mapping.get("entity_type"),
                "source_concept_id": mapping.get("source_concept_id"),
                "normalized_source_label": mapping.get("normalized_source_label"),
                "source_label_example": mapping.get("source_label_example"),
                "concept_id": mapping.get("concept_id"),
                "preferred_name": mapping.get("preferred_name"),
                "normalization_status": mapping.get("normalization_status"),
                "source_unit": mapping.get("source_unit"),
                "normalized_unit": mapping.get("normalized_unit"),
                "unit_normalization_status": mapping.get(
                    "unit_normalization_status"
                ),
                "mapping_rule": mapping.get("mapping_rule"),
                "mapping_version": mapping.get("mapping_version"),
                "event_count": mapping.get("event_count"),
                "first_event_id": first_event_id,
                "review_status": (
                    "pending" if review_scope != "optional" else "not_selected"
                ),
                "decision": None,
                "corrected_concept_id": None,
                "corrected_preferred_name": None,
                "reviewer": None,
                "review_comment": None,
            }
        )
    decisions.sort(
        key=lambda row: (
            row["priority_rank"],
            -int(row.get("event_count") or 0),
            row["review_id"],
        )
    )

    status_counts: Counter[str] = Counter()
    unit_status_counts: Counter[str] = Counter()
    sanity_issue_counts: Counter[str] = Counter(
        {issue: 0 for issue in SANITY_ISSUE_CODES}
    )
    strata_heaps: dict[
        tuple[str, str, str], list[tuple[int, str, dict[str, Any]]]
    ] = defaultdict(list)
    targeted_rows: dict[str, dict[str, Any]] = {}
    event_file = pq.ParquetFile(paths["normalized_events.parquet"])
    for batch in event_file.iter_batches(batch_size=5000):
        for event in batch.to_pylist():
            status = event.get("normalization_status") or "<none>"
            unit_status = event.get("unit_normalization_status") or "<none>"
            status_counts[status] += 1
            unit_status_counts[unit_status] += 1
            mapping = mappings_by_key.get(_term_key(event, unit_field="unit"))
            if event.get("entity_type") is not None and mapping is None:
                sanity_issue_counts["event_mapping_missing"] += 1
            if status == "mapped" and not event.get("concept_id"):
                sanity_issue_counts["mapped_event_missing_concept_id"] += 1
            if status == "unresolved" and event.get("concept_id") is not None:
                sanity_issue_counts["unresolved_event_has_concept_id"] += 1
            if (
                event.get("content_specificity") == "category_only"
                and status == "mapped"
            ):
                sanity_issue_counts["category_only_event_mapped"] += 1
            if unit_status == "unresolved" and event.get("normalized_unit") is not None:
                sanity_issue_counts["unresolved_unit_has_normalized_unit"] += 1
            if not _same_value(
                event.get("value_numeric"), event.get("normalized_value_numeric")
            ):
                sanity_issue_counts["normalized_numeric_value_changed"] += 1
            if not _same_value(
                event.get("value_text"), event.get("normalized_value_text")
            ):
                sanity_issue_counts["normalized_text_value_changed"] += 1

            projected = _event_projection(event, mapping)
            event_id = event["event_id"]
            if event_id in targeted_event_reasons:
                targeted_rows[event_id] = projected
            stratum = (
                event.get("source_table") or "<none>",
                event.get("event_kind") or "<none>",
                status,
            )
            score = int.from_bytes(
                hashlib.sha256(event_id.encode("utf-8")).digest()[:8], "big"
            )
            candidate = (-score, event_id, projected)
            heap = strata_heaps[stratum]
            if len(heap) < samples_per_stratum:
                heapq.heappush(heap, candidate)
            elif score < -heap[0][0]:
                heapq.heapreplace(heap, candidate)

    missing_target_events = sorted(
        set(targeted_event_reasons) - set(targeted_rows)
    )
    if missing_target_events:
        sanity_issue_counts["review_target_event_missing"] = len(
            missing_target_events
        )
    for issue in SANITY_ISSUE_CODES:
        count = sanity_issue_counts[issue]
        hard_gates[f"sanity:{issue}"] = count == 0

    sample_rows: dict[str, dict[str, Any]] = {}
    sample_reasons: dict[str, set[str]] = defaultdict(set)
    for event_id, row in targeted_rows.items():
        sample_rows[event_id] = row
        sample_reasons[event_id].update(targeted_event_reasons[event_id])
    for stratum, heap in strata_heaps.items():
        reason = "STRATIFIED:" + "|".join(stratum)
        for _, event_id, row in heap:
            sample_rows[event_id] = row
            sample_reasons[event_id].add(reason)
    samples = []
    for event_id, row in sample_rows.items():
        output = dict(row)
        output["sample_reasons"] = sorted(sample_reasons[event_id])
        samples.append(output)
    samples.sort(
        key=lambda row: (
            row.get("source_table") or "",
            row.get("event_kind") or "",
            row.get("normalization_status") or "",
            row["event_id"],
        )
    )

    failed_gates = [name for name, passed in hard_gates.items() if not passed]
    if failed_gates:
        raise EventPipelineError(
            "NORMALIZATION_REVIEW_GATE_FAILED", ",".join(failed_gates)
        )

    required_rows = [row for row in decisions if row["review_scope"] == "required"]
    sampled_rows = [row for row in decisions if row["review_scope"] == "sampled"]
    optional_rows = [row for row in decisions if row["review_scope"] == "optional"]
    review_reason_terms: Counter[str] = Counter()
    review_reason_events: Counter[str] = Counter()
    for decision in decisions:
        for reason in decision["review_reasons"]:
            review_reason_terms[reason] += 1
            review_reason_events[reason] += int(decision.get("event_count") or 0)

    review_run_id = hashlib.sha256(
        (
            REVIEW_CODE_VERSION
            + "|"
            + "|".join(live_hashes[name] for name in data_names)
            + f"|{samples_per_stratum}|{top_mappings_per_entity}"
        ).encode("utf-8")
    ).hexdigest()[:24]
    summary: dict[str, Any] = {
        "schema": {"name": "normalization_review_package", "version": "1.0.0"},
        "review_code_version": REVIEW_CODE_VERSION,
        "review_run_id": review_run_id,
        "inputs": {
            "event_workflow_run_id": workflow.get("run_id"),
            "normalization_run_id": manifest.get("run_id"),
            "sha256": live_hashes,
        },
        "parameters": {
            "samples_per_stratum": samples_per_stratum,
            "top_mappings_per_entity": top_mappings_per_entity,
        },
        "hard_gates": dict(sorted(hard_gates.items())),
        "sanity_issue_counts": {
            issue: sanity_issue_counts[issue] for issue in SANITY_ISSUE_CODES
        },
        "counts": {
            "normalized_events": sum(status_counts.values()),
            "mapping_rows": len(mappings),
            "normalization_review_queue_rows": len(review_queue),
            "required_review_rows": len(required_rows),
            "sampled_review_rows": len(sampled_rows),
            "optional_review_rows": len(optional_rows),
            "event_samples": len(samples),
        },
        "normalization_status_counts": dict(sorted(status_counts.items())),
        "unit_normalization_status_counts": dict(sorted(unit_status_counts.items())),
        "review_reason_term_counts": dict(sorted(review_reason_terms.items())),
        "review_reason_event_counts": dict(sorted(review_reason_events.items())),
        "acceptance": {
            "automated_review_passed": True,
            "ready_for_human_review": True,
            "human_review_complete": False,
            "pending_human_decisions": len(required_rows) + len(sampled_rows),
        },
    }

    output_directory.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{output_directory.name}.tmp-", dir=output_directory.parent
        )
    )
    try:
        _write_parquet(
            temporary / "normalization_review_samples.parquet",
            samples,
            SAMPLE_SCHEMA,
        )
        _write_parquet(
            temporary / "normalization_review_decisions.parquet",
            decisions,
            DECISION_SCHEMA,
        )
        _write_decision_csv(
            temporary / "normalization_review_decisions.csv", decisions
        )
        (temporary / "normalization_review_checklist.md").write_text(
            _checklist(summary), encoding="utf-8"
        )
        output_names = (
            "normalization_review_samples.parquet",
            "normalization_review_decisions.parquet",
            "normalization_review_decisions.csv",
            "normalization_review_checklist.md",
        )
        summary["outputs_sha256"] = {
            name: sha256_file(temporary / name) for name in output_names
        }
        write_json(temporary / "normalization_review_summary.json", summary)
        os.replace(temporary, output_directory)
    except Exception:
        if temporary.exists():
            remove_temporary(temporary, output_directory.parent)
        raise
    return summary


__all__ = [
    "DECISION_SCHEMA",
    "REVIEW_CODE_VERSION",
    "SAMPLE_SCHEMA",
    "generate_review_package",
]
