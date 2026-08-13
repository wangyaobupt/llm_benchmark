from __future__ import annotations

import copy
import hashlib
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from evaluation_pipeline.governance import build_protocol_lock
from evaluation_pipeline.subject_split import (
    SubjectSplitError,
    audit_subject_split,
    build_subject_split,
)
from tests.protocol_fixtures import frozen_protocol_bundle


ROOT = Path(__file__).resolve().parents[1]


class SubjectSplitTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.protocol_bundle = frozen_protocol_bundle(ROOT, cls.addClassCleanup)
        cls.protocol_lock = build_protocol_lock(cls.protocol_bundle)

    def _config(self, **overrides: object) -> dict:
        config = {
            "split_id": "synthetic-split-v1",
            "protocol_bundle": self.protocol_bundle,
            "protocol_lock": self.protocol_lock,
            "ratios": {
                "development": 0.6,
                "validation": 0.2,
                "final_test": 0.2,
            },
            "assignment_seed": "synthetic-seed",
            "subject_ref_key_id": "test-key",
            "subject_ref_secret": b"test-only-secret-material-32-bytes!",
        }
        config.update(overrides)
        return config

    def _artifacts(self, config: dict | None = None) -> dict:
        return build_subject_split(
            range(1, 21),
            [901, 902],
            config or self._config(),
        )

    def test_build_is_patient_atomic_order_invariant_and_schema_valid(self) -> None:
        first = self._artifacts()
        second = build_subject_split(
            reversed(range(1, 21)),
            [902, 901],
            self._config(),
        )
        self.assertEqual(first, second)
        self.assertTrue(first["audit_report"]["valid"])

        schema = json.loads(
            (ROOT / "schemas/subject-split-manifest.schema.json").read_text(
                encoding="utf-8"
            )
        )
        errors = list(
            Draft202012Validator(schema).iter_errors(first["public_manifest"])
        )
        self.assertEqual(errors, [])
        protected_schema = json.loads(
            (ROOT / "schemas/protected-subject-map.schema.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            list(
                Draft202012Validator(protected_schema).iter_errors(
                    first["protected_mapping"]
                )
            ),
            [],
        )
        refs = [row["subject_ref"] for row in first["public_manifest"]["assignments"]]
        self.assertEqual(len(refs), len(set(refs)))
        self.assertNotIn("subject_id", json.dumps(first["public_manifest"]))
        raw_rows = [
            {
                "subject_id": {
                    "type": type(row["subject_id"]).__name__,
                    "value": row["subject_id"],
                },
                "subject_role": row["subject_role"],
            }
            for row in first["protected_mapping"]["records"]
        ]
        raw_rows.sort(
            key=lambda value: json.dumps(
                value, sort_keys=True, separators=(",", ":")
            )
        )
        raw_identifier_fingerprint = hashlib.sha256(
            json.dumps(
                raw_rows,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        self.assertNotEqual(
            first["public_manifest"]["input_population_sha256"],
            raw_identifier_fingerprint,
        )

    def test_engineering_audit_is_isolated_and_raw_ids_are_protected(self) -> None:
        artifacts = self._artifacts()
        public = artifacts["public_manifest"]
        engineering = [
            row for row in public["assignments"]
            if row["subject_role"] == "engineering_audit"
        ]
        self.assertEqual(len(engineering), 2)
        self.assertTrue(all(not row["formal_test_eligible"] for row in engineering))
        self.assertEqual(
            {row["subject_id"] for row in artifacts["protected_mapping"]["records"]},
            {*range(1, 21), 901, 902},
        )

    def test_ratios_are_explicit_positive_and_sum_to_one(self) -> None:
        missing = self._config(ratios={"development": 0.8, "final_test": 0.2})
        with self.assertRaisesRegex(SubjectSplitError, "explicitly contain"):
            self._artifacts(missing)
        invalid_sum = self._config(
            ratios={"development": 0.5, "validation": 0.2, "final_test": 0.2}
        )
        with self.assertRaisesRegex(SubjectSplitError, "sum to 1"):
            self._artifacts(invalid_sum)

    def test_subject_reference_secret_requires_32_bytes(self) -> None:
        with self.assertRaisesRegex(SubjectSplitError, "at least 32 bytes"):
            self._artifacts(self._config(subject_ref_secret="short-secret"))

    def test_fake_or_rebound_protocol_lock_fails_before_split_construction(self) -> None:
        fake = dict(self.protocol_lock)
        fake["protocol_lock_sha256"] = "0" * 64
        with self.assertRaisesRegex(SubjectSplitError, "protocol lock verification failed"):
            self._artifacts(self._config(protocol_lock=fake))

        with self.assertRaisesRegex(SubjectSplitError, "complete protocol_lock"):
            self._artifacts(self._config(protocol_bundle=None, protocol_lock=None))

    def test_duplicate_overlap_and_empty_partition_inputs_fail_closed(self) -> None:
        with self.assertRaisesRegex(SubjectSplitError, "duplicate subject_id"):
            build_subject_split([1, 1, 2, 3], [], self._config())
        with self.assertRaisesRegex(SubjectSplitError, "must not appear"):
            build_subject_split([1, 2, 3], [3], self._config())
        with self.assertRaisesRegex(SubjectSplitError, "at least 3"):
            build_subject_split([1, 2], [], self._config())

    def test_expected_fingerprint_detects_input_drift(self) -> None:
        baseline = self._artifacts()
        fingerprint = baseline["public_manifest"]["input_population_sha256"]
        locked = self._artifacts(self._config(expected_input_sha256=fingerprint))
        self.assertEqual(locked["audit_report"]["input_drift"]["status"], "unchanged")
        with self.assertRaisesRegex(SubjectSplitError, "input population drift"):
            build_subject_split(
                range(1, 22),
                [901, 902],
                self._config(expected_input_sha256=fingerprint),
            )

    def test_independent_audit_rejects_cross_partition_duplicate_and_tampering(self) -> None:
        artifacts = self._artifacts()
        public = copy.deepcopy(artifacts["public_manifest"])
        protected = copy.deepcopy(artifacts["protected_mapping"])
        duplicate = dict(public["assignments"][0])
        duplicate["subject_role"] = "final_test"
        public["assignments"].append(duplicate)
        report = audit_subject_split(
            public, protected, subject_ref_secret=self._config()["subject_ref_secret"]
        )
        self.assertFalse(report["valid"])
        self.assertTrue(
            any("across partitions" in error for error in report["errors"])
        )
        self.assertTrue(any("duplicate public" in error for error in report["errors"]))

    def test_audit_detects_protected_input_role_change(self) -> None:
        artifacts = self._artifacts()
        public = copy.deepcopy(artifacts["public_manifest"])
        protected = copy.deepcopy(artifacts["protected_mapping"])
        row = next(
            item for item in protected["records"]
            if item["subject_role"] != "engineering_audit"
        )
        row["subject_role"] = "engineering_audit"
        report = audit_subject_split(
            public, protected, subject_ref_secret=self._config()["subject_ref_secret"]
        )
        self.assertFalse(report["valid"])
        self.assertIn(
            "input_population_sha256 does not match protected mapping", report["errors"]
        )
        self.assertIn(
            "public assignments and protected mapping do not match", report["errors"]
        )

    def test_audit_rejects_public_subject_id_leakage_and_split_mismatch(self) -> None:
        artifacts = self._artifacts()
        public = copy.deepcopy(artifacts["public_manifest"])
        protected = copy.deepcopy(artifacts["protected_mapping"])
        public["assignments"][0]["subject_id"] = 1
        protected["split_id"] = "different-split"
        report = audit_subject_split(
            public, protected, subject_ref_secret=self._config()["subject_ref_secret"]
        )
        self.assertFalse(report["valid"])
        self.assertIn("public manifest exposes subject_id", report["errors"])
        self.assertIn(
            "public and protected split_id values do not match", report["errors"]
        )

    def test_protected_subject_binding_swap_fails_hmac_audit(self) -> None:
        artifacts = self._artifacts()
        protected = copy.deepcopy(artifacts["protected_mapping"])
        formal = [
            row for row in protected["records"]
            if row["subject_role"] in {"development", "final_test"}
        ]
        formal[0]["subject_id"], formal[1]["subject_id"] = (
            formal[1]["subject_id"], formal[0]["subject_id"]
        )
        report = audit_subject_split(
            artifacts["public_manifest"],
            protected,
            subject_ref_secret=self._config()["subject_ref_secret"],
        )
        self.assertFalse(report["valid"])
        self.assertIn("subject split artifact HMAC mismatch", report["errors"])

    def test_protected_mapping_requires_matching_secret_and_key_id(self) -> None:
        artifacts = self._artifacts()
        wrong_secret_report = audit_subject_split(
            artifacts["public_manifest"],
            artifacts["protected_mapping"],
            subject_ref_secret=b"different-test-secret-material-32!",
        )
        self.assertFalse(wrong_secret_report["valid"])
        self.assertIn("subject split artifact HMAC mismatch", wrong_secret_report["errors"])

        protected = copy.deepcopy(artifacts["protected_mapping"])
        protected["subject_ref_key_id"] = "different-key"
        key_id_report = audit_subject_split(
            artifacts["public_manifest"],
            protected,
            subject_ref_secret=self._config()["subject_ref_secret"],
        )
        self.assertFalse(key_id_report["valid"])
        self.assertIn(
            "public and protected subject_ref_key_id values do not match",
            key_id_report["errors"],
        )

    def test_public_lineage_rewrite_fails_artifact_hmac(self) -> None:
        artifacts = self._artifacts()
        public = copy.deepcopy(artifacts["public_manifest"])
        protected = copy.deepcopy(artifacts["protected_mapping"])
        public["protocol_lock_sha256"] = "0" * 64
        protected["protocol_lock_sha256"] = "0" * 64
        protected["public_manifest_sha256"] = hashlib.sha256(
            json.dumps(
                public,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        report = audit_subject_split(
            public,
            protected,
            subject_ref_secret=self._config()["subject_ref_secret"],
        )
        self.assertFalse(report["valid"])
        self.assertIn("subject split artifact HMAC mismatch", report["errors"])


if __name__ == "__main__":
    unittest.main()
