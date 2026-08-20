from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from data_pipeline.mcq_visit_standardize.io import write_json_array
from data_pipeline.mcq_visit_timeline.clocks import parse_datetime
from data_pipeline.mcq_visit_timeline.events import merge_visit
from data_pipeline.mcq_visit_timeline.pipeline import TimelineError, run


def _timed(**overrides: object) -> dict:
    visit = {
        "subject_id": "1",
        "hadm_id": "10",
        "admittime": "2188-04-24 10:00:00",
        "dischtime": "2188-04-26 12:00:00",
        "deathtime": None,
        "ed_intime": "2188-04-24 09:00:00",
        "ed_outtime": "2188-04-24 11:00:00",
        "age_at_encounter": 60,
        "sex": "F",
        "admission_type": "EW EMER.",
        "temperature": 98.6,
        "heartrate": 110,
        "resprate": 18,
        "o2sat": 97,
        "sbp": 80,
        "dbp": 50,
        "acuity": 2,
        "rhythm": None,
        "rhythm_charttime": None,
        "vitals_source": "triage",
        "primary_icd_code": "I214",
        "primary_diagnosis_name": "NSTEMI",
        "primary_icd_version": "ICD-10-CM",
        "primary_service": "MED",
        "discharge_location": "HOME",
        "investigations": {
            "laboratory": [
                {
                    "itemid": 51003,
                    "label": "Troponin T",
                    "fluid": "Blood",
                    "results": [
                        {
                            "charttime": "2188-04-24 10:30:00",
                            "storetime": "2188-04-24 11:00:00",
                            "value": "0.2",
                            "valuenum": 0.2,
                            "flag": "abnormal",
                        }
                    ],
                },
                {
                    "itemid": 50912,
                    "label": "Creatinine",
                    "fluid": "Blood",
                    "results": [
                        {
                            "charttime": "2188-04-24 10:40:00",
                            "storetime": None,
                            "value": "1.5",
                            "valuenum": 1.5,
                            "flag": None,
                        }
                    ],
                },
            ],
            "radiology": [
                {
                    "exam_name": "CHEST (PA AND LAT)",
                    "charttime": "2188-04-24 10:20:00",
                    "storetime": "2188-04-24 12:00:00",
                }
            ],
            "cardiology": [{"order_subtype": "ECG", "ordertime": "2188-04-24 09:30:00", "poe_detail": []}],
            "respiratory": [],
        },
        "medications": [
            {
                "drug": "Aspirin",
                "prod_strength": "81mg",
                "form_rx": "TAB",
                "dose_val_rx": "81",
                "dose_unit_rx": "mg",
                "route": "PO",
                "doses_per_24_hrs": 1,
                "starttime": "2188-04-24 11:30:00",
                "stoptime": "2188-04-25 11:30:00",
            }
        ],
        "procedures": [
            {
                "procedure_name": "Coronary arteriography",
                "icd_code": "4A023N7",
                "icd_version": 10,
                "chartdate": "2188-04-24",
            }
        ],
        "poe_lab_imaging": [
            {"order_type": "Lab", "order_subtype": None, "ordertime": "2188-04-24 09:15:00", "poe_detail": []}
        ],
        "medrecon": [],
        "transfers": [],
        "service_path": [{"transfertime": "2188-04-24 10:00:00", "prev_service": None, "curr_service": "MED"}],
    }
    visit.update(overrides)
    return visit


