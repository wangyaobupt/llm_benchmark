"""Independent gates for local human annotation packages."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
import pyarrow.parquet as pq

from .annotation_contracts import ANNOTATION_ALLOCATION_ARROW_SCHEMA
from .annotation_validation import SectionAnnotationValidator


DECISION_SCHEMA_PATH = (
    Path(__file__).resolve().parent
    / "schemas"
    / "annotation-review-decision.schema.json"
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _check(name: str, passed: bool, observed: Any, expected: Any) -> dict[str, Any]:
    return {
        "check": name,
        "passed": bool(passed),
        "observed": observed,
        "expected": expected,
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Text NER 人工标注包独立验收",
        "",
        f"结论：**{'通过' if report['passed'] else '未通过'}**。标注包仅保存在 `data/derived/`，模型调用次数为0。",
        "",
        "## 核心计数",
        "",
        "| 指标 | 数量 |",
        "|---|---:|",
    ]
    for key, value in report["counts"].items():
        lines.append(f"| `{key}` | {value} |")
    lines.extend(["", "## 自动门禁", "", "| 检查 | 结果 | 观察值 | 期望值 |", "|---|---|---|---|"])
    for item in report["checks"]:
        lines.append(
            f"| `{item['check']}` | {'通过' if item['passed'] else '失败'} | "
            f"`{json.dumps(item['observed'], ensure_ascii=False, sort_keys=True)}` | "
            f"`{json.dumps(item['expected'], ensure_ascii=False, sort_keys=True)}` |"
        )
    lines.extend(
        [
            "",
            "## 边界",
            "",
            "- A/B calibration任务集合一致、顺序不同，双方均看不到对方结果。",
            "- evaluation包已生成但状态固定为 `blocked_pending_calibration`，不能提前标注或用于模型评测。",
            "- 原始临床文本仅存在于被Git忽略的本地任务文件；Git报告只有聚合计数和文件哈希。",
            "- 决策和裁决记录采用追加式Schema，第三方裁决必须引用至少两条输入决定，不覆盖A/B原始记录。",
            "",
        ]
    )
    return "\n".join(lines)


def audit_annotation_package(
    package_directory: Path,
    *,
    replay_directory: Path | None = None,
    output_json: Path | None = None,
    output_markdown: Path | None = None,
) -> dict[str, Any]:
    package_directory = Path(package_directory).resolve()
    allocation_path = package_directory / "allocation" / "annotation_allocation.parquet"
    summary_path = package_directory / "allocation" / "annotation_package_summary.json"
    a_path = package_directory / "calibration" / "annotator_a" / "tasks.jsonl"
    b_path = package_directory / "calibration" / "annotator_b" / "tasks.jsonl"
    evaluation_path = package_directory / "evaluation" / "tasks.locked.jsonl"
    decision_paths = {
        "annotator_a": package_directory / "decisions" / "annotator_a.jsonl",
        "annotator_b": package_directory / "decisions" / "annotator_b.jsonl",
        "adjudication": package_directory / "decisions" / "adjudication.jsonl",
    }
    run_path = package_directory / "run_manifest.json"
    allocation_table = pq.read_table(allocation_path)
    allocation = allocation_table.to_pylist()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    run = json.loads(run_path.read_text(encoding="utf-8"))
    a_tasks = _load_jsonl(a_path)
    b_tasks = _load_jsonl(b_path)
    evaluation_tasks = _load_jsonl(evaluation_path)
    decision_rows = {
        name: _load_jsonl(path) for name, path in decision_paths.items()
    }

    calibration = [row for row in allocation if row["partition"] == "calibration"]
    evaluation = [row for row in allocation if row["partition"] == "evaluation"]
    calibration_subjects = {row["subject_id"] for row in calibration}
    evaluation_subjects = {row["subject_id"] for row in evaluation}
    document_duplicates = len(allocation) - len({row["document_id"] for row in allocation})
    a_units = [task["annotation_unit_id"] for task in a_tasks]
    b_units = [task["annotation_unit_id"] for task in b_tasks]
    evaluation_units = [task["annotation_unit_id"] for task in evaluation_tasks]
    validator = SectionAnnotationValidator()
    task_failures = 0
    for task in a_tasks + b_tasks + evaluation_tasks:
        manifest_stub = {
            "manifest_row_id": task["manifest_row_id"],
            "document_id": task["document_id"],
            "section_id": task["section_id"],
            "span_sha256": task["section_text_sha256"],
        }
        try:
            validator.validate(task["annotation"], manifest_stub, task["section_text"])
        except ValueError:
            task_failures += 1

    calibration_source_counts = dict(
        sorted(Counter(row["source_table"] for row in calibration).items())
    )
    calibration_strata = {
        row["pilot_stratum"] for row in calibration if row["source_table"] == "note.radiology"
    }
    all_radiology_strata = {
        row["pilot_stratum"] for row in allocation if row["source_table"] == "note.radiology"
    }
    expected_pilot_documents = summary["allocation"]["pilot_documents"]
    expected_calibration_documents = summary["allocation"]["calibration_documents"]
    expected_evaluation_documents = summary["allocation"]["evaluation_documents"]
    expected_source_balance = {
        "ed.triage": expected_calibration_documents // 2,
        "note.radiology": expected_calibration_documents // 2,
    }
    expected_calibration_units = sum(row["text_unit_count"] for row in calibration)
    expected_evaluation_units = sum(row["text_unit_count"] for row in evaluation)
    expected_calibration_task_counts = Counter(
        {row["document_id"]: row["text_unit_count"] for row in calibration}
    )
    expected_evaluation_task_counts = Counter(
        {row["document_id"]: row["text_unit_count"] for row in evaluation}
    )
    a_document_counts = Counter(task["document_id"] for task in a_tasks)
    b_document_counts = Counter(task["document_id"] for task in b_tasks)
    evaluation_document_counts = Counter(
        task["document_id"] for task in evaluation_tasks
    )
    forbidden_task_keys = {"subject_id", "hadm_id", "raw_row_ref", "jsonl_line_number"}
    observed_forbidden_task_keys = sorted(
        {
            key
            for task in a_tasks + b_tasks + evaluation_tasks
            for key in task
            if key in forbidden_task_keys
        }
    )
    run_hash_failures = 0
    for relative, expected_hash in run["outputs"].items():
        if _sha256_file(package_directory / relative) != expected_hash:
            run_hash_failures += 1

    replay_match = True
    replay_hashes: dict[str, str] | None = None
    if replay_directory is not None:
        replay_directory = Path(replay_directory).resolve()
        relative_paths = [
            "allocation/annotation_allocation.parquet",
            "allocation/annotation_package_summary.json",
            "calibration/annotator_a/tasks.jsonl",
            "calibration/annotator_b/tasks.jsonl",
            "evaluation/tasks.locked.jsonl",
            "decisions/annotator_a.jsonl",
            "decisions/annotator_b.jsonl",
            "decisions/adjudication.jsonl",
            "run_manifest.json",
        ]
        replay_hashes = {
            relative: _sha256_file(replay_directory / relative)
            for relative in relative_paths
        }
        replay_match = replay_hashes == {
            relative: _sha256_file(package_directory / relative)
            for relative in relative_paths
        }

    decision_schema = json.loads(DECISION_SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(decision_schema)
    decision_validator = Draft202012Validator(
        decision_schema, format_checker=FormatChecker()
    )
    decision_examples = [
        {
            "schema_version": "annotation-review-decision/1.0.0",
            "decision_id": "dec:a",
            "annotation_unit_id": "aunit:test",
            "manifest_row_id": "mrow:test",
            "annotator_role": "annotator_a",
            "annotator_id": "annotator-a-local",
            "protocol_version": "text-ner-annotation-protocol/1.0.0",
            "submitted_at": "2026-08-13T12:00:00+08:00",
            "decision": "accept",
            "annotation_payload_path": "annotations/aunit-test.json",
            "annotation_payload_sha256": "0" * 64,
            "reason_codes": [],
            "comments": None,
            "input_decision_ids": [],
            "supersedes_decision_id": None,
        },
        {
            "schema_version": "annotation-review-decision/1.0.0",
            "decision_id": "dec:judge",
            "annotation_unit_id": "aunit:test",
            "manifest_row_id": "mrow:test",
            "annotator_role": "adjudicator",
            "annotator_id": "adjudicator-local",
            "protocol_version": "text-ner-annotation-protocol/1.0.0",
            "submitted_at": "2026-08-13T13:00:00+08:00",
            "decision": "correct",
            "annotation_payload_path": "annotations/aunit-test-adjudicated.json",
            "annotation_payload_sha256": "1" * 64,
            "reason_codes": ["SPAN_ERROR"],
            "comments": "Resolved disagreement.",
            "input_decision_ids": ["dec:a", "dec:b"],
            "supersedes_decision_id": None,
        },
    ]
    decision_example_failures = sum(
        bool(list(decision_validator.iter_errors(example)))
        for example in decision_examples
    )

    checks = [
        _check("allocation_arrow_schema", allocation_table.schema == ANNOTATION_ALLOCATION_ARROW_SCHEMA, str(allocation_table.schema.metadata), str(ANNOTATION_ALLOCATION_ARROW_SCHEMA.metadata)),
        _check("pilot_document_reconciliation", len(allocation) == expected_pilot_documents and document_duplicates == 0, {"documents": len(allocation), "duplicates": document_duplicates}, {"documents": expected_pilot_documents, "duplicates": 0}),
        _check("exact_partition_sizes", len(calibration) == expected_calibration_documents and len(evaluation) == expected_evaluation_documents, {"calibration": len(calibration), "evaluation": len(evaluation)}, {"calibration": expected_calibration_documents, "evaluation": expected_evaluation_documents}),
        _check("patient_isolation", not (calibration_subjects & evaluation_subjects), len(calibration_subjects & evaluation_subjects), 0),
        _check("calibration_source_balance", calibration_source_counts == expected_source_balance, calibration_source_counts, expected_source_balance),
        _check("calibration_stratum_coverage", calibration_strata == all_radiology_strata, sorted(calibration_strata), sorted(all_radiology_strata)),
        _check("annotator_task_sets_equal", set(a_units) == set(b_units), len(set(a_units) ^ set(b_units)), 0),
        _check("annotator_task_orders_blinded", a_units != b_units, a_units == b_units, False),
        _check("task_document_allocation", a_document_counts == expected_calibration_task_counts and b_document_counts == expected_calibration_task_counts and evaluation_document_counts == expected_evaluation_task_counts, {"a_mismatch": sum((a_document_counts - expected_calibration_task_counts).values()) + sum((expected_calibration_task_counts - a_document_counts).values()), "b_mismatch": sum((b_document_counts - expected_calibration_task_counts).values()) + sum((expected_calibration_task_counts - b_document_counts).values()), "evaluation_mismatch": sum((evaluation_document_counts - expected_evaluation_task_counts).values()) + sum((expected_evaluation_task_counts - evaluation_document_counts).values())}, {"a_mismatch": 0, "b_mismatch": 0, "evaluation_mismatch": 0}),
        _check("direct_patient_identifiers_absent_from_tasks", not observed_forbidden_task_keys, observed_forbidden_task_keys, []),
        _check("evaluation_locked", all(task["release_status"] == "blocked_pending_calibration" and task["annotator_slot"] is None for task in evaluation_tasks), sum(task["release_status"] != "blocked_pending_calibration" or task["annotator_slot"] is not None for task in evaluation_tasks), 0),
        _check("task_schema_and_text_hash", task_failures == 0, task_failures, 0),
        _check("task_unit_reconciliation", len(a_units) == expected_calibration_units and len(b_units) == expected_calibration_units and len(evaluation_units) == expected_evaluation_units and not (set(a_units) & set(evaluation_units)), {"a": len(a_units), "b": len(b_units), "evaluation": len(evaluation_units), "cross_partition": len(set(a_units) & set(evaluation_units))}, {"a": expected_calibration_units, "b": expected_calibration_units, "evaluation": expected_evaluation_units, "cross_partition": 0}),
        _check("decision_schema_examples", decision_example_failures == 0, decision_example_failures, 0),
        _check("decision_logs_initialized_empty", all(not rows for rows in decision_rows.values()) and summary["human_decisions"] == 0, {name: len(rows) for name, rows in decision_rows.items()}, {"annotator_a": 0, "annotator_b": 0, "adjudication": 0}),
        _check("run_output_hashes", run_hash_failures == 0, run_hash_failures, 0),
        _check("model_calls", run["model"]["calls"] == 0 and summary["model_calls"] == 0, {"run": run["model"]["calls"], "summary": summary["model_calls"]}, {"run": 0, "summary": 0}),
        _check("repeat_run_hashes", replay_match, replay_hashes, "identical to primary run"),
    ]
    report = {
        "schema": {"name": "text_ner_annotation_package_acceptance", "version": "1.0.0"},
        "passed": all(item["passed"] for item in checks),
        "counts": {
            "pilot_documents": len(allocation),
            "calibration_documents": len(calibration),
            "evaluation_documents": len(evaluation),
            "calibration_subjects": len(calibration_subjects),
            "evaluation_subjects": len(evaluation_subjects),
            "annotator_a_text_units": len(a_tasks),
            "annotator_b_text_units": len(b_tasks),
            "evaluation_locked_text_units": len(evaluation_tasks),
            "model_calls": run["model"]["calls"],
        },
        "checks": checks,
        "artifacts": {
            "allocation_sha256": _sha256_file(allocation_path),
            "annotator_a_tasks_sha256": _sha256_file(a_path),
            "annotator_b_tasks_sha256": _sha256_file(b_path),
            "evaluation_locked_tasks_sha256": _sha256_file(evaluation_path),
            "run_manifest_sha256": _sha256_file(run_path),
        },
        "restricted_text_files_committed": False,
    }
    if output_json is not None:
        output_json = Path(output_json)
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(
            json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
    if output_markdown is not None:
        output_markdown = Path(output_markdown)
        output_markdown.parent.mkdir(parents=True, exist_ok=True)
        output_markdown.write_text(_markdown(report), encoding="utf-8")
    if not report["passed"]:
        raise ValueError(
            "TEXT_NER_ANNOTATION_PACKAGE_ACCEPTANCE_FAILED: "
            f"{[item['check'] for item in checks if not item['passed']]}"
        )
    return report
