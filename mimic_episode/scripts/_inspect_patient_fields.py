"""Read-only: inspect what fields are available for a patient-level wide table."""
from pathlib import Path
import duckdb

G = Path(r"G:\Projects\医疗数据集评测-MIMIC\outputs\episodes")


def lit(p: Path) -> str:
    return "'" + str(p.resolve()).replace("'", "''") + "'"


def rp(p: Path) -> str:
    return f"read_parquet({lit(p)})"


conn = duckdb.connect()

print("=== episode_index schema ===")
for r in conn.execute(f"DESCRIBE SELECT * FROM {rp(G / 'episode_index.parquet')}").fetchall():
    print(f"  {r[0]:30s} {r[1]}")

print("\n=== timeline_events schema ===")
for r in conn.execute(f"DESCRIBE SELECT * FROM {rp(G / 'timeline_events.parquet')}").fetchall():
    print(f"  {r[0]:30s} {r[1]}")

print("\n=== documents schema ===")
for r in conn.execute(f"DESCRIBE SELECT * FROM {rp(G / 'documents.parquet')}").fetchall():
    print(f"  {r[0]:30s} {r[1]}")

print("\n=== care_contacts schema ===")
for r in conn.execute(f"DESCRIBE SELECT * FROM {rp(G / 'care_contacts.parquet')}").fetchall():
    print(f"  {r[0]:30s} {r[1]}")

# Sample: one patient's episode count + event types
print("\n=== sample patient (first subject_id) ===")
sid = conn.execute(f"SELECT subject_id FROM {rp(G / 'episode_index.parquet')} LIMIT 1").fetchone()[0]
eps = conn.execute(f"SELECT * FROM {rp(G / 'episode_index.parquet')} WHERE subject_id = {sid}").fetchall()
print(f"subject_id={sid}, episodes={len(eps)}")
ev_types = conn.execute(f"""
    SELECT event_type, COUNT(*) FROM {rp(G / 'timeline_events.parquet')}
    WHERE subject_id = {sid} GROUP BY 1 ORDER BY 2 DESC
""").fetchall()
print(f"event_types: {ev_types[:10]}")

# document types
doc_types = conn.execute(f"""
    SELECT note_type, COUNT(*) FROM {rp(G / 'documents.parquet')}
    WHERE subject_id = {sid} GROUP BY 1 ORDER BY 2 DESC
""").fetchall()
print(f"doc_types: {doc_types}")

conn.close()
