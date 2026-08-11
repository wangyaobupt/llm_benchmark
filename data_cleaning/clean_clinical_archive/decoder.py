"""Shared dictionary-decoding core for raw and clinical-readable archives."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

import duckdb


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


DictionaryRows = dict[tuple[str, ...], dict[str, Any]]
DictionaryIndex = dict[str, DictionaryRows]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _clean_key_component(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _dictionary_key(
    entry: dict[str, Any],
    key_fields: tuple[str, ...],
    dictionary_name: str,
    row_index: int,
) -> tuple[str, ...]:
    values = tuple(_clean_key_component(entry.get(field)) for field in key_fields)
    if any(value is None for value in values):
        raise DecodeError(
            f"dictionary {dictionary_name} row {row_index} has an incomplete key: "
            + ", ".join(
                f"{field}={value!r}"
                for field, value in zip(key_fields, values)
            )
        )
    return tuple(value for value in values if value is not None)


def _source_key(
    row: dict[str, Any],
    rule: DecodeRule,
    record_index: int,
    row_index: int,
) -> tuple[str, ...] | None:
    values = tuple(_clean_key_component(row.get(field)) for field in rule.key_fields)
    present = tuple(value is not None for value in values)
    if not any(present):
        return None
    if not all(present):
        joined = ", ".join(
            f"{field}={value!r}"
            for field, value in zip(rule.key_fields, values)
        )
        raise DecodeError(
            f"partial dictionary key at record {record_index} "
            f"{rule.path}[{row_index}]: {joined}"
        )
    return tuple(value for value in values if value is not None)


def _index_dictionary_rows(
    dictionary_name: str,
    key_fields: tuple[str, ...],
    values: list[dict[str, Any]],
) -> DictionaryRows:
    rows: DictionaryRows = {}
    for row_index, entry in enumerate(values):
        if not isinstance(entry, dict):
            raise DecodeError(
                f"dictionary {dictionary_name} row {row_index} is not an object"
            )
        key = _dictionary_key(entry, key_fields, dictionary_name, row_index)
        if key in rows:
            raise DecodeError(
                f"duplicate key {key} in dictionary {dictionary_name}"
            )
        rows[key] = entry
    return rows


def load_json_dictionaries(
    dictionary_directory: Path,
) -> tuple[DictionaryIndex, dict[str, dict[str, Any]]]:
    if not dictionary_directory.is_dir():
        raise FileNotFoundError(
            f"dictionary directory does not exist: {dictionary_directory}"
        )

    dictionaries: DictionaryIndex = {}
    files: dict[str, dict[str, Any]] = {}
    for dictionary_name, key_fields in DICTIONARY_KEYS.items():
        path = dictionary_directory / f"{dictionary_name}.json"
        if not path.is_file():
            raise FileNotFoundError(f"dictionary JSON does not exist: {path}")
        try:
            values = json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            raise DecodeError(f"invalid dictionary JSON {path}: {exc}") from exc
        if not isinstance(values, list):
            raise DecodeError(f"dictionary {dictionary_name} root must be an array")
        rows = _index_dictionary_rows(dictionary_name, key_fields, values)
        dictionaries[dictionary_name] = rows
        files[dictionary_name] = {
            "path": path.resolve().as_posix(),
            "rows": len(rows),
            "bytes": path.stat().st_size,
            "sha256": file_sha256(path),
        }
    return dictionaries, files


def load_duckdb_dictionaries(database_path: Path) -> DictionaryIndex:
    if not database_path.is_file():
        raise FileNotFoundError(
            f"dictionary database does not exist: {database_path}"
        )
    dictionaries: DictionaryIndex = {}
    connection = duckdb.connect(str(database_path), read_only=True)
    try:
        for dictionary_name, key_fields in DICTIONARY_KEYS.items():
            cursor = connection.execute(f'SELECT * FROM "{dictionary_name}"')
            columns = [column[0] for column in cursor.description]
            values = [dict(zip(columns, row)) for row in cursor.fetchall()]
            dictionaries[dictionary_name] = _index_dictionary_rows(
                dictionary_name, key_fields, values
            )
    finally:
        connection.close()
    return dictionaries


def _rows_for_rule(
    record: dict[str, Any], rule: DecodeRule, record_index: int
) -> list[dict[str, Any]]:
    group = record.get(rule.group)
    if not isinstance(group, dict):
        raise DecodeError(f"record {record_index} missing object {rule.group}")
    rows = group.get(rule.table)
    if not isinstance(rows, list):
        raise DecodeError(f"record {record_index} missing array {rule.path}")
    if any(not isinstance(row, dict) for row in rows):
        raise DecodeError(
            f"record {record_index} has non-object row in {rule.path}"
        )
    return rows


def decode_record(
    record: dict[str, Any],
    dictionaries: DictionaryIndex,
    record_index: int,
    decoded_counts: Counter[str],
    null_key_counts: Counter[str],
) -> None:
    if not isinstance(record, dict):
        raise DecodeError(f"record {record_index} is not an object")
    for rule in DECODE_RULES:
        dictionary = dictionaries[rule.dictionary]
        for row_index, row in enumerate(
            _rows_for_rule(record, rule, record_index)
        ):
            if rule.decoded_field in row:
                raise DecodeError(
                    f"record {record_index} {rule.path}[{row_index}] already contains "
                    f"{rule.decoded_field}"
                )
            key = _source_key(row, rule, record_index, row_index)
            if key is None:
                null_key_counts[rule.path] += 1
                continue
            entry = dictionary.get(key)
            if entry is None:
                joined = ", ".join(
                    f"{field}={value!r}"
                    for field, value in zip(rule.key_fields, key)
                )
                raise DecodeError(
                    f"unresolved code at record {record_index} "
                    f"{rule.path}[{row_index}]: {joined} in {rule.dictionary}"
                )
            if rule.dictionary == "d_items" and _clean_key_component(
                entry.get("linksto")
            ) != rule.table:
                raise DecodeError(
                    f"dictionary table mismatch at record {record_index} "
                    f"{rule.path}[{row_index}]: itemid={key[0]!r} links to "
                    f"{entry.get('linksto')!r}, not {rule.table!r}"
                )
            row[rule.decoded_field] = {
                "source_dictionary": rule.dictionary,
                **entry,
            }
            decoded_counts[rule.path] += 1


def build_decode_report(
    record_count: int,
    decoded_counts: Counter[str],
    null_key_counts: Counter[str],
) -> dict[str, Any]:
    return {
        "records": record_count,
        "decoded_total": sum(decoded_counts.values()),
        "decoded_by_path": dict(sorted(decoded_counts.items())),
        "null_keys_by_path": dict(sorted(null_key_counts.items())),
        "unresolved_total": 0,
    }


def decode_records(
    records: list[dict[str, Any]], dictionaries: DictionaryIndex
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    decoded_records = deepcopy(records)
    decoded_counts: Counter[str] = Counter()
    null_key_counts: Counter[str] = Counter()
    for record_index, record in enumerate(decoded_records):
        decode_record(
            record,
            dictionaries,
            record_index,
            decoded_counts,
            null_key_counts,
        )
    return decoded_records, build_decode_report(
        len(decoded_records), decoded_counts, null_key_counts
    )


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


__all__ = [
    "DECODE_RULES",
    "DICTIONARY_KEYS",
    "DecodeError",
    "DictionaryIndex",
    "build_decode_report",
    "decode_record",
    "decode_records",
    "file_sha256",
    "load_duckdb_dictionaries",
    "load_json_dictionaries",
    "strip_decoded_fields",
]
