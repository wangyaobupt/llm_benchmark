from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import duckdb

from data_pipeline.tools.mimic_dictionary.decode_archive import (
    DecodeError,
    decode_file,
    strip_decoded_fields,
)


class DecodeArchiveTest(unittest.TestCase):
    def _database(self, path: Path) -> None:
        connection = duckdb.connect(str(path))
        try:
            connection.execute(
                "CREATE TABLE d_labitems AS SELECT '50878' AS itemid, "
                "'Asparate Aminotransferase (AST)' AS \"label\", 'Blood' AS fluid, "
                "'Chemistry' AS category"
            )
            connection.execute(
                "CREATE TABLE d_items AS SELECT '225158' AS itemid, 'NaCl 0.9%' AS \"label\", "
                "'NaCl 0.9%' AS abbreviation, 'inputevents' AS linksto, "
                "'Fluids/Intake' AS category, 'mL' AS unitname, 'Numeric' AS param_type, "
                "NULL AS lownormalvalue, NULL AS highnormalvalue"
            )
            connection.execute(
                "CREATE TABLE d_icd_diagnoses AS SELECT '41001' AS icd_code, "
                "'9' AS icd_version, 'Acute myocardial infarction' AS long_title"
            )
            connection.execute(
                "CREATE TABLE d_icd_procedures AS SELECT '0066' AS icd_code, "
                "'9' AS icd_version, 'Percutaneous coronary intervention' AS long_title"
            )
            connection.execute(
                "CREATE TABLE d_hcpcs AS SELECT '99223' AS code, 'Evaluation' AS category, "
                "'Initial hospital care' AS long_description, "
                "'Initial hosp care' AS short_description"
            )
        finally:
            connection.close()

    def _record(self) -> dict:
        icd = {"icd_code": "41001", "icd_version": "9"}
        return {
            "mimic_iv_hosp": {
                "labevents": [{"itemid": "50878", "value": "42"}],
                "diagnoses_icd": [dict(icd)],
                "procedures_icd": [{"icd_code": "0066", "icd_version": "9"}],
                "hcpcsevents": [{"hcpcs_cd": "99223"}],
            },
            "mimic_iv_ed": {"diagnosis": [dict(icd)]},
            "mimic_iv_icu": {
                "datetimeevents": [],
                "ingredientevents": [],
                "inputevents": [{"itemid": "225158", "amount": "80"}],
                "outputevents": [],
                "procedureevents": [],
            },
        }

    def test_decodes_known_codes_without_changing_original_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "dictionary.duckdb"
            source = root / "source.json"
            output = root / "parsed.json"
            self._database(database)
            original = [self._record()]
            source.write_text(json.dumps(original), encoding="utf-8")

            report = decode_file(source, output, database)
            parsed = json.loads(output.read_text(encoding="utf-8"))

            self.assertEqual(report["decoded_total"], 6)
            self.assertEqual(report["unresolved_total"], 0)
            self.assertEqual(strip_decoded_fields(parsed), original)
            lab = parsed[0]["mimic_iv_hosp"]["labevents"][0]["itemid_decoded"]
            self.assertEqual(lab["label"], "Asparate Aminotransferase (AST)")
            self.assertEqual(lab["fluid"], "Blood")
            self.assertEqual(
                parsed[0]["mimic_iv_icu"]["inputevents"][0]["itemid_decoded"]["label"],
                "NaCl 0.9%",
            )

    def test_streams_jsonl_without_changing_original_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "dictionary.duckdb"
            source = root / "source.jsonl"
            output = root / "parsed.jsonl"
            self._database(database)
            original = [self._record(), self._record()]
            source.write_text(
                "".join(json.dumps(record) + "\n" for record in original),
                encoding="utf-8",
            )

            report = decode_file(source, output, database)
            parsed = [
                json.loads(line)
                for line in output.read_text(encoding="utf-8").splitlines()
            ]

            self.assertEqual(report["records"], 2)
            self.assertEqual(report["decoded_total"], 12)
            self.assertEqual(report["input_format"], "jsonl")
            self.assertEqual(report["output_format"], "jsonl")
            self.assertEqual(strip_decoded_fields(parsed), original)

    def test_rejects_d_items_code_linked_to_another_event_table(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "dictionary.duckdb"
            source = root / "source.jsonl"
            output = root / "parsed.jsonl"
            self._database(database)
            with duckdb.connect(str(database)) as connection:
                connection.execute(
                    "UPDATE d_items SET linksto = 'chartevents' WHERE itemid = '225158'"
                )
            source.write_text(json.dumps(self._record()) + "\n", encoding="utf-8")

            with self.assertRaisesRegex(DecodeError, "links to 'chartevents'.*'inputevents'"):
                decode_file(source, output, database)
            self.assertFalse(output.exists())
            self.assertFalse(output.with_suffix(".jsonl.partial").exists())

    def test_rejects_unresolved_nonempty_code(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "dictionary.duckdb"
            source = root / "source.json"
            output = root / "parsed.json"
            self._database(database)
            record = self._record()
            record["mimic_iv_hosp"]["labevents"][0]["itemid"] = "99999"
            source.write_text(json.dumps([record]), encoding="utf-8")

            with self.assertRaisesRegex(DecodeError, "unresolved code.*itemid='99999'"):
                decode_file(source, output, database)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
