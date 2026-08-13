from __future__ import annotations

import copy
from contextlib import redirect_stdout
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from evaluation_pipeline.governance.protocol import (
    ProtocolBundleError,
    build_protocol_lock,
    load_protocol_bundle,
    semantic_sha256,
    validate_protocol_bundle,
)
from evaluation_pipeline.governance.__main__ import main as governance_main


ROOT = Path(__file__).resolve().parents[1]


class EvaluationProtocolTest(unittest.TestCase):
    @staticmethod
    def _file_sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

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
        scientific["patient_journey_scope"]["linked_pre_admission_ed"] = "include_native_hadm_handoff"
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
            "source_git_commit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "dependency_lock_sha256": self._file_sha256(ROOT / "uv.lock"),
            "input_manifest_sha256": {
                "tests/fixtures/event-cleaning-regression.json": self._file_sha256(
                    ROOT / "tests/fixtures/event-cleaning-regression.json"
                )
            },
        }
        handle = tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", encoding="utf-8", delete=False
        )
        path = Path(handle.name)
        with handle:
            handle.write(yaml.safe_dump(protocol, sort_keys=False))
        self.addCleanup(path.unlink, missing_ok=True)
        frozen = load_protocol_bundle(
            path,
            ROOT / "schemas/investigation-selection-protocol.schema.json",
            ROOT / "config/investigation-selection/reason-code-registry.yaml",
        )
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

    def test_empty_scientific_section_and_construct_swap_are_rejected(self) -> None:
        bundle = self._bundle()
        bundle["protocol"] = copy.deepcopy(bundle["protocol"])
        bundle["protocol"]["scientific_protocol"]["task_definition"] = {}
        self.assertFalse(validate_protocol_bundle(bundle)["valid"])

        bundle = self._bundle()
        bundle["protocol"] = copy.deepcopy(bundle["protocol"])
        constructs = bundle["protocol"]["scientific_protocol"]["construct_registry"]
        constructs[0]["gold_field"], constructs[1]["gold_field"] = (
            constructs[1]["gold_field"], constructs[0]["gold_field"]
        )
        self.assertFalse(validate_protocol_bundle(bundle)["valid"])

    def test_lock_rejects_in_memory_or_on_disk_source_drift(self) -> None:
        bundle = self._frozen_bundle()
        mutated = copy.deepcopy(bundle)
        mutated["protocol"]["runtime_configuration"]["threads"] = 99
        with self.assertRaisesRegex(ProtocolBundleError, "differs from its loaded source"):
            build_protocol_lock(mutated)

        bundle = self._frozen_bundle()
        bundle["paths"]["protocol"].write_text("protocol_status: draft\n", encoding="utf-8")
        with self.assertRaisesRegex(ProtocolBundleError, "source file changed"):
            build_protocol_lock(bundle)

    def test_nonsense_policies_and_invalid_statistical_ranges_are_rejected(self) -> None:
        bundle = self._bundle()
        bundle["protocol"] = copy.deepcopy(bundle["protocol"])
        scientific = bundle["protocol"]["scientific_protocol"]
        scientific["task_definition"]["tie_policy"] = "banana"
        scientific["hypothesis_space"]["pre_fdr_allowed_filters"] = ["p_value"]
        scientific["statistical_policy"]["fdr_q"] = 1
        scientific["statistical_policy"]["score_ratio_minimum"] = 0.1
        report = validate_protocol_bundle(bundle)
        self.assertFalse(report["valid"])
        self.assertGreaterEqual(len(report["errors"]), 4)

    def test_registry_schema_is_enforced_by_governance(self) -> None:
        bundle = self._bundle()
        bundle["reason_registry"] = copy.deepcopy(bundle["reason_registry"])
        bundle["reason_registry"]["codes"].append({
            "code": "_INVALID_LEADING_UNDERSCORE",
            "stage": "journey",
            "description": "invalid fixture",
        })
        report = validate_protocol_bundle(bundle)
        self.assertFalse(report["valid"])
        self.assertTrue(any("registry_schema" in error for error in report["errors"]))

    def test_frozen_protocol_rejects_fake_audit_evidence(self) -> None:
        cases = (
            ("source_git_commit", "a" * 40, "source_git_commit"),
            ("dependency_lock_sha256", "b" * 64, "dependency_lock_sha256"),
        )
        for field, value, marker in cases:
            with self.subTest(field=field):
                bundle = self._frozen_bundle()
                bundle["protocol"]["audit_metadata"][field] = value
                report = validate_protocol_bundle(bundle)
                self.assertFalse(report["freeze_ready"])
                self.assertTrue(
                    any(marker in item for item in report["freeze_blockers"])
                )

        bundle = self._frozen_bundle()
        path = next(
            iter(bundle["protocol"]["audit_metadata"]["input_manifest_sha256"])
        )
        bundle["protocol"]["audit_metadata"]["input_manifest_sha256"][path] = (
            "c" * 64
        )
        report = validate_protocol_bundle(bundle)
        self.assertFalse(report["freeze_ready"])
        self.assertTrue(
            any("input_manifest_sha256" in item for item in report["freeze_blockers"])
        )

        bundle = self._frozen_bundle()
        bundle["protocol"]["audit_metadata"]["input_manifest_sha256"] = {
            "../outside.json": "c" * 64
        }
        report = validate_protocol_bundle(bundle)
        self.assertTrue(
            any("input_manifest_path_invalid" in item for item in report["freeze_blockers"])
        )

    def test_invalid_schema_returns_structured_failure(self) -> None:
        bundle = self._bundle()
        bundle["schema"] = {"type": "not-a-json-schema-type"}
        report = validate_protocol_bundle(bundle)
        self.assertFalse(report["valid"])
        self.assertFalse(report["freeze_ready"])
        self.assertTrue(any("invalid_json_schema:protocol" in error for error in report["errors"]))

        bundle = self._bundle()
        bundle["reason_registry_schema"] = {"$ref": "#/$defs/missing"}
        report = validate_protocol_bundle(bundle)
        self.assertFalse(report["valid"])
        self.assertTrue(any("invalid_json_schema:reason_registry" in error for error in report["errors"]))

    def test_validate_cli_returns_nonzero_for_invalid_protocol(self) -> None:
        handle = tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", encoding="utf-8", delete=False
        )
        path = Path(handle.name)
        with handle:
            handle.write("{}\n")
        self.addCleanup(path.unlink, missing_ok=True)
        argv = [
            "evaluation-governance",
            "validate",
            "--protocol",
            str(path),
            "--schema",
            str(ROOT / "schemas/investigation-selection-protocol.schema.json"),
            "--reason-registry",
            str(ROOT / "config/investigation-selection/reason-code-registry.yaml"),
        ]
        with patch.object(sys, "argv", argv):
            with redirect_stdout(io.StringIO()):
                self.assertEqual(governance_main(), 1)


if __name__ == "__main__":
    unittest.main()
