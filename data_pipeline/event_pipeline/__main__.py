"""Command line entry points for cleaning and deterministic normalization."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import tempfile

from .normalization import run_normalization
from .pipeline import run_cleaning


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build and normalize MIMIC clinical-event Parquet files."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    clean = subparsers.add_parser("clean", help="Run structured eventization")
    clean.add_argument("input", type=Path)
    clean.add_argument("--output-dir", type=Path, required=True)
    clean.add_argument("--batch-size", type=int, default=5000)
    clean.add_argument("--limit", type=int)

    normalize = subparsers.add_parser(
        "normalize", help="Apply frozen deterministic normalization"
    )
    normalize.add_argument("cleaned_events", type=Path)
    normalize.add_argument("term_inventory", type=Path)
    normalize.add_argument("--output-dir", type=Path, required=True)
    normalize.add_argument("--batch-size", type=int, default=5000)

    run = subparsers.add_parser("run", help="Run both stages in order")
    run.add_argument("input", type=Path)
    run.add_argument("--output-dir", type=Path, required=True)
    run.add_argument("--batch-size", type=int, default=5000)
    run.add_argument("--limit", type=int)
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.command == "clean":
        result = run_cleaning(
            args.input,
            args.output_dir,
            batch_size=args.batch_size,
            limit=args.limit,
        )
    elif args.command == "normalize":
        result = run_normalization(
            args.cleaned_events,
            args.term_inventory,
            args.output_dir,
            batch_size=args.batch_size,
        )
    else:
        output_directory = args.output_dir.resolve()
        if output_directory.exists():
            raise FileExistsError(output_directory)
        output_directory.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(
            tempfile.mkdtemp(
                prefix=f".{output_directory.name}.tmp-",
                dir=output_directory.parent,
            )
        )
        try:
            cleaning_directory = temporary / "cleaning"
            normalization_directory = temporary / "normalization"
            cleaning = run_cleaning(
                args.input,
                cleaning_directory,
                batch_size=args.batch_size,
                limit=args.limit,
            )
            normalization = run_normalization(
                cleaning_directory / "cleaned_events.parquet",
                cleaning_directory / "term_inventory.parquet",
                normalization_directory,
                batch_size=args.batch_size,
            )
            result = {"cleaning": cleaning, "normalization": normalization}
            os.replace(temporary, output_directory)
        except Exception:
            shutil.rmtree(temporary, ignore_errors=True)
            raise
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
