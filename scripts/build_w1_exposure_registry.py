"""Build the W1 exposure registry and new subject split from approved sources."""

from __future__ import annotations

import hashlib
import json
import secrets
import sys
from pathlib import Path

import pandas as pd
import pyarrow.dataset as ds

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation_pipeline.governance import load_protocol_bundle
from evaluation_pipeline.subject_split.contract import build_subject_split


OUT = ROOT / "data/derived/investigation_selection/w1"
SECRET_PATH = ROOT / ".local/subject_ref_secret.bin"
OLD_SPLIT = ROOT / "versions/v1-template-stem/artifacts/investigation_selection/output/split/subject_split.parquet"
FORMAL_EVENTS = Path(
    r"G:\Projects\llm_benchmark\data\derived\coronary_all_three_modules_full"
    r"\event_pipeline\normalization\normalized_events.parquet"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_subjects() -> tuple[dict[str, set[str]], set[str]]:
    old = pd.read_parquet(OLD_SPLIT)
    by_role = {
        str(role): set(old.loc[old["role"] == role, "subject_id"].astype(str))
        for role in sorted(old["role"].unique())
    }
    source_subjects: set[str] = set()
    for batch in ds.dataset(FORMAL_EVENTS, format="parquet").scanner(
        columns=["subject_id"], batch_size=250_000
    ).to_batches():
        source_subjects.update(map(str, batch.column("subject_id").to_pylist()))
    return by_role, source_subjects


def main() -> int:
    by_role, source_subjects = load_subjects()
    old_development = by_role["development"]
    old_engineering = by_role["validation"] | by_role["final_test"]
    unseen = source_subjects - set().union(*by_role.values())
    formal_subjects = sorted(old_development | unseen)
    OUT.mkdir(parents=True, exist_ok=True)
    if not unseen:
        audit = {
            "schema_version": "investigation-selection-exposure-audit/1.0.0",
            "status": "failed",
            "reason_code": "SPLIT_NO_UNEXPOSED_FORMAL_SUBJECTS",
            "source": str(FORMAL_EVENTS),
            "counts": {
                "formal_source_subjects": len(source_subjects),
                "legacy_split_subjects": len(set().union(*by_role.values())),
                "previous_exposure_none": 0,
                "old_development": len(old_development),
                "old_validation": len(by_role["validation"]),
                "old_final_test": len(by_role["final_test"]),
            },
            "conclusion": "W1 protocol freeze is forbidden; old validation/final-test cannot be promoted.",
        }
        (OUT / "exposure-audit.json").write_text(
            json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        raise SystemExit(json.dumps(audit, ensure_ascii=False))
    SECRET_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not SECRET_PATH.is_file():
        SECRET_PATH.write_bytes(secrets.token_bytes(32))
    protocol_bundle = load_protocol_bundle(
        ROOT / "config/investigation-selection/protocol.yaml",
        ROOT / "schemas/investigation-selection-protocol.schema.json",
        ROOT / "config/investigation-selection/reason-code-registry.yaml",
    )
    config = {
        "split_id": "mimic-investigation-selection-w1",
        "protocol_bundle": protocol_bundle["protocol"],
        "protocol_lock": json.loads(
            (ROOT / "config/investigation-selection/protocol-lock.json").read_text(encoding="utf-8")
        ),
        "assignment_seed": "mimic-investigation-selection-w1-subject-bucket",
        "subject_ref_key_id": "local-w1-subject-ref-key",
        "subject_ref_secret": SECRET_PATH.read_bytes(),
        "ratios": {"development": 0.7, "validation": 0.15, "final_test": 0.15},
    }
    result = build_subject_split(formal_subjects, sorted(old_engineering), config)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "subject_split_public.json").write_text(
        json.dumps(result["public_manifest"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUT / "subject_split_protected.json").write_text(
        json.dumps(result["protected_mapping"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    public_roles = {row["subject_ref"]: row["subject_role"] for row in result["public_manifest"]["assignments"]}
    old_role_by_subject = {subject: "development" for subject in old_development}
    old_role_by_subject.update({subject: "engineering_audit" for subject in old_engineering})
    protected = {row["subject_ref"]: str(row["subject_id"]) for row in result["protected_mapping"]["records"]}
    rows = []
    for subject_ref, role in public_roles.items():
        subject_id = protected[subject_ref]
        previous = old_role_by_subject.get(subject_id, "none")
        rows.append({
            "subject_ref": subject_ref,
            "subject_role": role,
            "previous_exposure": previous,
            "formal_test_eligible": role != "engineering_audit",
            "source_scope": "mimic_iv_raw_10000_unseen_or_legacy_development",
        })
    pd.DataFrame(rows).sort_values("subject_ref").to_parquet(OUT / "subject_exposure_registry.parquet", index=False)
    manifest = {
        "schema_version": "investigation-selection-exposure-registry/1.0.0",
        "status": "frozen",
        "protocol_lock_sha256": result["public_manifest"]["protocol_lock_sha256"],
        "source": {"legacy_split_sha256": sha256(OLD_SPLIT), "formal_events_path": str(FORMAL_EVENTS)},
        "counts": {
            "old_development": len(old_development),
            "old_validation_engineering_audit": len(by_role["validation"]),
            "old_final_test_engineering_audit": len(by_role["final_test"]),
            "previous_exposure_none": len(unseen),
            **result["public_manifest"]["counts"],
        },
        "audit_report": result["audit_report"],
    }
    (OUT / "exposure-registry-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest["counts"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
