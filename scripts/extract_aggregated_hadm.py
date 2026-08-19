"""Extract one complete traceable admission from event_aggregation outputs."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime
import argparse
import json
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq


def jsonable(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [jsonable(v) for v in value]
    return value


def extract(aggregation_dir: Path, hadm_id: str | None, output: Path) -> dict[str, Any]:
    processed_path = aggregation_dir / "processed_events.parquet"
    traceable_path = aggregation_dir / "traceable_events.parquet"
    source_path = aggregation_dir / "raw_source_records.parquet"
    for path in (processed_path, traceable_path, source_path):
        if not path.is_file():
            raise FileNotFoundError(path)

    processed = pq.read_table(processed_path, columns=["subject_id", "hadm_id", "event_kind"])
    counts: Counter[tuple[str, str]] = Counter(
        zip(processed.column("subject_id").to_pylist(), processed.column("hadm_id").to_pylist())
    )
    if hadm_id is None:
        (subject_id, selected_hadm), event_count = counts.most_common(1)[0]
    else:
        matches = [(pair, count) for pair, count in counts.items() if str(pair[1]) == str(hadm_id)]
        if not matches:
            raise ValueError(f"hadm_id not found: {hadm_id}")
        (subject_id, selected_hadm), event_count = matches[0]

    events = pq.read_table(
        traceable_path,
        filters=[("hadm_id", "=", selected_hadm)],
    ).to_pylist()
    source_records = pq.read_table(
        source_path,
        filters=[("hadm_id", "=", selected_hadm)],
    ).to_pylist()
    event_source_ids = {event.get("source_record_id") for event in events}
    supporting_source_ids = {
        source_id
        for event in events
        for source_id in (event.get("supporting_source_record_ids") or [])
    }
    source_ids = {
        record.get("source_record_id")
        for record in source_records
        if record.get("source_record_id") in event_source_ids | supporting_source_ids
    }
    groups = Counter(event.get("event_kind") for event in events)
    source_tables = Counter(
        f"{record.get('source_module')}.{record.get('source_table_name')}"
        for record in source_records
    )
    bundle = {
        "schema_version": "aggregated-hadm-extract/1.0.0",
        "source_aggregation_dir": str(aggregation_dir),
        "subject_id": str(subject_id),
        "hadm_id": str(selected_hadm),
        "event_count_expected_from_index": event_count,
        "event_count": len(events),
        "source_record_count": len(source_records),
        "event_source_record_count": len(event_source_ids),
        "supporting_source_record_count": len(supporting_source_ids),
        "source_records_referenced_count": len(source_ids),
        "event_kind_counts": dict(sorted(groups.items())),
        "source_table_counts": dict(sorted(source_tables.items())),
        "event_fields": list(events[0]) if events else [],
        "source_record_fields": list(source_records[0]) if source_records else [],
        "events": [jsonable(event) for event in events],
        "source_records": [jsonable(record) for record in source_records],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return bundle


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--aggregation-dir", type=Path, required=True)
    parser.add_argument("--hadm-id")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = extract(args.aggregation_dir, args.hadm_id, args.output)
    print(json.dumps({
        "output": str(args.output),
        "subject_id": result["subject_id"],
        "hadm_id": result["hadm_id"],
        "event_count": result["event_count"],
        "source_record_count": result["source_record_count"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
