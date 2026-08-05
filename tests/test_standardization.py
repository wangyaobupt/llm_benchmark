import csv
import json
import tempfile
import unittest
from pathlib import Path

from rwd_standardization.common import INPUT_COLUMNS, OUTPUT_COLUMNS, canonical_name
from rwd_standardization.mapping import MappingIndex
from rwd_standardization.pipeline import (
    StandardizationError,
    _validate_standardized_output,
    build_mappings,
    parse_dose,
    run_standardization,
    transform_with_mappings,
)


class FakeMappingClient:
    def __init__(self):
        self.mapped = []
        self.verified = []

    def map_batch(self, candidates):
        self.mapped.extend(candidate.source for candidate in candidates)
        return {
            candidate.key: (
                ["Myocardial infarction"]
                if candidate.source.casefold() == "heart attack"
                else [canonical_name(candidate.source)]
            )
            for candidate in candidates
        }

    def verify_batch(self, candidates, proposed):
        self.verified.extend(candidate.source for candidate in candidates)
        return {
            candidate.key: candidate.source.casefold() == "heart attack"
            for candidate in candidates
        }


class StandardizationTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.input = self.root / "cleaned.csv"
        self.output = self.root / "out" / "standardized.csv"
        self.mappings = self.root / "out" / "mappings.jsonl"
        self.review = self.root / "out" / "review.jsonl"
        self.manifest = self.root / "out" / "manifest.json"
        self.row = self._row()
        self._write_input([self.row])

    def tearDown(self):
        self.tempdir.cleanup()

    def _row(self):
        return {
            "subject_id": "1",
            "hadm_id": "10",
            "age_at_encounter": "52",
            "sex": "F",
            "chief_complaint": json.dumps(["SOB", "dyspnea", "shortness of breath"]),
            "history_of_present_illness": json.dumps(["heart attack", "knee"]),
            "past_medical_history": json.dumps(["HTN", "CABG"]),
            "medications_on_admission": json.dumps(["ASA", "Truvada"]),
            "investigation_orders": json.dumps(
                [
                    {
                        "order_type": "Lab",
                        "order_subtype": "CSF",
                        "poe_detail": [
                            {"field_name": "Specimen", "field_value": "CSF"}
                        ],
                    }
                ]
            ),
            "investigation_reports": json.dumps(
                {
                    "laboratory": [
                        {
                            "d_labitems": {
                                "itemid": 50912,
                                "label": "Creatinine",
                                "fluid": "Blood",
                                "category": "Chemistry",
                            },
                            "labevents": {
                                "value": "1.2",
                                "valuenum": 1.2,
                                "valueuom": "mg/dL",
                                "ref_range_lower": 0.4,
                                "ref_range_upper": 1.1,
                                "flag": "abnormal",
                                "comments": "Original comment.",
                            },
                        },
                        {
                            "d_labitems": {
                                "itemid": 51000,
                                "label": "Example screen",
                                "fluid": "Blood",
                                "category": "Chemistry",
                            },
                            "labevents": {
                                "value": "NEGATIVE",
                                "valuenum": None,
                                "valueuom": None,
                                "ref_range_lower": None,
                                "ref_range_upper": None,
                                "flag": None,
                                "comments": None,
                            },
                        },
                    ],
                    "radiology": [
                        {
                            "radiology": {"text": "Original report text."},
                            "radiology_detail": [
                                {
                                    "field_name": "exam_code",
                                    "field_value": "C11",
                                    "field_ordinal": 1,
                                },
                                {
                                    "field_name": "exam_name",
                                    "field_value": "CHEST PA AND LAT",
                                    "field_ordinal": 1,
                                },
                            ],
                        }
                    ],
                }
            ),
            "primary_icd_code": "5723",
            "primary_diagnosis_name": "Portal hypertension",
            "primary_icd_version": "ICD-9-CM",
            "other_diagnoses": json.dumps(["Other ascites"]),
            "medication_prescriptions": json.dumps(
                [
                    {
                        "drug": "CeftriaXONE",
                        "prod_strength": "1g Frozen Bag",
                        "form_rx": "VIAL",
                        "dose_val_rx": "1-2",
                        "dose_unit_rx": "gm",
                        "route": "IV",
                        "doses_per_24_hrs": 1.0,
                    }
                ]
            ),
            "procedures": json.dumps(
                [
                    {
                        "procedure_name": "Percutaneous abdominal drainage",
                        "icd_code": "5491",
                        "icd_version": "ICD-9-PCS",
                    }
                ]
            ),
            "discharge_record": "Keep this text exactly.",
        }

    def _write_input(self, rows):
        with self.input.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=INPUT_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)

    def _read_output(self):
        with self.output.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            self.assertEqual(tuple(reader.fieldnames), OUTPUT_COLUMNS)
            return list(reader)

    def test_offline_end_to_end_preserves_information_and_writes_artifacts(self):
        summary = run_standardization(
            self.input,
            self.output,
            self.mappings,
            self.review,
            self.manifest,
            workers=1,
            batch_size=5,
        )

        self.assertEqual(summary.row_count, 1)
        self.assertGreater(summary.candidate_count, 10)
        row = self._read_output()[0]
        self.assertEqual(json.loads(row["chief_complaint"]), ["Shortness of breath"])
        self.assertEqual(json.loads(row["history_of_present_illness"]), ["Heart attack", "Knee"])
        self.assertEqual(
            json.loads(row["past_medical_history"]),
            ["Hypertension", "Coronary artery bypass grafting"],
        )
        self.assertEqual(
            json.loads(row["medications_on_admission"]),
            ["Aspirin", "Emtricitabine", "Tenofovir disoproxil"],
        )
        self.assertEqual(row["primary_diagnosis"], "Portal hypertension")
        self.assertEqual(row["discharge_record"], "Keep this text exactly.")

        reports = json.loads(row["investigation_reports"])
        self.assertEqual(reports["laboratory"][0]["test_name"], "Creatinine, blood")
        self.assertEqual(reports["laboratory"][0]["result"]["type"], "numeric")
        self.assertEqual(reports["laboratory"][1]["result"]["text"], "NEGATIVE")
        self.assertEqual(reports["radiology"][0]["report_text"], "Original report text.")

        prescription = json.loads(row["medication_prescriptions"])[0]
        self.assertEqual(prescription["ingredients"], ["Ceftriaxone"])
        self.assertEqual(prescription["product_strength"], "1 g Frozen Bag")
        self.assertEqual(prescription["dose_form"], "Vial")
        self.assertEqual(prescription["dose"]["type"], "range")
        self.assertEqual(prescription["dose"]["minimum"], 1)
        self.assertEqual(prescription["dose"]["maximum"], 2)
        self.assertEqual(prescription["dose"]["unit"], "g")
        self.assertEqual(prescription["route"], "intravenous")

        self.assertTrue(self.mappings.is_file())
        self.assertTrue(self.review.is_file())
        manifest = json.loads(self.manifest.read_text(encoding="utf-8"))
        self.assertEqual(manifest["row_count"], 1)
        self.assertFalse(manifest["llm_enabled"])
        self.assertIn("standardized_output", manifest)

    def test_llm_agreement_and_disagreement_are_distinguished(self):
        client = FakeMappingClient()
        _, _, counts = build_mappings(
            self.input,
            self.mappings,
            self.review,
            self.manifest,
            client=client,
            workers=1,
            batch_size=100,
        )
        records = [
            json.loads(line)
            for line in self.mappings.read_text(encoding="utf-8").splitlines()
        ]
        by_source = {
            (record["source_field"], record["source"]): record for record in records
        }
        heart_attack = by_source[("history_of_present_illness", "heart attack")]
        knee = by_source[("history_of_present_illness", "knee")]
        diagnosis = by_source[("primary_diagnosis", "Portal hypertension")]
        procedure = by_source[("procedures", "Percutaneous abdominal drainage")]
        self.assertEqual(heart_attack["standard"], ["Myocardial infarction"])
        self.assertEqual(heart_attack["method"], "llm_agreement")
        self.assertEqual(knee["standard"], ["Knee"])
        self.assertEqual(knee["method"], "normalized_identity")
        self.assertEqual(diagnosis["method"], "normalized_identity")
        self.assertEqual(procedure["method"], "normalized_identity")
        self.assertEqual(counts["unique"]["llm_agreement"], 1)
        self.assertIn("heart attack", client.mapped)
        self.assertIn("heart attack", client.verified)
        self.assertIn("knee", client.mapped)
        self.assertIn("Portal hypertension", client.mapped)
        self.assertIn("Percutaneous abdominal drainage", client.mapped)

    def test_transform_is_deterministic(self):
        run_standardization(
            self.input,
            self.output,
            self.mappings,
            self.review,
            self.manifest,
            workers=1,
        )
        first = self.output.read_bytes()
        transform_with_mappings(self.input, self.mappings, self.output, self.manifest)
        self.assertEqual(self.output.read_bytes(), first)

    def test_missing_frozen_mapping_does_not_replace_output(self):
        run_standardization(
            self.input,
            self.output,
            self.mappings,
            self.review,
            self.manifest,
            workers=1,
        )
        original_output = self.output.read_bytes()
        records = self.mappings.read_text(encoding="utf-8").splitlines()
        filtered = [line for line in records if '"source":"SOB"' not in line]
        self.mappings.write_text("\n".join(filtered) + "\n", encoding="utf-8")

        with self.assertRaises(StandardizationError):
            transform_with_mappings(self.input, self.mappings, self.output, self.manifest)
        self.assertEqual(self.output.read_bytes(), original_output)

    def test_transform_rejects_mapping_that_does_not_match_manifest(self):
        run_standardization(
            self.input,
            self.output,
            self.mappings,
            self.review,
            self.manifest,
            workers=1,
        )
        original_output = self.output.read_bytes()
        records = self.mappings.read_text(encoding="utf-8").splitlines()
        record = json.loads(records[0])
        record["standard"] = ["Changed standard name"]
        records[0] = json.dumps(record, separators=(",", ":"), sort_keys=True)
        self.mappings.write_text("\n".join(records) + "\n", encoding="utf-8")

        with self.assertRaisesRegex(StandardizationError, "does not match the manifest"):
            transform_with_mappings(self.input, self.mappings, self.output, self.manifest)
        self.assertEqual(self.output.read_bytes(), original_output)

    def test_validation_detects_one_missing_output_visit(self):
        run_standardization(
            self.input,
            self.output,
            self.mappings,
            self.review,
            self.manifest,
            workers=1,
        )
        second = dict(self.row)
        second["subject_id"] = "2"
        second["hadm_id"] = "20"
        self._write_input([self.row, second])

        with self.assertRaisesRegex(StandardizationError, "Visit counts differ"):
            _validate_standardized_output(self.input, self.output)

    def test_dose_parser_preserves_unparsed_text(self):
        self.assertEqual(parse_dose("25,000", "unit")["value"], 25000)
        self.assertEqual(parse_dose("0.5 to 1", "mg")["type"], "range")
        text = parse_dose("one tablet as needed", "tablet")
        self.assertEqual(text["type"], "text")
        self.assertEqual(text["text"], "one tablet as needed")


if __name__ == "__main__":
    unittest.main()
