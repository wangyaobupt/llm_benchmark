"""One-pass dictionary decoding and POE parsing for admission JSONL."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from .decoder import (
    DecodeError,
    DictionaryIndex,
    decode_record,
    file_sha256,
    load_json_dictionaries,
    strip_decoded_fields,
)
from .poe import OUTPUT_SCHEMA as POE_OUTPUT_SCHEMA
from .poe import PoeTimelineError, parse_admission


INPUT_SCHEMA = {"name": "mimic_admission_raw", "version": "1.0.0"}
OUTPUT_SCHEMA = {
    "name": "mimic_admission_clinical_readable",
    "version": "1.0.0",
}
INPUT_TOP_LEVEL_FIELDS = (
    "schema",
    "subject_id",
    "hadm_id",
    "mimic_iv_hosp",
    "mimic_iv_icu",
    "mimic_iv_ed",
    "mimic_iv_note",
)
DEFAULT_DICTIONARY_DIRECTORY = Path(__file__).resolve().parent / "dictionaries"


class ClinicalReadableArchiveError(ValueError):
    """Raised when the clinical-readable contract cannot be satisfied."""


def validate_input_record(record: dict[str, Any], record_index: int) -> None:
    if not isinstance(record, dict):
        raise ClinicalReadableArchiveError(
            f"record {record_index} is not an object"
        )
    if tuple(record) != INPUT_TOP_LEVEL_FIELDS:
        raise ClinicalReadableArchiveError(
            f"record {record_index} top-level schema drift: "
            f"expected {INPUT_TOP_LEVEL_FIELDS}, got {tuple(record)}"
        )
    if record.get("schema") != INPUT_SCHEMA:
        raise ClinicalReadableArchiveError(
            f"record {record_index} schema identity mismatch: "
            f"expected {INPUT_SCHEMA}, got {record.get('schema')!r}"
        )
    if not record.get("subject_id") or not record.get("hadm_id"):
        raise ClinicalReadableArchiveError(
            f"record {record_index} subject_id and hadm_id are required"
        )
    for group_name in (
        "mimic_iv_hosp",
        "mimic_iv_icu",
        "mimic_iv_ed",
        "mimic_iv_note",
    ):
        if not isinstance(record.get(group_name), dict):
            raise ClinicalReadableArchiveError(
                f"record {record_index} missing object {group_name}"
            )


def restore_source_record(record: dict[str, Any]) -> dict[str, Any]:
    restored = strip_decoded_fields(deepcopy(record))
    source_schema = restored.pop("source_schema", None)
    if source_schema is None:
        raise ClinicalReadableArchiveError(
            "clinical-readable record is missing source_schema"
        )
    hosp = restored.get("mimic_iv_hosp")
    if isinstance(hosp, dict):
        hosp.pop("poe_timeline", None)
    source_items = {
        key: value
        for key, value in restored.items()
        if key != "schema"
    }
    return {"schema": source_schema, **source_items}


def _prepare_record(
    original: dict[str, Any],
    dictionaries: DictionaryIndex,
    record_index: int,
    decoded_counts: Counter[str],
    null_key_counts: Counter[str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    validate_input_record(original, record_index)
    prepared = deepcopy(original)
    try:
        decode_record(
            prepared,
            dictionaries,
            record_index,
            decoded_counts,
            null_key_counts,
        )
        events = parse_admission(prepared)
    except (DecodeError, PoeTimelineError) as exc:
        raise ClinicalReadableArchiveError(
            f"record {record_index} enrichment failed: {exc}"
        ) from exc
    prepared["mimic_iv_hosp"]["poe_timeline"] = events
    source_schema = deepcopy(prepared["schema"])
    prepared = {
        "schema": deepcopy(OUTPUT_SCHEMA),
        "source_schema": source_schema,
        **{
            key: value
            for key, value in prepared.items()
            if key != "schema"
        },
    }
    if restore_source_record(prepared) != original:
        raise ClinicalReadableArchiveError(
            f"enrichment changed original fields at record {record_index}"
        )
    return prepared, events


def _validate_paths(input_path: Path, output_path: Path, report_path: Path) -> None:
    resolved = {
        "input": input_path.resolve(),
        "output": output_path.resolve(),
        "report": report_path.resolve(),
    }
    if len(set(resolved.values())) != 3:
        raise ClinicalReadableArchiveError(
            "input, output, and report paths must be different"
        )
    if not input_path.is_file():
        raise FileNotFoundError(f"input JSONL does not exist: {input_path}")
    if output_path.exists():
        raise FileExistsError(f"output already exists: {output_path}")
    if report_path.exists():
        raise FileExistsError(f"report already exists: {report_path}")


def prepare_archive(
    input_path: Path,
    output_path: Path,
    report_path: Path,
    dictionary_directory: Path = DEFAULT_DICTIONARY_DIRECTORY,
    *,
    limit: int | None = None,
) -> dict[str, Any]:
    """Stream raw admissions into a schema-identified readable JSONL."""
    if limit is not None and limit <= 0:
        raise ClinicalReadableArchiveError("limit must be a positive integer")
    _validate_paths(input_path, output_path, report_path)
    try:
        dictionaries, dictionary_files = load_json_dictionaries(
            dictionary_directory
        )
    except (DecodeError, FileNotFoundError) as exc:
        raise ClinicalReadableArchiveError(str(exc)) from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    output_partial = output_path.with_suffix(output_path.suffix + ".partial")
    report_partial = report_path.with_suffix(report_path.suffix + ".partial")
    for partial in (output_partial, report_partial):
        if partial.exists():
            raise FileExistsError(f"partial output already exists: {partial}")

    decoded_counts: Counter[str] = Counter()
    null_key_counts: Counter[str] = Counter()
    action_counts: Counter[str] = Counter()
    quality_flag_counts: Counter[str] = Counter()
    admissions = 0
    poe_events = 0
    output_finalized = False

    try:
        with input_path.open(encoding="utf-8-sig") as source, output_partial.open(
            "x", encoding="utf-8", newline="\n"
        ) as output:
            for line_number, line in enumerate(source, 1):
                if limit is not None and admissions >= limit:
                    break
                if not line.strip():
                    raise ClinicalReadableArchiveError(
                        f"input line {line_number} is empty"
                    )
                try:
                    original = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ClinicalReadableArchiveError(
                        f"invalid JSON at input line {line_number}: {exc}"
                    ) from exc
                prepared, events = _prepare_record(
                    original,
                    dictionaries,
                    admissions,
                    decoded_counts,
                    null_key_counts,
                )
                output.write(
                    json.dumps(
                        prepared,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    + "\n"
                )
                admissions += 1
                poe_events += len(events)
                for event in events:
                    action_counts[str(event.get("action"))] += 1
                    for flag in event.get("quality_flags", []):
                        quality_flag_counts[str(flag)] += 1

        if admissions == 0:
            raise ClinicalReadableArchiveError("input contains no admission records")

        metrics: dict[str, Any] = {
            "schema": deepcopy(OUTPUT_SCHEMA),
            "source_schema": deepcopy(INPUT_SCHEMA),
            "poe_event_schema": POE_OUTPUT_SCHEMA,
            "input_path": input_path.resolve().as_posix(),
            "input_sha256": file_sha256(input_path),
            "output_path": output_path.resolve().as_posix(),
            "dictionary_directory": dictionary_directory.resolve().as_posix(),
            "dictionary_files": dictionary_files,
            "admissions": admissions,
            "dictionary_decoded_total": sum(decoded_counts.values()),
            "decoded_by_path": dict(sorted(decoded_counts.items())),
            "null_keys_by_path": dict(sorted(null_key_counts.items())),
            "unresolved_total": 0,
            "poe_events": poe_events,
            "poe_action_counts": dict(sorted(action_counts.items())),
            "poe_quality_flag_counts": dict(
                sorted(quality_flag_counts.items())
            ),
            "limit": limit,
            "output_bytes": output_partial.stat().st_size,
            "output_sha256": file_sha256(output_partial),
        }
        report_partial.write_text(
            json.dumps(metrics, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        json.loads(report_partial.read_text(encoding="utf-8"))
        output_partial.replace(output_path)
        output_finalized = True
        report_partial.replace(report_path)
        return metrics
    except Exception:
        output_partial.unlink(missing_ok=True)
        report_partial.unlink(missing_ok=True)
        if output_finalized:
            output_path.unlink(missing_ok=True)
        raise
