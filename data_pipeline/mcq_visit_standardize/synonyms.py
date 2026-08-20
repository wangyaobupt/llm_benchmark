"""Load and compile reviewed symptom synonyms. Transform never invents aliases."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from data_pipeline.mcq_visit_extract.atomic import atomic_write_jsonl

from .mappings import SYMPTOM_ALIASES
from .text import lookup_key


def concept_id_from_standard(standard: str) -> str:
    key = lookup_key(standard) or "unknown"
    slug = re.sub(r"[^a-z0-9]+", "_", key).strip("_")
    return f"symptom:{slug or 'unknown'}"


def catalog_entries(
    extra: dict[str, tuple[str, str]] | None = None,
) -> list[dict[str, str]]:
    merged = dict(SYMPTOM_ALIASES)
    if extra:
        merged.update(extra)
    by_id: dict[str, dict[str, Any]] = {}
    for alias, (standard, concept_id) in merged.items():
        item = by_id.setdefault(
            concept_id,
            {"standard": standard, "concept_id": concept_id, "aliases": []},
        )
        item["aliases"].append(alias)
    return sorted(by_id.values(), key=lambda row: row["standard"].casefold())


def load_reviewed_maps(path: Path) -> dict[str, dict[str, tuple[str, str]]]:
    extra: dict[str, dict[str, tuple[str, str]]] = {}
    if not path.is_file():
        return extra
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            key = row.get("lookup_key") or lookup_key(row.get("source"))
            standard = row.get("standard")
            concept_id = row.get("concept_id")
            domain = str(row.get("domain") or "symptom")
            if key and standard and concept_id:
                extra.setdefault(domain, {})[str(key)] = (str(standard), str(concept_id))
    return extra


def load_reviewed_synonyms(path: Path) -> dict[str, tuple[str, str]]:
    return load_reviewed_maps(path).get("symptom", {})


def compile_table_from_decisions(decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for row in decisions:
        key = row.get("lookup_key")
        if not key:
            continue
        domain = str(row.get("domain") or "symptom")
        latest[(domain, str(key))] = row
    rows = []
    for key, row in sorted(latest.items()):
        if row.get("action") != "accept":
            continue
        rows.append(
            {
                "lookup_key": key[1],
                "source": row.get("source"),
                "standard": row.get("standard"),
                "concept_id": row.get("concept_id"),
                "domain": row.get("domain") or "symptom",
            }
        )
    return rows


def write_synonym_table(path: Path, rows: list[dict[str, Any]]) -> None:
    atomic_write_jsonl(path, rows)


def append_decision(path: Path, decision: dict[str, Any]) -> None:
    append_decisions(path, [decision])


def append_decisions(path: Path, decisions: list[dict[str, Any]]) -> None:
    if not decisions:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().isoformat(timespec="seconds")
    with path.open("a", encoding="utf-8") as handle:
        for decision in decisions:
            payload = dict(decision)
            payload.setdefault("decided_at", stamp)
            handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
        handle.flush()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows
