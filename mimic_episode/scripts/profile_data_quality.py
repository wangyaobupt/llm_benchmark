"""Data quality profiling for the episode aggregation outputs.

Runs 8 profiling dimensions as DuckDB aggregate queries over already-landed
Parquet files. Outputs ONLY summary counts, distributions, and percentiles.
Never SELECTs patient-level rows.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import duckdb

OUTPUT_DIR = Path(r"G:\Projects\医疗数据集评测-MIMIC\outputs\episodes")
REPORT_PATH = Path(__file__).resolve().parents[2] / "docs" / "data-profiling-report.md"


def lit(p: Path) -> str:
    return "'" + p.resolve().as_posix().replace("'", "''") + "'"


def main() -> int:
    g = OUTPUT_DIR
    lines: list[str] = []
    w = lines.append

    w("# 数据画像报告（Episode 聚合层）")
    w("")
    w("> 自动生成，仅含汇总计数、分布与分位数，不含患者级数据。")
    w("")

    conn = duckdb.connect(config={"memory_limit": "12GB", "threads": "4"})
    conn.execute("SET preserve_insertion_order = false")

    # Register views
    for t in [
        "episode_index", "episode_coverage", "timeline_events",
        "event_items", "documents", "unresolved_events",
    ]:
        conn.execute(
            f"CREATE VIEW {t} AS SELECT * FROM read_parquet(" + lit(g / f"{t}.parquet") + ")"
        )
        print(f"  registered view: {t}")

    def timed(label: str, fn):
        t0 = time.time()
        result = fn(conn)
        dt = time.time() - t0
        print(f"  [done] {label} ({dt:.1f}s)")
        return result

    # ---- D1: Episode coverage ----
    w("## 维度 1：Episode 资料覆盖度")
    w("")
    w("### 各数据类型覆盖率（占 768,125 个 episode 的百分比）")
    w("")
    w("| 数据类型 | 有此数据的 episode 数 | 覆盖率 |")
    w("|---|---:|---:|")
    cov_cols = [
        "has_chief_complaint","has_triage_vitals","has_serial_vitals",
        "has_laboratory","has_microbiology","has_radiology",
        "has_orders","has_prescriptions","has_medication_administration",
        "has_procedures","has_diagnoses","has_disposition","has_discharge_summary",
    ]
    cov_labels = {
        "has_chief_complaint":"主诉","has_triage_vitals":"分诊生命体征",
        "has_serial_vitals":"连续生命体征","has_laboratory":"化验",
        "has_microbiology":"微生物","has_radiology":"放射报告",
        "has_orders":"医嘱","has_prescriptions":"处方",
        "has_medication_administration":"用药执行","has_procedures":"操作",
        "has_diagnoses":"诊断","has_disposition":"处置",
        "has_discharge_summary":"出院小结",
    }
    total_eps = conn.execute("SELECT COUNT(*) FROM episode_coverage").fetchone()[0]
    for col in cov_cols:
        cnt = conn.execute(
            f"SELECT COUNT(*) FROM episode_coverage WHERE {col} = true"
        ).fetchone()[0]
        pct = cnt / total_eps * 100
        w(f"| {cov_labels[col]} ({col}) | {cnt:,} | {pct:.1f}% |")

    w("")
    w("### 每 episode 拥有的数据类型数量分布")
    w("")
    has_sum = " + ".join(f"CAST({c} AS INT)" for c in cov_cols)
    dist = conn.execute(
        f"SELECT ({has_sum}) AS n_types, COUNT(*) FROM episode_coverage GROUP BY 1 ORDER BY 1"
    ).fetchall()
    w("| 类型数 | episode 数 | 占比 |")
    w("|---:|---:|---:|")
    for n, cnt in dist:
        w(f"| {n} | {cnt:,} | {cnt/total_eps*100:.1f}% |")

    # ---- D2: Episode duration & scale ----
    w("")
    w("## 维度 2：Episode 规模与时长")
    w("")
    dur = conn.execute("""
        SELECT
            MIN(date_diff('hour', episode_start_time, clinical_end_time)),
            percentile_cont(0.25) WITHIN GROUP (
                ORDER BY date_diff('hour', episode_start_time, clinical_end_time)),
            percentile_cont(0.50) WITHIN GROUP (
                ORDER BY date_diff('hour', episode_start_time, clinical_end_time)),
            percentile_cont(0.75) WITHIN GROUP (
                ORDER BY date_diff('hour', episode_start_time, clinical_end_time)),
            MAX(date_diff('hour', episode_start_time, clinical_end_time))
        FROM episode_index
        WHERE clinical_end_time IS NOT NULL
    """).fetchone()
    w(f"临床时长（小时）：min={dur[0]}, P25={dur[1]}, P50={dur[2]}, P75={dur[3]}, max={dur[4]}")
    very_short = conn.execute("""
        SELECT COUNT(*) FROM episode_index
        WHERE date_diff('hour', episode_start_time, clinical_end_time) < 1
    """).fetchone()[0]
    very_long = conn.execute("""
        SELECT COUNT(*) FROM episode_index
        WHERE date_diff('hour', episode_start_time, clinical_end_time) > 24*365
    """).fetchone()[0]
    w(f"- 异短 episode（<1 小时）：{very_short:,}")
    w(f"- 异长 episode（>365 天）：{very_long:,}")
    w("")

    # ---- D3: Time logic consistency ----
    w("## 维度 3：时间逻辑一致性")
    w("")
    t_before = conn.execute("""
        SELECT COUNT(*) FROM timeline_events
        WHERE episode_id IS NOT NULL
          AND available_time IS NOT NULL
          AND available_time < (SELECT episode_start_time FROM episode_index e
                                WHERE e.episode_id = timeline_events.episode_id)
    """).fetchone()[0]
    w(f"available_time 早于 episode_start 的事件（时间倒挂）：{t_before:,}")
    ev_after = conn.execute("""
        SELECT COUNT(*) FROM timeline_events t
        JOIN episode_index e ON e.episode_id = t.episode_id
        WHERE t.event_time IS NOT NULL
          AND t.event_time > e.clinical_end_time
    """).fetchone()[0]
    w(f"event_time 晚于 clinical_end_time 的事件：{ev_after:,}")
    w("")

    # ---- D4: Text completeness ----
    w("## 维度 4：文本完整性")
    w("")
    total_docs = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    empty_docs = conn.execute(
        "SELECT COUNT(*) FROM documents WHERE text IS NULL OR length(text) = 0"
    ).fetchone()[0]
    w(f"- 总文档数：{total_docs:,}")
    w(f"- 空文本文档：{empty_docs:,}（{empty_docs/total_docs*100:.2f}%）")
    w("")
    w("### 文本长度分布（按文档类型）")
    w("")
    w("| 类型 | 数量 | P10 | P50 | P90 | 均值 |")
    w("|---|---:|---:|---:|---:|---:|")
    for doc_type in ["discharge", "radiology"]:
        row = conn.execute(f"""
            SELECT COUNT(*),
                percentile_cont(0.10) WITHIN GROUP (ORDER BY length(text)),
                percentile_cont(0.50) WITHIN GROUP (ORDER BY length(text)),
                percentile_cont(0.90) WITHIN GROUP (ORDER BY length(text)),
                AVG(length(text))
            FROM documents WHERE document_type = '{doc_type}' AND text IS NOT NULL
        """).fetchone()
        w(f"| {doc_type} | {row[0]:,} | {row[1]:,.0f} | {row[2]:,.0f} | {row[3]:,.0f} | {row[4]:,.0f} |")
    # duplicate discharge summaries
    w("")
    dup_discharge = conn.execute("""
        SELECT COUNT(*) FROM (
            SELECT episode_id FROM documents
            WHERE document_type = 'discharge' AND episode_id IS NOT NULL
            GROUP BY episode_id HAVING COUNT(*) > 1
        )
    """).fetchone()[0]
    w(f"- 同一 episode 有多份出院小结的 episode 数：{dup_discharge:,}")
    w("")

    # ---- D5: Numeric & unit ----
    w("## 维度 5：数值与单位")
    w("")
    norm_fail = conn.execute("""
        SELECT COUNT(*) FROM event_items
        WHERE normalized_value IS NULL AND raw_value IS NOT NULL AND raw_value != ''
    """).fetchone()[0]
    has_raw = conn.execute("""
        SELECT COUNT(*) FROM event_items
        WHERE raw_value IS NOT NULL AND raw_value != ''
    """).fetchone()[0]
    w(f"- 有 raw_value 但 normalized_value 为 NULL（归一化失败）：{norm_fail:,}（{norm_fail/has_raw*100:.1f}% of {has_raw:,}）")
    w("")
    w("### raw_unit top 15")
    w("")
    w("| raw_unit | 数量 |")
    w("|---|---:|")
    units = conn.execute("""
        SELECT raw_unit, COUNT(*) FROM event_items
        WHERE raw_value IS NOT NULL AND raw_value != ''
        GROUP BY 1 ORDER BY 2 DESC LIMIT 15
    """).fetchall()
    for u, cnt in units:
        label = u if u else "(NULL)"
        w(f"| {label} | {cnt:,} |")
    w("")

    # ---- D6: Link quality ----
    w("## 维度 6：链接质量")
    w("")
    w("### unresolved_reason 分布（timeline_events）")
    w("")
    w("| reason | 数量 |")
    w("|---|---:|")
    reasons = conn.execute("""
        SELECT COALESCE(unresolved_reason,'(null)'), COUNT(*)
        FROM timeline_events WHERE link_status = 'unresolved'
        GROUP BY 1 ORDER BY 2 DESC
    """).fetchall()
    for r, cnt in reasons:
        w(f"| {r} | {cnt:,} |")
    w("")

    # ---- D7: Event type distribution ----
    w("## 维度 7：事件类型分布")
    w("")
    w("| event_type | 数量 | unresolved 数 | unresolved 率 |")
    w("|---|---:|---:|---:|")
    etypes = conn.execute("""
        SELECT event_type, COUNT(*),
            COUNT(*) FILTER (WHERE link_status='unresolved')
        FROM timeline_events GROUP BY event_type ORDER BY 2 DESC
    """).fetchall()
    for et, total, unr in etypes:
        w(f"| {et} | {total:,} | {unr:,} | {unr/total*100:.1f}% |")
    w("")

    # ---- D8: Patient cardinality ----
    w("## 维度 8：患者维度基数核对")
    w("")
    subj_count = conn.execute(
        "SELECT COUNT(DISTINCT subject_id) FROM episode_index"
    ).fetchone()[0]
    w(f"- episode_index distinct subject_id：{subj_count:,}")
    eps_per_subj = conn.execute("""
        SELECT
            MIN(n), percentile_cont(0.5) WITHIN GROUP (ORDER BY n),
            percentile_cont(0.9) WITHIN GROUP (ORDER BY n), MAX(n)
        FROM (SELECT subject_id, COUNT(*) AS n FROM episode_index GROUP BY 1)
    """).fetchone()
    w(f"- 每患者 episode 数：min={eps_per_subj[0]}, P50={eps_per_subj[1]}, P90={eps_per_subj[2]}, max={eps_per_subj[3]}")
    w("")
    w("---")
    w("")
    w("**画像完成。** 根据以上分布判断是否需要数据清洗及清洗重点。")

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n=== Report written to {REPORT_PATH} ===")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
