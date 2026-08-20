from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from data_pipeline.mcq_visit_standardize.drugs import resolve_drug_ingredients
from data_pipeline.mcq_visit_standardize.merge import merge_similar, _symptom_merge_key
from data_pipeline.mcq_visit_standardize.symptoms import _alias_table
from data_pipeline.mcq_visit_standardize.synonyms import load_jsonl
from data_pipeline.mcq_visit_standardize.transform import standardize_visit
from tests.test_mcq_visit_standardize import _base_visit


class DrugResolveTests(unittest.TestCase):
    def test_maps_brand_and_salt(self) -> None:
        self.assertEqual(resolve_drug_ingredients("Lasix"), ("Furosemide",))
        self.assertEqual(resolve_drug_ingredients("HYDROmorphone (Dilaudid)"), ("Hydromorphone",))
        self.assertEqual(resolve_drug_ingredients("Metoprolol Tartrate"), ("Metoprolol",))


class MergeTests(unittest.TestCase):
    def test_fevers_and_dyspnea_share_catalog_concepts(self) -> None:
        catalog = _alias_table(None)
        self.assertEqual(_symptom_merge_key("Fevers", catalog), _symptom_merge_key("Fever", catalog))
        self.assertEqual(
            _symptom_merge_key("Dyspnea", catalog),
            _symptom_merge_key("Shortness of breath", catalog),
        )
        self.assertEqual(
            _symptom_merge_key("abdominal distension", catalog),
            _symptom_merge_key("Abdominal distention", catalog),
        )

    def test_merge_rewrites_synonym_table(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            decisions = root / "decisions.jsonl"
            table = root / "table.jsonl"
            decisions.write_text(
                json.dumps(
                    {
                        "action": "accept",
                        "domain": "symptom",
                        "field": "chief_complaint",
                        "source": "fevers",
                        "lookup_key": "fevers",
                        "standard": "Fevers",
                        "concept_id": "symptom:fevers",
                    }
                )
                + "\n"
                + json.dumps(
                    {
                        "action": "accept",
                        "domain": "symptom",
                        "field": "chief_complaint",
                        "source": "Fever",
                        "lookup_key": "fever",
                        "standard": "Fever",
                        "concept_id": "symptom:fever",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            merge_similar(decisions, table)
            rows = load_jsonl(table)
            standards = {row["lookup_key"]: row["standard"] for row in rows}
            self.assertEqual(standards["fevers"], "Fever")
            self.assertEqual(standards["fever"], "Fever")
            ids = {row["concept_id"] for row in rows}
            self.assertEqual(ids, {"symptom:fever"})


class ExtraMapTests(unittest.TestCase):
    def test_extra_drug_and_allergy_are_applied(self) -> None:
        visit = _base_visit(
            medications=[{"drug": "Unknowncillin", "route": "PO"}],
            allergies="Penicillin",
        )
        out, _reviews = standardize_visit(
            visit,
            extra_drugs={"unknowncillin": ("Unknowncillin", "drug:unknowncillin")},
            extra_allergies={"penicillin": ("Penicillin", "allergy:penicillin")},
        )
        self.assertEqual(out["medications_normalized"][0]["standard_ingredients"], ["Unknowncillin"])
        self.assertEqual(out["allergy_concepts"][0]["standard"], "Penicillin")
        self.assertEqual(out["allergy_concepts"][0]["status"], "mapped/exact")


if __name__ == "__main__":
    unittest.main()
