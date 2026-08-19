"""Fail-closed rule counting and ranking primitives for W7."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any, Iterable, Mapping


class RankingContractError(ValueError):
    pass


@dataclass(frozen=True)
class ContingencyTable:
    n_x: int
    n_y: int
    n_xy: int
    n_total: int

    @property
    def a(self) -> int:
        return self.n_xy

    @property
    def b(self) -> int:
        return self.n_x - self.n_xy

    @property
    def c(self) -> int:
        return self.n_y - self.n_xy

    @property
    def d(self) -> int:
        return self.n_total - self.a - self.b - self.c

    def as_dict(self) -> dict[str, int]:
        return {"a": self.a, "b": self.b, "c": self.c, "d": self.d, "n_x": self.n_x, "n_y": self.n_y, "n_xy": self.n_xy, "n_total": self.n_total}


def contingency(condition_ids: Iterable[str], target_ids: Iterable[str], eligible_ids: Iterable[str]) -> ContingencyTable:
    universe = {str(value) for value in eligible_ids}
    conditions = {str(value) for value in condition_ids} & universe
    targets = {str(value) for value in target_ids} & universe
    if not universe:
        raise RankingContractError("eligible development documents cannot be empty")
    overlap = conditions & targets
    return ContingencyTable(len(conditions), len(targets), len(overlap), len(universe))


def statistics(table: ContingencyTable, *, prior: float = 0.5) -> dict[str, float | int]:
    if prior <= 0:
        raise RankingContractError("prior must be positive")
    a, b, c, d = (float(table.a), float(table.b), float(table.c), float(table.d))
    if min(a, b, c, d) < 0:
        raise RankingContractError("invalid 2x2 table")
    probability = a / table.n_x if table.n_x else 0.0
    target_prevalence = table.n_y / table.n_total
    lift = probability / target_prevalence if target_prevalence else math.inf
    log_rr = math.log((a + 1e-12) / max(table.n_x - a, 1e-12)) - math.log((c + 1e-12) / max(table.n_total - table.n_x - c, 1e-12))
    shrunk_log_rr = math.log((a + prior) / (b + prior)) - math.log((c + prior) / (d + prior))
    # Conservative two-sided Wald interval on log odds ratio; the table remains the source of truth.
    se = math.sqrt(sum(1.0 / (value + prior) for value in (a, b, c, d)))
    return {**table.as_dict(), "frequency": float(a), "probability": probability, "lift": lift, "log_rr": log_rr, "shrunk_log_rr": shrunk_log_rr, "wilson_low": max(0.0, probability - 1.96 * math.sqrt(probability * (1 - probability) / table.n_x)) if table.n_x else 0.0, "wilson_high": min(1.0, probability + 1.96 * math.sqrt(probability * (1 - probability) / table.n_x)) if table.n_x else 0.0, "log_rr_se": se}


def _log_comb(n: int, k: int) -> float:
    if k < 0 or k > n:
        return float("-inf")
    if k == 0 or k == n:
        return 0.0
    k = min(k, n - k)
    result = 0.0
    for index in range(k):
        result += math.log(n - index) - math.log(index + 1)
    return result


def fisher_greater(a: int, b: int, c: int, d: int) -> float:
    """One-sided Fisher exact P(X >= a) under the hypergeometric null."""
    if min(a, b, c, d) < 0:
        raise RankingContractError("invalid 2x2 table")
    n_total = a + b + c + d
    n_draw = a + b
    n_success = a + c
    if n_total == 0 or n_draw == 0 or n_success == 0:
        return 1.0
    maximum = min(n_draw, n_success)
    log_den = _log_comb(n_total, n_draw)
    p_value = 0.0
    for count in range(a, maximum + 1):
        p_value += math.exp(
            _log_comb(n_success, count) + _log_comb(n_total - n_success, n_draw - count) - log_den
        )
    return min(1.0, max(0.0, p_value))


def benjamini_hochberg(p_values: Mapping[str, float], *, family: str) -> dict[str, Any]:
    if any(not 0 <= value <= 1 for value in p_values.values()):
        raise RankingContractError("p-values must be within [0, 1]")
    ordered = sorted(p_values.items(), key=lambda item: (item[1], item[0]))
    q_values: dict[str, float] = {}
    running = 1.0
    for rank, (key, p_value) in reversed(list(enumerate(ordered, start=1))):
        running = min(running, p_value * len(ordered) / rank)
        q_values[key] = running
    manifest = {"family": family, "keys": [key for key, _ in ordered], "p_values": dict(ordered), "q_values": {key: q_values[key] for key, _ in ordered}, "family_sha256": hashlib.sha256(json.dumps([key for key, _ in ordered], separators=(",", ":")).encode()).hexdigest()}
    return manifest


def subject_bootstrap_units(documents: Iterable[Mapping[str, Any]]) -> tuple[tuple[str, ...], ...]:
    by_subject: dict[str, list[str]] = {}
    for document in documents:
        subject = str(document.get("subject_ref", ""))
        decision = str(document.get("decision_id", ""))
        if not subject or not decision:
            raise RankingContractError("subject_ref and decision_id are required")
        by_subject.setdefault(subject, []).append(decision)
    return tuple(tuple(sorted(decisions)) for _, decisions in sorted(by_subject.items()))
