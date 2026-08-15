"""Command-line entry point for lossless event aggregation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pipeline import build_event_aggregation


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Combine accepted normalized events with complete clinical-readable "
            "and raw source rows."
        )
    )
    parser.add_argument(
        "input_directory",
        type=Path,
        help="Directory containing event_pipeline_output and source JSONL files",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help=(
            "Output directory; defaults to "
            "INPUT/event_pipeline_output/aggregation"
        ),
    )
    parser.add_argument("--batch-size", type=int, default=5000)
    return parser


def main() -> None:
    args = _parser().parse_args()
    output_directory = args.output_dir or (
        args.input_directory / "event_pipeline_output" / "aggregation"
    )
    result = build_event_aggregation(
        args.input_directory,
        output_directory,
        batch_size=args.batch_size,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
