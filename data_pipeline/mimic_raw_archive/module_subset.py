"""Extract admissions containing MIMIC-IV hosp, MIMIC-IV-ED and MIMIC-IV-Note.

The raw archive stores those products as separate top-level modules. ICU content is
reported for audit purposes but is deliberately excluded from the selection rule;
the archive itself already excludes high-volume ``chartevents`` monitoring data.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


REQUIRED_MODULES = ("mimic_iv_hosp", "mimic_iv_ed", "mimic_iv_note")
AUDITED_MODULES = (*REQUIRED_MODULES, "mimic_iv_icu")
MODULE_LABELS = {
    "mimic_iv_hosp": "MIMIC-IV（HOSP）",
    "mimic_iv_ed": "MIMIC-IV-ED",
    "mimic_iv_note": "MIMIC-IV-Note",
    "mimic_iv_icu": "MIMIC-IV ICU（仅统计）",
}


class ModuleSubsetError(ValueError):
    """Raised when a source record cannot be classified without guessing."""


def module_has_content(record: dict[str, Any], module_name: str) -> bool:
    """Return whether at least one source table in a module has one or more rows."""
    module = record.get(module_name)
    if not isinstance(module, dict):
        raise ModuleSubsetError(f"{module_name} must be an object")
    has_content = False
    for table_name, rows in module.items():
        if not isinstance(rows, list):
            raise ModuleSubsetError(f"{module_name}.{table_name} must be an array")
        if rows:
            has_content = True
    return has_content


def classify_record(record: dict[str, Any]) -> dict[str, bool]:
    """Classify source-product coverage without using ICU as a requirement."""
    if not isinstance(record, dict):
        raise ModuleSubsetError("JSONL record must be an object")
    if not record.get("subject_id") or not record.get("hadm_id"):
        raise ModuleSubsetError("subject_id and hadm_id are required")
    return {name: module_has_content(record, name) for name in AUDITED_MODULES}


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    _atomic_write_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def _format_bytes(value: float | int) -> str:
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.2f} {unit}"
        size /= 1024
    raise AssertionError("unreachable")


def _format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    seconds = max(0, int(round(seconds)))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}时{minutes:02d}分{seconds:02d}秒"
    return f"{minutes}分{seconds:02d}秒"


def render_monitor_html(status: dict[str, Any]) -> str:
    """Render a standalone monitor page; running pages reload from disk every 2s."""
    running = status["status"] == "running"
    refresh = '<meta http-equiv="refresh" content="2">' if running else ""
    progress = float(status.get("progress_percent", 0.0))
    module_counts = status.get("module_counts", {})
    pair_counts = status.get("intersection_counts", {})
    table_counts = status.get("nonempty_table_record_counts", {})
    rows = "".join(
        "<tr><td>{}</td><td>{:,}</td></tr>".format(html.escape(name), count)
        for name, count in sorted(table_counts.items())
    ) or '<tr><td colspan="2" class="muted">等待首条记录</td></tr>'
    status_class = {"running": "run", "complete": "ok", "failed": "bad"}.get(
        status["status"], ""
    )
    error_html = ""
    if status.get("error"):
        error_html = '<section class="error"><b>处理失败</b><pre>{}</pre></section>'.format(
            html.escape(str(status["error"]))
        )
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">{refresh}
<title>MIMIC 三模块子集提取监控</title>
<style>
:root{{--bg:#08111f;--panel:#111d31;--line:#263958;--text:#eef5ff;--muted:#91a4c2;--blue:#58a6ff;--green:#42d392;--red:#ff6b81}}
*{{box-sizing:border-box}}body{{margin:0;background:linear-gradient(145deg,#08111f,#0e1730);color:var(--text);font-family:system-ui,"Microsoft YaHei",sans-serif}}
main{{max-width:1180px;margin:auto;padding:28px}}header{{display:flex;justify-content:space-between;gap:20px;align-items:end}}h1{{margin:0 0 7px;font-size:27px}}.muted{{color:var(--muted)}}.badge{{padding:8px 14px;border-radius:999px;background:#1d2d49;font-weight:700}}.run{{color:var(--blue)}}.ok{{color:var(--green)}}.bad{{color:var(--red)}}
.progress{{height:13px;background:#1a2943;border-radius:20px;overflow:hidden;margin:22px 0 8px}}.progress i{{display:block;height:100%;width:{progress:.4f}%;background:linear-gradient(90deg,var(--blue),var(--green))}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:13px;margin:20px 0}}.card,.panel,.error{{background:rgba(17,29,49,.96);border:1px solid var(--line);border-radius:14px;padding:17px}}.label{{font-size:13px;color:var(--muted)}}.value{{font-size:25px;font-weight:750;margin-top:7px}}.panel{{margin-top:14px}}table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;padding:9px;border-bottom:1px solid var(--line)}}th{{color:var(--muted)}}.tables{{max-height:360px;overflow:auto}}.error{{border-color:var(--red);margin-top:14px}}pre{{white-space:pre-wrap}}
@media(max-width:850px){{.grid{{grid-template-columns:repeat(2,1fr)}}header{{display:block}}}}
</style></head><body><main>
<header><div><h1>MIMIC 三模块子集提取</h1><div class="muted">HOSP + ED + Note；ICU 内容不参与筛选</div></div><div class="badge {status_class}">{html.escape(status['status_label'])}</div></header>
<div class="progress"><i></i></div><div class="muted">{progress:.2f}% · {html.escape(status['input_path'])}</div>
<div class="grid">
<div class="card"><div class="label">已处理记录</div><div class="value">{status['records_processed']:,}</div></div>
<div class="card"><div class="label">三模块命中</div><div class="value">{status['matched_records']:,}</div></div>
<div class="card"><div class="label">已读取 / 总大小</div><div class="value">{_format_bytes(status['input_bytes_read'])}</div><div class="muted">共 {_format_bytes(status['input_bytes_total'])}</div></div>
<div class="card"><div class="label">平均速度</div><div class="value">{_format_bytes(status['bytes_per_second'])}/s</div></div>
<div class="card"><div class="label">已用时间</div><div class="value">{_format_duration(status['elapsed_seconds'])}</div></div>
<div class="card"><div class="label">预计剩余</div><div class="value">{_format_duration(status.get('eta_seconds'))}</div></div>
<div class="card"><div class="label">输出大小</div><div class="value">{_format_bytes(status['output_bytes_written'])}</div></div>
<div class="card"><div class="label">结构/解析异常</div><div class="value">{status['invalid_records']:,}</div></div>
</div>
<section class="panel"><h3>模块覆盖</h3><table><thead><tr><th>模块</th><th>记录数</th><th>筛选角色</th></tr></thead><tbody>
<tr><td>MIMIC-IV（HOSP）</td><td>{module_counts.get('mimic_iv_hosp',0):,}</td><td>必需</td></tr>
<tr><td>MIMIC-IV-ED</td><td>{module_counts.get('mimic_iv_ed',0):,}</td><td>必需</td></tr>
<tr><td>MIMIC-IV-Note</td><td>{module_counts.get('mimic_iv_note',0):,}</td><td>必需</td></tr>
<tr><td>MIMIC-IV ICU</td><td>{module_counts.get('mimic_iv_icu',0):,}</td><td>仅统计；不要求</td></tr>
</tbody></table></section>
<section class="panel"><h3>交集统计</h3><table><thead><tr><th>交集</th><th>记录数</th></tr></thead><tbody>
<tr><td>HOSP ∩ ED</td><td>{pair_counts.get('hosp_and_ed',0):,}</td></tr>
<tr><td>HOSP ∩ Note</td><td>{pair_counts.get('hosp_and_note',0):,}</td></tr>
<tr><td>ED ∩ Note</td><td>{pair_counts.get('ed_and_note',0):,}</td></tr>
<tr><td>HOSP ∩ ED ∩ Note</td><td>{pair_counts.get('all_three',0):,}</td></tr>
</tbody></table></section>
<section class="panel"><h3>非空源表覆盖</h3><div class="tables"><table><thead><tr><th>源表</th><th>非空记录数</th></tr></thead><tbody>{rows}</tbody></table></div></section>
{error_html}<p class="muted">更新时间：{html.escape(status['updated_at'])}。运行时页面每 2 秒重新读取本文件；完成后停止刷新。</p>
</main></body></html>"""


