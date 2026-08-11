from __future__ import annotations

import copy
import unittest

from data_pipeline.archived.parquet_to_jsonl.assembler import assemble_visit
from data_pipeline.archived.parquet_to_jsonl.partitioning import assign_subject_partition
from data_pipeline.archived.parquet_to_jsonl.schema import (
    SCHEMA_VERSION,
    TOP_LEVEL_FIELDS,
    validate_visit_archive,
)
from data_pipeline.archived.parquet_to_jsonl.snapshots import (
    FutureInformationLeakageError,
    QUESTION_TYPES,
    validate_snapshot_evidence,
)


class VisitArchiveContractTest(unittest.TestCase):
    def build_record(self):
        episode = {
            "episode_id": "H:10",
            "episode_type": "hospital",
            "subject_id": 1,
            "hadm_id": 10,
            "episode_start_time": "2200-01-01 08:00:00",
            "clinical_end_time": "2200-01-03 08:00:00",
            "administrative_end_time": "2200-01-03 12:00:00",
            "outcome_type": "discharge",
            "admission_type": "URGENT",
            "admission_location": "EMERGENCY ROOM",
            "discharge_location": "HOME",
            "source_versions": "mimic-iv=3.1",
        }
        timed = {
            "event_id": "EV:1",
            "event_time": "2200-01-01 09:00:00",
            "available_time": "2200-01-01 09:05:00",
            "recorded_time": "2200-01-01 09:05:00",
        }
        ds_note = {
            "note_id": "DS:1",
            "event_time": "2200-01-03 08:00:00",
            "available_time": "2200-01-03 12:00:00",
            "recorded_time": "2200-01-03 12:00:00",
            "text": "Synthetic note",
            "_parsed": {
                "narrative": {
                    "chief_complaint": "Retrospective chest pain",
                    "history_of_present_illness": "History",
                },
                "disposition": {"discharge_record": "Follow up"},
            },
        }
        return assemble_visit(
            episode=episode,
            patients={1: {}},
            age=60,
            sex="F",
            ds_note=ds_note,
            lab_data={"H:10": [{"label": "Troponin", "results": [dict(timed, value="1")]}]},
            dx_data={"H:10": {"primary": {"icd_code": "I21", "evidence_phase": "post_hoc"}, "coded_diagnoses": [{"icd_code": "I21", "evidence_phase": "post_hoc"}]}},
            micro_data={},
            rad_data={"H:10": [dict(timed, note_id="RR:1", text="Chest radiograph")]},
            rx_data={"H:10": [dict(timed, drug="Aspirin")]},
            pharm_data={"H:10": [dict(timed, medication="Aspirin")]},
            emar_data={"H:10": [dict(timed, medication="Aspirin", details=[{"dose": "81 mg"}])]},
            proc_data={},
            ed_dx_data={},
            transfer_data={"H:10": [dict(timed, careunit="Cardiology")]},
            icu_data={"H:10": [{"first_careunit": "MICU", "last_careunit": "MICU", "los": 1.0}]},
            drg_data={"H:10": [{"drg_code": "280"}]},
            triage_data={"H:10": dict(timed, chief_complaint="Chest pain", pain="7")},
            service_data={"H:10": [dict(timed, _event_subtype="MED")]},
            medrecon_data={},
            omr_data={"H:10": [dict(timed, result_name="BMI", result_value="25")]},
            hcpcs_data={},
            order_data={"H:10": [dict(timed, order_type="Lab", details=[{"field_name": "Test", "field_value": "Troponin"}])]},
            encounter_context={"H:10": {"ed_start_time": "2200-01-01 07:00:00", "ed_end_time": "2200-01-01 10:00:00", "ed_disposition": "ADMITTED", "arrival_transport": "AMBULANCE"}},
            longitudinal_data={"H:10": [{"referenced_id": "H:9", "content_included": False}]},
        )

    def test_frozen_schema_and_repaired_fields(self):
        record = self.build_record()
        self.assertIsNotNone(record)
        self.assertEqual(tuple(record), TOP_LEVEL_FIELDS)
        self.assertEqual(record["metadata"]["schema_version"], SCHEMA_VERSION)
        self.assertEqual(record["presentation"]["triage_chief_complaint"]["text"], "Chest pain")
        self.assertEqual(record["presentation"]["discharge_summary_retrospective"]["chief_complaint"], "Retrospective chest pain")
        self.assertEqual(record["care_path"]["ed"]["disposition"], "ADMITTED")
        self.assertEqual(record["care_path"]["icu_stays"][0]["first_careunit"], "MICU")
        self.assertEqual(record["vitals"]["initial"]["pain"], "7")
        self.assertTrue(record["orders"]["provider_orders"][0]["details"])
        self.assertTrue(record["treatments"]["medication_administrations"][0]["details"])
        validate_visit_archive(record)

    def test_generates_exactly_five_snapshot_contracts(self):
        snapshots = self.build_record()["decision_snapshots"]
        self.assertEqual(tuple(item["question_type"] for item in snapshots), QUESTION_TYPES)
        self.assertTrue(all("hidden_outcome" in item for item in snapshots))
        ready = [item for item in snapshots if item["status"] == "ready"]
        self.assertTrue(ready)
        for snapshot in ready:
            validate_snapshot_evidence(snapshot, snapshot["evidence"])

    def test_schema_rejects_pain_drift(self):
        record = self.build_record()
        del record["vitals"]["initial"]["pain"]
        with self.assertRaisesRegex(ValueError, "pain"):
            validate_visit_archive(record)


class SubjectIsolationTest(unittest.TestCase):
    def test_all_episodes_of_one_patient_share_partition(self):
        first = assign_subject_partition("123")
        second = assign_subject_partition(123)
        self.assertEqual(first, second)
        self.assertIn(first["name"], {"development", "final_test"})


class FutureLeakageTest(unittest.TestCase):
    def setUp(self):
        self.snapshot = {
            "cutoff_time": "2200-01-01 10:00:00",
            "forbidden_evidence_phases": ["post_hoc"],
        }

    def test_accepts_evidence_available_at_cutoff(self):
        validate_snapshot_evidence(self.snapshot, [{"event_id": "LAB:1", "available_time": "2200-01-01 10:00:00", "evidence_phase": "contemporaneous"}])

    def test_rejects_future_availability(self):
        with self.assertRaises(FutureInformationLeakageError):
            validate_snapshot_evidence(self.snapshot, [{"event_id": "LAB:1", "available_time": "2200-01-01 10:00:01", "evidence_phase": "contemporaneous"}])

    def test_rejects_post_hoc_even_when_timestamp_is_early(self):
        with self.assertRaises(FutureInformationLeakageError):
            validate_snapshot_evidence(self.snapshot, [{"event_id": "DX:1", "available_time": "2200-01-01 09:00:00", "evidence_phase": "post_hoc"}])


if __name__ == "__main__":
    unittest.main()
