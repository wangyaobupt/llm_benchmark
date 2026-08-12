"""Consolidate normalization review packages into one cross-batch pilot."""

from __future__ import annotations

from collections import Counter, defaultdict
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from ..event_cleaning.validation import EventPipelineError
from ..event_normalization.io import sha256_file, write_json
from ..event_viewer import review_app
from .review_normalization import DECISION_SCHEMA, SAMPLE_SCHEMA


CONSOLIDATION_VERSION = "normalization-review-master/1.0.0"
PARQUET_ROW_GROUP_SIZE = 5000
MASTER_DECISION_SCHEMA = pa.schema(
    [
        *DECISION_SCHEMA,
        ("corrected_normalized_unit", pa.string()),
        ("pilot_category", pa.string()),
        ("pilot_category_rank", pa.int32()),
        ("batch_count", pa.int32()),
        ("batch_ids", pa.list_(pa.string())),
        ("batch_event_counts_json", pa.string()),
        ("batch_first_event_ids_json", pa.string()),
        ("source_label_examples", pa.list_(pa.string())),
    ],
    metadata={b"schema": b"consolidated_normalization_review_decisions/1.0.0"},
)
MASTER_SAMPLE_SCHEMA = pa.schema(
    [
        ("batch_id", pa.string()),
        *SAMPLE_SCHEMA,
    ],
    metadata={b"schema": b"cross_batch_normalization_evidence/1.0.0"},
)

PILOT_TARGETS: tuple[tuple[str, int, str], ...] = (
    ("p0_text_rules", 2, "P0文本规则"),
    ("high_frequency_uncoded_medication", 25, "高频无代码药物"),
    ("general_orders", 15, "一般医嘱"),
    ("invalid_ndc_zero", 20, "无效NDC代码"),
    ("unresolved_units", 15, "未解决单位"),
    ("category_only_unresolved", 10, "正确保持未解决的类别项"),
    ("valid_source_code_mapping", 13, "有效源代码映射"),
)


def _term_key(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        row.get("entity_type") or "<none>",
        row.get("source_concept_id") or "<none>",
        row.get("normalized_source_label") or "<missing>",
        row.get("source_unit") or "<none>",
        row.get("mapping_version") or "<none>",
    )


def _mapping_signature(row: dict[str, Any]) -> tuple[Any, ...]:
    """Compare semantics while ignoring presentation-only name capitalization."""
    preferred_name = row.get("preferred_name")
    normalized_preferred_name = (
        str(preferred_name).casefold() if preferred_name is not None else None
    )
    return (
        row.get("concept_id"),
        normalized_preferred_name,
        row.get("normalization_status"),
        row.get("normalized_unit"),
        row.get("unit_normalization_status"),
        row.get("mapping_rule"),
    )


def _canonical_text(values: list[str]) -> str | None:
    unique = sorted(set(values), key=lambda value: (value.casefold(), value))
    return unique[0] if unique else None


def _is_pilot_candidate(category: str, row: dict[str, Any]) -> bool:
    reasons = set(row.get("review_reasons") or [])
    if category == "p0_text_rules":
        return "REVIEWED_TEXT_RULE" in reasons
    if category == "high_frequency_uncoded_medication":
        return (
            row.get("entity_type") == "medication"
            and not row.get("source_concept_id")
            and row.get("normalization_status") == "unresolved"
            and row.get("mapping_rule") == "unresolved"
        )
    if category == "general_orders":
        return row.get("entity_type") == "clinical_order"
    if category == "invalid_ndc_zero":
        return (
            row.get("mapping_rule") == "invalid-source-code"
            and row.get("source_concept_id") == "ndc:0"
        )
    if category == "unresolved_units":
        return row.get("unit_normalization_status") == "unresolved"
    if category == "category_only_unresolved":
        return (
            row.get("entity_type") == "medication_order_category"
            and row.get("normalization_status") == "unresolved"
        )
    if category == "valid_source_code_mapping":
        return (
            row.get("normalization_status") == "mapped"
            and bool(row.get("source_concept_id"))
            and row.get("mapping_rule") == "source-code"
        )
    raise ValueError(f"unknown pilot category: {category}")


