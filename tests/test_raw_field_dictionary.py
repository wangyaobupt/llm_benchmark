from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from eda.analysis.build_raw_field_dictionary import build_outputs
from data_pipeline.mimic_raw_archive.catalog import (
    ARCHIVE_SOURCES,
    REFERENCE_SOURCE_KEYS,
)
from data_pipeline.mimic_raw_archive.field_dictionary import (
    build_field_dictionary,
    validate_dictionary,
)


class RawFieldDictionaryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.reference_root = Path("docs/reference/mimic_reference")
        cls.rows = build_field_dictionary(cls.reference_root)

    def test_dictionary_exactly_covers_frozen_headers(self) -> None:
        validate_dictionary(self.rows)
        archive = [row for row in self.rows if row["scope"] == "archive"]
        self.assertEqual(len(archive), 380)
        self.assertEqual(len({(row["module"], row["table"]) for row in archive}), 32)
        self.assertEqual(
            {row["json_path"] for row in archive},
            {
                f"{source.module}.{source.output_key}[].{field}"
                for source in ARCHIVE_SOURCES for field in source.source.header
            },
        )

    def test_top_level_and_external_references_are_documented(self) -> None:
        self.assertEqual(sum(row["scope"] == "top_level" for row in self.rows), 7)
        external = [row for row in self.rows if row["scope"] == "external_reference"]
        self.assertEqual(len({row["table"] for row in external}), len(REFERENCE_SOURCE_KEYS))
        self.assertTrue(all(row["description_zh"] for row in self.rows))

    def test_leakage_sensitive_fields_are_explicit(self) -> None:
        by_path = {row["json_path"]: row for row in self.rows}
        self.assertTrue(by_path["mimic_iv_hosp.diagnoses_icd[].icd_code"]["information_phase"].startswith("post_hoc"))
        self.assertTrue(by_path["mimic_iv_note.discharge[].text"]["information_phase"].startswith("post_hoc"))
        self.assertTrue(by_path["mimic_iv_ed.diagnosis[].icd_code"]["information_phase"].startswith("post_hoc"))
        self.assertTrue(by_path["mimic_iv_hosp.admissions[].discharge_location"]["information_phase"].startswith("administrative_end"))
        self.assertTrue(by_path["mimic_iv_ed.edstays[].disposition"]["information_phase"].startswith("clinical_end"))
        self.assertIn("recorded/available", by_path["mimic_iv_hosp.labevents[].storetime"]["time_semantics"])

    def test_generated_outputs_are_machine_and_human_readable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            markdown = Path(directory) / "dictionary.md"
            json_path = Path(directory) / "dictionary.json"
            build_outputs(self.reference_root, markdown, json_path)
            text = markdown.read_text(encoding="utf-8")
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        self.assertIn("JSONL内32张源表字段", text)
        self.assertIn("mimic_iv_hosp.emar_detail[].dose_given", text)
        self.assertEqual(len(payload["fields"]), len(self.rows))


if __name__ == "__main__":
    unittest.main()
