"""Apriori condition mining with eight hard gates. One family per call."""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from itertools import combinations
from typing import Any

from .families import CLINICAL_FEATURE_TYPES
from .stats import (
    benjamini_hochberg,
    bootstrap_rank1_stability,
    pair_stats,
    rule_score,
)


def _join_features(feature_ids: tuple[str, ...]) -> str:
    return "|".join(feature_ids)


def _hash_rule(family: str, feature_ids: tuple[str, ...], target: str, window_id: str, profile: str) -> str:
    payload = "|".join([family, _join_features(feature_ids), target, window_id, profile])
    return "rule:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _indexes(transactions: list[dict[str, Any]]) -> tuple[dict[str, set[str]], dict[str, str], dict[str, str], dict[str, set[str]], dict[str, tuple[str, ...]], dict[str, str], int]:
    feature_visits: dict[str, set[str]] = defaultdict(set)
    feature_type: dict[str, str] = {}
    feature_name: dict[str, str] = {}
    outcome_visits: dict[str, set[str]] = defaultdict(set)
    outcomes_by_visit: dict[str, tuple[str, ...]] = {}
    outcome_name: dict[str, str] = {}
    universe: list[str] = []
    for row in transactions:
        visit_id = str(row["visit_key"])
        universe.append(visit_id)
        for feature in row.get("features") or []:
            fid = str(feature["feature_id"])
            feature_visits[fid].add(visit_id)
            feature_type[fid] = str(feature.get("feature_type") or "")
            feature_name[fid] = str(feature.get("display_name") or fid)
        seen: set[str] = set()
        oids: list[str] = []
        for outcome in row.get("outcomes") or []:
            oid = str(outcome["outcome_id"])
            if oid in seen:
                continue
            seen.add(oid)
            oids.append(oid)
            outcome_visits[oid].add(visit_id)
            outcome_name.setdefault(oid, str(outcome.get("outcome_name") or oid))
        outcomes_by_visit[visit_id] = tuple(oids)
    return (
        dict(feature_visits),
        feature_type,
        feature_name,
        dict(outcome_visits),
        outcomes_by_visit,
        outcome_name,
        len(universe),
    )


def _valid_combo(
    feature_ids: tuple[str, ...],
    feature_type: dict[str, str],
) -> bool:
    types = [feature_type[fid] for fid in feature_ids]
    if types.count("age_band") > 1 or types.count("sex") > 1:
        return False
    return any(ftype in CLINICAL_FEATURE_TYPES for ftype in types)


def frequent_itemsets(
    feature_visits: dict[str, set[str]],
    feature_type: dict[str, str],
    *,
    min_support: int,
    min_conditions: int,
    max_conditions: int,
) -> list[tuple[str, ...]]:
    frequent = {fid: visits for fid, visits in feature_visits.items() if len(visits) >= min_support}
    if not frequent:
        return []
    ordered = tuple(sorted(frequent))
    kept: list[tuple[str, ...]] = []
    previous: list[tuple[str, ...]] = [(fid,) for fid in ordered]
    for size in range(1, max_conditions + 1):
        if size == 1:
            candidates = previous
        else:
            prev_set = set(previous)
            previous_sorted = sorted(previous)
            raw: list[tuple[str, ...]] = []
            for index, left in enumerate(previous_sorted):
                for right in previous_sorted[index + 1 :]:
                    if left[:-1] != right[:-1]:
                        break
                    merged = tuple(sorted(set(left) | set(right)))
                    if len(merged) != size:
                        continue
                    tails = combinations(merged, size - 1)
                    if any(tuple(tail) not in prev_set for tail in tails):
                        continue
                    raw.append(merged)
            candidates = sorted(set(raw))
        next_level: list[tuple[str, ...]] = []
        for combo in candidates:
            visits = None
            for fid in combo:
                visits = frequent[fid] if visits is None else visits & frequent[fid]
                if visits is None or len(visits) < min_support:
                    break
            if visits is None or len(visits) < min_support:
                continue
            next_level.append(combo)
            if size >= min_conditions and _valid_combo(combo, feature_type):
                kept.append(combo)
        previous = next_level
        if not previous:
            break
    return kept


def _same_name(feature_names: list[str], outcome_name: str) -> bool:
    target = outcome_name.casefold()
    return any(name.casefold() == target for name in feature_names)


