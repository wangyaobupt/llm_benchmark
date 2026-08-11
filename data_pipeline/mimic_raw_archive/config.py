"""Configuration for sharded, resumable raw admission extraction."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass(frozen=True)
class RawArchiveConfig:
    data_root: Path = Path("D:/Projects/llm_benchmark/data/RawData")
    output_dir: Path = Path(
        "G:/Projects/llm_benchmark/data/validation/mimic-admission-raw-10000"
    )
    merged_path: Path = Path(
        "G:/Projects/llm_benchmark/data/validation/mimic-admission-raw-10000.jsonl"
    )
    sample_size: int = 10_000
    shard_size: int = 1_000
    workers: int = 2
    duckdb_threads: int = 4
    duckdb_memory_limit: str = "12GB"
    development_percent: int = 20
    selection_input: Path | None = None

    def validate(self) -> None:
        if self.sample_size <= 0:
            raise ValueError("sample_size must be positive")
        if self.shard_size <= 0:
            raise ValueError("shard_size must be positive")
        if self.workers <= 0 or self.duckdb_threads <= 0:
            raise ValueError("workers and duckdb_threads must be positive")
        if not re.fullmatch(r"[1-9][0-9]*(MB|GB)", self.duckdb_memory_limit):
            raise ValueError("duckdb_memory_limit must look like 512MB or 4GB")
        if not 1 <= self.development_percent <= 99:
            raise ValueError("development_percent must be between 1 and 99")
        if self.selection_input is not None and not self.selection_input.is_file():
            raise ValueError(f"selection_input does not exist: {self.selection_input}")
