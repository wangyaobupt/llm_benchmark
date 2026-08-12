from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from data_pipeline.text_ner.annotation_app import (
    INDEX_HTML,
    ReviewAccessError,
    ReviewStore,
    browser_utf16_offset_to_python,
    create_server,
)
from data_pipeline.text_ner.annotation_contracts import (
    ANNOTATION_PROTOCOL_VERSION,
    SECTION_ANNOTATION_SCHEMA_VERSION,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


class TextNerReviewStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.package = Path(self.temporary.name) / "package"
        self.text = "A😀\r\npain at left chest."
        digest = hashlib.sha256(self.text.encode("utf-8")).hexdigest()
        base = {
            "package_schema_version": "text-ner-human-annotation-package/1.0.0",
            "annotation_protocol_version": ANNOTATION_PROTOCOL_VERSION,
            "annotation_unit_id": "aunit:test",
            "partition": "calibration",
            "release_status": "released",
            "manifest_row_id": "mrow:test",
            "document_id": "doc:test",
            "section_id": "section:test",
            "source_table": "note.radiology",
            "note_type": "radiology",
            "section_name": "findings",
            "event_time": "2026-01-01T00:00:00Z",
            "available_time": "2026-01-01T00:01:00Z",
            "evidence_phase": "during_encounter",
            "section_text": self.text,
            "section_text_sha256": digest,
            "annotation": {
                "schema_version": SECTION_ANNOTATION_SCHEMA_VERSION,
                "manifest_row_id": "mrow:test",
                "document_id": "doc:test",
                "section_id": "section:test",
                "section_text_sha256": digest,
                "mentions": [],
                "relations": [],
            },
        }
        for role in ("annotator_a", "annotator_b"):
            task = dict(base, task_id=f"task:{role}", annotator_slot=role)
            _write_jsonl(
                self.package / "calibration" / role / "tasks.jsonl", [task]
            )
        evaluation = dict(
            base,
            task_id="task:evaluation",
            annotation_unit_id="aunit:evaluation",
            annotator_slot=None,
            partition="evaluation",
            release_status="blocked_pending_calibration",
        )
        _write_jsonl(
            self.package / "evaluation" / "tasks.locked.jsonl", [evaluation]
        )
        for name in ("annotator_a", "annotator_b", "adjudication"):
            _write_jsonl(self.package / "decisions" / f"{name}.jsonl", [])
        for name in ("annotator_a", "annotator_b", "adjudicated"):
            (self.package / "annotations" / name).mkdir(parents=True)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def annotation(self) -> dict:
        annotation = ReviewStore(self.package, "annotator_a").task_detail(
            "aunit:test"
        )["task"]["annotation"]
        annotation = json.loads(json.dumps(annotation))
        annotation["mentions"] = [
            {
                "local_id": "m1",
                "surface_text": "pain",
                "section_span_start": 4,
                "section_span_end": 8,
                "entity_type": "symptom_or_sign",
                "assertion": "present",
                "temporality": "current",
                "experiencer": "patient",
                "laterality": "not_stated",
                "severity": "not_stated",
                "trend": "not_stated",
                "normalization_status": "unattempted",
                "concept_id": None,
                "preferred_name": None,
                "terminology": None,
                "quality_flags": [],
            },
            {
                "local_id": "m2",
                "surface_text": "left chest",
                "section_span_start": 12,
                "section_span_end": 22,
                "entity_type": "anatomical_site",
                "assertion": "present",
                "temporality": "current",
                "experiencer": "patient",
                "laterality": "left",
                "severity": "not_applicable",
                "trend": "not_applicable",
                "normalization_status": "unattempted",
                "concept_id": None,
                "preferred_name": None,
                "terminology": None,
                "quality_flags": [],
            },
        ]
        annotation["relations"] = [
            {
                "local_id": "r1",
                "source_mention_id": "m1",
                "target_mention_id": "m2",
                "relation_type": "located_at",
                "evidence_text": "pain at left chest",
                "section_evidence_start": 4,
                "section_evidence_end": 22,
                "relation_basis": "text_explicit",
                "quality_flags": [],
            }
        ]
        return annotation

    def submit(self, role: str, annotator_id: str) -> dict:
        return ReviewStore(self.package, role).submit_decision(
            {
                "annotation_unit_id": "aunit:test",
                "annotator_id": annotator_id,
                "decision": "accept",
                "annotation": self.annotation(),
                "reason_codes": [],
                "comments": None,
                "input_decision_ids": [],
            }
        )

    def test_utf16_and_crlf_offsets_map_to_python_codepoints(self) -> None:
        browser_text = self.text.replace("\r\n", "\n")
        # Browser offset: A=1, emoji=2 UTF-16 units, LF=1 => pain starts at 4.
        self.assertEqual(
            browser_utf16_offset_to_python(self.text, browser_text, 4), 4
        )
        self.assertEqual(
            browser_utf16_offset_to_python(self.text, browser_text, 8), 8
        )
        with self.assertRaisesRegex(ValueError, "SPLITS_SURROGATE_PAIR"):
            browser_utf16_offset_to_python(self.text, browser_text, 2)

    def test_role_isolation_schema_validation_and_append_only_history(self) -> None:
        a = ReviewStore(self.package, "annotator_a")
        self.assertEqual(a.list_tasks()["role"], "annotator_a")
        self.assertNotIn("input_decisions", a.task_detail("aunit:test"))
        invalid = self.annotation()
        invalid["mentions"][0]["surface_text"] = "ache"
        with self.assertRaisesRegex(ValueError, "MENTION_SURFACE_MISMATCH"):
            a.submit_decision(
                {
                    "annotation_unit_id": "aunit:test",
                    "annotator_id": "a",
                    "decision": "accept",
                    "annotation": invalid,
                }
            )
        first = a.submit_decision(
            {
                "annotation_unit_id": "aunit:test",
                "annotator_id": "a",
                "decision": "accept",
                "annotation": self.annotation(),
                "reason_codes": [],
                "comments": None,
            }
        )
        second = a.submit_decision(
            {
                "annotation_unit_id": "aunit:test",
                "annotator_id": "a",
                "decision": "correct",
                "annotation": self.annotation(),
                "reason_codes": ["ATTRIBUTE_ERROR"],
                "comments": "second immutable record",
                "supersedes_decision_id": first["decision_id"],
            }
        )
        rows = _read_jsonl(self.package / "decisions" / "annotator_a.jsonl")
        self.assertEqual([row["decision_id"] for row in rows], [first["decision_id"], second["decision_id"]])
        self.assertNotEqual(first["annotation_payload_path"], second["annotation_payload_path"])
        self.assertEqual(
            _read_jsonl(self.package / "decisions" / "annotator_b.jsonl"), []
        )

    def test_adjudication_requires_one_decision_from_each_annotator(self) -> None:
        # Keep the adjudicator process alive while A/B submit; it must refresh
        # append-only logs at each request boundary.
        adjudicator = ReviewStore(self.package, "adjudicator")
        a = self.submit("annotator_a", "a")
        with self.assertRaisesRegex(ReviewAccessError, "REQUIRES_A_AND_B"):
            adjudicator.task_detail("aunit:test")
        b = self.submit("annotator_b", "b")
        detail = adjudicator.task_detail("aunit:test")
        self.assertEqual(
            {row["decision_id"] for row in detail["input_decisions"]},
            {a["decision_id"], b["decision_id"]},
        )
        second_a = ReviewStore(self.package, "annotator_a").submit_decision(
            {
                "annotation_unit_id": "aunit:test",
                "annotator_id": "a",
                "decision": "accept",
                "annotation": self.annotation(),
                "reason_codes": [],
                "comments": "second A decision",
                "supersedes_decision_id": a["decision_id"],
            }
        )
        with self.assertRaisesRegex(ValueError, "ONE_A_AND_ONE_B"):
            adjudicator.submit_decision(
                {
                    "annotation_unit_id": "aunit:test",
                    "annotator_id": "judge",
                    "decision": "correct",
                    "annotation": self.annotation(),
                    "input_decision_ids": [a["decision_id"], second_a["decision_id"]],
                }
            )
        result = adjudicator.submit_decision(
            {
                "annotation_unit_id": "aunit:test",
                "annotator_id": "judge",
                "decision": "correct",
                "annotation": self.annotation(),
                "reason_codes": ["RELATION_ERROR"],
                "comments": "resolved",
                "input_decision_ids": [a["decision_id"], b["decision_id"]],
            }
        )
        self.assertEqual(result["annotator_role"], "adjudicator")
        self.assertEqual(len(result["input_decision_ids"]), 2)

    def test_evaluation_is_locked_and_non_loopback_bind_is_rejected(self) -> None:
        store = ReviewStore(self.package, "annotator_a")
        with self.assertRaisesRegex(ReviewAccessError, "BLOCKED_PENDING_CALIBRATION"):
            store.open_evaluation_tasks()
        with self.assertRaisesRegex(ReviewAccessError, "LOOPBACK_ONLY"):
            create_server(self.package, "annotator_a", host="0.0.0.0", port=0)

    def test_ui_contains_codepoint_conversion_and_relation_editor(self) -> None:
        self.assertIn("domUtf16ToPython", INDEX_HTML)
        self.assertIn("replace(/\\r\\n?/g,'\\n')", INDEX_HTML)
        self.assertIn("captureEvidence", INDEX_HTML)
        self.assertIn("A/B 独立标注（裁决输入）", INDEX_HTML)
        self.assertIn("以此标注为裁决起点", INDEX_HTML)
        self.assertNotIn("https://", INDEX_HTML)


def _read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


if __name__ == "__main__":
    unittest.main()
