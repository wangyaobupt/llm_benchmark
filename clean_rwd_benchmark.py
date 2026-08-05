from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rwd_cleaning import CleaningError, run_cleaning


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clean the MIMIC RWD benchmark dataset.")
    parser.add_argument("--input", type=Path, default=Path("rwd_benchmark_visits.csv"))
    parser.add_argument(
        "--output", type=Path, default=Path("out/rwd_benchmark_visits_cleaned.csv")
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=Path("out/rwd_benchmark_cleaning_checkpoint.jsonl"),
    )
    parser.add_argument("--workers", type=int, default=64)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        summary = run_cleaning(args.input, args.output, args.checkpoint, args.workers)
    except (CleaningError, FileNotFoundError, ValueError) as exc:
        print(f"Cleaning failed: {exc}", file=sys.stderr)
        return 1

    print(
        f"Completed: rows={summary.row_count}, api_requests={summary.api_requests}, "
        f"checkpoint_reused={summary.checkpoint_reused}, skipped_empty={summary.skipped_empty}, "
        f"entities={dict(summary.entity_counts)}, empty={dict(summary.empty_counts)}, "
        f"output={summary.output_path}, elapsed={summary.elapsed_seconds:.1f}s"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
