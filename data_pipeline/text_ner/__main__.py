"""Command-line entry point for model-free text NER input preparation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .audit import audit_manifest
from .annotation_package import prepare_annotation_package
from .annotation_package_audit import audit_annotation_package
from .manifest import DEFAULT_PILOT_SEED, DEFAULT_PILOT_SIZE, prepare_manifest
from .method_run import prepare_method_run
from .method_run_audit import audit_method_run
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
    package = subparsers.add_parser(
        "prepare-annotation-package",
        help="Create patient-isolated local human annotation packages",
    )
    package.add_argument("input_jsonl", type=Path)
    package.add_argument("manifest", type=Path)
    package.add_argument("--output-dir", type=Path, required=True)
    package.add_argument("--calibration-documents", type=int, default=50)

    package_audit = subparsers.add_parser(
        "audit-annotation-package",
        help="Audit allocation, blinding, task hashes, and decision contracts",
    )
    package_audit.add_argument("package_directory", type=Path)
    package_audit.add_argument("--replay-directory", type=Path)
    package_audit.add_argument("--output-json", type=Path)
    package_audit.add_argument("--output-markdown", type=Path)
    method_run = subparsers.add_parser(
        "prepare-method-run",
        help="Prepare calibration-only two-stage NER requests without model calls",
    )
    method_run.add_argument("annotation_package", type=Path)
    method_run.add_argument("method_config", type=Path)
    method_run.add_argument("--output-dir", type=Path, required=True)
    method_run.add_argument(
        "--execute",
        action="store_true",
        help="Explicit model execution gate; intentionally unavailable in this version",
    )
    method_audit = subparsers.add_parser(
        "audit-method-run",
        help="Audit calibration isolation, request hashes, gold gate, and zero model calls",
    )
    method_audit.add_argument("annotation_package", type=Path)
    method_audit.add_argument("method_config", type=Path)
    method_audit.add_argument("run_directory", type=Path)
    method_audit.add_argument("--replay-directory", type=Path)
    method_audit.add_argument("--output-json", type=Path)
    method_audit.add_argument("--output-markdown", type=Path)
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
    elif args.command == "rehearse-scope":
        result = rehearse_scope(
            args.input_jsonl,
            args.manifest,
            expected_pilot_documents=args.expected_pilot_documents,
            output_json=args.output_json,
            output_markdown=args.output_markdown,
        )
    elif args.command == "prepare-annotation-package":
        result = prepare_annotation_package(
            args.input_jsonl,
            args.manifest,
            args.output_dir,
            calibration_documents=args.calibration_documents,
        )
    elif args.command == "audit-annotation-package":
        result = audit_annotation_package(
            args.package_directory,
            replay_directory=args.replay_directory,
            output_json=args.output_json,
            output_markdown=args.output_markdown,
        )
    elif args.command == "prepare-method-run":
        result = prepare_method_run(
            args.annotation_package,
            args.method_config,
            args.output_dir,
            execute=args.execute,
        )
    else:
        result = audit_method_run(
            args.annotation_package,
            args.method_config,
            args.run_directory,
            replay_directory=args.replay_directory,
            output_json=args.output_json,
            output_markdown=args.output_markdown,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
