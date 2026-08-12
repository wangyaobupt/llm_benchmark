"""Independent acceptance checks for text NER input manifests."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from .contracts import MANIFEST_ARROW_SCHEMA, MANIFEST_SCHEMA_VERSION, RAW_TEXT_COLUMNS


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _load_sources(input_path: Path) -> dict[tuple[int, str, int], dict[str, Any]]:
    result: dict[tuple[int, str, int], dict[str, Any]] = {}
    with input_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            admission = json.loads(line)
            for module, table in (
                ("mimic_iv_ed", "triage"),
                ("mimic_iv_note", "radiology"),
                ("mimic_iv_note", "discharge"),
            ):
                for index, row in enumerate(admission[module].get(table, [])):
                    result[(line_number, f"{module}.{table}", index)] = row
    return result


def _check(name: str, passed: bool, observed: Any, expected: Any) -> dict[str, Any]:
    return {
        "check": name,
        "passed": bool(passed),
        "observed": observed,
        "expected": expected,
    }


def _markdown(report: dict[str, Any]) -> str:
    verdict = "通过" if report["passed"] else "未通过"
    lines = [
        "# Text NER 输入清单独立验收",
        "",
        f"结论：**{verdict}**。本阶段只生成可追溯输入清单，模型调用次数为 0。",
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
        status = "通过" if item["passed"] else "失败"
        observed = json.dumps(item["observed"], ensure_ascii=False, sort_keys=True)
        expected = json.dumps(item["expected"], ensure_ascii=False, sort_keys=True)
        lines.append(f"| `{item['check']}` | {status} | `{observed}` | `{expected}` |")
    lines.extend(
        [
            "",
            "## 边界",
            "",
            "- 清单不保存原始临床文本，只保存来源定位、字符 span 和 SHA-256。",
            "- ED chief complaint 的可用时间保持未知，不使用 ED 入科时间替代。",
            "- discharge summary 全部以 `POST_HOC_DISCHARGE` 排除。",
            "- 本验收不证明任何 NER 模型质量，也不授权模型调用。",
            "",
        ]
    )
    return "\n".join(lines)


def audit_manifest(
    input_path: Path,
    manifest_directory: Path,
    *,
    replay_directory: Path | None = None,
    output_json: Path | None = None,
    output_markdown: Path | None = None,
) -> dict[str, Any]:
    input_path = Path(input_path).resolve()
    manifest_directory = Path(manifest_directory).resolve()
    manifest_path = manifest_directory / "text_ner_input_manifest.parquet"
    summary_path = manifest_directory / "text_ner_input_manifest_summary.json"
    run_path = manifest_directory / "run_manifest.json"
    table = pq.read_table(manifest_path)
    rows = table.to_pylist()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    run = json.loads(run_path.read_text(encoding="utf-8"))
    sources = _load_sources(input_path)

    duplicate_rows = len(rows) - len({row["manifest_row_id"] for row in rows})
    included = [row for row in rows if row["inclusion_status"] == "included"]
    excluded = [row for row in rows if row["inclusion_status"] == "excluded"]
    source_failures = 0
    span_failures = 0
    time_failures = 0
    exclusion_failures = 0
    rows_by_document: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        rows_by_document.setdefault(row["document_id"], []).append(row)
        key = (
            row["jsonl_line_number"],
            f"{row['source_module']}.{row['source_table'].split('.', 1)[1]}",
            row["source_array_index"],
        )
        source = sources.get(key)
        if source is None:
            source_failures += 1
            continue
        text = str(source.get(row["text_field"]) or "")
        if _sha256_text(text) != row["source_text_sha256"] or len(text) != row["source_text_character_count"]:
            source_failures += 1
        if row["inclusion_status"] == "included":
            start, end = row["span_start"], row["span_end"]
            if (
                start is None
                or end is None
                or start < 0
                or end <= start
                or end > len(text)
                or _sha256_text(text[start:end]) != row["span_sha256"]
                or end - start != row["span_character_count"]
            ):
                span_failures += 1
        if row["source_table"] == "ed.triage" and (
            row["available_time"] is not None
            or "TIME_UNAVAILABLE_IN_SOURCE" not in row["quality_flags"]
        ):
            time_failures += 1
        if row["source_table"] == "note.radiology" and row["inclusion_status"] == "included" and (
            row["available_time"] is None or row["recorded_time"] is None
        ):
            time_failures += 1
        if row["source_table"] == "note.discharge" and (
            row["inclusion_status"] != "excluded"
            or row["reason_code"] != "POST_HOC_DISCHARGE"
            or row["evidence_phase"] != "post_hoc"
        ):
            exclusion_failures += 1

    coverage_failures = 0
    manifest_source_keys: set[tuple[int, str, int]] = set()
    for document_rows in rows_by_document.values():
        first = document_rows[0]
        manifest_source_keys.add(
            (
                first["jsonl_line_number"],
                f"{first['source_module']}.{first['source_table'].split('.', 1)[1]}",
                first["source_array_index"],
            )
        )
        included_rows = [
            row for row in document_rows if row["inclusion_status"] == "included"
        ]
        if not included_rows:
            continue
        ordered = sorted(included_rows, key=lambda row: row["section_ordinal"])
        cursor = 0
        for expected_ordinal, row in enumerate(ordered):
            if (
                row["section_ordinal"] != expected_ordinal
                or row["span_start"] != cursor
                or row["span_end"] is None
            ):
                coverage_failures += 1
                break
            cursor = row["span_end"]
        else:
            if cursor != first["source_text_character_count"]:
                coverage_failures += 1
    source_reconciliation_failures = len(
        set(sources) ^ manifest_source_keys
    )

    pilot_docs = {
        row["document_id"]
        for row in included
        if row["pilot_document_selected"]
    }
    pilot_sources = Counter(
        next(row["source_table"] for row in included if row["document_id"] == document_id)
        for document_id in pilot_docs
    )
    source_documents = Counter(
        (row["source_table"], row["inclusion_status"])
        for row in {item["document_id"]: item for item in rows}.values()
    )
    requested_pilot = summary["pilot"]["requested_documents"]
    expected_ed = min(
        source_documents[("ed.triage", "included")], requested_pilot // 2
    )
    expected_radiology = requested_pilot - expected_ed
    if source_documents[("note.radiology", "included")] < expected_radiology:
        expected_radiology = source_documents[("note.radiology", "included")]
        expected_ed = requested_pilot - expected_radiology
    expected_pilot_sources = {
        "ed.triage": expected_ed,
        "note.radiology": expected_radiology,
    }
    replay_match = True
    replay_hashes: dict[str, str] | None = None
    if replay_directory is not None:
        replay_directory = Path(replay_directory).resolve()
        replay_hashes = {
            name: _sha256_file(replay_directory / name)
            for name in (
                "text_ner_input_manifest.parquet",
                "text_ner_input_manifest_summary.json",
                "run_manifest.json",
            )
        }
        replay_match = replay_hashes == {
            name: _sha256_file(manifest_directory / name) for name in replay_hashes
        }

    checks = [
        _check("arrow_schema", table.schema == MANIFEST_ARROW_SCHEMA, str(table.schema.metadata), str(MANIFEST_ARROW_SCHEMA.metadata)),
        _check("schema_version", all(row["schema_version"] == MANIFEST_SCHEMA_VERSION for row in rows), sorted({row["schema_version"] for row in rows}), [MANIFEST_SCHEMA_VERSION]),
        _check("raw_text_columns_absent", not (set(table.column_names) & RAW_TEXT_COLUMNS), sorted(set(table.column_names) & RAW_TEXT_COLUMNS), []),
        _check("manifest_row_ids_unique", duplicate_rows == 0, duplicate_rows, 0),
        _check("source_hash_and_locator", source_failures == 0, source_failures, 0),
        _check("included_spans_exact", span_failures == 0, span_failures, 0),
        _check("section_coverage_exact", coverage_failures == 0, coverage_failures, 0),
        _check("source_document_reconciliation", source_reconciliation_failures == 0, source_reconciliation_failures, 0),
        _check("time_policy", time_failures == 0, time_failures, 0),
        _check("post_hoc_exclusion", exclusion_failures == 0 and not any(row["evidence_phase"] == "post_hoc" for row in included), exclusion_failures, 0),
        _check("pilot_document_count", len(pilot_docs) == summary["pilot"]["requested_documents"], len(pilot_docs), summary["pilot"]["requested_documents"]),
        _check("pilot_source_balance", dict(sorted(pilot_sources.items())) == expected_pilot_sources, dict(sorted(pilot_sources.items())), expected_pilot_sources),
        _check("model_calls", run["model"]["calls"] == 0 and summary["model_calls"] == 0, {"run": run["model"]["calls"], "summary": summary["model_calls"]}, {"run": 0, "summary": 0}),
        _check("input_hash", run["input"]["sha256"] == _sha256_file(input_path), run["input"]["sha256"], _sha256_file(input_path)),
        _check("repeat_run_hashes", replay_match, replay_hashes, "identical to primary run"),
    ]
    counts = {
        "manifest_rows": len(rows),
        "included_text_units": len(included),
        "excluded_documents": len(excluded),
        "ed_chief_complaint_documents": source_documents[("ed.triage", "included")],
        "radiology_documents": source_documents[("note.radiology", "included")],
        "discharge_documents_excluded": source_documents[("note.discharge", "excluded")],
        "pilot_documents": len(pilot_docs),
        "pilot_subjects": len({row["subject_id"] for row in included if row["pilot_document_selected"]}),
        "model_calls": run["model"]["calls"],
    }
    report = {
        "schema": {"name": "text_ner_input_manifest_acceptance", "version": "1.0.0"},
        "passed": all(item["passed"] for item in checks),
        "counts": counts,
        "checks": checks,
        "artifacts": {
            "input_sha256": _sha256_file(input_path),
            "manifest_sha256": _sha256_file(manifest_path),
            "summary_sha256": _sha256_file(summary_path),
            "run_manifest_sha256": _sha256_file(run_path),
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
    if not report["passed"]:
        failed = [item["check"] for item in checks if not item["passed"]]
        raise ValueError(f"TEXT_NER_MANIFEST_ACCEPTANCE_FAILED: {failed}")
    return report
