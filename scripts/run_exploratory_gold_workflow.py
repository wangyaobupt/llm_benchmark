"""Run E1-E4 exploratory Gold audits for a supplied normalization source.

This orchestrator is deliberately exploratory-only. It updates the progress
dashboard and writes a run manifest, but never runs official final-test and
never performs Git operations.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def build_stage_specs(source_root: Path, output_dir: Path) -> list[dict[str, Any]]:
    return [
        {"stage": "E1", "script": "scripts/exploratory_source_audit.py", "json": output_dir / "e1-source-audit.json", "markdown": output_dir / "e1-source-audit.md", "args": ["--source-root", str(source_root), "--json-output", str(output_dir / "e1-source-audit.json"), "--markdown-output", str(output_dir / "e1-source-audit.md")]},
        {"stage": "E2", "script": "scripts/exploratory_gold_definition_audit.py", "json": output_dir / "e2-gold-definition-audit.json", "markdown": output_dir / "e2-gold-definition-audit.md", "args": ["--source-root", str(source_root), "--json-output", str(output_dir / "e2-gold-definition-audit.json"), "--markdown-output", str(output_dir / "e2-gold-definition-audit.md")]},
        {"stage": "E3", "script": "scripts/exploratory_gold_coverage_audit.py", "json": output_dir / "e3-gold-coverage-audit.json", "markdown": output_dir / "e3-gold-coverage-audit.md", "args": ["--source-root", str(source_root), "--json-output", str(output_dir / "e3-gold-coverage-audit.json"), "--markdown-output", str(output_dir / "e3-gold-coverage-audit.md")]},
        {"stage": "E4", "script": "scripts/exploratory_method_feasibility_audit.py", "json": output_dir / "e4-method-feasibility-audit.json", "markdown": output_dir / "e4-method-feasibility-audit.md", "args": ["--e2", str(output_dir / "e2-gold-definition-audit.json"), "--e3", str(output_dir / "e3-gold-coverage-audit.json"), "--json-output", str(output_dir / "e4-method-feasibility-audit.json"), "--markdown-output", str(output_dir / "e4-method-feasibility-audit.md")]},
    ]


def write_manifest(path: Path, manifest: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temp, path)


def update_dashboard(stage: str, status: str, message: str) -> None:
    subprocess.run([sys.executable, "scripts/benchmark_progress.py", "update", stage, status, message], cwd=ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    source_root = args.source_root.resolve()
    output_dir = args.output_dir.resolve()
    if not source_root.is_dir():
        raise SystemExit(f"source root not found: {source_root}")
    specs = build_stage_specs(source_root, output_dir)
    manifest_path = output_dir / "exploratory-run-manifest.json"
    manifest: dict[str, Any] = {"schema": "exploratory-gold-workflow-run/1.0.0", "started_at": now(), "source_root": source_root.as_posix(), "output_dir": output_dir.as_posix(), "official_final_test": False, "git_operations": False, "status": "running", "stages": []}
    write_manifest(manifest_path, manifest)
    try:
        for spec in specs:
            update_dashboard(spec["stage"], "running", f"探索性工作流运行中：{spec['stage']}，official final-test=false")
            command = [sys.executable, spec["script"], *spec["args"]]
            subprocess.run(command, cwd=ROOT, check=True)
            manifest["stages"].append({"stage": spec["stage"], "status": "completed", "script": spec["script"], "json": str(spec["json"]), "markdown": str(spec["markdown"])})
            write_manifest(manifest_path, manifest)
            update_dashboard(spec["stage"], "completed", f"探索性 {spec['stage']} 完成；official final-test=false")
        manifest["status"] = "completed"
        manifest["finished_at"] = now()
        write_manifest(manifest_path, manifest)
        return 0
    except subprocess.CalledProcessError as error:
        manifest["status"] = "failed"
        manifest["failed_at"] = now()
        manifest["failure_returncode"] = error.returncode
        write_manifest(manifest_path, manifest)
        current = specs[len(manifest["stages"])] ["stage"] if len(manifest["stages"]) < len(specs) else "E4"
        update_dashboard(current, "failed", f"探索性工作流失败；保留已完成产物，official final-test=false")
        return error.returncode or 1


if __name__ == "__main__":
    raise SystemExit(main())
