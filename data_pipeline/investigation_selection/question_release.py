"""W9 fail-closed question construction, review, and gold release contracts."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Iterable, Mapping


class QuestionReleaseError(ValueError):
    pass


LEGACY_RULE_IDS = frozenset({"legacy_134", "v1", "v0.1"})
DECISION_EVIDENCE_FIELDS = frozenset({"event_id", "feature", "occurrence_time", "available_time", "visibility_status"})


@dataclass(frozen=True)
class QuestionValidation:
    question_id: str
    valid: bool
    reasons: tuple[str, ...]
    question_hash: str


def _hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_candidate_question(*, rule: Mapping[str, Any], decision: Mapping[str, Any], stem: str, options: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rule_id = str(rule.get("rule_id", ""))
    if not rule_id or rule_id in LEGACY_RULE_IDS or rule.get("validation_status") != "validated":
        raise QuestionReleaseError("only validated non-legacy rules may create questions")
    if rule.get("track_id") != decision.get("track_id") or rule.get("candidate_class") != decision.get("candidate_class"):
        raise QuestionReleaseError("rule and decision track/class mismatch")
    evidence = []
    for item in decision.get("decision_evidence", ()):
        unknown = set(item) - DECISION_EVIDENCE_FIELDS
        if unknown:
            raise QuestionReleaseError(f"decision evidence contains non-whitelisted fields: {sorted(unknown)}")
        evidence.append(dict(item))
    if not evidence:
        raise QuestionReleaseError("decision evidence cannot be empty")
    options_list = [dict(option) for option in options]
    answer_id = str(rule.get("selected_candidate_id", ""))
    if len({str(option.get("candidate_id", "")) for option in options_list}) != len(options_list) or answer_id not in {str(option.get("candidate_id", "")) for option in options_list}:
        raise QuestionReleaseError("options must contain one unique rule-selected answer")
    question_id = str(rule_id) + ":" + str(decision.get("decision_id", ""))
    body = {"question_id": question_id, "rule_id": rule_id, "decision_id": decision.get("decision_id"), "subject_ref": decision.get("subject_ref"), "track_id": rule.get("track_id"), "candidate_class": rule.get("candidate_class"), "stem": str(stem), "options": options_list, "answer_candidate_id": answer_id, "decision_evidence": evidence, "protocol_lock_sha256": decision.get("protocol_lock_sha256"), "subject_split_manifest_sha256": decision.get("subject_split_manifest_sha256"), "rule_lineage_sha256": rule.get("rule_lineage_sha256"), "gold_status": "zero_unapproved"}
    body["question_sha256"] = _hash(body)
    return body


def validate_question(question: Mapping[str, Any], *, allowed_rule_ids: Iterable[str], legacy_rule_ids: Iterable[str] = ()) -> QuestionValidation:
    reasons: list[str] = []
    rule_id = str(question.get("rule_id", ""))
    if rule_id not in set(allowed_rule_ids):
        reasons.append("RULE_NOT_VALIDATED")
    if rule_id in LEGACY_RULE_IDS or rule_id in set(legacy_rule_ids):
        reasons.append("LEGACY_RULE_FORBIDDEN")
    options = list(question.get("options", ()))
    candidate_ids = [str(option.get("candidate_id", "")) for option in options]
    if len(candidate_ids) != len(set(candidate_ids)) or str(question.get("answer_candidate_id", "")) not in set(candidate_ids):
        reasons.append("ANSWER_NOT_UNIQUE_OR_ABSENT")
    if question.get("track_id") != question.get("candidate_class") and not question.get("track_id"):
        reasons.append("TRACK_MISSING")
    if not question.get("decision_evidence"):
        reasons.append("DECISION_EVIDENCE_MISSING")
    if not question.get("protocol_lock_sha256") or not question.get("rule_lineage_sha256"):
        reasons.append("LINEAGE_HASH_MISSING")
    body = dict(question)
    supplied_hash = body.pop("question_sha256", None)
    expected_hash = _hash(body)
    if supplied_hash != expected_hash:
        reasons.append("QUESTION_HASH_MISMATCH")
    return QuestionValidation(str(question.get("question_id", "")), not reasons, tuple(reasons), expected_hash)


def review_record(*, question_id: str, reviewer_id: str, review_type: str, checks: Mapping[str, bool], signed: bool) -> dict[str, Any]:
    allowed = {"independent_program", "clinical"}
    if review_type not in allowed or not reviewer_id or not question_id:
        raise QuestionReleaseError("invalid review identity or type")
    required = {"factual_correctness", "time_visibility", "comparison_reasonable", "behavior_normative_boundary", "answer_unique"}
    missing = required - set(checks)
    if missing:
        raise QuestionReleaseError(f"review checks missing: {sorted(missing)}")
    return {"question_id": question_id, "reviewer_id": reviewer_id, "review_type": review_type, "checks": dict(checks), "signed": bool(signed), "approved": bool(signed and all(checks.values()))}


def release_gold(question: Mapping[str, Any], *, program_review: Mapping[str, Any], clinical_review: Mapping[str, Any], gold_type: str) -> dict[str, Any]:
    if gold_type not in {"pattern_rule_concordance", "clinical_best_decision"}:
        raise QuestionReleaseError("unknown gold type")
    if not program_review.get("approved") or program_review.get("review_type") != "independent_program":
        raise QuestionReleaseError("independent program review is required")
    if not clinical_review.get("approved") or clinical_review.get("review_type") != "clinical":
        raise QuestionReleaseError("signed clinical review is required")
    if gold_type == "clinical_best_decision" and clinical_review.get("normative_source") is None:
        raise QuestionReleaseError("normative source and expert adjudication are required")
    label = "MIMIC 观察数据中同类最可能选择" if gold_type == "pattern_rule_concordance" else "clinical_best_decision"
    return {"question_id": question.get("question_id"), "gold_type": gold_type, "label": label, "gold_status": "approved"}
