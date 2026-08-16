"""CLI: run the exploratory investigation-selection generator and print a
readable report. Writes JSON artifacts to an output directory when given one.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from pipeline import CLASS_LABEL, run


def _fmt_cat(cat: list[dict]) -> str:
    return ", ".join(f"{c['candidate']}({c['n_adm']})" for c in cat)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--events", type=Path, default=None)
    ap.add_argument("--min-condition-support", type=int, default=5)
    ap.add_argument("--gold-semantics", type=str, default="psr",
                    choices=["selectivity", "likelihood", "psr",
                             "specificity_reliability"])
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--max-questions", type=int, default=40)
    args = ap.parse_args()

    summary = run(
        events_path=args.events,
        min_condition_support=args.min_condition_support,
        gold_semantics=args.gold_semantics,
        out_dir=args.out_dir,
    )

    print("=" * 78)
    print("INVESTIGATION-SELECTION — EXPLORATORY FIRST CUT (unreviewed)")
    print("=" * 78)
    print(f"source            : {summary['source']}")
    print(f"admissions total  : {summary['admissions_total']}")
    print(f"with condition    : {summary['admissions_with_condition']}")
    print(f"input sha256      : {summary['input_sha256']}")
    print(f"min cond support  : {summary['params']['min_condition_support']}")
    print(f"max baseline share: {summary['params']['max_baseline_share']}")
    print(f"gold patterns     : {summary['n_gold_patterns']}")
    print(f"questions         : {summary['n_questions']}")

    print("\n--- candidate catalog ---")
    for k, label in [("imaging", "imaging"), ("clinical_order", "clinical"),
                     ("laboratory", "laboratory")]:
        cat = summary["candidate_catalog"][k]
        print(f"\n[{label}] {len(cat)} candidates (top shown)")
        print("  " + _fmt_cat(cat[:15]))

    print("\n--- behavioral gold patterns (condition -> most likely) ---")
    by_class: dict[str, list[dict]] = {}
    for g in summary["gold_patterns"]:
        by_class.setdefault(g["class"], []).append(g)
    for k in ("imaging", "clinical_order", "laboratory"):
        rows = by_class.get(k, [])
        print(f"\n[{k}] ({len(rows)} patterns)")
        for g in rows[:20]:
            print(f"  {g['condition']!r:<32} -> {g['gold_candidate']!r:<24} "
                  f"share={g['gold_share']:.2f} sel={g['gold_selectivity']} "
                  f"(n={g['condition_support']})")

    print("\n--- sample questions ---")
    for q in summary["questions"][: args.max_questions]:
        print(f"\n[{q['question_id']}] class={q['comparison_class']} "
              f"support={q['condition_support']}")
        print(f"  {q['stem']}")
        for i, o in enumerate(q["options"]):
            mark = " *" if i == q["answer_index"] else ""
            print(f"    {chr(65 + i)}. {o}{mark}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
