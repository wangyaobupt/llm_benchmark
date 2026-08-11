from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from data_pipeline.mimic_raw_archive.catalog import (
    ARCHIVE_SOURCES,
    REFERENCE_SOURCE_KEYS,
)
from data_pipeline.mimic_raw_archive.monitor import StatusCache, collect_status


class RawArchiveMonitorTest(unittest.TestCase):
    def test_status_cache_coalesces_repeated_dashboard_reads(self) -> None:
        calls = []
        cache = StatusCache(
            lambda: calls.append(1) or {"status": "running"},
            ttl_seconds=60,
        )
        self.assertEqual(cache.get()["status"], "running")
        self.assertEqual(cache.get()["status"], "running")
        self.assertEqual(len(calls), 1)

    def test_partial_file_activity_prevents_false_stopped_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "run"
            root.mkdir()
            merged = Path(tmp) / "raw.jsonl"
            (root / "selection.jsonl").write_text("{}\n", encoding="utf-8")
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps({
                "identity": {"sample_size": 1, "shard_size": 1},
                "staging": {},
                "reference_tables": {},
                "shards": {},
                "merged": None,
            }), encoding="utf-8")
            old = time.time() - 400
            os.utime(manifest_path, (old, old))
            partial = root / "staging" / "labevents.partial"
            partial.mkdir(parents=True)
            (partial / "data.parquet").write_bytes(b"active")

            with patch(
                "data_pipeline.mimic_raw_archive.monitor._memory_status",
                return_value=(32, 8),
            ):
                status = collect_status(root, merged)

            self.assertEqual(status["status"], "running")

    def test_reports_completed_run_without_reading_jsonl_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "run"
            root.mkdir()
            merged = Path(tmp) / "raw.jsonl"
            merged.write_bytes(b"{}\n")
            (root / "selection.jsonl").write_text(
                '{"subject_id":"1","hadm_id":"10"}\n', encoding="utf-8"
            )
            manifest = {
                "identity": {"sample_size": 1, "shard_size": 1},
                "staging": {source.key: {"status": "complete"} for source in ARCHIVE_SOURCES},
                "reference_tables": {key: {"status": "complete"} for key in REFERENCE_SOURCE_KEYS},
                "shards": {"0": {"status": "complete", "records": 1}},
                "merged": {"status": "complete", "records": 1},
            }
            (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            eda = Path(tmp) / "eda.json"
            eda.write_text(json.dumps({
                "subjects": 1,
                "cad": {"admissions": 1},
                "line_bytes": {"mean": 3.0},
                "schema": {"invalid_records": 0},
                "orphan_child_rows": {"poe_detail": 0},
            }), encoding="utf-8")

            with patch(
                "data_pipeline.mimic_raw_archive.monitor._memory_status",
                return_value=(32, 8),
            ):
                status = collect_status(root, merged, eda)

            self.assertEqual(status["status"], "complete")
            self.assertEqual(status["staging_complete"], 32)
            self.assertEqual(status["reference_complete"], 7)
            self.assertEqual(status["shards_complete"], 1)
            self.assertEqual(status["records"], 1)
            self.assertEqual(status["merged_bytes"], 3)
            self.assertEqual(status["eda"]["cad_admissions"], 1)


if __name__ == "__main__":
    unittest.main()
