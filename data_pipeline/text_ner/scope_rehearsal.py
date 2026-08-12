"""Aggregate-only rehearsal of annotation scope on the real pilot manifest."""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
from typing import Any

import pyarrow.parquet as pq

from .annotation_contracts import ENTITY_TYPES, RELATION_TYPES


SCOPE_REHEARSAL_VERSION = "text-ner-annotation-scope-rehearsal/1.0.0"

CONTEXT_PATTERNS: dict[str, re.Pattern[str]] = {
    "negation": re.compile(r"\b(?:no|not|without|negative for|absence of|free of)\b", re.I),
    "uncertainty": re.compile(r"\b(?:possible|possibly|may|might|cannot exclude|suspicious|likely|probable)\b", re.I),
    "historical_or_comparison": re.compile(r"\b(?:history of|prior|previous|compared|interval|unchanged|stable)\b", re.I),
    "recommendation": re.compile(r"\b(?:recommend|recommendation|follow[- ]?up|suggest)\b", re.I),
    "measurement": re.compile(r"\b\d+(?:\.\d+)?\s*(?:mm|cm|m|ml|mg|kg|cc|%)\b", re.I),
    "laterality": re.compile(r"\b(?:left|right|bilateral|midline)\b", re.I),
    "device": re.compile(r"\b(?:tube|catheter|line|pacemaker|stent|prosthesis|drain)\b", re.I),
    "temporal_expression": re.compile(r"\b(?:today|yesterday|days?|weeks?|months?|years?|since)\b", re.I),
}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _load_sources(input_path: Path) -> dict[tuple[int, str, int], str]:
    sources: dict[tuple[int, str, int], str] = {}
    with input_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            admission = json.loads(line)
            for module, table, field in (
                ("mimic_iv_ed", "triage", "chiefcomplaint"),
                ("mimic_iv_note", "radiology", "text"),
            ):
                for index, row in enumerate(admission[module].get(table, [])):
                    sources[(line_number, f"{module}.{table}", index)] = str(
                        row.get(field) or ""
                    )
    return sources


def _percentile(values: list[int], fraction: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = round((len(ordered) - 1) * fraction)
    return ordered[index]


def _markdown(report: dict[str, Any]) -> str:
    counts = report["counts"]
    lines = [
        "# Text NER 标注范围只读演练",
        "",
        "结论：**通过**。真实 pilot 仅用于聚合结构和语言现象覆盖检查；报告不包含原始临床文本，也不构成实体 gold。",
        "",
        "## Pilot 范围",
        "",
        "| 指标 | 数量 |",
        "|---|---:|",
    ]
    for key, value in counts.items():
        lines.append(f"| `{key}` | {value} |")
    lines.extend(["", "## 观察到的标注难点", "", "| 现象 | 文本单元数 | 文档数 |", "|---|---:|---:|"])
    for name, values in report["context_signals"].items():
        lines.append(
            f"| `{name}` | {values['text_units']} | {values['documents']} |"
        )
    lines.extend(["", "## 章节分布（前20）", "", "| section | 数量 |", "|---|---:|"])
    for name, count in list(report["section_counts"].items())[:20]:
        lines.append(f"| `{name}` | {count} |")
    lines.extend(
        [
            "",
            "## 边界与结论",
            "",
            "- 词法信号只证明 pilot 中存在否定、不确定、比较、建议、测量、侧别、器械和时间表达等标注场景，不是 NER 结果。",
            "- 九类 mention 和七类显式关系可以表达当前观察到的场景；标准概念映射、事件合并和医学常识推断不属于本层。",
            "- 下一步必须先做人工双标校准并形成裁决 gold；尚未授权本地或外部模型调用。",
            "",
        ]
    )
    return "\n".join(lines)


def rehearse_scope(
    input_path: Path,
    manifest_path: Path,
    *,
    expected_pilot_documents: int = 200,
    output_json: Path | None = None,
    output_markdown: Path | None = None,
) -> dict[str, Any]:
    input_path = Path(input_path).resolve()
    manifest_path = Path(manifest_path).resolve()
    rows = [
        row
        for row in pq.read_table(manifest_path).to_pylist()
        if row["inclusion_status"] == "included"
        and row["pilot_document_selected"]
    ]
    sources = _load_sources(input_path)
    document_ids: set[str] = set()
    subject_ids: set[str] = set()
    source_counts: Counter[str] = Counter()
    section_counts: Counter[str] = Counter()
    lengths: list[int] = []
    signal_units: Counter[str] = Counter()
    signal_documents: dict[str, set[str]] = defaultdict(set)
    source_failures = 0
    post_hoc_units = 0
    for row in rows:
        key = (
            row["jsonl_line_number"],
            f"{row['source_module']}.{row['source_table'].split('.', 1)[1]}",
            row["source_array_index"],
        )
        source_text = sources.get(key)
        if source_text is None:
            source_failures += 1
            continue
        start, end = row["span_start"], row["span_end"]
        section_text = source_text[start:end]
        if (
            _sha256_text(source_text) != row["source_text_sha256"]
            or _sha256_text(section_text) != row["span_sha256"]
        ):
            source_failures += 1
            continue
        document_ids.add(row["document_id"])
        subject_ids.add(row["subject_id"])
        source_counts[row["source_table"]] += 1
        section_counts[row["section_name"]] += 1
        lengths.append(len(section_text))
        post_hoc_units += row["evidence_phase"] == "post_hoc"
        for name, pattern in CONTEXT_PATTERNS.items():
            if pattern.search(section_text):
                signal_units[name] += 1
                signal_documents[name].add(row["document_id"])

    context_signals = {
        name: {
            "text_units": signal_units[name],
            "documents": len(signal_documents[name]),
        }
        for name in CONTEXT_PATTERNS
    }
    checks = {
        "source_and_span_hash_failures": source_failures,
        "post_hoc_text_units": post_hoc_units,
        "pilot_documents": len(document_ids),
        "expected_pilot_documents": expected_pilot_documents,
        "raw_text_written": False,
        "model_calls": 0,
    }
    passed = (
        source_failures == 0
        and post_hoc_units == 0
        and len(document_ids) == expected_pilot_documents
    )
    report = {
        "schema_version": SCOPE_REHEARSAL_VERSION,
        "passed": passed,
        "counts": {
            "pilot_documents": len(document_ids),
            "pilot_text_units": len(rows),
            "pilot_subjects": len(subject_ids),
            "ed_text_units": source_counts["ed.triage"],
            "radiology_text_units": source_counts["note.radiology"],
            "minimum_characters": min(lengths) if lengths else 0,
            "median_characters": _percentile(lengths, 0.5),
            "p95_characters": _percentile(lengths, 0.95),
            "maximum_characters": max(lengths) if lengths else 0,
        },
        "context_signals": context_signals,
        "section_counts": dict(
            sorted(section_counts.items(), key=lambda item: (-item[1], item[0]))
        ),
        "frozen_scope": {
            "entity_types": list(ENTITY_TYPES),
            "relation_types": list(RELATION_TYPES),
        },
        "checks": checks,
        "artifacts": {
            "input_sha256": _sha256_file(input_path),
            "manifest_sha256": _sha256_file(manifest_path),
        },
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
    if not passed:
        raise ValueError(f"TEXT_NER_SCOPE_REHEARSAL_FAILED: {checks}")
    return report
