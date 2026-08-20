from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from data_pipeline.mcq_visit_extract.columns import RESULT_COLUMNS
from data_pipeline.mcq_visit_standardize.pipeline import StandardizeError, run
from data_pipeline.mcq_visit_standardize.abbrev import expand_for_display
from data_pipeline.mcq_visit_standardize.exams import exam_display_name
from data_pipeline.mcq_visit_standardize.symptoms import complaint_concepts, split_complaint
from data_pipeline.mcq_visit_standardize.transform import (
    celsius_to_fahrenheit,
    fahrenheit_to_celsius,
    standardize_visit,
)


def _base_visit(**overrides: object) -> dict:
    visit = {key: None for key in RESULT_COLUMNS}
    visit.update(
        {
            "subject_id": "1",
            "hadm_id": "10",
            "age_at_encounter": 60,
            "sex": "F",
            "admission_type": "EW EMER.",
            "chief_complaint": "CP, SOB",
            "allergies": "No Known Allergies / Adverse Drug Reactions",
            "primary_icd_code": "I214",
            "primary_diagnosis_name": "Non-ST elevation NSTEMI",
            "primary_icd_version": "ICD-10-CM",
            "other_diagnoses": [],
            "investigations": {
                "laboratory": [
                    {
                        "itemid": 50912,
                        "label": "Creatinine",
                        "fluid": "Blood",
                        "category": "Chemistry",
                        "results": [
                            {
                                "valuenum": 1.5,
                                "valueuom": "mg/dl",
                                "flag": "abnormal",
                            }
                        ],
                    }
                ],
                "radiology": [{"exam_name": "CHEST X-RAY", "charttime": None, "text": None, "details": []}],
                "cardiology": [],
                "respiratory": [],
            },
            "medications": [{"drug": "VANCOMYCIN", "route": "IV"}],
            "medrecon": [],
            "procedures": [],
            "primary_service": "MED",
            "ed_diagnoses": [],
            "transfers": [],
            "service_path": [],
            "poe_lab_imaging": [],
            "discharge_note_full": "Chief Complaint:\nCP, SOB\n",
            "temperature": 98.6,
        }
    )
    visit.update(overrides)
    return visit


class SymptomAndUnitTests(unittest.TestCase):
    def test_maps_cp_and_sob(self) -> None:
        concepts = complaint_concepts("CP, SOB")
        self.assertEqual(
            [item["standard"] for item in concepts],
            ["Chest pain", "Shortness of breath"],
        )
        self.assertTrue(all(item["status"] == "mapped/exact" for item in concepts))

    def test_splits_comma_separated_complaints(self) -> None:
        concepts = complaint_concepts("Chest pain, Dyspnea")
        self.assertEqual(
            [item["standard"] for item in concepts],
            ["Chest pain", "Shortness of breath"],
        )
        self.assertEqual([item["source"] for item in concepts], ["Chest pain", "Dyspnea"])

    def test_standard_name_is_also_an_alias(self) -> None:
        concepts = complaint_concepts("Dyspnea on exertion")
        self.assertEqual(concepts[0]["status"], "mapped/exact")
        self.assertEqual(concepts[0]["standard"], "Dyspnea on exertion")

    def test_expands_bilateral_and_laterality_abbreviations(self) -> None:
        self.assertEqual(expand_for_display("B/L FOOT PAIN"), "Bilateral foot pain")
        self.assertEqual(expand_for_display("B Leg swelling"), "Bilateral leg swelling")
        self.assertEqual(expand_for_display("Abnormal CT"), "Abnormal computed tomography")
        self.assertEqual(expand_for_display("R foot pain"), "Right foot pain")
        self.assertEqual(expand_for_display("L Weakness"), "Left weakness")
        self.assertEqual(expand_for_display("LLE pain"), "Left lower extremity pain")
        self.assertEqual(expand_for_display("RUQ pain"), "Right upper quadrant pain")
        self.assertEqual(expand_for_display("s/p fall"), "Status post fall")
        self.assertEqual(expand_for_display("STEMI"), "ST-elevation myocardial infarction")
        self.assertEqual(expand_for_display("NSTEMI"), "Non-ST-elevation myocardial infarction")
        self.assertEqual(expand_for_display("SBO"), "Small bowel obstruction")
        self.assertEqual(expand_for_display("ILI"), "Influenza-like illness")
        self.assertEqual(expand_for_display("ABD pain"), "Abdominal pain")
        self.assertEqual(expand_for_display("bilat ribs subacute fx"), "Bilateral ribs subacute fracture")
        self.assertEqual(expand_for_display("BRBPR"), "Bright red blood per rectum")
        self.assertEqual(expand_for_display("CVA"), "Cerebrovascular accident")
        self.assertEqual(expand_for_display("SOB/CP"), "Shortness of breath/chest pain")
        self.assertEqual(expand_for_display("N/V/D"), "Nausea, vomiting, and diarrhea")
        self.assertEqual(split_complaint("B/L FOOT PAIN"), ["B/L FOOT PAIN"])
        concepts = complaint_concepts("B/L FOOT PAIN")
        self.assertEqual(concepts[0]["source"], "B/L FOOT PAIN")
        self.assertEqual(concepts[0]["standard"], "Bilateral foot pain")
        self.assertEqual(concepts[0]["status"], "mapped/exact")
        fall = complaint_concepts("s/p fall")
        self.assertEqual(fall[0]["standard"], "Status post fall")

    def test_denied_chest_pain_is_not_asserted(self) -> None:
        concepts = complaint_concepts("denies chest pain")
        self.assertEqual(concepts[0]["polarity"], "denied")
        self.assertEqual(concepts[0]["standard"], "Chest pain")

    def test_not_sleeping_well_is_poor_sleep_not_denied(self) -> None:
        extra = {"not sleeping well": ("Poor sleep", "symptom:poor_sleep")}
        concepts = complaint_concepts("not sleeping well", extra_aliases=extra)
        self.assertEqual(concepts[0]["polarity"], "asserted")
        self.assertEqual(concepts[0]["standard"], "Poor sleep")
        self.assertEqual(concepts[0]["status"], "mapped/exact")

    def test_exam_names_become_readable_english(self) -> None:
        cases = {
            "ABDOMEN (SUPINE & ERECT)": "Abdominal X-ray, Supine and Erect Views",
            "CHEST (PA & LAT)": "Chest X-ray, PA and Lateral Views",
            "CHEST (PORTABLE AP)": "Chest X-ray, Portable AP View",
            "CHEST PORT. LINE PLACEMENT": "Chest X-ray, Line Placement",
            "CT HEAD W/O CONTRAST": "CT head without contrast",
            "CT ABD & PELVIS WITH CONTRAST": "CT abdomen and pelvis with contrast",
            "CT CHEST W/CONTRAST": "CT chest with contrast",
            "CTA CHEST": "CT angiography chest",
            "MR HEAD W/O CONTRAST": "MRI head without contrast",
            "LIVER OR GALLBLADDER US (SINGLE ORGAN)": "Ultrasound liver or gallbladder (single organ)",
            "RENAL U.S.": "Ultrasound renal",
            "PICC W/O PORT": "PICC without port",
            "FOOT AP,LAT & OBL RIGHT": "Right Foot X-ray, AP, Lateral and Oblique Views",
            "BILAT LOWER EXT VEINS": "Ultrasound bilateral lower extremity veins",
            "L-SPINE (AP & LAT) IN O.R.": "Lumbar Spine X-ray, AP and Lateral Views",
        }
        for source, expected in cases.items():
            self.assertEqual(exam_display_name(source), expected, source)

    def test_temperature_conversion_is_reversible(self) -> None:
        celsius = fahrenheit_to_celsius(98.6)
        self.assertEqual(celsius, 37.0)
        self.assertLessEqual(abs(celsius_to_fahrenheit(celsius) - 98.6), 0.15)


