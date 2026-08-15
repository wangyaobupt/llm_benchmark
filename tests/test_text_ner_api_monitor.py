from __future__ import annotations

import json
from pathlib import Path
import tempfile
import time
import unittest

from data_pipeline.text_ner.api_monitor import (
    ApiMonitorError,
    ApiMonitorSession,
    monitor_api_html,
    render_monitor_html,
)


def _append_jsonl(path: Path, *records: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


class ApiMonitorTests(unittest.TestCase):
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
