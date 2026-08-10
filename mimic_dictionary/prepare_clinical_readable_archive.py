"""Create a directly usable admission JSONL with dictionary labels and POE timelines.

The source archive remains traceable: source codes and source rows are preserved,
while deterministic dictionary payloads and parsed provider-order events are added.
"""

from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from poe_timeline import OUTPUT_SCHEMA as POE_OUTPUT_SCHEMA
from poe_timeline import parse_admission
from poe_timeline.parser import PoeTimelineError

from .decode_archive import DECODE_RULES, DICTIONARY_KEYS, strip_decoded_fields


OUTPUT_SCHEMA = {
    "name": "mimic-admission-clinical-readable",
    "version": "1.0.0",
}

DEFAULT_DICTIONARY_DIRECTORY = Path(
    "D:/Projects/llm_benchmark/data/解析/json"
)


class ClinicalReadableArchiveError(ValueError):
    """Raised when a readable archive cannot be produced deterministically."""


def _normalize_key(values: tuple[Any, ...]) -> tuple[str, ...] | None:
    if any(value is None or str(value).strip() == "" for value in values):
        return None
    return tuple(str(value).strip() for value in values)


def load_json_dictionaries(
    dictionary_directory: Path,
) -> tuple[
    dict[str, dict[tuple[str, ...], dict[str, Any]]],
    dict[str, dict[str, Any]],
]:
    """Load and validate the five official dictionary JSON arrays once."""
    if not dictionary_directory.is_dir():
        raise FileNotFoundError(
            f"dictionary directory does not exist: {dictionary_directory}"
        )

    dictionaries: dict[str, dict[tuple[str, ...], dict[str, Any]]] = {}
    dictionary_files: dict[str, dict[str, Any]] = {}
    for dictionary_name, key_fields in DICTIONARY_KEYS.items():
        path = dictionary_directory / f"{dictionary_name}.json"
        if not path.is_file():
            raise FileNotFoundError(f"dictionary JSON does not exist: {path}")
        try:
            values = json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            raise ClinicalReadableArchiveError(
                f"invalid dictionary JSON {path}: {exc}"
            ) from exc
        if not isinstance(values, list):
            raise ClinicalReadableArchiveError(
                f"dictionary {dictionary_name} root must be an array"
            )

        rows: dict[tuple[str, ...], dict[str, Any]] = {}
        for row_index, entry in enumerate(values):
            if not isinstance(entry, dict):
                raise ClinicalReadableArchiveError(
                    f"dictionary {dictionary_name} row {row_index} is not an object"
                )
            key = _normalize_key(tuple(entry.get(field) for field in key_fields))
            if key is None:
                raise ClinicalReadableArchiveError(
                    f"empty key at dictionary {dictionary_name} row {row_index}"
                )
            if key in rows:
                raise ClinicalReadableArchiveError(
                    f"duplicate key {key} in dictionary {dictionary_name}"
                )
            rows[key] = entry

        dictionaries[dictionary_name] = rows
        dictionary_files[dictionary_name] = {
            "path": path.resolve().as_posix(),
            "rows": len(rows),
            "bytes": path.stat().st_size,
        }

    return dictionaries, dictionary_files


def _rows_for_rule(
    record: dict[str, Any], record_index: int, group_name: str, table_name: str
) -> list[dict[str, Any]]:
    group = record.get(group_name)
    if not isinstance(group, dict):
        raise ClinicalReadableArchiveError(
            f"record {record_index} missing object {group_name}"
        )
    rows = group.get(table_name)
    path = f"{group_name}.{table_name}"
    if not isinstance(rows, list):
        raise ClinicalReadableArchiveError(
            f"record {record_index} missing array {path}"
        )
    if any(not isinstance(row, dict) for row in rows):
        raise ClinicalReadableArchiveError(
            f"record {record_index} has non-object row in {path}"
        )
    return rows


