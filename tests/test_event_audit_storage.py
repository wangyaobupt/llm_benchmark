from __future__ import annotations

import json
from pathlib import Path
import re
import tempfile
import unittest

from data_pipeline.event_pipeline.event_cleaning.ids import build_source_row_id
from data_pipeline.event_pipeline.event_cleaning.source_catalog import SOURCE_CATALOG
from data_pipeline.event_pipeline.event_quality.audit_storage import (
    AuditIndex,
    JsonlRecordStore,
    SourceIdentityResolver,
)


RAW_REF_RE = re.compile(
    r"(?P<filename>[^#]+)#L(?P<line>\d+)/"
    r"(?P<module>[^.]+)\.(?P<table>[^[]+)\[(?P<index>\d+)\]"
)


def _empty_admission() -> dict:
    admission = {
        "schema": {"name": "test", "version": "1"},
        "subject_id": "1",
        "hadm_id": "2",
    }
    for spec in SOURCE_CATALOG:
        admission.setdefault(spec.module, {})[spec.table] = []
    return admission


class EventAuditStorageTest(unittest.TestCase):
    def test_jsonl_store_uses_offsets_and_supports_random_lookup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.jsonl"
            path.write_bytes(
                json.dumps({"value": 1}).encode() + b"\n\n"
                + json.dumps({"value": 3}).encode() + b"\n"
            )
            with JsonlRecordStore(path) as records:
                self.assertEqual(len(records), 2)
                self.assertEqual(list(records), [1, 3])
                self.assertEqual(records.get(3), {"value": 3})
                self.assertEqual(records.get(1), {"value": 1})
                self.assertIsNone(records.get(2))
                self.assertEqual(list(records.items()), [(1, {"value": 1}), (3, {"value": 3})])

    def test_identity_resolver_preserves_duplicate_occurrence_ordinal(self) -> None:
        target = next(
            spec
            for spec in SOURCE_CATALOG
            if spec.identity_strategy == "canonical_row_hash_with_occurrence"
        )
        admission = _empty_admission()
        row = {"subject_id": "1", "hadm_id": "2", "value": "same"}
        admission[target.module][target.table] = [row, dict(row)]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "source.jsonl"
            path.write_text(json.dumps(admission) + "\n", encoding="utf-8")
            with JsonlRecordStore(path) as records:
                resolver = SourceIdentityResolver(records, path.name, RAW_REF_RE)
                first = f"{path.name}#L1/{target.module}.{target.table}[0]"
                second = f"{path.name}#L1/{target.module}.{target.table}[1]"
                self.assertEqual(
                    resolver[first],
                    build_source_row_id(target, row, duplicate_occurrence_ordinal=0),
                )
                self.assertEqual(
                    resolver[second],
                    build_source_row_id(target, row, duplicate_occurrence_ordinal=1),
                )
                self.assertNotEqual(resolver[first], resolver[second])

    def test_audit_index_reports_bulk_coverage_issues(self) -> None:
        event_table = next(spec.source_table for spec in SOURCE_CATALOG if spec.role == "event")
        support_table = next(spec.source_table for spec in SOURCE_CATALOG if spec.role == "support")
        with tempfile.TemporaryDirectory() as directory:
            with AuditIndex(Path(directory), batch_size=2) as index:
                index.add_event("event-1", event_table, "accepted")
                index.add_event("event-1", event_table, "wrong-count")
                index.add_rejected(event_table, "rejected")
                index.add_source(event_table, "accepted", "event", 1)
                index.add_source(event_table, "rejected", "event", 0)
                index.add_source(event_table, "unclassified", "event", 0)
                index.add_source(event_table, "wrong-count", "event", 2)
                index.add_source(support_table, "unlinked", "support", 0)
                result = index.analyze()
            self.assertEqual(result["duplicate_event_ids"], 1)
            self.assertEqual(
                result["issues"]["source_row_classification_mismatch"][0], 1
            )
            self.assertEqual(
                result["issues"]["supporting_source_row_unlinked"][0], 1
            )
            self.assertEqual(
                result["issues"]["source_row_event_count_mismatch"][0], 1
            )


if __name__ == "__main__":
    unittest.main()
