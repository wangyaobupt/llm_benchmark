"""Shared test fixtures for the v2 MCQ pipeline (offline, synthetic)."""
from __future__ import annotations

import shutil
import sys
import uuid
from pathlib import Path

import pandas as pd
import pytest

# Make the v2 package importable from the version directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcq.client import FakeStructuredClient  # noqa: E402
from mcq.config_loader import load_prompt, load_thresholds  # noqa: E402


def _row(event_id, subject_id, hadm_id, event_kind, entity_type,
         source_label=None, preferred_name=None, concept_id=None, assertion=None):
    return {
        "event_id": event_id,
        "subject_id": subject_id,
        "hadm_id": hadm_id,
        "event_kind": event_kind,
        "entity_type": entity_type,
        "source_label": source_label,
        "preferred_name": preferred_name,
        "source_concept_id": None,
        "concept_id": concept_id,
        "assertion": assertion,
    }


@pytest.fixture
def events() -> pd.DataFrame:
    """Synthetic event stream with clear imaging signals + distractor pool."""
    rows = []
    eid = 0

    def add(**kw):
        nonlocal eid
        rows.append(_row(str(eid), **kw))
        eid += 1

    # 30 "chest pain": 25 CT Scan, 5 General Xray (imaging answer space).
    for i in range(30):
        add(subject_id=f"s_chest_{i}", hadm_id=f"a_chest_{i}",
            event_kind="symptom_reported", entity_type="symptom",
            source_label="chest pain")
        img = "CT Scan" if i < 25 else "General Xray"
        add(subject_id=f"s_chest_{i}", hadm_id=f"a_chest_{i}",
            event_kind="imaging_ordered", entity_type="imaging_study",
            source_label=img)
    # 30 "abdominal pain": 25 Ultrasound, 5 CT Scan.
    for i in range(30):
        add(subject_id=f"s_abdo_{i}", hadm_id=f"a_abdo_{i}",
            event_kind="symptom_reported", entity_type="symptom",
            source_label="abdominal pain")
        img = "Ultrasound" if i < 25 else "CT Scan"
        add(subject_id=f"s_abdo_{i}", hadm_id=f"a_abdo_{i}",
            event_kind="imaging_ordered", entity_type="imaging_study",
            source_label=img)
    # 6 "headache": populate the distractor pool (non-allowlist imaging studies).
    # "MRI" is a general (specific) modality; "CT Angiogram" is a procedure;
    # "Nuclear Scan" is a specialized modality (excluded from distractors).
    distractors = ["MRI", "CT Angiogram", "Nuclear Scan"] * 2
    for i, img in enumerate(distractors):
        add(subject_id=f"s_head_{i}", hadm_id=f"a_head_{i}",
            event_kind="symptom_reported", entity_type="symptom",
            source_label="headache")
        add(subject_id=f"s_head_{i}", hadm_id=f"a_head_{i}",
            event_kind="imaging_ordered", entity_type="imaging_study",
            source_label=img)
    return pd.DataFrame(rows)


@pytest.fixture
def thresholds_exploratory() -> dict:
    return load_thresholds("exploratory")


@pytest.fixture
def thresholds_formal() -> dict:
    return load_thresholds("formal")


@pytest.fixture
def generate_prompt() -> str:
    return load_prompt("generate_stem.md")


@pytest.fixture
def review_prompt() -> str:
    return load_prompt("review_question.md")


@pytest.fixture
def fake_client() -> FakeStructuredClient:
    return FakeStructuredClient(model_name="fake-mcq-model")


@pytest.fixture
def out_dir():
    """A writable temp dir under the version directory.

    Uses ``Path.mkdir`` (not ``tempfile.mkdtemp``) because the sandbox denies
    writes inside mkdtemp-created directories; Path.mkdir-created directories
    are writable (verified by the smoke test).
    """
    base = Path(__file__).resolve().parents[1] / ".pytest-out"
    base.mkdir(parents=True, exist_ok=True)
    d = base / ("test-" + uuid.uuid4().hex)
    d.mkdir(parents=True, exist_ok=True)
    yield d
    shutil.rmtree(d, ignore_errors=True)
