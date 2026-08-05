from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, TypeVar

from .cohort import apply_demographics, extract_diagnoses, load_candidates
from .common import RunConfig, RunSummary
from .discharge import extract_discharge_fields
from .investigations import extract_investigation_orders, extract_laboratory_results
from .output import build_output_frame, validate_output, write_output
from .radiology import extract_radiology_reports
from .treatments import extract_prescriptions, extract_procedures


T = TypeVar("T")


def _stage(label: str, function: Callable[[], T]) -> T:
    started = time.monotonic()
    print(f"[{label}] started", flush=True)
    result = function()
    print(f"[{label}] completed in {time.monotonic() - started:.1f}s", flush=True)
    return result


def run_extraction(data_root: Path, output: Path, limit: int) -> RunSummary:
    started = time.monotonic()
    config = RunConfig(data_root=Path(data_root), output=Path(output), limit=limit)
    if not config.data_root.is_dir():
        raise FileNotFoundError(f"Data root does not exist: {config.data_root}")

    candidates = _stage("admissions", lambda: load_candidates(config.data_root, config.limit))
    candidate_count = len(candidates)
    candidate_order = dict(zip(candidates["hadm_id"], candidates["_source_order"]))
    print(f"[admissions] candidates={candidate_count}", flush=True)

    demographic = _stage("demographics", lambda: apply_demographics(config.data_root, candidates))
    demographic_ids = set(demographic["hadm_id"])
    print(f"[demographics] eligible={len(demographic_ids)}", flush=True)

    diagnosis_ids, diagnoses = _stage(
        "diagnoses",
        lambda: extract_diagnoses(config.data_root, candidates, demographic_ids),
    )
    print(f"[diagnoses] eligible={len(diagnosis_ids)}", flush=True)

    discharge_ids, discharge = _stage(
        "discharge",
        lambda: extract_discharge_fields(config.data_root, candidates, diagnosis_ids),
    )
    eligible_ids = diagnosis_ids & discharge_ids
    print(f"[discharge] eligible={len(eligible_ids)}", flush=True)

    orders = _stage(
        "investigation orders",
        lambda: extract_investigation_orders(config.data_root, candidates, eligible_ids),
    )
    labs = _stage(
        "laboratory results",
        lambda: extract_laboratory_results(config.data_root, candidates, eligible_ids),
    )
    radiology = _stage(
        "radiology",
        lambda: extract_radiology_reports(config.data_root, candidates, eligible_ids),
    )
    prescriptions = _stage(
        "prescriptions",
        lambda: extract_prescriptions(config.data_root, candidates, eligible_ids),
    )
    procedures = _stage(
        "procedures",
        lambda: extract_procedures(config.data_root, candidates, eligible_ids),
    )

    output_frame = build_output_frame(
        demographic,
        eligible_ids,
        diagnoses,
        discharge,
        orders,
        labs,
        radiology,
        prescriptions,
        procedures,
    )
    validate_output(output_frame, candidate_order)
    write_output(output_frame, config.output)

    return RunSummary(
        candidate_count=candidate_count,
        eligible_count=len(output_frame),
        output_path=config.output.resolve(),
        elapsed_seconds=time.monotonic() - started,
    )
