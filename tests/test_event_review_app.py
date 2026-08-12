from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import pyarrow as pa
import pyarrow.parquet as pq

from data_pipeline.event_pipeline.event_quality.review_normalization import (
    DECISION_SCHEMA,
    SAMPLE_SCHEMA,
)
from data_pipeline.event_pipeline.event_quality.consolidate_review import (
    MASTER_DECISION_SCHEMA,
    MASTER_SAMPLE_SCHEMA,
)
from data_pipeline.event_pipeline.event_viewer.review_app import ReviewStore


class ReviewAppTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.event_directory = self.root / "event-output"
        self.review_directory = self.event_directory / "review"
        cleaning = self.event_directory / "cleaning"
        self.review_directory.mkdir(parents=True)
        cleaning.mkdir()
        self.source = self.root / "source.jsonl"
        self.source.write_text(
            json.dumps(
                {
                    "mimic_iv_ed": {
                        "triage": [
                            {"subject_id": "1", "chiefcomplaint": "Chest pain"}
                        ]
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (cleaning / "run_manifest.json").write_text(
            json.dumps({"input": {"filename": self.source.name}}),
            encoding="utf-8",
        )
        review_id = "mapping-review-1"
        decision = {name: None for name in DECISION_SCHEMA.names}
        decision.update(
            {
                "review_id": review_id,
                "priority_rank": 0,
                "review_scope": "required",
                "review_reasons": ["REVIEWED_TEXT_RULE"],
                "entity_type": "symptom",
                "normalized_source_label": "chest pain",
                "source_label_example": "Chest pain",
                "concept_id": "symptom:chest_pain",
                "preferred_name": "Chest pain",
                "normalization_status": "mapped",
                "unit_normalization_status": "not_applicable",
                "mapping_rule": "reviewed-synonym",
                "mapping_version": "event-terminology/1.1.0",
                "event_count": 10,
                "first_event_id": "event-1",
                "review_status": "pending",
            }
        )
        sample = {name: None for name in SAMPLE_SCHEMA.names}
        sample.update(
            {
                "review_sample_id": "sample-1",
                "mapping_review_id": review_id,
                "sample_reasons": ["REVIEWED_TEXT_RULE"],
                "event_id": "event-1",
                "subject_id": "1",
                "hadm_id": "10",
                "source_table": "ed.triage",
                "event_kind": "symptom_reported",
                "entity_type": "symptom",
                "raw_row_ref": "source.jsonl#L1/mimic_iv_ed.triage[0]",
                "source_label": "Chest pain",
                "concept_id": "symptom:chest_pain",
                "preferred_name": "Chest pain",
                "normalization_status": "mapped",
                "mapping_rule": "reviewed-synonym",
                "content_specificity": "entity_specific",
                "quality_flags": [],
            }
        )
        pq.write_table(
            pa.Table.from_pylist([decision], schema=DECISION_SCHEMA),
            self.review_directory / "normalization_review_decisions.parquet",
        )
        pq.write_table(
            pa.Table.from_pylist([sample], schema=SAMPLE_SCHEMA),
            self.review_directory / "normalization_review_samples.parquet",
        )
        (self.review_directory / "normalization_review_summary.json").write_text(
            json.dumps(
                {
                    "review_run_id": "review-run",
                    "counts": {
                        "normalized_events": 10,
                        "mapping_rows": 1,
                        "required_review_rows": 1,
                        "sampled_review_rows": 0,
                        "event_samples": 1,
                    },
                    "normalization_status_counts": {
                        "mapped": 10,
                        "unresolved": 0,
                    },
                    "acceptance": {"automated_review_passed": True},
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_query_raw_lookup_and_append_only_decisions_persist(self) -> None:
        store = ReviewStore(self.review_directory)
        try:
            self.assertEqual(store.summary()["review_ui"]["remaining_human_decisions"], 1)
            rows = store.query_decisions(priority_rank="0")
            self.assertEqual(rows["total"], 1)
            detail = store.detail("mapping-review-1")
            self.assertEqual(detail["samples"][0]["event_id"], "event-1")
            source = store.source_row(detail["samples"][0]["raw_row_ref"])
            self.assertEqual(source["source_row"]["chiefcomplaint"], "Chest pain")
            annotation = store.save_annotation(
                {
                    "review_id": "mapping-review-1",
                    "decision": "accepted",
                    "reviewer": "tester",
                    "review_comment": "raw source agrees",
                }
            )
            self.assertEqual(annotation["decision"], "accepted")
            self.assertEqual(
                store.query_decisions(current_status="accepted")["total"], 1
            )
        finally:
            store.close()

        reopened = ReviewStore(self.review_directory)
        try:
            summary = reopened.summary()["review_ui"]
            self.assertEqual(summary["annotation_count"], 1)
            self.assertEqual(summary["remaining_human_decisions"], 0)
            history = reopened.detail("mapping-review-1")["annotation_history"]
            self.assertEqual(len(history), 1)
        finally:
            reopened.close()

    def test_rejects_invalid_decision_and_unknown_review_id(self) -> None:
        store = ReviewStore(self.review_directory)
        try:
            with self.assertRaises(ValueError):
                store.save_annotation(
                    {
                        "review_id": "mapping-review-1",
                        "decision": "approved",
                        "reviewer": "tester",
                    }
                )
            with self.assertRaises(KeyError):
                store.save_annotation(
                    {
                        "review_id": "missing",
                        "decision": "accepted",
                        "reviewer": "tester",
                    }
                )
        finally:
            store.close()


class MasterReviewAppTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.review_directory = self.root / "master-review"
        self.review_directory.mkdir()
        batches = []
        for batch_id, complaint in (("batch-1", "Chest pain"), ("batch-2", "Dyspnea")):
            source_directory = self.root / batch_id
            source_directory.mkdir()
            source = source_directory / "source.jsonl"
            source.write_text(
                json.dumps(
                    {
                        "mimic_iv_ed": {
                            "triage": [
                                {"subject_id": batch_id, "chiefcomplaint": complaint}
                            ]
                        }
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            batches.append({"batch_id": batch_id, "source_jsonl": str(source)})

        decision = {name: None for name in MASTER_DECISION_SCHEMA.names}
        decision.update(
            {
                "review_id": "mapping-master-1",
                "priority_rank": 0,
                "review_scope": "pilot",
                "review_reasons": ["REVIEWED_TEXT_RULE"],
                "entity_type": "symptom",
                "normalized_source_label": "chest pain",
                "source_label_example": "Chest pain",
                "concept_id": "symptom:chest_pain",
                "preferred_name": "Chest pain",
                "normalization_status": "mapped",
                "unit_normalization_status": "not_applicable",
                "mapping_rule": "reviewed-synonym",
                "mapping_version": "event-terminology/1.1.0",
                "event_count": 20,
                "first_event_id": "event-1",
                "review_status": "pending",
                "pilot_category": "p0_text_rules",
                "pilot_category_rank": 0,
                "batch_count": 2,
                "batch_ids": ["batch-1", "batch-2"],
                "batch_event_counts_json": '{"batch-1": 10, "batch-2": 10}',
                "batch_first_event_ids_json": '{"batch-1": "event-1", "batch-2": "event-2"}',
                "source_label_examples": ["Chest pain"],
            }
        )
        samples = []
        for batch_id, event_id in (("batch-1", "event-1"), ("batch-2", "event-2")):
            sample = {name: None for name in MASTER_SAMPLE_SCHEMA.names}
            sample.update(
                {
                    "batch_id": batch_id,
                    "review_sample_id": f"sample-{batch_id}",
                    "mapping_review_id": "mapping-master-1",
                    "sample_reasons": ["REVIEWED_TEXT_RULE"],
                    "event_id": event_id,
                    "subject_id": batch_id,
                    "hadm_id": "10",
                    "source_table": "ed.triage",
                    "event_kind": "symptom_reported",
                    "entity_type": "symptom",
                    "raw_row_ref": "source.jsonl#L1/mimic_iv_ed.triage[0]",
                    "source_label": "Chest pain",
                    "concept_id": "symptom:chest_pain",
                    "preferred_name": "Chest pain",
                    "normalization_status": "mapped",
                    "mapping_rule": "reviewed-synonym",
                    "content_specificity": "entity_specific",
                    "quality_flags": [],
                }
            )
            samples.append(sample)
        pq.write_table(
            pa.Table.from_pylist([decision], schema=MASTER_DECISION_SCHEMA),
            self.review_directory / "consolidated_review_decisions.parquet",
        )
        pq.write_table(
            pa.Table.from_pylist(samples, schema=MASTER_SAMPLE_SCHEMA),
            self.review_directory / "cross_batch_evidence_samples.parquet",
        )
        (self.review_directory / "review_summary.json").write_text(
            json.dumps(
                {
                    "review_run_id": "master-run",
                    "inputs": {"batches": batches},
                    "counts": {
                        "normalized_events": 20,
                        "mapping_rows": 1,
                        "unique_mapping_rows": 1,
                        "pilot_review_rows": 1,
                        "event_samples": 2,
                    },
                    "normalization_status_counts": {"mapped": 20},
                    "acceptance": {"ready_for_human_review": True},
                    "decision_taxonomy": {
                        "allowed": [
                            "accepted_mapped",
                            "accepted_unresolved",
                            "deterministic_correction",
                            "needs_external_evidence",
                            "source_defect",
                        ],
                        "completed": [
                            "accepted_mapped",
                            "accepted_unresolved",
                            "deterministic_correction",
                            "source_defect",
                        ],
                        "comment_required": [
                            "deterministic_correction",
                            "needs_external_evidence",
                            "source_defect",
                        ],
                        "correction_concept_or_unit_required": [
                            "deterministic_correction"
                        ],
                    },
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_multi_batch_lookup_and_master_taxonomy(self) -> None:
        store = ReviewStore(self.review_directory)
        try:
            detail = store.detail("mapping-master-1")
            self.assertEqual([row["batch_id"] for row in detail["samples"]], ["batch-1", "batch-2"])
            source = store.source_row(detail["samples"][1]["raw_row_ref"], "batch-2")
            self.assertEqual(source["source_row"]["chiefcomplaint"], "Dyspnea")
            with self.assertRaises(ValueError):
                store.source_row(detail["samples"][0]["raw_row_ref"])
            with self.assertRaises(ValueError):
                store.save_annotation(
                    {
                        "review_id": "mapping-master-1",
                        "decision": "accepted_unresolved",
                        "reviewer": "tester",
                    }
                )
            correction = store.save_annotation(
                {
                    "review_id": "mapping-master-1",
                    "decision": "deterministic_correction",
                    "corrected_normalized_unit": "mg/dL",
                    "reviewer": "tester",
                    "review_comment": "unit alias evidence",
                }
            )
            self.assertEqual(correction["corrected_normalized_unit"], "mg/dL")
            annotation = store.save_annotation(
                {
                    "review_id": "mapping-master-1",
                    "decision": "accepted_mapped",
                    "reviewer": "tester",
                }
            )
            self.assertEqual(annotation["decision"], "accepted_mapped")
            self.assertEqual(store.summary()["review_ui"]["remaining_human_decisions"], 0)
        finally:
            store.close()


if __name__ == "__main__":
    unittest.main()
