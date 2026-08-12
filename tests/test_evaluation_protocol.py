from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

import yaml

from evaluation_pipeline.governance.protocol import (
    ProtocolBundleError,
    build_protocol_lock,
    load_protocol_bundle,
    semantic_sha256,
    validate_protocol_bundle,
)


ROOT = Path(__file__).resolve().parents[1]


class EvaluationProtocolTest(unittest.TestCase):
    def _bundle(self) -> dict:
        return load_protocol_bundle(
            ROOT / "config/investigation-selection/protocol.yaml",
            ROOT / "schemas/investigation-selection-protocol.schema.json",
            ROOT / "config/investigation-selection/reason-code-registry.yaml",
        )

    def _frozen_bundle(self) -> dict:
        bundle = self._bundle()
        protocol = copy.deepcopy(bundle["protocol"])
        protocol["protocol_status"] = "frozen"
        protocol["unresolved_decisions"] = []
        scientific = protocol["scientific_protocol"]
        scientific["patient_journey_scope"]["linked_pre_admission_ed"] = "include_when_hadm_linked"
        scientific["patient_journey_scope"]["standalone_ed"] = "exclude_first_release"
        scientific["subject_split"]["ratios"] = {
            "development": 0.7,
            "validation": 0.15,
            "final_test": 0.15,
        }
        scientific["task_definition"]["observation_window"]["start_minutes_before_index"] = -1440
        scientific["task_definition"]["target_window"]["end_minutes_after_index"] = 360
        scientific["task_definition"].update(
            tie_policy="reject_item",
            missing_policy="inconclusive",
            zero_denominator_policy="inconclusive",
            refusal_policy="allowed_when_no_eligible_candidate",
        )
        scientific["hypothesis_space"].update(
            condition_generator_ref="condition-generator/1.0.0",
            candidate_catalog_ref="investigation-catalog/1.0.0",
            comparison_class_catalog_ref="comparison-class/1.0.0",
        )
        scientific["statistical_policy"].update(
            fdr_q=0.05,
            minimum_condition_support=5,
            minimum_candidate_support=5,
            minimum_joint_support_post_fdr=4,
            wilson_lower_bound_minimum=0.35,
            probability_gap_minimum=0.15,
            score_ratio_minimum=1.25,
        )
        scientific["validation_policy"].update(
            bootstrap_replicates=1000,
            stability_minimum=0.8,
        )
        protocol["audit_metadata"] = {
            "source_git_commit": "a" * 40,
            "dependency_lock_sha256": "b" * 64,
            "input_manifest_sha256": {"normalized_events": "c" * 64},
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "protocol.yaml"
            path.write_text(yaml.safe_dump(protocol, sort_keys=False), encoding="utf-8")
            frozen = load_protocol_bundle(
                path,
                ROOT / "schemas/investigation-selection-protocol.schema.json",
                ROOT / "config/investigation-selection/reason-code-registry.yaml",
            )
            frozen["paths"]["protocol"] = path
            # The temporary source must outlive callers, so materialize source bytes.
            frozen["_protocol_source_bytes"] = path.read_bytes()
            frozen["paths"] = dict(bundle["paths"])
            frozen["paths"]["protocol"] = ROOT / "config/investigation-selection/protocol.yaml"
        frozen["protocol"] = protocol
        return frozen

    def test_repository_protocol_is_valid_draft_and_not_freeze_ready(self) -> None:
        report = validate_protocol_bundle(self._bundle())
        self.assertTrue(report["valid"])
        self.assertFalse(report["freeze_ready"])
        self.assertIn("formal_subject_split_ratios", report["freeze_blockers"])
        self.assertTrue(any("target_window" in item for item in report["freeze_blockers"]))

    def test_lock_refuses_unresolved_draft(self) -> None:
        with self.assertRaises(ProtocolBundleError):
            build_protocol_lock(self._bundle())

    def test_frozen_protocol_requires_complete_audit_metadata(self) -> None:
        bundle = self._frozen_bundle()
        bundle["protocol"]["audit_metadata"]["input_manifest_sha256"] = {}
        report = validate_protocol_bundle(bundle)
        self.assertFalse(report["freeze_ready"])
        self.assertIn(
            "AUDIT_METADATA:input_manifest_sha256", report["freeze_blockers"]
        )

    def test_frozen_bundle_has_stable_scientific_and_lock_hashes(self) -> None:
        bundle = self._frozen_bundle()
        first = build_protocol_lock(bundle)
        second = build_protocol_lock(bundle)
        self.assertEqual(first, second)
        self.assertEqual(
            first["scientific_protocol_sha256"],
            semantic_sha256(bundle["protocol"]["scientific_protocol"]),
        )

    def test_construct_gold_fields_must_be_distinct(self) -> None:
        bundle = self._bundle()
        bundle["protocol"] = copy.deepcopy(bundle["protocol"])
        constructs = bundle["protocol"]["scientific_protocol"]["construct_registry"]
        constructs[1]["gold_field"] = constructs[0]["gold_field"]
        report = validate_protocol_bundle(bundle)
        self.assertFalse(report["valid"])
        self.assertIn("construct gold_field values must be unique", report["errors"])

    def test_unknown_reason_code_fails_validation(self) -> None:
        bundle = self._bundle()
        bundle["protocol"] = copy.deepcopy(bundle["protocol"])
        bundle["protocol"]["scientific_protocol"]["validation_policy"][
            "tie_reason_code"
        ] = "UNKNOWN_CODE"
        report = validate_protocol_bundle(bundle)
        self.assertFalse(report["valid"])
        self.assertTrue(any("UNKNOWN_CODE" in error for error in report["errors"]))


if __name__ == "__main__":
    unittest.main()