class TransformTests(unittest.TestCase):
    def test_preserves_original_columns_and_adds_concepts(self) -> None:
        visit = _base_visit()
        out, reviews = standardize_visit(visit)
        for key in RESULT_COLUMNS:
            self.assertEqual(out[key], visit[key])
        self.assertEqual(out["temperature_c"], 37.0)
        self.assertEqual(
            out["investigations_normalized"]["radiology"][0]["standard_exam_name"],
            "Chest X-ray",
        )
        self.assertEqual(out["investigations_normalized"]["laboratory"][0]["standard_test_name"], "Creatinine, Blood")
        self.assertEqual(
            out["investigations_normalized"]["laboratory"][0]["results"][0]["normalized_unit"],
            "mg/dL",
        )
        self.assertEqual(out["medications_normalized"][0]["standard_ingredients"], ["Vancomycin"])
        self.assertEqual(out["standard_service_name"]["standard"], "Medicine")
        self.assertEqual(out["allergy_concepts"][0]["concept_id"], "allergy:nka")
        self.assertEqual(out["mapping_version"], "mcq-visit-standardize/1.0.8")

    def test_unknown_symptom_goes_unresolved(self) -> None:
        visit = _base_visit(chief_complaint="zanzibar flare")
        out, reviews = standardize_visit(visit)
        self.assertEqual(out["chief_complaint_concepts"][0]["status"], "unresolved")
        self.assertTrue(any(item["field"] == "chief_complaint" for item in reviews))


class PipelineTests(unittest.TestCase):
    def test_run_writes_sidecar_and_refuses_extract_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            extract = Path(tmp) / "extract"
            extract.mkdir()
            visits = [_base_visit(hadm_id="10"), _base_visit(hadm_id="20", subject_id="2")]
            input_path = extract / "visits.json"
            input_path.write_text(
                "[\n"
                + ",\n".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) for row in visits)
                + "\n]\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(StandardizeError, "extract directory"):
                run(input_path=input_path, output_dir=extract, expected_count=2)
            output = Path(tmp) / "std"
            manifest = run(input_path=input_path, output_dir=output, expected_count=2)
            self.assertEqual(manifest["acceptance"]["records"], 2)
            self.assertTrue((extract / "visits.json").exists())
            standardized = json.loads((output / "visits_standardized.json").read_text(encoding="utf-8"))
            self.assertEqual(len(standardized), 2)
            self.assertEqual(standardized[0]["chief_complaint"], "CP, SOB")
            self.assertEqual(standardized[0]["chief_complaint_concepts"][0]["standard"], "Chest pain")
            second = run(input_path=input_path, output_dir=output, expected_count=2)
            self.assertEqual(second["identity_sha256"], manifest["identity_sha256"])


if __name__ == "__main__":
    unittest.main()
