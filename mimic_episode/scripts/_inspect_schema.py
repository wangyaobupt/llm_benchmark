"""Read-only schema inspection for extraction planning."""
from pathlib import Path
import duckdb

G = Path(r"G:\Projects\医疗数据集评测-MIMIC\outputs\episodes")


def lit(p: Path) -> str:
    return "'" + str(p.resolve()).replace("'", "''") + "'"


def rp(p: Path) -> str:
    return f"read_parquet({lit(p)})"


conn = duckdb.connect()
tables = [
    "episode_index", "care_contacts", "episode_coverage",
    "patient_history_refs", "timeline_events", "documents",
    "event_items", "evidence_links", "unresolved_events",
]

for t in tables:
    cols = conn.execute(f"DESCRIBE SELECT * FROM {rp(G / f'{t}.parquet')}").fetchall()
    col_names = [c[0] for c in cols]
    has_sid = "subject_id" in col_names
    has_eid = "episode_id" in col_names
    print(f"{t:25s} cols={len(col_names):2d}  subject_id={'Y' if has_sid else 'N'}  episode_id={'Y' if has_eid else 'N'}")
    if not has_sid:
        print(f"    columns: {', '.join(col_names)}")

# patient count estimate
n_patients = conn.execute(
    f"SELECT COUNT(DISTINCT subject_id) FROM {rp(G / 'episode_index.parquet')}"
).fetchone()[0]
print(f"\ndistinct patients in episode_index: {n_patients:,}")

# episodes per patient distribution (top-level stats)
stats = conn.execute(f"""
    SELECT
        MIN(ep_cnt), MAX(ep_cnt),
        AVG(ep_cnt)::DOUBLE,
        MEDIAN(ep_cnt)::DOUBLE
    FROM (
        SELECT subject_id, COUNT(*) AS ep_cnt
        FROM {rp(G / 'episode_index.parquet')}
        GROUP BY subject_id
    )
""").fetchone()
print(f"episodes/patient: min={stats[0]} max={stats[1]} avg={stats[2]:.1f} median={stats[3]}")

conn.close()
