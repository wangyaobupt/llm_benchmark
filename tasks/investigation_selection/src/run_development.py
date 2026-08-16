"""Run selectivity-gold generation on the full-cohort DEVELOPMENT split."""
import argparse
import sys
from pathlib import Path

from pipeline import run_split

EVENTS = Path(r"G:\Projects\llm_benchmark\data\derived\coronary_all_three_modules_full\event_pipeline\normalization\normalized_events.parquet")
SPLIT = Path(r"D:\Projects\llm_benchmark\tasks\investigation_selection\output\split\subject_split.parquet")
OUT = Path(r"D:\Projects\llm_benchmark\tasks\investigation_selection\output\development")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--events", type=Path, default=EVENTS)
    ap.add_argument("--split", type=Path, default=SPLIT)
    ap.add_argument("--role", type=str, default="development")
    ap.add_argument("--out-dir", type=Path, default=OUT)
    args = ap.parse_args()

    summary = run_split(args.events, args.split, role=args.role,
                        gold_semantics="selectivity",
                        min_condition_support=10,
                        out_dir=args.out_dir)

    print("=" * 78)
    print("FULL-COHORT DEVELOPMENT — selectivity gold (exploratory)")
    print("=" * 78)
    print(f"role              : {summary['split_role']}")
    print(f"subjects          : {summary['subjects_total']}")
    print(f"admissions        : {summary['admissions_total']}")
    print(f"with condition    : {summary['admissions_with_condition']}")
    print(f"events sha256     : {summary['events_sha256']}")
    print(f"split  sha256     : {summary['split_sha256']}")
    print(f"gold patterns     : {summary['n_gold_patterns']}")
    print(f"questions         : {summary['n_questions']}")

    by_class: dict[str, int] = {}
    for g in summary["gold_patterns"]:
        by_class[g["class"]] = by_class.get(g["class"], 0) + 1
    print("patterns by class :", by_class)
    return 0


if __name__ == "__main__":
    sys.exit(main())
