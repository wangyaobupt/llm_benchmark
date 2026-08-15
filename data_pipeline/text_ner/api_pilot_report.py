"""Payload-free acceptance reporting for an OpenAI-compatible NER pilot."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from statistics import median
from typing import Any


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"PILOT_REPORT_JSONL_NOT_OBJECT: {path}:{line_number}")
            rows.append(value)
    return rows


def _usage(value: object) -> dict[str, int]:
    source = value if isinstance(value, dict) else {}
    return {
        key: item if isinstance(item := source.get(key), int) else 0
        for key in ("prompt_tokens", "completion_tokens", "total_tokens")
    }


def _write_atomically(path: Path, content: str) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.temporary")
    try:
        temporary.write_text(content, encoding="utf-8", newline="\n")
        os.replace(temporary, destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def _markdown(summary: dict[str, Any]) -> str:
    counts = summary["counts"]
    quality = summary["quality_gate"]
    usage = summary["usage"]
    failure_lines = "\n".join(
        f"| `{reason}` | {count:,} |"
        for reason, count in summary["unresolved_failure_reasons"].items()
    ) or "| 无 | 0 |"
    grounding_lines = "\n".join(
        f"| `{rule}` | {count:,} |"
        for rule, count in summary["span_grounding"]["rule_counts"].items()
    ) or "| 无 | 0 |"
    return f"""# Text NER API Pilot 验收

## 结论

- 技术状态：`{quality['status']}`
- 是否具备扩大到500条的技术条件：`{str(quality['can_expand_to_500']).lower()}`
- 模型结果状态：`unreviewed_model_output`
- 本报告不构成人工准确性或实验有效性验证。

## 覆盖与结果

| 指标 | 数值 |
|---|---:|
| Pilot 目标 | {summary['pilot_target']:,} |
| 已尝试不同文本单元 | {counts['attempted_unique']:,} |
| 成功响应 | {counts['successful_unique']:,} |
| 尚未解决失败 | {counts['unresolved_failed_unique']:,} |
| 中断在重试过程中的文本单元 | {counts['incomplete_failed_unique']:,} |
| 未解决失败率 | {quality['unresolved_failure_rate']:.2%} |
| response/audit 单边缺失 | {counts['response_only']:,} / {counts['audit_only']:,} |

## Token 与调用

| 指标 | 数值 |
|---|---:|
| 模型调用 | {counts['model_calls']:,} |
| Prompt tokens | {usage['prompt_tokens']:,} |
| Completion tokens | {usage['completion_tokens']:,} |
| Total tokens | {usage['total_tokens']:,} |
| 每次调用 token 中位数 | {usage['median_tokens_per_call']:.1f} |
| 每个不同文本单元平均 tokens | {usage['mean_tokens_per_attempted_unit']:.1f} |

## Span grounding

| 规则 | 次数 |
|---|---:|
{grounding_lines}

- 发生 grounding 的成功响应：{summary['span_grounding']['successful_responses_with_repairs']:,}
- repair 总数：{summary['span_grounding']['repair_count']:,}
- 从原文回填 surface：{summary['span_grounding']['surface_rewrite_count']:,}

## 尚未解决失败原因

| 原因 | 文本单元数 |
|---|---:|
{failure_lines}

## 扩大条件

