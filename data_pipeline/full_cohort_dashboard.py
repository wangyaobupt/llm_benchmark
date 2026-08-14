"""Continuously render a clearer dashboard from an existing run-state file."""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
import time
from typing import Any, Sequence

from .full_cohort_run import _atomic_write_text, render_monitor


def _argument_value(
    state: dict[str, Any], stage: str, flag: str
) -> str | None:
    for command in state.get("commands", []):
        if command.get("stage") != stage:
            continue
        argv = command.get("argv") or []
        if flag in argv:
            index = argv.index(flag)
            if index + 1 < len(argv):
                return str(argv[index + 1])
    return None


def enrich_state(state: dict[str, Any]) -> dict[str, Any]:
    enriched = deepcopy(state)
    runtime = enriched.setdefault("runtime", {})
    if runtime.get("clinical_metrics"):
        return enriched
    report_value = _argument_value(enriched, "clinical_readable", "--report")
    if not report_value:
        return enriched
    report_path = Path(report_value)
    if not report_path.is_file():
        return enriched
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return enriched
    runtime["clinical_metrics"] = {
        "admissions": report.get("admissions"),
        "decoded_total": report.get("dictionary_decoded_total"),
        "poe_events": report.get("poe_events"),
    }
    return enriched


def render_once(state_path: Path, output_path: Path) -> str:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    enriched = enrich_state(state)
    _atomic_write_text(output_path, render_monitor(enriched))
    return str(enriched.get("status", "unknown"))


def follow(state_path: Path, output_path: Path, interval_seconds: int) -> int:
    while True:
        status = render_once(state_path, output_path)
        if status in {"succeeded", "failed"}:
            return 0
        time.sleep(interval_seconds)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render a readable HTML dashboard from a full-cohort state file."
    )
    parser.add_argument("state", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--interval-seconds", type=int, default=15)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.interval_seconds < 1:
        parser.error("--interval-seconds 必须大于 0")
    if not args.state.is_file():
        parser.error(f"状态文件不存在：{args.state}")
    return follow(args.state.resolve(), args.output.resolve(), args.interval_seconds)


if __name__ == "__main__":
    sys.exit(main())
