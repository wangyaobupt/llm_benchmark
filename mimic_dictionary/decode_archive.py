from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import duckdb


DEFAULT_DICTIONARY_DB = Path("D:/Projects/llm_benchmark/data/解析/mimic_dictionaries.duckdb")


class DecodeError(ValueError):
    """Raised when a coded source row cannot be decoded without guessing."""


@dataclass(frozen=True)
class DecodeRule:
    group: str
    table: str
    dictionary: str
    key_fields: tuple[str, ...]
    decoded_field: str

    @property
    def path(self) -> str:
        return f"{self.group}.{self.table}"


DECODE_RULES: tuple[DecodeRule, ...] = (
    DecodeRule(
        "mimic_iv_hosp", "labevents", "d_labitems", ("itemid",), "itemid_decoded"
    ),
    DecodeRule(
        "mimic_iv_hosp",
        "diagnoses_icd",
        "d_icd_diagnoses",
        ("icd_code", "icd_version"),
        "icd_decoded",
    ),
    DecodeRule(
        "mimic_iv_ed",
        "diagnosis",
        "d_icd_diagnoses",
        ("icd_code", "icd_version"),
        "icd_decoded",
    ),
    DecodeRule(
        "mimic_iv_hosp",
        "procedures_icd",
        "d_icd_procedures",
        ("icd_code", "icd_version"),
        "icd_decoded",
    ),
    DecodeRule(
        "mimic_iv_hosp", "hcpcsevents", "d_hcpcs", ("hcpcs_cd",), "hcpcs_cd_decoded"
    ),
    DecodeRule(
        "mimic_iv_icu", "datetimeevents", "d_items", ("itemid",), "itemid_decoded"
    ),
    DecodeRule(
        "mimic_iv_icu", "ingredientevents", "d_items", ("itemid",), "itemid_decoded"
    ),
    DecodeRule(
        "mimic_iv_icu", "inputevents", "d_items", ("itemid",), "itemid_decoded"
    ),
    DecodeRule(
        "mimic_iv_icu", "outputevents", "d_items", ("itemid",), "itemid_decoded"
    ),
    DecodeRule(
        "mimic_iv_icu", "procedureevents", "d_items", ("itemid",), "itemid_decoded"
    ),
)


DICTIONARY_KEYS: dict[str, tuple[str, ...]] = {
    "d_labitems": ("itemid",),
    "d_items": ("itemid",),
    "d_icd_diagnoses": ("icd_code", "icd_version"),
    "d_icd_procedures": ("icd_code", "icd_version"),
    "d_hcpcs": ("code",),
}


def _normalize_key(values: tuple[Any, ...]) -> tuple[str, ...] | None:
    if any(value is None or str(value).strip() == "" for value in values):
        return None
    return tuple(str(value).strip() for value in values)


def _load_dictionaries(database_path: Path) -> dict[str, dict[tuple[str, ...], dict[str, Any]]]:
    if not database_path.is_file():
        raise FileNotFoundError(f"dictionary database does not exist: {database_path}")
    dictionaries: dict[str, dict[tuple[str, ...], dict[str, Any]]] = {}
    connection = duckdb.connect(str(database_path), read_only=True)
    try:
        for table, key_fields in DICTIONARY_KEYS.items():
            cursor = connection.execute(f'SELECT * FROM "{table}"')
            columns = [column[0] for column in cursor.description]
            rows: dict[tuple[str, ...], dict[str, Any]] = {}
            for values in cursor.fetchall():
                entry = dict(zip(columns, values))
                key = _normalize_key(tuple(entry.get(field) for field in key_fields))
                if key is None:
                    raise DecodeError(f"dictionary {table} contains an empty key")
                if key in rows:
                    raise DecodeError(f"dictionary {table} contains duplicate key {key}")
                rows[key] = entry
            dictionaries[table] = rows
    finally:
        connection.close()
    return dictionaries


def _rows_for_rule(record: dict[str, Any], rule: DecodeRule, record_index: int) -> list[dict[str, Any]]:
    group = record.get(rule.group)
    if not isinstance(group, dict):
        raise DecodeError(f"record {record_index} missing object {rule.group}")
    rows = group.get(rule.table)
    if not isinstance(rows, list):
        raise DecodeError(f"record {record_index} missing array {rule.path}")
    if any(not isinstance(row, dict) for row in rows):
        raise DecodeError(f"record {record_index} has non-object row in {rule.path}")
    return rows


def decode_records(
    records: list[dict[str, Any]],
    dictionaries: dict[str, dict[tuple[str, ...], dict[str, Any]]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    decoded_records = deepcopy(records)
    decoded_counts: Counter[str] = Counter()
    null_key_counts: Counter[str] = Counter()

    for record_index, record in enumerate(decoded_records):
        if not isinstance(record, dict):
            raise DecodeError(f"record {record_index} is not an object")
        for rule in DECODE_RULES:
            dictionary = dictionaries[rule.dictionary]
            for row_index, row in enumerate(_rows_for_rule(record, rule, record_index)):
                if rule.decoded_field in row:
                    raise DecodeError(
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
                        f"{field}={value!r}" for field, value in zip(rule.key_fields, key)
                    )
                    raise DecodeError(
                        f"unresolved code at record {record_index} {rule.path}[{row_index}]: "
                        f"{joined} in {rule.dictionary}"
                    )
                row[rule.decoded_field] = {
                    "source_dictionary": rule.dictionary,
                    **entry,
                }
                decoded_counts[rule.path] += 1

    return decoded_records, {
        "records": len(decoded_records),
        "decoded_total": sum(decoded_counts.values()),
        "decoded_by_path": dict(sorted(decoded_counts.items())),
        "null_keys_by_path": dict(sorted(null_key_counts.items())),
        "unresolved_total": 0,
    }


def strip_decoded_fields(value: Any) -> Any:
    if isinstance(value, list):
        return [strip_decoded_fields(item) for item in value]
    if isinstance(value, dict):
        return {
            key: strip_decoded_fields(item)
            for key, item in value.items()
            if not key.endswith("_decoded")
        }
    return value


def decode_file(input_path: Path, output_path: Path, database_path: Path) -> dict[str, Any]:
    if not input_path.is_file():
        raise FileNotFoundError(f"input JSON does not exist: {input_path}")
    if output_path.exists():
        raise FileExistsError(f"output already exists: {output_path}")
    original = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(original, list):
        raise DecodeError("input JSON root must be an array")
    dictionaries = _load_dictionaries(database_path)
    decoded, report = decode_records(original, dictionaries)
    if strip_decoded_fields(decoded) != original:
        raise DecodeError("decoded output changed original fields")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    partial = output_path.with_suffix(output_path.suffix + ".partial")
    partial.write_text(
        json.dumps(decoded, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    json.loads(partial.read_text(encoding="utf-8"))
    partial.replace(output_path)
    report.update(
        {
            "input_path": input_path.resolve().as_posix(),
            "output_path": output_path.resolve().as_posix(),
            "dictionary_database": database_path.resolve().as_posix(),
            "output_bytes": output_path.stat().st_size,
        }
    )
    return report


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Add auditable MIMIC-IV dictionary decodings to a raw admission JSON array"
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dictionary-db", type=Path, default=DEFAULT_DICTIONARY_DB)
    return parser


def main() -> None:
    args = create_parser().parse_args()
    report = decode_file(args.input, args.output, args.dictionary_db)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
