"""Resume a verified full-cohort Event workflow and update its HTML dashboard."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Sequence

from .full_cohort_run import (
    FullCohortRunError,
    _atomic_write_text,
    _now,
    publish,
    render_monitor,
)


def build_resume_command(
    python_executable: Path,
    staging_directory: Path,
    readable_output: Path,
    raw_input: Path,
    event_output: Path,
    work_directory: Path,
    *,
    batch_size: int,
    replay_batch_size: int,
) -> list[str]:
    return [
        str(python_executable),
        "-m",
        "data_pipeline.event_pipeline",
        "resume",
        str(staging_directory),
        str(readable_output),
        "--raw-source-jsonl",
        str(raw_input),
        "--output-dir",
        str(event_output),
        "--batch-size",
        str(batch_size),
        "--replay-batch-size",
        str(replay_batch_size),
        "--work-dir",
        str(work_directory),
    ]


def _publish_dashboard(
    state: dict[str, Any],
    state_path: Path,
    monitor_path: Path,
    dashboard_path: Path,
    *,
    raw_input: Path,
    readable_output: Path,
    report_path: Path,
    event_output: Path,
    active_log: Path,
) -> None:
    publish(
        state,
        state_path,
        monitor_path,
        input_path=raw_input,
        readable_output=readable_output,
        report_path=report_path,
        event_output=event_output,
        active_log=active_log,
    )
    _atomic_write_text(dashboard_path, render_monitor(state))


def run(args: argparse.Namespace) -> int:
    project_root = args.project_root.resolve()
    python_executable = args.python_executable.resolve()
    raw_input = args.input.resolve()
    readable_output = args.readable_output.resolve()
    report_path = args.report.resolve()
    staging_directory = args.staging_directory.resolve()
    event_output = args.event_output.resolve()
    work_directory = args.work_directory.resolve()
    control_directory = args.control_directory.resolve()
    state_path = control_directory / "run-state.json"
    monitor_path = control_directory / "monitor.html"
    dashboard_path = control_directory / "dashboard.html"
    active_log = control_directory / "event_pipeline-recovery.log"

    required_files = (python_executable, raw_input, readable_output, state_path)
    missing = [str(path) for path in required_files if not path.is_file()]
    if missing:
        raise FullCohortRunError("恢复所需文件不存在：" + "; ".join(missing))
    if not project_root.is_dir() or not staging_directory.is_dir():
        raise FullCohortRunError("项目目录或恢复临时目录不存在")
    if event_output.exists():
        raise FullCohortRunError(f"正式 Event 输出已存在：{event_output}")
    if active_log.exists():
        raise FullCohortRunError(f"恢复日志已存在，拒绝覆盖：{active_log}")
    if args.batch_size < 1 or args.replay_batch_size < 1:
        raise FullCohortRunError("batch size 必须大于 0")
    work_directory.mkdir(parents=True, exist_ok=True)

    state = json.loads(state_path.read_text(encoding="utf-8"))
    previous_failure = {
        "status": state.get("status"),
        "stage": state.get("stage"),
        "error": state.get("error"),
        "updated_at": state.get("updated_at"),
    }
    command = build_resume_command(
        python_executable,
        staging_directory,
        readable_output,
        raw_input,
        event_output,
        work_directory,
        batch_size=args.batch_size,
        replay_batch_size=args.replay_batch_size,
    )
    state.setdefault("attempts", []).append(previous_failure)
    state.update(
        {
            "status": "running",
            "stage": "event_pipeline",
            "recovery_started_at": _now(),
            "runner_pid": os.getpid(),
            "child_pid": None,
            "error": None,
        }
    )
    state.setdefault("commands", []).append(
        {"stage": "event_pipeline_resume", "argv": command, "started_at": _now()}
    )
    _publish_dashboard(
        state,
        state_path,
        monitor_path,
        dashboard_path,
        raw_input=raw_input,
        readable_output=readable_output,
        report_path=report_path,
        event_output=event_output,
        active_log=active_log,
    )

    try:
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
                _publish_dashboard(
                    state,
                    state_path,
                    monitor_path,
                    dashboard_path,
                    raw_input=raw_input,
                    readable_output=readable_output,
                    report_path=report_path,
                    event_output=event_output,
                    active_log=active_log,
                )
                time.sleep(args.refresh_seconds)
            exit_code = int(process.returncode)
        state["commands"][-1]["exit_code"] = exit_code
        state["commands"][-1]["finished_at"] = _now()
        state["child_pid"] = None
        if exit_code != 0:
            raise FullCohortRunError(
                f"阶段 event_pipeline_resume 失败，退出码 {exit_code}；详见 {active_log}"
            )
        state.update({"status": "succeeded", "stage": "completed"})
        _publish_dashboard(
            state,
            state_path,
            monitor_path,
            dashboard_path,
            raw_input=raw_input,
            readable_output=readable_output,
            report_path=report_path,
            event_output=event_output,
            active_log=active_log,
        )
        return 0
    except Exception as error:
        state.update(
            {
                "status": "failed",
                "stage": "event_pipeline_resume_failed",
                "child_pid": None,
                "error": str(error),
            }
        )
        _publish_dashboard(
            state,
            state_path,
            monitor_path,
            dashboard_path,
            raw_input=raw_input,
            readable_output=readable_output,
            report_path=report_path,
            event_output=event_output,
            active_log=active_log,
        )
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--python-executable", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--readable-output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--staging-directory", type=Path, required=True)
    parser.add_argument("--event-output", type=Path, required=True)
    parser.add_argument("--work-directory", type=Path, required=True)
    parser.add_argument("--control-directory", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=5000)
    parser.add_argument("--replay-batch-size", type=int, default=777)
    parser.add_argument("--refresh-seconds", type=int, default=15)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.refresh_seconds < 1:
        raise FullCohortRunError("--refresh-seconds 必须大于 0")
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
