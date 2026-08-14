"""Run the existing full-cohort pipelines and publish a local HTML monitor."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import html
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any, Sequence


RUNNER_SCHEMA = {"name": "full_cohort_run_status", "version": "1.0.0"}


class FullCohortRunError(RuntimeError):
    """Raised when the detached full-cohort run cannot proceed safely."""


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _atomic_write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(value, encoding="utf-8")
    os.replace(temporary, path)


def _format_bytes(value: int | None) -> str:
    if value is None:
        return "—"
    size = float(value)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            return f"{size:.2f} {unit}"
        size /= 1024
    raise AssertionError("unreachable")


def _file_size(path: Path) -> int | None:
    try:
        return path.stat().st_size
    except FileNotFoundError:
        return None


def _tail(path: Path, max_lines: int = 40, max_bytes: int = 64 * 1024) -> str:
    if not path.is_file():
        return "日志尚未生成。"
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        length = handle.tell()
        handle.seek(max(0, length - max_bytes))
        data = handle.read().decode("utf-8", errors="replace")
    return "\n".join(data.splitlines()[-max_lines:]) or "日志当前为空。"


def _event_stage(event_output: Path) -> tuple[str, list[str]]:
    if (event_output / "workflow_manifest.json").is_file():
        return "正式 Event 目录已发布", ["workflow_manifest.json"]

    candidates = sorted(event_output.parent.glob(f".{event_output.name}.tmp-*"))
    if not candidates:
        return "等待 Event 临时目录", []

    root = candidates[-1]
    checks = (
        ("cleaning/run_manifest.json", "正式 cleaning 已完成"),
        (
            "normalization/normalization_manifest.json",
            "正式 normalization 已完成",
        ),
        (".replay/cleaning/run_manifest.json", "复跑 cleaning 已完成"),
        (
            ".replay/normalization/normalization_manifest.json",
            "复跑 normalization 已完成",
        ),
    )
    artifacts = [relative for relative, _ in checks if (root / relative).is_file()]
    for relative, label in reversed(checks):
        if (root / relative).is_file():
            return label, artifacts

    if (root / "cleaning").exists():
        return "正在生成正式 cleaning", artifacts
    return "Event 临时目录已建立", artifacts


def collect_runtime(
    input_path: Path,
    readable_output: Path,
    report_path: Path,
    event_output: Path,
    active_log: Path | None,
) -> dict[str, Any]:
    partial_output = readable_output.with_suffix(readable_output.suffix + ".partial")
    event_detail, event_artifacts = _event_stage(event_output)
    disk = shutil.disk_usage(event_output.parent)
    return {
        "input_bytes": _file_size(input_path),
        "readable_partial_bytes": _file_size(partial_output),
        "readable_output_bytes": _file_size(readable_output),
        "report_exists": report_path.is_file(),
        "event_output_exists": event_output.is_dir(),
        "event_detail": event_detail,
        "event_artifacts": event_artifacts,
        "disk_free_bytes": disk.free,
        "active_log": str(active_log) if active_log else None,
        "log_tail": _tail(active_log) if active_log else "尚未进入执行阶段。",
    }


def render_monitor(state: dict[str, Any]) -> str:
    runtime = state.get("runtime", {})
    status = str(state.get("status", "unknown"))
    status_label = {
        "starting": "正在启动",
        "running": "运行中",
        "succeeded": "全部通过",
        "failed": "运行失败",
    }.get(status, status)
    status_class = {
        "running": "running",
        "succeeded": "success",
        "failed": "failed",
    }.get(status, "starting")
    artifacts = runtime.get("event_artifacts") or []
    artifact_html = "".join(
        f"<li><code>{html.escape(str(item))}</code></li>" for item in artifacts
    ) or "<li>尚无已完成阶段标志。</li>"
    error = state.get("error")
    error_html = (
        f'<section class="error"><h2>失败原因</h2><pre>{html.escape(str(error))}</pre></section>'
        if error
        else ""
    )
    updated_at = html.escape(str(state.get("updated_at", "")))
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="15">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MIMIC 冠脉全队列清洗监控</title>
<style>
:root {{ color-scheme: light; --ink:#13231f; --muted:#60706b; --paper:#f3f7f5; --card:#fff; --line:#d8e3df; --accent:#087f5b; --danger:#b42318; }}
* {{ box-sizing:border-box; }} body {{ margin:0; background:var(--paper); color:var(--ink); font:15px/1.55 "Segoe UI","Microsoft YaHei",sans-serif; }}
main {{ max-width:1120px; margin:0 auto; padding:32px 22px 56px; }} h1 {{ margin:0 0 6px; font-size:28px; }} h2 {{ margin:0 0 12px; font-size:17px; }}
.sub {{ color:var(--muted); margin-bottom:22px; }} .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px; }}
.card, section {{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:17px; box-shadow:0 4px 16px rgba(20,55,44,.05); }}
.label {{ color:var(--muted); font-size:13px; }} .value {{ margin-top:5px; font-size:18px; font-weight:650; overflow-wrap:anywhere; }}
.status {{ display:inline-block; padding:6px 11px; border-radius:999px; font-weight:700; }} .running {{ color:#075b45; background:#d8f5e9; }} .success {{ color:#075b45; background:#c7f0dd; }} .failed {{ color:#8a1c13; background:#fee4e2; }} .starting {{ color:#6b4f00; background:#fff2c7; }}
section {{ margin-top:14px; }} code, pre {{ font-family:"Cascadia Mono",Consolas,monospace; }} pre {{ white-space:pre-wrap; overflow-wrap:anywhere; background:#101c19; color:#d9eee7; border-radius:10px; padding:14px; max-height:380px; overflow:auto; }}
ul {{ margin:0; padding-left:20px; }} .error {{ border-color:#f4b8b2; }} #stale {{ display:none; margin:12px 0; padding:10px 12px; background:#fff2c7; border-radius:9px; }}
</style>
</head>
<body data-updated-at="{updated_at}">
<main>
  <h1>MIMIC 冠脉全队列清洗监控</h1>
  <div class="sub">页面每 15 秒重新读取本地 HTML。进度仅展示已落盘、可核验的状态。</div>
  <div id="stale">状态超过 60 秒未更新，后台编排器可能已经停止；请检查日志。</div>
  <div class="grid">
    <div class="card"><div class="label">总状态</div><div class="value"><span class="status {status_class}">{html.escape(status_label)}</span></div></div>
    <div class="card"><div class="label">当前阶段</div><div class="value">{html.escape(str(state.get("stage", "—")))}</div></div>
    <div class="card"><div class="label">编排器 / 子进程 PID</div><div class="value">{html.escape(str(state.get("runner_pid", "—")))} / {html.escape(str(state.get("child_pid") or "—"))}</div></div>
    <div class="card"><div class="label">最后更新</div><div class="value">{updated_at or "—"}</div></div>
    <div class="card"><div class="label">原始输入</div><div class="value">{_format_bytes(runtime.get("input_bytes"))}</div></div>
    <div class="card"><div class="label">临床可读 partial</div><div class="value">{_format_bytes(runtime.get("readable_partial_bytes"))}</div></div>
    <div class="card"><div class="label">临床可读正式输出</div><div class="value">{_format_bytes(runtime.get("readable_output_bytes"))}</div></div>
    <div class="card"><div class="label">G 盘剩余空间</div><div class="value">{_format_bytes(runtime.get("disk_free_bytes"))}</div></div>
  </div>
  <section><h2>Event 阶段</h2><p>{html.escape(str(runtime.get("event_detail", "—")))}</p><ul>{artifact_html}</ul></section>
  <section><h2>当前日志末尾</h2><div class="label">{html.escape(str(runtime.get("active_log") or "—"))}</div><pre>{html.escape(str(runtime.get("log_tail", "")))}</pre></section>
  {error_html}
</main>
<script>
const stamp = Date.parse(document.body.dataset.updatedAt);
if (!Number.isNaN(stamp) && Date.now() - stamp > 60000) document.getElementById('stale').style.display='block';
</script>
</body>
</html>
"""


