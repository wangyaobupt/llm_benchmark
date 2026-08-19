"""B1 — rule deduplication (subsumption removal).

Greedy highest-score-first: a rule is dropped when an already-kept rule has the
same answer AND its condition features are a subset (i.e. the kept rule is the
more-general "minimal sufficient condition" and the current rule only adds
demographic / extra modifiers).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

RULES = Path(r"D:\Projects\llm_benchmark\data\phenotype\conditional_rules_development.jsonl")
OUT = Path(r"D:\Projects\llm_benchmark\data\phenotype\conditional_rules_dedup.jsonl")
OUT_READABLE = Path(r"D:\Projects\llm_benchmark\data\phenotype\dedup_rules_readable.md")


def load_rules(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


# Presentation features that define the clinical signal; demographics, medication,
# and past-condition are context modifiers that create near-duplicate variants.
CORE_FEATURE_TYPES = {"symptom", "sign", "physiologic_flag", "absent"}


def _core_features(feature_ids: list[str]) -> tuple[str, ...]:
    core = tuple(sorted(
        f for f in feature_ids if f.split(":", 1)[0] in CORE_FEATURE_TYPES
    ))
    if not core:
        # Safety: a rule with no presentation feature is kept as-is (not collapsed).
        return tuple(sorted(feature_ids))
    return core


def converge_rules(rules: list[dict]) -> list[dict]:
    """B2 — collapse context variants of the same clinical signal.

    Group accepted rules by (target, core presentation features) and keep the
    most general (fewest features), highest-score representative per group.
    """
    groups: dict[tuple[str, tuple[str, ...]], list[dict]] = {}
    for r in rules:
        key = (r["target_investigation_id"], _core_features(r["condition_feature_ids"]))
        groups.setdefault(key, []).append(r)
    out: list[dict] = []
    for rs in groups.values():
        best = max(rs, key=lambda r: (
            -len(r["condition_feature_ids"]),
            r.get("score") or 0.0,
            r.get("n_x") or 0,
        ))
        out.append(best)
    return sorted(out, key=lambda r: -(r.get("score") or 0.0))


def dedup_rules(rules: list[dict]) -> list[dict]:
    ordered = sorted(rules, key=lambda r: -(r.get("score") or 0.0))
    kept: list[dict] = []
    for r in ordered:
        r_feats = set(r["condition_feature_ids"])
        r_cls = r["comparison_class"]
        r_target = r["target_investigation_id"]
        covered = any(
            k["comparison_class"] == r_cls
            and k["target_investigation_id"] == r_target
            and set(k["condition_feature_ids"]).issubset(r_feats)
            for k in kept
        )
        if not covered:
            kept.append(r)
    return kept


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rules", type=Path, default=RULES)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--out-readable", type=Path, default=OUT_READABLE)
    ap.add_argument("--converge", action="store_true",
                    help="Also emit B2 converged rules (context-variant collapse).")
    ap.add_argument("--out-converged", type=Path,
                    default=Path(r"D:\Projects\llm_benchmark\data\phenotype\conditional_rules_converged.jsonl"))
    ap.add_argument("--out-converged-readable", type=Path,
                    default=Path(r"D:\Projects\llm_benchmark\data\phenotype\converge_rules_readable.md"))
    args = ap.parse_args(argv)

    rules = load_rules(args.rules)
    deduped = dedup_rules(rules)

    args.out.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in deduped) + "\n",
        encoding="utf-8")

    from collections import Counter
    by_class = Counter(r["comparison_class"] for r in deduped)
    lines = [
        "# 去重后的 accepted 规则（按 score 降序）\n",
        f"> 去重前 {len(rules)} 条 → 去重后 {len(deduped)} 条\n\n",
        "| 比较类 | 条件特征 | 答案 | score | n_x | lift |\n",
        "|---|---|---|---|---:|---:|---:|\n",
    ]
    for r in sorted(deduped, key=lambda x: -(x.get("score") or 0.0)):
        cond = "; ".join(r["condition_display_names"])
        lines.append(
            f"| {r['comparison_class']} | {cond} | {r['target_investigation_name']} "
            f"| {r['score']:.2f} | {r['n_x']} | {r['lift']:.2f} |\n"
        )
    args.out_readable.write_text("".join(lines), encoding="utf-8")

    summary = {
        "n_before": len(rules),
        "n_after": len(deduped),
        "by_class": dict(by_class),
    }

    if args.converge:
        converged = converge_rules(deduped)
        args.out_converged.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in converged) + "\n",
            encoding="utf-8")
        c_by_class = Counter(r["comparison_class"] for r in converged)
        clines = [
            "# 收敛后的规则（按临床表现核心信号去变体，B2）\n",
            f"> 去重后 {len(deduped)} 条 → 收敛后 {len(converged)} 条\n\n",
            "| 比较类 | 条件特征 | 答案 | score | n_x | lift |\n",
            "|---|---|---|---|---:|---:|---:|\n",
        ]
        for r in converged:
            cond = "; ".join(r["condition_display_names"])
            clines.append(
                f"| {r['comparison_class']} | {cond} | {r['target_investigation_name']} "
                f"| {r['score']:.2f} | {r['n_x']} | {r['lift']:.2f} |\n"
            )
        args.out_converged_readable.write_text("".join(clines), encoding="utf-8")
        summary["n_converged"] = len(converged)
        summary["converged_by_class"] = dict(c_by_class)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
