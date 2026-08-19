"""Build the W0 audit manifest without copying legacy data into the new chain."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "legacy-invalidation-manifest.json"

LEGACY_FILES = [
    ROOT / "data/phenotype/conditional_rules_development.jsonl",
    ROOT / "data/phenotype/conditional_rules_dedup.jsonl",
    ROOT / "data/phenotype/conditional_rules_converged.jsonl",
    ROOT / "data/phenotype/phenotype_manifest_development.json",
    ROOT / "data/phenotype/generation_formal_v2/questions_candidates.jsonl",
    ROOT / "data/phenotype/generation_formal_v2/questions_reviewed.jsonl",
    ROOT / "data/phenotype/generation_formal_v2/questions_gold.jsonl",
    ROOT / "versions/v1-template-stem/artifacts/investigation_selection/output/split/subject_split.parquet",
    ROOT / "versions/v1-template-stem/artifacts/investigation_selection/output/split/split_manifest.json",
    ROOT / "versions/v1-template-stem/artifacts/investigation_selection/output/development/run_manifest.json",
    ROOT / "versions/v1-template-stem/artifacts/investigation_selection/output/validated/validated_manifest.json",
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def read_jsonl_ids(path: Path) -> tuple[int, set[str], set[str], set[str]]:
    rows = 0
    candidates: set[str] = set()
    rules: set[str] = set()
    questions: set[str] = set()
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            rows += 1
            for key, target in (
                ("target_investigation_id", candidates),
                ("source_rule_id", rules),
                ("rule_id", rules),
                ("question_id", questions),
            ):
                value = row.get(key)
                if isinstance(value, str) and value:
                    target.add(value)
    return rows, candidates, rules, questions


def artifact_record(path: Path) -> dict[str, Any]:
    record: dict[str, Any] = {
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "exists": path.is_file(),
    }
    if not path.is_file():
        return record
    record.update({"bytes": path.stat().st_size, "sha256": sha256_file(path)})
    if path.suffix == ".jsonl":
        rows, candidates, rules, questions = read_jsonl_ids(path)
        record.update(
            {
                "rows": rows,
                "candidate_ids": sorted(candidates),
                "rule_ids": sorted(rules),
                "question_ids": sorted(questions),
            }
        )
    elif path.suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            record["declared_counts"] = payload.get("counts", {})
            record["status"] = payload.get("status")
    return record


def build() -> dict[str, Any]:
    artifacts = [artifact_record(path) for path in LEGACY_FILES]
    candidate_ids = sorted(
        {value for item in artifacts for value in item.get("candidate_ids", [])}
    )
    rule_ids = sorted({value for item in artifacts for value in item.get("rule_ids", [])})
    question_ids = sorted(
        {value for item in artifacts for value in item.get("question_ids", [])}
    )
    split_path = ROOT / "versions/v1-template-stem/artifacts/investigation_selection/output/split/subject_split.parquet"
    split_artifacts = []
    if split_path.is_file():
        split_artifacts.append(
            {
                "path": str(split_path.resolve()),
                "sha256": sha256_file(split_path),
                "status": "legacy_holdout_not_formal_final_test",
            }
        )
    return {
        "schema_version": "legacy-invalidation-manifest/1.0.0",
        "status": "active",
        "generated_by": "scripts/build_legacy_invalidation_manifest.py",
        "git_commit": git_head(),
        "scope": "W0 investigation-selection rebuild",
        "gold_count": 0,
        "invalidated_ids": {
            "candidate_ids": candidate_ids,
            "rule_ids": rule_ids,
            "question_ids": question_ids,
        },
        "reasons": {
            "candidate_ids": "invalidated_upstream_contract",
            "rule_ids": "invalidated_upstream_contract",
            "question_ids": "invalidated_upstream_contract",
            "legacy_split": "legacy_holdout_not_formal_final_test",
            "phenotype_formal_entrypoint": "legacy_phenotype_formal_generation_forbidden",
        },
        "historical_chain": {
            "formal_accepted_rules": 1584,
            "deduplicated_rules": 738,
            "converged_rules": 165,
            "candidate_questions": 134,
            "human_approved_gold": 0,
        },
        "legacy_split_artifacts": split_artifacts,
        "artifacts": artifacts,
    }


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(build(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(OUT)