def publish(
    state: dict[str, Any],
    state_path: Path,
    monitor_path: Path,
    *,
    input_path: Path,
    readable_output: Path,
    report_path: Path,
    event_output: Path,
    active_log: Path | None,
) -> None:
    state["updated_at"] = _now()
    state["runtime"] = collect_runtime(
        input_path,
        readable_output,
        report_path,
        event_output,
        active_log,
    )
    _atomic_write_text(
        state_path,
        json.dumps(state, ensure_ascii=False, indent=2) + "\n",
    )
    _atomic_write_text(monitor_path, render_monitor(state))


def build_commands(
    python_executable: Path,
    input_path: Path,
    readable_output: Path,
    report_path: Path,
    event_output: Path,
) -> list[tuple[str, list[str]]]:
    return [
        (
            "clinical_readable",
            [
                str(python_executable),
                "-m",
                "data_pipeline.clean_clinical_archive",
                str(input_path),
                "--output",
                str(readable_output),
                "--report",
                str(report_path),
            ],
        ),
        (
            "event_pipeline",
            [
                str(python_executable),
                "-m",
                "data_pipeline.event_pipeline",
                "run",
                str(readable_output),
                "--raw-source-jsonl",
                str(input_path),
                "--output-dir",
                str(event_output),
            ],
        ),
    ]


