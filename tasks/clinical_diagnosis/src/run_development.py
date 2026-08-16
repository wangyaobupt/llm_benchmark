"""Run clinical-diagnosis gold generation on the full-cohort DEVELOPMENT split."""
import argparse
import sys
from pathlib import Path

from diagnosis import run_diagnosis

EVENTS = Path(r"G:\Projects\llm_benchmark\data\derived\coronary_all_three_modules_full\event_pipeline\normalization\normalized_events.parquet")
SPLIT = Path(r"D:\Projects\llm_benchmark\tasks\investigation_selection\output\split\subject_split.parquet")
OUT = Path(r"D:\Projects\llm_benchmark\tasks\clinical_diagnosis\output\development")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--events", type=Path, default=EVENTS)
    ap.add_argument("--split", type=Path, default=SPLIT)
    ap.add_argument("--role", type=str, default="development")
    ap.add_argument("--gold-semantics", type=str, default="psr",
                    choices=["psr", "selectivity", "likelihood"])
    ap.add_argument("--out-dir", type=Path, default=OUT)
    args = ap.parse_args()

    summary = run_diagnosis(args.events, args.split, role=args.role,
                            gold_semantics=args.gold_semantics, out_dir=args.out_dir)

    print("=" * 78)
    print("FULL-COHORT DEVELOPMENT — clinical diagnosis (exploratory)")
    print("=" * 78)
    print(f"role           : {summary['split_role']}")
    print(f"subjects       : {summary['subjects_total']}")
    print(f"admissions     : {summary['admissions_total']}")
    print(f"with condition : {summary['admissions_with_condition']}")
    print(f"gold_semantics : {summary['gold_semantics']}")
    print(f"events sha256  : {summary['events_sha256']}")
    print(f"gold patterns  : {summary['n_gold_patterns']}")
    print(f"questions      : {summary['n_questions']}")

    print("\n=== sample gold patterns (top 20) ===")
    for g in summary["gold_patterns"][:20]:
        print(f"  {g['condition']:<34} -> {g['gold_candidate']} "
              f"(share={g['gold_share']}, sel={g['gold_selectivity']}, psr={g['gold_psr']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
