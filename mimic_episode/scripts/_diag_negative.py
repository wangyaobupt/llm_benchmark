"""Read-only diagnostic: count negative-duration episodes."""
from pathlib import Path
import duckdb

G = Path(r"G:\Projects\医疗数据集评测-MIMIC\outputs\episodes")


def lit(p: Path) -> str:
    return "'" + str(p.resolve()).replace("'", "''") + "'"


def rp(p: Path) -> str:
    return f"read_parquet({lit(p)})"


conn = duckdb.connect(config={"memory_limit": "8GB", "threads": "4"})
conn.execute("SET preserve_insertion_order = false")

ep = G / "episode_index.parquet"
total = conn.execute(f"SELECT COUNT(*) FROM {rp(ep)}").fetchone()[0]
bad = conn.execute(
    f"SELECT COUNT(*) FROM {rp(ep)} WHERE clinical_end_time < episode_start_time"
).fetchone()[0]
print(f"episode_index  total={total:,}  negative_duration={bad}")

te = G / "timeline_events.parquet"
dc = G / "documents.parquet"
bad_events = conn.execute(
    f"SELECT COUNT(*) FROM {rp(te)} "
    f"WHERE episode_id IN (SELECT episode_id FROM {rp(ep)} "
    f"WHERE clinical_end_time < episode_start_time)"
).fetchone()[0]
bad_docs = conn.execute(
    f"SELECT COUNT(*) FROM {rp(dc)} "
    f"WHERE episode_id IN (SELECT episode_id FROM {rp(ep)} "
    f"WHERE clinical_end_time < episode_start_time)"
).fetchone()[0]
print(f"cascade impact: bad_events={bad_events:,}  bad_docs={bad_docs:,}")
conn.close()
"""Read-only diagnostic: verify cleanup state of all 9 tables."""
from pathlib import Path

import duckdb

G = Path(r"G:\Projects\医疗数据集评测-MIMIC\outputs\episodes")


def lit(p: Path) -> str:
    return "'" + str(p.resolve()).replace("'", "''") + "'"


def rp(p: Path) -> str:
    return f"read_parquet({lit(p)})"


conn = duckdb.connect(config={"memory_limit": "8GB", "threads": "4"})
conn.execute("SET preserve_insertion_order = false")

# Row counts for all tables
tables = [
    "episode_index", "care_contacts", "episode_coverage", "patient_history_refs",
    "timeline_events", "documents", "event_items", "evidence_links",
    "unresolved_events",
]
print("=== Row counts ===")
for t in tables:
    cnt = conn.execute(f"SELECT COUNT(*) FROM {rp(G / f'{t}.parquet')}").fetchone()[0]
    print(f"  {t:25s} {cnt:>14,}")

# Check for remaining negative episodes (should be 0 if episode_index was cleaned)
ep = G / "episode_index.parquet"
neg = conn.execute(
    f"SELECT COUNT(*) FROM {rp(ep)} WHERE clinical_end_time < episode_start_time"
).fetchone()[0]
print(f"\nnegative_duration_episodes={neg}")

# Check orphan event_items (items whose parent event was removed)
ei = G / "event_items.parquet"
te = G / "timeline_events.parquet"
orphans = conn.execute(
    f"SELECT COUNT(*) FROM {rp(ei)} ei "
    f"WHERE NOT EXISTS ("
    f"  SELECT 1 FROM {rp(te)} te WHERE te.event_id = ei.event_id)"
).fetchone()[0]
print(f"orphan_event_items={orphans:,}  (0 = event_items already cleaned)")

conn.close()
