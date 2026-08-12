"""Command-line entry point for model-free text NER input preparation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .audit import audit_manifest
from .manifest import DEFAULT_PILOT_SEED, DEFAULT_PILOT_SIZE, prepare_manifest
from .scope_rehearsal import rehearse_scope


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare and audit traceable text NER inputs without model calls."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("input_jsonl", type=Path)
    prepare.add_argument("--output-dir", type=Path, required=True)
    prepare.add_argument("--pilot-size", type=int, default=DEFAULT_PILOT_SIZE)
    prepare.add_argument("--pilot-seed", default=DEFAULT_PILOT_SEED)

    audit = subparsers.add_parser("audit")
    audit.add_argument("input_jsonl", type=Path)
    audit.add_argument("manifest_directory", type=Path)
    audit.add_argument("--replay-directory", type=Path)
    audit.add_argument("--output-json", type=Path)
    audit.add_argument("--output-markdown", type=Path)
    rehearse = subparsers.add_parser(
        "rehearse-scope",
        help="Profile annotation scenarios on pilot spans without saving raw text",
    )
    rehearse.add_argument("input_jsonl", type=Path)
    rehearse.add_argument("manifest", type=Path)
    rehearse.add_argument("--expected-pilot-documents", type=int, default=200)
    rehearse.add_argument("--output-json", type=Path)
    rehearse.add_argument("--output-markdown", type=Path)
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.command == "prepare":
        result = prepare_manifest(
            args.input_jsonl,
            args.output_dir,
            pilot_size=args.pilot_size,
            pilot_seed=args.pilot_seed,
        )
    elif args.command == "audit":
        result = audit_manifest(
            args.input_jsonl,
            args.manifest_directory,
            replay_directory=args.replay_directory,
            output_json=args.output_json,
            output_markdown=args.output_markdown,
        )
    else:
        result = rehearse_scope(
            args.input_jsonl,
            args.manifest,
            expected_pilot_documents=args.expected_pilot_documents,
            output_json=args.output_json,
            output_markdown=args.output_markdown,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