def select_pilot_rows(
    rows: list[dict[str, Any]], evidence_batches_by_review: dict[str, set[str]]
) -> dict[str, list[str]]:
    """Select exclusive, impact-ranked terms with evidence in every source batch."""
    selected: set[str] = set()
    output: dict[str, list[str]] = {}
    for category_rank, (category, target, _label) in enumerate(PILOT_TARGETS):
        candidates = [
            row
            for row in rows
            if row["review_id"] not in selected
            and set(row.get("batch_ids") or [])
            <= evidence_batches_by_review.get(row["review_id"], set())
            and _is_pilot_candidate(category, row)
        ]
        candidates.sort(
            key=lambda row: (
                -int(row.get("event_count") or 0),
                row.get("normalized_source_label") or "",
                row["review_id"],
            )
        )
        if len(candidates) < target:
            raise EventPipelineError(
                "PILOT_CATEGORY_INSUFFICIENT",
                f"{category}: required={target}, available={len(candidates)}",
            )
        chosen = candidates[:target]
        output[category] = [row["review_id"] for row in chosen]
        for row in chosen:
            row["pilot_category"] = category
            row["pilot_category_rank"] = category_rank
            row["priority_rank"] = category_rank
            row["review_scope"] = "pilot"
            row["review_status"] = "pending"
            selected.add(row["review_id"])
    return output


