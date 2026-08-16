"""Validate referral gold rules on a held-out split (validation / final_test)."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parents[0]))

from run import candidate_fn
from benchmark_common.task import validate_task

EVENTS = Path(r"G:\Projects\llm_benchmark\data\derived\coronary_all_three_modules_full\event_pipeline\normalization\normalized_events.parquet")
SPLIT = Path(r"D:\Projects\llm_benchmark\tasks\investigation_selection\output\split\subject_split.parquet")
DEV_GOLD = Path(r"D:\Projects\llm_benchmark\tasks\referral\output\development\gold_patterns.jsonl")
BASE = Path(r"D:\Projects\llm_benchmark\tasks\referral\output")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--role", default="validation", choices=["validation", "final_test"])
    args = ap.parse_args()
    out_dir = BASE / args.role
    out = validate_task(EVENTS, SPLIT, DEV_GOLD, candidate_fn, out_dir, role=args.role)
    s = out["summary"]
    print(f"REFERRAL {args.role}: rank1={s['rank1_concordance']}, "
          f"top3={s['top3_concordance']}, checked={s['n_checked']}/{s['n_rules']}")
    disc = [r for r in out["results"] if r.get("status") == "checked" and not r["concordant_rank1"]]
    print(f"discordant: {len(disc)}")
    for r in disc[:15]:
        print(f"  {r['condition']:<30} dev={r['gold_candidate']:<28} val={r['top_candidate_validation']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
