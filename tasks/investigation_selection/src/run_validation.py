"""Validate development gold rules on the full-cohort VALIDATION split."""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from pipeline import _verify_normalized_events, _sha256_file, validate_rules

EVENTS = Path(r"G:\Projects\llm_benchmark\data\derived\coronary_all_three_modules_full\event_pipeline\normalization\normalized_events.parquet")
SPLIT = Path(r"D:\Projects\llm_benchmark\tasks\investigation_selection\output\split\subject_split.parquet")
DEV_GOLD = Path(r"D:\Projects\llm_benchmark\tasks\investigation_selection\output\development\gold_patterns.jsonl")
BASE = Path(r"D:\Projects\llm_benchmark\tasks\investigation_selection\output")

COLS = ["event_id", "subject_id", "hadm_id", "event_kind", "entity_type",
        "source_label", "preferred_name", "concept_id", "assertion"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--events", type=Path, default=EVENTS)
    ap.add_argument("--split", type=Path, default=SPLIT)
    ap.add_argument("--dev-gold", type=Path, default=DEV_GOLD)
    ap.add_argument("--role", default="validation", choices=["validation", "final_test"])
    ap.add_argument("--min-condition-support", type=int, default=10)
    args = ap.parse_args()
    out_dir = BASE / args.role

    events_hash = _verify_normalized_events(args.events)
    split_hash = _sha256_file(args.split)
    dev_gold = [json.loads(l) for l in args.dev_gold.read_text(encoding="utf-8").splitlines() if l.strip()]

    split = pd.read_parquet(args.split)
    val_subjects = set(split[split["role"] == args.role]["subject_id"].astype(str))
    events = pq.read_table(args.events, columns=COLS).to_pandas()
    events = events[events["subject_id"].astype(str).isin(val_subjects)]

    out = validate_rules(dev_gold, events,
                         min_condition_support=args.min_condition_support)
    s = out["summary"]

    print("=" * 78)
    print(f"{args.role.upper()} — development rules vs independent patients (exploratory)")
    print("=" * 78)
    print(f"dev rules          : {s['n_rules']}")
    print(f"checked            : {s['n_checked']}")
    print(f"condition absent   : {s['n_condition_absent']}")
    print(f"insufficient       : {s['n_insufficient_support']}")
    print(f"no candidate       : {s['n_no_eligible_candidate']}")
    print(f"rank-1 concordance : {s['rank1_concordance']}")
    print(f"top-3 concordance  : {s['top3_concordance']}")
    print("\nby class:")
    for cls, v in s["by_class"].items():
        print(f"  {cls:<16} n={v['n_checked']:<4} rank1={v['rank1_concordance']}  "
              f"top3={v['top3_concordance']}")

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "validation_summary.json").write_text(
        json.dumps({"events_sha256": events_hash, "split_sha256": split_hash,
                    "summary": s}, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "validation_results.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in out["results"]) + "\n",
        encoding="utf-8")

    # show a few discordant rules (gold rank > 1)
    discord = [r for r in out["results"]
               if r.get("status") == "checked" and not r["concordant_rank1"]]
    print(f"\n=== discordant rules (gold not rank-1 in validation), n={len(discord)} ===")
    for r in discord[:20]:
        print(f"  {r['class']:<16} {r['condition']:<34} dev={r['gold_candidate']:<20} "
              f"val_top={r['top_candidate_validation']:<20} rank={r['gold_rank']}")
    print(f"\nwritten to {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
