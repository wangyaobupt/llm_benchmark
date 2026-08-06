from __future__ import annotations

import csv
import gzip
import json
import tempfile
import unittest
from pathlib import Path

import duckdb

from mimic_pipeline.cli import create_parser
from mimic_pipeline.episode_export import export_episode_json
from mimic_pipeline.episode_pipeline import build_episode_outputs
from mimic_pipeline.source_catalog import (
    EpisodeDatasetPaths,
    SOURCE_BY_KEY,
    SOURCE_SPECS,
)


def write_source_rows(
    root: Path,
    key: str,
    rows: list[dict[str, object]],
) -> None:
    spec = SOURCE_BY_KEY[key]
    path = root / spec.relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=spec.header)
        writer.writeheader()
        writer.writerows(rows)


def create_episode_fixture(root: Path) -> None:
    for spec in SOURCE_SPECS:
        write_source_rows(root, spec.key, [])

    write_source_rows(
        root,
        "patients",
        [
            {"subject_id": 1, "gender": "F", "anchor_age": 60, "anchor_year": 2150},
            {"subject_id": 2, "gender": "M", "anchor_age": 70, "anchor_year": 2150},
            {"subject_id": 3, "gender": "F", "anchor_age": 50, "anchor_year": 2150},
        ],
    )
    write_source_rows(
        root,
        "admissions",
        [
            {
                "subject_id": 1,
                "hadm_id": 10,
                "admittime": "2150-01-01 00:00:00",
                "dischtime": "2150-01-05 00:00:00",
                "admission_type": "URGENT",
                "discharge_location": "HOME",
                "hospital_expire_flag": 0,
            },
            {
                "subject_id": 1,
                "hadm_id": 11,
                "admittime": "2150-02-01 00:00:00",
                "dischtime": "2150-02-05 00:00:00",
                "admission_type": "ELECTIVE",
                "discharge_location": "HOME",
                "hospital_expire_flag": 0,
            },
            {
                "subject_id": 2,
                "hadm_id": 20,
                "admittime": "2150-01-08 00:00:00",
                "dischtime": "2150-01-10 00:00:00",
                "admission_type": "URGENT",
                "discharge_location": "HOME",
                "hospital_expire_flag": 0,
            },
        ],
    )
    write_source_rows(
        root,
        "edstays",
        [
            {
                "subject_id": 1,
                "hadm_id": 10,
                "stay_id": 100,
                "intime": "2149-12-31 22:00:00",
                "outtime": "2150-01-01 02:00:00",
                "disposition": "ADMITTED",
            },
            {
                "subject_id": 2,
                "hadm_id": "",
                "stay_id": 200,
                "intime": "2150-01-07 00:00:00",
                "outtime": "2150-01-07 04:00:00",
                "disposition": "HOME",
            },
            {
                "subject_id": 3,
                "hadm_id": 999,
                "stay_id": 300,
                "intime": "2150-03-01 00:00:00",
                "outtime": "2150-03-01 02:00:00",
                "disposition": "ADMITTED",
            },
        ],
    )
    write_source_rows(
        root,
        "triage",
        [
            {
                "subject_id": 1,
                "stay_id": 100,
                "temperature": 37.0,
                "heartrate": 100,
                "acuity": 2,
                "chiefcomplaint": "chest pain",
            },
            {
                "subject_id": 2,
                "stay_id": 200,
                "temperature": 36.5,
                "heartrate": 80,
                "acuity": 3,
                "chiefcomplaint": "cough",
            },
        ],
    )
    write_source_rows(
        root,
        "vitalsign",
        [
            {
                "subject_id": 2,
                "stay_id": 200,
                "charttime": "2150-01-07 01:00:00",
                "heartrate": 82,
                "o2sat": 98,
            }
        ],
    )
    write_source_rows(
        root,
        "ed_diagnosis",
        [
            {
                "subject_id": 2,
                "stay_id": 200,
                "seq_num": 1,
                "icd_code": "R05",
                "icd_version": 10,
                "icd_title": "Cough",
            }
        ],
    )
    write_source_rows(
        root,
        "medrecon",
        [
            {
                "subject_id": 2,
                "stay_id": 200,
                "charttime": "2150-01-07 01:10:00",
                "name": "aspirin",
                "etc_rn": 1,
            }
        ],
    )
    write_source_rows(
        root,
        "pyxis",
        [
            {
                "subject_id": 2,
                "stay_id": 200,
                "charttime": "2150-01-07 02:00:00",
                "med_rn": 1,
                "name": "acetaminophen",
                "gsn_rn": 1,
            }
        ],
    )
    write_source_rows(
        root,
        "icustays",
        [
            {
                "subject_id": 1,
                "hadm_id": 10,
                "stay_id": 1000,
                "first_careunit": "MICU",
                "last_careunit": "MICU",
                "intime": "2150-01-02 00:00:00",
                "outtime": "2150-01-03 00:00:00",
                "los": 1,
            }
        ],
    )
    write_source_rows(
        root,
        "transfers",
        [
            {
                "subject_id": 1,
                "hadm_id": 10,
                "transfer_id": 500,
                "eventtype": "transfer",
                "careunit": "MICU",
                "intime": "2150-01-02 00:00:00",
                "outtime": "2150-01-03 00:00:00",
            }
        ],
    )
    write_source_rows(
        root,
        "services",
        [
            {
                "subject_id": 1,
                "hadm_id": 10,
                "transfertime": "2150-01-01 00:00:00",
                "curr_service": "MED",
            }
        ],
    )
    write_source_rows(
        root,
        "d_labitems",
        [
            {"itemid": 50912, "label": "Creatinine", "fluid": "Blood", "category": "Chemistry"}
        ],
    )
    write_source_rows(
        root,
        "labevents",
        [
            {
                "labevent_id": 1,
                "subject_id": 1,
                "hadm_id": 10,
                "specimen_id": 900,
                "itemid": 50912,
                "charttime": "2150-01-02 01:00:00",
                "storetime": "2150-01-02 02:00:00",
                "value": "1.4",
                "valuenum": 1.4,
                "valueuom": "mg/dL",
                "flag": "abnormal",
            },
            {
                "labevent_id": 2,
                "subject_id": 2,
                "hadm_id": "",
                "specimen_id": 901,
                "itemid": 50912,
                "charttime": "2150-01-07 02:00:00",
                "storetime": "2150-01-07 03:00:00",
                "value": "0.8",
                "valuenum": 0.8,
                "valueuom": "mg/dL",
            },
            {
                "labevent_id": 3,
                "subject_id": 1,
                "hadm_id": "",
                "specimen_id": 902,
                "itemid": 50912,
                "charttime": "2150-01-20 01:00:00",
                "storetime": "2150-01-20 02:00:00",
                "value": "1.0",
                "valuenum": 1.0,
                "valueuom": "mg/dL",
            },
        ],
    )
    write_source_rows(
        root,
        "microbiologyevents",
        [
            {
                "microevent_id": 10,
                "subject_id": 2,
                "micro_specimen_id": 910,
                "chartdate": "2150-01-07",
                "charttime": "2150-01-07 02:30:00",
                "storedate": "2150-01-09",
                "storetime": "2150-01-09 10:00:00",
                "spec_type_desc": "BLOOD CULTURE",
                "test_seq": 1,
                "test_name": "AEROBIC BOTTLE",
                "org_name": "NO GROWTH",
            }
        ],
    )
    write_source_rows(
        root,
        "omr",
        [
            {
                "subject_id": 1,
                "chartdate": "2149-12-01",
                "seq_num": 1,
                "result_name": "Blood Pressure",
                "result_value": "120/80",
            }
        ],
    )
    write_source_rows(
        root,
        "poe",
        [
            {
                "poe_id": "1-1",
                "poe_seq": 1,
                "subject_id": 1,
                "hadm_id": 10,
                "ordertime": "2150-01-01 03:00:00",
                "order_type": "Lab",
                "transaction_type": "New",
                "order_status": "Inactive",
            }
        ],
    )
    write_source_rows(
        root,
        "poe_detail",
        [
            {
                "poe_id": "1-1",
                "poe_seq": 1,
                "subject_id": 1,
                "field_name": "Order Name",
                "field_value": "Creatinine",
            }
        ],
    )
    write_source_rows(
        root,
        "pharmacy",
        [
            {
                "subject_id": 1,
                "hadm_id": 10,
                "pharmacy_id": 10001,
                "poe_id": "1-1",
                "starttime": "2150-01-01 04:00:00",
                "stoptime": "2150-01-02 04:00:00",
                "medication": "aspirin",
                "proc_type": "Unit Dose",
                "status": "Discontinued",
                "entertime": "2150-01-01 03:00:00",
                "verifiedtime": "2150-01-01 03:10:00",
            }
        ],
    )
    write_source_rows(
        root,
        "prescriptions",
        [
            {
                "subject_id": 1,
                "hadm_id": 10,
                "pharmacy_id": 10001,
                "poe_id": "1-1",
                "poe_seq": 1,
                "starttime": "2150-01-01 04:00:00",
                "stoptime": "2150-01-02 04:00:00",
                "drug_type": "MAIN",
                "drug": "aspirin",
                "dose_val_rx": "81",
                "dose_unit_rx": "mg",
                "route": "PO",
            }
        ],
    )
    write_source_rows(
        root,
        "emar",
        [
            {
                "subject_id": 1,
                "hadm_id": 10,
                "emar_id": "1-1.1",
                "emar_seq": 1,
                "poe_id": "1-1",
                "pharmacy_id": 10001,
                "charttime": "2150-01-01 08:00:00",
                "medication": "aspirin",
                "event_txt": "Administered",
                "storetime": "2150-01-01 08:05:00",
            }
        ],
    )
    write_source_rows(
        root,
        "chartevents",
        [
            {
                "subject_id": 1,
                "hadm_id": 10,
                "stay_id": 1000,
                "caregiver_id": 5,
                "charttime": "2150-01-02 01:00:00",
                "storetime": "2150-01-02 01:01:00",
                "itemid": 220045,
                "value": "90",
                "valuenum": 90,
                "valueuom": "bpm",
            },
            {
                "subject_id": 1,
                "hadm_id": 10,
                "stay_id": 1000,
                "caregiver_id": 5,
                "charttime": "2150-01-02 01:00:00",
                "storetime": "2150-01-02 01:02:00",
                "itemid": 220179,
                "value": "120",
                "valuenum": 120,
                "valueuom": "mmHg",
            },
            {
                "subject_id": 1,
                "hadm_id": 10,
                "stay_id": 1000,
                "caregiver_id": 5,
                "charttime": "2150-01-02 01:00:00",
                "storetime": "2150-01-02 01:01:00",
                "itemid": 220045,
                "value": "90",
                "valuenum": 90,
                "valueuom": "bpm",
            },
        ],
    )
    write_source_rows(
        root,
        "d_items",
        [
            {
                "itemid": 220045,
                "label": "Heart Rate",
                "abbreviation": "HR",
                "linksto": "chartevents",
                "category": "Routine Vital Signs",
                "unitname": "bpm",
                "param_type": "Numeric",
            },
            {
                "itemid": 220179,
                "label": "Non Invasive Blood Pressure systolic",
                "abbreviation": "NBPs",
                "linksto": "chartevents",
                "category": "Routine Vital Signs",
                "unitname": "mmHg",
                "param_type": "Numeric",
            },
        ],
    )
    note_fields = [
        {
            "note_id": "d1",
            "subject_id": 1,
            "hadm_id": 10,
            "note_type": "DS",
            "note_seq": 1,
            "charttime": "2150-01-05 00:00:00",
            "storetime": "2150-01-06 00:00:00",
            "text": "Synthetic discharge note.",
        }
    ]
    write_source_rows(root, "discharge", note_fields)
    write_source_rows(
        root,
        "radiology",
        [
            {
                "note_id": "r1",
                "subject_id": 1,
                "hadm_id": 10,
                "note_type": "RR",
                "note_seq": 1,
                "charttime": "2150-01-02 01:00:00",
                "storetime": "2150-01-02 02:00:00",
                "text": "Synthetic inpatient report.",
            },
            {
                "note_id": "r2",
                "subject_id": 2,
                "hadm_id": "",
                "note_type": "RR",
                "note_seq": 1,
                "charttime": "2150-01-07 02:00:00",
                "storetime": "2150-01-07 03:00:00",
                "text": "Synthetic ED report.",
            },
            {
                "note_id": "r3",
                "subject_id": 3,
                "hadm_id": "",
                "note_type": "RR",
                "note_seq": 1,
                "charttime": "2150-04-01 00:00:00",
                "storetime": "2150-04-01 01:00:00",
                "text": "Synthetic unresolved report.",
            },
        ],
    )
    write_source_rows(
        root,
        "radiology_detail",
        [
            {
                "note_id": "r1",
                "subject_id": 1,
                "field_name": "exam_name",
                "field_value": "CHEST X-RAY",
                "field_ordinal": 1,
            }
        ],
    )


