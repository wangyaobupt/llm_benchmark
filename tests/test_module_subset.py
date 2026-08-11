from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from data_pipeline.mimic_raw_archive.module_subset import (
    ModuleSubsetError,
    classify_record,
    extract_subset,
    render_monitor_html,
)


def make_record(*, ed: bool = False, note: bool = False, icu: bool = False) -> dict:
    return {
        "schema": {"name": "mimic_admission_raw", "version": "1.0.0"},
        "subject_id": "1",
        "hadm_id": "10",
        "mimic_iv_hosp": {"admissions": [{"hadm_id": "10"}]},
        "mimic_iv_icu": {"inputevents": [{"amount": "1"}] if icu else []},
        "mimic_iv_ed": {"edstays": [{"stay_id": "100"}] if ed else []},
        "mimic_iv_note": {"discharge": [{"text": "note"}] if note else []},
    }


class ModuleSubsetTest(unittest.TestCase):
    def test_icu_is_audited_but_not_required(self) -> None:
        no_icu = classify_record(make_record(ed=True, note=True, icu=False))
        with_icu = classify_record(make_record(ed=True, note=True, icu=True))
        self.assertTrue(all(no_icu[name] for name in (
            "mimic_iv_hosp", "mimic_iv_ed", "mimic_iv_note"
        )))
        self.assertFalse(no_icu["mimic_iv_icu"])
        self.assertTrue(with_icu["mimic_iv_icu"])

    def test_rejects_non_array_module_tables(self) -> None:
        record = make_record(ed=True, note=True)
        record["mimic_iv_ed"]["triage"] = {"not": "an array"}
        with self.assertRaisesRegex(ModuleSubsetError, "must be an array"):
            classify_record(record)

    def test_streams_only_all_three_records_and_preserves_source_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source.jsonl"
            output = root / "subset.jsonl"
            summary = root / "summary.json"
            monitor = root / "monitor.html"
            status = root / "status.json"
            records = [
                make_record(),
                make_record(ed=True),
                make_record(note=True),
                make_record(ed=True, note=True),
                make_record(ed=True, note=True, icu=True),
            ]
            lines = [
                json.dumps(record, ensure_ascii=False, separators=(",", ":")).encode()
                + b"\n"
                for record in records
            ]
            source.write_bytes(b"".join(lines))

            result = extract_subset(
                source, output, summary, monitor, status, refresh_seconds=0
            )

            self.assertEqual(output.read_bytes(), lines[3] + lines[4])
            self.assertEqual(result["records_processed"], 5)
            self.assertEqual(result["matched_records"], 2)
            self.assertEqual(result["module_counts"]["mimic_iv_hosp"], 5)
            self.assertEqual(result["module_counts"]["mimic_iv_ed"], 3)
            self.assertEqual(result["module_counts"]["mimic_iv_note"], 3)
            self.assertEqual(result["module_counts"]["mimic_iv_icu"], 1)
            self.assertEqual(result["intersection_counts"]["all_three"], 2)
            self.assertEqual(json.loads(summary.read_text())["status"], "complete")
            self.assertNotIn('http-equiv="refresh"', monitor.read_text(encoding="utf-8"))

    def test_running_dashboard_auto_refreshes(self) -> None:
        status = {
            "status": "running",
            "status_label": "正在处理",
            "updated_at": "now",
            "input_path": "source.jsonl",
            "records_processed": 0,
            "matched_records": 0,
            "invalid_records": 0,
            "input_bytes_total": 100,
            "input_bytes_read": 0,
            "output_bytes_written": 0,
            "progress_percent": 0,
            "elapsed_seconds": 0,
            "bytes_per_second": 0,
            "eta_seconds": None,
            "module_counts": {},
            "intersection_counts": {},
            "nonempty_table_record_counts": {},
            "error": None,
        }
        self.assertIn('http-equiv="refresh"', render_monitor_html(status))


if __name__ == "__main__":
    unittest.main()