- 累计覆盖达到 pilot 目标；
- 未解决合同失败率不高于 {quality['maximum_unresolved_failure_rate']:.0%}；
- 不存在只记录了待重试失败、但没有成功或终止失败的文本单元；
- response/audit 无单边缺失；
- 即使技术门通过，扩大后的输出仍须标记为 `unreviewed_model_output`。
"""


def summarize_api_pilot(
    responses_path: Path,
    audit_path: Path,
    failure_audit_path: Path,
    *,
    pilot_target: int,
    output_json_path: Path,
    output_markdown_path: Path,
    maximum_unresolved_failure_rate: float = 0.05,
) -> dict[str, Any]:
    if pilot_target <= 0:
        raise ValueError(f"PILOT_REPORT_TARGET_INVALID: {pilot_target}")
    if not 0.0 <= maximum_unresolved_failure_rate <= 1.0:
        raise ValueError(
            "PILOT_REPORT_FAILURE_RATE_INVALID: "
            f"{maximum_unresolved_failure_rate}"
        )
    responses = _load_jsonl(Path(responses_path))
    audits = _load_jsonl(Path(audit_path))
    failures = _load_jsonl(Path(failure_audit_path))
    response_ids = {str(row["request_id"]) for row in responses}
    audit_ids = {str(row["request_id"]) for row in audits}
    failure_ids = {
        str(row["request_id"]) for row in failures if row.get("request_id")
    }
    terminal_failure_ids: set[str] = set()
    terminal_reason_by_id: dict[str, str] = {}
    for row in failures:
        if row.get("will_retry") is False and row.get("request_id"):
            request_id = str(row["request_id"])
            terminal_failure_ids.add(request_id)
            terminal_reason_by_id[request_id] = str(
                row.get("annotation_validation_reason_code")
                or row.get("reason_code")
                or "UNKNOWN"
            )
    unresolved_failure_ids = terminal_failure_ids - response_ids
    incomplete_failure_ids = failure_ids - terminal_failure_ids - response_ids
    attempted_ids = response_ids | failure_ids
    unresolved_reasons = Counter(
        terminal_reason_by_id[request_id] for request_id in unresolved_failure_ids
    )

    token_rows = [_usage(row.get("usage")) for row in (*audits, *failures)]
    total_usage = {
        key: sum(row[key] for row in token_rows)
        for key in ("prompt_tokens", "completion_tokens", "total_tokens")
    }
    token_values = [row["total_tokens"] for row in token_rows]
    grounding_rules: Counter[str] = Counter()
    repaired_successes = 0
    repair_count = 0
    surface_rewrite_count = 0
    for row in audits:
        grounding = row.get("span_grounding")
        if not isinstance(grounding, dict):
            continue
        repairs = grounding.get("repairs")
        if not isinstance(repairs, list):
            continue
        if repairs:
            repaired_successes += 1
        repair_count += len(repairs)
        for repair in repairs:
            if not isinstance(repair, dict):
                continue
            grounding_rules[str(repair.get("rule") or "UNKNOWN")] += 1
            if repair.get("surface_rewritten_from_source") is True:
                surface_rewrite_count += 1

    attempted_count = len(attempted_ids)
    unresolved_rate = (
        len(unresolved_failure_ids) / attempted_count if attempted_count else 0.0
    )
    response_only = len(response_ids - audit_ids)
    audit_only = len(audit_ids - response_ids)
    coverage_reached = attempted_count >= pilot_target
    can_expand = (
        coverage_reached
        and unresolved_rate <= maximum_unresolved_failure_rate
        and not incomplete_failure_ids
        and response_only == 0
        and audit_only == 0
    )
    status = (
        "technical_pilot_passed"
        if can_expand
        else ("pilot_incomplete" if not coverage_reached else "technical_pilot_failed")
    )
    summary = {
        "schema_version": "text-ner-api-pilot-report/1.0.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "pilot_target": pilot_target,
        "counts": {
            "attempted_unique": attempted_count,
            "successful_unique": len(response_ids),
            "unresolved_failed_unique": len(unresolved_failure_ids),
            "incomplete_failed_unique": len(incomplete_failure_ids),
            "model_calls": len(token_rows),
            "response_only": response_only,
            "audit_only": audit_only,
        },
        "usage": {
            **total_usage,
            "median_tokens_per_call": median(token_values) if token_values else 0.0,
            "mean_tokens_per_attempted_unit": (
                total_usage["total_tokens"] / attempted_count
                if attempted_count
                else 0.0
            ),
        },
        "span_grounding": {
            "successful_responses_with_repairs": repaired_successes,
            "repair_count": repair_count,
            "surface_rewrite_count": surface_rewrite_count,
            "rule_counts": dict(sorted(grounding_rules.items())),
        },
        "unresolved_failure_reasons": dict(sorted(unresolved_reasons.items())),
        "quality_gate": {
            "status": status,
            "coverage_reached": coverage_reached,
            "unresolved_failure_rate": unresolved_rate,
            "maximum_unresolved_failure_rate": maximum_unresolved_failure_rate,
            "can_expand_to_500": can_expand,
            "validated_experimental_results": False,
        },
    }
    _write_atomically(
        Path(output_json_path),
        json.dumps(summary, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
    )
    _write_atomically(Path(output_markdown_path), _markdown(summary))
    return summary
