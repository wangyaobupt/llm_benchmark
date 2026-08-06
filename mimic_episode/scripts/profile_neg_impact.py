"""Measure cascade impact of removing negative-duration episodes."""
import duckdb
G = r"G:\Projects\医疗数据集评测-MIMIC\outputs\episodes"
conn = duckdb.connect(config={"memory_limit":"12GB","threads":"4"})
conn.execute("SET preserve_insertion_order = false")

conn.execute(f"CREATE VIEW ep AS SELECT * FROM read_parquet('{G}/episode_index.parquet')")
conn.execute(f"CREATE VIEW cc AS SELECT * FROM read_parquet('{G}/care_contacts.parquet')")
conn.execute(f"CREATE VIEW te AS SELECT * FROM read_parquet('{G}/timeline_events.parquet')")
conn.execute(f"CREATE VIEW ei AS SELECT * FROM read_parquet('{G}/event_items.parquet')")
conn.execute(f"CREATE VIEW dc AS SELECT * FROM read_parquet('{G}/documents.parquet')")

# 负时长 episode_id 集合
conn.execute("""
    CREATE VIEW bad_eps AS
    SELECT episode_id FROM ep
    WHERE clinical_end_time IS NOT NULL AND episode_start_time IS NOT NULL
      AND clinical_end_time < episode_start_time
""")

print("=== 负时长 episode 数 ===")
print(conn.execute("SELECT COUNT(*) FROM bad_eps").fetchone()[0])

print("\n=== 级联影响（这些 episode 关联的行数）===")
print(f"  care_contacts:     {conn.execute('SELECT COUNT(*) FROM cc WHERE episode_id IN (SELECT episode_id FROM bad_eps)').fetchone()[0]:,}")
print(f"  timeline_events:   {conn.execute('SELECT COUNT(*) FROM te WHERE episode_id IN (SELECT episode_id FROM bad_eps)').fetchone()[0]:,}")
print(f"  documents:         {conn.execute('SELECT COUNT(*) FROM dc WHERE episode_id IN (SELECT episode_id FROM bad_eps)').fetchone()[0]:,}")

print("\n=== event_items 级联（通过 event_id 关联）===")
print(f"  {conn.execute('SELECT COUNT(*) FROM ei WHERE event_id IN (SELECT event_id FROM te WHERE episode_id IN (SELECT episode_id FROM bad_eps))').fetchone()[0]:,}")

print("\n=== 这些 episode 涉及的 subject_id 数 ===")
print(f"  {conn.execute('SELECT COUNT(DISTINCT subject_id) FROM ep WHERE episode_id IN (SELECT episode_id FROM bad_eps)').fetchone()[0]:,}")

print("\n=== 这些 subject_id 是否还有其他正常 episode ===")
print(f"  {conn.execute('SELECT COUNT(*) FROM ep WHERE subject_id IN (SELECT subject_id FROM bad_eps) AND episode_id NOT IN (SELECT episode_id FROM bad_eps)').fetchone()[0]:,}")

conn.close()
