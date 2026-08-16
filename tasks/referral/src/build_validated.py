"""Filter referral questions to validation-stable rules."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from benchmark_common.task import build_validated

QUESTIONS = Path(r"D:\Projects\llm_benchmark\tasks\referral\output\development\questions.jsonl")
VALIDATION = Path(r"D:\Projects\llm_benchmark\tasks\referral\output\validation\validation_results.jsonl")
OUT = Path(r"D:\Projects\llm_benchmark\tasks\referral\output\validated")


def main() -> int:
    r = build_validated(QUESTIONS, VALIDATION, OUT)
    print(f"rank1={r['rank1']}, top3={r['top3']}, dropped={r['dropped']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
