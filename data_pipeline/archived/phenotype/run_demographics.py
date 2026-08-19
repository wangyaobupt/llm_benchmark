"""CLI entry for the P1 demographics extraction (reproducible)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from data_pipeline.archived.phenotype.demographics import extract_demographics

RAW_ARCHIVE = Path(
    r"G:\Projects\llm_benchmark\data\validation\mimic-admission-raw-coronary-all-three-modules.jsonl"
)
OUT = Path(r"D:\Projects\llm_benchmark\data\phenotype\hadm_demographics.parquet")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--raw-archive", type=Path, default=RAW_ARCHIVE)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--max-lines", type=int, default=None)
    args = ap.parse_args(argv)

    manifest = extract_demographics(args.raw_archive, args.out, max_lines=args.max_lines)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