def _new_status(input_path: Path, output_path: Path, input_size: int) -> dict[str, Any]:
    return {
        "status": "running",
        "status_label": "正在处理",
        "started_at": _now_iso(),
        "updated_at": _now_iso(),
        "completed_at": None,
        "input_path": str(input_path.resolve()),
        "output_path": str(output_path.resolve()),
        "selection_rule": {
            "required_nonempty_modules": list(REQUIRED_MODULES),
            "icu_role": "audit_only_not_required",
            "content_definition": "at least one source table array contains a row",
        },
        "records_processed": 0,
        "matched_records": 0,
        "invalid_records": 0,
        "input_bytes_total": input_size,
        "input_bytes_read": 0,
        "output_bytes_written": 0,
        "progress_percent": 0.0,
        "elapsed_seconds": 0.0,
        "bytes_per_second": 0.0,
        "eta_seconds": None,
        "module_counts": {name: 0 for name in AUDITED_MODULES},
        "intersection_counts": {
            "hosp_and_ed": 0,
            "hosp_and_note": 0,
            "ed_and_note": 0,
            "all_three": 0,
        },
        "nonempty_table_record_counts": {},
        "input_sha256": None,
        "output_sha256": None,
        "error": None,
    }


def _update_rates(status: dict[str, Any], started: float) -> None:
    elapsed = max(0.0, time.monotonic() - started)
    read_bytes = int(status["input_bytes_read"])
    total_bytes = int(status["input_bytes_total"])
    speed = read_bytes / elapsed if elapsed > 0 else 0.0
    status["elapsed_seconds"] = elapsed
    status["bytes_per_second"] = speed
    status["progress_percent"] = (
        min(100.0, read_bytes * 100.0 / total_bytes) if total_bytes else 100.0
    )
    status["eta_seconds"] = (
        max(0.0, (total_bytes - read_bytes) / speed) if speed > 0 else None
    )
    status["updated_at"] = _now_iso()


