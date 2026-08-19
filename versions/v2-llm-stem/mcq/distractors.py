"""Distractor selection and A-D option locking (design doc §8, logic doc §4).

The correct answer and its position are fixed by the program before any LLM call;
the model may not add, remove, reorder, or rename options.
"""
from __future__ import annotations

from .catalog import Catalog
from .constants import INSUFFICIENT_DISTRACTORS
from .hashing import candidate_id, sha256_hex

_LETTERS = ["A", "B", "C", "D"]


def select_distractors(comparison_class: str, target_name: str,
                       catalog: Catalog) -> list[str]:
    """Return exactly three eligible distractor names (or fewer if unavailable).

    Filter: not the target, orderable, same granularity as the target (design
    doc §8.1), not a synonym. Sort: same family first, then |visit_count diff|
    ascending, then name, then id (design doc §8.2).
    """
    pool = catalog.pool.get(comparison_class, [])
    target = next(
        (c for c in pool if c.canonical_name.casefold() == target_name.casefold()),
        None,
    )
    if target is None:
        # Target not in pool (e.g. imaging answer is first-line but pool is full;
        # it will be present since pool is a superset). Fall back to the same
        # eligibility rules; without a target, only "specific" items are eligible.
        candidates = [
            c for c in pool
            if c.canonical_name.casefold() != target_name.casefold()
            and c.is_orderable
            and c.granularity == "specific"
        ]
        key = lambda c: (
            abs(c.source_visit_count),
            c.canonical_name.casefold(),
            c.investigation_id,
        )
    else:
        candidates = [
            c for c in pool
            if c.investigation_id != target.investigation_id
            and c.is_orderable
            and c.granularity == target.granularity
        ]
        key = lambda c: (
            c.family != target.family,
            abs(c.source_visit_count - target.source_visit_count),
            c.canonical_name.casefold(),
            c.investigation_id,
        )
    candidates.sort(key=key)
    return [c.canonical_name for c in candidates[:3]]


def lock_options(accepted_rules: list[dict], catalog: Catalog) -> list[dict]:
    """Lock A-D options for each accepted rule (deterministic, reproducible).

    Rules are ordered by sha256(rule_id); the correct option letter cycles A-D;
    distractor internal order is sha256(rule_id + investigation_id). Returns a
    list of locked-question skeletons; rules with <3 distractors are skipped and
    recorded via the returned failures list.
    """
    ordered = sorted(accepted_rules, key=lambda r: sha256_hex(r["rule_id"]))
    locked: list[dict] = []
    failures: list[dict] = []
    for i, rule in enumerate(ordered):
        cls = rule["comparison_class"]
        target_name = rule["target_investigation_name"]
        distractors = select_distractors(cls, target_name, catalog)
        if len(distractors) < 3:
            failures.append({
                "rule_id": rule["rule_id"],
                "stage": "question_generation",
                "error_type": INSUFFICIENT_DISTRACTORS,
                "error": "Fewer than three orderable same-granularity distractors",
            })
            continue
        # Distractor internal order via sha256(rule_id + investigation_id).
        distractors.sort(
            key=lambda d: sha256_hex(rule["rule_id"] + candidate_id(cls, d))
        )
        correct_letter = _LETTERS[i % 4]
        distractor_letters = [l for l in _LETTERS if l != correct_letter]
        options = {correct_letter: target_name}
        for letter, distractor in zip(distractor_letters, distractors):
            options[letter] = distractor
        options = {l: options[l] for l in _LETTERS}
        locked.append({
            "rule": rule,
            "options": options,
            "correct_option": correct_letter,
            "correct_answer": target_name,
        })
    return locked, failures
