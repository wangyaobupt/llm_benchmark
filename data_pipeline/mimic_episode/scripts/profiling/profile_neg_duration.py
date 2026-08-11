"""Diagnose negative-duration episodes (episode_index only, fast)."""
import duckdb
G = r"G:\Projects\医疗数据集评测-MIMIC\outputs\episodes"
conn = duckdb.connect(config={"memory_limit": "8GB", "threads": "4"})
conn.execute(f"CREATE VIEW episode_index AS SELECT * FROM read_parquet('{G}/episode_index.parquet')")

print("=== 1. 负时长 episode 按 type ===")
for r in conn.execute("""
    SELECT episode_type, COUNT(*),
        MIN(date_diff('hour', episode_start_time, clinical_end_time))
    FROM episode_index
    WHERE clinical_end_time IS NOT NULL AND episode_start_time IS NOT NULL
      AND clinical_end_time < episode_start_time
    GROUP BY 1 ORDER BY 2 DESC
""").fetchall():
    print(f"  {r[0]:25s} count={r[1]:,}  min_dur={r[2]}h")

print("\n=== 2. 全部 NULL 时间统计 ===")
r = conn.execute("""
    SELECT
      SUM(CASE WHEN clinical_end_time IS NULL THEN 1 ELSE 0 END),
      SUM(CASE WHEN episode_start_time IS NULL THEN 1 ELSE 0 END)
    FROM episode_index
""").fetchone()
print(f"  end_NULL={r[0]:,}  start_NULL={r[1]:,}")

print("\n=== 3. hospital 负时长 episode 的 end 字段来源 ===")
r = conn.execute("""
    SELECT COUNT(*) FROM episode_index
    WHERE episode_type='hospital'
      AND clinical_end_time IS NOT NULL AND episode_start_time IS NOT NULL
      AND clinical_end_time < episode_start_time
      AND administrative_end_time IS NOT NULL
""").fetchone()
print(f"  hospital负且disch非NULL: {r[0]:,}")

print("\n=== 4. ED standalone 负时长 ===")
r = conn.execute("""
    SELECT COUNT(*) FROM episode_index
    WHERE episode_type='emergency_department'
      AND clinical_end_time IS NOT NULL AND episode_start_time IS NOT NULL
      AND clinical_end_time < episode_start_time
""").fetchone()
print(f"  ED负: {r[0]:,}")

print("\n=== 5. 死亡 episode 里 deathtime 关系 ===")
r = conn.execute("""
    SELECT COUNT(*) FROM episode_index
    WHERE outcome_type='death'
      AND clinical_end_time < episode_start_time
""").fetchone()
print(f"  death且负时长: {r[0]:,}")

conn.close()
