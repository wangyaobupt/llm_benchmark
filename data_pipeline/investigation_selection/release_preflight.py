"""W10 reproducibility and final-test release preflight gates."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Iterable, Mapping


class ReleasePreflightError(ValueError):
    pass


@dataclass(frozen=True)
class PreflightResult:
    ready: bool
    blockers: tuple[str, ...]
    manifest: Mapping[str, Any]


def _hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def audit_release_inputs(*, protocol: Mapping[str, Any], split: Mapping[str, Any], artifacts: Mapping[str, Any], final_test_subjects: Iterable[str], final_test_run_count: int = 0, mode: str = "official") -> PreflightResult:
    if mode not in {"official", "rehearsal"}:
        raise ReleasePreflightError("mode must be official or rehearsal")
    blockers: list[str] = []
    if mode == "official" and protocol.get("status") != "frozen":
        blockers.append("PROTOCOL_NOT_FROZEN")
    if mode == "official" and not protocol.get("protocol_lock_sha256"):
        blockers.append("PROTOCOL_LOCK_HASH_MISSING")
    roles = {str(key): {str(value) for value in values} for key, values in split.get("roles", {}).items()}
    if not roles.get("development") or not roles.get("validation") or not roles.get("final_test"):
        blockers.append("SPLIT_ROLE_EMPTY")
    role_names = ("development", "validation", "final_test")
    for index, left in enumerate(role_names):
        for right in role_names[index + 1:]:
            if roles.get(left, set()) & roles.get(right, set()):
                blockers.append("SPLIT_SUBJECT_OVERLAP")
    if split.get("previous_exposure_none") != len(roles.get("final_test", set())):
        blockers.append("FINAL_TEST_PRIOR_EXPOSURE_UNPROVEN")
    required_artifacts = {"protocol", "catalog", "panel", "diagnosis", "feature_whitelist"}
    if not required_artifacts <= set(artifacts):
        blockers.append("ARTIFACT_MANIFEST_INCOMPLETE")
    final_subjects = {str(subject) for subject in final_test_subjects if str(subject)}
    if not final_subjects:
        blockers.append("FINAL_TEST_SUBJECTS_EMPTY")
    if mode == "rehearsal" and any(not subject.startswith("fixture:") for subject in final_subjects):
        blockers.append("REHEARSAL_NON_FIXTURE_SUBJECT")
    if final_test_run_count != 0:
        blockers.append("FINAL_TEST_ALREADY_RUN_OR_RUN_STATE_INVALID")
    manifest = {"mode": mode, "official_final_test": mode == "official", "protocol_lock_sha256": protocol.get("protocol_lock_sha256"), "split_sha256": _hash(split), "artifact_sha256": _hash(artifacts), "final_test_subjects_sha256": _hash(sorted(final_subjects)), "final_test_run_count": final_test_run_count, "final_test_read": False, "tuning_after_final_test": False, "gold_mutation_allowed": False if mode == "rehearsal" else True}
    return PreflightResult(not blockers, tuple(dict.fromkeys(blockers)), manifest)


def assert_release_ready(result: PreflightResult) -> None:
    if not result.ready:
        raise ReleasePreflightError("release blocked: " + ", ".join(result.blockers))


def record_final_test_run(*, result: PreflightResult, metrics: Mapping[str, Any], tuning_after_run: bool = False) -> dict[str, Any]:
    assert_release_ready(result)
    if tuning_after_run:
        raise ReleasePreflightError("final-test metrics cannot flow back into tuning")
    return {"run_count": 1, "metrics": dict(metrics), "preflight_manifest": dict(result.manifest), "final_test_single_run": True, "official_final_test": bool(result.manifest.get("official_final_test")), "gold_mutated": False if result.manifest.get("mode") == "rehearsal" else False, "tuning_after_final_test": False}
