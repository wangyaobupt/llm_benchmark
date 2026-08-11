"""Export unresolved_events.parquet from already-landed Parquet outputs.

独立补产出脚本：直接从已落盘的 timeline_events / event_items / documents
parquet 构造 unresolved_events.parquet，无需重跑全量聚合管线。

修复后的 SQL 先过滤 link_status='unresolved'（约 1300 万行）作为 base，
再 INNER JOIN event_items 取 native_row_key，把昂贵的 GROUP BY 基数从
全量 event_id（2.38 亿）降到 unresolved event_id（1300 万），与
sql/episode_aggregation/build_auxiliary.sql 中修复后的视图定义保持一致。
"""
from __future__ import annotations

from pathlib import Path

import duckdb

OUTPUT_DIR = Path(r"G:\Projects\医疗数据集评测-MIMIC\outputs\episodes")
TEMP_DIR = OUTPUT_DIR / "duckdb-unresolved-export"


def lit(p: Path) -> str:
    """Return a SQL-safe single-quoted literal for a path."""
    return "'" + p.resolve().as_posix().replace("'", "''") + "'"


def main() -> int:
    te = lit(OUTPUT_DIR / "timeline_events.parquet")
    ei = lit(OUTPUT_DIR / "event_items.parquet")
    dc = lit(OUTPUT_DIR / "documents.parquet")
    dest = OUTPUT_DIR / "unresolved_events.parquet"

    TEMP_DIR.mkdir(parents=True, exist_ok=True)

    conn = duckdb.connect(config={"memory_limit": "8GB", "threads": "4"})
    conn.execute(f"SET temp_directory = {lit(TEMP_DIR)}")
    conn.execute("SET preserve_insertion_order = false")

    conn.execute(f"CREATE VIEW timeline_events AS SELECT * FROM read_parquet({te})")
    conn.execute(f"CREATE VIEW event_items AS SELECT * FROM read_parquet({ei})")
    conn.execute(f"CREATE VIEW documents AS SELECT * FROM read_parquet({dc})")

    conn.execute(
        f"""
        COPY (
            WITH unresolved_event_base AS (
                SELECT
                    event_id,
                    subject_id,
                    event_type,
                    event_time,
                    available_time,
                    native_hadm_id,
                    native_contact_id,
                    candidate_episode_count,
                    unresolved_reason,
                    source_table
                FROM timeline_events
                WHERE link_status = 'unresolved'
            ),
            event_keys AS (
                SELECT i.event_id, MIN(i.native_row_key) AS native_row_key
                FROM event_items i
                INNER JOIN unresolved_event_base b ON b.event_id = i.event_id
                GROUP BY i.event_id
            )
            SELECT
                b.event_id,
                b.subject_id,
                b.event_type,
                b.event_time,
                b.available_time,
                b.native_hadm_id,
                TRY_CAST(SPLIT_PART(b.native_contact_id, ':', 2) AS BIGINT) AS native_stay_id,
                b.candidate_episode_count,
                b.unresolved_reason,
                b.source_table,
                k.native_row_key
            FROM unresolved_event_base b
            LEFT JOIN event_keys k ON k.event_id = b.event_id

            UNION ALL

            SELECT
                'DOCUMENT:' || d.note_id,
                d.subject_id,
                'document',
                d.event_time,
                d.available_time,
                d.native_hadm_id,
                NULL::BIGINT,
                d.candidate_episode_count,
                d.unresolved_reason,
                d.source_table,
                'note_id=' || d.note_id
            FROM documents d
            WHERE d.link_status = 'unresolved'
        ) TO {lit(dest)} (FORMAT PARQUET, COMPRESSION ZSTD)
        """
    )

    rows = conn.execute(f"SELECT COUNT(*) FROM read_parquet({lit(dest)})").fetchone()[0]
    print(f"unresolved_events.parquet: {rows:,} rows -> {dest}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())