def _named(**overrides: object) -> dict:
    visit = {
        "subject_id": "1",
        "hadm_id": "10",
        "temperature_c": 37.0,
        "standard_rhythm": None,
        "chief_complaint_concepts": [
            {
                "source": "CP",
                "standard": "Chest pain",
                "concept_id": "symptom:chest pain",
                "polarity": "asserted",
                "status": "mapped/exact",
            }
        ],
        "ed_chief_complaint_concepts": [],
        "allergy_concepts": [],
        "standard_diagnosis_name": "Non-ST elevation NSTEMI",
        "standard_service_name": "Medicine",
        "mapping_version": "mcq-visit-standardize/1.0.8",
        "investigations_normalized": {
            "laboratory": [
                {
                    "itemid": 51003,
                    "standard_test_name": "Troponin T, Blood",
                    "status": "mapped/exact",
                    "results": [],
                },
                {
                    "itemid": 50912,
                    "standard_test_name": "Creatinine, Blood",
                    "status": "mapped/exact",
                    "results": [],
                },
            ],
            "radiology": [
                {
                    "source_exam_name": "CHEST (PA AND LAT)",
                    "standard_exam_name": "Chest radiography",
                    "status": "mapped/exact",
                    "charttime": "2188-04-24 10:20:00",
                }
            ],
            "cardiology": [
                {
                    "source_order_subtype": "ECG",
                    "standard_order_name": "ECG",
                    "status": "mapped/exact",
                    "ordertime": "2188-04-24 09:30:00",
                }
            ],
            "respiratory": [],
        },
        "medications_normalized": [
            {
                "source_drug": "Aspirin",
                "standard_ingredients": ["aspirin"],
                "status": "mapped/exact",
            }
        ],
        "medrecon_normalized": [],
        "procedures_normalized": [
            {
                "icd_code": "4A023N7",
                "icd_version": 10,
                "standard_procedure_name": "Coronary arteriography",
                "status": "mapped/exact",
            }
        ],
    }
    visit.update(overrides)
    return visit


class TimelineMergeTests(unittest.TestCase):
    def test_lab_clocks_use_charttime_not_storetime(self) -> None:
        header, events, facts = merge_visit(_timed(), _named())
        self.assertEqual(facts["presentation_origin_basis"], "ed_intime")
        lab = next(event for event in events if event["event_kind"] == "lab_resulted" and event["itemid"] == "51003")
        self.assertEqual(lab["occurrence_basis"], "charttime")
        self.assertEqual(lab["available_basis"], "storetime")
        self.assertEqual(lab["occurrence_time"], "2188-04-24 10:30:00")
        self.assertEqual(lab["available_time"], "2188-04-24 11:00:00")
        self.assertFalse(lab["time_missing"])
        self.assertEqual(lab["standard_name"], "Troponin T, Blood")

    def test_missing_storetime_keeps_occurrence(self) -> None:
        _, events, _ = merge_visit(_timed(), _named())
        creat = next(event for event in events if event["itemid"] == "50912")
        self.assertEqual(creat["occurrence_time"], "2188-04-24 10:40:00")
        self.assertIsNone(creat["available_time"])
        self.assertFalse(creat["time_missing"])

    def test_poe_lab_is_category_only(self) -> None:
        _, events, _ = merge_visit(_timed(), _named())
        poe = next(event for event in events if event["event_kind"] == "poe_lab_imaging")
        self.assertTrue(poe["category_only"])
        self.assertEqual(poe["source_name"], "Lab")

    def test_procedure_is_date_precision(self) -> None:
        _, events, _ = merge_visit(_timed(), _named())
        proc = next(event for event in events if event["event_kind"] == "procedure_recorded")
        self.assertEqual(proc["time_precision"], "date")
        self.assertEqual(proc["occurrence_basis"], "chartdate")

    def test_hadm_mismatch_fails(self) -> None:
        named = _named()
        named["hadm_id"] = "99"
        with self.assertRaises(ValueError):
            merge_visit(_timed(), named)

    def test_pipeline_refuses_upstream_output(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            times = root / "times"
            times.mkdir()
            write_json_array(times / "visits.json", [_timed()])
            named_path = root / "named.json"
            write_json_array(named_path, [_named()])
            with self.assertRaises(TimelineError):
                run(
                    times_path=times / "visits.json",
                    standardized_path=named_path,
                    output_dir=times,
                    expected_count=1,
                    skip_fingerprint=True,
                )

    def test_pipeline_writes_parquet(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            times_dir = root / "times"
            std_dir = root / "std"
            times_dir.mkdir()
            std_dir.mkdir()
            times_path = times_dir / "visits.json"
            named_path = std_dir / "visits_standardized.json"
            write_json_array(times_path, [_timed()])
            write_json_array(named_path, [_named()])
            output = root / "timeline"
            manifest = run(
                times_path=times_path,
                standardized_path=named_path,
                output_dir=output,
                expected_count=1,
                skip_fingerprint=True,
            )
            summary = manifest["summary"]
            self.assertEqual(summary["visits"], 1)
            self.assertGreater(summary["lab_result_rows"], 0)
            self.assertTrue((output / "visit_events.parquet").is_file())
            self.assertTrue((output / "presentation_facts.jsonl").is_file())
            self.assertTrue(parse_datetime("2188-04-24 10:00:00"))


if __name__ == "__main__":
    unittest.main()
