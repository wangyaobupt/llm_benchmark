"""Stable content-addressed ID derivation (design doc §5.2, §11).

IDs are deterministic hashes over canonical content so that identical rules /
candidates produce identical IDs across runs (reproducibility), while content
changes produce new IDs (which is what invalidates stale human approvals).
"""
from __future__ import annotations

import hashlib

from .constants import (
    CANDIDATE_ID_PREFIX,
    ID_HASH_HEX,
    QUESTION_ID_PREFIX,
    RULE_ID_PREFIX,
)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def candidate_id(comparison_class: str, canonical_name: str) -> str:
    """Stable candidate ID: cand_ + sha256(class + ':' + casefolded name)."""
    payload = f"{comparison_class}:{canonical_name.casefold()}"
    return CANDIDATE_ID_PREFIX + sha256_hex(payload)[:ID_HASH_HEX]


def feature_id(display_name: str) -> str:
    """Stable feature ID: symptom:<hash16> (current feature space is symptoms)."""
    return "symptom:" + sha256_hex(display_name.casefold())[:16]


def rule_id(condition_feature_ids: list[str], target_investigation_id: str) -> str:
    """rule_ + sha256(sorted feature ids joined + target id)."""
    payload = "|".join(sorted(condition_feature_ids)) + "|" + target_investigation_id
    return RULE_ID_PREFIX + sha256_hex(payload)[:ID_HASH_HEX]


def question_id(source_rule_id: str) -> str:
    """iq_ + sha256('question' + rule_id)."""
    return QUESTION_ID_PREFIX + sha256_hex("question" + source_rule_id)[:ID_HASH_HEX]
