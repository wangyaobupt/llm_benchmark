"""Internal data models for the clinical event pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal


SourceRole = Literal["event", "enrichment", "context", "derived"]
Transformer = Callable[["SourceRow", "AdmissionContext"], list[dict[str, Any]]]


@dataclass(frozen=True)
class SourceSpec:
    module: str
    table: str
    role: SourceRole
    native_key_fields: tuple[str, ...]
    transformer_name: str | None = None

    @property
    def source_table(self) -> str:
        prefix = {
            "mimic_iv_hosp": "hosp",
            "mimic_iv_icu": "icu",
            "mimic_iv_ed": "ed",
            "mimic_iv_note": "note",
        }[self.module]
        return f"{prefix}.{self.table}"


@dataclass(frozen=True)
class SourceRow:
    spec: SourceSpec
    row: dict[str, Any]
    jsonl_line_number: int
    source_array_index: int
    subject_id: str
    hadm_id: str
    input_name: str
    source_row_id: str

    @property
    def raw_row_ref(self) -> str:
        return (
            f"{self.input_name}#L{self.jsonl_line_number}/"
            f"{self.spec.module}.{self.spec.table}[{self.source_array_index}]"
        )


@dataclass
class AdmissionContext:
    admission: dict[str, Any]
    source_rows: dict[tuple[str, str], list[SourceRow]]
    indexes: dict[str, Any]

    def rows(self, module: str, table: str) -> list[SourceRow]:
        return self.source_rows.get((module, table), [])
