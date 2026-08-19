from collections import Counter, defaultdict
from pathlib import Path

import pyarrow.parquet as pq

CORPUS = Path("data/derived/investigation_timepoint/corpus_1000")
MINING = CORPUS / "mining"


def main() -> None:
    docs = pq.read_table(CORPUS / "decision_documents.parquet").to_pylist()
    evidence = pq.read_table(
        CORPUS / "decision_evidence.parquet",
        columns=["decision_id", "event_kind", "concept_id", "preferred_name"],
    ).to_pylist()
    targets = pq.read_table(
        CORPUS / "decision_targets.parquet",
        columns=["decision_id", "candidate_name", "candidate_class"],
    ).to_pylist()
    family = pq.read_table(MINING / "rule_family.parquet").to_pylist()
    validated = pq.read_table(MINING / "validated_rules.parquet").to_pylist()

    by_split = defaultdict(list)
    for row in docs:
        by_split[row["split_role"]].append(row)
    print("=== split ===")
    for role, rows in sorted(by_split.items()):
        n_subj = len({r["subject_id"] for r in rows})
        n_hadm = len({r["hadm_id"] for r in rows})
        tracks = Counter(r["track_id"] for r in rows)
        print(role, "docs", len(rows), "subjects", n_subj, "hadm", n_hadm, "tracks", dict(tracks))

    print("=== family vs gates ===")
    print("family", len(family), "validated_rows", len(validated))
    print("family by class", Counter(r["family"] for r in family))
    print("lift>=1", sum(1 for r in family if r["lift"] >= 1))
    print("shrunk>0", sum(1 for r in family if r["shrunk_log_rr"] > 0))

    print("=== 28 surviving rules: validation joint vs threshold 20 ===")
    joints = [int(r.get("validation_joint_subjects") or 0) for r in validated]
    print("val_joint min/median/max", min(joints), sorted(joints)[len(joints) // 2], max(joints))
    print("would pass if threshold 10", sum(j >= 10 for j in joints))
    print("would pass if threshold 5", sum(j >= 5 for j in joints))
    print("dev_joint min/max", min(r["n_xy_subjects"] for r in validated), max(r["n_xy_subjects"] for r in validated))

    print("=== surviving condition names ===")
    print(Counter(r["condition_name"] for r in validated))
    short = [(r["condition_name"], r["condition_id"], r["candidate_name"]) for r in validated if len(str(r["condition_name"] or "")) <= 2]
    print("short names", short)

    print("=== evidence name quality on development imaging docs ===")
    imaging_ids = {
        r["decision_id"]
        for r in docs
        if r["split_role"] == "development" and r["track_id"] == "imaging_order"
    }
    ev_img = [r for r in evidence if r["decision_id"] in imaging_ids]
    print("imaging evidence rows", len(ev_img))
    print("kinds", Counter(r["event_kind"] for r in ev_img).most_common(8))
    lab = [r for r in ev_img if r["event_kind"] == "laboratory_resulted"]
    print("lab evidence with concept", sum(bool(r.get("concept_id")) for r in lab), "of", len(lab))
    print("lab name length<=2", sum(len(str(r.get("preferred_name") or "")) <= 2 for r in lab))
    print("top lab names", Counter(r.get("preferred_name") for r in lab).most_common(15))

    print("=== development association quality of 28 ===")
    print("all bootstrap >=0.8", all(r["bootstrap_direction_stability"] >= 0.8 for r in validated))
    print("all lift>1", all(r["lift"] > 1 for r in validated))
    print("wilson_low>=0.35", sum(r["wilson_low"] >= 0.35 for r in validated), "of", len(validated))

    print("=== generic_lab family ===")
    lab_docs = [r for r in by_split["development"] if r["track_id"] == "generic_lab_order"]
    print("generic_lab docs", len(lab_docs), "subjects", len({r["subject_id"] for r in lab_docs}))
    lab_ids = {d["decision_id"] for d in lab_docs}
    lab_t = [t for t in targets if t["decision_id"] in lab_ids]
    print("generic_lab target names", Counter(t["candidate_name"] for t in lab_t))


if __name__ == "__main__":
    main()
