"""End-to-end: full development phenotype conditions -> v2 rule mining.

Verifies the whole chain at full scale (23,626 admissions -> 2.44M distinct
conditions -> accepted/rejected rules) and writes the rule artifacts.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

sys.path.insert(0, str(ROOT / "versions" / "v2-llm-stem"))

from data_pipeline.archived.phenotype.progress import write_progress  # noqa: E402
from data_pipeline.archived.phenotype.run_phenotype import load_events  # noqa: E402
from mcq.catalog import build_catalog  # noqa: E402
from mcq.config_loader import load_thresholds  # noqa: E402
from mcq.mining import mine_rules  # noqa: E402

CONDITIONS = Path(r"D:\Projects\llm_benchmark\data\phenotype\visit_conditions_development.parquet")
OUT_RULES = Path(r"D:\Projects\llm_benchmark\data\phenotype\conditional_rules_development.jsonl")
OUT_REJECTED = Path(r"D:\Projects\llm_benchmark\data\phenotype\conditional_rules_rejected_development.jsonl")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="exploratory", choices=["formal", "exploratory"])
    args = ap.parse_args()

    events, meta = load_events(
        Path(r"G:\Projects\llm_benchmark\data\derived\coronary_all_three_modules_full\event_pipeline\normalization\normalized_events.parquet"),
        Path(r"D:\Projects\llm_benchmark\tasks\investigation_selection\output\split\subject_split.parquet"),
        "development",
    )
    conditions = pd.read_parquet(CONDITIONS)
    catalog = build_catalog(events)
    thresholds = load_thresholds(args.profile)

    n_conditions = int(conditions["condition"].nunique())
    t0 = time.time()
    write_progress("mining", {
        "status": "running", "stage": "loading", "n_total": n_conditions,
        "n_done": 0, "n_accepted": 0, "elapsed_s": 0,
    })

    def _cb(info):
        write_progress("mining", {
            "status": "running", "stage": f"mining {info['class']}",
            "n_total": n_conditions, "n_done": None,
            "n_accepted": info["n_accepted"], "elapsed_s": round(time.time() - t0, 1),
        })

    counts: dict[str, int] = {}
    accepted, rejected = mine_rules(
        events, conditions, catalog, thresholds,
        materialize_rejections=False, counts=counts, progress_callback=_cb,
    )
    elapsed = time.time() - t0

    with OUT_RULES.open("w", encoding="utf-8") as fh:
        for r in accepted:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    write_progress("mining", {
        "status": "done", "stage": "done", "n_total": n_conditions,
        "n_done": None, "n_accepted": len(accepted), "elapsed_s": round(elapsed, 1),
    })

    from collections import Counter
    print(json.dumps({
        "profile": args.profile,
        "elapsed_seconds": round(elapsed, 1),
        "n_accepted": len(accepted),
        "n_rejected_materialized": len(rejected),
        "rejection_counts": dict(Counter(counts).most_common()),
        "accepted_by_class": dict(Counter(r["comparison_class"] for r in accepted)),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
