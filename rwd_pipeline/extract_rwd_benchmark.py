from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rwd_pipeline.extraction.common import ExtractionError
from rwd_pipeline.extraction.pipeline import run_extraction


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract the MIMIC-IV RWD benchmark dataset.")
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path("/data/ehr/MIMIC/physionet.org/files/mimiciv/3.1"),
    )
    parser.add_argument("--limit", type=int, default=20_000)
    parser.add_argument("--output", type=Path, default=Path("rwd_benchmark_visits.csv"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        summary = run_extraction(args.data_root, args.output, args.limit)
    except (ExtractionError, FileNotFoundError, ValueError) as exc:
        print(f"Extraction failed: {exc}", file=sys.stderr)
        return 1

    print(
        f"Completed: candidates={summary.candidate_count}, "
        f"eligible={summary.eligible_count}, output={summary.output_path}, "
        f"elapsed={summary.elapsed_seconds:.1f}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
