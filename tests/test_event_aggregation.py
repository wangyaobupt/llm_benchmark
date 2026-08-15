from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

import pyarrow as pa
import pyarrow.parquet as pq

from data_pipeline.event_aggregation import AggregationError, build_event_aggregation


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


class EventAggregationTest(unittest.TestCase):
    def _fixture(self, root: Path, *, invalid_ref: bool = False) -> Path:
        input_directory = root / "batch"
        event_output = input_directory / "event_pipeline_output"
        normalization = event_output / "normalization"
        normalization.mkdir(parents=True)
        source = {
            "schema": {"name": "clinical_readable", "version": "1"},
            "source_schema": {"name": "raw", "version": "1"},
            "subject_id": "1",
            "hadm_id": "10",
            "mimic_iv_hosp": {
                "labevents": [
                    {
                        "labevent_id": "100",
                        "subject_id": "1",
                        "hadm_id": "10",
                        "comments": "manual differential",
                        "itemid_decoded": {"label": "Hemoglobin"},
                    }
                ]
            },
            "mimic_iv_icu": {},
            "mimic_iv_ed": {
                "triage": [
                    {
                        "subject_id": "1",
                        "stay_id": "20",
                        "chiefcomplaint": "chest pain",
                    }
                ]
            },
            "mimic_iv_note": {
                "radiology": [
                    {
                        "note_id": "R1",
                        "subject_id": "1",
                        "hadm_id": "10",
                        "text": "No acute cardiopulmonary process.",
                    }
                ]
            },
        }
        raw = json.loads(json.dumps(source))
        raw.pop("source_schema")
        raw["mimic_iv_hosp"]["labevents"][0].pop("itemid_decoded")
        source_path = input_directory / "source.jsonl"
        raw_path = input_directory / "raw.jsonl"
        source_path.write_text(json.dumps(source) + "\n", encoding="utf-8")
        raw_path.write_text(json.dumps(raw) + "\n", encoding="utf-8")
        base_ref = "source.jsonl#L1/"
        rows = [
            {
                "event_id": "evt:lab",
                "subject_id": "1",
                "hadm_id": "10",
                "source_module": "mimic_iv_hosp",
                "source_table": "hosp.labevents",
                "source_array_index": 0,
                "jsonl_line_number": 1,
                "raw_row_ref": base_ref
                + ("mimic_iv_hosp.labevents[9]" if invalid_ref else "mimic_iv_hosp.labevents[0]"),
                "supporting_raw_row_refs": [],
                "normalization_status": "mapped",
            },
            {
                "event_id": "evt:triage",
                "subject_id": "1",
                "hadm_id": "10",
                "source_module": "mimic_iv_ed",
                "source_table": "ed.triage",
                "source_array_index": 0,
                "jsonl_line_number": 1,
                "raw_row_ref": base_ref + "mimic_iv_ed.triage[0]",
                "supporting_raw_row_refs": [],
                "normalization_status": "unresolved",
            },
            {
                "event_id": "evt:radiology",
                "subject_id": "1",
                "hadm_id": "10",
                "source_module": "mimic_iv_note",
                "source_table": "note.radiology",
                "source_array_index": 0,
                "jsonl_line_number": 1,
                "raw_row_ref": base_ref + "mimic_iv_note.radiology[0]",
                "supporting_raw_row_refs": [],
                "normalization_status": "mapped",
            },
        ]
        schema = pa.schema(
            [
                ("event_id", pa.string()),
                ("subject_id", pa.string()),
                ("hadm_id", pa.string()),
                ("source_module", pa.string()),
                ("source_table", pa.string()),
                ("source_array_index", pa.int64()),
                ("jsonl_line_number", pa.int64()),
                ("raw_row_ref", pa.string()),
                ("supporting_raw_row_refs", pa.list_(pa.string())),
                ("normalization_status", pa.string()),
            ]
        )
        normalized_path = normalization / "normalized_events.parquet"
        pq.write_table(pa.Table.from_pylist(rows, schema=schema), normalized_path)
        workflow = {
            "acceptance": {
                "cleaning": True,
                "normalization": True,
                "reproducible": True,
            },
            "inputs": {
                "source_jsonl": source_path.name,
                "source_jsonl_sha256": _sha256(source_path),
                "raw_source_jsonl": raw_path.name,
                "raw_source_jsonl_sha256": _sha256(raw_path),
            },
            "stages": {
                "cleaning": {"counts": {"admissions": 1, "source_rows": 3}},
                "normalization": {
                    "counts": {"events": 3},
                    "output_sha256": {
                        "normalized_events.parquet": _sha256(normalized_path)
                    },
                },
            },
        }
        (event_output / "workflow_manifest.json").write_text(
            json.dumps(workflow), encoding="utf-8"
        )
        return input_directory

    def test_builds_three_lossless_layers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_directory = self._fixture(root)
            output = input_directory / "event_pipeline_output" / "aggregation"
            manifest = build_event_aggregation(input_directory, output, batch_size=2)
            self.assertEqual(manifest["quality_status"], "passed")
            processed = pq.read_table(output / "processed_events.parquet").to_pylist()
            sources = pq.read_table(output / "raw_source_records.parquet").to_pylist()
            traceable = pq.read_table(output / "traceable_events.parquet").to_pylist()
            self.assertEqual(len(processed), 3)
            self.assertEqual(len(sources), 3)
            self.assertEqual(len(traceable), 3)
            by_event = {row["event_id"]: row for row in processed}
            self.assertEqual(by_event["evt:lab"]["source_text"], "manual differential")
            self.assertEqual(by_event["evt:triage"]["source_text"], "chest pain")
            self.assertEqual(
                by_event["evt:radiology"]["source_text"],
                "No acute cardiopulmonary process.",
            )
            lab_source = next(row for row in sources if row["source_table"] == "hosp.labevents")
            self.assertIn("itemid_decoded", lab_source["clinical_readable_record_json"])
            self.assertNotIn("itemid_decoded", lab_source["raw_record_json"])
            self.assertIn("clinical_readable_record_json", traceable[0])
            quality = json.loads((output / "quality_report.json").read_text(encoding="utf-8"))
            self.assertEqual(quality["status"], "passed")
            self.assertTrue(all(quality["checks"].values()))
            self.assertEqual(
                quality["observed"]["source_role_counts"]["event"], 3
            )

    def test_invalid_lineage_fails_without_publishing_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_directory = self._fixture(root, invalid_ref=True)
            output = input_directory / "event_pipeline_output" / "aggregation"
            with self.assertRaises(AggregationError) as raised:
                build_event_aggregation(input_directory, output, batch_size=2)
            self.assertEqual(raised.exception.reason_code, "NORMALIZED_EVENT_LINEAGE_MISMATCH")
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
