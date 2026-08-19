"""Smoke test: run the v2 pipeline offline on synthetic events."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # v2-llm-stem

import pandas as pd

from mcq.client import FakeStructuredClient
from mcq.config_loader import load_prompt, load_thresholds
from mcq.pipeline import run_pipeline
from mcq.audit import read_jsonl
from mcq.validators import QUESTION_VALIDATOR, RULE_VALIDATOR, validate_strict


def make_events():
    rows = []
    eid = 0

    def add(**kw):
        nonlocal eid
        rows.append({"event_id": str(eid), "subject_id": kw["subject_id"],
                     "hadm_id": kw["hadm_id"], "event_kind": kw["event_kind"],
                     "entity_type": kw["entity_type"], "source_label": kw.get("source_label"),
                     "preferred_name": None, "source_concept_id": None,
                     "concept_id": kw.get("concept_id"), "assertion": None})
        eid += 1

    for i in range(30):
        add(subject_id=f"s_chest_{i}", hadm_id=f"a_chest_{i}",
            event_kind="symptom_reported", entity_type="symptom", source_label="chest pain")
        img = "CT Scan" if i < 25 else "General Xray"
        add(subject_id=f"s_chest_{i}", hadm_id=f"a_chest_{i}",
            event_kind="imaging_ordered", entity_type="imaging_study", source_label=img)
    for i in range(30):
        add(subject_id=f"s_abdo_{i}", hadm_id=f"a_abdo_{i}",
            event_kind="symptom_reported", entity_type="symptom", source_label="abdominal pain")
        img = "Ultrasound" if i < 25 else "CT Scan"
        add(subject_id=f"s_abdo_{i}", hadm_id=f"a_abdo_{i}",
            event_kind="imaging_ordered", entity_type="imaging_study", source_label=img)
    distractors = ["MRI Brain", "CT Angiogram", "Nuclear Scan"] * 2
    for i, img in enumerate(distractors):
        add(subject_id=f"s_head_{i}", hadm_id=f"a_head_{i}",
            event_kind="symptom_reported", entity_type="symptom", source_label="headache")
        add(subject_id=f"s_head_{i}", hadm_id=f"a_head_{i}",
            event_kind="imaging_ordered", entity_type="imaging_study", source_label=img)
    return pd.DataFrame(rows)


def main():
    events = make_events()
    thresholds = load_thresholds("exploratory")
    client = FakeStructuredClient()
    gp = load_prompt("generate_stem.md")
    rp = load_prompt("review_question.md")
    out = Path(__file__).resolve().parent / "_smoke_out"
    t0 = time.time()
    summary = run_pipeline(events, thresholds, client, gp, rp,
                           profile="exploratory", out_dir=out)
    print("elapsed", round(time.time() - t0, 2), "s")
    print(json.dumps(summary["counts"], indent=2))

    # Strict-schema conformance of produced artifacts.
    rules = read_jsonl(out / "conditional_rules.jsonl")
    rejected = read_jsonl(out / "conditional_rules_rejected.jsonl")
    reviewed = read_jsonl(out / "questions_reviewed.jsonl")
    for r in rules + rejected:
        validate_strict(RULE_VALIDATOR, r)
    for q in reviewed:
        validate_strict(QUESTION_VALIDATOR, q)
    print("schema conformance: OK (rules=%d, rejected=%d, questions=%d)"
          % (len(rules), len(rejected), len(reviewed)))
    print("sample stem:", reviewed[0]["stem"] if reviewed else "(none)")
    print("sample options:", reviewed[0]["options"] if reviewed else "(none)")
    return 0


import json  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
