from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from data_pipeline.mcq_visit_extract.catalog import REQUIRED_SOURCE_KEYS
from data_pipeline.mcq_visit_extract.columns import FORBIDDEN_DELIVERABLE_KEYS, RESULT_COLUMNS
from data_pipeline.mcq_visit_extract.config import VisitExtractConfig
from data_pipeline.mcq_visit_extract.ds_parser import followup_unusable, parse_ds_sections, select_ds
from data_pipeline.mcq_visit_extract.extract import age_at_encounter
from data_pipeline.mcq_visit_extract.pipeline import VisitExtractError, run
from tests.test_episode_pipeline import write_source_rows

DS_TEXT = """\
Chief Complaint:
Chest pain

History of Present Illness:
Pain started today.

Past Medical History:
Hypertension

Social History:
Never smoker

Allergies:
No Known Allergies / Adverse Drug Reactions

Physical Exam:
Unremarkable

Brief Hospital Course:
Ruled out ACS.

Medications on Admission:
Aspirin

Discharge Medications:
Aspirin 81 mg

Discharge Diagnosis:
NSTEMI

Discharge Condition:
Stable

Discharge Instructions:
Follow up in 1 week.

Follow-up Instructions:
___
"""


def _ds(subject_id: int, hadm_id: int, note_seq: int = 1) -> dict[str, object]:
    return {
        "note_id": f"{subject_id}-DS-{note_seq}",
        "subject_id": subject_id,
        "hadm_id": hadm_id,
        "note_type": "DS",
        "note_seq": note_seq,
        "charttime": "2150-01-05 00:00:00",
        "storetime": "2150-01-05 01:00:00",
        "text": DS_TEXT,
    }


