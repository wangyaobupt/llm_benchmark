from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from data_pipeline.mcq_visit_standardize.dashboard import compute_stats, render_html
from data_pipeline.mcq_visit_standardize.io import write_json_array


class DashboardTests(unittest.TestCase):
    def test_compute_stats_and_html_have_no_patient_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            visits_path = Path(tmp) / "visits.json"
            write_json_array(
                visits_path,
                [
                    {
                        "sex": "F",
                        "age_at_encounter": 64,
                        "admission_type": "EW EMER.",
                        "temperature": 98.6,
                        "chief_complaint_concepts": [
                            {
                                "source": "CP",
                                "standard": "Chest pain",
                                "status": "mapped/exact",
                                "polarity": "asserted",
                            }
                        ],
                        "ed_chief_complaint_concepts": [],
                        "investigations": {
                            "laboratory": [
                                {
                                    "itemid": 50912,
                                    "label": "Creatinine",
                                    "fluid": "Blood",
                                    "results": [
                                        {"charttime": "2100-01-02T08:00:00", "valuenum": 1.5},
                                        {"charttime": None, "valuenum": 1.4},
                                    ],
                                }
                            ]
                        },
                        "investigations_normalized": {
                            "radiology": [
                                {
                                    "source_exam_name": "CHEST (PA & LAT)",
                                    "standard_exam_name": "Chest X-ray, PA and Lateral Views",
                                    "status": "mapped/normalized",
                                }
                            ],
                            "laboratory": [
                                {
                                    "standard_test_name": "Creatinine, Blood",
                                    "source_label": "Creatinine",
                                    "results": [
                                        {"unit_status": "mapped/exact", "normalized_unit": "mg/dL"}
                                    ],
                                }
                            ],
                        },
                        "medications_normalized": [
                            {"status": "mapped/exact", "standard_ingredients": ["Vancomycin"]}
                        ],
                        "allergy_concepts": [
                            {"status": "mapped/exact", "standard": "No known allergies"}
                        ],
                        "standard_rhythm": {"status": "mapped/exact", "standard": "Sinus rhythm"},
                    }
                ],
            )
            stats = compute_stats(
                visits_path,
                acceptance={
                    "records": 1,
                    "chief_complaint_mapped_rate": 1.0,
                    "chief_complaint_mapped": 1,
                    "chief_complaint_concepts": 1,
                    "review_queue_rows": 0,
                    "mapping_version": "test",
                    "temperature_reversible": 1,
                },
                synonyms=[
                    {
                        "domain": "symptom",
                        "lookup_key": "cp",
                        "standard": "Chest pain",
                        "concept_id": "symptom:chest_pain",
                    }
                ],
            )
            self.assertEqual(stats["visits"], 1)
            self.assertEqual(stats["chief_complaint"]["top_standards"][0]["name"], "Chest pain")
            self.assertEqual(stats["laboratory"]["top_names"][0]["name"], "Creatinine, Blood")
            self.assertEqual(stats["laboratory"]["results"], 2)
            self.assertEqual(stats["laboratory"]["charttime"][0]["name"], "有 charttime")
            self.assertEqual(stats["laboratory"]["charttime"][0]["count"], 1)
            page = render_html(stats)
            self.assertIn("Chest pain", page)
            self.assertIn("Creatinine, Blood", page)
            self.assertIn("charttime", page)
            self.assertIn("gold = 0", page)
            self.assertNotIn("subject_id", page.lower())
            self.assertNotIn("discharge_note_full", page.lower())


if __name__ == "__main__":
    unittest.main()
