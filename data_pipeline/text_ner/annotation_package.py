"""Create deterministic patient-isolated human annotation work packages."""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from .annotation_contracts import (
    ANNOTATION_ALLOCATION_ARROW_SCHEMA,
    ANNOTATION_ALLOCATION_SCHEMA_VERSION,
    ANNOTATION_PROTOCOL_VERSION,
    SECTION_ANNOTATION_SCHEMA_VERSION,
)
from .annotation_validation import SectionAnnotationValidator


ANNOTATION_PACKAGE_VERSION = "text-ner-human-annotation-package/1.0.0"
ALLOCATION_SEED = "text-ner-annotation-allocation/1.0.0"


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _stable_id(prefix: str, *parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts)
    return f"{prefix}:{_sha256_text(payload)[:24]}"


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


def _load_source_texts(input_path: Path) -> dict[tuple[int, str, int], str]:
    result: dict[tuple[int, str, int], str] = {}
    with input_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            admission = json.loads(line)
            for module, table, field in (
                ("mimic_iv_ed", "triage", "chiefcomplaint"),
                ("mimic_iv_note", "radiology", "text"),
            ):
                for index, row in enumerate(admission[module].get(table, [])):
                    result[(line_number, f"{module}.{table}", index)] = str(
                        row.get(field) or ""
                    )
    return result


def _patient_allocation(
    document_rows: dict[str, dict[str, Any]], calibration_documents: int
) -> set[str]:
    if calibration_documents <= 0:
        raise ValueError("CALIBRATION_DOCUMENT_COUNT_INVALID")
    if calibration_documents % 2:
        raise ValueError("CALIBRATION_SOURCE_BALANCE_REQUIRES_EVEN_DOCUMENT_COUNT")
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in document_rows.values():
        groups[row["subject_id"]].append(row)
    source_target = calibration_documents // 2
    radiology_strata = sorted(
        {
            row["pilot_stratum"]
            for row in document_rows.values()
            if row["source_table"] == "note.radiology"
        }
    )
    stratum_bit = {name: 1 << index for index, name in enumerate(radiology_strata)}
    subject_order = sorted(
        groups,
        key=lambda subject: _sha256_text(f"{ALLOCATION_SEED}\x1f{subject}"),
    )
    states: dict[tuple[int, int, int], tuple[str, ...]] = {(0, 0, 0): ()}
    for subject in subject_order:
        values = groups[subject]
        document_count = len(values)
        ed_count = sum(row["source_table"] == "ed.triage" for row in values)
        mask = 0
        for row in values:
            mask |= stratum_bit.get(row["pilot_stratum"], 0)
        additions: dict[tuple[int, int, int], tuple[str, ...]] = {}
        for (total, ed_total, current_mask), selected in list(states.items()):
            key = (
                total + document_count,
                ed_total + ed_count,
                current_mask | mask,
            )
            if (
                key[0] <= calibration_documents
                and key[1] <= source_target
                and key not in states
                and key not in additions
            ):
                additions[key] = selected + (subject,)
        states.update(additions)
    candidates = [
        (key, selected)
        for key, selected in states.items()
        if key[0] == calibration_documents and key[1] == source_target
    ]
    if not candidates:
        raise ValueError(
            "PATIENT_ISOLATED_EXACT_ALLOCATION_UNAVAILABLE: "
            f"documents={calibration_documents}, ed={source_target}"
        )

    maximum_coverage = max(state[2].bit_count() for state, _ in candidates)
    if maximum_coverage != len(radiology_strata):
        raise ValueError(
            "PATIENT_ISOLATED_STRATUM_COVERAGE_UNAVAILABLE: "
            f"covered={maximum_coverage}, required={len(radiology_strata)}"
        )
    coverage_candidates = [
        item for item in candidates if item[0][2].bit_count() == maximum_coverage
    ]
    maximum_subjects = max(len(subjects) for _, subjects in coverage_candidates)
    diversity_candidates = [
        item for item in coverage_candidates if len(item[1]) == maximum_subjects
    ]
    _, selected_subjects = min(
        diversity_candidates,
        key=lambda item: _sha256_text("|".join(item[1])),
    )
    return set(selected_subjects)


def _source_key(row: dict[str, Any]) -> tuple[int, str, int]:
    return (
        row["jsonl_line_number"],
        f"{row['source_module']}.{row['source_table'].split('.', 1)[1]}",
        row["source_array_index"],
    )