def _decode_record(
    record: dict[str, Any],
    dictionaries: dict[str, dict[tuple[str, ...], dict[str, Any]]],
    record_index: int,
    decoded_counts: Counter[str],
    null_key_counts: Counter[str],
) -> None:
    for rule in DECODE_RULES:
        dictionary = dictionaries[rule.dictionary]
        rows = _rows_for_rule(record, record_index, rule.group, rule.table)
        for row_index, row in enumerate(rows):
            if rule.decoded_field in row:
                raise ClinicalReadableArchiveError(
                    f"record {record_index} {rule.path}[{row_index}] already contains "
                    f"{rule.decoded_field}"
                )
            key = _normalize_key(tuple(row.get(field) for field in rule.key_fields))
            if key is None:
                null_key_counts[rule.path] += 1
                continue
            entry = dictionary.get(key)
            if entry is None:
                joined = ", ".join(
                    f"{field}={value!r}"
                    for field, value in zip(rule.key_fields, key)
                )
                raise ClinicalReadableArchiveError(
                    f"unresolved code at record {record_index} "
                    f"{rule.path}[{row_index}]: {joined} in {rule.dictionary}"
                )
            if rule.dictionary == "d_items":
                linksto = _normalize_key((entry.get("linksto"),))
                if linksto != (rule.table,):
                    raise ClinicalReadableArchiveError(
                        f"dictionary table mismatch at record {record_index} "
                        f"{rule.path}[{row_index}]: itemid={key[0]!r} links to "
                        f"{entry.get('linksto')!r}, not {rule.table!r}"
                    )
            row[rule.decoded_field] = {
                "source_dictionary": rule.dictionary,
                **entry,
            }
            decoded_counts[rule.path] += 1


def _remove_enrichments(record: dict[str, Any]) -> dict[str, Any]:
    restored = strip_decoded_fields(record)
    hosp = restored.get("mimic_iv_hosp")
    if isinstance(hosp, dict):
        hosp.pop("poe_timeline", None)
    return restored


def _prepare_record(
    original: dict[str, Any],
    dictionaries: dict[str, dict[tuple[str, ...], dict[str, Any]]],
    record_index: int,
    decoded_counts: Counter[str],
    null_key_counts: Counter[str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not isinstance(original, dict):
        raise ClinicalReadableArchiveError(
            f"record {record_index} is not an object"
        )
    prepared = deepcopy(original)
    _decode_record(
        prepared,
        dictionaries,
        record_index,
        decoded_counts,
        null_key_counts,
    )

    hosp = prepared.get("mimic_iv_hosp")
    if not isinstance(hosp, dict):
        raise ClinicalReadableArchiveError(
            f"record {record_index} missing object mimic_iv_hosp"
        )
    if "poe_timeline" in hosp:
        raise ClinicalReadableArchiveError(
            f"record {record_index} already contains mimic_iv_hosp.poe_timeline"
        )
    try:
        events = parse_admission(prepared)
    except PoeTimelineError as exc:
        raise ClinicalReadableArchiveError(
            f"POE parsing failed at record {record_index}: {exc}"
        ) from exc
    hosp["poe_timeline"] = events

    if _remove_enrichments(deepcopy(prepared)) != original:
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
    """Stream raw admissions into an enriched, directly readable JSONL."""
    if limit is not None and limit <= 0:
        raise ClinicalReadableArchiveError("limit must be a positive integer")
    _validate_paths(input_path, output_path, report_path)
    dictionaries, dictionary_files = load_json_dictionaries(dictionary_directory)

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
            "schema": OUTPUT_SCHEMA,
            "poe_event_schema": POE_OUTPUT_SCHEMA,
            "input_path": input_path.resolve().as_posix(),
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Add all supported MIMIC dictionary decodings and a parsed POE "
            "timeline to admission-level raw JSONL records."
        )
    )
    parser.add_argument("input", type=Path, help="Admission-level raw JSONL")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--dictionary-dir",
        type=Path,
        default=DEFAULT_DICTIONARY_DIRECTORY,
        help="Directory containing the five official dictionary JSON arrays",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only process the first N admissions",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    metrics = prepare_archive(
        args.input,
        args.output,
        args.report,
        args.dictionary_dir,
        limit=args.limit,
    )
    print(
        f"processed {metrics['admissions']} admissions, decoded "
        f"{metrics['dictionary_decoded_total']} coded rows, and parsed "
        f"{metrics['poe_events']} POE events into {args.output}"
    )


if __name__ == "__main__":
    main()
