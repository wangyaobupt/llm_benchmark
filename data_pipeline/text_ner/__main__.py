"""Command-line entry point for traceable text NER preparation and execution."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .audit import audit_manifest
from .annotation_package import prepare_annotation_package
from .annotation_package_audit import audit_annotation_package
from .api_monitor import monitor_api_html
from .deepseek_cost import estimate_deepseek_cost
from .aggregation_manifest import prepare_aggregation_text_manifest
from .full_extraction import compile_model_responses, prepare_full_extraction_package
from .manifest import DEFAULT_PILOT_SEED, DEFAULT_PILOT_SIZE, prepare_manifest
from .method_run import prepare_method_run
from .method_run_audit import audit_method_run
from .openai_compatible_api import run_api_batch
from .scope_rehearsal import rehearse_scope


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare, execute, validate, and compile traceable text NER workflows; "
            "model execution remains an explicit opt-in action."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser(
        "prepare-legacy-ed-radiology",
        help="Deprecated historical 100-case ED/radiology manifest builder",
    )
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
    deepseek_cost = subparsers.add_parser(
        "estimate-deepseek-cost",
        help="Estimate DeepSeek API cost without calls and report the MIMIC policy gate",
    )
    deepseek_cost.add_argument("method_run_directory", type=Path)
    deepseek_cost.add_argument("policy", type=Path)
    deepseek_cost.add_argument("--output-json", type=Path)
    deepseek_cost.add_argument("--output-markdown", type=Path)
    full = subparsers.add_parser(
        "prepare-full-extraction",
        help="Prepare requests for all included manifest sources without model calls",
    )
    full.add_argument("aggregation_directory", type=Path)
    full.add_argument("manifest", type=Path)
    full.add_argument("--output-dir", type=Path, required=True)
    full.add_argument("--mention-prompt", type=Path, required=True)
    full.add_argument("--relation-prompt", type=Path, required=True)
    compile_responses = subparsers.add_parser(
        "compile-model-responses",
        help="Validate supplied model responses and compile entity/relation sidecars",
    )
    compile_responses.add_argument("package_directory", type=Path)
    compile_responses.add_argument("manifest", type=Path)
    compile_responses.add_argument("mention_responses", type=Path)
    compile_responses.add_argument("relation_responses", type=Path)
    compile_responses.add_argument("--output-dir", type=Path, required=True)
    aggregation_manifest = subparsers.add_parser(
        "prepare-aggregation-manifest",
        help="Prepare all configured free text from an accepted aggregation package",
    )
    aggregation_manifest.add_argument("aggregation_directory", type=Path)
    aggregation_manifest.add_argument("source_catalog", type=Path)
    aggregation_manifest.add_argument("--output-dir", type=Path, required=True)
    api_batch = subparsers.add_parser(
        "run-openai-compatible-api",
        help="Explicitly execute or resume one model stage through a generic API",
    )
    api_batch.add_argument("requests", type=Path)
    api_batch.add_argument("prompt", type=Path)
    api_batch.add_argument("responses", type=Path)
    api_batch.add_argument("audit", type=Path)
    api_batch.add_argument("config", type=Path)
    api_batch.add_argument(
        "--env-file",
        type=Path,
        help=(
            "Read the five TEXT_NER_* settings from a UTF-8 KEY=VALUE file; "
            "process environment variables override file values"
        ),
    )
    api_batch.add_argument(
        "--failure-audit",
        type=Path,
        help=(
            "Write failed API attempts to this JSONL; defaults to "
            "<audit-stem>.failures.jsonl"
        ),
    )
    api_batch.add_argument("--execute", action="store_true")
    api_batch.add_argument(
        "--endpoint-scope", choices=("local", "external"), default="external"
    )
    api_batch.add_argument("--confirm-data-transfer-authorized", action="store_true")
    api_batch.add_argument("--maximum-requests", type=int)
    api_monitor = subparsers.add_parser(
        "monitor-openai-compatible-api",
        help="Continuously refresh a read-only HTML dashboard from response/audit JSONL",
    )
    api_monitor.add_argument("responses", type=Path)
    api_monitor.add_argument("audit", type=Path)
    api_monitor.add_argument(
        "--output-html",
        type=Path,
        help=(
            "Dashboard path; by default it is derived beside the audit file"
        ),
    )
    api_monitor.add_argument("--expected-requests", type=int, required=True)
    api_monitor.add_argument("--stage-label", default="Text NER")
    api_monitor.add_argument(
        "--refresh-seconds",
        "--interval-seconds",
        dest="refresh_seconds",
        type=int,
        default=10,
        help="HTML generation and browser refresh interval (default: 10 seconds)",
    )
    api_monitor.add_argument("--stalled-after-seconds", type=int, default=300)
    api_monitor.add_argument(
        "--watch",
        action="store_true",
        help="Keep updating until Ctrl+C; otherwise write one HTML snapshot",
    )
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.command == "prepare-legacy-ed-radiology":
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
    elif args.command == "audit-method-run":
        result = audit_method_run(
            args.annotation_package,
            args.method_config,
            args.run_directory,
            replay_directory=args.replay_directory,
            output_json=args.output_json,
            output_markdown=args.output_markdown,
        )
    elif args.command == "estimate-deepseek-cost":
        result = estimate_deepseek_cost(
            args.method_run_directory,
            args.policy,
            output_json=args.output_json,
            output_markdown=args.output_markdown,
        )
    elif args.command == "prepare-full-extraction":
        result = prepare_full_extraction_package(
            args.aggregation_directory,
            args.manifest,
            args.output_dir,
            mention_prompt_path=args.mention_prompt,
            relation_prompt_path=args.relation_prompt,
        )
    elif args.command == "compile-model-responses":
        result = compile_model_responses(
            args.package_directory,
            args.manifest,
            args.mention_responses,
            args.relation_responses,
            args.output_dir,
        )
    elif args.command == "prepare-aggregation-manifest":
        result = prepare_aggregation_text_manifest(
            args.aggregation_directory,
            args.source_catalog,
            args.output_dir,
        )
    elif args.command == "monitor-openai-compatible-api":
        result = monitor_api_html(
            args.responses,
            args.audit,
            args.output_html,
            expected_requests=args.expected_requests,
            stage_label=args.stage_label,
            refresh_seconds=args.refresh_seconds,
            stalled_after_seconds=args.stalled_after_seconds,
            watch=args.watch,
        )
    else:
        result = run_api_batch(
            args.requests,
            args.prompt,
            args.responses,
            args.audit,
            args.config,
            execute=args.execute,
            endpoint_scope=args.endpoint_scope,
            data_transfer_authorized=args.confirm_data_transfer_authorized,
            maximum_requests=args.maximum_requests,
            environment_file=args.env_file,
            failure_audit_path=args.failure_audit,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
