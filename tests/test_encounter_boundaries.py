from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator
import yaml

from evaluation_pipeline.journey import (
    EncounterBoundaryError,
    EncounterInputs,
    JourneyScopePolicy,
    audit_encounter_boundary_manifest,
    build_encounter_boundaries,
)
from evaluation_pipeline.journey.boundaries import JOURNEY_REASON_CODES
from evaluation_pipeline.governance import build_protocol_lock
from evaluation_pipeline.subject_split import build_subject_split
from tests.protocol_fixtures import frozen_protocol_bundle


ROOT = Path(__file__).resolve().parents[1]


def split_artifacts(test_case: unittest.TestCase) -> dict:
    return test_case.subject_split_artifacts


def rehash_manifest(manifest: dict) -> None:
    body = {
        key: value
        for key, value in manifest.items()
        if key not in {"manifest_sha256", "manifest_hmac_sha256"}
    }
    manifest["manifest_sha256"] = hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def inputs(test_case: unittest.TestCase, **changes: object) -> EncounterInputs:
    value = {
        "admissions": [
            {"subject_id": "s1", "hadm_id": "h1", "admittime": "2026-01-01T10:00:00", "dischtime": "2026-01-03T10:00:00"},
            {"subject_id": "s1", "hadm_id": "h2", "admittime": "2026-02-01T10:00:00", "dischtime": "2026-02-03T10:00:00"},
        ],
        "ed_stays": [
            {"subject_id": "s1", "hadm_id": "h1", "stay_id": "ed1", "intime": "2026-01-01T08:00:00", "outtime": "2026-01-01T10:30:00"},
            {"subject_id": "s1", "hadm_id": None, "stay_id": "ed-alone", "intime": "2026-04-01T08:00:00", "outtime": "2026-04-01T09:00:00"},
        ],
        "icu_stays": [
            {"subject_id": "s1", "hadm_id": "h1", "stay_id": "icu1", "intime": "2026-01-01T12:00:00", "outtime": "2026-01-02T12:00:00"}
        ],
        "events": [
            {"event_id": "evt:000000000000000000000001", "subject_id": "s1", "hadm_id": "h1", "event_time": "2026-01-01T11:00:00", "available_time": "2026-01-01T11:01:00", "time_precision": "second"},
            {"event_id": "evt:000000000000000000000002", "subject_id": "s1", "hadm_id": "h1", "event_time": "2026-01-01T11:00:00", "available_time": "2026-01-01T11:02:00", "time_precision": "second"},
            {"event_id": "evt:000000000000000000000003", "subject_id": "s1", "hadm_id": "h2", "event_time": "2026-02-01T11:00:00", "available_time": None, "time_precision": "second"},
        ],
        "protocol_bundle": test_case.protocol_bundle,
        "protocol_lock": test_case.protocol_lock,
        "subject_split_artifacts": split_artifacts(test_case),
        "subject_split_secret": b"s" * 32,
        "subject_role": "development",
        "reference_key_id": "synthetic-key",
        "reference_secret": b"r" * 32,
    }
    value.update(changes)
    return EncounterInputs(**value)


class EncounterBoundaryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        bundle = frozen_protocol_bundle(ROOT, cls.addClassCleanup)
        cls.protocol_bundle = bundle
        cls.protocol_lock = build_protocol_lock(bundle)
        cls.subject_split_artifacts = build_subject_split(
            ["s1", "s3", "s4"],
            ["s2"],
            {
                "split_id": "synthetic-split",
                "protocol_bundle": bundle,
                "protocol_lock": cls.protocol_lock,
                "ratios": {"development": 1 / 3, "validation": 1 / 3, "final_test": 1 / 3},
                "assignment_seed": "7",
                "subject_ref_key_id": "synthetic-subject-key",
                "subject_ref_secret": b"s" * 32,
            },
        )

    def _build(self, **changes: object) -> dict:
        return build_encounter_boundaries(inputs(self, **changes), JourneyScopePolicy())

    def _audit(self, manifest: dict, expected: dict | None = None) -> dict:
        expected = expected or manifest
        return audit_encounter_boundary_manifest(
            manifest,
            reference_secret=b"r" * 32,
            expected_protocol_lock_sha256=expected["split_lineage"]["protocol_lock_sha256"],
            expected_public_manifest_sha256=expected["split_lineage"]["public_manifest_sha256"],
            expected_source_inputs_sha256=expected["source_inputs_sha256"],
        )

    def test_builds_admission_journeys_linked_ed_nested_icu_and_schema(self) -> None:
        manifest = self._build()
        self.assertEqual(manifest["counts"]["journeys"], 2)
        self.assertEqual(manifest["counts"]["linked_ed_stays"], 1)
        self.assertEqual(manifest["counts"]["icu_substays"], 1)
        self.assertEqual(manifest["counts"]["engineering_audit_journeys"], 0)
        self.assertEqual(manifest["counts"]["rule_discovery_eligible_journeys"], 2)
        self.assertEqual(manifest["split_lineage"]["subject_role"], "development")
        schema = json.loads((ROOT / "schemas/encounter-boundary-manifest.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator(schema).validate(manifest)
        serialized = json.dumps(manifest)
        for raw_id in ("s1", "s2", "h1", "h2", "h3", "ed1", "icu1"):
            self.assertNotIn(f'"{raw_id}"', serialized)

    def test_multiple_admissions_are_separate_and_same_time_events_remain_tied(self) -> None:
        manifest = self._build()
        s1_refs = {
            row["subject_ref"]
            for row in manifest["journeys"]
        }
        self.assertEqual(len(s1_refs), 1)
        s1_journeys = list(manifest["journeys"])
        self.assertEqual(len(s1_journeys), 2)
        assignments = {row["event_id"]: row for row in manifest["event_assignments"]}
        first = assignments["evt:000000000000000000000001"]
        second = assignments["evt:000000000000000000000002"]
        self.assertEqual(first["journey_id"], second["journey_id"])
        self.assertEqual(first["time_group_id"], second["time_group_id"])
        self.assertEqual(first["event_time"], "2026-01-01T11:00:00")
        self.assertEqual(second["event_time"], "2026-01-01T11:00:00")
        self.assertEqual(first["available_time"], "2026-01-01T11:01:00")
        self.assertNotIn("sequence", first)

    def test_standalone_ed_and_unlinked_records_are_explicitly_unresolved(self) -> None:
        manifest = self._build(
            ed_stays=[
                {"subject_id": "s1", "hadm_id": None, "stay_id": "standalone", "intime": "2026-01-01T01:00:00", "outtime": "2026-01-01T02:00:00"},
                {"subject_id": "s1", "hadm_id": "missing", "stay_id": "unlinked", "intime": "2026-01-01T01:00:00", "outtime": "2026-01-01T02:00:00"},
            ],
            icu_stays=[],
            events=[{"event_id": "evt:000000000000000000000004", "subject_id": "s1", "hadm_id": None, "event_time": None, "available_time": None, "time_precision": "unknown"}],
        )
        reasons = [code for row in manifest["unresolved"] for code in row["reason_codes"]]
        self.assertIn("JOURNEY_STANDALONE_ED_EXCLUDED", reasons)
        self.assertIn("JOURNEY_LINKED_ADMISSION_NOT_FOUND", reasons)
        self.assertIn("JOURNEY_EVENT_HADM_MISSING", reasons)
        self.assertTrue(all(row["reason_codes"] for row in manifest["unresolved"]))

    def test_subject_and_interval_conflicts_do_not_silently_link(self) -> None:
        manifest = self._build(
            ed_stays=[{"subject_id": "unknown", "hadm_id": "h1", "stay_id": "bad-ed", "intime": "2026-01-01T11:00:00", "outtime": "2026-01-01T12:00:00"}],
            icu_stays=[{"subject_id": "s1", "hadm_id": "h1", "stay_id": "bad-icu", "intime": "2025-12-31T12:00:00", "outtime": "2026-01-02T12:00:00"}],
            events=[{"event_id": "evt:000000000000000000000005", "subject_id": "unknown", "hadm_id": "h1", "event_time": "2026-01-01T11:00:00", "available_time": None, "time_precision": "second"}],
        )
        reasons = [code for row in manifest["unresolved"] for code in row["reason_codes"]]
        self.assertGreaterEqual(reasons.count("JOURNEY_SUBJECT_MISMATCH"), 2)
        self.assertIn("JOURNEY_ED_HANDOFF_INVALID", reasons)
        self.assertIn("JOURNEY_ICU_OUTSIDE_ADMISSION", reasons)

    def test_invalid_admission_and_unknown_split_are_unresolved(self) -> None:
        manifest = self._build(
            admissions=[
                {"subject_id": "unknown", "hadm_id": "hu", "admittime": "2026-01-02T00:00:00", "dischtime": "2026-01-01T00:00:00"}
            ],
            ed_stays=[],
            icu_stays=[],
            events=[],
        )
        self.assertEqual(manifest["counts"]["journeys"], 0)
        self.assertEqual(
            manifest["unresolved"][0]["reason_codes"],
            ["JOURNEY_SPLIT_ROLE_UNKNOWN", "JOURNEY_ADMISSION_INVALID_INTERVAL"],
        )

    def test_input_order_does_not_change_manifest_hash(self) -> None:
        base = inputs(self)
        reversed_inputs = EncounterInputs(
            admissions=reversed(list(base.admissions)),
            ed_stays=reversed(list(base.ed_stays)),
            icu_stays=reversed(list(base.icu_stays)),
            events=reversed(list(base.events)),
            protocol_bundle=base.protocol_bundle,
            protocol_lock=base.protocol_lock,
            subject_split_artifacts=base.subject_split_artifacts,
            subject_split_secret=base.subject_split_secret,
            subject_role=base.subject_role,
            reference_key_id=base.reference_key_id,
            reference_secret=base.reference_secret,
        )
        self.assertEqual(
            build_encounter_boundaries(base),
            build_encounter_boundaries(reversed_inputs),
        )

    def test_duplicate_native_identity_and_unfrozen_policy_fail_closed(self) -> None:
        duplicate = inputs(self, admissions=[
            {"subject_id": "s1", "hadm_id": "h1", "admittime": "2026-01-01T10:00:00", "dischtime": "2026-01-02T10:00:00"},
            {"subject_id": "s1", "hadm_id": "h1", "admittime": "2026-01-03T10:00:00", "dischtime": "2026-01-04T10:00:00"},
        ])
        with self.assertRaisesRegex(EncounterBoundaryError, "duplicate admission"):
            build_encounter_boundaries(duplicate)
        with self.assertRaisesRegex(EncounterBoundaryError, "outside the frozen"):
            build_encounter_boundaries(inputs(self), JourneyScopePolicy(standalone_ed="include"))

    def test_tampered_split_artifacts_fail_closed(self) -> None:
        artifacts = copy.deepcopy(split_artifacts(self))
        artifacts["protected_mapping"]["records"][0]["subject_ref"] = "sub_" + "0" * 64
        with self.assertRaisesRegex(EncounterBoundaryError, "subject split audit failed"):
            self._build(subject_split_artifacts=artifacts)

    def test_fake_protocol_lock_fails_before_boundary_construction(self) -> None:
        fake = dict(self.protocol_lock)
        fake["protocol_lock_sha256"] = "0" * 64
        with self.assertRaisesRegex(EncounterBoundaryError, "protocol lock verification failed"):
            self._build(protocol_lock=fake)

    def test_invalid_non_null_event_time_is_unresolved(self) -> None:
        manifest = self._build(events=[{
            "event_id": "evt:000000000000000000000006",
            "subject_id": "s1",
            "hadm_id": "h1",
            "event_time": "2026-01-01T11:00:00Z",
            "available_time": None,
            "time_precision": "second",
        }])
        self.assertEqual(manifest["counts"]["assigned_events"], 0)
        self.assertEqual(
            next(row["reason_codes"] for row in manifest["unresolved"] if "JOURNEY_EVENT_TIME_INVALID" in row["reason_codes"]),
            ["JOURNEY_EVENT_TIME_INVALID"],
        )

    def test_engineering_audit_is_built_in_a_separate_non_formal_manifest(self) -> None:
        manifest = self._build(
            subject_role="engineering_audit",
            admissions=[{"subject_id": "s2", "hadm_id": "he", "admittime": "2026-03-01T10:00:00", "dischtime": "2026-03-03T10:00:00"}],
            ed_stays=[], icu_stays=[], events=[],
        )
        self.assertEqual(manifest["split_lineage"]["permitted_use"], "engineering_audit_only")
        self.assertFalse(manifest["journeys"][0]["formal_evaluation_eligible"])
        self.assertFalse(manifest["journeys"][0]["rule_discovery_eligible"])

    def test_mixed_split_input_fails_closed(self) -> None:
        with self.assertRaisesRegex(EncounterBoundaryError, "one split per manifest"):
            self._build(admissions=[
                {"subject_id": "s1", "hadm_id": "h1", "admittime": "2026-01-01T10:00:00", "dischtime": "2026-01-03T10:00:00"},
                {"subject_id": "s4", "hadm_id": "hf", "admittime": "2026-01-01T10:00:00", "dischtime": "2026-01-03T10:00:00"},
            ])

    def test_event_must_be_inside_ed_to_discharge_boundary(self) -> None:
        manifest = self._build(events=[
            {"event_id": "evt:000000000000000000000007", "subject_id": "s1", "hadm_id": "h1", "event_time": "2026-01-01T07:59:59", "available_time": None, "time_precision": "second"},
            {"event_id": "evt:000000000000000000000008", "subject_id": "s1", "hadm_id": "h1", "event_time": "2026-01-03T10:00:01", "available_time": None, "time_precision": "second"},
        ])
        reasons = [row["reason_codes"] for row in manifest["unresolved"]]
        self.assertEqual(reasons.count(["JOURNEY_EVENT_OUTSIDE_BOUNDARY"]), 2)

    def test_date_precision_is_not_fabricated_as_exact_midnight_tie(self) -> None:
        manifest = self._build(events=[
            {"event_id": "evt:000000000000000000000009", "subject_id": "s1", "hadm_id": "h1", "event_time": "2026-01-01", "available_time": None, "time_precision": "date"},
            {"event_id": "evt:00000000000000000000000a", "subject_id": "s1", "hadm_id": "h1", "event_time": "2026-01-01T00:00:00", "available_time": None, "time_precision": "second"},
        ])
        rows = {row["event_id"]: row for row in manifest["event_assignments"]}
        self.assertIsNone(rows["evt:000000000000000000000009"]["time_group_id"])
        self.assertNotIn("evt:00000000000000000000000a", rows)

    def test_missing_event_time_is_unresolved(self) -> None:
        manifest = self._build(events=[{
            "event_id": "evt:00000000000000000000000b", "subject_id": "s1", "hadm_id": "h1",
            "event_time": None, "available_time": None, "time_precision": "unknown",
        }])
        self.assertTrue(any(
            row["reason_codes"] == ["JOURNEY_EVENT_TIME_UNKNOWN"]
            for row in manifest["unresolved"]
        ))

    def test_event_id_and_time_precision_follow_clinical_event_contract(self) -> None:
        with self.assertRaisesRegex(EncounterBoundaryError, "event.event_id"):
            self._build(events=[{
                "event_id": "native-patient-event",
                "subject_id": "s1",
                "hadm_id": "h1",
                "event_time": "2026-01-01T11:00:00",
                "available_time": None,
                "time_precision": "second",
            }])

        for event_time, precision in (
            ("2026-01-01", "second"),
            ("2026-01-01T11:00:00.123456", "date"),
            ("2026-01-01T11:00:00", "subsecond"),
        ):
            with self.subTest(event_time=event_time, precision=precision):
                manifest = self._build(events=[{
                    "event_id": "evt:00000000000000000000000c",
                    "subject_id": "s1",
                    "hadm_id": "h1",
                    "event_time": event_time,
                    "available_time": None,
                    "time_precision": precision,
                }])
                self.assertEqual(manifest["counts"]["assigned_events"], 0)
                self.assertTrue(
                    any(
                        row["record_type"] == "event"
                        and row["reason_codes"] == ["JOURNEY_EVENT_TIME_INVALID"]
                        for row in manifest["unresolved"]
                    )
                )

    def test_linked_ed_must_handoff_at_admission(self) -> None:
        manifest = self._build(ed_stays=[{
            "subject_id": "s1", "hadm_id": "h1", "stay_id": "remote-ed",
            "intime": "2025-12-01T08:00:00", "outtime": "2025-12-01T09:00:00",
        }], icu_stays=[], events=[])
        self.assertIn("JOURNEY_ED_HANDOFF_INVALID", manifest["unresolved"][0]["reason_codes"])

    def test_reason_codes_are_registered(self) -> None:
        registry = yaml.safe_load((ROOT / "config/investigation-selection/reason-code-registry.yaml").read_text(encoding="utf-8"))
        registry_schema = json.loads((ROOT / "schemas/reason-code-registry.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator(registry_schema).validate(registry)
        registered = {row["code"] for row in registry["codes"]}
        self.assertLessEqual(set(JOURNEY_REASON_CODES), registered)

    def test_independent_audit_detects_hash_count_and_reference_tampering(self) -> None:
        for mutate in (
            lambda value: value["counts"].__setitem__("journeys", 99),
            lambda value: value["event_assignments"][0].__setitem__("journey_id", "journey_" + "0" * 64),
            lambda value: value.__setitem__("manifest_sha256", "0" * 64),
        ):
            manifest = copy.deepcopy(self._build())
            mutate(manifest)
            self.assertFalse(self._audit(manifest)["valid"])

    def test_independent_audit_rejects_self_rehashed_schema_and_time_tampering(self) -> None:
        manifest = copy.deepcopy(self._build())
        manifest["schema_version"] = "evil/9"
        rehash_manifest(manifest)
        self.assertFalse(self._audit(manifest)["valid"])

    def test_independent_audit_rejects_group_and_reference_ownership_tampering(self) -> None:
        manifest = copy.deepcopy(self._build())
        manifest["event_assignments"][1]["time_group_id"] = "time_group_" + "0" * 64
        rehash_manifest(manifest)
        self.assertFalse(self._audit(manifest)["valid"])

        manifest = copy.deepcopy(self._build())
        duplicated_ref = manifest["journeys"][0]["linked_ed_stay_refs"][0]
        manifest["journeys"][1]["linked_ed_stay_refs"].append(duplicated_ref)
        manifest["counts"]["linked_ed_stays"] += 1
        rehash_manifest(manifest)
        self.assertFalse(self._audit(manifest)["valid"])

        manifest = copy.deepcopy(self._build())
        manifest["event_assignments"][0]["event_time"] = "not-a-time"
        rehash_manifest(manifest)
        self.assertFalse(self._audit(manifest)["valid"])

        manifest = copy.deepcopy(self._build())
        manifest["event_assignments"][0]["time_group_id"] = None
        rehash_manifest(manifest)
        self.assertFalse(self._audit(manifest)["valid"])

    def test_independent_audit_returns_structured_failure_for_invalid_schema(self) -> None:
        manifest = self._build()
        with tempfile.TemporaryDirectory() as directory:
            invalid_schema = Path(directory) / "invalid-schema.json"
            invalid_schema.write_text(
                json.dumps({"type": "not-a-json-schema-type"}),
                encoding="utf-8",
            )
            with patch(
                "evaluation_pipeline.journey.boundaries.MANIFEST_SCHEMA_PATH",
                invalid_schema,
            ):
                report = self._audit(manifest)
        self.assertFalse(report["valid"])
        self.assertTrue(
            any(
                error.startswith("manifest schema unavailable or invalid:")
                for error in report["errors"]
            )
        )

    def test_independent_audit_authenticates_lineage_and_consistent_rewrites(self) -> None:
        original = self._build()
        rewritten = copy.deepcopy(original)
        rewritten["reference_key_id"] = "rewritten-key"
        rewritten["split_lineage"]["protocol_lock_sha256"] = "0" * 64
        rewritten["journeys"][0]["journey_id"] = "journey_" + "0" * 64
        old_id = original["journeys"][0]["journey_id"]
        for assignment in rewritten["event_assignments"]:
            if assignment["journey_id"] == old_id:
                assignment["journey_id"] = rewritten["journeys"][0]["journey_id"]
        rehash_manifest(rewritten)
        report = self._audit(rewritten, expected=original)
        self.assertFalse(report["valid"])
        self.assertIn("manifest_hmac_sha256 mismatch", report["errors"])
        self.assertIn("protocol lock lineage mismatch", report["errors"])


if __name__ == "__main__":
    unittest.main()
