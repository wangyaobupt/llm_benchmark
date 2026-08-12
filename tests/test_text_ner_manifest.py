from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import pyarrow.parquet as pq

from data_pipeline.text_ner.audit import audit_manifest
from data_pipeline.text_ner.manifest import prepare_manifest
from data_pipeline.text_ner.sections import split_radiology_sections


class TextNerManifestTest(unittest.TestCase):
    def test_radiology_sections_preserve_exact_spans(self) -> None:
        text = "Portable study.\n\nFINDINGS: No edema.\nIMPRESSION: No acute disease.\n"
        sections = split_radiology_sections(text)
        self.assertEqual([item.name for item in sections], ["preamble", "findings", "impression"])
        reconstructed = "".join(text[item.start : item.end] for item in sections)
        self.assertEqual(reconstructed, text)

    def _admission(self) -> dict[str, object]:
        return {
            "schema": {"name": "mimic_admission_raw", "version": "1.0.0"},
            "subject_id": "1",
            "hadm_id": "10",
            "mimic_iv_hosp": {
                "patients": [], "admissions": [], "labevents": [], "microbiologyevents": [],
                "poe": [], "poe_detail": [], "poe_timeline": [], "prescriptions": [],
                "pharmacy": [], "emar": [], "emar_detail": [], "diagnoses_icd": [],
                "hcpcsevents": [], "drgcodes": [], "services": [], "transfers": [],
                "procedures_icd": [],
            },
            "mimic_iv_icu": {
                "icustays": [], "datetimeevents": [], "procedureevents": [],
                "inputevents": [], "outputevents": [], "ingredientevents": [],
            },
            "mimic_iv_ed": {
                "edstays": [], "triage": [{"subject_id": "1", "stay_id": "2", "chiefcomplaint": "chest pain"}],
                "vitalsign": [], "diagnosis": [], "medrecon": [], "pyxis": [],
            },
            "mimic_iv_note": {
                "radiology": [
                    {
                        "subject_id": "1", "hadm_id": "10", "note_id": "R1", "note_type": "RR",
                        "note_seq": 1, "charttime": "2150-01-01 10:00:00",
                        "storetime": "2150-01-01 11:00:00",
                        "text": "  FINDINGS: No edema.\nIMPRESSION: Clear.\n\n",
                    }
                ],
                "radiology_detail": [],
                "discharge": [
                    {
                        "subject_id": "1", "hadm_id": "10", "note_id": "D1", "note_type": "DS",
                        "note_seq": 1, "charttime": "2150-01-02 10:00:00",
                        "storetime": "2150-01-02 12:00:00", "text": "Hospital course",
                    }
                ],
                "discharge_detail": [],
            },
        }

    def test_prepare_and_audit_without_raw_text_or_model_calls(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "sample.jsonl"
            source.write_text(json.dumps(self._admission()) + "\n", encoding="utf-8")
            first = root / "first"
            second = root / "second"
            prepare_manifest(source, first, pilot_size=2)
            prepare_manifest(source, second, pilot_size=2)
            report = audit_manifest(source, first, replay_directory=second)
            self.assertTrue(report["passed"])
            table = pq.read_table(first / "text_ner_input_manifest.parquet")
            self.assertNotIn("text", table.column_names)
            self.assertNotIn("chiefcomplaint", table.column_names)
            rows = table.to_pylist()
            radiology = [row for row in rows if row["source_table"] == "note.radiology"]
            expected_text = self._admission()["mimic_iv_note"]["radiology"][0]["text"]
            self.assertTrue(all(row["source_text_character_count"] == len(expected_text) for row in radiology))
            discharge = [row for row in rows if row["source_table"] == "note.discharge"]
            self.assertEqual(discharge[0]["reason_code"], "POST_HOC_DISCHARGE")
            self.assertFalse(discharge[0]["pilot_document_selected"])
            run = json.loads((first / "run_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(run["model"]["calls"], 0)

    def test_text_contract_does_not_require_derived_poe_timeline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            admission = self._admission()
            del admission["mimic_iv_hosp"]["poe_timeline"]
            source = root / "raw.jsonl"
            source.write_text(json.dumps(admission) + "\n", encoding="utf-8")
            prepare_manifest(source, root / "output", pilot_size=2)


if __name__ == "__main__":
    unittest.main()
