"""P4 — compare the ICD and NER past_condition tracks on a common admission set.

Reports per-track coverage and the overlap/agreement on admissions present in
both. The NER track is currently pilot-scale (one text_ner_v2 sidecar), so the
comparison is a coverage/agreement probe, not a final head-to-head.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_pipeline.archived.phenotype.past_condition import (  # noqa: E402
    extract_past_condition_icd,
    extract_past_condition_ner,
)
from data_pipeline.archived.phenotype.run_phenotype import load_events  # noqa: E402

MENTIONS = Path(
    r"D:\Projects\llm_benchmark\data\ner_v2_v2\sidecars\entity_mentions.parquet"
)


def compare(events: pd.DataFrame, mentions_path: Path) -> dict:
    icd = extract_past_condition_icd(events)
    ner = extract_past_condition_ner(mentions_path)

    icd_by = {r.hadm_id: set(r.features) for r in icd.itertuples(index=False)}
    ner_by = {r.hadm_id: set(r.features) for r in ner.itertuples(index=False)}

    icd_n = len(icd_by)
    ner_n = len(ner_by)
    common = set(icd_by) & set(ner_by)

    overlap = {
        h: {"icd_only": sorted(icd_by[h] - ner_by.get(h, set())),
            "ner_only": sorted(ner_by.get(h, set()) - icd_by[h]),
            "shared": sorted(icd_by[h] & ner_by.get(h, set()))}
        for h in sorted(common)
    }
    shared_concepts = sum(1 for v in overlap.values() if v["shared"])
    return {
        "icd_admissions_with_past_condition": icd_n,
        "ner_admissions_with_past_condition": ner_n,
        "common_admissions": len(common),
        "admissions_with_shared_concept": shared_concepts,
        "icd_concepts": sorted({c for s in icd_by.values() for c in s}),
        "ner_concepts": sorted({c for s in ner_by.values() for c in s}),
        "overlap_examples": [
            {"hadm_id": h, **v}
            for h, v in list(overlap.items())[:20]
        ],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--events", type=Path,
                    default=Path(r"G:\Projects\llm_benchmark\data\derived\coronary_all_three_modules_full\event_pipeline\normalization\normalized_events.parquet"))
    ap.add_argument("--split", type=Path,
                    default=Path(r"D:\Projects\llm_benchmark\tasks\investigation_selection\output\split\subject_split.parquet"))
    ap.add_argument("--mentions", type=Path, default=MENTIONS)
    ap.add_argument("--role", default="development")
    ap.add_argument("--max-admissions", type=int, default=1500)
    args = ap.parse_args(argv)

    events, _ = load_events(args.events, args.split, args.role)
    if args.max_admissions is not None:
        hadms = sorted(events["hadm_id"].unique())[: args.max_admissions]
        events = events[events["hadm_id"].isin(set(hadms))]

    result = compare(events, args.mentions)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
