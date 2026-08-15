from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
import tempfile
import time
import unittest

from data_pipeline.text_ner.api_monitor import (
    ApiMonitorError,
    ApiMonitorSession,
    default_monitor_html_path,
    monitor_api_html,
    render_monitor_html,
)
from data_pipeline.text_ner.__main__ import _parser


def _append_jsonl(path: Path, *records: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


class ApiMonitorTests(unittest.TestCase):
    def test_parquet_command_explains_missing_pyarrow(self) -> None:
        program = """
import builtins
import runpy
import sys

real_import = builtins.__import__

def reject_pyarrow(name, globals=None, locals=None, fromlist=(), level=0):
    if name == "pyarrow" or name.startswith("pyarrow."):
        raise ModuleNotFoundError("No module named 'pyarrow'", name="pyarrow")
    return real_import(name, globals, locals, fromlist, level)

builtins.__import__ = reject_pyarrow
sys.argv = [
    "data_pipeline.text_ner",
    "prepare-aggregation-manifest",
    "aggregation",
    "sources.json",
    "--output-dir",
    "output",
]
runpy.run_module("data_pipeline.text_ner", run_name="__main__")
"""
        completed = subprocess.run(
            [sys.executable, "-c", program],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("TEXT_NER_DEPENDENCY_MISSING", completed.stderr)
        self.assertIn(".venv", completed.stderr)
        self.assertNotIn("Traceback", completed.stderr)

    def test_monitor_cli_does_not_import_pyarrow(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "monitor.html"
            program = f"""
import builtins
import runpy
import sys

real_import = builtins.__import__

def reject_pyarrow(name, globals=None, locals=None, fromlist=(), level=0):
    if name == "pyarrow" or name.startswith("pyarrow."):
        raise AssertionError("monitor command imported pyarrow")
    return real_import(name, globals, locals, fromlist, level)

builtins.__import__ = reject_pyarrow
sys.argv = [
    "data_pipeline.text_ner",
    "monitor-openai-compatible-api",
    "missing-responses.jsonl",
    "missing-audit.jsonl",
    "--output-html",
    {str(output)!r},
    "--expected-requests",
    "1",
]
runpy.run_module("data_pipeline.text_ner", run_name="__main__")
"""
            completed = subprocess.run(
                [sys.executable, "-c", program],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(output.is_file())

    def test_cli_accepts_interval_alias_and_derives_html_path(self) -> None:
        arguments = _parser().parse_args(
            [
                "monitor-openai-compatible-api",
                "mention_responses.jsonl",
                "mention_api_audit.jsonl",
                "--expected-requests",
                "64509",
                "--watch",
                "--interval-seconds",
                "10",
            ]
        )
        self.assertEqual(arguments.refresh_seconds, 10)
        self.assertIsNone(arguments.output_html)
        self.assertEqual(
            default_monitor_html_path(Path(arguments.audit)),
            Path("mention_monitor.html"),
        )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            audit = root / "mention_api_audit.jsonl"
            summary = monitor_api_html(
                root / "mention_responses.jsonl",
                audit,
                expected_requests=64509,
                stage_label="Mention 实体识别",
            )
            expected_output = root / "mention_monitor.html"
            self.assertEqual(summary["output_html_path"], str(expected_output))
            self.assertTrue(expected_output.is_file())

    def test_incremental_progress_rate_consistency_and_payload_redaction(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            responses = root / "responses.jsonl"
            audit = root / "audit.jsonl"
            _append_jsonl(
                responses,
                {"request_id": "request:1", "clinical_text": "private chest pain"},
                {"request_id": "request:2", "clinical_text": "private fever"},
            )
            _append_jsonl(
                audit,
                {
                    "request_id": "request:1",
                    "provider": "test-provider",
                    "model_name": "test-model",
                    "model_version": "test-revision",
                    "usage": {
                        "prompt_tokens": 10,
                        "completion_tokens": 4,
                        "total_tokens": 14,
                    },
                },
            )
            session = ApiMonitorSession(
                responses,
                audit,
                expected_requests=3,
                stage_label="Mention <stage>",
                refresh_seconds=10,
            )
            first = session.sample(now_epoch=time.time(), now_monotonic=100.0)
            self.assertEqual(first["completed_requests"], 1)
            self.assertEqual(first["response_only_request_ids"], 1)
            self.assertEqual(first["status_code"], "mismatch")

            _append_jsonl(
                audit,
                {
                    "request_id": "request:2",
                    "provider": "test-provider",
                    "model_name": "test-model",
                    "model_version": "test-revision",
                    "usage": {
                        "prompt_tokens": 12,
                        "completion_tokens": 5,
                        "total_tokens": 17,
                    },
                },
            )
            second = session.sample(now_epoch=time.time(), now_monotonic=110.0)
            self.assertEqual(second["completed_requests"], 2)
            self.assertEqual(second["status_code"], "running")
            self.assertAlmostEqual(second["requests_per_minute"], 6.0)
            self.assertEqual(second["usage"]["total_tokens"], 31)

            page = render_monitor_html(second)
            self.assertIn('<meta http-equiv="refresh" content="10">', page)
            self.assertIn("66.67%", page)
            self.assertIn("Mention &lt;stage&gt;", page)
            self.assertNotIn("private chest pain", page)
            self.assertNotIn("private fever", page)
            self.assertNotIn("request:1", page)
            self.assertNotIn("request:2", page)

    def test_watch_writes_html_atomically_and_stops_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "monitor" / "progress.html"

            def interrupt(_: float) -> None:
                raise KeyboardInterrupt

            summary = monitor_api_html(
                root / "missing-responses.jsonl",
                root / "missing-audit.jsonl",
                output,
                expected_requests=64509,
                stage_label="Mention 实体识别",
                refresh_seconds=10,
                watch=True,
                sleep=interrupt,
            )
            self.assertTrue(summary["watch_stopped_by_user"])
            self.assertEqual(summary["status_code"], "waiting")
            self.assertTrue(output.is_file())
            self.assertIn("等待任务启动", output.read_text(encoding="utf-8"))
            self.assertEqual(list(output.parent.glob("*.temporary")), [])

    def test_invalid_jsonl_duplicate_ids_and_invalid_options_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            responses = root / "responses.jsonl"
            audit = root / "audit.jsonl"
            responses.write_text(
                '{"request_id":"request:1"}\n'
                '{"request_id":"request:1"}\n'
                "not-json\n",
                encoding="utf-8",
            )
            _append_jsonl(audit, {"request_id": "request:1", "usage": {}})
            snapshot = ApiMonitorSession(
                responses,
                audit,
                expected_requests=2,
                stage_label="Relation",
            ).sample()
            self.assertEqual(snapshot["status_code"], "invalid")
            self.assertEqual(snapshot["invalid_jsonl_rows"], 1)
            self.assertEqual(snapshot["duplicate_request_ids"], 1)
            with self.assertRaisesRegex(
                ApiMonitorError, "API_MONITOR_EXPECTED_REQUESTS_INVALID"
            ):
                ApiMonitorSession(
                    responses,
                    audit,
                    expected_requests=0,
                    stage_label="Relation",
                )


if __name__ == "__main__":
    unittest.main()
