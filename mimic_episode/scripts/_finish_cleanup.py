"""Finish negative-episode cleanup: process the 2 remaining large tables.

After remove_negative_episodes.py timed out on event_items (6 of 8 tables
already cleaned), this script completes the job for event_items and
evidence_links only.

Two-step approach for performance:
  1. Compute small bad_evs (25K rows) + bad_notes (256 rows) via anti-join
     of un-cleaned event_items/evidence_links against cleaned timeline_events/
     documents. This is a read-only scan that produces tiny result sets.
  2. COPY with NOT IN bad_evs/bad_notes. The hash table is tiny (25K) so
     DuckDB can use all available memory for parquet I/O.

A SEMI JOIN against 238M valid event_ids was tried first but the hash table
did not fit in memory, causing 14x slowdown from disk spilling.
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

import duckdb

OUTPUT_DIR = Path(r"G:\Projects\医疗数据集评测-MIMIC\outputs\episodes")
TEMP_DIR = OUTPUT_DIR / "duckdb-finish-temp"


def lit(p: Path) -> str:
    return "'" + str(p.resolve()).replace("'", "''") + "'"


def rp(p: Path) -> str:
    return f"read_parquet({lit(p)})"


def main() -> int:
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    g = OUTPUT_DIR
    conn = duckdb.connect(config={"memory_limit": "20GB", "threads": "4"})
    conn.execute(f"SET temp_directory = {lit(TEMP_DIR)}")
    conn.execute("SET preserve_insertion_order = false")

    # --- Step 1: Compute small bad sets via anti-join (read-only) ---
    print("computing bad_evs (event_ids in event_items but NOT in cleaned timeline_events)...", flush=True)
    conn.execute(f"""
        CREATE TEMP TABLE bad_evs AS
        SELECT DISTINCT event_id FROM {rp(g / 'event_items.parquet')}
        EXCEPT
        SELECT event_id FROM {rp(g / 'timeline_events.parquet')}
    """)
    be = conn.execute("SELECT COUNT(*) FROM bad_evs").fetchone()[0]
    print(f"  bad_evs: {be:,}", flush=True)

    print("computing bad_notes (note_ids in documents-targets but NOT in cleaned documents)...", flush=True)
    conn.execute(f"""
        CREATE TEMP TABLE bad_notes AS
        SELECT DISTINCT target_id AS note_id FROM {rp(g / 'evidence_links.parquet')}
        WHERE target_type = 'document'
        EXCEPT
        SELECT note_id FROM {rp(g / 'documents.parquet')}
    """)
    bn = conn.execute("SELECT COUNT(*) FROM bad_notes").fetchone()[0]
    print(f"  bad_notes: {bn:,}", flush=True)

    def filter_copy(table_name: str, where_sql: str) -> None:
        t0 = time.time()
        src = g / f"{table_name}.parquet"
        tmp = g / f"{table_name}.tmp.parquet"
        # Remove stale tmp if it exists (from a previous interrupted run)
        if tmp.exists():
            tmp.unlink()
            print(f"  removed stale {tmp.name}", flush=True)
        before = conn.execute(f"SELECT COUNT(*) FROM {rp(src)}").fetchone()[0]
        print(f"  filtering {table_name} ({before:,} rows)...", flush=True)
        conn.execute(
            f"COPY (SELECT * FROM {rp(src)} WHERE {where_sql}) "
            f"TO {lit(tmp)} (FORMAT PARQUET, COMPRESSION ZSTD)"
        )
        after = conn.execute(f"SELECT COUNT(*) FROM {rp(tmp)}").fetchone()[0]
        shutil.move(str(tmp), str(src))
        print(
            f"  {table_name:20s} {before:>14,} -> {after:>14,}  "
            f"({before - after:>6,} removed, {time.time() - t0:.1f}s)",
            flush=True,
        )

    # event_items: keep rows whose event_id is NOT in bad_evs
    filter_copy(
        "event_items",
        "event_id NOT IN (SELECT event_id FROM bad_evs)",
    )

    # evidence_links: keep rows whose targets still exist in cleaned tables
    filter_copy(
        "evidence_links",
        "(target_type != 'timeline_event'"
        " OR target_id NOT IN (SELECT event_id FROM bad_evs))"
        " AND (target_type != 'document'"
        " OR target_id NOT IN (SELECT note_id FROM bad_notes))",
    )

    conn.close()
    shutil.rmtree(str(TEMP_DIR), ignore_errors=True)
    print("\n=== Remaining table cleanup complete ===", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
