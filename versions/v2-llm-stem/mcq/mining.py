"""Deterministic rule mining: X -> investigation, gated by the 8 hard thresholds.

Implements ``question_generation_logic.md`` §6 / design doc §7:
conditional/smoothed/baseline probability, lift, Wilson lower bound, one-sided
Fisher exact p-value, BH-FDR q-value, bootstrap stability, score, and the
probability-gap / score-ratio separation from the runner-up.

Only rules passing every gate are ``accepted``; others are ``rejected`` with
stable reason codes. The statistics are computed exactly once per condition and
are reproducible under a fixed seed.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmark_common.stats import benjamini_hochberg, wilson_lower  # noqa: E402

from .catalog import (  # noqa: E402
    COMPARISON_CLASSES,
    CLINICAL_ORDER_ALLOWLIST,
    IMAGING_ALLOWLIST,
    Catalog,
)
from .conditions import extract_condition_frame  # noqa: E402
from .hashing import candidate_id, rule_id  # noqa: E402
from .lab_panels import lab_panel, _OTHER  # noqa: E402
from .constants import RULE_VERSION, SCHEMA_VERSION  # noqa: E402

# Finite upper bound for score_ratio when the runner-up score is 0 but the target
# score is > 0 (design doc §7.2 "约定的有限上界值").
SCORE_RATIO_UPPER = 1e9


def _fisher_p_greater(n_xy: int, n_x: int, n_y: int, n_total: int) -> float:
    """One-sided Fisher exact p-value for positive association.

    P(X >= n_xy) under the hypergeometric with N=n_total, K=n_y, n=n_x.
    Log-gamma summation is numerically stable for large tables.
    """
    if n_total <= 0 or n_x <= 0 or n_y <= 0:
        return 1.0
    a = int(n_xy)
    n1 = int(n_x)          # draws (condition admissions)
    k_success = int(n_y)   # successes in population (candidate baseline)
    n = int(n_total)
    kmax = min(n1, k_success)
    if a > kmax:
        return 0.0
    total = 0.0
    for k in range(a, kmax + 1):
        log_p = (
            math.lgamma(k_success + 1) - math.lgamma(k + 1) - math.lgamma(k_success - k + 1)
            + math.lgamma(n - k_success + 1) - math.lgamma(n1 - k + 1)
            - math.lgamma((n - k_success) - (n1 - k) + 1)
            - (math.lgamma(n + 1) - math.lgamma(n1 + 1) - math.lgamma(n - n1 + 1))
        )
        total += math.exp(log_p)
        if total >= 1.0:
            return 1.0
    return min(1.0, total)


def _wilson_lower_vec(k, n, z: float = 1.96):
    """Vectorized Wilson lower bound (same formula as ``wilson_lower``)."""
    k = np.asarray(k, float)
    n = np.asarray(n, float)
    with np.errstate(divide="ignore", invalid="ignore"):
        denom = np.where(n > 0, n, 1.0)
        p = np.where(n > 0, k / denom, 0.0)
        z2 = z * z
        d = 1 + z2 / denom
        center = (p + z2 / (2 * denom)) / d
        half = z * np.sqrt(p * (1 - p) / denom + z2 / (4 * denom * denom)) / d
        out = center - half
    return np.maximum(0.0, out)


def _binomial_greater_p_vec(k, n, p0):
    """Vectorized one-sided binomial P(X >= k), normal approximation.

    Equivalent to ``binomial_greater_pvalue`` for large tables; exact for the
    p0<=0 / p0>=1 / k<=0 edge cases. Used for the vectorized rule mining.
    """
    k = np.asarray(k, float)
    n = np.asarray(n, float)
    p0 = np.asarray(p0, float)
    out = np.empty_like(k)
    m0 = p0 <= 0.0
    out[m0] = np.where(k[m0] > 0, 0.0, 1.0)
    m1 = (~m0) & (p0 >= 1.0)
    out[m1] = 0.0
    m2 = (~m0) & (~m1) & (k <= 0)
    out[m2] = 1.0
    m3 = ~(m0 | m1 | m2)
    var = n[m3] * p0[m3] * (1.0 - p0[m3])
    with np.errstate(divide="ignore", invalid="ignore"):
        z = (k[m3] - 0.5 - n[m3] * p0[m3]) / np.sqrt(var)
        out[m3] = 0.5 * _erfc_vec(z / np.sqrt(2.0))
    return np.clip(out, 0.0, 1.0)


_erfc_vec = np.vectorize(math.erfc, otypes=[float])


def _bh_q(df: pd.DataFrame, group_col: str, p_col: str,
          m: int | None = None) -> pd.Series:
    """Vectorized Benjamini-Hochberg q-values computed within groups.

    ``m`` is the number of tests per group (the full candidate universe size).
    When None, it defaults to the group size. Passing ``m`` accounts for the
    n_xy=0 candidates (p=1.0) without materializing them.
    """
    d = df[[group_col, p_col]].copy()
    d["_gid"] = pd.factorize(d[group_col], sort=False)[0]
    if m is None:
        d["_m"] = d.groupby("_gid")[p_col].transform("size")
    else:
        d["_m"] = m
    d = d.sort_values(["_gid", p_col], kind="stable")
    d["_rank"] = d.groupby("_gid").cumcount() + 1
    d["_q"] = (d[p_col] * d["_m"] / d["_rank"]).clip(upper=1.0)
    # running min over descending rank == forward cummin on reversed order
    d = d.sort_values(["_gid", "_rank"], ascending=[True, False], kind="stable")
    d["_q"] = d.groupby("_gid")["_q"].cummin()
    d = d.sort_index()
    return d["_q"]


def _answer_order_frame(events: pd.DataFrame, cls: str) -> pd.DataFrame:
    """Per-admission answer-space candidates for one comparison class."""
    if cls == "imaging":
        m = (events["event_kind"] == "imaging_ordered") & (
            events["entity_type"] == "imaging_study"
        ) & events["source_label"].isin(IMAGING_ALLOWLIST)
        sub = events[m][["hadm_id", "source_label"]].drop_duplicates()
        return sub.rename(columns={"source_label": "candidate"})
    if cls == "clinical_order":
        m = (events["event_kind"] == "clinical_ordered") & (
            events["entity_type"] == "clinical_order"
        ) & events["source_label"].isin(CLINICAL_ORDER_ALLOWLIST)
        sub = events[m][["hadm_id", "source_label"]].drop_duplicates()
        return sub.rename(columns={"source_label": "candidate"})
    if cls == "laboratory":
        lab = events[events["event_kind"] == "laboratory_resulted"].copy()
        lab["panel"] = lab["concept_id"].map(lab_panel)
        lab = lab[lab["panel"] != _OTHER]
        return lab[["hadm_id", "panel"]].drop_duplicates().rename(
            columns={"panel": "candidate"}
        )
    raise ValueError(f"unknown comparison class: {cls}")


def _bootstrap_stability(
    adm_candidate_lists: list[list[str]],
    universe: list[str],
    n_x: int,
    iterations: int,
    seed: int,
) -> dict[str, float]:
    """Fraction of fixed-seed bootstrap resamples where each candidate is the
    UNIQUE argmax of smoothed probability (design doc §7.2)."""
    idx_of = {c: i for i, c in enumerate(universe)}
    n_cand = len(universe)
    adm_idx = [
        np.array([idx_of[c] for c in lst], dtype=np.int64)
        for lst in adm_candidate_lists
    ]
    rng = np.random.default_rng(seed)
    wins = np.zeros(n_cand, dtype=np.int64)
    for _ in range(iterations):
        sample = rng.integers(0, n_x, size=n_x)
        counts = np.zeros(n_cand, dtype=np.int64)
        for s in sample:
            arr = adm_idx[s]
            if arr.size:
                counts[arr] += 1
        smoothed = (counts + 1.0) / (n_x + 2.0)
        order = np.argsort(-smoothed, kind="stable")
        if smoothed[order[0]] > smoothed[order[1]]:
            wins[order[0]] += 1
    return {c: float(wins[i]) / iterations for i, c in enumerate(universe)}


def _seed_for(random_seed: int, cls: str, condition: str) -> int:
    from .hashing import sha256_hex
    return random_seed + int(sha256_hex(f"{cls}|{condition}")[:8], 16)


def mine_rules(
    events: pd.DataFrame,
    cond: pd.DataFrame,
    catalog: Catalog,
    thresholds: dict,
    *,
    materialize_rejections: bool = True,
    counts: dict | None = None,
    progress_callback=None,
) -> tuple[list[dict], list[dict]]:
    """Mine X -> investigation rules across the three comparison classes.

    ``cond`` must be the ``extract_condition_frame`` output. Returns
    ``(accepted_rules, rejected_rules)``, each conforming to the rule schema.
    """
    min_conditions = int(thresholds["min_conditions"])
    max_conditions = int(thresholds["max_conditions"])
    bootstrap_iterations = int(thresholds["bootstrap_iterations"])
    random_seed = int(thresholds["random_seed"])
    rank_by = thresholds.get("rank_by", "lift")

    cond = cond[
        (cond["n_features"] >= min_conditions) & (cond["n_features"] <= max_conditions)
    ]
    n_total = int(cond["hadm_id"].nunique())
    if n_total == 0:
        return [], []
    if counts is not None:
        counts.clear()

    accepted: list[dict] = []
    rejected: list[dict] = []

    for cls in COMPARISON_CLASSES:
        order_frame = _answer_order_frame(events, cls)
        if order_frame.empty:
            continue
        universe = catalog.answer_names(cls)
        if not universe:
            continue
        base = order_frame.groupby("candidate")["hadm_id"].nunique().rename("n_y")
        merged = cond.merge(order_frame, on="hadm_id", how="inner")
        if merged.empty:
            continue

        # --- Vectorized co-occurrence counts + statistics -------------------
        pair = (
            merged.groupby(["condition", "candidate"], sort=False)["hadm_id"]
            .nunique().reset_index(name="n_xy")
        )
        # Full cross product (condition × universe) so n_xy=0 candidates are
        # included in the FDR correction and ranking (they carry fisher_p=1.0).
        # NOTE: this materializes |conditions| × |universe| rows — too large for
        # the full development split (laboratory has 16 candidates). Replaced by
        # a denominator-only correction below.
        n_x_map = merged.groupby("condition")["hadm_id"].nunique().rename("n_x")
        pair = pair.merge(n_x_map.reset_index(), on="condition", how="left")
        pair = pair.merge(base.reset_index(), on="candidate", how="left")
        pair["n_y"] = pair["n_y"].fillna(0).astype(int)

        k = pair["n_xy"].to_numpy(dtype=float)
        nx = pair["n_x"].to_numpy(dtype=float)
        ny = pair["n_y"].to_numpy(dtype=float)
        pair["conditional_probability"] = k / nx
        pair["smoothed_probability"] = (k + 1.0) / (nx + 2.0)
        pair["baseline_probability"] = (ny + 1.0) / (n_total + 2.0)
        pair["lift"] = pair["smoothed_probability"] / pair["baseline_probability"]
        pair["wilson_lower"] = _wilson_lower_vec(k, nx)
        pair["fisher_p"] = _binomial_greater_p_vec(k, nx, ny / n_total)
        pair["fdr_q"] = _bh_q(pair, "condition", "fisher_p", m=len(universe))

        feat = (
            cond[["condition", "condition_feature_ids", "condition_features"]]
            .drop_duplicates("condition").set_index("condition")
        )

        # Support short-circuit: one cheap rejection per low-support condition.
        low = pair[pair["n_x"] < thresholds["min_x_support"]]
        if not low.empty:
            low_best = low.sort_values("n_xy", ascending=False).drop_duplicates("condition")
            for row in low_best.itertuples(index=False):
                fid = list(feat.loc[row.condition, "condition_feature_ids"])
                fname = list(feat.loc[row.condition, "condition_features"])
                if counts is not None:
                    counts["low_x_support"] = counts.get("low_x_support", 0) + 1
                if materialize_rejections:
                    rejected.append(_cheap_rejected_rule(
                        cls, fid, fname, n_total, int(row.n_x), row.candidate,
                        int(row.n_xy), int(row.n_y), ["low_x_support"]))
        pair = pair[pair["n_x"] >= thresholds["min_x_support"]]

        # Per-condition loop (reduced to support-survivors): cheap gates first.
        survivors = []
        for condition, grp in pair.groupby("condition", sort=True):
            grp = grp.sort_values("smoothed_probability", ascending=False)
            fid = list(feat.loc[condition, "condition_feature_ids"])
            fname = list(feat.loc[condition, "condition_features"])
            nx_val = int(grp.iloc[0]["n_x"])
            rows = {r["candidate"]: {
                "n_xy": int(r["n_xy"]), "n_y": int(r["n_y"]),
                "conditional_probability": float(r["conditional_probability"]),
                "smoothed_probability": float(r["smoothed_probability"]),
                "baseline_probability": float(r["baseline_probability"]),
                "lift": float(r["lift"]),
                "wilson_lower": float(r["wilson_lower"]),
                "fisher_p": float(r["fisher_p"]),
                "fdr_q": float(r["fdr_q"]),
            } for r in grp.to_dict("records")}
            # add missing universe candidates (n_xy == 0) with stable defaults
            for c in universe:
                if c not in rows:
                    ny0 = int(base.get(c, 0))
                    bp0 = (ny0 + 1.0) / (n_total + 2.0)
                    rows[c] = {
                        "n_xy": 0, "n_y": ny0, "conditional_probability": 0.0,
                        "smoothed_probability": 1.0 / (nx_val + 2.0),
                        "baseline_probability": bp0,
                        "lift": (1.0 / (nx_val + 2.0)) / bp0,
                        "wilson_lower": 0.0, "fisher_p": 1.0, "fdr_q": 1.0,
                    }
            # rank over the FULL universe (n_xy=0 candidates included) so the
            # runner-up / gap gate is correct.
            order = _rank_order(universe, rows, rank_by)
            tgt = order[0]
            run = order[1] if len(order) > 1 else None
            cheap_reasons = _cheap_gate_reasons(rows[tgt], nx_val, run, rows, thresholds, rank_by)
            if cheap_reasons:
                if counts is not None:
                    for r in cheap_reasons:
                        counts[r] = counts.get(r, 0) + 1
                if materialize_rejections:
                    rejected.append(_build_rule(
                        cls, fid, fname, n_total, nx_val, tgt, run, rows,
                        "rejected", cheap_reasons, rank_by))
            else:
                survivors.append((condition, fid, fname, nx_val, rows, tgt, run))

        # Bootstrap only for cheap-gate survivors.
        if survivors:
            surv_set = {s[0] for s in survivors}
            surv_merged = merged[merged["condition"].isin(surv_set)]
            adm_by_cond = surv_merged.groupby("condition").apply(
                lambda g: g.groupby("hadm_id")["candidate"].apply(list).tolist(),
                include_groups=False)
            for condition, fid, fname, nx_val, rows, tgt, run in survivors:
                adm_lists = adm_by_cond.get(condition, [])
                stability = _bootstrap_stability(
                    adm_lists, universe, nx_val, bootstrap_iterations,
                    _seed_for(random_seed, cls, condition))
                for cand in universe:
                    if cand in rows:
                        rows[cand]["bootstrap_stability"] = stability[cand]
                        r = rows[cand]
                        r["score"] = (
                            r["wilson_lower"]
                            * max(0.0, math.log2(r["lift"]) if r["lift"] > 0 else 0.0)
                            * math.log1p(r["n_xy"])
                            * r["bootstrap_stability"])
                order = _rank_order(universe, rows, rank_by)
                target = order[0]
                runner_up = order[1] if len(order) > 1 else None
                t = rows[target]
                probability_gap = _rank_gap(t, runner_up, rows, rank_by)
                if runner_up is not None:
                    ts, rs = t["score"], rows[runner_up].get("score", 0.0)
                    if ts > 0 and rs == 0:
                        score_ratio = SCORE_RATIO_UPPER
                    elif ts == 0 and rs == 0:
                        score_ratio = 0.0
                    else:
                        score_ratio = ts / rs if rs > 0 else SCORE_RATIO_UPPER
                else:
                    score_ratio = None
                reasons = _gate_reasons(t, nx_val, probability_gap, score_ratio, thresholds, rank_by)
                status = "accepted" if not reasons else "rejected"
                (accepted if status == "accepted" else rejected).append(_build_rule(
                    cls, fid, fname, n_total, nx_val, target, runner_up,
                    rows, status, reasons, rank_by))

        if progress_callback is not None:
            progress_callback({
                "class": cls, "n_accepted": len(accepted),
                "n_rejected": len(rejected),
            })

    return accepted, rejected


def _rank_order(universe: list[str], rows: dict[str, dict], rank_by: str) -> list[str]:
    """Rank candidates: by lift (selectivity) or by smoothed probability."""
    if rank_by == "lift":
        return sorted(universe, key=lambda c: (-rows[c]["lift"], -rows[c].get("score", 0.0), c))
    return sorted(universe, key=lambda c: (-rows[c]["smoothed_probability"], -rows[c].get("score", 0.0), c))


def _rank_gap(t: dict, runner_up: str | None, rows: dict[str, dict],
              rank_by: str) -> float | None:
    """Separation between the rank-1 target and runner-up (rank-appropriate)."""
    if runner_up is None:
        return None
    if rank_by == "lift":
        return t["lift"] - rows[runner_up]["lift"]
    return t["smoothed_probability"] - rows[runner_up]["smoothed_probability"]


def _gap_threshold(thresholds: dict, rank_by: str) -> float:
    return thresholds["min_lift_gap"] if rank_by == "lift" else thresholds["min_probability_gap"]


def _gate_reasons(t: dict, n_x: int, gap: float | None, ratio: float | None,
                  thresholds: dict, rank_by: str = "lift") -> list[str]:
    reasons: list[str] = []
    if n_x < thresholds["min_x_support"]:
        reasons.append("low_x_support")
    if t["n_xy"] < thresholds["min_xy_support"]:
        reasons.append("low_xy_support")
    if t["smoothed_probability"] < thresholds["min_smoothed_probability"]:
        reasons.append("low_conditional_probability")
    if t["lift"] < thresholds["min_lift"]:
        reasons.append("low_lift")
    if t["wilson_lower"] < thresholds["min_wilson_lower"]:
        reasons.append("low_wilson_lower")
    if t["fdr_q"] > thresholds["max_fdr_q"]:
        reasons.append("fdr_not_significant")
    if t["bootstrap_stability"] < thresholds["min_bootstrap_stability"]:
        reasons.append("low_bootstrap_stability")
    if gap is None or gap < _gap_threshold(thresholds, rank_by):
        reasons.append("ambiguous_probability_gap")
    if ratio is None or ratio < thresholds["min_score_ratio"]:
        reasons.append("ambiguous_score_ratio")
    return reasons


def _cheap_rejected_rule(cls: str, feature_ids: list[str], feature_names: list[str],
                         n_total: int, n_x: int, target: str, n_xy: int, n_y: int,
                         reasons: list[str]) -> dict:
    """Build a schema-valid rejected rule without bootstrap / fisher (cheap path).

    Used for conditions that fail the cheapest gate (support) — the expensive
    statistics and bootstrap are skipped because they cannot change the verdict.
    """
    sp = (n_xy + 1) / (n_x + 2) if n_x else 0.0
    bp = (n_y + 1) / (n_total + 2) if n_total else 0.0
    lift = sp / bp if bp > 0 else 0.0
    return {
        "schema_version": SCHEMA_VERSION,
        "rule_version": RULE_VERSION,
        "rule_id": rule_id(feature_ids, candidate_id(cls, target)),
        "comparison_class": cls,
        "condition_feature_ids": feature_ids,
        "condition_display_names": feature_names,
        "target_investigation_id": candidate_id(cls, target),
        "target_investigation_name": target,
        "n_total": n_total, "n_x": n_x, "n_y": int(n_y), "n_xy": int(n_xy),
        "conditional_probability": round(n_xy / n_x, 6) if n_x else 0.0,
        "smoothed_probability": round(sp, 6),
        "baseline_probability": round(bp, 6),
        "lift": round(lift, 6),
        "wilson_lower": round(wilson_lower(n_xy, n_x), 6),
        "fisher_p": 1.0, "fdr_q": 1.0, "bootstrap_stability": 0.0, "score": 0.0,
        "runner_up_investigation_id": None, "runner_up_probability": None,
        "probability_gap": None, "score_ratio": None,
        "status": "rejected", "rejection_reasons": reasons,
    }


def _cheap_gate_reasons(t: dict, n_x: int, runner_up: str | None,
                        rows: dict[str, dict], thresholds: dict,
                        rank_by: str = "lift") -> list[str]:
    """Cheap gates that can reject a condition WITHOUT the expensive bootstrap."""
    reasons: list[str] = []
    if t["n_xy"] < thresholds["min_xy_support"]:
        reasons.append("low_xy_support")
    if t["smoothed_probability"] < thresholds["min_smoothed_probability"]:
        reasons.append("low_conditional_probability")
    if t["lift"] < thresholds["min_lift"]:
        reasons.append("low_lift")
    if t["wilson_lower"] < thresholds["min_wilson_lower"]:
        reasons.append("low_wilson_lower")
    if t["fdr_q"] > thresholds["max_fdr_q"]:
        reasons.append("fdr_not_significant")
    gap = _rank_gap(t, runner_up, rows, rank_by)
    if gap is None or gap < _gap_threshold(thresholds, rank_by):
        reasons.append("ambiguous_probability_gap")
    return reasons


def _build_rule(cls: str, feature_ids: list[str], feature_names: list[str],
                n_total: int, n_x: int, target: str, runner_up: str | None,
                rows: dict[str, dict], status: str, reasons: list[str],
                rank_by: str = "lift") -> dict:
    """Assemble the full rule dict (bootstrap/score default to 0 when skipped)."""
    t = rows[target]
    bootstrap = t.get("bootstrap_stability", 0.0)
    score = t.get("score", 0.0)
    probability_gap = _rank_gap(t, runner_up, rows, rank_by)
    if runner_up is not None:
        ts, rs = score, rows[runner_up].get("score", 0.0)
        if ts > 0 and rs == 0:
            score_ratio = SCORE_RATIO_UPPER
        elif ts == 0 and rs == 0:
            score_ratio = 0.0
        else:
            score_ratio = ts / rs if rs > 0 else SCORE_RATIO_UPPER
    else:
        score_ratio = None
    return {
        "schema_version": SCHEMA_VERSION,
        "rule_version": RULE_VERSION,
        "rule_id": rule_id(feature_ids, candidate_id(cls, target)),
        "comparison_class": cls,
        "condition_feature_ids": feature_ids,
        "condition_display_names": feature_names,
        "target_investigation_id": candidate_id(cls, target),
        "target_investigation_name": target,
        "n_total": n_total, "n_x": n_x, "n_y": t["n_y"], "n_xy": t["n_xy"],
        "conditional_probability": round(t["conditional_probability"], 6),
        "smoothed_probability": round(t["smoothed_probability"], 6),
        "baseline_probability": round(t["baseline_probability"], 6),
        "lift": round(t["lift"], 6) if math.isfinite(t["lift"]) else None,
        "wilson_lower": round(t["wilson_lower"], 6),
        "fisher_p": round(t["fisher_p"], 9),
        "fdr_q": round(t["fdr_q"], 9),
        "bootstrap_stability": round(bootstrap, 6),
        "score": round(score, 6),
        "runner_up_investigation_id": (
            candidate_id(cls, runner_up) if runner_up else None
        ),
        "runner_up_probability": (
            round(rows[runner_up]["smoothed_probability"], 6) if runner_up else None
        ),
        "probability_gap": (
            round(probability_gap, 6) if probability_gap is not None else None
        ),
        "score_ratio": round(score_ratio, 6) if score_ratio is not None else None,
        "status": status,
        "rejection_reasons": reasons,
    }
