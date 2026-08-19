"""Command-line entry point for the clean text NER v2 pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Clean, resumable two-stage clinical NER + relation extraction."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="Build chunked documents from the aggregation package")
    prepare.add_argument("aggregation_directory", type=Path)
    prepare.add_argument("--output-dir", type=Path, required=True)
    prepare.add_argument("--max-chunk-chars", type=int, default=3000)
    prepare.add_argument("--overlap-chars", type=int, default=200)

    run_mentions = subparsers.add_parser("run-mentions", help="Extract entity mentions via the API")
    run_mentions.add_argument("output_dir", type=Path)
    run_mentions.add_argument("--env-file", type=Path, default=None)
    run_mentions.add_argument("--mention-prompt", type=Path, required=True)
    run_mentions.add_argument("--max-docs", type=int, default=None)
    run_mentions.add_argument("--sample-per-source", type=int, default=None)
    run_mentions.add_argument(
        "--source-tables", type=str, default=None,
        help="Comma-separated source_table filter (e.g. note.discharge,ed.triage).",
    )
    run_mentions.add_argument("--max-tokens", type=int, default=6000)
    run_mentions.add_argument("--requests-per-minute", type=int, default=30)
    run_mentions.add_argument("--maximum-retries", type=int, default=3)
    run_mentions.add_argument("--retry-failed", action="store_true")
    run_mentions.add_argument(
        "--workers", type=int, default=1,
        help="Concurrent doc workers (default 1 = sequential).",
    )

    run_relations = subparsers.add_parser("run-relations", help="Extract explicit text relations via the API")
    run_relations.add_argument("output_dir", type=Path)
    run_relations.add_argument("--env-file", type=Path, default=None)
    run_relations.add_argument("--relation-prompt", type=Path, required=True)
    run_relations.add_argument("--max-docs", type=int, default=None)
    run_relations.add_argument("--max-tokens", type=int, default=8000)
    run_relations.add_argument("--requests-per-minute", type=int, default=30)
    run_relations.add_argument("--maximum-retries", type=int, default=3)
    run_relations.add_argument("--retry-failed", action="store_true")

    subparsers.add_parser("compile", help="Compile entity/relation sidecars").add_argument(
        "output_dir", type=Path
    )
    subparsers.add_parser("status", help="Report pipeline progress").add_argument(
        "output_dir", type=Path
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    from . import pipeline

    def reporter(message: str) -> None:
        print(message, flush=True)

    if args.command == "prepare":
        result = pipeline.build_documents(
            args.aggregation_directory,
            args.output_dir,
            max_chunk_chars=args.max_chunk_chars,
            overlap_chars=args.overlap_chars,
        )
    elif args.command == "run-mentions":
        result = pipeline.run_mentions(
            args.output_dir,
            env_file=args.env_file,
            mention_prompt=args.mention_prompt,
            max_docs=args.max_docs,
            sample_per_source=args.sample_per_source,
            source_tables=(
                [s.strip() for s in args.source_tables.split(",") if s.strip()]
                if args.source_tables else None
            ),
            max_tokens=args.max_tokens,
            requests_per_minute=args.requests_per_minute,
            maximum_retries=args.maximum_retries,
            retry_failed=args.retry_failed,
            workers=args.workers,
            report=reporter,
        )
    elif args.command == "run-relations":
        result = pipeline.run_relations(
            args.output_dir,
            env_file=args.env_file,
            relation_prompt=args.relation_prompt,
            max_docs=args.max_docs,
            max_tokens=args.max_tokens,
            requests_per_minute=args.requests_per_minute,
            maximum_retries=args.maximum_retries,
            retry_failed=args.retry_failed,
            report=reporter,
        )
    elif args.command == "compile":
        result = pipeline.compile_sidecars(args.output_dir)
    elif args.command == "status":
        result = pipeline.status(args.output_dir)
    else:
        raise SystemExit("unknown command")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cli() -> None:
    try:
        main()
    except KeyboardInterrupt:
        print(
            "\nNER_V2_INTERRUPTED: 已停止；此前落盘的 checkpoint 保持有效，可原命令续跑。",
            file=sys.stderr,
            flush=True,
        )
        raise SystemExit(130) from None


if __name__ == "__main__":
    cli()
