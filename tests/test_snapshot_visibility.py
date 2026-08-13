from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
import yaml

from evaluation_pipeline.snapshot import (
    SNAPSHOT_REASON_CODES,
    SnapshotConfigurationError,
    SnapshotInputError,
    SnapshotPolicy,
    build_snapshot,
)


ROOT = Path(__file__).resolve().parents[1]


def clinical_event(number: int, **changes: object) -> dict:
    token = f"{number:024x}"
    event = {
        "schema_version": "1.2.0",
        "cleaning_status": "accepted",
        "event_id": f"evt:{token}",
        "entity_id": f"ent:{token}",
        "source_row_id": f"src:{token}",
        "subject_id": "subject-development",
        "hadm_id": "admission-1",
        "encounter_id": "encounter-1",
        "event_kind": "laboratory_resulted",
        "lifecycle_action": None,
        "status": "final",
        "assertion": "present",
        "event_time": "2026-01-01T09:00:00",
        "source_available_time": "2026-01-01T09:05:00",
        "available_time": "2026-01-01T09:05:00",
        "recorded_time": "2026-01-01T09:05:00",
        "time_resolution_status": "resolved",
        "time_precision": "second",
        "time_policy_id": "synthetic-policy/1.0.0",
        "time_resolution_reasons": [],
        "evidence_phase": "source_event",
        "source_concept_id": "lab-1",
        "concept_id": "LOINC:synthetic",
        "preferred_name": "Serum potassium",
        "source_label": "Potassium",
        "entity_type": "laboratory_test",
        "normalization_status": "mapped",
        "terminology_mapping_version": "synthetic/1.0.0",
        "content_specificity": "entity_specific",
        "value_numeric": 4.2,
        "value_text": None,
        "value_structured_json": None,
        "unit": "mEq/L",
        "abnormal_flag": None,
        "normalized_value_numeric": 4.2,
        "normalized_value_text": None,
        "normalized_unit": "mmol/L",
        "unit_normalization_status": "mapped",
        "source_module": "mimic_iv_hosp",
        "source_table": "hosp.labevents",
        "source_array_index": 0,
        "jsonl_line_number": 1,
        "raw_row_ref": "synthetic-only",
        "source_action": None,
        "quality_flags": [],
        "supporting_source_row_ids": [],
        "supporting_raw_row_refs": [],
    }
    event.update(changes)
    return event


def policy(**changes: object) -> SnapshotPolicy:
    values = {
        "allowed_splits": ("development",),
        "subject_splits": {
            "subject-development": "development",
            "subject-validation": "validation",
        },
        "field_whitelist": {
            "laboratory_resulted": (
                "preferred_name",
                "normalized_value_numeric",
                "normalized_unit",
            )
        },
        "semantic_leakage_terms": ("hidden target",),
        "identity_leakage_patterns": (r"patient\s+name\s*:",),
    }
    values.update(changes)
    return SnapshotPolicy(**values)


class SnapshotVisibilityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest_schema = json.loads(
            (ROOT / "schemas/snapshot-manifest.schema.json").read_text(encoding="utf-8")
        )
        cls.event_schema = json.loads(
            (
                ROOT
                / "data_pipeline/event_pipeline/event_contracts/schemas/clinical-event.schema.json"
            ).read_text(encoding="utf-8")
        )

    def _build(self, events: list[dict], **changes: object) -> dict:
        return build_snapshot(
            events,
            index_time="2026-01-01T10:00:00",
            policy=policy(**changes),
        )

    def test_synthetic_fixture_matches_current_clinical_event_contract(self) -> None:
        Draft202012Validator(self.event_schema).validate(clinical_event(1))

    def test_visible_event_is_projected_to_whitelisted_fields(self) -> None:
        manifest = self._build([clinical_event(1)])
        self.assertEqual(manifest["lineage_status"], "generic_unverified")
        self.assertNotIn("source_lineage", manifest)
        self.assertNotIn("snapshot_hmac_sha256", manifest)
        decision = manifest["events"][0]
        self.assertEqual(decision["visibility_status"], "visible")
        self.assertEqual(decision["exclusion_reason_codes"], [])
        self.assertEqual(
            decision["visible_evidence"],
            {
                "normalized_unit": "mmol/L",
                "normalized_value_numeric": 4.2,
                "preferred_name": "Serum potassium",
            },
        )
        Draft202012Validator(self.manifest_schema).validate(manifest)

    def test_time_phase_split_and_field_gates_are_independent(self) -> None:
        events = [
            clinical_event(1, event_time="2026-01-01T10:00:01"),
            clinical_event(2, available_time="2026-01-01T10:00:01"),
            clinical_event(3, evidence_phase="post_hoc"),
            clinical_event(4, evidence_phase="administrative_end"),
            clinical_event(5, subject_id="subject-validation"),
            clinical_event(6, event_kind="medication_ordered"),
        ]
        manifest = self._build(events)
        reasons = {
            row["event_id"]: row["exclusion_reason_codes"] for row in manifest["events"]
        }
        self.assertEqual(reasons[events[0]["event_id"]], ["SNAPSHOT_NOT_YET_OCCURRED"])
        self.assertEqual(reasons[events[1]["event_id"]], ["SNAPSHOT_NOT_YET_AVAILABLE"])
        self.assertEqual(reasons[events[2]["event_id"]], ["SNAPSHOT_POST_HOC"])
        self.assertEqual(reasons[events[3]["event_id"]], ["SNAPSHOT_ADMINISTRATIVE_END"])
        self.assertEqual(reasons[events[4]["event_id"]], ["SNAPSHOT_SPLIT_FORBIDDEN"])
        self.assertEqual(reasons[events[5]["event_id"]], ["SNAPSHOT_FIELD_NOT_ALLOWED"])

    def test_missing_times_fail_closed_and_multiple_reasons_are_preserved(self) -> None:
        event = clinical_event(
            1,
            event_time=None,
            available_time=None,
            evidence_phase="post_hoc",
            subject_id="subject-validation",
            event_kind="medication_ordered",
        )
        decision = self._build([event])["events"][0]
        self.assertEqual(decision["visibility_status"], "excluded")
        self.assertEqual(
            decision["exclusion_reason_codes"],
            [
                "SNAPSHOT_TIME_UNKNOWN",
                "SNAPSHOT_POST_HOC",
                "SNAPSHOT_FIELD_NOT_ALLOWED",
                "SNAPSHOT_SPLIT_FORBIDDEN",
            ],
        )
        self.assertIsNone(decision["visible_evidence"])

    def test_configured_semantic_and_identity_leakage_are_excluded(self) -> None:
        leak_policy = {
            "laboratory_resulted": ("preferred_name", "value_text")
        }
        semantic = clinical_event(1, value_text="The hidden target was selected")
        identity = clinical_event(2, value_text="Patient name: Synthetic Person")
        manifest = self._build([semantic, identity], field_whitelist=leak_policy)
        self.assertEqual(
            manifest["events"][0]["exclusion_reason_codes"],
            ["SNAPSHOT_SEMANTIC_LEAKAGE"],
        )
        self.assertEqual(
            manifest["events"][1]["exclusion_reason_codes"],
            ["SNAPSHOT_IDENTITY_LEAKAGE"],
        )

    def test_whitelisting_an_identifier_is_identity_leakage(self) -> None:
        manifest = self._build(
            [clinical_event(1)],
            field_whitelist={"laboratory_resulted": ("preferred_name", "subject_id")},
        )
        decision = manifest["events"][0]
        self.assertEqual(decision["exclusion_reason_codes"], ["SNAPSHOT_IDENTITY_LEAKAGE"])
        self.assertIsNone(decision["visible_evidence"])

    def test_input_order_and_batch_size_do_not_change_hash(self) -> None:
        events = [clinical_event(3), clinical_event(1), clinical_event(2)]
        first = build_snapshot(
            events,
            index_time="2026-01-01T10:00:00",
            policy=policy(),
            batch_size=1,
        )
        second = build_snapshot(
            list(reversed(events)),
            index_time="2026-01-01T10:00:00",
            policy=policy(),
            batch_size=20,
        )
        self.assertEqual(first, second)
        self.assertEqual(
            [row["event_id"] for row in first["events"]],
            sorted(event["event_id"] for event in events),
        )

    def test_all_exclusion_codes_are_registered_and_schema_enumerated(self) -> None:
        registry = yaml.safe_load(
            (ROOT / "config/investigation-selection/reason-code-registry.yaml").read_text(
                encoding="utf-8"
            )
        )
        registered = {row["code"] for row in registry["codes"]}
        schema_codes = set(
            self.manifest_schema["$defs"]["reasonCode"]["enum"]
        )
        self.assertEqual(set(SNAPSHOT_REASON_CODES), schema_codes)
        self.assertLessEqual(set(SNAPSHOT_REASON_CODES), registered)

    def test_malformed_time_duplicate_id_and_bad_batch_fail_closed(self) -> None:
        with self.assertRaises(SnapshotInputError):
            self._build([clinical_event(1, event_time="not-a-time")])
        with self.assertRaises(SnapshotInputError):
            self._build([clinical_event(1, evidence_phase="unregistered")])
        with self.assertRaises(SnapshotInputError):
            self._build([clinical_event(1), copy.deepcopy(clinical_event(1))])
        with self.assertRaises(SnapshotConfigurationError):
            build_snapshot(
                [clinical_event(1)],
                index_time="2026-01-01T10:00:00",
                policy=policy(),
                batch_size=0,
            )


if __name__ == "__main__":
    unittest.main()
