from __future__ import annotations

import unittest

from data_pipeline.event_pipeline.event_normalization.terminology import (
    MAPPING_VERSION,
    resolve_term,
    resolve_unit,
)


class EventTerminologyTest(unittest.TestCase):
    def test_structured_codes_require_usable_native_identifier(self) -> None:
        valid_ndc = resolve_term("medication", "ndc:00002751001", "Insulin")
        self.assertEqual(valid_ndc["concept_id"], "ndc:00002751001")
        self.assertEqual(valid_ndc["normalization_status"], "mapped")

        for invalid_code in (
            "ndc:0",
            "ndc:00000000000",
            "gsn:027413 001723",
        ):
            with self.subTest(invalid_code=invalid_code):
                resolution = resolve_term("medication", invalid_code, "Drug")
                self.assertIsNone(resolution["concept_id"])
                self.assertEqual(resolution["normalization_status"], "unresolved")
                self.assertEqual(resolution["mapping_rule"], "invalid-source-code")

    def test_frozen_units_map_only_explicit_aliases(self) -> None:
        expected = {
            "mL": "mL",
            "sec": "s",
            "mm Hg": "mmHg",
            "grams": "g",
            "mEq.": "mEq",
            "mm/hr": "mm/h",
        }
        for source, normalized in expected.items():
            with self.subTest(source=source):
                self.assertEqual(resolve_unit(source), (normalized, "mapped"))
        self.assertEqual(resolve_unit("N/A"), (None, "not_applicable"))
        self.assertEqual(resolve_unit("dose"), (None, "unresolved"))

    def test_rule_change_has_new_mapping_version(self) -> None:
        self.assertEqual(MAPPING_VERSION, "event-terminology/1.1.0")


if __name__ == "__main__":
    unittest.main()
