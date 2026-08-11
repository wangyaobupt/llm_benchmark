"""Compatibility CLI for dictionary-only archive decoding.

The decoding rules and implementation live in
``data_pipeline.clean_clinical_archive.decoder`` so this dictionary-only entry point and
the combined clinical-readable pipeline cannot diverge.
"""

from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path
from typing import Any

from data_pipeline.clean_clinical_archive.decoder import (
    DecodeError,
    DictionaryIndex,
    build_decode_report,
    decode_record,
    decode_records,
    load_duckdb_dictionaries,
    strip_decoded_fields,
)


DEFAULT_DICTIONARY_DB = Path(
    "D:/Projects/llm_benchmark/data/解析/mimic_dictionaries.duckdb"
)


def _input_format(input_path: Path) -> str:
    with input_path.open(encoding="utf-8-sig") as source:
        while character := source.read(1):
            if character.isspace():
                continue
            if character == "[":
                return "json_array"
            if character == "{":
                return "jsonl"
            raise DecodeError(
                "input must begin with a JSON array or JSON object, "
                f"got {character!r}"
            )
    raise DecodeError("input is empty")


def _decode_json_array(
    input_path: Path,
    partial_path: Path,
    dictionaries: DictionaryIndex,
) -> dict[str, Any]:
    original = json.loads(input_path.read_text(encoding="utf-8-sig"))
    if not isinstance(original, list):
        raise DecodeError("JSON array input root must be an array")
    decoded, report = decode_records(original, dictionaries)
    if strip_decoded_fields(decoded) != original:
        raise DecodeError("decoded output changed original fields")
    partial_path.write_text(
        json.dumps(decoded, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return report


def _decode_jsonl(
    input_path: Path,
    partial_path: Path,
    dictionaries: DictionaryIndex,
) -> dict[str, Any]:
    decoded_counts: Counter[str] = Counter()
    null_key_counts: Counter[str] = Counter()
    record_count = 0
    with input_path.open(encoding="utf-8-sig") as source, partial_path.open(
        "x", encoding="utf-8", newline="\n"
    ) as output:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                raise DecodeError(f"input line {line_number} is empty")
            try:
                original = json.loads(line)
            except json.JSONDecodeError as exc:
                raise DecodeError(
                    f"invalid JSON at input line {line_number}: {exc}"
                ) from exc
            decoded = deepcopy(original)
            decode_record(
                decoded,
                dictionaries,
                record_count,
                decoded_counts,
                null_key_counts,
            )
            if strip_decoded_fields(decoded) != original:
                raise DecodeError(
                    "decoded output changed original fields at input line "
                    f"{line_number}"
                )
            output.write(
                json.dumps(decoded, ensure_ascii=False, separators=(",", ":"))
                + "\n"
            )
            record_count += 1
    return build_decode_report(
        record_count, decoded_counts, null_key_counts
    )


def decode_file(
    input_path: Path, output_path: Path, database_path: Path
) -> dict[str, Any]:
    if not input_path.is_file():
        raise FileNotFoundError(f"input JSON/JSONL does not exist: {input_path}")
    if output_path.exists():
        raise FileExistsError(f"output already exists: {output_path}")
    input_format = _input_format(input_path)
    dictionaries = load_duckdb_dictionaries(database_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    partial = output_path.with_suffix(output_path.suffix + ".partial")
    if partial.exists():
        raise FileExistsError(f"partial output already exists: {partial}")
    try:
        if input_format == "json_array":
            report = _decode_json_array(input_path, partial, dictionaries)
        else:
            report = _decode_jsonl(input_path, partial, dictionaries)
        partial.replace(output_path)
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    report.update(
        {
            "input_path": input_path.resolve().as_posix(),
            "output_path": output_path.resolve().as_posix(),
            "dictionary_database": database_path.resolve().as_posix(),
            "input_format": input_format,
            "output_format": input_format,
            "output_bytes": output_path.stat().st_size,
        }
    )
    return report


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Add auditable MIMIC-IV dictionary decodings to raw admission "
            "JSON or JSONL"
        )
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--dictionary-db", type=Path, default=DEFAULT_DICTIONARY_DB
    )
    return parser


def main() -> None:
    args = create_parser().parse_args()
    report = decode_file(args.input, args.output, args.dictionary_db)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()


__all__ = [
    "DecodeError",
    "decode_file",
    "decode_records",
    "strip_decoded_fields",
]
