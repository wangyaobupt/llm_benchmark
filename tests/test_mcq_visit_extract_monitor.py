from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from data_pipeline.mcq_visit_extract.catalog import DICTIONARY_KEYS, FACT_SOURCES
from data_pipeline.mcq_visit_extract.monitor import (
    HTML,
    StatusCache,
    _directory_stats,
    collect_status,
)
from data_pipeline.mcq_visit_extract.progress import write_progress


class VisitExtractMonitorTest(unittest.TestCase):
    def test_status_cache_coalesces_repeated_reads(self) -> None:
        calls: list[int] = []
        cache = StatusCache(lambda: calls.append(1) or {"status": "running"}, ttl_seconds=60)
        self.assertEqual(cache.get()["status"], "running")
        self.assertEqual(cache.get()["status"], "running")
        self.assertEqual(len(calls), 1)

    def test_reports_completed_run_without_reading_visit_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "run"
            root.mkdir()
            secret = "SECRET_CHIEF_COMPLAINT_SHOULD_NOT_LEAK"
            (root / "visits.csv").write_text(f"chief_complaint\n{secret}\n", encoding="utf-8")
            (root / "visits.json").write_text(
                json.dumps([{"chief_complaint": secret}]),
                encoding="utf-8",
            )
            (root / "funnel.json").write_text(
                json.dumps({"candidate_count": 10, "eligible_count": 3}),
                encoding="utf-8",
            )
            manifest = {
                "identity": {"sample_size": 2, "shard_size": 1, "sample_pool": "development"},
                "funnel": {
                    "n1": {"status": "complete"},
                    "n2": {"status": "complete"},
                    "eligible": {"status": "complete"},
                },
                "selection": {"status": "complete"},
                "staging": {source.key: {"status": "complete"} for source in FACT_SOURCES},
                "reference_tables": {key: {"status": "complete"} for key in DICTIONARY_KEYS},
                "shards": {
                    "0": {"status": "complete", "records": 1},
                    "1": {"status": "complete", "records": 1},
                },
                "working": {"status": "complete"},
                "deliverables": {"status": "complete", "records": 2},
            }
            (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            write_progress(root, phase="complete", detail="2 visits")

            with patch(
                "data_pipeline.mcq_visit_extract.monitor._memory_status",
                return_value=(32, 8),
            ):
                status = collect_status(root)

            encoded = json.dumps(status)
            self.assertNotIn(secret, encoded)
            self.assertEqual(status["status"], "complete")
            self.assertEqual(status["staging_complete"], len(FACT_SOURCES))
            self.assertEqual(status["shards_complete"], 2)
            self.assertEqual(status["records"], 2)
            self.assertTrue(status["deliverables_complete"])
            self.assertEqual(status["funnel_counts"]["eligible_count"], 3)

    def test_recent_activity_marks_running_and_current_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "run"
            root.mkdir()
            (root / "manifest.json").write_text(
                json.dumps(
                    {
                        "identity": {"sample_size": 10, "shard_size": 10},
                        "funnel": {"n1": {"status": "complete"}, "n2": {"status": "complete"}},
                        "staging": {"admissions": {"status": "complete"}},
                    }
                ),
                encoding="utf-8",
            )
            write_progress(root, phase="staging", detail="labevents")
            (root / "staging").mkdir()
            (root / "staging" / "labevents.parquet.partial").write_bytes(b"active")

            with patch(
                "data_pipeline.mcq_visit_extract.monitor._memory_status",
                return_value=(32, 8),
            ):
                status = collect_status(root)

            self.assertEqual(status["status"], "running")
            self.assertEqual(status["phase"], "staging")
            self.assertEqual(status["detail"], "labevents")
            lab = next(row for row in status["tables"] if row["key"] == "labevents")
            self.assertEqual(lab["status"], "running")

    def test_stale_manifest_without_activity_is_stopped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "run"
            root.mkdir()
            manifest_path = root / "manifest.json"
            manifest_path.write_text(
                json.dumps({"identity": {"sample_size": 1, "shard_size": 1}}),
                encoding="utf-8",
            )
            old = time.time() - 400
            os.utime(manifest_path, (old, old))
            with patch(
                "data_pipeline.mcq_visit_extract.monitor._memory_status",
                return_value=(32, 8),
            ):
                status = collect_status(root)
            self.assertEqual(status["status"], "stopped")

    def test_directory_stats_ignores_vanishing_partial_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "keep.txt").write_text("ok", encoding="utf-8")
            ghost = root / "part-00054.jsonl.partial"
            ghost.write_text("tmp", encoding="utf-8")
            real_stat = Path.stat

            def flaky_stat(self: Path, *args: object, **kwargs: object):
                if self.name.endswith(".partial"):
                    raise FileNotFoundError(2, "not found", str(self))
                return real_stat(self, *args, **kwargs)

            with patch.object(Path, "stat", flaky_stat):
                total, _modified = _directory_stats(root)
            self.assertGreaterEqual(total, 2)

    def test_status_cache_keeps_last_value_when_collector_raises(self) -> None:
        calls = {"n": 0}

        def collector() -> dict[str, str]:
            calls["n"] += 1
            if calls["n"] == 1:
                return {"status": "running"}
            raise FileNotFoundError("part-00054.jsonl.partial")

        cache = StatusCache(collector, ttl_seconds=60)
        self.assertEqual(cache.get()["status"], "running")
        cache._refresh_locked()
        self.assertEqual(cache.get()["status"], "running")

    def test_html_contains_progress_hooks(self) -> None:
        for marker in (
            "出题 Visit 抽取",
            "/api/status",
            "id=\"runStatus\"",
            "id=\"funnel\"",
            "id=\"staging\"",
            "id=\"shards\"",
            "setInterval(refresh,2000)",
        ):
            self.assertIn(marker, HTML)


if __name__ == "__main__":
    unittest.main()
