"""Prepare deterministic, calibration-only exploratory NER method runs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any

from .annotation_contracts import ANNOTATION_PROTOCOL_VERSION
from .annotation_validation import SectionAnnotationValidator
from .method_contracts import (
    METHOD_REQUEST_SCHEMA_VERSION,
    METHOD_RUN_SCHEMA_VERSION,
    MethodContractError,
    validate_method_config,
    validate_method_run,
)
from .method_evaluation import evaluate_section_annotations


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _stable_id(prefix: str, *parts: object) -> str:
    return f"{prefix}:{_sha256_text(chr(31).join(str(part) for part in parts))[:24]}"


def _json_dump(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _jsonl_dump(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(
                json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                + "\n"
            )


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise MethodContractError(
                    "METHOD_TASK_JSON_INVALID", f"{path.name}:{line_number}: {error}"
                ) from error
    return rows


def _resolve_prompt(config_path: Path, relative_path: str) -> Path:
    base = config_path.parent.resolve()
    path = (base / relative_path).resolve()
    if base != path and base not in path.parents:
        raise MethodContractError("METHOD_PROMPT_PATH_ESCAPE", relative_path)
    if not path.is_file():
        raise MethodContractError("METHOD_PROMPT_MISSING", relative_path)
    return path


def _implementation_hash() -> str:
    module_directory = Path(__file__).resolve().parent
    paths = [
        module_directory / "method_contracts.py",
        module_directory / "method_evaluation.py",
        module_directory / "method_run.py",
        module_directory / "rule_baseline.py",
        module_directory / "annotation_validation.py",
        module_directory / "annotation_contracts.py",
        module_directory / "schemas" / "ner-method-config.schema.json",
        module_directory / "schemas" / "ner-method-run.schema.json",
        module_directory / "schemas" / "section-annotation.schema.json",
    ]
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: item.name):
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\x00")
        digest.update(path.read_bytes())
        digest.update(b"\x00")
    return digest.hexdigest()


def _validate_calibration_tasks(
    a_tasks: list[dict[str, Any]], b_tasks: list[dict[str, Any]]
) -> None:
    if not a_tasks:
        raise MethodContractError("METHOD_CALIBRATION_EMPTY", "annotator_a tasks")
    a_units = [task.get("annotation_unit_id") for task in a_tasks]
    b_units = [task.get("annotation_unit_id") for task in b_tasks]
    if len(a_units) != len(set(a_units)):
        raise MethodContractError("METHOD_DUPLICATE_TASK", "annotator_a")
    if set(a_units) != set(b_units):
        raise MethodContractError("METHOD_ANNOTATOR_TASK_SET_MISMATCH", "A versus B")
    validator = SectionAnnotationValidator()
    for task in a_tasks:
        if task.get("partition") != "calibration":
            raise MethodContractError(
                "METHOD_NON_CALIBRATION_INPUT", str(task.get("partition"))
            )
        if task.get("release_status") != "released":
            raise MethodContractError(
                "METHOD_CALIBRATION_NOT_RELEASED", str(task.get("annotation_unit_id"))
            )
        if task.get("annotator_slot") != "annotator_a":
            raise MethodContractError(
                "METHOD_CANONICAL_TASK_SLOT_INVALID", str(task.get("annotator_slot"))
            )
        if task.get("annotation", {}).get("mentions") or task.get("annotation", {}).get(
            "relations"
        ):
            raise MethodContractError(
                "METHOD_TASK_CONTAINS_HUMAN_ANNOTATION",
                str(task.get("annotation_unit_id")),
            )
        validator.validate(
            task["annotation"],
            {
                "manifest_row_id": task["manifest_row_id"],
                "document_id": task["document_id"],
                "section_id": task["section_id"],
                "span_sha256": task["section_text_sha256"],
            },
            task["section_text"],
        )


def prepare_method_run(
    annotation_package: Path,
    method_config_path: Path,
    output_directory: Path,
    *,
    execute: bool = False,
) -> dict[str, Any]:
    """Prepare immutable requests without invoking a model.

    Real model execution is intentionally unavailable in this version. The explicit
    flag fails before any output is written so authorization cannot be inferred from
    a prepared request package.
    """

    if execute:
        raise MethodContractError(
            "MODEL_EXECUTION_NOT_AUTHORIZED",
            "this method version supports deterministic dry-run preparation only",
        )
    annotation_package = Path(annotation_package).resolve()
    method_config_path = Path(method_config_path).resolve()
    output_directory = Path(output_directory).resolve()
    if output_directory.exists():
        raise FileExistsError(f"output directory already exists: {output_directory}")

    config_bytes = method_config_path.read_bytes()
    config = json.loads(config_bytes.decode("utf-8"))
    validate_method_config(config)
    if config["annotation_protocol_version"] != ANNOTATION_PROTOCOL_VERSION:
        raise MethodContractError(
            "METHOD_PROTOCOL_VERSION_MISMATCH",
            config["annotation_protocol_version"],
        )

    package_manifest_path = annotation_package / "run_manifest.json"
    a_path = annotation_package / "calibration" / "annotator_a" / "tasks.jsonl"
    b_path = annotation_package / "calibration" / "annotator_b" / "tasks.jsonl"
    for required_path in (package_manifest_path, a_path, b_path):
        if not required_path.is_file():
            raise MethodContractError("METHOD_PACKAGE_FILE_MISSING", str(required_path))
    a_tasks = _load_jsonl(a_path)
    b_tasks = _load_jsonl(b_path)
    _validate_calibration_tasks(a_tasks, b_tasks)
    tasks = sorted(a_tasks, key=lambda task: task["annotation_unit_id"])

    prompts: dict[str, dict[str, Any]] = {}
    for stage in config["stages"]:
        path = _resolve_prompt(method_config_path, stage["prompt_path"])
        prompt_text = path.read_text(encoding="utf-8")
        prompts[stage["stage_id"]] = {
            "path": path,
            "text": prompt_text,
            "sha256": _sha256_text(prompt_text),
        }

    output_directory.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{output_directory.name}.", dir=output_directory.parent
        )
    )
    try:
        (temporary / "configuration" / "prompts").mkdir(parents=True)
        (temporary / "requests").mkdir()
        (temporary / "candidates").mkdir()
        (temporary / "evaluation").mkdir()
        (temporary / "configuration" / "method.json").write_bytes(config_bytes)
        for stage_id, prompt in prompts.items():
            (temporary / "configuration" / "prompts" / f"{stage_id}.md").write_text(
                prompt["text"], encoding="utf-8", newline="\n"
            )

        mention_requests: list[dict[str, Any]] = []
        relation_pending: list[dict[str, Any]] = []
        for task in tasks:
            unit_id = task["annotation_unit_id"]
            mention_requests.append(
                {
                    "schema_version": METHOD_REQUEST_SCHEMA_VERSION,
                    "request_id": _stable_id(
                        "nreq", config["method_id"], "mentions", unit_id
                    ),
                    "method_id": config["method_id"],
                    "method_version": config["method_version"],
                    "stage_id": "mentions",
                    "candidate_status": "exploratory_candidate",
                    "partition": "calibration",
                    "annotation_unit_id": unit_id,
                    "manifest_row_id": task["manifest_row_id"],
                    "document_id": task["document_id"],
                    "section_id": task["section_id"],
                    "source_table": task["source_table"],
                    "section_name": task["section_name"],
                    "section_text": task["section_text"],
                    "section_text_sha256": task["section_text_sha256"],
                    "prompt_sha256": prompts["mentions"]["sha256"],
                    "response_schema_version": task["annotation"]["schema_version"],
                }
            )
            relation_pending.append(
                {
                    "schema_version": METHOD_REQUEST_SCHEMA_VERSION,
                    "request_id": _stable_id(
                        "nreq", config["method_id"], "relations", unit_id
                    ),
                    "method_id": config["method_id"],
                    "method_version": config["method_version"],
                    "stage_id": "relations",
                    "candidate_status": "exploratory_candidate",
                    "partition": "calibration",
                    "annotation_unit_id": unit_id,
                    "manifest_row_id": task["manifest_row_id"],
                    "dependency_status": "blocked_pending_validated_mentions",
                    "prompt_sha256": prompts["relations"]["sha256"],
                }
            )
        mention_path = temporary / "requests" / "mention_requests.jsonl"
        relation_path = temporary / "requests" / "relation_requests.pending.jsonl"
        candidates_path = temporary / "candidates" / "section_annotations.jsonl"
        metrics_path = temporary / "evaluation" / "metrics.json"
        _jsonl_dump(mention_path, mention_requests)
        _jsonl_dump(relation_path, relation_pending)
        _jsonl_dump(candidates_path, [])
        _json_dump(metrics_path, evaluate_section_annotations([], None))

        summary = {
            "schema_version": METHOD_RUN_SCHEMA_VERSION,
            "run_status": "prepared_no_model_calls",
            "candidate_status": "exploratory_candidate",
            "partition": "calibration",
            "text_units": len(tasks),
            "mention_requests": len(mention_requests),
            "relation_requests_pending": len(relation_pending),
            "candidate_annotations": 0,
            "evaluation_access_count": 0,
            "human_gold_access_count": 0,
            "model_calls": 0,
            "metrics_status": "not_evaluable",
            "restricted_text": {
                "present_in_local_request_file": True,
                "git_tracking_allowed": False,
            },
        }
        summary_path = temporary / "method_run_summary.json"
        _json_dump(summary_path, summary)

        output_paths = [
            temporary / "configuration" / "method.json",
            temporary / "configuration" / "prompts" / "mentions.md",
            temporary / "configuration" / "prompts" / "relations.md",
            mention_path,
            relation_path,
            candidates_path,
            metrics_path,
            summary_path,
        ]
        output_hashes = {
            path.relative_to(temporary).as_posix(): _sha256_file(path)
            for path in output_paths
        }
        method_config_sha256 = _sha256_bytes(config_bytes)
        package_manifest_sha256 = _sha256_file(package_manifest_path)
        task_sha256 = _sha256_file(a_path)
        run_manifest = {
            "schema_version": METHOD_RUN_SCHEMA_VERSION,
            "run_id": _stable_id(
                "nrun",
                method_config_sha256,
                package_manifest_sha256,
                task_sha256,
                _implementation_hash(),
            ),
            "run_status": "prepared_no_model_calls",
            "candidate_status": "exploratory_candidate",
            "method": {
                "method_id": config["method_id"],
                "method_version": config["method_version"],
                "method_config_sha256": method_config_sha256,
                "annotation_protocol_version": config[
                    "annotation_protocol_version"
                ],
            },
            "input": {
                "annotation_package_manifest_sha256": package_manifest_sha256,
                "calibration_task_sha256": task_sha256,
                "partition": "calibration",
                "text_units": len(tasks),
                "evaluation_access_count": 0,
            },
            "execution": {
                "mode": "dry_run",
                "model_calls": 0,
                "provider": None,
                "model_name": None,
                "started_at_utc": None,
                "completed_at_utc": None,
            },
            "reproducibility": {
                "implementation_sha256": _implementation_hash(),
                "prompt_sha256": {
                    stage_id: prompt["sha256"]
                    for stage_id, prompt in sorted(prompts.items())
                },
                "request_order": "annotation_unit_id",
                "seed": None,
            },
            "outputs": output_hashes,
        }
        validate_method_run(run_manifest)
        _json_dump(temporary / "run_manifest.json", run_manifest)
        temporary.replace(output_directory)
        return run_manifest
    except Exception:
        resolved_temporary = temporary.resolve()
        if output_directory.parent.resolve() in resolved_temporary.parents:
            shutil.rmtree(resolved_temporary, ignore_errors=True)
        raise
