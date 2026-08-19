"""Print order_type x subtype counts from the 1,000-admission aggregation."""

from __future__ import annotations

import json
from pathlib import Path

from data_pipeline.investigation_selection.audit import audit_poe_subtypes_from_parquet

ROOT = Path(__file__).resolve().parents[1]
PARQUET = ROOT / "data/test_1000_0812/event_pipeline_output/aggregation/processed_events.parquet"
OUT = ROOT / "data/derived/investigation_timepoint/poe-subtype-audit-1000.json"


def main() -> int:
    rows = audit_poe_subtypes_from_parquet(PARQUET)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT} n_keys={len(rows)} n_events={sum(r['count'] for r in rows)}")
    from collections import defaultdict

    grouped: dict[str, list] = defaultdict(list)
    for row in rows:
        grouped[str(row["order_type"])].append(row)
    for order_type, items in sorted(grouped.items(), key=lambda kv: -sum(i["count"] for i in kv[1])):
        print(f"=== {order_type} n={sum(i['count'] for i in items)}")
        for item in sorted(items, key=lambda row: -row["count"])[:30]:
            print(
                f"  {str(item['order_subtype'])!r:42} {item['event_kind']:22} "
                f"{item['count']:6} hadm={item['hadm_count']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
