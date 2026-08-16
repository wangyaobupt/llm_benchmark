"""One-shot fixup: update remaining docs (README + recent reports) path refs."""
import sys
from pathlib import Path

ROOT = Path(r"D:\Projects\llm_benchmark")

PLANS = {
    "benchmark_common/README.md": [
        ("investigation_selection/output/split/", "tasks/investigation_selection/output/split/"),
    ],
    "docs/reports/final-test-blind-evaluation.md": [
        ("investigation_selection/output/split/subject_split.parquet",
         "tasks/investigation_selection/output/split/subject_split.parquet"),
        ("investigation_selection/src/run_validation.py", "tasks/investigation_selection/src/run_validation.py"),
        ("clinical_diagnosis/src/run_validation.py", "tasks/clinical_diagnosis/src/run_validation.py"),
        ("treatment/src/validate.py", "tasks/treatment/src/validate.py"),
        ("referral/src/validate.py", "tasks/referral/src/validate.py"),
    ],
    "docs/reports/execution-progress-p1-p5.md": [
        ("treatment/src/run.py", "tasks/treatment/src/run.py"),
        ("clinical_diagnosis/src/diagnosis.py", "tasks/clinical_diagnosis/src/diagnosis.py"),
        ("referral/src/run.py", "tasks/referral/src/run.py"),
        ("treatment/src/sweep.py", "tasks/treatment/src/sweep.py"),
        ("clinical_diagnosis/src/sweep.py", "tasks/clinical_diagnosis/src/sweep.py"),
        ("referral/src/sweep.py", "tasks/referral/src/sweep.py"),
        ("discharge_followup/src/", "tasks/discharge_followup/src/"),
    ],
}


def main() -> int:
    for rel, repls in PLANS.items():
        p = ROOT / rel
        text = p.read_text(encoding="utf-8")
        for old, new in repls:
            n = text.count(old)
            if n:
                text = text.replace(old, new)
                print(f"{rel}: {n} x {old!r}")
        p.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