def create_mcq_fixture(root: Path) -> None:
    for key in REQUIRED_SOURCE_KEYS:
        write_source_rows(root, key, [])
    write_source_rows(
        root,
        "patients",
        [
            {"subject_id": 1, "gender": "F", "anchor_age": 60, "anchor_year": 2150},
            {"subject_id": 2, "gender": "M", "anchor_age": 70, "anchor_year": 2150},
            {"subject_id": 3, "gender": "F", "anchor_age": 10, "anchor_year": 2150},
            {"subject_id": 4, "gender": "M", "anchor_age": 55, "anchor_year": 2150},
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
                "admission_type": "EW EMER.",
                "admission_location": "EMERGENCY ROOM",
                "discharge_location": "HOME",
            },
            {
                "subject_id": 1,
                "hadm_id": 11,
                "admittime": "2150-02-01 00:00:00",
                "admission_type": "ELECTIVE",
                "discharge_location": "HOME",
            },
            {
                "subject_id": 2,
                "hadm_id": 20,
                "admittime": "2150-01-08 00:00:00",
                "admission_type": "URGENT",
                "discharge_location": "HOME",
            },
            {
                "subject_id": 3,
                "hadm_id": 30,
                "admittime": "2150-01-01 00:00:00",
                "admission_type": "URGENT",
                "discharge_location": "HOME",
            },
            {
                "subject_id": 4,
                "hadm_id": 40,
                "admittime": "2150-03-01 00:00:00",
                "admission_type": "EW EMER.",
                "discharge_location": "HOME",
            },
        ],
    )
    write_source_rows(
        root,
        "d_icd_diagnoses",
        [
            {"icd_code": "I214", "icd_version": "10", "long_title": "Non-ST elevation NSTEMI"},
            {"icd_code": "I10", "icd_version": "10", "long_title": "Essential (primary) hypertension"},
        ],
    )
    write_source_rows(
        root,
        "d_icd_procedures",
        [
            {
                "icd_code": "9604",
                "icd_version": "9",
                "long_title": "Insertion of endotracheal tube",
            }
        ],
    )
    write_source_rows(
        root,
        "procedures_icd",
        [
            {
                "subject_id": 1,
                "hadm_id": 10,
                "seq_num": 1,
                "chartdate": "2150-01-02",
                "icd_code": "9604",
                "icd_version": "9",
            }
        ],
    )
    write_source_rows(
        root,
        "diagnoses_icd",
        [
            {"subject_id": 1, "hadm_id": 10, "seq_num": 1, "icd_code": "I214", "icd_version": "10"},
            {"subject_id": 1, "hadm_id": 10, "seq_num": 2, "icd_code": "I10", "icd_version": "10"},
            {"subject_id": 1, "hadm_id": 11, "seq_num": 1, "icd_code": "I214", "icd_version": "10"},
            {"subject_id": 2, "hadm_id": 20, "seq_num": 1, "icd_code": "I214", "icd_version": "10"},
            {"subject_id": 3, "hadm_id": 30, "seq_num": 1, "icd_code": "I214", "icd_version": "10"},
            {"subject_id": 4, "hadm_id": 40, "seq_num": 1, "icd_code": "I214", "icd_version": "10"},
        ],
    )
    write_source_rows(
        root,
        "discharge",
        [_ds(1, 10), _ds(2, 20), _ds(4, 40)],
    )
    write_source_rows(
        root,
        "d_labitems",
        [{"itemid": 50912, "label": "Creatinine", "fluid": "Blood", "category": "Chemistry"}],
    )
    write_source_rows(
        root,
        "labevents",
        [
            {
                "labevent_id": 1,
                "subject_id": 1,
                "hadm_id": 10,
                "itemid": 50912,
                "charttime": "2150-01-01 08:00:00",
                "value": "1.5",
                "valuenum": "1.5",
                "valueuom": "mg/dL",
                "flag": "abnormal",
            },
            {
                "labevent_id": 2,
                "subject_id": 1,
                "hadm_id": 10,
                "itemid": 50912,
                "charttime": "2150-01-02 08:00:00",
                "value": "1.2",
                "valuenum": "1.2",
                "valueuom": "mg/dL",
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
            }
        ],
    )
    write_source_rows(
        root,
        "triage",
        [
            {
                "subject_id": 1,
                "stay_id": 100,
                "temperature": "98.6",
                "heartrate": "88",
                "resprate": "18",
                "o2sat": "97",
                "sbp": "130",
                "dbp": "80",
                "acuity": "3",
                "chiefcomplaint": "CHEST PAIN",
                "pain": "8",
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
                "starttime": "2150-01-01 03:00:00",
                "stoptime": "2150-01-03 03:00:00",
                "drug_type": "MAIN",
                "drug": "Aspirin",
                "route": "PO",
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
                "transfertime": "2150-01-01 02:10:00",
                "curr_service": "CMED",
            }
        ],
    )


def _config(root: Path, output: Path, **overrides: object) -> VisitExtractConfig:
    values = {
        "data_root": root,
        "output_dir": output,
        "sample_size": 3,
        "shard_size": 1,
        "development_percent": 99,
        "sample_pool": "development",
        "duckdb_threads": 1,
        "duckdb_memory_limit": "512MB",
        "funnel_shard_size": 10,
    }
    values.update(overrides)
    return VisitExtractConfig(**values)  # type: ignore[arg-type]


class ParserTests(unittest.TestCase):
    def test_age_formula(self) -> None:
        self.assertEqual(age_at_encounter(60, 2100, "2105-03-01 00:00:00"), 65)

    def test_ds_sections_and_followup_unusable(self) -> None:
        sections = parse_ds_sections(DS_TEXT)
        self.assertEqual(sections["chief_complaint"], "Chest pain")
        self.assertEqual(sections["discharge_record"], "Follow up in 1 week.")
        self.assertTrue(followup_unusable(sections["followup_instructions"]))
        selected = select_ds(
            [
                {
                    "note_id": "old",
                    "note_type": "DS",
                    "note_seq": 1,
                    "charttime": "2150-01-01",
                    "text": DS_TEXT,
                },
                {
                    "note_id": "new",
                    "note_type": "DS",
                    "note_seq": 2,
                    "charttime": "2150-01-02",
                    "text": DS_TEXT.replace("Chest pain", "Dyspnea"),
                },
                {
                    "note_id": "ad",
                    "note_type": "AD",
                    "note_seq": 9,
                    "text": DS_TEXT,
                },
            ]
        )
        assert selected is not None
        self.assertEqual(selected.note_id, "new")
        self.assertEqual(selected.sections["chief_complaint"], "Dyspnea")


