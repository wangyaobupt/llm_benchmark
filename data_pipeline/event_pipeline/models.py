"""Internal data models for the clinical event pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal


SourceRole = Literal["event", "support", "context", "excluded"]
SourceOrigin = Literal["raw", "derived"]
IdentityStrategy = Literal[
    "native_key",
    "composite_key",
    "canonical_row_hash_with_occurrence",
]
Transformer = Callable[["SourceRow", "AdmissionContext"], list[dict[str, Any]]]


@dataclass(frozen=True)
class TimePolicy:
    policy_id: str
    event_time_rule: str
    available_time_rule: str
    recorded_time_rule: str
    missing_time_rule: str
    rationale: str


@dataclass(frozen=True)
class SourceSpec:
    module: str
    table: str
    origin: SourceOrigin
    role: SourceRole
    fact_owner: str | None
    supports: tuple[str, ...]
    identity_strategy: IdentityStrategy
    native_key_fields: tuple[str, ...]
    time_policy: str
    evidence_phase: str | None
    transformer_name: str | None
    inclusion_reason: str | None
    exclusion_reason: str | None
    required: bool = True

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
