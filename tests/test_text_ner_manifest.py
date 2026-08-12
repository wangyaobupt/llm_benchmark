from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import pyarrow.parquet as pq

from data_pipeline.text_ner.annotation_contracts import (
    ANNOTATION_QUALITY_FLAGS,
    ASSERTION_VALUES,
    ENTITY_TYPES,
    RELATION_TYPES,
    SECTION_ANNOTATION_SCHEMA_VERSION,
)
from data_pipeline.text_ner.annotation_validation import (
    AnnotationValidationError,
    ANNOTATION_SCHEMA_PATH,
    SectionAnnotationValidator,
)
from data_pipeline.text_ner.audit import audit_manifest
from data_pipeline.text_ner.manifest import prepare_manifest
from data_pipeline.text_ner.scope_rehearsal import rehearse_scope
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

    def test_annotation_schema_enums_match_python_contract(self) -> None:
        schema = json.loads(ANNOTATION_SCHEMA_PATH.read_text(encoding="utf-8"))
        mention = schema["$defs"]["mention"]["properties"]
        relation = schema["$defs"]["relation"]["properties"]
        self.assertEqual(tuple(mention["entity_type"]["enum"]), ENTITY_TYPES)
        self.assertEqual(tuple(mention["assertion"]["enum"]), ASSERTION_VALUES)
        self.assertEqual(tuple(relation["relation_type"]["enum"]), RELATION_TYPES)
        self.assertEqual(
            tuple(mention["quality_flags"]["items"]["enum"]),
            ANNOTATION_QUALITY_FLAGS,
        )
        self.assertEqual(
            tuple(relation["quality_flags"]["items"]["enum"]),
            ANNOTATION_QUALITY_FLAGS,
        )

    def test_annotation_validator_requires_exact_spans_and_explicit_relation_evidence(self) -> None:
        text = "Opacity in the left lung."
        manifest_row = {
            "manifest_row_id": "row1",
            "document_id": "doc1",
            "section_id": "sec1",
            "span_sha256": __import__("hashlib").sha256(text.encode()).hexdigest(),
        }
        annotation = {
            "schema_version": SECTION_ANNOTATION_SCHEMA_VERSION,
            "manifest_row_id": "row1",
            "document_id": "doc1",
            "section_id": "sec1",
            "section_text_sha256": manifest_row["span_sha256"],
            "mentions": [
                {
                    "local_id": "m1", "surface_text": "Opacity",
                    "section_span_start": 0, "section_span_end": 7,
                    "entity_type": "imaging_finding", "assertion": "present",
                    "temporality": "current", "experiencer": "patient",
                    "laterality": "not_stated", "severity": "not_stated",
                    "trend": "not_stated", "normalization_status": "unattempted",
                    "concept_id": None, "preferred_name": None, "terminology": None,
                    "quality_flags": [],
                },
                {
                    "local_id": "m2", "surface_text": "left lung",
                    "section_span_start": 15, "section_span_end": 24,
                    "entity_type": "anatomical_site", "assertion": "present",
                    "temporality": "current", "experiencer": "patient",
                    "laterality": "left", "severity": "not_applicable",
                    "trend": "not_applicable", "normalization_status": "unattempted",
                    "concept_id": None, "preferred_name": None, "terminology": None,
                    "quality_flags": [],
                },
            ],
            "relations": [
                {
                    "local_id": "r1", "source_mention_id": "m1",
                    "target_mention_id": "m2", "relation_type": "located_at",
                    "evidence_text": text[:24], "section_evidence_start": 0,
                    "section_evidence_end": 24, "relation_basis": "text_explicit",
                    "quality_flags": [],
                }
            ],
        }
        validator = SectionAnnotationValidator()
        validator.validate(annotation, manifest_row, text)
        annotation["mentions"][0]["surface_text"] = "opacity"
        with self.assertRaisesRegex(AnnotationValidationError, "MENTION_SURFACE_MISMATCH"):
            validator.validate(annotation, manifest_row, text)

    def test_scope_rehearsal_writes_only_aggregate_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "sample.jsonl"
            source.write_text(json.dumps(self._admission()) + "\n", encoding="utf-8")
            output = root / "manifest"
            prepare_manifest(source, output, pilot_size=2)
            report = rehearse_scope(
                source,
                output / "text_ner_input_manifest.parquet",
                expected_pilot_documents=2,
            )
            self.assertTrue(report["passed"])
            self.assertFalse(report["checks"]["raw_text_written"])
            self.assertEqual(report["checks"]["model_calls"], 0)


if __name__ == "__main__":
    unittest.main()
