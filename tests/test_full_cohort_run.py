from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from data_pipeline.full_cohort_run import (
    FullCohortRunError,
    build_commands,
    collect_runtime,
    render_monitor,
    validate_targets,
)
from data_pipeline.full_cohort_dashboard import enrich_state, render_once


class FullCohortRunTest(unittest.TestCase):
    def test_commands_call_existing_pipeline_entry_points(self) -> None:
        commands = build_commands(
            Path("python.exe"),
            Path("raw.jsonl"),
            Path("readable.jsonl"),
            Path("report.json"),
            Path("event-output"),
        )
        self.assertEqual(commands[0][0], "clinical_readable")
        self.assertEqual(
            commands[0][1][1:3], ["-m", "data_pipeline.clean_clinical_archive"]
        )
        self.assertEqual(commands[1][0], "event_pipeline")
        self.assertEqual(
            commands[1][1][1:4], ["-m", "data_pipeline.event_pipeline", "run"]
        )
        self.assertIn("--raw-source-jsonl", commands[1][1])

    def test_runtime_detects_partial_and_event_stage_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "raw.jsonl"
            readable = root / "readable.jsonl"
            report = root / "report.json"
            event_output = root / "event"
            source.write_bytes(b"1234")
            readable.with_suffix(".jsonl.partial").write_bytes(b"123456")
            temporary = root / ".event.tmp-test"
            artifact = temporary / "cleaning" / "run_manifest.json"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("{}", encoding="utf-8")
            runtime = collect_runtime(
                source, readable, report, event_output, None
            )
            self.assertEqual(runtime["input_bytes"], 4)
            self.assertEqual(runtime["readable_partial_bytes"], 6)
            self.assertEqual(runtime["event_detail"], "正式 cleaning 已完成")
            self.assertEqual(
                runtime["event_artifacts"], ["cleaning/run_manifest.json"]
            )

    def test_html_escapes_log_and_marks_stale_updates(self) -> None:
        rendered = render_monitor(
            {
                "status": "running",
                "stage": "clinical_readable",
                "updated_at": "2026-08-14T12:00:00+08:00",
                "runner_pid": 10,
                "child_pid": 11,
                "runtime": {
                    "log_tail": "<script>alert(1)</script>",
                    "event_detail": "等待",
                    "event_artifacts": [],
                },
            }
        )
        self.assertIn('http-equiv="refresh" content="15"', rendered)
        self.assertNotIn("<script>alert(1)</script>", rendered)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", rendered)
        self.assertIn("状态超过 60 秒未更新", rendered)
        self.assertIn("处理流程", rendered)
        self.assertIn("无需操作，任务正在后台继续", rendered)
        self.assertIn("技术详情", rendered)

    def test_existing_target_is_rejected_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            python_executable = root / "python.exe"
            source = root / "raw.jsonl"
            readable = root / "readable.jsonl"
            python_executable.touch()
            source.touch()
            readable.touch()
            with self.assertRaisesRegex(FullCohortRunError, "拒绝覆盖"):
                validate_targets(
                    root,
                    python_executable,
                    source,
                    readable,
                    root / "report.json",
                    root / "event",
                    root / "control",
                )

    def test_dashboard_enriches_current_state_from_clinical_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "report.json"
            report.write_text(
                '{"admissions":39036,"dictionary_decoded_total":12,"poe_events":34}',
                encoding="utf-8",
            )
            state = {
                "status": "running",
                "stage": "event_pipeline",
                "updated_at": "2026-08-14T15:00:00+08:00",
                "commands": [
                    {
                        "stage": "clinical_readable",
                        "argv": ["python", "--report", str(report)],
                    }
                ],
                "runtime": {
                    "readable_output_bytes": 100,
                    "event_detail": "正在生成正式 cleaning",
                },
            }
            enriched = enrich_state(state)
            self.assertEqual(
                enriched["runtime"]["clinical_metrics"]["admissions"], 39036
            )
            state_path = root / "run-state.json"
            output_path = root / "dashboard.html"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            self.assertEqual(render_once(state_path, output_path), "running")
            self.assertIn("39,036", output_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
