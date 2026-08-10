from __future__ import annotations

from copy import deepcopy
import json
import tempfile
import unittest
from pathlib import Path

from mimic_dictionary.decode_archive import strip_decoded_fields
from mimic_dictionary.prepare_clinical_readable_archive import (
    ClinicalReadableArchiveError,
    prepare_archive,
)


class PrepareClinicalReadableArchiveTest(unittest.TestCase):
    def _dictionary_directory(self, root: Path) -> Path:
        directory = root / "dictionaries"
        directory.mkdir()
        dictionaries = {
            "d_labitems.json": [
                {
                    "itemid": "50878",
                    "label": "Asparate Aminotransferase (AST)",
                    "fluid": "Blood",
                    "category": "Chemistry",
                }
            ],
            "d_items.json": [
                {
                    "itemid": "225158",
                    "label": "NaCl 0.9%",
                    "abbreviation": "NaCl 0.9%",
                    "linksto": "inputevents",
                    "category": "Fluids/Intake",
                    "unitname": "mL",
                    "param_type": "Numeric",
                    "lownormalvalue": None,
                    "highnormalvalue": None,
                }
            ],
            "d_icd_diagnoses.json": [
                {
                    "icd_code": "41001",
                    "icd_version": "9",
                    "long_title": "Acute myocardial infarction",
                }
            ],
            "d_icd_procedures.json": [
                {
                    "icd_code": "0066",
                    "icd_version": "9",
                    "long_title": "Percutaneous coronary intervention",
                }
            ],
            "d_hcpcs.json": [
                {
                    "code": "99223",
                    "category": "1",
                    "long_description": "Initial hospital care",
                    "short_description": "Initial hosp care",
                }
            ],
        }
        for filename, rows in dictionaries.items():
            (directory / filename).write_text(
                json.dumps(rows), encoding="utf-8"
            )
        return directory

    def _record(self) -> dict[str, object]:
        diagnosis = {"icd_code": "41001", "icd_version": "9"}
        return {
            "schema": {"name": "mimic-admission-raw", "version": "1.0.0"},
            "subject_id": "1",
            "hadm_id": "10",
            "mimic_iv_hosp": {
                "labevents": [{"itemid": "50878", "value": "42"}],
                "diagnoses_icd": [dict(diagnosis)],
                "procedures_icd": [
                    {"icd_code": "0066", "icd_version": "9"}
                ],
                "hcpcsevents": [{"hcpcs_cd": "99223"}],
                "poe": [
                    {
                        "poe_id": "1-1",
                        "poe_seq": "1",
                        "subject_id": "1",
                        "hadm_id": "10",
                        "ordertime": "2150-01-01 09:00:00",
                        "order_type": "Lab",
                        "order_subtype": "Complete Blood Count",
                        "transaction_type": "New",
                        "discontinue_of_poe_id": None,
                        "discontinued_by_poe_id": None,
                        "order_provider_id": "P1",
                        "order_status": "Inactive",
                    }
                ],
                "poe_detail": [],
                "prescriptions": [],
                "pharmacy": [],
            },
            "mimic_iv_ed": {"diagnosis": [dict(diagnosis)]},
            "mimic_iv_icu": {
                "datetimeevents": [],
                "ingredientevents": [],
                "inputevents": [{"itemid": "225158", "amount": "80"}],
                "outputevents": [],
                "procedureevents": [],
            },
            "mimic_iv_note": {},
        }

    def test_decodes_all_supported_paths_and_adds_poe_timeline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dictionary_directory = self._dictionary_directory(root)
            source = root / "source.jsonl"
            output = root / "readable.jsonl"
            report = root / "report.json"
            original = self._record()
            source.write_text(json.dumps(original) + "\n", encoding="utf-8")

            metrics = prepare_archive(
                source, output, report, dictionary_directory
            )
            actual = json.loads(output.read_text(encoding="utf-8"))

            self.assertEqual(metrics["admissions"], 1)
            self.assertEqual(metrics["dictionary_decoded_total"], 6)
            self.assertEqual(metrics["poe_events"], 1)
            self.assertEqual(
                actual["mimic_iv_hosp"]["labevents"][0]["itemid_decoded"][
                    "label"
                ],
                "Asparate Aminotransferase (AST)",
            )
            self.assertEqual(
                actual["mimic_iv_hosp"]["diagnoses_icd"][0]["icd_decoded"][
                    "long_title"
                ],
                "Acute myocardial infarction",
            )
            self.assertEqual(
                actual["mimic_iv_hosp"]["procedures_icd"][0]["icd_decoded"][
                    "long_title"
                ],
                "Percutaneous coronary intervention",
            )
            self.assertEqual(
                actual["mimic_iv_hosp"]["hcpcsevents"][0][
                    "hcpcs_cd_decoded"
                ]["long_description"],
                "Initial hospital care",
            )
            self.assertEqual(
                actual["mimic_iv_icu"]["inputevents"][0]["itemid_decoded"][
                    "label"
                ],
                "NaCl 0.9%",
            )
            self.assertEqual(
                actual["mimic_iv_hosp"]["poe_timeline"][0]["action"], "create"
            )

            restored = strip_decoded_fields(deepcopy(actual))
            restored["mimic_iv_hosp"].pop("poe_timeline")
            self.assertEqual(restored, original)

    def test_rejects_unresolved_nonempty_code_without_partial_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dictionary_directory = self._dictionary_directory(root)
            source = root / "source.jsonl"
            output = root / "readable.jsonl"
            report = root / "report.json"
            record = self._record()
            record["mimic_iv_hosp"]["labevents"][0]["itemid"] = "99999"
            source.write_text(json.dumps(record) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(
                ClinicalReadableArchiveError, "unresolved code.*itemid='99999'"
            ):
                prepare_archive(source, output, report, dictionary_directory)

            self.assertFalse(output.exists())
            self.assertFalse(report.exists())
            self.assertFalse(output.with_suffix(".jsonl.partial").exists())
            self.assertFalse(report.with_suffix(".json.partial").exists())

    def test_rejects_icu_dictionary_entry_linked_to_another_table(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dictionary_directory = self._dictionary_directory(root)
            items_path = dictionary_directory / "d_items.json"
            items = json.loads(items_path.read_text(encoding="utf-8"))
            items[0]["linksto"] = "chartevents"
            items_path.write_text(json.dumps(items), encoding="utf-8")
            source = root / "source.jsonl"
            output = root / "readable.jsonl"
            report = root / "report.json"
            source.write_text(json.dumps(self._record()) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(
                ClinicalReadableArchiveError,
                "links to 'chartevents'.*not 'inputevents'",
            ):
                prepare_archive(source, output, report, dictionary_directory)

            self.assertFalse(output.exists())
            self.assertFalse(report.exists())

    def test_rejects_duplicate_dictionary_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dictionary_directory = self._dictionary_directory(root)
            labs_path = dictionary_directory / "d_labitems.json"
            labs = json.loads(labs_path.read_text(encoding="utf-8"))
            labs.append(dict(labs[0]))
            labs_path.write_text(json.dumps(labs), encoding="utf-8")
            source = root / "source.jsonl"
            source.write_text(json.dumps(self._record()) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(
                ClinicalReadableArchiveError, "duplicate key.*d_labitems"
            ):
                prepare_archive(
                    source,
                    root / "readable.jsonl",
                    root / "report.json",
                    dictionary_directory,
                )


if __name__ == "__main__":
    unittest.main()
