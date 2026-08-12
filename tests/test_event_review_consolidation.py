from __future__ import annotations

import unittest

from data_pipeline.event_pipeline.event_quality.consolidate_review import (
    PILOT_TARGETS,
    _mapping_signature,
    select_pilot_rows,
)


class ReviewConsolidationTest(unittest.TestCase):
    def _row(self, review_id: str, category: str, impact: int) -> dict:
        row = {
            "review_id": review_id,
            "entity_type": "coded_clinical_concept",
            "source_concept_id": f"code:{review_id}",
            "normalized_source_label": review_id,
            "concept_id": f"code:{review_id}",
            "preferred_name": review_id,
            "normalization_status": "mapped",
            "source_unit": None,
            "normalized_unit": None,
            "unit_normalization_status": "not_applicable",
            "mapping_rule": "source-code",
            "review_reasons": [],
            "event_count": impact,
            "batch_ids": ["batch-1"],
        }
        if category == "p0_text_rules":
            row.update(
                source_concept_id=None,
                concept_id="local:test",
                mapping_rule="reviewed-synonym",
                review_reasons=["REVIEWED_TEXT_RULE"],
            )
        elif category == "high_frequency_uncoded_medication":
            row.update(
                entity_type="medication",
                source_concept_id=None,
                concept_id=None,
                normalization_status="unresolved",
                mapping_rule="unresolved",
            )
        elif category == "general_orders":
            row.update(
                entity_type="clinical_order",
                source_concept_id=None,
                concept_id=None,
                normalization_status="unresolved",
                mapping_rule="unresolved",
            )
        elif category == "invalid_ndc_zero":
            row.update(
                entity_type="medication",
                source_concept_id="ndc:0",
                concept_id=None,
                normalization_status="unresolved",
                mapping_rule="invalid-source-code",
            )
        elif category == "unresolved_units":
            row.update(unit_normalization_status="unresolved")
        elif category == "category_only_unresolved":
            row.update(
                entity_type="medication_order_category",
                source_concept_id=None,
                concept_id=None,
                normalization_status="unresolved",
                mapping_rule="unresolved",
            )
        return row

    def test_pilot_selection_is_exact_exclusive_and_impact_ranked(self) -> None:
        rows = []
        expected_top_ids = {}
        for category, target, _label in PILOT_TARGETS:
            category_rows = [
                self._row(f"{category}-{index:02d}", category, 1000 - index)
                for index in range(target + 3)
            ]
            rows.extend(category_rows)
            expected_top_ids[category] = [
                row["review_id"] for row in category_rows[:target]
            ]
        evidence = {row["review_id"]: {"batch-1"} for row in rows}

        selected = select_pilot_rows(rows, evidence)

        self.assertEqual(selected, expected_top_ids)
        flattened = [review_id for values in selected.values() for review_id in values]
        self.assertEqual(len(flattened), 100)
        self.assertEqual(len(set(flattened)), 100)
        self.assertTrue(
            all(row["review_scope"] == "pilot" for row in rows if row["review_id"] in flattened)
        )

    def test_unresolved_display_case_is_not_a_mapping_conflict(self) -> None:
        left = {
            "concept_id": None,
            "preferred_name": "HydrALAzine",
            "normalization_status": "unresolved",
            "normalized_unit": None,
            "unit_normalization_status": "not_applicable",
            "mapping_rule": "unresolved",
        }
        right = {**left, "preferred_name": "HydrALAZINE"}
        changed = {**left, "concept_id": "rxnorm:123", "preferred_name": "Hydralazine"}

        self.assertEqual(_mapping_signature(left), _mapping_signature(right))
        self.assertNotEqual(_mapping_signature(left), _mapping_signature(changed))
        mapped_left = {
            **left,
            "concept_id": "ndc:123",
            "preferred_name": "Lorazepam",
            "normalization_status": "mapped",
            "mapping_rule": "source-code",
        }
        mapped_right = {**mapped_left, "preferred_name": "LORazepam"}
        mapped_different = {**mapped_left, "preferred_name": "Lorazepam injection"}
        self.assertEqual(
            _mapping_signature(mapped_left), _mapping_signature(mapped_right)
        )
        self.assertNotEqual(
            _mapping_signature(mapped_left), _mapping_signature(mapped_different)
        )


if __name__ == "__main__":
    unittest.main()
