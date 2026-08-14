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
    clinical_metrics: dict[str, Any] = {}
    if report_path.is_file():
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            clinical_metrics = {
                "admissions": report.get("admissions"),
                "decoded_total": report.get("dictionary_decoded_total"),
                "poe_events": report.get("poe_events"),
            }
        except (OSError, json.JSONDecodeError):
            clinical_metrics = {}
    return {
        "input_bytes": _file_size(input_path),
        "readable_partial_bytes": _file_size(partial_output),
        "readable_output_bytes": _file_size(readable_output),
        "report_exists": report_path.is_file(),
        "event_output_exists": event_output.is_dir(),
        "event_detail": event_detail,
        "event_artifacts": event_artifacts,
        "disk_free_bytes": disk.free,
        "clinical_metrics": clinical_metrics,
        "active_log": str(active_log) if active_log else None,
        "log_tail": _tail(active_log) if active_log else "尚未进入执行阶段。",
    }


def _timeline(state: dict[str, Any]) -> list[tuple[str, str, str]]:
    runtime = state.get("runtime", {})
    artifacts = set(runtime.get("event_artifacts") or [])
    published = bool(runtime.get("event_output_exists")) or state.get("status") == "succeeded"
    clinical_done = runtime.get("readable_output_bytes") is not None
    cleaning_done = "cleaning/run_manifest.json" in artifacts
    normalization_done = "normalization/normalization_manifest.json" in artifacts
    replay_done = ".replay/normalization/normalization_manifest.json" in artifacts

    if published:
        current = 5
    elif replay_done:
        current = 3
    elif normalization_done:
        current = 3
    elif cleaning_done:
        current = 2
    elif clinical_done:
        current = 1
    else:
        current = 0

    definitions = (
        ("临床可读归档", "字典解码与 POE 解析"),
        ("Event cleaning", "结构化事件与来源对账"),
        ("审计与归一化", "Cleaning 门禁及确定性归一化"),
        ("复跑与复现比较", "不同批大小重新运行并核对哈希"),
        ("原子发布", "全部门禁通过后发布正式目录"),
    )
    result: list[tuple[str, str, str]] = []
    for index, (label, detail) in enumerate(definitions):
        if published or index < current:
            item_status = "done"
        elif index == current:
            item_status = "failed" if state.get("status") == "failed" else "active"
        else:
            item_status = "pending"
        result.append((label, detail, item_status))
    return result


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
    headline = {
        "clinical_readable": "正在生成临床可读 JSONL",
        "event_pipeline": str(runtime.get("event_detail") or "正在运行 Event 工作流"),
        "completed": "全流程已完成并通过门禁",
    }.get(str(state.get("stage")), str(state.get("stage", "正在准备")))
    if status == "failed":
        headline = "流水线已停止，请查看失败原因"
    action = (
        "无需操作，任务正在后台继续。"
        if status in {"starting", "running"}
        else "所有自动门禁均已通过，正式结果已经发布。"
        if status == "succeeded"
        else "需要检查失败原因；系统不会自动绕过门禁或重试。"
    )
    timeline_html = "".join(
        f'<div class="step {item_status}"><div class="marker">'
        f'{"✓" if item_status == "done" else "!" if item_status == "failed" else index + 1}'
        f'</div><div><strong>{html.escape(label)}</strong>'
        f'<span>{html.escape(detail)}</span></div></div>'
        for index, (label, detail, item_status) in enumerate(_timeline(state))
    )
    clinical_metrics = runtime.get("clinical_metrics") or {}
    admissions = clinical_metrics.get("admissions")
    admissions_text = f"{int(admissions):,}" if admissions is not None else "—"
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
:root {{ color-scheme:light; --ink:#17211e; --muted:#64736e; --paper:#f5f7f6; --card:#fff; --line:#dfe7e3; --green:#087f5b; --blue:#2563eb; --red:#b42318; }}
* {{ box-sizing:border-box; }} body {{ margin:0; background:var(--paper); color:var(--ink); font:15px/1.55 "Segoe UI","Microsoft YaHei",sans-serif; }}
main {{ max-width:1080px; margin:auto; padding:28px 20px 52px; }} h1 {{ margin:0; font-size:25px; }} h2 {{ margin:0 0 14px; font-size:18px; }}
.topline {{ display:flex; justify-content:space-between; gap:16px; align-items:center; margin-bottom:18px; }} .refresh {{ color:var(--muted); font-size:13px; }}
.hero, section, .metric {{ background:var(--card); border:1px solid var(--line); border-radius:16px; box-shadow:0 5px 20px rgba(18,48,39,.05); }}
.hero {{ padding:24px; border-left:6px solid var(--blue); }} .hero.success {{ border-left-color:var(--green); }} .hero.failed {{ border-left-color:var(--red); }}
.hero-row {{ display:flex; flex-wrap:wrap; gap:12px; align-items:center; }} .hero h2 {{ font-size:25px; margin:13px 0 4px; }} .hero p {{ margin:0; color:var(--muted); }}
.status {{ display:inline-block; padding:6px 11px; border-radius:999px; font-weight:750; }} .running {{ color:#1749a5; background:#e7efff; }} .success {{ color:#075b45; background:#d8f5e9; }} .failed {{ color:#8a1c13; background:#fee4e2; }} .starting {{ color:#6b4f00; background:#fff2c7; }}
.action {{ margin-top:17px; padding:12px 14px; background:#f0f5ff; border-radius:10px; font-weight:650; }}
section {{ margin-top:14px; padding:20px; }} .timeline {{ display:grid; grid-template-columns:repeat(5,1fr); gap:0; }}
.step {{ position:relative; display:flex; gap:10px; padding:6px 10px 6px 0; min-width:0; }} .step:not(:last-child)::after {{ content:""; position:absolute; top:21px; left:37px; right:0; height:3px; background:#d9e1de; z-index:0; }}
.marker {{ position:relative; z-index:1; flex:0 0 32px; width:32px; height:32px; display:grid; place-items:center; border-radius:50%; background:#e8edeb; color:#72807b; font-weight:800; }}
.step strong,.step span {{ display:block; }} .step strong {{ margin-top:4px; font-size:14px; }} .step span {{ color:var(--muted); font-size:12px; margin-top:4px; }}
.step.done .marker {{ background:var(--green); color:white; }} .step.done:not(:last-child)::after {{ background:#72c9aa; }} .step.active .marker {{ background:var(--blue); color:white; box-shadow:0 0 0 6px #dfe9ff; animation:pulse 1.8s infinite; }} .step.failed .marker {{ background:var(--red); color:white; }}
@keyframes pulse {{ 50% {{ box-shadow:0 0 0 10px rgba(37,99,235,0); }} }}
.metrics {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-top:14px; }} .metric {{ padding:16px; }} .label {{ color:var(--muted); font-size:12px; }} .value {{ margin-top:5px; font-size:19px; font-weight:720; overflow-wrap:anywhere; }}
.uncertain {{ margin-top:14px; color:#51625c; }} details {{ margin-top:14px; background:var(--card); border:1px solid var(--line); border-radius:14px; padding:15px 18px; }} summary {{ cursor:pointer; font-weight:700; }}
code,pre {{ font-family:"Cascadia Mono",Consolas,monospace; }} pre {{ white-space:pre-wrap; overflow-wrap:anywhere; background:#101c19; color:#d9eee7; border-radius:10px; padding:14px; max-height:340px; overflow:auto; }}
ul {{ padding-left:20px; }} .error {{ border-color:#f4b8b2; }} #stale {{ display:none; margin-top:14px; padding:12px 14px; background:#fff2c7; border-radius:10px; font-weight:650; }}
@media(max-width:760px) {{ .timeline,.metrics {{ grid-template-columns:1fr; }} .step:not(:last-child)::after {{ left:15px; top:38px; bottom:-8px; width:3px; height:auto; right:auto; }} .topline {{ align-items:flex-start; flex-direction:column; }} }}
</style>
</head>
<body data-updated-at="{updated_at}">
<main>
  <div class="topline"><h1>MIMIC 冠脉全队列</h1><div class="refresh">本地页面每 15 秒刷新 · 只展示可核验状态</div></div>
  <div class="hero {status_class}">
    <div class="hero-row"><span class="status {status_class}">{html.escape(status_label)}</span><span class="refresh">最后更新：{updated_at or "—"}</span></div>
    <h2>{html.escape(headline)}</h2>
    <p>当前阶段没有可靠分母时，不显示推测百分比。</p>
    <div class="action">{html.escape(action)}</div>
  </div>
  <div id="stale">状态超过 60 秒未更新。后台编排器可能已经停止，请展开技术详情检查日志。</div>
  <section><h2>处理流程</h2><div class="timeline">{timeline_html}</div><div class="uncertain">正在运行的步骤以蓝色标记；绿色仅表示对应产物已经落盘。</div></section>
  <div class="metrics">
    <div class="metric"><div class="label">已完成住院记录</div><div class="value">{admissions_text}</div></div>
    <div class="metric"><div class="label">临床可读 JSONL</div><div class="value">{_format_bytes(runtime.get("readable_output_bytes"))}</div></div>
    <div class="metric"><div class="label">G 盘剩余空间</div><div class="value">{_format_bytes(runtime.get("disk_free_bytes"))}</div></div>
    <div class="metric"><div class="label">当前运行阶段</div><div class="value">{html.escape(str(state.get("stage", "—")))}</div></div>
  </div>
  <details><summary>技术详情</summary>
    <p><strong>编排器 / 子进程 PID：</strong> {html.escape(str(state.get("runner_pid", "—")))} / {html.escape(str(state.get("child_pid") or "—"))}</p>
    <p><strong>Event 状态：</strong> {html.escape(str(runtime.get("event_detail", "—")))}</p>
    <p><strong>当前日志：</strong> <code>{html.escape(str(runtime.get("active_log") or "—"))}</code></p>
    <h3>已落盘阶段标志</h3><ul>{artifact_html}</ul>
    <h3>日志末尾</h3><pre>{html.escape(str(runtime.get("log_tail", "")))}</pre>
  </details>
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