def _task(
    row: dict[str, Any],
    section_text: str,
    *,
    partition: str,
    annotator_slot: str | None,
    release_status: str,
) -> dict[str, Any]:
    annotation_unit_id = _stable_id("aunit", row["manifest_row_id"])
    slot = annotator_slot or "locked"
    return {
        "package_schema_version": ANNOTATION_PACKAGE_VERSION,
        "annotation_protocol_version": ANNOTATION_PROTOCOL_VERSION,
        "task_id": _stable_id("atask", annotation_unit_id, slot),
        "annotation_unit_id": annotation_unit_id,
        "annotator_slot": annotator_slot,
        "partition": partition,
        "release_status": release_status,
        "manifest_row_id": row["manifest_row_id"],
        "document_id": row["document_id"],
        "section_id": row["section_id"],
        "source_table": row["source_table"],
        "note_type": row["note_type"],
        "section_name": row["section_name"],
        "event_time": row["event_time"],
        "available_time": row["available_time"],
        "evidence_phase": row["evidence_phase"],
        "section_text": section_text,
        "section_text_sha256": row["span_sha256"],
        "annotation": {
            "schema_version": SECTION_ANNOTATION_SCHEMA_VERSION,
            "manifest_row_id": row["manifest_row_id"],
            "document_id": row["document_id"],
            "section_id": row["section_id"],
            "section_text_sha256": row["span_sha256"],
            "mentions": [],
            "relations": [],
        },
    }


