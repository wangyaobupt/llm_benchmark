"""Command-line entry point for the v2 MCQ pipeline.

Commands:
  run-all      mine -> lock -> generate -> review -> human queue -> gold

Real model calls are OFF by default; pass --execute-api together with the
environment authorization to make real calls (design doc §4.4 / §20).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_pipeline.text_ner.openai_compatible_api import OpenAICompatibleSettings  # noqa: E402

from .client import FakeStructuredClient, OpenAIStructuredClient, load_api_config  # noqa: E402
from .config_loader import CONFIG_DIR, load_prompt, load_thresholds  # noqa: E402
from .pipeline import load_events, run_pipeline  # noqa: E402

DEFAULT_EVENTS = Path(
    r"G:\Projects\llm_benchmark\data\derived\coronary_all_three_modules_full"
    r"\event_pipeline\normalization\normalized_events.parquet"
)
DEFAULT_SPLIT = Path(
    r"D:\Projects\llm_benchmark\tasks\investigation_selection\output\split\subject_split.parquet"
)
DEFAULT_OUT = Path(r"D:\Projects\llm_benchmark\versions\v2-llm-stem\output")


def _external_authorized() -> bool:
    return (
        os.environ.get("MCQ_EXTERNAL_API_APPROVED", "") == "YES"
        or os.environ.get("MIMIC_EXTERNAL_API_APPROVED", "") == "YES"
    )


def _build_client(args) -> tuple[object, str]:
    """Return (client, effective_model)."""
    if args.execute_api:
        api_config = load_api_config(Path(args.api_config))
        settings = OpenAICompatibleSettings.from_environment(api_config, os.environ)
        client = OpenAIStructuredClient(
            settings, api_config, execute=True,
            data_transfer_authorized=_external_authorized(),
        )
        return client, settings.model
    model = args.generator_model or "fake-mcq-model"
    return FakeStructuredClient(model_name=model), model


def _parse_human_decisions(path: Path | None) -> dict[str, str]:
    if path is None or not Path(path).exists():
        return {}
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {str(k): str(v) for k, v in data.items()}


def _prompt_path(args, name: str) -> Path:
    if args.prompts_dir:
        return Path(args.prompts_dir) / name
    return CONFIG_DIR / "prompts" / name


def cmd_run_all(args) -> int:
    thresholds = load_thresholds(args.profile, Path(args.thresholds))
    client, model = _build_client(args)
    generate_prompt = load_prompt("generate_stem.md", _prompt_path(args, "generate_stem.md"))
    review_prompt = load_prompt("review_question.md", _prompt_path(args, "review_question.md"))

    events, meta = load_events(Path(args.events), Path(args.split), args.role)

    summary = run_pipeline(
        events,
        thresholds,
        client,
        generate_prompt,
        review_prompt,
        profile=args.profile,
        human_decisions=_parse_human_decisions(args.human_decisions),
        release_policy={"allowed_schema_versions": ["1.0.0"],
                        "allowed_prompt_versions": ["1.0.0"]},
        out_dir=Path(args.out_dir),
        generator_model=args.generator_model,
        reviewer_model=args.reviewer_model,
        input_meta=meta,
    )
    _print_summary(summary)
    return 0


def _print_summary(summary: dict) -> None:
    print("=" * 78)
    print("v2 MCQ pipeline — clinical investigation selection")
    print("=" * 78)
    print(f"profile          : {summary['run_profile']}")
    print(f"generator        : {summary['generator_model']}")
    print(f"reviewer         : {summary['reviewer_model']}")
    for k, v in summary["counts"].items():
        print(f"{k:<28}: {v}")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("run-all", help="run the full pipeline")
    p.add_argument("--events", type=str, default=str(DEFAULT_EVENTS))
    p.add_argument("--split", type=str, default=str(DEFAULT_SPLIT))
    p.add_argument("--role", default="development")
    p.add_argument("--profile", default="exploratory", choices=["formal", "exploratory"])
    p.add_argument("--thresholds", type=str, default=str(CONFIG_DIR / "thresholds.yaml"))
    p.add_argument("--prompts-dir", type=str, default=None)
    p.add_argument("--api-config", type=str, default=str(CONFIG_DIR / "api.json"))
    p.add_argument("--out-dir", type=str, default=str(DEFAULT_OUT))
    p.add_argument("--execute-api", action="store_true")
    p.add_argument("--generator-model", type=str, default=None)
    p.add_argument("--reviewer-model", type=str, default=None)
    p.add_argument("--human-decisions", type=str, default=None)
    p.set_defaults(func=cmd_run_all)
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