def _publish_status(
    status: dict[str, Any], status_path: Path, monitor_path: Path
) -> None:
    _atomic_write_json(status_path, status)
    _atomic_write_text(monitor_path, render_monitor_html(status))


def extract_subset(
    input_path: Path,
    output_path: Path,
    summary_path: Path,
    monitor_path: Path,
    status_path: Path,
    *,
    refresh_seconds: float = 1.0,
    max_records: int | None = None,
) -> dict[str, Any]:
    """Stream a JSONL archive and preserve qualifying source lines byte-for-byte."""
    input_path = input_path.resolve()
    output_path = output_path.resolve()
    summary_path = summary_path.resolve()
    monitor_path = monitor_path.resolve()
    status_path = status_path.resolve()
    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    if input_path == output_path:
        raise ValueError("input and output paths must differ")
    for target in (output_path, summary_path, monitor_path, status_path):
        if target.exists():
            raise FileExistsError(f"refusing to overwrite existing output: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
    partial_path = output_path.with_suffix(output_path.suffix + ".partial")
    if partial_path.exists():
        raise FileExistsError(f"refusing to overwrite incomplete output: {partial_path}")

    status = _new_status(input_path, output_path, input_path.stat().st_size)
    module_counts: Counter[str] = Counter()
    intersections: Counter[str] = Counter()
    table_counts: Counter[str] = Counter()
    input_digest = hashlib.sha256()
    output_digest = hashlib.sha256()
    started = time.monotonic()
    last_publish = 0.0
    _publish_status(status, status_path, monitor_path)

    try:
        with input_path.open("rb") as source, partial_path.open("xb") as output:
            for line_number, raw_line in enumerate(source, start=1):
                input_digest.update(raw_line)
                try:
                    record = json.loads(raw_line)
                    coverage = classify_record(record)
                except (json.JSONDecodeError, UnicodeDecodeError, ModuleSubsetError) as error:
                    status["invalid_records"] += 1
                    raise ModuleSubsetError(
                        f"line {line_number}, byte offset {source.tell()}: {error}"
                    ) from error

                status["records_processed"] += 1
                for module_name, present in coverage.items():
                    if present:
                        module_counts[module_name] += 1
                for module_name in AUDITED_MODULES:
                    for table_name, rows in record[module_name].items():
                        if rows:
                            table_counts[f"{module_name}.{table_name}"] += 1

                hosp = coverage["mimic_iv_hosp"]
                ed = coverage["mimic_iv_ed"]
                note = coverage["mimic_iv_note"]
                if hosp and ed:
                    intersections["hosp_and_ed"] += 1
                if hosp and note:
                    intersections["hosp_and_note"] += 1
                if ed and note:
                    intersections["ed_and_note"] += 1
                if hosp and ed and note:
                    intersections["all_three"] += 1
                    preserved_line = raw_line if raw_line.endswith(b"\n") else raw_line + b"\n"
                    output.write(preserved_line)
                    output_digest.update(preserved_line)
                    status["matched_records"] += 1
                    status["output_bytes_written"] += len(preserved_line)

                status["input_bytes_read"] = source.tell()
                status["module_counts"] = {
                    name: module_counts[name] for name in AUDITED_MODULES
                }
                status["intersection_counts"] = {
                    name: intersections[name]
                    for name in (
                        "hosp_and_ed",
                        "hosp_and_note",
                        "ed_and_note",
                        "all_three",
                    )
                }
                status["nonempty_table_record_counts"] = dict(table_counts)
                now = time.monotonic()
                if now - last_publish >= refresh_seconds:
                    _update_rates(status, started)
                    _publish_status(status, status_path, monitor_path)
                    last_publish = now
                if max_records is not None and line_number >= max_records:
                    break
            output.flush()
            os.fsync(output.fileno())

        os.replace(partial_path, output_path)
        _update_rates(status, started)
        status["status"] = "complete"
        status["status_label"] = "处理完成"
        status["completed_at"] = _now_iso()
        status["eta_seconds"] = 0.0
        status["input_sha256"] = input_digest.hexdigest()
        status["output_sha256"] = output_digest.hexdigest()
        status["limited_run"] = max_records is not None
        _atomic_write_json(summary_path, status)
        _publish_status(status, status_path, monitor_path)
        return status
    except Exception as error:
        _update_rates(status, started)
        status["status"] = "failed"
        status["status_label"] = "处理失败"
        status["error"] = f"{type(error).__name__}: {error}"
        _publish_status(status, status_path, monitor_path)
        raise


def _default_paths(input_path: Path) -> tuple[Path, Path, Path, Path]:
    stem = input_path.stem + "-all-three-modules"
    parent = input_path.parent
    return (
        parent / f"{stem}.jsonl",
        parent / f"{stem}-summary.json",
        parent / f"{stem}-monitor.html",
        parent / f"{stem}-status.json",
    )


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract records with non-empty MIMIC-IV HOSP, ED and Note modules"
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--monitor-html", type=Path)
    parser.add_argument("--status-json", type=Path)
    parser.add_argument("--refresh-seconds", type=float, default=1.0)
    parser.add_argument("--max-records", type=int)
    return parser


def main() -> None:
    args = create_parser().parse_args()
    defaults = _default_paths(args.input)
    result = extract_subset(
        args.input,
        args.output or defaults[0],
        args.summary or defaults[1],
        args.monitor_html or defaults[2],
        args.status_json or defaults[3],
        refresh_seconds=args.refresh_seconds,
        max_records=args.max_records,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