def _resolve_input(event_directory: Path) -> dict[str, Any]:
    event_directory = Path(event_directory).resolve()
    review_directory = (
        event_directory if event_directory.name == "review" else event_directory / "review"
    )
    event_root = review_directory.parent
    dataset_root = event_root.parent
    batch_id = dataset_root.name
    summary_path = review_directory / "normalization_review_summary.json"
    decisions_path = review_directory / "normalization_review_decisions.parquet"
    samples_path = review_directory / "normalization_review_samples.parquet"
    manifest_path = event_root / "cleaning" / "run_manifest.json"
    required = (summary_path, decisions_path, samples_path, manifest_path)
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise EventPipelineError("MASTER_REVIEW_INPUT_MISSING", ",".join(missing))
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("acceptance", {}).get("automated_review_passed") is not True:
        raise EventPipelineError("MASTER_REVIEW_INPUT_NOT_ACCEPTED", batch_id)
    expected_hashes = summary.get("outputs_sha256", {})
    for path in (decisions_path, samples_path):
        if sha256_file(path) != expected_hashes.get(path.name):
            raise EventPipelineError(
                "MASTER_REVIEW_INPUT_HASH_MISMATCH", f"{batch_id}:{path.name}"
            )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source_filename = manifest.get("input", {}).get("filename")
    source_path = dataset_root / str(source_filename)
    if not source_path.is_file():
        raise EventPipelineError("MASTER_REVIEW_SOURCE_MISSING", str(source_path))
    return {
        "batch_id": batch_id,
        "event_directory": event_root,
        "review_directory": review_directory,
        "review_summary": summary,
        "review_summary_path": summary_path,
        "decisions_path": decisions_path,
        "samples_path": samples_path,
        "source_jsonl": source_path.resolve(),
        "source_jsonl_bytes": manifest.get("input", {}).get("bytes"),
        "source_jsonl_sha256": manifest.get("input", {}).get("sha256"),
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


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = MASTER_DECISION_SCHEMA.names
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            output = {name: row.get(name) for name in fieldnames}
            for name in ("review_reasons", "batch_ids", "source_label_examples"):
                output[name] = "+".join(output.get(name) or [])
            writer.writerow(output)


def _protocol(summary: dict[str, Any]) -> str:
    lines = [
        "# 跨批归一化人工试审协议",
        "",
        "本目录只记录人工判断，不修改任何 normalization Parquet。相同冻结键只审一次，决定通过批次证据传播。",
        "",
        "## 冻结键",
        "",
        "`entity_type + source_concept_id + normalized_source_label + source_unit + mapping_version`",
        "",
        "## 100条试审构成",
        "",
    ]
    counts = summary["pilot"]["selected_counts"]
    for category, target, label in PILOT_TARGETS:
        lines.append(f"- {label}：{counts[category]} 条（目标 {target}）")
    lines.extend(
        [
            "",
            "## 决策定义",
            "",
            "- `accepted_mapped`：现有概念和单位映射均正确。",
            "- `accepted_unresolved`：证据不足以确定到具体概念，保持 unresolved 正确。",
            "- `deterministic_correction`：可由明确规则纠正；填写 concept_id+preferred_name 或 normalized_unit，并写明依据。",
            "- `needs_external_evidence`：需要词典、术语库或专家证据，暂不形成最终决定。",
            "- `source_defect`：源代码、源名称或源行本身存在缺陷；必须说明证据。",
            "",
            "## 审阅步骤",
            "",
            "1. 默认按试审类别和影响事件数检查 100 条 pilot。",
            "2. 对照两批事件计数，逐批打开证据样本并通过 raw_row_ref 回查原始 JSONL。",
            "3. mapped 项核对源代码、标准概念和单位；unresolved 项确认是否确实不能由确定性规则解决。",
            "4. 选择决定、填写审阅者；纠正、外部证据和源缺陷必须写明依据。",
            "5. 决定只追加到 `normalization_review_annotations.jsonl`。试审完成后先汇总错误模式，再决定是否修改规则和重跑归一化。",
            "",
            "## 完成门槛",
            "",
            "100 条均形成终态决定才算试审完成。`needs_external_evidence` 不是终态，仍计入待处理。",
            "任何确定性错误都应回到映射或单位规则修复并重新生成，不直接编辑 Parquet。",
            "",
        ]
    )
    return "\n".join(lines)


def consolidate_review_packages(
    event_directories: list[Path], output_directory: Path
) -> dict[str, Any]:
    """Merge accepted review packages and build a fixed 100-term pilot."""
    if len(event_directories) < 2:
        raise EventPipelineError("MASTER_REVIEW_NEEDS_MULTIPLE_BATCHES", "at least 2")
    output_directory = Path(output_directory).resolve()
    if output_directory.exists():
        raise EventPipelineError("OUTPUT_ALREADY_EXISTS", str(output_directory))
    inputs = [_resolve_input(path) for path in event_directories]
    batch_ids = [item["batch_id"] for item in inputs]
    if len(set(batch_ids)) != len(batch_ids):
        raise EventPipelineError("DUPLICATE_MASTER_REVIEW_BATCH_ID", ",".join(batch_ids))

    rows_by_key: dict[tuple[str, str, str, str, str], list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    evidence_rows: list[dict[str, Any]] = []
    for item in inputs:
        batch_id = item["batch_id"]
        for row in pq.read_table(item["decisions_path"]).to_pylist():
            rows_by_key[_term_key(row)].append((batch_id, row))
        for sample in pq.read_table(item["samples_path"]).to_pylist():
            evidence_rows.append({"batch_id": batch_id, **sample})

    conflicts: list[dict[str, Any]] = []
    display_variant_count = 0
    merged_rows: list[dict[str, Any]] = []
    for key, occurrences in rows_by_key.items():
        signatures = {_mapping_signature(row) for _batch, row in occurrences}
        if len(signatures) > 1:
            conflicts.append(
                {
                    "key": key,
                    "batches": {
                        batch: dict(zip(
                            (
                                "concept_id",
                                "preferred_name_when_mapped",
                                "normalization_status",
                                "normalized_unit",
                                "unit_normalization_status",
                                "mapping_rule",
                            ),
                            _mapping_signature(row),
                            strict=True,
                        ))
                        for batch, row in occurrences
                    },
                }
            )
            continue
        review_ids = {row["review_id"] for _batch, row in occurrences}
        if len(review_ids) != 1:
            conflicts.append({"key": key, "review_ids": sorted(review_ids)})
            continue
        base = dict(occurrences[0][1])
        event_counts = {
            batch: int(row.get("event_count") or 0) for batch, row in occurrences
        }
        first_events = {
            batch: row.get("first_event_id") for batch, row in occurrences
        }
        examples = [
            str(row.get("source_label_example"))
            for _batch, row in occurrences
            if row.get("source_label_example")
        ]
        preferred_names = [
            str(row.get("preferred_name"))
            for _batch, row in occurrences
            if row.get("preferred_name")
        ]
        if len(set(preferred_names)) > 1:
            display_variant_count += 1
        base.update(
            {
                "priority_rank": 9,
                "review_scope": "not_selected",
                "review_reasons": sorted(
                    {
                        reason
                        for _batch, row in occurrences
                        for reason in (row.get("review_reasons") or [])
                    }
                ),
                "source_label_example": _canonical_text(examples),
                "preferred_name": _canonical_text(preferred_names),
                "event_count": sum(event_counts.values()),
                "first_event_id": next(
                    (first_events[batch] for batch in sorted(first_events) if first_events[batch]),
                    None,
                ),
                "review_status": "not_selected",
                "decision": None,
                "corrected_concept_id": None,
                "corrected_preferred_name": None,
                "corrected_normalized_unit": None,
                "reviewer": None,
                "review_comment": None,
                "pilot_category": None,
                "pilot_category_rank": None,
                "batch_count": len(occurrences),
                "batch_ids": sorted(event_counts),
                "batch_event_counts_json": json.dumps(
                    dict(sorted(event_counts.items())), ensure_ascii=False, sort_keys=True
                ),
                "batch_first_event_ids_json": json.dumps(
                    dict(sorted(first_events.items())), ensure_ascii=False, sort_keys=True
                ),
                "source_label_examples": sorted(
                    set(examples), key=lambda value: (value.casefold(), value)
                ),
            }
        )
        merged_rows.append(base)
    if conflicts:
        preview = json.dumps(conflicts[:20], ensure_ascii=False, default=list)
        raise EventPipelineError(
            "CROSS_BATCH_MAPPING_CONFLICT", f"count={len(conflicts)}; preview={preview}"
        )

    evidence_batches_by_review: dict[str, set[str]] = defaultdict(set)
    for row in evidence_rows:
        if row.get("mapping_review_id"):
            evidence_batches_by_review[str(row["mapping_review_id"])].add(
                row["batch_id"]
            )
    pilot_selection = select_pilot_rows(merged_rows, evidence_batches_by_review)
    selected_ids = {review_id for values in pilot_selection.values() for review_id in values}
    merged_rows.sort(
        key=lambda row: (
            row.get("pilot_category_rank")
            if row.get("pilot_category_rank") is not None
            else 99,
            -int(row.get("event_count") or 0),
            row.get("normalized_source_label") or "",
            row["review_id"],
        )
    )
    evidence_rows.sort(
        key=lambda row: (
            0 if row.get("mapping_review_id") in selected_ids else 1,
            row.get("mapping_review_id") or "",
            row["batch_id"],
            row.get("event_id") or "",
        )
    )

    normalization_counts = Counter()
    unit_counts = Counter()
    normalized_events = 0
    for item in inputs:
        source_summary = item["review_summary"]
        normalization_counts.update(source_summary.get("normalization_status_counts", {}))
        unit_counts.update(source_summary.get("unit_normalization_status_counts", {}))
        normalized_events += int(source_summary.get("counts", {}).get("normalized_events", 0))
    pilot_counts = {key: len(value) for key, value in pilot_selection.items()}
    pilot_impact = {
        key: sum(
            int(row.get("event_count") or 0)
            for row in merged_rows
            if row.get("pilot_category") == key
        )
        for key in pilot_selection
    }
    run_payload = {
        item["batch_id"]: {
            "review_run_id": item["review_summary"].get("review_run_id"),
            "decisions_sha256": sha256_file(item["decisions_path"]),
            "samples_sha256": sha256_file(item["samples_path"]),
        }
        for item in inputs
    }
    review_run_id = "master-" + hashlib.sha256(
        json.dumps(run_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:24]
    summary: dict[str, Any] = {
        "schema": {"name": "normalization_review_master", "version": "1.0.0"},
        "review_code_version": CONSOLIDATION_VERSION,
        "review_run_id": review_run_id,
        "inputs": {
            "batches": [
                {
                    "batch_id": item["batch_id"],
                    "event_directory": str(item["event_directory"]),
                    "review_directory": str(item["review_directory"]),
                    "review_run_id": item["review_summary"].get("review_run_id"),
                    "review_decisions_sha256": sha256_file(item["decisions_path"]),
                    "review_samples_sha256": sha256_file(item["samples_path"]),
                    "source_jsonl": str(item["source_jsonl"]),
                    "source_jsonl_bytes": item["source_jsonl_bytes"],
                    "source_jsonl_sha256": item["source_jsonl_sha256"],
                }
                for item in inputs
            ]
        },
        "merge_key": [
            "entity_type",
            "source_concept_id",
            "normalized_source_label",
            "source_unit",
            "mapping_version",
        ],
        "counts": {
            "normalized_events": normalized_events,
            "mapping_rows": len(merged_rows),
            "input_mapping_rows": sum(len(rows) for rows in rows_by_key.values()),
            "unique_mapping_rows": len(merged_rows),
            "cross_batch_mapping_rows": sum(
                1 for rows in rows_by_key.values() if len(rows) > 1
            ),
            "single_batch_mapping_rows": sum(
                1 for rows in rows_by_key.values() if len(rows) == 1
            ),
            "event_samples": len(evidence_rows),
            "pilot_review_rows": len(selected_ids),
            "required_review_rows": len(selected_ids),
            "sampled_review_rows": 0,
            "not_selected_rows": len(merged_rows) - len(selected_ids),
            "mapping_conflicts": 0,
            "unresolved_display_name_variants": display_variant_count,
        },
        "normalization_status_counts": dict(sorted(normalization_counts.items())),
        "unit_normalization_status_counts": dict(sorted(unit_counts.items())),
        "pilot": {
            "selection_method": "sequential_exclusive_descending_total_event_count",
            "selected_counts": pilot_counts,
            "selected_event_impact": pilot_impact,
            "total_selected": len(selected_ids),
            "all_selected_batches_have_evidence": all(
                set(row.get("batch_ids") or [])
                <= evidence_batches_by_review.get(row["review_id"], set())
                for row in merged_rows
                if row["review_id"] in selected_ids
            ),
        },
        "decision_taxonomy": {
            "allowed": [
                "accepted_mapped",
                "accepted_unresolved",
                "deterministic_correction",
                "needs_external_evidence",
                "source_defect",
            ],
            "completed": [
                "accepted_mapped",
                "accepted_unresolved",
                "deterministic_correction",
                "source_defect",
            ],
            "comment_required": [
                "deterministic_correction",
                "needs_external_evidence",
                "source_defect",
            ],
            "correction_concept_or_unit_required": ["deterministic_correction"],
        },
        "acceptance": {
            "input_reviews_accepted": True,
            "mapping_conflicts_absent": True,
            "pilot_targets_met": all(
                pilot_counts[category] == target
                for category, target, _label in PILOT_TARGETS
            ),
            "pilot_evidence_complete": all(
                set(row.get("batch_ids") or [])
                <= evidence_batches_by_review.get(row["review_id"], set())
                for row in merged_rows
                if row["review_id"] in selected_ids
            ),
            "ready_for_human_review": True,
            "human_review_complete": False,
            "pending_human_decisions": len(selected_ids),
        },
    }

    output_directory.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output_directory.name}-", dir=output_directory.parent)
    )
    try:
        _write_parquet(
            temporary / "consolidated_review_decisions.parquet",
            merged_rows,
            MASTER_DECISION_SCHEMA,
        )
        _write_csv(temporary / "consolidated_review_decisions.csv", merged_rows)
        _write_parquet(
            temporary / "cross_batch_evidence_samples.parquet",
            evidence_rows,
            MASTER_SAMPLE_SCHEMA,
        )
        (temporary / "adjudication_protocol.md").write_text(
            _protocol(summary), encoding="utf-8", newline="\n"
        )
        shutil.copy2(Path(review_app.__file__), temporary / "review_app.py")
        output_names = (
            "consolidated_review_decisions.parquet",
            "consolidated_review_decisions.csv",
            "cross_batch_evidence_samples.parquet",
            "adjudication_protocol.md",
            "review_app.py",
        )
        summary["outputs_sha256"] = {
            name: sha256_file(temporary / name) for name in output_names
        }
        write_json(temporary / "review_summary.json", summary)
        os.replace(temporary, output_directory)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return summary
