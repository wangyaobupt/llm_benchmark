"""Referral/service task (task 4): chief complaint -> most likely service.

Behavioral gold = R1 services 团队变更 (住院场景), per
docs/reports/five-dimension-execution-refinement.md §2.4. R2 (poe consult, ED)
and R3 (transfers) are NOT used here (transfers = 床位管理噪声; consult needs
ED-scope design). Normative gold has no international scale — deferred.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from benchmark_common.task import run_task

EVENTS = Path(r"G:\Projects\llm_benchmark\data\derived\coronary_all_three_modules_full\event_pipeline\normalization\normalized_events.parquet")
SPLIT = Path(r"D:\Projects\llm_benchmark\tasks\investigation_selection\output\split\subject_split.parquet")
OUT = Path(r"D:\Projects\llm_benchmark\tasks\referral\output\development")

# MIMIC-IV service code -> readable name (placeholder, review before freeze).
SERVICE_MAP = {
    "MED": "medicine", "CMED": "cardiac medicine", "NMED": "neurology medicine",
    "OMED": "oncology medicine", "SURG": "surgery", "CSURG": "cardiac surgery",
    "VSURG": "vascular surgery", "ORTHO": "orthopedics", "NSURG": "neurosurgery",
    "TRAUM": "trauma", "TSURG": "trauma surgery", "PSURG": "plastic surgery",
    "GU": "urology", "GYN": "gynecology", "PSYCH": "psychiatry",
    "ENT": "otolaryngology", "OBS": "obstetrics", "EYE": "ophthalmology",
}


def candidate_fn(events):
    d = events[events["event_kind"] == "service_changed"].copy()
    d["candidate"] = d["source_label"].str.upper().map(SERVICE_MAP)
    d = d[d["candidate"].notna()]
    return d[["hadm_id", "candidate"]].drop_duplicates()


def pool_fn(events):
    d = candidate_fn(events)
    return (d.groupby("candidate")["hadm_id"].nunique()
             .sort_values(ascending=False).index.tolist())


def stem_fn(condition):
    return (f"A patient presents to the emergency department with {condition}. "
            f"Which service is the patient most likely to be admitted under?")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--events", type=Path, default=EVENTS)
    ap.add_argument("--split", type=Path, default=SPLIT)
    ap.add_argument("--role", default="development")
    ap.add_argument("--min-share-gap", type=float, default=0.10)
    ap.add_argument("--out-dir", type=Path, default=OUT)
    args = ap.parse_args()

    s = run_task(args.events, args.split, candidate_fn, pool_fn, stem_fn,
                 "referral", role=args.role, out_dir=args.out_dir,
                 min_share_gap=args.min_share_gap)
    print("=" * 70)
    print(f"REFERRAL (task 4) — behavioral gold (R1 services), {s['gold_semantics']}")
    print("=" * 70)
    print(f"admissions: {s['admissions_total']}, patterns: {s['n_gold_patterns']}, "
          f"questions: {s['n_questions']}")
    for g in s["gold_patterns"][:15]:
        print(f"  {g['condition']:<30} -> {g['gold_candidate']} (sel={g['gold_selectivity']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
