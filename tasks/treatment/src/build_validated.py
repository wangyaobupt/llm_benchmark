"""Filter treatment questions (per layer) to validation-stable rules."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from benchmark_common.task import build_validated

BASE = Path(r"D:\Projects\llm_benchmark\tasks\treatment\output")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--layer", default="t1", choices=["t1", "t2", "t3"])
    args = ap.parse_args()

    questions = BASE / args.layer / "development" / "questions.jsonl"
    validation = BASE / args.layer / "validation" / "validation_results.jsonl"
    out_dir = BASE / args.layer / "validated"
    r = build_validated(questions, validation, out_dir)
    print(f"rank1={r['rank1']}, top3={r['top3']}, dropped={r['dropped']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
