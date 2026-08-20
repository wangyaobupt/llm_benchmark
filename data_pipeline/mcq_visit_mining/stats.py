"""Self-contained Wilson / Fisher / BH / bootstrap. Does not import investigation_selection."""

from __future__ import annotations

import math
import random
from collections import Counter, defaultdict
from typing import Iterable, Mapping, Sequence


def wilson_lower(successes: int, n: int, z: float = 1.96) -> float:
    if n <= 0:
        return 0.0
    p = successes / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = p + z2 / (2.0 * n)
    margin = z * math.sqrt((p * (1.0 - p) + z2 / (4.0 * n)) / n)
    return max(0.0, (center - margin) / denom)


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
    if min(a, b, c, d) < 0:
        raise ValueError("invalid 2x2 table")
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


def benjamini_hochberg(p_values: Mapping[str, float]) -> dict[str, float]:
    if not p_values:
        return {}
    if any(not 0 <= value <= 1 for value in p_values.values()):
        raise ValueError("p-values must be within [0, 1]")
    ordered = sorted(p_values.items(), key=lambda item: (item[1], item[0]))
    q_values: dict[str, float] = {}
    running = 1.0
    total = len(ordered)
    for rank, (key, p_value) in reversed(list(enumerate(ordered, start=1))):
        running = min(running, p_value * total / rank)
        q_values[key] = running
    return q_values


def pair_stats(*, n_x: int, n_y: int, n_xy: int, n_total: int) -> dict[str, float | int]:
    if n_x <= 0 or n_total <= 0:
        raise ValueError("n_x and n_total must be positive")
    a = n_xy
    b = n_x - n_xy
    c = n_y - n_xy
    d = n_total - n_x - n_y + n_xy
    if min(a, b, c, d) < 0:
        raise ValueError("invalid contingency")
    conditional = n_xy / n_x
    smoothed = (n_xy + 1) / (n_x + 2)
    baseline = (n_y + 1) / (n_total + 2)
    lift = smoothed / baseline if baseline else math.inf
    return {
        "n_x": n_x,
        "n_y": n_y,
        "n_xy": n_xy,
        "n_total": n_total,
        "conditional_probability": conditional,
        "smoothed_probability": smoothed,
        "baseline_probability": baseline,
        "lift": lift,
        "wilson_lower": wilson_lower(n_xy, n_x),
        "fisher_p": fisher_greater(a, b, c, d),
    }


def rule_score(
    *,
    wilson: float,
    lift: float,
    n_xy: int,
    bootstrap_stability: float,
) -> float:
    association = max(0.0, math.log2(lift)) if lift > 0 else 0.0
    return wilson * association * math.log(1.0 + n_xy) * bootstrap_stability


def bootstrap_rank1_stability(
    x_visit_ids: Sequence[str],
    outcomes_by_visit: Mapping[str, Sequence[str]],
    target: str,
    *,
    iterations: int,
    seed: int,
) -> float:
    if not x_visit_ids:
        return 0.0
    rng = random.Random(seed)
    n = len(x_visit_ids)
    wins = 0
    for _ in range(iterations):
        counts: Counter[str] = Counter()
        for _draw in range(n):
            visit_id = x_visit_ids[rng.randrange(n)]
            for outcome_id in outcomes_by_visit.get(visit_id, ()):
                counts[outcome_id] += 1
        if not counts:
            continue
        ranked = sorted(
            counts.items(),
            key=lambda item: (-(item[1] + 1) / (n + 2), item[0]),
        )
        if ranked[0][0] == target and (len(ranked) == 1 or ranked[0][1] > ranked[1][1]):
            wins += 1
    return wins / iterations


def invert_outcomes(transactions: Iterable[Mapping]) -> tuple[dict[str, set[str]], dict[str, tuple[str, ...]], dict[str, str]]:
    outcome_visits: dict[str, set[str]] = defaultdict(set)
    outcomes_by_visit: dict[str, tuple[str, ...]] = {}
    labels: dict[str, str] = {}
    for row in transactions:
        visit_id = str(row["visit_key"])
        ids = []
        seen: set[str] = set()
        for outcome in row.get("outcomes") or []:
            outcome_id = str(outcome["outcome_id"])
            if outcome_id in seen:
                continue
            seen.add(outcome_id)
            ids.append(outcome_id)
            outcome_visits[outcome_id].add(visit_id)
            labels.setdefault(outcome_id, str(outcome.get("outcome_name") or outcome_id))
        outcomes_by_visit[visit_id] = tuple(ids)
    return dict(outcome_visits), outcomes_by_visit, labels
