from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from data_pipeline.mcq_visit_extract.backfill_times import (
    BackfillError,
    attach_times,
    overlay_times,
    procedure_key,
    run,
)
from data_pipeline.mcq_visit_extract.extract import _procedures
from data_pipeline.mcq_visit_extract.extract import _medications, medication_core


def _row(**overrides: object) -> dict:
    payload = {
        "drug_type": "MAIN",
        "drug": "Aspirin",
        "prod_strength": "81mg",
        "form_rx": "TAB",
        "dose_val_rx": "81",
        "dose_unit_rx": "mg",
        "route": "PO",
        "doses_per_24_hrs": "1",
        "starttime": "2150-01-02 08:00:00",
        "stoptime": "2150-01-04 08:00:00",
    }
    payload.update(overrides)
    return payload


class MedicationTimeTests(unittest.TestCase):
    def test_keeps_start_and_stop_and_sorts(self) -> None:
        items = _medications(
            [
                _row(drug="Later", starttime="2150-01-03 00:00:00"),
                _row(drug="Earlier", starttime="2150-01-01 00:00:00", stoptime=None),
                _row(drug_type="BASE", drug="Ignored"),
            ]
        )
        self.assertEqual([item["drug"] for item in items], ["Earlier", "Later"])
        self.assertEqual(items[0]["starttime"], "2150-01-01 00:00:00")
        self.assertIsNone(items[0]["stoptime"])
        self.assertEqual(items[1]["stoptime"], "2150-01-04 08:00:00")
        self.assertEqual(
            list(items[0]),
            [
                "drug",
                "prod_strength",
                "form_rx",
                "dose_val_rx",
                "dose_unit_rx",
                "route",
                "doses_per_24_hrs",
                "starttime",
                "stoptime",
            ],
        )

    def test_attach_times_matches_frozen_core(self) -> None:
        published = [medication_core(_medications([_row()])[0])]
        timed = attach_times(published, [_row()])
        self.assertEqual(timed[0]["starttime"], "2150-01-02 08:00:00")
        self.assertEqual(medication_core(timed[0]), published[0])

    def test_attach_times_accepts_permuted_order(self) -> None:
        later = _row(drug="Later", starttime="2150-01-03 00:00:00")
        earlier = _row(drug="Earlier", starttime="2150-01-01 00:00:00")
        published = [
            medication_core(_medications([later])[0]),
            medication_core(_medications([earlier])[0]),
        ]
        timed = attach_times(published, [later, earlier])
        self.assertEqual([item["drug"] for item in timed], ["Earlier", "Later"])
        self.assertEqual(timed[0]["starttime"], "2150-01-01 00:00:00")

    def test_attach_times_fails_on_mismatch(self) -> None:
        with self.assertRaisesRegex(BackfillError, "core mismatch"):
            attach_times([{"drug": "Other", "route": "IV"}], [_row()])

    def test_procedure_chartdate_overlay(self) -> None:
        dictionary = {("9604", "9"): "Insertion of endotracheal tube"}
        published = [
            {
                "procedure_name": "Insertion of endotracheal tube",
                "icd_code": "9604",
                "icd_version": 9,
            }
        ]
        rebuilt = _procedures(
            [
                {
                    "icd_code": "9604",
                    "icd_version": "9",
                    "chartdate": "2150-01-02",
                    "seq_num": "1",
                }
            ],
            dictionary,
        )
        timed = overlay_times(
            published,
            rebuilt,
            procedure_key,
            ("chartdate",),
            label="procedure",
        )
        self.assertEqual(timed[0]["chartdate"], "2150-01-02")
        self.assertEqual(timed[0]["procedure_name"], published[0]["procedure_name"])


class BackfillPipelineTests(unittest.TestCase):
    def test_writes_new_dir_and_refuses_extract_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            extract_dir = Path(raw) / "extract"
            output_dir = Path(raw) / "medtimes"
            extract_dir.mkdir()
            visits = [
                {
                    "subject_id": "1",
                    "hadm_id": "10",
                    "medications": [medication_core(_medications([_row()])[0])],
                    "discharge_note_full": "Chief Complaint:\nChest pain\n",
                }
            ]
            visits_path = extract_dir / "visits.json"
            visits_path.write_text(
                "[\n"
                + json.dumps(visits[0], ensure_ascii=False, separators=(",", ":"))
                + "\n]\n",
                encoding="utf-8",
            )
            staging = extract_dir / "staging"
            staging.mkdir()
            table = pa.Table.from_pylist(
                [_row(subject_id="1", hadm_id="10", pharmacy_id="p1")]
            )
            pq.write_table(table, staging / "prescriptions.parquet")

            with self.assertRaisesRegex(BackfillError, "refusing to write"):
                run(
                    extract_dir=extract_dir,
                    output_dir=extract_dir,
                    expected_count=1,
                )

            summary = run(
                extract_dir=extract_dir,
                output_dir=output_dir,
                expected_count=1,
            )
            self.assertEqual(summary["visits"], 1)
            self.assertEqual(summary["medication_rows"], 1)
            self.assertEqual(summary["medication_starttime_rate"], 1.0)
            self.assertTrue(summary["does_not_overwrite_extract"])
            frozen = json.loads(visits_path.read_text(encoding="utf-8"))
            self.assertNotIn("starttime", frozen[0]["medications"][0])
            patched = json.loads((output_dir / "visits.json").read_text(encoding="utf-8"))
            self.assertEqual(
                patched[0]["medications"][0]["starttime"], "2150-01-02 08:00:00"
            )
            self.assertEqual(
                patched[0]["discharge_note_full"], visits[0]["discharge_note_full"]
            )
            self.assertEqual(patched[0]["procedures"], [])
            self.assertIn("admittime", patched[0])


if __name__ == "__main__":
    unittest.main()
