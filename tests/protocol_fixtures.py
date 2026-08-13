from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import subprocess
import tempfile
from typing import Callable

import yaml

from evaluation_pipeline.governance import load_protocol_bundle


def frozen_protocol_bundle(
    root: Path,
    add_cleanup: Callable[..., object],
) -> dict:
    """Build a freeze-ready synthetic bundle backed by real repository evidence."""
    source = load_protocol_bundle(
        root / "config/investigation-selection/protocol.yaml",
        root / "schemas/investigation-selection-protocol.schema.json",
        root / "config/investigation-selection/reason-code-registry.yaml",
    )
    protocol = copy.deepcopy(source["protocol"])
    protocol["protocol_status"] = "frozen"
    protocol["unresolved_decisions"] = []
    scientific = protocol["scientific_protocol"]
    scientific["patient_journey_scope"].update(
        linked_pre_admission_ed="include_native_hadm_handoff",
        standalone_ed="exclude_first_release",
    )
    scientific["subject_split"]["ratios"] = {
        "development": 0.7,
        "validation": 0.15,
        "final_test": 0.15,
    }
    scientific["task_definition"]["observation_window"][
        "start_minutes_before_index"
    ] = -1440
    scientific["task_definition"]["target_window"][
        "end_minutes_after_index"
    ] = 360
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
    file_sha256 = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    protocol["audit_metadata"] = {
        "source_git_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip(),
        "dependency_lock_sha256": file_sha256(root / "uv.lock"),
        "input_manifest_sha256": {
            "tests/fixtures/event-cleaning-regression.json": file_sha256(
                root / "tests/fixtures/event-cleaning-regression.json"
            )
        },
    }
    handle = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", encoding="utf-8", delete=False
    )
    path = Path(handle.name)
    with handle:
        handle.write(yaml.safe_dump(protocol, sort_keys=False))
    add_cleanup(path.unlink, missing_ok=True)
    return load_protocol_bundle(
        path,
        root / "schemas/investigation-selection-protocol.schema.json",
        root / "config/investigation-selection/reason-code-registry.yaml",
    )
