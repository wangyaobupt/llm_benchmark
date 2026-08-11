from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from data_pipeline.mimic_raw_archive.catalog import (
    ARCHIVE_SOURCES,
    EXCLUDED_SOURCE_REASONS,
    MODULE_TABLES,
    validate_catalog,
)
from data_pipeline.mimic_raw_archive.config import RawArchiveConfig
from data_pipeline.mimic_raw_archive.extractor import run
from data_pipeline.mimic_raw_archive.schema import (
    RawArchiveValidationError,
    build_record,
    empty_record,
    validate_record,
)
from tests.test_episode_pipeline import create_episode_fixture, write_source_rows


class RawArchiveSchemaTest(unittest.TestCase):
    def test_rejects_invalid_duckdb_memory_limit(self) -> None:
        with self.assertRaisesRegex(ValueError, "duckdb_memory_limit"):
            RawArchiveConfig(duckdb_memory_limit="unlimited").validate()

    def test_catalog_excludes_monitoring_and_unlinked_omr(self) -> None:
        validate_catalog()
        keys = {source.key for source in ARCHIVE_SOURCES}
        self.assertNotIn("chartevents", keys)
        self.assertNotIn("omr", keys)
        self.assertIn("chartevents", EXCLUDED_SOURCE_REASONS)

    def test_empty_record_has_all_raw_table_arrays(self) -> None:
        record = empty_record("1", "10")
        for module, sources in MODULE_TABLES.items():
            self.assertEqual(
                tuple(record[module]), tuple(source.output_key for source in sources)
            )
            self.assertTrue(all(value == [] for value in record[module].values()))

    def test_rejects_derived_or_unknown_raw_fields(self) -> None:
        admission = {
            field: None for field in next(
                source for source in ARCHIVE_SOURCES if source.key == "admissions"
            ).source.header
        }
        admission.update({"subject_id": "1", "hadm_id": "10"})
        record = build_record("1", "10", {"admissions": [admission]})
        record["mimic_iv_hosp"]["admissions"][0]["clinical_end_time"] = "x"
        with self.assertRaisesRegex(RawArchiveValidationError, "raw field drift"):
            validate_record(record)


class RawArchiveEndToEndTest(unittest.TestCase):
    def test_extracts_original_rows_and_resumes_completed_shards(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "mimic"
            output = Path(tmp) / "output"
            merged = Path(tmp) / "raw.jsonl"
            create_episode_fixture(root)
            write_source_rows(
                root,
                "emar_detail",
                [
                    {
                        "subject_id": 1,
                        "emar_id": "1-1.1",
                        "emar_seq": 1,
                        "parent_field_ordinal": 1,
                        "dose_given": "81",
                        "dose_given_unit": "mg",
                        "product_amount_given": "1",
                        "product_unit": "TAB",
                        "product_description": "aspirin 81 mg tablet",
                    },
                    {
                        "subject_id": 1,
                        "emar_id": "1-1.1",
                        "emar_seq": 2,
                        "parent_field_ordinal": 1,
                        "dose_given": "999",
                        "dose_given_unit": "mg",
                    },
                ],
            )
            write_source_rows(
                root,
                "inputevents",
                [{
                    "subject_id": 1,
                    "hadm_id": 10,
                    "stay_id": 1000,
                    "caregiver_id": 5,
                    "starttime": "2150-01-02 01:00:00",
                    "endtime": "2150-01-02 02:00:00",
                    "storetime": "2150-01-02 02:05:00",
                    "itemid": 225158,
                    "amount": "100",
                    "amountuom": "ml",
                    "orderid": 700,
                    "linkorderid": 700,
                    "statusdescription": "FinishedRunning",
                }],
            )
            config = RawArchiveConfig(
                data_root=root,
                output_dir=output,
                merged_path=merged,
                sample_size=3,
                shard_size=2,
                workers=2,
                duckdb_threads=1,
                development_percent=99,
            )
            first = run(config)
            part = output / "parts" / "part-00000.jsonl"
            first_part_hash = first["shards"]["0"]["sha256"]
            second = run(config)
            self.assertEqual(second["shards"]["0"]["sha256"], first_part_hash)
            self.assertEqual(second["merged"]["records"], 3)
            self.assertTrue(part.exists())

            records = [json.loads(line) for line in merged.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(records), 3)
            by_hadm = {record["hadm_id"]: record for record in records}
            h10 = by_hadm["10"]
            self.assertNotIn("chartevents", h10["mimic_iv_icu"])
            self.assertNotIn("decision_snapshots", h10)
            self.assertTrue(h10["mimic_iv_hosp"]["poe"])
            self.assertTrue(h10["mimic_iv_hosp"]["poe_detail"])
            self.assertEqual(len(h10["mimic_iv_hosp"]["emar_detail"]), 1)
            self.assertEqual(
                h10["mimic_iv_hosp"]["emar_detail"][0]["dose_given"], "81"
            )
            self.assertTrue(h10["mimic_iv_ed"]["triage"])
            self.assertTrue(h10["mimic_iv_icu"]["inputevents"])
            self.assertTrue(h10["mimic_iv_note"]["discharge"])
            validate_record(h10)

    def test_accepts_external_selection_without_cohort_fields_in_raw_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "mimic"
            output = Path(tmp) / "output"
            selection = Path(tmp) / "selection.jsonl"
            merged = Path(tmp) / "raw.jsonl"
            create_episode_fixture(root)
            selection.write_text(
                json.dumps({
                    "subject_id": "1",
                    "hadm_id": "10",
                    "selection_rank": 0,
                    "cohort": "coronary_disease_spectrum",
                    "partition": "development",
                }) + "\n",
                encoding="utf-8",
            )
            run(RawArchiveConfig(
                data_root=root,
                output_dir=output,
                merged_path=merged,
                sample_size=1,
                shard_size=1,
                workers=1,
                duckdb_threads=1,
                development_percent=99,
                selection_input=selection,
            ))
            record = json.loads(merged.read_text(encoding="utf-8"))
            self.assertNotIn("cohort", record)
            self.assertNotIn("partition", record)
            self.assertEqual(record["hadm_id"], "10")


if __name__ == "__main__":
    unittest.main()
