from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from rwd_pipeline.standardization import (
    StandardizationError,
    build_mappings,
    run_standardization,
    transform_with_mappings,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Standardize cleaned MIMIC RWD benchmark medical names."
    )
    parser.add_argument(
        "--mode", choices=("run", "build-mappings", "transform"), default="run"
    )
    parser.add_argument(
        "--input", type=Path, default=Path("out/rwd_benchmark_visits_cleaned.csv")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("out/rwd_benchmark_visits_standardized.csv")
    )
    parser.add_argument(
        "--mappings",
        type=Path,
        default=Path("out/rwd_benchmark_standardization_mappings_v1.jsonl"),
    )
    parser.add_argument(
        "--review",
        type=Path,
        default=Path("out/rwd_benchmark_standardization_review_v1.jsonl"),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("out/rwd_benchmark_standardization_manifest_v1.json"),
    )
    parser.add_argument("--workers", type=int, default=16)
    parser.add_argument("--batch-size", type=int, default=20)
    mapping_mode = parser.add_mutually_exclusive_group()
    mapping_mode.add_argument(
        "--use-llm",
        action="store_true",
        help="Use DeepSeek for candidate mapping and agreement checks.",
    )
    mapping_mode.add_argument(
        "--offline",
        action="store_true",
        help="Build self-mappings for pipeline testing; these artifacts are not release v1.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    started = time.monotonic()
    try:
        if args.mode in {"run", "build-mappings"} and not (
            args.use_llm or args.offline
        ):
            raise StandardizationError(
                "Choose --use-llm for release mappings or --offline for a non-release dry run"
            )
        if args.mode == "run":
            summary = run_standardization(
                args.input,
                args.output,
                args.mappings,
                args.review,
                args.manifest,
                workers=args.workers,
                batch_size=args.batch_size,
                use_llm=args.use_llm,
            )
            print(
                f"Completed: rows={summary.row_count}, candidates={summary.candidate_count}, "
                f"mappings={dict(summary.mapping_counts)}, output={summary.output_path}, "
                f"elapsed={summary.elapsed_seconds:.1f}s"
            )
        elif args.mode == "build-mappings":
            if args.use_llm:
                from rwd_standardization.mapping import DeepSeekMappingClient

                import os

                api_key = os.environ.get("DEEPSEEK_API_KEY", "")
                if not api_key:
                    raise StandardizationError("DEEPSEEK_API_KEY is required with --use-llm")
                client = DeepSeekMappingClient(api_key)
            else:
                client = None
            rows, candidates, counts = build_mappings(
                args.input,
                args.mappings,
                args.review,
                args.manifest,
                client=client,
                workers=args.workers,
                batch_size=args.batch_size,
            )
            print(
                f"Mappings completed: rows={rows}, candidates={candidates}, "
                f"mappings={dict(counts)}, elapsed={time.monotonic() - started:.1f}s"
            )
        else:
            rows = transform_with_mappings(
                args.input, args.mappings, args.output, args.manifest
            )
            print(
                f"Transform completed: rows={rows}, output={args.output.resolve()}, "
                f"elapsed={time.monotonic() - started:.1f}s"
            )
    except (StandardizationError, FileNotFoundError, ValueError) as exc:
        print(f"Standardization failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