class ExtractResumeTests(unittest.TestCase):
    def test_extracts_flat_rows_and_resumes_without_resampling(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "mimic"
            output = Path(tmp) / "out"
            create_mcq_fixture(root)
            config = _config(root, output)
            first = run(config)
            csv_path = output / "visits.csv"
            json_path = output / "visits.json"
            self.assertTrue(csv_path.exists())
            visits = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(len(visits), 3)
            self.assertEqual(list(visits[0]), list(RESULT_COLUMNS))
            for record in visits:
                leaked = FORBIDDEN_DELIVERABLE_KEYS.intersection(record)
                self.assertFalse(leaked)
                self.assertTrue(record["chief_complaint"])
                self.assertIn("Chest pain", record["discharge_note_full"])
            self.assertTrue(any(record["hadm_id"] == "10" for record in visits))
            ten = next(record for record in visits if record["hadm_id"] == "10")
            self.assertEqual(ten["age_at_encounter"], 60)
            self.assertEqual(ten["primary_icd_version"], "ICD-10-CM")
            self.assertEqual(len(ten["investigations"]["laboratory"][0]["results"]), 2)
            self.assertEqual(ten["vitals_source"], "triage")
            self.assertEqual(ten["ed_chief_complaint"], "CHEST PAIN")
            self.assertEqual(ten["medications"][0]["drug"], "Aspirin")
            self.assertEqual(ten["medications"][0]["starttime"], "2150-01-01 03:00:00")
            self.assertEqual(ten["medications"][0]["stoptime"], "2150-01-03 03:00:00")
            self.assertEqual(ten["admittime"], "2150-01-01 00:00:00")
            self.assertEqual(ten["procedures"][0]["chartdate"], "2150-01-02")
            self.assertEqual(
                ten["investigations"]["laboratory"][0]["results"][0].get("storetime"),
                None,
            )
            self.assertNotIn("lineage", ten)

            first_selection = (output / "selection.jsonl").read_bytes()
            first_shard = first["shards"]["0"]["sha256"]
            self.assertFalse(first["selection"]["reused"])

            second = run(config)
            self.assertEqual(second["deliverables"]["json_sha256"], first["deliverables"]["json_sha256"])
            self.assertEqual(second["shards"]["0"]["sha256"], first_shard)

            json_path.unlink()
            csv_path.unlink()
            third = run(config)
            self.assertTrue(third["selection"]["reused"])
            self.assertEqual((output / "selection.jsonl").read_bytes(), first_selection)
            self.assertEqual(third["shards"]["0"]["sha256"], first_shard)
            rebuilt = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual(len(rebuilt), 3)
            self.assertEqual(rebuilt[0]["hadm_id"], visits[0]["hadm_id"])

    def test_identity_mismatch_refuses_resume(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "mimic"
            output = Path(tmp) / "out"
            create_mcq_fixture(root)
            run(_config(root, output, sample_size=3))
            with self.assertRaisesRegex(VisitExtractError, "identity mismatch"):
                run(_config(root, output, sample_size=1))

    def test_corrupt_completed_shard_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "mimic"
            output = Path(tmp) / "out"
            create_mcq_fixture(root)
            run(_config(root, output))
            (output / "visits.csv").unlink()
            (output / "visits.json").unlink()
            part = output / "working" / "part-00000.jsonl"
            part.write_text(part.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            with self.assertRaisesRegex(VisitExtractError, "integrity failure"):
                run(_config(root, output))


if __name__ == "__main__":
    unittest.main()
