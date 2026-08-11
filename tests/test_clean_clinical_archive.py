from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from data_pipeline.clean_clinical_archive import (
    INPUT_SCHEMA,
    OUTPUT_SCHEMA,
    ClinicalReadableArchiveError,
    prepare_archive,
    restore_source_record,
)
from data_pipeline.clean_clinical_archive import decoder as shared_decoder
from data_pipeline.clean_clinical_archive.pipeline import (
    DEFAULT_DICTIONARY_DIRECTORY,
)
from data_pipeline.tools.mimic_dictionary import decode_archive as dictionary_decoder


class CleanClinicalArchiveTest(unittest.TestCase):
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
                    "itemid": str(225150 + index),
                    "label": table,
                    "linksto": table,
                    "category": "Test",
                }
                for index, table in enumerate(
                    (
                        "datetimeevents",
                        "ingredientevents",
                        "inputevents",
                        "outputevents",
                        "procedureevents",
                    )
                )
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
        icu_tables = (
            "datetimeevents",
            "ingredientevents",
            "inputevents",
            "outputevents",
            "procedureevents",
        )
        return {
            "schema": dict(INPUT_SCHEMA),
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
            "mimic_iv_icu": {
                table: [{"itemid": str(225150 + index)}]
                for index, table in enumerate(icu_tables)
            },
            "mimic_iv_ed": {"diagnosis": [dict(diagnosis)]},
            "mimic_iv_note": {},
        }

    def _run(
        self, root: Path, record: dict[str, object]
    ) -> tuple[dict[str, object], dict[str, object]]:
        dictionary_directory = self._dictionary_directory(root)
        source = root / "source.jsonl"
        output = root / "readable.jsonl"
        report = root / "report.json"
        source.write_text(json.dumps(record) + "\n", encoding="utf-8")
        metrics = prepare_archive(
            source, output, report, dictionary_directory
        )
        actual = json.loads(output.read_text(encoding="utf-8"))
        return metrics, actual

    def test_decodes_all_ten_paths_adds_poe_and_identifies_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = self._record()
            metrics, actual = self._run(root, original)

            self.assertEqual(metrics["admissions"], 1)
            self.assertEqual(metrics["dictionary_decoded_total"], 10)
            self.assertEqual(len(metrics["decoded_by_path"]), 10)
            self.assertEqual(metrics["poe_events"], 1)
            self.assertEqual(metrics["schema"], OUTPUT_SCHEMA)
            self.assertEqual(metrics["source_schema"], INPUT_SCHEMA)
            self.assertEqual(actual["schema"], OUTPUT_SCHEMA)
            self.assertEqual(actual["source_schema"], INPUT_SCHEMA)
            self.assertEqual(
                actual["mimic_iv_hosp"]["poe_timeline"][0]["action"],
                "create",
            )
            self.assertEqual(restore_source_record(actual), original)

    def test_dictionary_entry_uses_shared_decode_core(self) -> None:
        self.assertIs(
            dictionary_decoder.decode_records,
            shared_decoder.decode_records,
        )
        self.assertIs(
            dictionary_decoder.strip_decoded_fields,
            shared_decoder.strip_decoded_fields,
        )

    def test_default_dictionary_location_is_inside_portable_package(self) -> None:
        package_root = Path(shared_decoder.__file__).resolve().parent
        self.assertEqual(
            DEFAULT_DICTIONARY_DIRECTORY,
            package_root / "dictionaries",
        )

    def test_runs_from_portable_package_without_project_imports(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dictionaries = self._dictionary_directory(root)
            source = root / "source.jsonl"
            output = root / "readable.jsonl"
            report = root / "report.json"
            original = self._record()
            source.write_text(json.dumps(original) + "\n", encoding="utf-8")
            package_parent = Path(__file__).resolve().parents[1] / "data_pipeline"
            environment = os.environ.copy()
            environment["PYTHONPATH"] = str(package_parent)
            probe = (
                "import importlib.util,sys; "
                "assert importlib.util.find_spec('poe_timeline') is None; "
                "import clean_clinical_archive; "
                "assert 'duckdb' not in sys.modules"
            )
            subprocess.run(
                [sys.executable, "-c", probe],
                cwd=root,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "clean_clinical_archive",
                    str(source),
                    "--output",
                    str(output),
                    "--report",
                    str(report),
                    "--dictionary-dir",
                    str(dictionaries),
                ],
                cwd=root,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )
            actual = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(actual["schema"], OUTPUT_SCHEMA)
            self.assertEqual(restore_source_record(actual), original)

    def test_rejects_wrong_input_schema_without_partial_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dictionaries = self._dictionary_directory(root)
            record = self._record()
            record["schema"] = {
                "name": "mimic_admission_clinical_readable",
                "version": "1.0.0",
            }
            source = root / "source.jsonl"
            output = root / "readable.jsonl"
            report = root / "report.json"
            source.write_text(json.dumps(record) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(
                ClinicalReadableArchiveError, "schema identity mismatch"
            ):
                prepare_archive(source, output, report, dictionaries)

            self.assertFalse(output.exists())
            self.assertFalse(report.exists())
            self.assertFalse(output.with_suffix(".jsonl.partial").exists())
            self.assertFalse(report.with_suffix(".json.partial").exists())

    def test_rejects_partial_icd_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dictionaries = self._dictionary_directory(root)
            record = self._record()
            record["mimic_iv_hosp"]["diagnoses_icd"][0][
                "icd_version"
            ] = None
            source = root / "source.jsonl"
            source.write_text(json.dumps(record) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(
                ClinicalReadableArchiveError,
                "partial dictionary key.*icd_code='41001'.*icd_version=None",
            ):
                prepare_archive(
                    source,
                    root / "readable.jsonl",
                    root / "report.json",
                    dictionaries,
                )

    def test_rejects_unresolved_nonempty_code(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dictionaries = self._dictionary_directory(root)
            record = self._record()
            record["mimic_iv_hosp"]["labevents"][0]["itemid"] = "99999"
            source = root / "source.jsonl"
            source.write_text(json.dumps(record) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(
                ClinicalReadableArchiveError, "unresolved code.*itemid='99999'"
            ):
                prepare_archive(
                    source,
                    root / "readable.jsonl",
                    root / "report.json",
                    dictionaries,
                )

    def test_rejects_d_items_table_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dictionaries = self._dictionary_directory(root)
            items_path = dictionaries / "d_items.json"
            items = json.loads(items_path.read_text(encoding="utf-8"))
            items[2]["linksto"] = "chartevents"
            items_path.write_text(json.dumps(items), encoding="utf-8")
            source = root / "source.jsonl"
            source.write_text(
                json.dumps(self._record()) + "\n", encoding="utf-8"
            )

            with self.assertRaisesRegex(
                ClinicalReadableArchiveError,
                "links to 'chartevents'.*not 'inputevents'",
            ):
                prepare_archive(
                    source,
                    root / "readable.jsonl",
                    root / "report.json",
                    dictionaries,
                )

    def test_rejects_duplicate_dictionary_key(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dictionaries = self._dictionary_directory(root)
            labs_path = dictionaries / "d_labitems.json"
            labs = json.loads(labs_path.read_text(encoding="utf-8"))
            labs.append(dict(labs[0]))
            labs_path.write_text(json.dumps(labs), encoding="utf-8")
            source = root / "source.jsonl"
            source.write_text(
                json.dumps(self._record()) + "\n", encoding="utf-8"
            )

            with self.assertRaisesRegex(
                ClinicalReadableArchiveError, "duplicate key.*d_labitems"
            ):
                prepare_archive(
                    source,
                    root / "readable.jsonl",
                    root / "report.json",
                    dictionaries,
                )


if __name__ == "__main__":
    unittest.main()