def prepare_annotation_package(
    input_path: Path,
    manifest_path: Path,
    output_directory: Path,
    *,
    calibration_documents: int = 50,
) -> dict[str, Any]:
    input_path = Path(input_path).resolve()
    manifest_path = Path(manifest_path).resolve()
    output_directory = Path(output_directory).resolve()
    if output_directory.exists():
        raise FileExistsError(f"output directory already exists: {output_directory}")
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(
            prefix=f".{output_directory.name}.", dir=output_directory.parent
        )
    )
    try:
        pilot_rows = [
            row
            for row in pq.read_table(manifest_path).to_pylist()
            if row["inclusion_status"] == "included"
            and row["pilot_document_selected"]
        ]
        document_rows: dict[str, dict[str, Any]] = {}
        text_unit_counts: Counter[str] = Counter()
        for row in pilot_rows:
            document_rows.setdefault(row["document_id"], row)
            text_unit_counts[row["document_id"]] += 1
        calibration_subjects = _patient_allocation(
            document_rows, calibration_documents
        )
        input_manifest_sha256 = _sha256_file(manifest_path)
        allocation_rows: list[dict[str, Any]] = []
        for document_id, row in document_rows.items():
            partition = (
                "calibration"
                if row["subject_id"] in calibration_subjects
                else "evaluation"
            )
            allocation_rows.append(
                {
                    "schema_version": ANNOTATION_ALLOCATION_SCHEMA_VERSION,
                    "allocation_id": _stable_id(
                        "alloc", input_manifest_sha256, document_id, partition
                    ),
                    "document_id": document_id,
                    "subject_id": row["subject_id"],
                    "hadm_id": row["hadm_id"],
                    "split_group_id": row["subject_id"],
                    "source_table": row["source_table"],
                    "note_type": row["note_type"],
                    "pilot_stratum": row["pilot_stratum"],
                    "text_unit_count": text_unit_counts[document_id],
                    "partition": partition,
                    "partition_status": (
                        "open_for_annotation"
                        if partition == "calibration"
                        else "blocked_pending_calibration"
                    ),
                    "allocation_reason": "patient_isolated_exact_source_balanced_stratum_covering",
                    "allocation_rank": 0,
                    "input_manifest_sha256": input_manifest_sha256,
                    "annotation_protocol_version": ANNOTATION_PROTOCOL_VERSION,
                }
            )
        allocation_rows.sort(
            key=lambda row: (
                row["partition"],
                _sha256_text(f"{ALLOCATION_SEED}\x1f{row['document_id']}"),
            )
        )
        for rank, row in enumerate(allocation_rows, start=1):
            row["allocation_rank"] = rank
        allocation_by_document = {
            row["document_id"]: row for row in allocation_rows
        }

        (temporary / "allocation").mkdir()
        (temporary / "calibration" / "annotator_a").mkdir(parents=True)
        (temporary / "calibration" / "annotator_b").mkdir(parents=True)
        (temporary / "evaluation").mkdir()
        (temporary / "decisions").mkdir()
        (temporary / "annotations" / "annotator_a").mkdir(parents=True)
        (temporary / "annotations" / "annotator_b").mkdir(parents=True)
        (temporary / "annotations" / "adjudicated").mkdir(parents=True)
        allocation_path = temporary / "allocation" / "annotation_allocation.parquet"
        pq.write_table(
            pa.Table.from_pylist(
                allocation_rows, schema=ANNOTATION_ALLOCATION_ARROW_SCHEMA
            ),
            allocation_path,
            compression="zstd",
            use_dictionary=True,
            write_statistics=True,
        )

        source_texts = _load_source_texts(input_path)
        validator = SectionAnnotationValidator()
        tasks: dict[str, list[dict[str, Any]]] = {
            "annotator_a": [],
            "annotator_b": [],
            "evaluation": [],
        }
        for row in pilot_rows:
            source_text = source_texts[_source_key(row)]
            section_text = source_text[row["span_start"] : row["span_end"]]
            if _sha256_text(section_text) != row["span_sha256"]:
                raise ValueError(f"PACKAGE_SOURCE_SPAN_MISMATCH: {row['manifest_row_id']}")
            partition = allocation_by_document[row["document_id"]]["partition"]
            if partition == "calibration":
                for slot in ("annotator_a", "annotator_b"):
                    task = _task(
                        row,
                        section_text,
                        partition=partition,
                        annotator_slot=slot,
                        release_status="released",
                    )
                    validator.validate(task["annotation"], row, section_text)
                    tasks[slot].append(task)
            else:
                task = _task(
                    row,
                    section_text,
                    partition=partition,
                    annotator_slot=None,
                    release_status="blocked_pending_calibration",
                )
                validator.validate(task["annotation"], row, section_text)
                tasks["evaluation"].append(task)
        for slot in ("annotator_a", "annotator_b"):
            tasks[slot].sort(
                key=lambda task: _sha256_text(
                    f"{ALLOCATION_SEED}\x1f{slot}\x1f{task['annotation_unit_id']}"
                )
            )
        tasks["evaluation"].sort(
            key=lambda task: _sha256_text(
                f"{ALLOCATION_SEED}\x1fevaluation\x1f{task['annotation_unit_id']}"
            )
        )
        a_path = temporary / "calibration" / "annotator_a" / "tasks.jsonl"
        b_path = temporary / "calibration" / "annotator_b" / "tasks.jsonl"
        evaluation_path = temporary / "evaluation" / "tasks.locked.jsonl"
        _jsonl_dump(a_path, tasks["annotator_a"])
        _jsonl_dump(b_path, tasks["annotator_b"])
        _jsonl_dump(evaluation_path, tasks["evaluation"])
        decision_paths = {
            "decisions/annotator_a.jsonl": temporary / "decisions" / "annotator_a.jsonl",
            "decisions/annotator_b.jsonl": temporary / "decisions" / "annotator_b.jsonl",
            "decisions/adjudication.jsonl": temporary / "decisions" / "adjudication.jsonl",
        }
        for path in decision_paths.values():
            path.write_text("", encoding="utf-8")

        calibration_allocations = [
            row for row in allocation_rows if row["partition"] == "calibration"
        ]
        evaluation_allocations = [
            row for row in allocation_rows if row["partition"] == "evaluation"
        ]
        summary = {
            "schema_version": ANNOTATION_PACKAGE_VERSION,
            "allocation": {
                "pilot_documents": len(allocation_rows),
                "calibration_documents": len(calibration_allocations),
                "evaluation_documents": len(evaluation_allocations),
                "calibration_subjects": len(calibration_subjects),
                "evaluation_subjects": len(
                    {row["subject_id"] for row in evaluation_allocations}
                ),
                "calibration_source_counts": dict(
                    sorted(Counter(row["source_table"] for row in calibration_allocations).items())
                ),
                "evaluation_source_counts": dict(
                    sorted(Counter(row["source_table"] for row in evaluation_allocations).items())
                ),
                "calibration_stratum_counts": dict(
                    sorted(Counter(row["pilot_stratum"] for row in calibration_allocations).items())
                ),
            },
            "tasks": {
                "annotator_a_calibration": len(tasks["annotator_a"]),
                "annotator_b_calibration": len(tasks["annotator_b"]),
                "evaluation_locked": len(tasks["evaluation"]),
            },
            "restricted_text": {
                "present_in_local_task_files": True,
                "git_tracking_allowed": False,
            },
            "model_calls": 0,
            "human_decisions": 0,
        }
        summary_path = temporary / "allocation" / "annotation_package_summary.json"
        _json_dump(summary_path, summary)
        output_hashes = {
            "allocation/annotation_allocation.parquet": _sha256_file(allocation_path),
            "allocation/annotation_package_summary.json": _sha256_file(summary_path),
            "calibration/annotator_a/tasks.jsonl": _sha256_file(a_path),
            "calibration/annotator_b/tasks.jsonl": _sha256_file(b_path),
            "evaluation/tasks.locked.jsonl": _sha256_file(evaluation_path),
            **{
                relative: _sha256_file(path)
                for relative, path in decision_paths.items()
            },
        }
        run_manifest = {
            "schema_version": ANNOTATION_PACKAGE_VERSION,
            "run_id": _stable_id(
                "arun",
                _sha256_file(input_path),
                input_manifest_sha256,
                calibration_documents,
                ALLOCATION_SEED,
            ),
            "input": {
                "source_filename": input_path.name,
                "source_sha256": _sha256_file(input_path),
                "manifest_filename": manifest_path.name,
                "manifest_sha256": input_manifest_sha256,
            },
            "configuration": {
                "calibration_documents": calibration_documents,
                "evaluation_documents": len(document_rows) - calibration_documents,
                "allocation_seed": ALLOCATION_SEED,
                "patient_isolation": True,
                "annotation_protocol_version": ANNOTATION_PROTOCOL_VERSION,
            },
            "outputs": output_hashes,
            "model": {"calls": 0, "provider": None, "name": None},
        }
        _json_dump(temporary / "run_manifest.json", run_manifest)
        temporary.replace(output_directory)
        return run_manifest
    except Exception:
        resolved_temporary = temporary.resolve()
        if output_directory.parent.resolve() in resolved_temporary.parents:
            shutil.rmtree(resolved_temporary, ignore_errors=True)
        raise
