"""Resume Stage 2 (a+b) from existing Stage 1 raw Parquet files.

Skips Stage 1 (CSV -> Parquet conversion, ~21 min).
Re-runs Stage 2a (views + materialization) and Stage 2b (link + export).
"""
import gc
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

import duckdb
from data_pipeline.mimic_episode.episode_pipeline import (
    PARQUET_VIEWS,
    _assert_hard_quality,
    _collect_report,
    _create_phase_two_views,
    _create_raw_views,
    _export_parquet_views,
    _load_episode_sql,
    _materialize_event_sources,
    _materialize_phase_one_views,
    _new_connection,
    _sql_literal,
)

OUTPUT_DIR = Path(r"G:\Projects\医疗数据集评测-MIMIC\outputs\episodes")
TEMP_DIR = OUTPUT_DIR / "duckdb-episode-w8z8xpdl"

if not (TEMP_DIR / "raw").is_dir():
    raise SystemExit(f"Stage 1 raw/ not found at {TEMP_DIR}")

# Clean up partial outputs and stale materialized files
for subdir in ("core", "events", "items"):
    d = TEMP_DIR / subdir
    if d.is_dir():
        for f in d.glob("*.parquet"):
            f.unlink()
for file_name in PARQUET_VIEWS:
    p = OUTPUT_DIR / file_name
    if p.is_file():
        p.unlink()

logger.info("=== Stage 2a: views + materialization ===")
source_conn = _new_connection("8GB", 4, TEMP_DIR)
try:
    _create_raw_views(source_conn, TEMP_DIR)
    logger.info("Raw views created. Running build SQL...")
    source_conn.execute(_load_episode_sql("build_episodes.sql"))
    logger.info("Episodes built. Building documents...")
    source_conn.execute(_load_episode_sql("build_documents.sql"))
    logger.info("Documents built. Building event sources...")
    source_conn.execute(_load_episode_sql("build_event_sources.sql"))
    logger.info("Event sources built. Building auxiliary sources...")
    source_conn.execute(_load_episode_sql("build_auxiliary_sources.sql"))
    logger.info("Materializing phase one views...")
    _materialize_phase_one_views(source_conn, TEMP_DIR)
    logger.info("Materializing event sources...")
    _materialize_event_sources(source_conn, TEMP_DIR)
finally:
    source_conn.close()
    gc.collect()

logger.info("=== Stage 2b: link + export ===")
agg_conn = _new_connection("8GB", 4, TEMP_DIR)
try:
    _create_phase_two_views(agg_conn, TEMP_DIR)
    logger.info("Phase two views created. Running link_events.sql...")
    agg_conn.execute(_load_episode_sql("link_events.sql"))
    logger.info("Events linked. Running build_auxiliary.sql...")
    agg_conn.execute(_load_episode_sql("build_auxiliary.sql"))
    logger.info("Exporting final Parquet views...")
    _export_parquet_views(agg_conn, OUTPUT_DIR)
    logger.info("Collecting quality report...")
    report = _collect_report(agg_conn, OUTPUT_DIR)
    _assert_hard_quality(report)
    logger.info("Quality checks passed.")
finally:
    agg_conn.close()
    gc.collect()

report_path = OUTPUT_DIR / "quality_report.json"
report_path.write_text(
    json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
logger.info("=== PIPELINE COMPLETE ===")
print(json.dumps(report, ensure_ascii=False, indent=2))
