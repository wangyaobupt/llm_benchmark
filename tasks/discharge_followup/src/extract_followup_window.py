"""First-pass F1 extraction: follow-up time window from discharge summaries.

Regex-based (no NER yet). Discretizes "follow up in X <unit>" into the survey's
windows: <=1w, 1-4w, 1-3m, 3-12m, 3-5y. Signal-check only (exploratory_unreviewed).
"""
import argparse
import json
import re
import sys
from pathlib import Path

import pandas as pd

BASE = Path(r"D:\Projects\llm_benchmark\tasks\discharge_followup\output")

# "follow up in 2 weeks" / "follow up with cardiology in 2 weeks" /
# "follow-up in 3-4 weeks" / "return in 6 weeks" / "recheck in 1 week"
_PAT = re.compile(
    r"(?:follow[\s-]*up|followup|return|recheck|f/u|fu)\s+"
    r"(?:with\s+[\w\s.,/'-]+?\s+)?"
    r"(?:in|within|every|at)\s+"
    r"(\d{1,2})\s*(?:-\s*(\d{1,2}))?\s*"
    r"(day|days|week|weeks|month|months|year|years)",
    re.IGNORECASE,
)


def _days(n: int, unit: str) -> int:
    u = unit.lower()
    if u.startswith("day"):
        return n
    if u.startswith("week"):
        return n * 7
    if u.startswith("month"):
        return n * 30
    return n * 365


def bucket(days: int) -> str:
    if days <= 7:
        return "<=1w"
    if days <= 28:
        return "1-4w"
    if days <= 90:
        return "1-3m"
    if days <= 365:
        return "3-12m"
    return "3-5y"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--role", default="development")
    ap.add_argument("--in-dir", type=Path, default=BASE)
    args = ap.parse_args()

    df = pd.read_parquet(args.in_dir / args.role / "discharge_text.parquet")
    rows = []
    for hadm, text in zip(df["hadm_id"], df["discharge_text"]):
        if not text:
            continue
        for m in _PAT.finditer(text):
            n1 = int(m.group(1))
            n2 = int(m.group(2)) if m.group(2) else None
            unit = m.group(3)
            # use the upper bound when a range is given ("3-4 weeks" -> 4)
            days = _days(n2 if n2 else n1, unit)
            rows.append({"hadm_id": hadm, "days": days,
                         "bucket": bucket(days), "match": m.group(0).strip()})

    out = pd.DataFrame(rows)
    print(f"matches: {len(out)} across {out['hadm_id'].nunique()} admissions")
    print(out["bucket"].value_counts().to_string())
    print("\n--- 20 sample matches ---")
    print(out.sample(20, random_state=1)[["bucket", "match"]].to_string(index=False))

    out_dir = args.in_dir / args.role
    out.to_parquet(out_dir / "followup_window.parquet", index=False)
    (out_dir / "followup_window_manifest.json").write_text(json.dumps({
        "status": "exploratory_unreviewed", "stage": "f1_followup_window_first_pass",
        "n_matches": int(len(out)), "n_admissions": int(out["hadm_id"].nunique()),
        "pattern": _PAT.pattern,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwritten to {out_dir / 'followup_window.parquet'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
