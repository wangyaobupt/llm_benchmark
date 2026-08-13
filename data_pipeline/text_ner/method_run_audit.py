"""Independent aggregate-only audit for exploratory NER method dry-runs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .method_contracts import validate_method_run
from .method_run import prepare_method_run


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl_rows(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _write_report(
    result: dict[str, Any], output_json: Path | None, output_markdown: Path | None
) -> None:
    if output_json:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(
            json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
    if output_markdown:
        output_markdown.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            "# Text NER 方法 dry-run 独立验收",
            "",
            f"结论：**{'通过' if result['passed'] else '失败'}**。本报告不包含临床原文。",
            "",
            "## 核心计数",
            "",
            "| 指标 | 数量 |",
            "|---|---:|",
            f"| `calibration_text_units` | {result['counts']['calibration_text_units']} |",
            f"| `mention_requests` | {result['counts']['mention_requests']} |",
            f"| `relation_requests_pending` | {result['counts']['relation_requests_pending']} |",
            f"| `candidate_annotations` | {result['counts']['candidate_annotations']} |",
            f"| `evaluation_access_count` | {result['counts']['evaluation_access_count']} |",
            f"| `model_calls` | {result['counts']['model_calls']} |",
            "",
            "## 自动门禁",
            "",
            "| 检查 | 结果 | 观察值 | 期望值 |",
            "|---|---|---|---|",
        ]
        for check in result["checks"]:
            lines.append(
                "| `{name}` | {status} | `{observed}` | `{expected}` |".format(
                    name=check["name"],
                    status="通过" if check["passed"] else "失败",
                    observed=json.dumps(check["observed"], ensure_ascii=False, sort_keys=True),
                    expected=json.dumps(check["expected"], ensure_ascii=False, sort_keys=True),
                )
            )
        lines.extend(
            [
                "",
                "## 结论边界",
                "",
                "- 当前产物是 `exploratory_candidate` 方法请求，不是人工gold。",
                "- relation阶段必须等待mention通过Python校验，不能越过依赖直接运行。",
                "- calibration原文只存在于Git忽略的本地请求目录；聚合报告不保存原文。",
                "- evaluation未读取、模型未调用、性能指标固定为`not_evaluable`。",
            ]
        )
        output_markdown.write_text("\n".join(lines) + "\n", encoding="utf-8")


def audit_method_run(
    annotation_package: Path,
    method_config_path: Path,
    run_directory: Path,
    *,
    replay_directory: Path | None = None,
    output_json: Path | None = None,
    output_markdown: Path | None = None,
) -> dict[str, Any]:
    annotation_package = Path(annotation_package).resolve()
    method_config_path = Path(method_config_path).resolve()
    run_directory = Path(run_directory).resolve()
    manifest = _load_json(run_directory / "run_manifest.json")
    validate_method_run(manifest)
    summary = _load_json(run_directory / "method_run_summary.json")
    mentions = _jsonl_rows(run_directory / "requests" / "mention_requests.jsonl")
    relations = _jsonl_rows(
        run_directory / "requests" / "relation_requests.pending.jsonl"
    )
    candidates = _jsonl_rows(
        run_directory / "candidates" / "section_annotations.jsonl"
    )
    metrics = _load_json(run_directory / "evaluation" / "metrics.json")
    checks: list[dict[str, Any]] = []

    def check(name: str, passed: bool, observed: Any, expected: Any) -> None:
        checks.append(
            {
                "name": name,
                "passed": bool(passed),
                "observed": observed,
                "expected": expected,
            }
        )

    output_hash_mismatches: dict[str, Any] = {}
    for relative, expected in manifest["outputs"].items():
        path = run_directory / relative
        observed = _sha256_file(path) if path.is_file() else None
        if observed != expected:
            output_hash_mismatches[relative] = {
                "observed": observed,
                "expected": expected,
            }
    duplicate_units = len(mentions) - len(
        {request["annotation_unit_id"] for request in mentions}
    )
    invalid_text_hashes = sum(
        hashlib.sha256(request["section_text"].encode("utf-8")).hexdigest()
        != request["section_text_sha256"]
        for request in mentions
    )
    non_calibration = sum(
        request.get("partition") != "calibration" for request in mentions + relations
    )
    relation_dependency_errors = sum(
        request.get("dependency_status") != "blocked_pending_validated_mentions"
        for request in relations
    )
    check("manifest_output_hashes", not output_hash_mismatches, output_hash_mismatches, {})
    check(
        "summary_manifest_reconciliation",
        summary.get("text_units") == manifest["input"]["text_units"]
        and summary.get("mention_requests") == len(mentions)
        and summary.get("relation_requests_pending") == len(relations)
        and summary.get("candidate_annotations") == len(candidates)
        and summary.get("model_calls") == manifest["execution"]["model_calls"],
        {
            "text_units": summary.get("text_units"),
            "mention_requests": summary.get("mention_requests"),
            "relation_requests_pending": summary.get("relation_requests_pending"),
            "candidate_annotations": summary.get("candidate_annotations"),
            "model_calls": summary.get("model_calls"),
        },
        {
            "text_units": manifest["input"]["text_units"],
            "mention_requests": len(mentions),
            "relation_requests_pending": len(relations),
            "candidate_annotations": len(candidates),
            "model_calls": manifest["execution"]["model_calls"],
        },
    )
    check("calibration_only", non_calibration == 0, non_calibration, 0)
    check("request_unit_uniqueness", duplicate_units == 0, duplicate_units, 0)
    check("request_text_hashes", invalid_text_hashes == 0, invalid_text_hashes, 0)
    check(
        "two_stage_dependency",
        relation_dependency_errors == 0 and len(relations) == len(mentions),
        {"dependency_errors": relation_dependency_errors, "relations": len(relations)},
        {"dependency_errors": 0, "relations": len(mentions)},
    )
    check("candidate_output_empty", not candidates, len(candidates), 0)
    check(
        "human_gold_gate",
        metrics.get("status") == "not_evaluable" and metrics.get("metrics") is None,
        {"status": metrics.get("status"), "metrics": metrics.get("metrics")},
        {"status": "not_evaluable", "metrics": None},
    )
    check(
        "evaluation_locked",
        manifest["input"]["evaluation_access_count"] == 0,
        manifest["input"]["evaluation_access_count"],
        0,
    )
    check(
        "model_calls",
        manifest["execution"]["model_calls"] == 0,
        manifest["execution"]["model_calls"],
        0,
    )
    replay_hash_mismatches: dict[str, Any] = {}
    if replay_directory is not None:
        replay = prepare_method_run(
            annotation_package, method_config_path, replay_directory
        )
        for relative, expected in manifest["outputs"].items():
            observed = replay["outputs"].get(relative)
            if observed != expected:
                replay_hash_mismatches[relative] = {
                    "observed": observed,
                    "expected": expected,
                }
        if replay["run_id"] != manifest["run_id"]:
            replay_hash_mismatches["run_id"] = {
                "observed": replay["run_id"],
                "expected": manifest["run_id"],
            }
        check("repeat_run_hashes", not replay_hash_mismatches, replay_hash_mismatches, {})

    result = {
        "schema_version": "text-ner-method-run-acceptance/1.0.0",
        "passed": all(item["passed"] for item in checks),
        "counts": {
            "calibration_text_units": manifest["input"]["text_units"],
            "mention_requests": len(mentions),
            "relation_requests_pending": len(relations),
            "candidate_annotations": len(candidates),
            "evaluation_access_count": manifest["input"]["evaluation_access_count"],
            "model_calls": manifest["execution"]["model_calls"],
        },
        "checks": checks,
    }
    _write_report(result, output_json, output_markdown)
    if not result["passed"]:
        raise ValueError("TEXT_NER_METHOD_RUN_AUDIT_FAILED")
    return result
