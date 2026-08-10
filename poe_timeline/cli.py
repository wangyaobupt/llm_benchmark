from __future__ import annotations

import argparse
from pathlib import Path

from .parser import run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Add auditable provider-order timelines to complete admission-level "
            "MIMIC-IV raw JSONL records."
        )
    )
    parser.add_argument("input", type=Path, help="Admission-level raw JSONL")
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Admission-level JSONL with mimic_iv_hosp.poe_timeline added",
    )
    parser.add_argument("--report", type=Path, required=True, help="Quality metrics JSON")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process the first N admissions (for validation)",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.limit is not None and args.limit <= 0:
        raise SystemExit("--limit must be a positive integer")
    metrics = run(args.input, args.output, args.report, limit=args.limit)
    print(
        f"processed {metrics['admissions']} admissions and "
        f"embedded {metrics['events']} POE events in {args.output}"
    )
