from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator

from evaluation_pipeline.governance import build_protocol_lock
from evaluation_pipeline.journey import EncounterInputs, build_encounter_boundaries
from evaluation_pipeline.snapshot import (
    authenticate_boundary_context,
    BoundarySnapshotError,
    SnapshotPolicy,
    audit_authenticated_snapshot,
    build_snapshot,
    build_snapshot_from_boundary,
)
from evaluation_pipeline.subject_split import build_subject_split
from tests.protocol_fixtures import frozen_protocol_bundle
from tests.test_snapshot_visibility import clinical_event


ROOT = Path(__file__).resolve().parents[1]


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def resign_boundary(manifest: dict) -> None:
    body = {
        key: value
        for key, value in manifest.items()
        if key not in {"manifest_sha256", "manifest_hmac_sha256"}
    }
    manifest["manifest_sha256"] = hashlib.sha256(canonical_bytes(body)).hexdigest()
    import hmac
    manifest["manifest_hmac_sha256"] = hmac.new(
        b"r" * 32,
        b"encounter-boundary-manifest/1.0.0\x00" + canonical_bytes(body),
        hashlib.sha256,
    ).hexdigest()


def resign_snapshot(snapshot: dict) -> None:
    body = {
        key: value
        for key, value in snapshot.items()
        if key not in {"snapshot_sha256", "snapshot_hmac_sha256"}
    }
    snapshot["snapshot_sha256"] = hashlib.sha256(canonical_bytes(body)).hexdigest()
    import hmac
    snapshot["snapshot_hmac_sha256"] = hmac.new(
        b"r" * 32,
        b"boundary-authenticated-snapshot/1.0.0\x00" + canonical_bytes(body),
        hashlib.sha256,
    ).hexdigest()


class BoundarySnapshotTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.protocol_bundle = frozen_protocol_bundle(ROOT, cls.addClassCleanup)
        cls.protocol_lock = build_protocol_lock(cls.protocol_bundle)
        cls.split = build_subject_split(
            ["subject-a", "subject-b", "subject-c"],
            [],
            {
                "split_id": "boundary-snapshot-split",
                "protocol_bundle": cls.protocol_bundle,
                "protocol_lock": cls.protocol_lock,
                "ratios": {
                    "development": 1 / 3,
                    "validation": 1 / 3,
                    "final_test": 1 / 3,
                },
                "assignment_seed": "boundary-snapshot-seed",
                "subject_ref_key_id": "boundary-snapshot-subject-key",
                "subject_ref_secret": b"s" * 32,
            },
        )
        cls.development_subject = next(
            row["subject_id"]
            for row in cls.split["protected_mapping"]["records"]
            if row["subject_role"] == "development"
        )

    def _source_events(self) -> list[dict]:
        return [
            clinical_event(
                101,
                subject_id=self.development_subject,
                hadm_id="admission-1",
                encounter_id="admission-1",
            ),
            clinical_event(
                102,
                subject_id=self.development_subject,
                hadm_id="admission-1",
                encounter_id="admission-1",
                available_time="2026-01-01T11:00:00",
                source_available_time="2026-01-01T11:00:00",
            ),
        ]

    def _boundary(self, events: list[dict] | None = None) -> dict:
        return build_encounter_boundaries(
            EncounterInputs(
                admissions=[{
                    "subject_id": self.development_subject,
                    "hadm_id": "admission-1",
                    "admittime": "2026-01-01T08:00:00",
                    "dischtime": "2026-01-01T12:00:00",
                }],
                ed_stays=[],
                icu_stays=[],
                events=events or self._source_events(),
                protocol_bundle=self.protocol_bundle,
                protocol_lock=self.protocol_lock,
                subject_split_artifacts=self.split,
                subject_split_secret=b"s" * 32,
                subject_role="development",
                reference_key_id="boundary-snapshot-reference-key",
                reference_secret=b"r" * 32,
            )
        )

    def _policy(self, **changes: object) -> SnapshotPolicy:
        values = {
            "allowed_splits": ("development",),
            "subject_splits": {self.development_subject: "development"},
            "field_whitelist": {
                "laboratory_resulted": (
                    "preferred_name",
                    "normalized_value_numeric",
                    "normalized_unit",
                )
            },
        }
        values.update(changes)
        return SnapshotPolicy(**values)

    def _build(
        self,
        *,
        events: list[dict] | None = None,
        boundary: dict | None = None,
        policy: SnapshotPolicy | None = None,
        operation: str = "rule_discovery",
    ) -> dict:
        source_events = events or self._source_events()
        manifest = boundary or self._boundary(source_events)
        return build_snapshot_from_boundary(
            source_events,
            boundary_manifest=manifest,
            reference_secret=b"r" * 32,
            expected_protocol_lock_sha256=self.protocol_lock["protocol_lock_sha256"],
            expected_public_manifest_sha256=manifest["split_lineage"]["public_manifest_sha256"],
            expected_source_inputs_sha256=manifest["source_inputs_sha256"],
            journey_id=manifest["journeys"][0]["journey_id"],
            operation=operation,
            index_time="2026-01-01T10:00:00",
            policy=policy or self._policy(),
        )

    def _audit(
        self, snapshot: dict, boundary: dict, trusted_boundary: dict | None = None
    ) -> dict:
        trusted = trusted_boundary or boundary
        return audit_authenticated_snapshot(
            snapshot,
            boundary_manifest=boundary,
            reference_secret=b"r" * 32,
            expected_protocol_lock_sha256=self.protocol_lock["protocol_lock_sha256"],
            expected_public_manifest_sha256=trusted["split_lineage"]["public_manifest_sha256"],
            expected_source_inputs_sha256=trusted["source_inputs_sha256"],
            expected_journey_id=trusted["journeys"][0]["journey_id"],
            expected_operation="rule_discovery",
        )

    def test_builds_schema_valid_snapshot_with_authenticated_lineage(self) -> None:
        boundary = self._boundary()
        snapshot = self._build(boundary=boundary)
        self.assertEqual(snapshot["counts"]["total"], 2)
        self.assertEqual(snapshot["counts"]["visible"], 1)
        self.assertEqual(snapshot["lineage_status"], "boundary_authenticated")
        self.assertIn("snapshot_hmac_sha256", snapshot)
        self.assertEqual(snapshot["source_lineage"]["subject_role"], "development")
        self.assertEqual(snapshot["source_lineage"]["permitted_use"], "rule_discovery")
        schema = json.loads(
            (ROOT / "schemas/snapshot-manifest.schema.json").read_text(encoding="utf-8")
        )
        Draft202012Validator(schema).validate(snapshot)
        self.assertTrue(self._audit(snapshot, boundary)["valid"])

    def test_source_event_hash_and_completeness_fail_closed(self) -> None:
        events = self._source_events()
        boundary = self._boundary(events)
        changed = copy.deepcopy(events)
        changed[0]["preferred_name"] = "rewritten result"
        with self.assertRaisesRegex(BoundarySnapshotError, "hash differs"):
            self._build(events=changed, boundary=boundary)
        with self.assertRaisesRegex(BoundarySnapshotError, "missing exact source events"):
            self._build(events=events[:1], boundary=boundary)

    def test_boundary_auth_operation_and_policy_role_fail_closed(self) -> None:
        boundary = self._boundary()
        tampered = copy.deepcopy(boundary)
        tampered["manifest_hmac_sha256"] = "0" * 64
        with self.assertRaisesRegex(BoundarySnapshotError, "boundary audit failed"):
            self._build(boundary=tampered)
        with self.assertRaisesRegex(BoundarySnapshotError, "operation is not permitted"):
            self._build(boundary=boundary, operation="blind_final_evaluation")
        with self.assertRaisesRegex(BoundarySnapshotError, "allowed_splits"):
            self._build(
                boundary=boundary,
                policy=self._policy(allowed_splits=("validation",)),
            )
        with self.assertRaisesRegex(BoundarySnapshotError, "subject_splits"):
            self._build(
                boundary=boundary,
                policy=self._policy(subject_splits={"wrong-subject": "development"}),
            )

    def test_index_time_must_be_inside_selected_journey(self) -> None:
        boundary = self._boundary()
        common = {
            "events": self._source_events(),
            "boundary_manifest": boundary,
            "reference_secret": b"r" * 32,
            "expected_protocol_lock_sha256": self.protocol_lock["protocol_lock_sha256"],
            "expected_public_manifest_sha256": boundary["split_lineage"]["public_manifest_sha256"],
            "expected_source_inputs_sha256": boundary["source_inputs_sha256"],
            "journey_id": boundary["journeys"][0]["journey_id"],
            "operation": "rule_discovery",
            "policy": self._policy(),
        }
        for index_time in (
            "2026-01-01T07:59:59",
            "2026-01-01T12:00:01",
            "2026-01-01T10:00:00+00:00",
        ):
            with self.subTest(index_time=index_time):
                with self.assertRaises(BoundarySnapshotError):
                    build_snapshot_from_boundary(index_time=index_time, **common)

    def test_generic_or_rewritten_snapshot_cannot_claim_formal_lineage(self) -> None:
        generic = build_snapshot(
            self._source_events(),
            index_time="2026-01-01T10:00:00",
            policy=self._policy(),
        )
        self.assertEqual(generic["lineage_status"], "generic_unverified")
        boundary = self._boundary()
        self.assertFalse(self._audit(generic, boundary)["valid"])

        formal = self._build(boundary=boundary)
        rewritten = copy.deepcopy(formal)
        rewritten["source_lineage"]["protocol_lock_sha256"] = "0" * 64
        body = {
            key: value
            for key, value in rewritten.items()
            if key not in {"snapshot_sha256", "snapshot_hmac_sha256"}
        }
        rewritten["snapshot_sha256"] = hashlib.sha256(
            json.dumps(
                body, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()
        self.assertFalse(self._audit(rewritten, boundary)["valid"])

    def test_unassigned_events_cannot_be_injected_into_snapshot(self) -> None:
        events = self._source_events()
        boundary = self._boundary(events)
        extra = clinical_event(
            103,
            subject_id=self.development_subject,
            hadm_id="different-admission",
            encounter_id="different-admission",
        )
        snapshot = self._build(events=[*events, extra], boundary=boundary)
        self.assertEqual(snapshot["counts"]["total"], 2)
        self.assertNotIn(
            extra["event_id"], {row["event_id"] for row in snapshot["events"]}
        )

    def test_resigned_wrong_journey_assignment_is_rejected(self) -> None:
        events = self._source_events()
        extra = clinical_event(
            103,
            subject_id=self.development_subject,
            hadm_id="different-admission",
            encounter_id="different-admission",
        )
        boundary = self._boundary([*events, extra])
        injected = copy.deepcopy(boundary["event_assignments"][0])
        injected.update(
            event_id=extra["event_id"],
            source_event_sha256=hashlib.sha256(canonical_bytes(extra)).hexdigest(),
            event_time=extra["event_time"],
            available_time=extra["available_time"],
            time_precision=extra["time_precision"],
        )
        boundary["event_assignments"].append(injected)
        boundary["event_assignments"].sort(key=lambda row: row["event_id"])
        boundary["counts"]["assigned_events"] += 1
        resign_boundary(boundary)
        with self.assertRaisesRegex(BoundarySnapshotError, "does not belong"):
            authenticate_boundary_context(
                [*events, extra],
                boundary_manifest=boundary,
                reference_secret=b"r" * 32,
                expected_protocol_lock_sha256=self.protocol_lock["protocol_lock_sha256"],
                expected_public_manifest_sha256=self.split["protected_mapping"]["public_manifest_sha256"],
                expected_source_inputs_sha256=boundary["source_inputs_sha256"],
            )

    def test_context_scans_and_authenticates_source_events_once_for_reuse(self) -> None:
        events = self._source_events()
        boundary = self._boundary(events)
        visits = 0

        def source():
            nonlocal visits
            for event in events:
                visits += 1
                yield event

        context = authenticate_boundary_context(
            source(),
            boundary_manifest=boundary,
            reference_secret=b"r" * 32,
            expected_protocol_lock_sha256=self.protocol_lock["protocol_lock_sha256"],
            expected_public_manifest_sha256=boundary["split_lineage"]["public_manifest_sha256"],
            expected_source_inputs_sha256=boundary["source_inputs_sha256"],
        )
        representation = repr(context)
        self.assertNotIn("rrrrrrrr", representation)
        self.assertNotIn(events[0]["event_id"], representation)
        journey_id = boundary["journeys"][0]["journey_id"]
        context.build_snapshot(
            journey_id,
            operation="rule_discovery",
            index_time="2026-01-01T10:00:00",
            policy=self._policy(),
        )
        context.build_snapshot(
            journey_id,
            operation="rule_discovery",
            index_time="2026-01-01T10:00:00",
            policy=self._policy(),
        )
        self.assertEqual(visits, len(events))

    def test_context_isolated_from_post_authentication_input_mutation(self) -> None:
        events = self._source_events()
        boundary = self._boundary(events)
        context = authenticate_boundary_context(
            events,
            boundary_manifest=boundary,
            reference_secret=b"r" * 32,
            expected_protocol_lock_sha256=self.protocol_lock["protocol_lock_sha256"],
            expected_public_manifest_sha256=boundary["split_lineage"]["public_manifest_sha256"],
            expected_source_inputs_sha256=boundary["source_inputs_sha256"],
        )
        journey_id = boundary["journeys"][0]["journey_id"]
        before = context.build_snapshot(
            journey_id,
            operation="rule_discovery",
            index_time="2026-01-01T10:00:00",
            policy=self._policy(),
        )
        events[0]["quality_flags"].append("post-auth-mutation")
        boundary["journeys"][0]["discharge_time"] = "2099-01-01T00:00:00"
        after = context.build_snapshot(
            journey_id,
            operation="rule_discovery",
            index_time="2026-01-01T10:00:00",
            policy=self._policy(),
        )
        self.assertEqual(before, after)
        with self.assertRaises(TypeError):
            context._event_records_by_journey[journey_id] = ()
        with self.assertRaises(TypeError):
            context._source_lineage_base["subject_role"] = "final_test"

    def test_audit_rejects_signed_window_duplicate_and_count_attacks(self) -> None:
        boundary = self._boundary()
        snapshot = self._build(boundary=boundary)

        outside = copy.deepcopy(snapshot)
        outside["index_time"] = "2026-01-01T12:00:01.000000"
        resign_snapshot(outside)
        self.assertFalse(self._audit(outside, boundary)["valid"])

        aware = copy.deepcopy(snapshot)
        aware["index_time"] = "2026-01-01T10:00:00+00:00"
        resign_snapshot(aware)
        aware_report = self._audit(aware, boundary)
        self.assertFalse(aware_report["valid"])
        self.assertTrue(
            any("naive MIMIC timeline" in error for error in aware_report["errors"])
        )

        duplicated = copy.deepcopy(snapshot)
        duplicated["events"].append(copy.deepcopy(duplicated["events"][0]))
        duplicated["counts"]["total"] += 1
        duplicated["counts"]["visible"] += 1
        resign_snapshot(duplicated)
        report = self._audit(duplicated, boundary)
        self.assertFalse(report["valid"])
        self.assertIn("duplicate snapshot event_id", report["errors"])

        wrong_counts = copy.deepcopy(snapshot)
        wrong_counts["counts"]["visible"] = 99
        resign_snapshot(wrong_counts)
        self.assertIn(
            "snapshot counts do not match event decisions",
            self._audit(wrong_counts, boundary)["errors"],
        )


if __name__ == "__main__":
    unittest.main()
