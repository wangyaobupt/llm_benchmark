from __future__ import annotations

import argparse
from pathlib import Path

from .pipeline import DEFAULT_DICTIONARY_DIRECTORY, prepare_archive


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Decode all supported MIMIC codes and add a parsed POE timeline "
            "to admission-level raw JSONL records."
        )
    )
    parser.add_argument("input", type=Path, help="Admission-level raw JSONL")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--dictionary-dir",
        type=Path,
        default=DEFAULT_DICTIONARY_DIRECTORY,
        help="Directory containing the five official dictionary JSON arrays",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process the first N admissions",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    metrics = prepare_archive(
        args.input,
        args.output,
        args.report,
        args.dictionary_dir,
        limit=args.limit,
    )
    print(
        f"processed {metrics['admissions']} admissions, decoded "
        f"{metrics['dictionary_decoded_total']} coded rows, and parsed "
        f"{metrics['poe_events']} POE events into {args.output}"
    )


if __name__ == "__main__":
    main()
