"""Extract every normalized event for one hospitalization into an auditable JSON."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq


def sort_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (str(row.get("available_time") or ""), str(row.get("event_time") or ""), str(row.get("event_id") or ""))


def extract(source_root: Path, hadm_id: str) -> dict[str, Any]:
    parquet = source_root / "normalized_events.parquet"
    manifest_path = source_root / "normalization_manifest.json"
    if not parquet.is_file() or not manifest_path.is_file():
        raise FileNotFoundError(f"normalization source incomplete: {source_root}")
    table = pq.read_table(parquet, filters=[("hadm_id", "=", str(hadm_id))])
    events = [dict(row) for row in table.to_pylist()]
    events.sort(key=sort_key)
    subjects = sorted({str(event.get("subject_id")) for event in events if event.get("subject_id") not in (None, "")})
    encounters = sorted({str(event.get("encounter_id")) for event in events if event.get("encounter_id") not in (None, "")})
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    return {
        "extraction_schema": "normalized-hadm-event-bundle/1.0.0",
        "extracted_at_utc": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source_root": source_root.as_posix(),
        "source_file": "normalized_events.parquet",
        "source_output_sha256_from_manifest": manifest.get("output_sha256", {}).get("normalized_events.parquet"),
        "hadm_id": str(hadm_id),
        "subject_ids": subjects,
        "encounter_ids": encounters,
        "event_count": len(events),
        "event_fields": table.column_names,
        "events": events,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--hadm-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    bundle = extract(args.source_root, args.hadm_id)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(bundle, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "hadm_id": bundle["hadm_id"], "event_count": bundle["event_count"], "event_fields": len(bundle["event_fields"])}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
