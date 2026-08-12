"""Single command-line entry point for every event-processing task."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .event_cleaning.pipeline import run_cleaning
from .event_normalization.pipeline import run_normalization
from .event_quality import regression
from .event_quality.consolidate_review import consolidate_review_packages
from .event_quality.review_normalization import generate_review_package
from .event_viewer import app as viewer
from .event_viewer import review_app as review_ui
from .workflow import run_workflow


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Clean, audit, normalize, reproduce, and inspect MIMIC events."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser(
        "run",
        help="Run cleaning, both audits, normalization, and reproducibility gates",
    )
    run.add_argument("source_jsonl", type=Path)
    run.add_argument("--raw-source-jsonl", type=Path, required=True)
    run.add_argument("--output-dir", type=Path, required=True)
    run.add_argument("--batch-size", type=int, default=5000)
    run.add_argument("--replay-batch-size", type=int, default=777)
    run.add_argument("--limit", type=int)

    clean = subparsers.add_parser("clean", help="Run only structured event cleaning")
    clean.add_argument("source_jsonl", type=Path)
    clean.add_argument("--output-dir", type=Path, required=True)
    clean.add_argument("--batch-size", type=int, default=5000)
    clean.add_argument("--limit", type=int)

    normalize = subparsers.add_parser(
        "normalize", help="Run only frozen deterministic normalization"
    )
    normalize.add_argument("cleaned_events", type=Path)
    normalize.add_argument("term_inventory", type=Path)
    normalize.add_argument("--output-dir", type=Path, required=True)
    normalize.add_argument("--batch-size", type=int, default=5000)

    view = subparsers.add_parser("view", help="Open the read-only event viewer")
    view.add_argument("event_directory", type=Path)
    view.add_argument("--source-jsonl", type=Path)
    view.add_argument("--port", type=int, default=8765)
    view.add_argument("--no-browser", action="store_true")
    view.add_argument("--check", action="store_true")

    review = subparsers.add_parser(
        "review", help="Generate automated checks and a human normalization review package"
    )
    review.add_argument("event_directory", type=Path)
    review.add_argument("--output-dir", type=Path)
    review.add_argument("--samples-per-stratum", type=int, default=3)
    review.add_argument("--top-mappings-per-entity", type=int, default=10)

    review_view = subparsers.add_parser(
        "review-ui", help="Open the local normalization human-review window"
    )
    review_view.add_argument("event_directory", type=Path)
    review_view.add_argument("--source-jsonl", type=Path)
    review_view.add_argument("--port", type=int, default=8766)
    review_view.add_argument("--no-browser", action="store_true")
    review_view.add_argument("--check", action="store_true")

    review_master = subparsers.add_parser(
        "review-master",
        help="Consolidate multiple review packages and create a 100-term pilot",
    )
    review_master.add_argument("event_directories", nargs="+", type=Path)
    review_master.add_argument("--output-dir", type=Path, required=True)

    regression_parser = subparsers.add_parser(
        "regression", help="Capture or verify privacy-safe cleaning baselines"
    )
    regression_parser.add_argument("regression_args", nargs=argparse.REMAINDER)
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.command == "run":
        result = run_workflow(
            args.source_jsonl,
            args.raw_source_jsonl,
            args.output_dir,
            batch_size=args.batch_size,
            replay_batch_size=args.replay_batch_size,
            limit=args.limit,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if args.command == "clean":
        result = run_cleaning(
            args.source_jsonl,
            args.output_dir,
            batch_size=args.batch_size,
            limit=args.limit,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if args.command == "normalize":
        result = run_normalization(
            args.cleaned_events,
            args.term_inventory,
            args.output_dir,
            batch_size=args.batch_size,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if args.command == "view":
        viewer_args = [str(args.event_directory), "--port", str(args.port)]
        if args.source_jsonl:
            viewer_args.extend(["--source-jsonl", str(args.source_jsonl)])
        if args.no_browser:
            viewer_args.append("--no-browser")
        if args.check:
            viewer_args.append("--check")
        viewer.main(viewer_args)
        return
    if args.command == "review":
        result = generate_review_package(
            args.event_directory,
            args.output_dir,
            samples_per_stratum=args.samples_per_stratum,
            top_mappings_per_entity=args.top_mappings_per_entity,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if args.command == "review-ui":
        review_directory = (
            args.event_directory
            if args.event_directory.name == "review"
            or (args.event_directory / "review_summary.json").is_file()
            else args.event_directory / "review"
        )
        ui_args = [str(review_directory), "--port", str(args.port)]
        if args.source_jsonl:
            ui_args.extend(["--source-jsonl", str(args.source_jsonl)])
        if args.no_browser:
            ui_args.append("--no-browser")
        if args.check:
            ui_args.append("--check")
        raise SystemExit(review_ui.main(ui_args))
    if args.command == "review-master":
        result = consolidate_review_packages(
            args.event_directories,
            args.output_dir,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    raise SystemExit(regression.main(args.regression_args))


if __name__ == "__main__":
    main()
