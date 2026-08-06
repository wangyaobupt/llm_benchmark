import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from rwd_pipeline.extraction.common import ExtractionError, OUTPUT_COLUMNS
from rwd_pipeline.extraction.pipeline import run_extraction


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name) / "mimic"
        (self.root / "hosp").mkdir(parents=True)
        (self.root / "note").mkdir()
        self.output = Path(self.tempdir.name) / "output.csv"
        self._write_fixture()

    def tearDown(self):
        self.tempdir.cleanup()

    def write(self, module, filename, columns, rows):
        pd.DataFrame(rows, columns=columns).to_csv(self.root / module / filename, index=False)

    def _write_fixture(self):
        self.write(
            "hosp",
            "admissions.csv",
            ["subject_id", "hadm_id", "admittime"],
            [["1", "10", "2200-01-01 08:00:00"], ["2", "20", "2200-02-01 08:00:00"]],
        )
        self.write(
            "hosp",
            "patients.csv",
            ["subject_id", "gender", "anchor_age", "anchor_year"],
            [["1", "F", 40, 2200], ["2", "M", 50, 2200]],
        )
        self.write(
            "hosp",
            "d_icd_diagnoses.csv",
            ["icd_code", "icd_version", "long_title"],
            [["A1", "10", "Primary diagnosis"], ["B1", "10", "Other diagnosis"], ["C1", "10", "Second primary"]],
        )
        self.write(
            "hosp",
            "diagnoses_icd.csv",
            ["subject_id", "hadm_id", "seq_num", "icd_code", "icd_version"],
            [["1", "10", 1, "A1", "10"], ["1", "10", 2, "B1", "10"], ["2", "20", 1, "C1", "10"]],
        )
        self.write(
            "note",
            "discharge.csv",
            ["note_id", "subject_id", "hadm_id", "note_type", "note_seq", "charttime", "storetime", "text"],
            [
                ["1-DS-1", "1", "10", "DS", 1, "2200-01-03", "2200-01-04", "Chief Complaint:\nFever\nHistory of Present Illness:\nTwo days ill\nFollow-up Instructions:\nSee PCP"],
                ["2-DS-1", "2", "20", "DS", 1, "2200-02-03", "2200-02-04", "History of Present Illness:\nNo chief complaint section"],
            ],
        )
        self.write(
            "hosp",
            "poe.csv",
            ["poe_id", "poe_seq", "subject_id", "hadm_id", "ordertime", "order_type", "order_subtype", "transaction_type"],
            [
                ["p1", "1", "1", "10", "2200-01-01 09:00:00", "Lab", "CBC", "New"],
                ["p2", "2", "1", "10", "2200-01-02 09:00:00", "Lab", "CBC", "New"],
            ],
        )
        self.write(
            "hosp",
            "poe_detail.csv",
            ["poe_id", "poe_seq", "subject_id", "field_name", "field_value"],
            [["p1", "1", "1", "Test", "CBC"], ["p2", "2", "1", "Test", "CBC"]],
        )
        self.write(
            "hosp",
            "d_labitems.csv",
            ["itemid", "label", "fluid", "category"],
            [["100", "Hemoglobin", "Blood", "Hematology"]],
        )
        self.write(
            "hosp",
            "labevents.csv",
            ["labevent_id", "subject_id", "hadm_id", "itemid", "charttime", "storetime", "value", "valuenum", "valueuom", "ref_range_lower", "ref_range_upper", "flag", "comments"],
            [
                [2, "1", "10", "100", "2200-01-02", "2200-01-02", "12", 12.0, "g/dL", 10.0, 15.0, "", ""],
                [1, "1", "10", "100", "2200-01-01", "2200-01-01", "11", 11.0, "g/dL", 10.0, 15.0, "", ""],
            ],
        )
        self.write(
            "note",
            "radiology.csv",
            ["note_id", "subject_id", "hadm_id", "note_type", "note_seq", "charttime", "storetime", "text"],
            [["r1", "1", "10", "RR", 1, "2200-01-01", "2200-01-01", "Combined report"]],
        )
        self.write(
            "note",
            "radiology_detail.csv",
            ["note_id", "subject_id", "field_name", "field_value", "field_ordinal"],
            [["r1", "1", "exam_name", "CHEST X-RAY", 1], ["r1", "1", "exam_name", "ABDOMEN X-RAY", 2]],
        )
        self.write(
            "hosp",
            "prescriptions.csv",
            ["subject_id", "hadm_id", "pharmacy_id", "poe_id", "poe_seq", "starttime", "drug_type", "drug", "prod_strength", "form_rx", "dose_val_rx", "dose_unit_rx", "route", "doses_per_24_hrs"],
            [
                ["1", "10", "2", "p2", "2", "2200-01-02", "MAIN", "Aspirin", "81 mg", "TAB", "81", "mg", "PO", 1],
                ["1", "10", "1", "p1", "1", "2200-01-01", "MAIN", " aspirin ", "40 mg", "TAB", "40", "mg", "PO", 1],
            ],
        )
        self.write(
            "hosp",
            "d_icd_procedures.csv",
            ["icd_code", "icd_version", "long_title"],
            [["P1", "10", "Procedure one"]],
        )
        self.write(
            "hosp",
            "procedures_icd.csv",
            ["subject_id", "hadm_id", "seq_num", "chartdate", "icd_code", "icd_version"],
            [["1", "10", 2, "2200-01-02", "P1", "10"], ["1", "10", 1, "2200-01-01", "P1", "10"]],
        )

    def test_end_to_end_extracts_one_eligible_visit(self):
        summary = run_extraction(self.root, self.output, 2)
        self.assertEqual(summary.candidate_count, 2)
        self.assertEqual(summary.eligible_count, 1)
        output = pd.read_csv(self.output, dtype={"subject_id": "string", "hadm_id": "string"})
        self.assertEqual(list(output.columns), OUTPUT_COLUMNS)
        self.assertEqual(output.loc[0, "hadm_id"], "10")
        self.assertEqual(output.loc[0, "chief_complaint"], "Fever")
        self.assertEqual(len(json.loads(output.loc[0, "investigation_orders"])), 1)
        reports = json.loads(output.loc[0, "investigation_reports"])
        self.assertEqual(reports["laboratory"][0]["labevents"]["value"], "11")
        self.assertEqual(len(reports["radiology"]), 1)
        prescriptions = json.loads(output.loc[0, "medication_prescriptions"])
        self.assertEqual(prescriptions[0]["dose_val_rx"], "40")
        self.assertEqual(len(json.loads(output.loc[0, "procedures"])), 1)

    def test_subject_hadm_conflict_fails(self):
        path = self.root / "hosp" / "diagnoses_icd.csv"
        diagnoses = pd.read_csv(path, dtype="string")
        diagnoses.loc[0, "subject_id"] = "2"
        diagnoses.to_csv(path, index=False)
        with self.assertRaises(ExtractionError):
            run_extraction(self.root, self.output, 2)


if __name__ == "__main__":
    unittest.main()
