from __future__ import annotations

import csv
import gzip
import json
import tempfile
import unittest
from pathlib import Path

import duckdb

from data_pipeline.mimic_dictionary.builder import DICTIONARIES, build_dictionaries


class MimicDictionaryTest(unittest.TestCase):
    def _write_source(self, root: Path, spec, rows: list[dict[str, str]]) -> None:
        path = root / spec.relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    def _create_sources(self, root: Path) -> None:
        rows_by_name = {
            "d_labitems": [{"itemid": "50878", "label": "Asparate Aminotransferase (AST)", "fluid": "Blood", "category": "Chemistry"}],
            "d_items": [{"itemid": "220045", "label": "Heart Rate", "abbreviation": "HR", "linksto": "chartevents", "category": "Routine Vital Signs", "unitname": "bpm", "param_type": "Numeric", "lownormalvalue": "60", "highnormalvalue": "100"}],
            "d_icd_diagnoses": [{"icd_code": "41001", "icd_version": "9", "long_title": "Acute myocardial infarction"}],
            "d_icd_procedures": [{"icd_code": "0066", "icd_version": "9", "long_title": "Percutaneous coronary intervention"}],
            "d_hcpcs": [{"code": "99223", "category": "Evaluation", "long_description": "Initial hospital care", "short_description": "Initial hosp care"}],
        }
        for spec in DICTIONARIES:
            self._write_source(root, spec, rows_by_name[spec.name])

    def test_builds_only_mimic_iv_semantic_dictionaries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "RawData"
            output = root / "解析"
            self._create_sources(source)
            manifest = build_dictionaries(source, output)

            self.assertEqual(manifest["source_database"], "MIMIC-IV")
            self.assertEqual(manifest["source_version"], "3.1")
            self.assertEqual(manifest["dictionary_count"], 5)
            self.assertEqual(manifest["lookup_rows"], 5)
            self.assertTrue(all((output / "tables" / f"{spec.name}.parquet").is_file() for spec in DICTIONARIES))
            self.assertIn("MIMIC-III 1.4 dictionaries", manifest["excluded"])
            self.assertEqual(
                manifest["total_output_bytes"],
                sum(path.stat().st_size for path in output.rglob("*") if path.is_file()),
            )
            self.assertEqual(
                manifest["database"]["bytes"],
                (output / "mimic_dictionaries.duckdb").stat().st_size,
            )
            lookup_csv = output / "csv" / "code_lookup.csv"
            self.assertEqual(lookup_csv.read_bytes()[:3], b"\xef\xbb\xbf")
            with lookup_csv.open("r", encoding="utf-8-sig", newline="") as handle:
                csv_rows = list(csv.DictReader(handle))
            self.assertEqual(len(csv_rows), 5)
            self.assertEqual(
                next(row for row in csv_rows if row["dictionary_name"] == "d_labitems")["code"],
                "50878",
            )
            lab_json = json.loads((output / "json" / "d_labitems.json").read_text(encoding="utf-8"))
            lookup_json = json.loads(
                (output / "json" / "code_lookup" / "d_labitems.json").read_text(encoding="utf-8")
            )
            self.assertEqual(lab_json[0]["itemid"], "50878")
            self.assertEqual(lookup_json[0]["code"], "50878")
            self.assertNotIn("attributes_json", lookup_json[0])

            with duckdb.connect(str(output / "mimic_dictionaries.duckdb"), read_only=True) as connection:
                row = connection.execute(
                    "SELECT code, label, category, attributes_json FROM code_lookup "
                    "WHERE dictionary_name='d_labitems' AND code='50878'"
                ).fetchone()
            self.assertEqual(row[:3], ("50878", "Asparate Aminotransferase (AST)", "Chemistry"))
            self.assertEqual(json.loads(row[3])["fluid"], "Blood")

    def test_rejects_duplicate_dictionary_keys(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "RawData"
            output = root / "解析"
            self._create_sources(source)
            lab = next(spec for spec in DICTIONARIES if spec.name == "d_labitems")
            duplicate = {"itemid": "50878", "label": "Duplicate", "fluid": "Blood", "category": "Chemistry"}
            self._write_source(source, lab, [
                {"itemid": "50878", "label": "AST", "fluid": "Blood", "category": "Chemistry"},
                duplicate,
            ])
            with self.assertRaisesRegex(ValueError, "duplicate_key_groups=1"):
                build_dictionaries(source, output)


if __name__ == "__main__":
    unittest.main()
