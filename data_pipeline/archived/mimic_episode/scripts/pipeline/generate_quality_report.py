"""Generate quality_report.json from existing Parquet outputs, one file at a time."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5]))

import duckdb
from data_pipeline.archived.mimic_episode import __version__

OUTPUT_DIR = Path(r"G:\Projects\医疗数据集评测-MIMIC\outputs\episodes")

PARQUET_VIEWS = [
    "episode_index.parquet",
    "care_contacts.parquet",
    "timeline_events.parquet",
    "event_items.parquet",
    "documents.parquet",
    "evidence_links.parquet",
    "patient_history_refs.parquet",
    "episode_coverage.parquet",
    "unresolved_events.parquet",
]

report = {
    "pipeline": {
        "name": "mimic-clinical-episode-aggregation",
        "version": __version__,
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "duckdb": duckdb.__version__,
        "sources": {"mimic_iv": "3.1", "mimic_iv_ed": "2.2", "mimic_iv_note": "2.2"},
    },
    "outputs": {},
    "links": {},
    "quality": {},
    "quality_validation_basis": {},
}

def sql_path(p):
    """Return a SQL-safe single-quoted literal for a path."""
    return "'" + str(p.resolve()).replace("'", "''") + "'"

# Count rows one file at a time
for file_name in PARQUET_VIEWS:
    key = file_name.removesuffix(".parquet")
    path = OUTPUT_DIR / file_name
    if not path.is_file():
        report["outputs"][key] = {"rows": 0, "missing": True}
        print(f"  {key}: MISSING")
        continue
    conn = duckdb.connect(config={"memory_limit": "2GB", "threads": "1"})
    try:
        lit = sql_path(path)
        rows = conn.execute(f"SELECT COUNT(*) FROM read_parquet({lit})").fetchone()[0]
        report["outputs"][key] = {"rows": int(rows)}
        print(f"  {key}: {rows:,} rows")
    except Exception as e:
        report["outputs"][key] = {"rows": -1, "error": str(e)}
        print(f"  {key}: ERROR {e}")
    finally:
        conn.close()

# Link status counts
print("  Computing link_status counts...")
conn = duckdb.connect(config={"memory_limit": "4GB", "threads": "1"})
try:
    ev = sql_path(OUTPUT_DIR / "timeline_events.parquet")
    dc = sql_path(OUTPUT_DIR / "documents.parquet")
    link_rows = conn.execute(
        f"SELECT link_status, COUNT(*) FROM ("
        f"SELECT link_status FROM read_parquet({ev}) "
        f"UNION ALL SELECT link_status FROM read_parquet({dc})) "
        f"GROUP BY link_status"
    ).fetchall()
    report["links"] = {str(s): int(c) for s, c in link_rows}
    print(f"  links: {report['links']}")

    ep = sql_path(OUTPUT_DIR / "episode_index.parquet")
    ct = sql_path(OUTPUT_DIR / "care_contacts.parquet")
    dup_eps = conn.execute(f"SELECT COUNT(*) FROM (SELECT episode_id FROM read_parquet({ep}) GROUP BY episode_id HAVING COUNT(*) > 1)").fetchone()[0]
    dup_ct = conn.execute(f"SELECT COUNT(*) FROM (SELECT contact_id FROM read_parquet({ct}) GROUP BY contact_id HAVING COUNT(*) > 1)").fetchone()[0]
    subj = conn.execute(f"SELECT COUNT(*) FROM read_parquet({ct}) c JOIN read_parquet({ep}) e USING (episode_id) WHERE c.subject_id <> e.subject_id").fetchone()[0]
    report["quality"]["duplicate_episode_ids"] = int(dup_eps)
    report["quality"]["duplicate_contact_ids"] = int(dup_ct)
    report["quality"]["accepted_subject_conflicts"] = int(subj)
finally:
    conn.close()

for metric, basis in {
    "duplicate_event_ids": "0 by construction: source-prefixed IDs",
    "duplicate_item_event_ids": "0 by construction: source key + row number",
    "orphan_event_items": "0 by construction: every item shares parent event",
    "orphan_evidence_targets": "0 by construction: evidence emitted directly",
}.items():
    report["quality"][metric] = 0
    report["quality_validation_basis"][metric] = basis

report_path = OUTPUT_DIR / "quality_report.json"
report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(f"\n=== quality_report.json written ===")
