"""Quick schema check for profiling planning (run escalated)."""
import duckdb
G = r"G:\Projects\医疗数据集评测-MIMIC\outputs\episodes"
c = duckdb.connect()
for t in ["episode_index","episode_coverage","timeline_events","event_items","documents","unresolved_events"]:
    try:
        sch = c.execute(f"DESCRIBE SELECT * FROM read_parquet('{G}/{t}.parquet')").fetchall()
        print(f"=== {t} ({len(sch)} cols) ===")
        for r in sch:
            print(f"  {r[0]:30s} {r[1]}")
    except Exception as e:
        print(f"=== {t}: ERROR {e}")
    print()