def validate_targets(
    project_root: Path,
    python_executable: Path,
    input_path: Path,
    readable_output: Path,
    report_path: Path,
    event_output: Path,
    control_directory: Path,
) -> None:
    if not project_root.is_dir():
        raise FullCohortRunError(f"项目目录不存在：{project_root}")
    if not python_executable.is_file():
        raise FullCohortRunError(f"Python 不存在：{python_executable}")
    if not input_path.is_file():
        raise FullCohortRunError(f"输入 JSONL 不存在：{input_path}")
    targets = (
        readable_output,
        readable_output.with_suffix(readable_output.suffix + ".partial"),
        report_path,
        report_path.with_suffix(report_path.suffix + ".partial"),
        event_output,
        control_directory,
    )
    existing = [str(path) for path in targets if path.exists()]
    if existing:
        raise FullCohortRunError("拒绝覆盖已有路径：" + "; ".join(existing))


def run(args: argparse.Namespace) -> int:
    project_root = args.project_root.resolve()
    python_executable = args.python_executable.resolve()
    input_path = args.input.resolve()
    readable_output = args.readable_output.resolve()
    report_path = args.report.resolve()
    event_output = args.event_output.resolve()
    control_directory = args.control_directory.resolve()
    validate_targets(
        project_root,
        python_executable,
        input_path,
        readable_output,
        report_path,
        event_output,
        control_directory,
    )
    readable_output.parent.mkdir(parents=True, exist_ok=True)
    event_output.parent.mkdir(parents=True, exist_ok=True)
    control_directory.mkdir(parents=True, exist_ok=False)
    state_path = control_directory / "run-state.json"
    monitor_path = control_directory / "monitor.html"
    state: dict[str, Any] = {
        "schema": RUNNER_SCHEMA,
        "status": "starting",
        "stage": "preflight_complete",
        "started_at": _now(),
        "updated_at": _now(),
        "runner_pid": os.getpid(),
        "child_pid": None,
        "commands": [],
        "error": None,
    }
    active_log: Path | None = None
    publish(
        state,
        state_path,
        monitor_path,
        input_path=input_path,
        readable_output=readable_output,
        report_path=report_path,
        event_output=event_output,
        active_log=active_log,
    )

    try:
        for stage, command in build_commands(
            python_executable,
            input_path,
            readable_output,
            report_path,
            event_output,
        ):
            active_log = control_directory / f"{stage}.log"
            state.update(
                {
                    "status": "running",
                    "stage": stage,
                    "stage_started_at": _now(),
                    "child_pid": None,
                }
            )
            state["commands"].append({"stage": stage, "argv": command})
            with active_log.open("x", encoding="utf-8", newline="\n") as log:
                process = subprocess.Popen(
                    command,
                    cwd=project_root,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                state["child_pid"] = process.pid
                while process.poll() is None:
                    publish(
                        state,
                        state_path,
                        monitor_path,
                        input_path=input_path,
                        readable_output=readable_output,
                        report_path=report_path,
                        event_output=event_output,
                        active_log=active_log,
                    )
                    time.sleep(args.refresh_seconds)
                exit_code = process.returncode
            state["commands"][-1]["exit_code"] = exit_code
            state["commands"][-1]["finished_at"] = _now()
            state["child_pid"] = None
            if exit_code != 0:
                raise FullCohortRunError(
                    f"阶段 {stage} 失败，退出码 {exit_code}；详见 {active_log}"
                )

        state.update({"status": "succeeded", "stage": "completed"})
        publish(
            state,
            state_path,
            monitor_path,
            input_path=input_path,
            readable_output=readable_output,
            report_path=report_path,
            event_output=event_output,
            active_log=active_log,
        )
        return 0
    except Exception as exc:
        state.update(
            {
                "status": "failed",
                "stage": f"{state.get('stage', 'unknown')}_failed",
                "child_pid": None,
                "error": str(exc),
            }
        )
        publish(
            state,
            state_path,
            monitor_path,
            input_path=input_path,
            readable_output=readable_output,
            report_path=report_path,
            event_output=event_output,
            active_log=active_log,
        )
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run existing clinical-readable and event pipelines with HTML status."
    )
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--python-executable", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--readable-output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--event-output", type=Path, required=True)
    parser.add_argument("--control-directory", type=Path, required=True)
    parser.add_argument("--refresh-seconds", type=int, default=15)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.refresh_seconds < 1:
        parser.error("--refresh-seconds 必须大于 0")
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