def mine_family(
    transactions: list[dict[str, Any]],
    *,
    family: str,
    window_id: str,
    profile: str,
    thresholds: dict[str, Any],
    catalog_sha256: str,
    posthoc_flags: list[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    feature_visits, feature_type, feature_name, outcome_visits, outcomes_by_visit, outcome_name, n_total = _indexes(
        transactions
    )
    itemsets = frequent_itemsets(
        feature_visits,
        feature_type,
        min_support=int(thresholds["min_x_support"]),
        min_conditions=int(thresholds["min_conditions"]),
        max_conditions=int(thresholds["max_conditions"]),
    )
    pair_p: dict[str, float] = {}
    pair_rows: dict[str, dict[str, Any]] = {}
    for combo in itemsets:
        x_visits = None
        for fid in combo:
            x_visits = feature_visits[fid] if x_visits is None else x_visits & feature_visits[fid]
        if not x_visits:
            continue
        n_x = len(x_visits)
        names = [feature_name[fid] for fid in combo]
        for oid, y_visits in outcome_visits.items():
            if _same_name(names, outcome_name[oid]):
                continue
            n_xy = len(x_visits & y_visits)
            if n_xy < 1:
                continue
            if n_x < int(thresholds["min_x_support"]):
                continue
            stats = pair_stats(n_x=n_x, n_y=len(y_visits), n_xy=n_xy, n_total=n_total)
            pair_id = f"{_join_features(combo)}::{oid}"
            pair_p[pair_id] = float(stats["fisher_p"])
            pair_rows[pair_id] = {
                "combo": combo,
                "x_visits": x_visits,
                "oid": oid,
                **stats,
            }
    q_values = benjamini_hochberg(pair_p)

    by_combo: dict[tuple[str, ...], list[str]] = defaultdict(list)
    for pair_id, row in pair_rows.items():
        by_combo[row["combo"]].append(pair_id)

    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    x_visits_ids = {combo: pair_rows[ids[0]]["x_visits"] for combo, ids in by_combo.items() if ids}

    for combo, pair_ids in sorted(by_combo.items(), key=lambda item: item[0]):
        ranked = []
        for pair_id in pair_ids:
            row = pair_rows[pair_id]
            if int(row["n_xy"]) < int(thresholds["min_xy_support"]):
                continue
            ranked.append(pair_id)
        ranked.sort(
            key=lambda pair_id: (
                -float(pair_rows[pair_id]["smoothed_probability"]),
                -float(pair_rows[pair_id]["wilson_lower"]),
                pair_rows[pair_id]["oid"],
            )
        )
        reasons: list[str] = []
        if len(ranked) < 2:
            reasons.append("insufficient_outcomes")
            target_id = ranked[0] if ranked else None
            runner_id = None
        else:
            target_id = ranked[0]
            runner_id = ranked[1]
        if target_id is None:
            continue
        target = pair_rows[target_id]
        runner = pair_rows[runner_id] if runner_id else None
        x_list = sorted(x_visits_ids[combo])
        stability = bootstrap_rank1_stability(
            x_list,
            {vid: outcomes_by_visit.get(vid, ()) for vid in x_list},
            target["oid"],
            iterations=int(thresholds["bootstrap_iterations"]),
            seed=int(thresholds["random_seed"]),
        )
        target_score = rule_score(
            wilson=float(target["wilson_lower"]),
            lift=float(target["lift"]),
            n_xy=int(target["n_xy"]),
            bootstrap_stability=stability,
        )
        runner_score = 0.0
        if runner is not None:
            runner_score = rule_score(
                wilson=float(runner["wilson_lower"]),
                lift=float(runner["lift"]),
                n_xy=int(runner["n_xy"]),
                bootstrap_stability=1.0,
            )
        gap = float(target["smoothed_probability"]) - (float(runner["smoothed_probability"]) if runner else 0.0)
        if runner_score == 0 and target_score > 0:
            ratio = float(thresholds["score_ratio_cap"])
        elif runner_score == 0 and target_score == 0:
            ratio = 0.0
        else:
            ratio = target_score / runner_score

        if float(target["smoothed_probability"]) < float(thresholds["min_smoothed_probability"]):
            reasons.append("low_conditional_probability")
        if float(target["lift"]) < float(thresholds["min_lift"]):
            reasons.append("low_lift")
        if float(target["wilson_lower"]) < float(thresholds["min_wilson_lower"]):
            reasons.append("low_wilson_lower")
        if q_values.get(target_id, 1.0) > float(thresholds["max_fdr_q"]):
            reasons.append("fdr_not_significant")
        if stability < float(thresholds["min_bootstrap_stability"]):
            reasons.append("low_bootstrap_stability")
        if runner is None:
            pass
        elif gap < float(thresholds["min_probability_gap"]):
            reasons.append("ambiguous_probability_gap")
        if runner is not None and ratio < float(thresholds["min_score_ratio"]):
            reasons.append("ambiguous_score_ratio")

        status = "accepted" if not reasons else "rejected"
        record = {
            "schema_version": "1.0.0",
            "rule_version": "1.0.0",
            "rule_id": _hash_rule(family, combo, target["oid"], str(window_id), profile),
            "family": family,
            "profile": profile,
            "window_id": window_id,
            "catalog_sha256": catalog_sha256,
            "condition_feature_ids": list(combo),
            "condition_display_names": [feature_name[fid] for fid in combo],
            "target_outcome_id": target["oid"],
            "target_outcome_name": outcome_name[target["oid"]],
            "n_total": int(target["n_total"]),
            "n_x": int(target["n_x"]),
            "n_y": int(target["n_y"]),
            "n_xy": int(target["n_xy"]),
            "conditional_probability": round(float(target["conditional_probability"]), 6),
            "smoothed_probability": round(float(target["smoothed_probability"]), 6),
            "baseline_probability": round(float(target["baseline_probability"]), 6),
            "lift": round(float(target["lift"]), 6),
            "wilson_lower": round(float(target["wilson_lower"]), 6),
            "fisher_p": float(target["fisher_p"]),
            "fdr_q": q_values.get(target_id),
            "bootstrap_stability": round(stability, 6),
            "score": round(target_score, 6),
            "runner_up_outcome_id": runner["oid"] if runner else None,
            "runner_up_outcome_name": outcome_name[runner["oid"]] if runner else None,
            "runner_up_probability": round(float(runner["smoothed_probability"]), 6) if runner else None,
            "probability_gap": round(gap, 6),
            "score_ratio": round(ratio, 6) if math.isfinite(ratio) else None,
            "status": status,
            "rejection_reasons": reasons,
            "posthoc_flags": list(posthoc_flags),
            "gold": 0,
        }
        if status == "accepted":
            accepted.append(record)
        else:
            rejected.append(record)

    summary = {
        "family": family,
        "profile": profile,
        "n_total": n_total,
        "transactions": len(transactions),
        "frequent_itemsets": len(itemsets),
        "tested_pairs": len(pair_rows),
        "accepted": len(accepted),
        "rejected": len(rejected),
        "unique_features": len(feature_visits),
        "unique_outcomes": len(outcome_visits),
    }
    return accepted, rejected, summary
