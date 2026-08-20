from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from data_pipeline.mcq_visit_standardize.context import build_context_index
from data_pipeline.mcq_visit_standardize.propose import build_proposals
from data_pipeline.mcq_visit_standardize.io import write_json_array
from data_pipeline.mcq_visit_standardize.review_app import HTML, ReviewStore
from data_pipeline.mcq_visit_standardize.symptoms import complaint_concepts
from data_pipeline.mcq_visit_standardize.synonyms import load_reviewed_synonyms
from data_pipeline.mcq_visit_standardize.text import lookup_key


class ReviewAppTests(unittest.TestCase):
    def test_html_is_review_not_question_ui(self) -> None:
        self.assertIn("原文", HTML)
        self.assertIn("建议改成", HTML)
        self.assertIn("改成上面内容并确认", HTML)
        self.assertIn("/api/decision", HTML)
        self.assertIn("不是出题", HTML)
        self.assertIn("上下文样例", HTML)
        self.assertIn("/api/context", HTML)
        self.assertIn("keepIndex", HTML)
        self.assertIn("nextIndex", HTML)
        self.assertIn("e.key==='d'||e.key==='D'", HTML)
        self.assertNotIn("e.key==='Enter'", HTML)

    def test_accept_writes_synonym_table_used_by_mapper(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            queue = root / "review_queue.jsonl"
            queue.write_text(
                json.dumps(
                    {
                        "domain": "symptom",
                        "field": "chief_complaint",
                        "source": "chest tightness on exertion",
                        "frequency": 9,
                        "status": "unresolved",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            store = ReviewStore(
                queue,
                root / "decisions.jsonl",
                root / "reviewed_synonyms.jsonl",
                None,
            )
            before = store.state("chief_complaint")
            self.assertEqual(before["stats"]["remaining"], 1)
            key = lookup_key("chest tightness on exertion")
            store.decide(
                {
                    "action": "accept",
                    "field": "chief_complaint",
                    "source": "chest tightness on exertion",
                    "lookup_key": key,
                    "standard": "Chest pain",
                    "concept_id": "symptom:chest_pain",
                    "frequency": 9,
                }
            )
            after = store.state("chief_complaint")
            self.assertEqual(after["stats"]["remaining"], 0)
            extra = load_reviewed_synonyms(root / "reviewed_synonyms.jsonl")
            concepts = complaint_concepts("chest tightness on exertion", extra_aliases=extra)
            self.assertEqual(concepts[0]["standard"], "Chest pain")
            self.assertEqual(concepts[0]["status"], "mapped/exact")

    def test_build_proposals_for_identity_and_exam_suffix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            queue = root / "q.jsonl"
            queue.write_text(
                json.dumps(
                    {
                        "domain": "symptom",
                        "field": "chief_complaint",
                        "source": "Dyspnea on exertion",
                        "frequency": 54,
                        "status": "unresolved",
                    }
                )
                + "\n"
                + json.dumps(
                    {
                        "domain": "unit",
                        "field": "lab.valueuom",
                        "source": "N/A",
                        "frequency": 10,
                        "status": "unresolved",
                    }
                )
                + "\n"
                + json.dumps(
                    {
                        "domain": "symptom",
                        "field": "chief_complaint",
                        "source": "B/L FOOT PAIN",
                        "frequency": 1,
                        "status": "unresolved",
                    }
                )
                + "\n"
                + json.dumps(
                    {
                        "domain": "symptom",
                        "field": "chief_complaint",
                        "source": "SBO",
                        "frequency": 17,
                        "status": "unresolved",
                    }
                )
                + "\n"
                + json.dumps(
                    {
                        "domain": "symptom",
                        "field": "chief_complaint",
                        "source": "CHEST PAIN (CARDIAC FEATURES)",
                        "frequency": 11,
                        "status": "unresolved",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            inventory = root / "inv.jsonl"
            inventory.write_text(
                json.dumps(
                    {
                        "field": "ed_chief_complaint",
                        "source": "Chest pain, Dyspnea",
                        "frequency": 22,
                    }
                )
                + "\n"
                + json.dumps(
                    {
                        "field": "ed_chief_complaint",
                        "source": "B/L FOOT PAIN",
                        "frequency": 1,
                    }
                )
                + "\n"
                + json.dumps(
                    {
                        "field": "radiology.exam_name",
                        "source": "CHEST (PA & LAT) PORT",
                        "frequency": 3,
                    }
                )
                + "\n"
                + json.dumps(
                    {
                        "field": "lab.label",
                        "source": "Mesothelial Cells",
                        "frequency": 77,
                    }
                )
                + "\n"
                + json.dumps(
                    {
                        "field": "lab.label",
                        "source": "Mesothelial cells",
                        "frequency": 22,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            rows = build_proposals(queue, inventory)
            actions = {(row["source"], row.get("proposed_standard") or row.get("proposed_action")) for row in rows}
            self.assertIn(("Dyspnea on exertion", "Dyspnea on exertion"), actions)
            self.assertNotIn("Chest pain, Dyspnea", {row["source"] for row in rows})
            self.assertNotIn(("Chest pain, Dyspnea", "Chest pain, dyspnea"), actions)
            self.assertIn(("B/L FOOT PAIN", "Bilateral foot pain"), actions)
            self.assertIn(("SBO", "Small bowel obstruction"), actions)
            self.assertIn(("CHEST PAIN (CARDIAC FEATURES)", "Chest pain (cardiac features)"), actions)
            self.assertIn(("N/A", "not_applicable"), actions)
            self.assertIn(("CHEST (PA & LAT) PORT", "Chest X-ray, PA and Lateral Views"), actions)
            self.assertIn(("Mesothelial cells", "Mesothelial Cells"), actions)

    def test_low_frequency_short_complaint_is_proposed(self) -> None:
        from data_pipeline.mcq_visit_standardize.propose import propose_symptom
        from data_pipeline.mcq_visit_standardize.symptoms import _alias_table

        catalog = _alias_table(None)
        row = {
            "domain": "symptom",
            "field": "chief_complaint",
            "source": "Pelvic pain",
            "frequency": 1,
        }
        proposal = propose_symptom(row, catalog)
        self.assertIsNotNone(proposal)
        self.assertEqual(proposal["proposed_standard"], "Pelvic pain")
        long_row = {
            "domain": "symptom",
            "field": "chief_complaint",
            "source": "The patient presents with a long narrative that is not a chief-complaint token.",
            "frequency": 1,
        }
        self.assertEqual(propose_symptom(long_row, catalog)["proposed_action"], "not_applicable")

    def test_context_index_shows_full_chief_complaint_and_hpi_excerpt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            visits_path = Path(tmp) / "visits.json"
            write_json_array(
                visits_path,
                [
                    {
                        "hadm_id": "10",
                        "chief_complaint": "confusion, fever",
                        "history_of_present_illness": "The patient had confusion for two days after a fall.",
                        "ed_chief_complaint": None,
                        "investigations": {"laboratory": [], "radiology": [], "cardiology": [], "respiratory": []},
                    }
                ],
            )
            index = build_context_index(visits_path)
            examples = index[("chief_complaint", "confusion")]
            self.assertEqual(examples[0]["full_field"], "confusion, fever")
            self.assertIn("two days", examples[0]["hpi_excerpt"])
            self.assertNotIn("discharge_note_full", examples[0])


if __name__ == "__main__":
    unittest.main()
