"""Remove negative-duration episodes and cascade-delete related rows.

In-place filters all 9 output Parquet files to exclude 154 episodes where
clinical_end_time < episode_start_time. Aligned with the build_episodes.sql
source fix so future full reruns are also clean.
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path

import duckdb

OUTPUT_DIR = Path(r"G:\Projects\医疗数据集评测-MIMIC\outputs\episodes")
TEMP_DIR = OUTPUT_DIR / "duckdb-cleanup-temp"


def lit(p: Path) -> str:
    return "'" + p.resolve().as_posix().replace("'", "''") + "'"


def rp(p: Path) -> str:
    """Return read_parquet(...) SQL fragment."""
    return f"read_parquet({lit(p)})"


def main() -> int:
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(config={"memory_limit": "12GB", "threads": "4"})
    conn.execute(f"SET temp_directory = {lit(TEMP_DIR)}")
    conn.execute("SET preserve_insertion_order = false")

    g = OUTPUT_DIR

    # --- Identify bad episode_ids ---
    conn.execute(f"CREATE VIEW ep AS SELECT * FROM {rp(g / 'episode_index.parquet')}")
    bad = conn.execute(
        "SELECT episode_id FROM ep WHERE clinical_end_time < episode_start_time"
    ).fetchall()
    bad_eps = [r[0] for r in bad]
    print(f"Bad episodes to remove: {len(bad_eps)}")

    conn.execute(
        "CREATE TEMP TABLE bad_eps AS SELECT unnest(?::VARCHAR[]) AS episode_id",
        [bad_eps],
    )

    conn.execute(f"""
        CREATE TEMP TABLE bad_evs AS
        SELECT DISTINCT event_id FROM {rp(g / 'timeline_events.parquet')}
        WHERE episode_id IN (SELECT episode_id FROM bad_eps)
    """)
    bad_ev_count = conn.execute("SELECT COUNT(*) FROM bad_evs").fetchone()[0]
    print(f"  bad event_ids: {bad_ev_count:,}")

    conn.execute(f"""
        CREATE TEMP TABLE bad_notes AS
        SELECT DISTINCT note_id FROM {rp(g / 'documents.parquet')}
        WHERE episode_id IN (SELECT episode_id FROM bad_eps)
    """)
    bad_note_count = conn.execute("SELECT COUNT(*) FROM bad_notes").fetchone()[0]
    print(f"  bad note_ids: {bad_note_count:,}")

    def filter_table(table_name: str, where_clause: str) -> None:
        t0 = time.time()
        src = g / f"{table_name}.parquet"
        tmp = g / f"{table_name}.tmp.parquet"
        before = conn.execute(f"SELECT COUNT(*) FROM {rp(src)}").fetchone()[0]
        conn.execute(f"""
            COPY (SELECT * FROM {rp(src)} WHERE {where_clause})
            TO {lit(tmp)} (FORMAT PARQUET, COMPRESSION ZSTD)
        """)
        after = conn.execute(f"SELECT COUNT(*) FROM {rp(tmp)}").fetchone()[0]
        shutil.move(str(tmp), str(src))
        removed = before - after
        print(
            f"  {table_name:30s} {before:>14,} -> {after:>14,}  "
            f"({removed:>6,} removed, {time.time()-t0:.1f}s)"
        )

    # Tables with non-nullable episode_id
    for t in ["episode_index", "care_contacts", "episode_coverage", "patient_history_refs"]:
        filter_table(t, "episode_id NOT IN (SELECT episode_id FROM bad_eps)")

    # Tables with nullable episode_id (keep NULL = unresolved)
    for t in ["timeline_events", "documents"]:
        filter_table(
            t,
            "episode_id IS NULL OR episode_id NOT IN (SELECT episode_id FROM bad_eps)",
        )

    # event_items: filter by event_id
    filter_table("event_items", "event_id NOT IN (SELECT event_id FROM bad_evs)")

    # evidence_links: exclude bad events and bad documents
    filter_table(
        "evidence_links",
        "(target_type != 'timeline_event'"
        " OR target_id NOT IN (SELECT event_id FROM bad_evs))"
        " AND (target_type != 'document'"
        " OR target_id NOT IN (SELECT note_id FROM bad_notes))",
    )

    # unresolved_events: skip (bad episodes' events were linked, not unresolved)
    print(f"  {'unresolved_events':30s} (no filtering needed - linked episodes)")

    conn.close()
    shutil.rmtree(str(TEMP_DIR), ignore_errors=True)
    print("\n=== Cleanup complete ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())