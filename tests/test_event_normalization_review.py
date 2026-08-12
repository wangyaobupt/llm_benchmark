from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import pyarrow as pa
import pyarrow.parquet as pq

from data_pipeline.event_pipeline.event_cleaning.validation import EventPipelineError
from data_pipeline.event_pipeline.event_contracts.schemas import (
    EVENT_ARROW_SCHEMA,
    MAPPING_ARROW_SCHEMA,
    REVIEW_ARROW_SCHEMA,
    TERM_INVENTORY_ARROW_SCHEMA,
)
from data_pipeline.event_pipeline.event_normalization.io import sha256_file
from data_pipeline.event_pipeline.event_quality.review_normalization import (
    generate_review_package,
)


class NormalizationReviewTest(unittest.TestCase):
    def _event(self, event_id: str, *, mapped: bool) -> tuple[dict, dict]:
        cleaned = {name: None for name in EVENT_ARROW_SCHEMA.names}
        cleaned.update(
            {
                "schema_version": "1.2.0",
                "cleaning_status": "accepted",
                "event_id": event_id,
                "source_row_id": f"source-{event_id}",
                "subject_id": "1",
                "hadm_id": "10",
                "event_kind": "laboratory_resulted",
                "source_table": "hosp.labevents",
                "raw_row_ref": f"source.jsonl#L1/mimic_iv_hosp.labevents[{event_id[-1]}]",
                "entity_type": "laboratory_test",
                "source_concept_id": "loinc:1" if mapped else None,
                "source_label": "Known test" if mapped else "Mystery test",
                "content_specificity": "entity_specific",
                "value_numeric": 1.0,
                "unit": "mg/dL" if mapped else None,
                "quality_flags": [],
                "supporting_source_row_ids": [],
                "supporting_raw_row_refs": [],
                "time_resolution_reasons": [],
            }
        )
        normalized = dict(cleaned)
        normalized.update(
            {
                "concept_id": "loinc:1" if mapped else None,
                "preferred_name": "Known test" if mapped else "Mystery test",
                "normalization_status": "mapped" if mapped else "unresolved",
                "terminology_mapping_version": "event-terminology/1.1.0",
                "normalized_value_numeric": 1.0,
                "normalized_unit": "mg/dL" if mapped else None,
                "unit_normalization_status": "mapped" if mapped else "not_applicable",
            }
        )
        return cleaned, normalized

    def _write_fixture(self, root: Path) -> None:
        cleaning = root / "cleaning"
        normalization = root / "normalization"
        quality = root / "quality"
        cleaning.mkdir(parents=True)
        normalization.mkdir()
        quality.mkdir()

        cleaned_rows = []
        normalized_rows = []
        for event_id, mapped in (("event-1", True), ("event-2", False)):
            cleaned, normalized = self._event(event_id, mapped=mapped)
            cleaned_rows.append(cleaned)
            normalized_rows.append(normalized)
        inventory = [
            {
                "schema_version": "1.0.0",
                "entity_type": "laboratory_test",
                "source_concept_id": "loinc:1",
                "normalized_source_label": "known test",
                "source_label_example": "Known test",
                "unit": "mg/dL",
                "event_count": 1,
                "first_event_id": "event-1",
            },
            {
                "schema_version": "1.0.0",
                "entity_type": "laboratory_test",
                "source_concept_id": None,
                "normalized_source_label": "mystery test",
                "source_label_example": "Mystery test",
                "unit": None,
                "event_count": 1,
                "first_event_id": "event-2",
            },
        ]
        mappings = [
            {
                "schema_version": "1.0.0",
                "entity_type": "laboratory_test",
                "source_concept_id": "loinc:1",
                "normalized_source_label": "known test",
                "source_label_example": "Known test",
                "concept_id": "loinc:1",
                "preferred_name": "Known test",
                "normalization_status": "mapped",
                "source_unit": "mg/dL",
                "normalized_unit": "mg/dL",
                "unit_normalization_status": "mapped",
                "mapping_rule": "source-code",
                "mapping_version": "event-terminology/1.1.0",
                "event_count": 1,
            },
            {
                "schema_version": "1.0.0",
                "entity_type": "laboratory_test",
                "source_concept_id": None,
                "normalized_source_label": "mystery test",
                "source_label_example": "Mystery test",
                "concept_id": None,
                "preferred_name": "Mystery test",
                "normalization_status": "unresolved",
                "source_unit": None,
                "normalized_unit": None,
                "unit_normalization_status": "not_applicable",
                "mapping_rule": "unresolved",
                "mapping_version": "event-terminology/1.1.0",
                "event_count": 1,
            },
        ]
        review = [
            {
                "schema_version": "1.0.0",
                "entity_type": "laboratory_test",
                "source_concept_id": None,
                "normalized_source_label": "mystery test",
                "source_label_example": "Mystery test",
                "unit": None,
                "normalized_unit": None,
                "unit_normalization_status": "not_applicable",
                "review_reason": "TERM_UNRESOLVED",
                "event_count": 1,
                "first_event_id": "event-2",
                "mapping_version": "event-terminology/1.1.0",
            }
        ]
        pq.write_table(
            pa.Table.from_pylist(cleaned_rows, schema=EVENT_ARROW_SCHEMA),
            cleaning / "cleaned_events.parquet",
        )
        pq.write_table(
            pa.Table.from_pylist(inventory, schema=TERM_INVENTORY_ARROW_SCHEMA),
            cleaning / "term_inventory.parquet",
        )
        pq.write_table(
            pa.Table.from_pylist(normalized_rows, schema=EVENT_ARROW_SCHEMA),
            normalization / "normalized_events.parquet",
        )
        pq.write_table(
            pa.Table.from_pylist(mappings, schema=MAPPING_ARROW_SCHEMA),
            normalization / "normalization_mappings.parquet",
        )
        pq.write_table(
            pa.Table.from_pylist(review, schema=REVIEW_ARROW_SCHEMA),
            normalization / "normalization_review_queue.parquet",
        )

        files = {
            "cleaned_events.parquet": cleaning / "cleaned_events.parquet",
            "term_inventory.parquet": cleaning / "term_inventory.parquet",
            "normalized_events.parquet": normalization
            / "normalized_events.parquet",
            "normalization_mappings.parquet": normalization
            / "normalization_mappings.parquet",
            "normalization_review_queue.parquet": normalization
            / "normalization_review_queue.parquet",
        }
        hashes = {name: sha256_file(path) for name, path in files.items()}
        manifest = {
            "run_id": "normalization-run",
            "inputs": {
                "cleaned_events_sha256": hashes["cleaned_events.parquet"],
                "term_inventory_sha256": hashes["term_inventory.parquet"],
            },
            "output_sha256": {
                name: hashes[name]
                for name in (
                    "normalized_events.parquet",
                    "normalization_mappings.parquet",
                    "normalization_review_queue.parquet",
                )
            },
        }
        (normalization / "normalization_manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        audit = {
            "hashes": hashes,
            "issues": {"counts": {}},
            "event_invariants": {
                "same_row_count": True,
                "event_id_sequence_equal": True,
            },
            "acceptance": {"can_publish_normalization": True},
        }
        (quality / "normalized-events-acceptance-audit.json").write_text(
            json.dumps(audit), encoding="utf-8"
        )
        (root / "workflow_manifest.json").write_text(
            json.dumps(
                {
                    "run_id": "workflow-run",
                    "acceptance": {
                        "cleaning": True,
                        "normalization": True,
                        "reproducible": True,
                    },
                }
            ),
            encoding="utf-8",
        )

    def test_generates_deterministic_review_package_and_blocks_stale_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "event-output"
            self._write_fixture(root)
            summary = generate_review_package(
                root,
                samples_per_stratum=1,
                top_mappings_per_entity=1,
            )
            self.assertTrue(summary["acceptance"]["automated_review_passed"])
            self.assertFalse(summary["acceptance"]["human_review_complete"])
            self.assertTrue(summary["hard_gates"]["sanity:category_only_event_mapped"])
            self.assertEqual(
                summary["sanity_issue_counts"]["category_only_event_mapped"], 0
            )
            self.assertEqual(summary["counts"]["required_review_rows"], 1)
            self.assertEqual(summary["counts"]["sampled_review_rows"], 1)
            self.assertEqual(summary["counts"]["event_samples"], 2)
            review_directory = root / "review"
            self.assertTrue(
                (review_directory / "normalization_review_summary.json").is_file()
            )
            decisions = pq.read_table(
                review_directory / "normalization_review_decisions.parquet"
            ).to_pylist()
            self.assertEqual([row["priority_rank"] for row in decisions], [1, 2])
            self.assertEqual(decisions[0]["review_status"], "pending")

            manifest_path = root / "normalization" / "normalization_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["inputs"]["cleaned_events_sha256"] = "stale"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaises(EventPipelineError) as context:
                generate_review_package(root, root / "second-review")
            self.assertEqual(
                context.exception.reason_code, "NORMALIZATION_REVIEW_GATE_FAILED"
            )


if __name__ == "__main__":
    unittest.main()
