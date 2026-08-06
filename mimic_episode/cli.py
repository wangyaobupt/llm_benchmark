from __future__ import annotations

import argparse
import json
from pathlib import Path

from mimic_episode.episode_export import export_episode_json
from mimic_episode.episode_pipeline import build_episode_outputs
from mimic_episode.paths import DatasetPaths
from mimic_episode.pipeline import build_outputs
from mimic_episode.source_catalog import EpisodeDatasetPaths


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mimic-pipeline",
        description="使用 DuckDB 从本地 MIMIC CSV.GZ 构建文本、就诊和临床事件时间线。",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="检查第一阶段所需文件是否齐全")
    validate_parser.add_argument("--data-root", type=Path, default=Path("mimic"))

    extract_parser = subparsers.add_parser("extract", help="生成病例索引、文本和质量报告")
    extract_parser.add_argument("--data-root", type=Path, default=Path("mimic"))
    extract_parser.add_argument("--output-dir", type=Path, default=Path("outputs/stage1"))
    extract_parser.add_argument("--memory-limit", default="8GB")
    extract_parser.add_argument("--threads", type=int, default=4)
    extract_parser.add_argument("--overwrite", action="store_true")

    validate_episode_parser = subparsers.add_parser(
        "validate-episodes",
        help="检查全过程聚合所需的 41 张源表及锁定表头",
    )
    validate_episode_parser.add_argument("--data-root", type=Path, default=Path("mimic"))

    aggregate_parser = subparsers.add_parser(
        "aggregate-episodes",
        help="生成跨急诊、住院、ICU 和文本系统的就诊时间线",
    )
    aggregate_parser.add_argument("--data-root", type=Path, default=Path("mimic"))
    aggregate_parser.add_argument("--output-dir", type=Path, default=Path("outputs/episodes"))
    aggregate_parser.add_argument("--memory-limit", default="8GB")
    aggregate_parser.add_argument("--threads", type=int, default=4)
    aggregate_parser.add_argument("--overwrite", action="store_true")

    export_parser = subparsers.add_parser(
        "export-episode",
        help="按需导出一个严格区分既往资料与本次就诊的 JSON",
    )
    export_parser.add_argument("--output-dir", type=Path, default=Path("outputs/episodes"))
    export_parser.add_argument("--episode-id", required=True)
    export_parser.add_argument("--destination", type=Path, required=True)
    export_parser.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    if args.command == "validate":
        paths = DatasetPaths.from_root(args.data_root)
        paths.validate()
        print(f"第一阶段所需的 {len(paths.required_files())} 个文件及表头均通过验证。")
        return 0

    if args.command == "validate-episodes":
        paths = EpisodeDatasetPaths.from_root(args.data_root)
        paths.validate()
        print(f"全过程聚合所需的 {len(paths.required_files())} 张源表及表头均通过验证。")
        return 0

    if args.command == "aggregate-episodes":
        report = build_episode_outputs(
            data_root=args.data_root,
            output_dir=args.output_dir,
            memory_limit=args.memory_limit,
            threads=args.threads,
            overwrite=args.overwrite,
        )
        summary = {
            "output_dir": str(args.output_dir.resolve()),
            "episode_rows": report["outputs"]["episode_index"]["rows"],
            "contact_rows": report["outputs"]["care_contacts"]["rows"],
            "event_rows": report["outputs"]["timeline_events"]["rows"],
            "document_rows": report["outputs"]["documents"]["rows"],
            "link_status": report["links"],
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    if args.command == "export-episode":
        payload = export_episode_json(
            args.output_dir,
            args.episode_id,
            args.destination,
            overwrite=args.overwrite,
        )
        summary = {
            "episode_id": payload["episode_id"],
            "destination": str(args.destination.resolve()),
            "prior_event_rows": len(payload["prior_context"]["events"]),
            "current_event_rows": len(payload["current_episode"]["timeline_events"]),
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0

    report = build_outputs(
        data_root=args.data_root,
        output_dir=args.output_dir,
        memory_limit=args.memory_limit,
        threads=args.threads,
        overwrite=args.overwrite,
    )
    summary = {
        "output_dir": str(args.output_dir.resolve()),
        "case_index_rows": report["outputs"]["case_index"]["rows"],
        "text_document_rows": report["outputs"]["text_documents"]["rows"],
        "note_detail_rows": report["outputs"]["note_details"]["rows"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0