class EpisodeSourceCatalogTest(unittest.TestCase):
    def test_validates_all_locked_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "mimic"
            create_episode_fixture(root)
            paths = EpisodeDatasetPaths.from_root(root)
            paths.validate()
            self.assertEqual(len(paths.required_files()), len(SOURCE_SPECS))

    def test_rejects_schema_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "mimic"
            create_episode_fixture(root)
            triage = SOURCE_BY_KEY["triage"]
            path = root / triage.relative_path
            with gzip.open(path, "wt", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow([*triage.header[:-1], "chief_complaint"])
            with self.assertRaisesRegex(ValueError, "triage.csv.gz"):
                EpisodeDatasetPaths.from_root(root).validate()

    def test_large_item_sources_do_not_require_global_window_sort(self) -> None:
        sql_path = (
            Path(__file__).resolve().parents[1]
            / "sql"
            / "episode_aggregation"
            / "build_event_sources.sql"
        )
        sql = sql_path.read_text(encoding="utf-8").upper()
        self.assertNotIn("ROW_NUMBER() OVER", sql)


class EpisodeCliTest(unittest.TestCase):
    def test_exposes_validate_aggregate_and_export_commands(self) -> None:
        parser = create_parser()
        validate_args = parser.parse_args(["validate-episodes", "--data-root", "mimic"])
        aggregate_args = parser.parse_args(["aggregate-episodes"])
        export_args = parser.parse_args(
            [
                "export-episode",
                "--episode-id",
                "H:10",
                "--destination",
                "case.json",
            ]
        )
        self.assertEqual(validate_args.command, "validate-episodes")
        self.assertEqual(aggregate_args.output_dir, Path("outputs/episodes"))
        self.assertEqual(export_args.episode_id, "H:10")


class EpisodePipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name) / "mimic"
        self.output = Path(self.temp_dir.name) / "episode-output"
        create_episode_fixture(self.root)
        self.report = build_episode_outputs(
            self.root,
            self.output,
            memory_limit="1GB",
            threads=1,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def query(self, file_name: str, columns: str, order_by: str = "") -> list[tuple[object, ...]]:
        path = (self.output / file_name).as_posix()
        sql = f"SELECT {columns} FROM read_parquet('{path}')"
        if order_by:
            sql += f" ORDER BY {order_by}"
        connection = duckdb.connect()
        try:
            return connection.execute(sql).fetchall()
        finally:
            connection.close()

    def test_builds_hospital_and_standalone_ed_episodes(self) -> None:
        rows = self.query(
            "episode_index.parquet",
            "episode_id, episode_type, subject_id, hadm_id, episode_start_time",
            "episode_id",
        )
        self.assertEqual([row[0] for row in rows], ["E:200", "E:300", "H:10", "H:11", "H:20"])
        h10 = next(row for row in rows if row[0] == "H:10")
        self.assertEqual(str(h10[4]), "2149-12-31 22:00:00")
        e300 = next(row for row in rows if row[0] == "E:300")
        self.assertEqual(e300[1:4], ("emergency_department", 3, None))

    def test_preserves_all_care_contacts(self) -> None:
        rows = self.query(
            "care_contacts.parquet",
            "contact_id, episode_id, contact_type, link_method",
            "contact_id",
        )
        self.assertIn(("ED:100", "H:10", "emergency_department", "native_link"), rows)
        self.assertIn(("ED:200", "E:200", "emergency_department", "native_link"), rows)
        self.assertIn(("ICU:1000", "H:10", "icu", "native_link"), rows)
        self.assertIn(("TR:500", "H:10", "transfer", "native_link"), rows)

    def test_uses_native_temporal_and_unresolved_links(self) -> None:
        events = self.query(
            "timeline_events.parquet",
            "event_id, episode_id, link_status, event_time, available_time",
            "event_id",
        )
        by_id = {row[0]: row[1:] for row in events}
        self.assertEqual(by_id["LAB:1:900"][:2], ("H:10", "native_link"))
        self.assertEqual(by_id["LAB:2:901"][:2], ("E:200", "unique_temporal_link"))
        self.assertEqual(by_id["LAB:1:902"][:2], (None, "unresolved"))
        self.assertEqual(str(by_id["LAB:1:900"][2]), "2150-01-02 01:00:00")
        self.assertEqual(str(by_id["LAB:1:900"][3]), "2150-01-02 02:00:00")

        documents = self.query(
            "documents.parquet",
            "note_id, episode_id, link_status, available_time",
            "note_id",
        )
        by_note = {row[0]: row[1:] for row in documents}
        self.assertEqual(by_note["r1"][:2], ("H:10", "native_link"))
        self.assertEqual(by_note["r2"][:2], ("E:200", "unique_temporal_link"))
        self.assertEqual(by_note["r3"][:2], (None, "unresolved"))
        self.assertEqual(str(by_note["r2"][2]), "2150-01-07 03:00:00")

    def test_keeps_event_items_and_evidence_refs(self) -> None:
        lab_items = self.query(
            "event_items.parquet",
            "event_id, native_row_key, concept_name, raw_value, raw_unit",
            "native_row_key",
        )
        self.assertIn(("LAB:1:900", "labevent_id=1", "Creatinine", "1.4", "mg/dL"), lab_items)
        evidence = self.query(
            "evidence_links.parquet",
            "target_type, target_id, source_table, native_row_key",
        )
        self.assertIn(
            ("timeline_event", "LAB:1:900", "mimic-iv-3.1/hosp/labevents", "labevent_id=1"),
            evidence,
        )

    def test_groups_same_time_icu_observations_without_dropping_items(self) -> None:
        event_rows = self.query(
            "timeline_events.parquet",
            "event_id, available_time",
            "event_id",
        )
        icu_event_ids = [row[0] for row in event_rows if row[0].startswith("ICUCHART:")]
        self.assertEqual(len(icu_event_ids), 1)
        item_rows = self.query(
            "event_items.parquet",
            "event_id, concept_id",
            "concept_id",
        )
        grouped_items = [row for row in item_rows if row[0] == icu_event_ids[0]]
        self.assertEqual([row[1] for row in grouped_items], ["220045", "220045", "220179"])
        item_ids = self.query("event_items.parquet", "item_event_id")
        self.assertEqual(len(item_ids), len(set(item_ids)))

    def test_records_coverage_without_filtering_episodes(self) -> None:
        rows = self.query(
            "episode_coverage.parquet",
            "episode_id, has_chief_complaint, has_laboratory, has_radiology, has_discharge_summary",
            "episode_id",
        )
        by_episode = {row[0]: row[1:] for row in rows}
        self.assertEqual(by_episode["H:10"], (True, True, True, True))
        self.assertEqual(by_episode["H:11"], (False, False, False, False))
        self.assertEqual(by_episode["E:200"], (True, True, True, False))

    def test_exports_prior_context_separately(self) -> None:
        destination = Path(self.temp_dir.name) / "h11.json"
        payload = export_episode_json(self.output, "H:11", destination)
        self.assertEqual(payload["episode_id"], "H:11")
        self.assertTrue(payload["prior_context"])
        self.assertEqual(payload["current_episode"]["episode"]["episode_id"], "H:11")
        self.assertNotIn("Synthetic discharge note.", json.dumps(payload["current_episode"]))
        self.assertIn("Synthetic discharge note.", json.dumps(payload["prior_context"]))
        persisted = json.loads(destination.read_text(encoding="utf-8"))
        self.assertEqual(persisted, payload)

    def test_quality_report_is_aggregate_and_outputs_are_protected(self) -> None:
        self.assertEqual(self.report["outputs"]["episode_index"]["rows"], 5)
        self.assertEqual(self.report["quality"]["duplicate_episode_ids"], 0)
        self.assertEqual(self.report["quality"]["accepted_subject_conflicts"], 0)
        serialized = json.dumps(self.report)
        self.assertNotIn("Synthetic discharge note", serialized)
        with self.assertRaisesRegex(FileExistsError, "--overwrite"):
            build_episode_outputs(self.root, self.output, memory_limit="1GB", threads=1)


if __name__ == "__main__":
    unittest.main()
