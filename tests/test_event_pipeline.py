from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

import pyarrow.parquet as pq

from data_pipeline.event_pipeline import run_cleaning, run_normalization
from data_pipeline.event_pipeline.schemas import EVENT_JSON_SCHEMA_PATH, QUALITY_FLAG_CODES
from data_pipeline.event_pipeline.source_registry import (
    SOURCE_CATALOG_SHA256,
    SOURCE_CATALOG_VERSION,
)


class EventPipelineTest(unittest.TestCase):
    def _record(self) -> dict[str, object]:
        poe = [
            {
                "poe_id": "1-1",
                "poe_seq": "1",
                "subject_id": "1",
                "hadm_id": "10",
                "ordertime": "2150-01-01 09:00:00",
                "order_type": "Radiology",
                "order_subtype": "General Xray",
                "transaction_type": "New",
                "order_status": "Inactive",
            },
            {
                "poe_id": "1-2",
                "poe_seq": "2",
                "subject_id": "1",
                "hadm_id": "10",
                "ordertime": "2150-01-01 09:05:00",
                "order_type": "Lab",
                "order_subtype": None,
                "transaction_type": "New",
                "order_status": "Inactive",
            },
        ]
        timeline = [
            {
                "subject_id": "1",
                "hadm_id": "10",
                "poe_id": "1-1",
                "poe_seq": "1",
                "event_time": "2150-01-01 09:00:00",
                "action": "create",
                "order_status_raw": "Inactive",
                "clinical_category": {
                    "raw": "Radiology",
                    "subtype_raw": "General Xray",
                },
                "content_specificity": "subtype_only",
                "order_content": {"medications": []},
                "relations": {},
                "quality_flags": [],
            },
            {
                "subject_id": "1",
                "hadm_id": "10",
                "poe_id": "1-2",
                "poe_seq": "2",
                "event_time": "2150-01-01 09:05:00",
                "action": "create",
                "order_status_raw": "Inactive",
                "clinical_category": {"raw": "Lab", "subtype_raw": None},
                "content_specificity": "category_only",
                "order_content": {"medications": []},
                "relations": {},
                "quality_flags": ["category_only_no_specific_order_content"],
            },
        ]
        return {
            "schema": {"name": "mimic_admission_raw", "version": "1.0.0"},
            "subject_id": "1",
            "hadm_id": "10",
            "mimic_iv_hosp": {
                "patients": [],
                "admissions": [],
                "labevents": [
                    {
                        "labevent_id": "100",
                        "subject_id": "1",
                        "hadm_id": "10",
                        "itemid": "51222",
                        "itemid_decoded": {"label": "Hemoglobin"},
                        "charttime": "2150-01-01 08:30:00",
                        "storetime": "2150-01-01 08:45:00",
                        "value": "14.2",
                        "valuenum": "14.2",
                        "valueuom": "g/dL",
                        "ref_range_lower": "13.7",
                        "ref_range_upper": "17.5",
                        "flag": None,
                    }
                ],
                "microbiologyevents": [],
                "poe": poe,
                "poe_detail": [],
                "poe_timeline": timeline,
                "prescriptions": [
                    {
                        "subject_id": "1",
                        "hadm_id": "10",
                        "pharmacy_id": "p1",
                        "poe_id": "1-1",
                        "poe_seq": "1",
                        "drug": "Aspirin",
                        "ndc": "123",
                        "gsn": None,
                        "starttime": "2150-01-01 09:00:00",
                        "stoptime": "2150-01-02 09:00:00",
                        "dose_val_rx": "81",
                        "dose_unit_rx": "mg",
                        "route": "PO",
                    }
                ],
                "pharmacy": [
                    {
                        "subject_id": "1",
                        "hadm_id": "10",
                        "pharmacy_id": "p1",
                        "poe_id": "1-1",
                        "medication": "Aspirin",
                        "status": "Inactive",
                        "entertime": "2150-01-01 09:01:00",
                        "verifiedtime": "2150-01-01 09:02:00",
                    }
                ],
                "emar": [
                    {
                        "subject_id": "1",
                        "hadm_id": "10",
                        "emar_id": "e1",
                        "emar_seq": "1",
                        "medication": "Aspirin",
                        "event_txt": "Not Given",
                        "charttime": "2150-01-01 10:00:00",
                        "storetime": "2150-01-01 10:01:00",
                    }
                ],
                "emar_detail": [],
                "diagnoses_icd": [],
                "hcpcsevents": [],
                "drgcodes": [],
                "services": [
                    {
                        "subject_id": "1",
                        "hadm_id": "10",
                        "transfertime": "2150-01-01 08:00:00",
                        "prev_service": None,
                        "curr_service": "MED",
                    }
                ],
                "transfers": [
                    {
                        "subject_id": "1",
                        "hadm_id": "10",
                        "transfer_id": "t1",
                        "eventtype": "admit",
                        "careunit": "Medicine",
                        "intime": "2150-01-01 08:00:00",
                        "outtime": None,
                    }
                ],
                "procedures_icd": [
                    {
                        "subject_id": "1",
                        "hadm_id": "10",
                        "seq_num": "1",
                        "chartdate": "2150-01-02",
                        "icd_code": "0066",
                        "icd_version": "9",
                        "icd_decoded": {"long_title": "PCI"},
                    }
                ],
            },
            "mimic_iv_icu": {
                "icustays": [],
                "datetimeevents": [],
                "ingredientevents": [],
                "inputevents": [],
                "outputevents": [],
                "procedureevents": [
                    {
                        "subject_id": "1",
                        "hadm_id": "10",
                        "stay_id": "20",
                        "orderid": "o1",
                        "itemid": "225401",
                        "itemid_decoded": {"label": "Procedure"},
                        "starttime": "2150-01-01 11:00:00",
                        "endtime": "2150-01-01 11:30:00",
                        "storetime": "2150-01-01 11:31:00",
                        "value": "1",
                        "valueuom": None,
                    }
                ]
            },
            "mimic_iv_ed": {
                "edstays": [],
                "triage": [
                    {
                        "subject_id": "1",
                        "stay_id": "30",
                        "chiefcomplaint": "Chest pain",
                        "heartrate": "63",
                        "sbp": "127",
                        "dbp": "73",
                        "o2sat": "98",
                        "temperature": None,
                        "resprate": None,
                        "pain": None,
                        "acuity": "2",
                    }
                ],
                "vitalsign": [],
                "diagnosis": [],
                "medrecon": [],
                "pyxis": [],
            },
            "mimic_iv_note": {
                "radiology": [
                    {
                        "note_id": "r1",
                        "subject_id": "1",
                        "hadm_id": "10",
                        "note_type": "RR",
                        "note_seq": "1",
                        "charttime": "2150-01-01 12:00:00",
                        "storetime": "2150-01-01 12:05:00",
                        "text": "Not copied to derived event.",
                    }
                ],
                "radiology_detail": [],
                "discharge": [
                    {
                        "note_id": "d1",
                        "subject_id": "1",
                        "hadm_id": "10",
                        "note_type": "DS",
                        "note_seq": "1",
                        "charttime": "2150-01-03 12:00:00",
                        "storetime": "2150-01-03 12:05:00",
                        "text": "Not copied to derived event.",
                    }
                ],
                "discharge_detail": [],
            },
        }

    def _write_source(self, root: Path, record: dict[str, object]) -> Path:
        path = root / "source.jsonl"
        path.write_text(json.dumps(record) + "\n", encoding="utf-8")
        return path

    def test_two_stage_pipeline_is_traceable_and_category_order_stays_unresolved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = self._record()
            source = self._write_source(root, original)
            source_before = source.read_bytes()
            cleaning = run_cleaning(source, root / "cleaning", batch_size=3)
            normalization = run_normalization(
                root / "cleaning" / "cleaned_events.parquet",
                root / "cleaning" / "term_inventory.parquet",
                root / "normalization",
                batch_size=3,
            )

            self.assertEqual(source.read_bytes(), source_before)
            self.assertEqual(cleaning["counts"]["admissions"], 1)
            self.assertEqual(cleaning["source_catalog"]["sources"], 33)
            self.assertEqual(cleaning["source_catalog"]["event_sources"], 21)
            self.assertEqual(
                cleaning["source_catalog"]["version"], SOURCE_CATALOG_VERSION
            )
            self.assertEqual(
                cleaning["source_catalog"]["sha256"], SOURCE_CATALOG_SHA256
            )
            self.assertEqual(normalization["counts"]["events"], cleaning["counts"]["events"])
            for filename in (
                "cleaned_events.parquet",
                "cleaning_rejected.parquet",
                "term_inventory.parquet",
            ):
                self.assertTrue((root / "cleaning" / filename).is_file())
            for filename in (
                "normalization_mappings.parquet",
                "normalized_events.parquet",
                "normalization_review_queue.parquet",
            ):
                self.assertTrue((root / "normalization" / filename).is_file())

            cleaned = pq.read_table(root / "cleaning" / "cleaned_events.parquet").to_pylist()
            normalized = pq.read_table(root / "normalization" / "normalized_events.parquet").to_pylist()
            self.assertTrue(all(row["raw_row_ref"].startswith("source.jsonl#L1/") for row in cleaned))
            self.assertTrue(all(row["cleaning_status"] == "accepted" for row in cleaned))
            self.assertTrue(all(row["normalization_status"] is None for row in cleaned))
            chest_pain = next(row for row in normalized if row["event_kind"] == "symptom_reported")
            self.assertEqual(chest_pain["concept_id"], "symptom:chest_pain")
            hemoglobin = next(row for row in normalized if row["event_kind"] == "laboratory_resulted")
            self.assertEqual(hemoglobin["concept_id"], "lab:51222")
            self.assertEqual(hemoglobin["value_numeric"], 14.2)
            self.assertEqual(hemoglobin["normalized_unit"], "g/dL")
            category_only = next(
                row
                for row in normalized
                if row["event_kind"] == "laboratory_ordered"
                and row["content_specificity"] == "category_only"
            )
            self.assertIsNone(category_only["concept_id"])
            self.assertEqual(category_only["normalization_status"], "unresolved")
            self.assertEqual(
                category_only["quality_flags"],
                ["CATEGORY_ONLY_NO_SPECIFIC_ORDER_CONTENT"],
            )
            prescription = next(
                row for row in cleaned if row["event_kind"] == "medication_ordered"
            )
            self.assertEqual(len(prescription["supporting_source_row_ids"]), 1)
            self.assertEqual(
                prescription["supporting_raw_row_refs"],
                ["source.jsonl#L1/mimic_iv_hosp.poe_timeline[0]"],
            )
            discharge = next(
                row for row in cleaned if row["source_table"] == "note.discharge"
            )
            self.assertEqual(discharge["evidence_phase"], "post_hoc")
            normalized_prescription = next(
                row for row in normalized if row["event_id"] == prescription["event_id"]
            )
            self.assertEqual(normalized_prescription["cleaning_status"], "accepted")
            self.assertEqual(
                normalized_prescription["supporting_raw_row_refs"],
                prescription["supporting_raw_row_refs"],
            )

    def test_reconciliation_is_per_source_row_and_known_data_error_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = self._record()
            record["mimic_iv_hosp"]["labevents"][0].pop("itemid_decoded")  # type: ignore[index]
            source = self._write_source(root, record)
            manifest = run_cleaning(source, root / "cleaning")
            rejected = pq.read_table(root / "cleaning" / "cleaning_rejected.parquet").to_pylist()
            self.assertEqual(manifest["counts"]["rejected"], 1)
            self.assertEqual(rejected[0]["reason_code"], "LAB_CONCEPT_MISSING")
            self.assertEqual(rejected[0]["cleaning_status"], "rejected")
            reconciliation = json.loads(
                (root / "cleaning" / "source_reconciliation.json").read_text(encoding="utf-8")
            )
            for table in reconciliation["tables"]:
                self.assertEqual(
                    table["input_rows"],
                    table["accepted_source_rows"] + table["rejected_source_rows"],
                )

    def test_available_before_event_time_rejects_source_rows_without_stopping_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = self._record()
            record["mimic_iv_hosp"]["labevents"][0]["storetime"] = (  # type: ignore[index]
                "2150-01-01 08:00:00"
            )
            record["mimic_iv_note"]["radiology"][0]["storetime"] = (  # type: ignore[index]
                "2150-01-01 11:55:00"
            )
            source = self._write_source(root, record)

            manifest = run_cleaning(source, root / "cleaning")
            cleaned = pq.read_table(
                root / "cleaning" / "cleaned_events.parquet"
            ).to_pylist()
            rejected = pq.read_table(
                root / "cleaning" / "cleaning_rejected.parquet"
            ).to_pylist()

            self.assertEqual(manifest["counts"]["rejected"], 2)
            self.assertEqual(
                {row["source_table"] for row in rejected},
                {"hosp.labevents", "note.radiology"},
            )
            self.assertEqual(
                {row["reason_code"] for row in rejected},
                {"AVAILABLE_BEFORE_EVENT_TIME"},
            )
            rejected_source_ids = {row["source_row_id"] for row in rejected}
            self.assertTrue(
                rejected_source_ids.isdisjoint(
                    {row["source_row_id"] for row in cleaned}
                )
            )
            reconciliation = json.loads(
                (root / "cleaning" / "source_reconciliation.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(
                reconciliation["source_rows"],
                reconciliation["classified_source_rows"],
            )
            for table in reconciliation["tables"]:
                self.assertEqual(
                    table["input_rows"],
                    table["accepted_source_rows"] + table["rejected_source_rows"],
                )

    def test_stable_ids_do_not_depend_on_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = self._write_source(root, deepcopy(self._record()))
            run_cleaning(source, root / "first", batch_size=2)
            run_cleaning(source, root / "second", batch_size=7)
            first = pq.read_table(root / "first" / "cleaned_events.parquet").column("event_id").to_pylist()
            second = pq.read_table(root / "second" / "cleaned_events.parquet").column("event_id").to_pylist()
            self.assertEqual(first, second)
            self.assertEqual(len(first), len(set(first)))

    def test_unknown_quality_flag_stops_cleaning_without_partial_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record = self._record()
            record["mimic_iv_hosp"]["poe_timeline"][0]["quality_flags"] = [  # type: ignore[index]
                "new_unknown_flag"
            ]
            source = self._write_source(root, record)
            output = root / "cleaning"

            with self.assertRaisesRegex(ValueError, "unknown quality flag"):
                run_cleaning(source, output)

            self.assertFalse(output.exists())

    def test_quality_flag_enum_matches_json_schema(self) -> None:
        schema = json.loads(EVENT_JSON_SCHEMA_PATH.read_text(encoding="utf-8"))
        schema_codes = tuple(
            schema["properties"]["quality_flags"]["items"]["enum"]
        )
        self.assertEqual(schema_codes, QUALITY_FLAG_CODES)


if __name__ == "__main__":
    unittest.main()
