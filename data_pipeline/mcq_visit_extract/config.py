"""Runtime knobs for resumable visit extraction."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VisitExtractConfig:
    data_root: Path
    output_dir: Path
    sample_size: int = 10_000
    shard_size: int = 1_000
    development_percent: int = 20
    sample_pool: str = "development"
    duckdb_threads: int = 4
    duckdb_memory_limit: str = "12GB"
    funnel_shard_size: int = 5_000

    def validate(self) -> None:
        if self.sample_size <= 0:
            raise ValueError("sample_size must be positive")
        if self.shard_size <= 0:
            raise ValueError("shard_size must be positive")
        if self.funnel_shard_size <= 0:
            raise ValueError("funnel_shard_size must be positive")
        if self.duckdb_threads <= 0:
            raise ValueError("duckdb_threads must be positive")
        if not re.fullmatch(r"[1-9][0-9]*(MB|GB)", self.duckdb_memory_limit):
            raise ValueError("duckdb_memory_limit must look like 512MB or 4GB")
        if not 1 <= self.development_percent <= 99:
            raise ValueError("development_percent must be between 1 and 99")
        if self.sample_pool not in {"development", "all"}:
            raise ValueError("sample_pool must be development or all")
        if not self.data_root.exists():
            raise ValueError(f"data_root does not exist: {self.data_root}")
