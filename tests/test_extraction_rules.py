import json
import unittest

import pandas as pd

from rwd_extraction.common import compact_json, normalize_name, time_ascending
from rwd_extraction.output import validate_output


class ExtractionRuleTests(unittest.TestCase):
    def test_name_normalization_is_limited(self):
        self.assertEqual(normalize_name("  Acute   Kidney FAILURE "), "acute kidney failure")
        self.assertNotEqual(normalize_name("heart attack"), normalize_name("myocardial infarction"))

    def test_missing_times_sort_after_real_times(self):
        self.assertLess(time_ascending("2200-01-01 00:00:00"), time_ascending(pd.NA))

    def test_compact_json_uses_json_null(self):
        self.assertEqual(compact_json({"value": None}), '{"value":null}')

    def test_output_validation_accepts_fixed_schema(self):
        from rwd_extraction.common import OUTPUT_COLUMNS

        row = {column: "" for column in OUTPUT_COLUMNS}
        row.update(
            {
                "subject_id": "1",
                "hadm_id": "10",
                "age_at_encounter": 40,
                "sex": "F",
                "chief_complaint": "Pain",
                "primary_icd_code": "A1",
                "primary_diagnosis_name": "Diagnosis",
                "primary_icd_version": "ICD-10-CM",
                "investigation_orders": "[]",
                "investigation_reports": '{"laboratory":[],"radiology":[]}',
                "other_diagnoses": "[]",
                "medication_prescriptions": "[]",
                "procedures": "[]",
            }
        )
        frame = pd.DataFrame([row], columns=OUTPUT_COLUMNS)
        validate_output(frame, {"10": 0})
        self.assertEqual(json.loads(frame.loc[0, "other_diagnoses"]), [])


if __name__ == "__main__":
    unittest.main()
