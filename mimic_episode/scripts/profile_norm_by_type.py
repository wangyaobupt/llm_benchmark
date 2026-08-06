"""Profile normalization failure rate by event_type (event_items join timeline)."""
import duckdb, time
G = r"G:\Projects\医疗数据集评测-MIMIC\outputs\episodes"
conn = duckdb.connect(config={"memory_limit":"12GB","threads":"4"})
conn.execute("SET preserve_insertion_order = false")
conn.execute(f"CREATE VIEW ei AS SELECT * FROM read_parquet('{G}/event_items.parquet')")
conn.execute(f"CREATE VIEW te AS SELECT event_id, event_type FROM read_parquet('{G}/timeline_events.parquet')")

print("=== 归一化失败率 by event_type ===")
print(f"{'event_type':30s} {'total':>14s} {'norm_NULL':>14s} {'fail%':>7s}")
t0=time.time()
for r in conn.execute("""
    SELECT te.event_type,
        COUNT(*) AS total,
        SUM(CASE WHEN ei.normalized_value IS NULL
                  AND ei.raw_value IS NOT NULL AND ei.raw_value != '' THEN 1 ELSE 0 END) AS norm_null
    FROM ei JOIN te USING(event_id)
    WHERE ei.raw_value IS NOT NULL AND ei.raw_value != ''
    GROUP BY 1 ORDER BY 2 DESC
""").fetchall():
    pct = r[2]/r[1]*100 if r[1] else 0
    print(f"  {r[0]:30s} {r[1]:14,} {r[2]:14,} {pct:6.1f}%")
print(f"  ({time.time()-t0:.1f}s)")
conn.close()
