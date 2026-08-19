"""Version and stable reason-code constants for the v2 MCQ pipeline.

Every error / rejection code is a stable, machine-readable string so that a run
can be aggregated by failure cause and audited against a fixed registry (see
``question_generation_logic.md`` §6, §10).
"""
from __future__ import annotations

# Version contract. schema_version / rule_version / prompt_version follow the
# design doc; pipeline_version identifies the v2 implementation itself.
SCHEMA_VERSION = "1.0.0"
RULE_VERSION = "1.0.0"
PROMPT_VERSION = "1.0.0"
PIPELINE_VERSION = "2.0.0"

# Question / rule ID prefixes and hash width (design doc §11).
RULE_ID_PREFIX = "rule_"
QUESTION_ID_PREFIX = "iq_"
CANDIDATE_ID_PREFIX = "cand_"
ID_HASH_HEX = 24

# --- Stage-7 program validation error codes (design doc §10) -----------------
GENERATION_ERROR_CODES = frozenset(
    {
        "empty_or_short_content",
        "answer_leaked_in_stem",
        "answer_synonym_leaked_in_stem",
        "missing_prediction_semantics",
        "contains_exact_date",
        "contains_deidentification_placeholder",
        "contains_linkage_identifier",
        "contains_non_english_cjk_text",
        "unsupported_clinical_fact",
        "source_overlap",
        "invalid_option_set",
        "correct_answer_mismatch",
        "condition_feature_mismatch",
    }
)

# --- Stage-4 rule rejection reason codes (design doc §7.4) -------------------
REJECTION_REASON_CODES = frozenset(
    {
        "low_x_support",
        "low_xy_support",
        "low_conditional_probability",
        "low_lift",
        "low_wilson_lower",
        "fdr_not_significant",
        "low_bootstrap_stability",
        "ambiguous_probability_gap",
        "ambiguous_score_ratio",
    }
)

# --- Stage-5 distractor / option-locking error (design doc §8.2) -------------
INSUFFICIENT_DISTRACTORS = "insufficient_distractors"

# --- Automatic review recommendation values (design doc §12.2) ---------------
REVIEW_RECOMMENDATIONS = frozenset({"accept", "reject", "revise"})

# --- Automatic review status (design doc §11) --------------------------------
AUTO_REVIEW_STATUSES = frozenset({"pending", "candidate_passed", "candidate_rejected"})

# --- Human review decision (design doc §13.1) --------------------------------
HUMAN_REVIEW_DECISIONS = frozenset({"approved", "rejected", "revise"})

# --- Stage status values (design doc §16) ------------------------------------
STAGE_STATUSES = frozenset({"initialized", "running", "completed", "failed"})

# --- Run profiles. Only non-exploratory runs may export gold (§3, §13.2). ----
RUN_PROFILES = frozenset({"formal", "exploratory"})

# Required prediction semantics phrase (design doc §9.1, §10 item 2).
PREDICTION_SEMANTICS_PHRASE = "most likely to be selected"
