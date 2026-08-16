"""Explore the 1000-admission AGGREGATION artifacts to plan the first
investigation-selection task prototype.

Read-only. Uses aggregation/processed_events.parquet (all normalized event fields)
and aggregation/raw_source_records.parquet (free text + lineage) because the
cleaning/normalization/review dirs are ACL-denied in this environment.
"""
import sys
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[4]
AGG = ROOT / "data" / "test_1000_0812" / "event_pipeline_output" / "aggregation"

EVENTS = AGG / "processed_events.parquet"
RAW = AGG / "raw_source_records.parquet"


def section(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def dump_schema(path: Path, name: str) -> None:
    section(f"schema: {name}")
    try:
        sch = pq.read_schema(path)
        for f in sch:
            print(f"  {f.name:<36} {f.type}")
    except Exception as e:  # noqa: BLE001
        print(f"  ERROR: {e!r}")


def value_counts(path: Path, cols: list[str], name: str) -> None:
    section(f"value counts: {name}")
    try:
        t = pq.read_table(path, columns=[c for c in cols])
    except Exception as e:  # noqa: BLE001
        print(f"  ERROR reading columns: {e!r}")
        return
    df = t.to_pandas()
    for c in cols:
        if c not in df.columns:
            print(f"  [missing] {c}")
            continue
        print(f"\n  --- {c} ---")
        vc = df[c].value_counts(dropna=False).head(50)
        for val, cnt in vc.items():
            print(f"    {val!r:<60} {cnt}")


def cross_tab(path: Path, a: str, b: str) -> None:
    section(f"cross-tab: {a} x {b}")
    try:
        t = pq.read_table(path, columns=[a, b])
    except Exception as e:  # noqa: BLE001
        print(f"  ERROR: {e!r}")
        return
    df = t.to_pandas()
    ct = df.groupby([a, b], dropna=False).size().reset_index(name="n")
    ct = ct.sort_values("n", ascending=False).head(70)
    for _, row in ct.iterrows():
        print(f"    {row[a]!r:<30} | {row[b]!r:<34} | {row['n']}")


def sample(path: Path, cols: list[str], predicate_desc: str, n: int = 6) -> None:
    section(f"sample rows: {predicate_desc}")
    try:
        t = pq.read_table(path, columns=cols)
    except Exception as e:  # noqa: BLE001
        print(f"  ERROR: {e!r}")
        return
    df = t.to_pandas()
    print(f"  (total rows = {len(df)})")
    with pd_option():
        print(df.head(n).to_string(max_colwidth=44))


def pd_option():
    import pandas as pd
    return pd.option_context("display.max_columns", None, "display.width", 240)


def main() -> int:
    for p in (EVENTS, RAW):
        if not p.exists():
            print(f"MISSING: {p}")
            return 2

    dump_schema(EVENTS, "processed_events.parquet")
    value_counts(
        EVENTS,
        ["event_kind", "entity_type", "source_table", "lifecycle_action",
         "assertion", "evidence_phase", "normalization_status",
         "unit_normalization_status", "time_policy_id", "time_precision"],
        "processed_events",
    )
    cross_tab(EVENTS, "source_table", "event_kind")

    # POE orders (target actions)
    sample(
        EVENTS,
        ["event_id", "subject_id", "hadm_id", "source_table", "event_kind",
         "lifecycle_action", "entity_type", "source_label", "preferred_name",
         "concept_id", "normalization_status", "event_time", "available_time",
         "assertion"],
        "POE timeline events",
    )

    # ED chief complaint / triage
    sample(
        EVENTS,
        ["event_id", "subject_id", "hadm_id", "source_table", "event_kind",
         "entity_type", "source_label", "value_text", "event_time",
         "available_time", "assertion", "preferred_name", "concept_id"],
        "ED triage / chief complaint",
    )

    dump_schema(RAW, "raw_source_records.parquet")
    return 0


if __name__ == "__main__":
    sys.exit(main())
