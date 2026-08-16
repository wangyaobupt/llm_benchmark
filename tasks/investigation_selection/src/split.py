"""Build an EXPLORATORY deterministic subject-level split on the full cohort.

This is NOT the formal protocol-locked subject split (which requires a frozen
protocol). It uses SHA256(subject_id + seed) ranking + largest remainder to
assign each subject to development / validation / final_test. Placeholder
ratios only; clearly marked exploratory.
"""
import hashlib
import json
import sys
from pathlib import Path

import pyarrow.parquet as pq
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
EVENTS = Path(r"G:\Projects\llm_benchmark\data\derived\coronary_all_three_modules_full\event_pipeline\normalization\normalized_events.parquet")
OUT = ROOT / "tasks" / "investigation_selection" / "output" / "split"

ROLES = ["development", "validation", "final_test"]
# placeholder ratios (unresolved scientific decision; exploratory only)
RATIOS = {"development": 0.60, "validation": 0.20, "final_test": 0.20}
SEED = "exploratory-full-cohort-split-2026"


def _rank_key(subject_id: str) -> str:
    return hashlib.sha256((subject_id + "|" + SEED).encode("utf-8")).hexdigest()


def build_split(subjects: list[str]) -> dict[str, str]:
    n = len(subjects)
    ranked = sorted(subjects, key=_rank_key)
    # largest remainder
    quotas = {r: n * RATIOS[r] for r in ROLES}
    base = {r: int(quotas[r]) for r in ROLES}
    leftover = n - sum(base.values())
    for r in sorted(ROLES, key=lambda x: -(quotas[x] - int(quotas[x]))):
        if leftover <= 0:
            break
        base[r] += 1
        leftover -= 1
    assignment: dict[str, str] = {}
    idx = 0
    for role in ROLES:
        for s in ranked[idx:idx + base[role]]:
            assignment[s] = role
        idx += base[role]
    return assignment


def main() -> int:
    if not EVENTS.exists():
        print("MISSING", EVENTS)
        return 2
    t = pq.read_table(EVENTS, columns=["subject_id", "hadm_id"]).to_pandas()
    subjects = sorted(t["subject_id"].unique().tolist())
    adm = t.groupby("subject_id")["hadm_id"].nunique()
    print(f"subjects: {len(subjects)}, admissions: {int(t['hadm_id'].nunique())}")

    assignment = build_split(subjects)
    df = pd.DataFrame({"subject_id": subjects,
                       "role": [assignment[s] for s in subjects]})
    df["n_admissions"] = df["subject_id"].map(adm)

    counts = df.groupby("role").agg(
        n_subjects=("subject_id", "nunique"),
        n_admissions=("n_admissions", "sum"),
    ).reindex(ROLES)

    OUT.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT / "subject_split.parquet", index=False)
    manifest = {
        "status": "exploratory_unreviewed",
        "method": "sha256-ranked-largest-remainder",
        "seed": SEED,
        "ratios": RATIOS,
        "counts": {
            role: {
                "n_subjects": int(counts.loc[role, "n_subjects"]),
                "n_admissions": int(counts.loc[role, "n_admissions"]),
            }
            for role in ROLES
        },
    }
    (OUT / "split_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== split counts (exploratory placeholder ratios) ===")
    for role in ROLES:
        print(f"  {role:<12} subjects={int(counts.loc[role, 'n_subjects']):>6}  "
              f"admissions={int(counts.loc[role, 'n_admissions']):>6}")
    print(f"\nwritten to {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
