"""Capture and verify privacy-safe cleaning regression baselines.

The committed fixture contains source references and deterministic identifiers,
but fingerprints patient/admission identities and timestamps.  Full patient-level
values remain in the ignored local MIMIC-derived files.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any, Iterable

import pyarrow.parquet as pq

from ..event_cleaning.pipeline import run_cleaning


FIXTURE_SCHEMA = {"name": "event_cleaning_regression", "version": "1.1.0"}
DEFAULT_FIXTURE = Path("tests/fixtures/event-cleaning-regression.json")


@dataclass(frozen=True)
class BatchDefinition:
    batch_id: str
    input_path: Path
    accepted_cleaning_directory: Path


DEFAULT_BATCHES: tuple[BatchDefinition, ...] = (
    BatchDefinition(
        "sample_100",
        Path(
            "data/validation/"
            "mimic-admission-raw-coronary-sample-100-poe-timeline-decoded.jsonl"
        ),
        Path("data/derived/event_pipeline_sample_100/cleaning"),
    ),
    BatchDefinition(
        "random_1000_a",
        Path(
            "data/test_1000_0812/"
            "mimic-admission-clinical-readable-coronary-random-1000.jsonl"
        ),
        Path(
            "data/test_1000_0812/"
            "event_pipeline_coronary_random_1000/cleaning"
        ),
    ),
    BatchDefinition(
        "random_1000_b",
        Path(
            "data/test_1000_0812_2/"
            "mimic-admission-clinical-readable-coronary-random-1000.jsonl"
        ),
        Path(
            "data/test_1000_0812_2/"
            "event_pipeline_coronary_random_1000/cleaning"
        ),
    ),
)


EVENT_COLUMNS = (
    "schema_version",
    "cleaning_status",
    "event_id",
    "entity_id",
    "source_row_id",
    "subject_id",
    "hadm_id",
    "encounter_id",
    "event_kind",
    "lifecycle_action",
    "status",
    "assertion",
    "event_time",
    "source_available_time",
    "available_time",
    "recorded_time",
    "time_resolution_status",
    "time_precision",
    "time_policy_id",
    "time_resolution_reasons",
    "evidence_phase",
    "source_concept_id",
    "concept_id",
    "preferred_name",
    "source_label",
    "entity_type",
    "normalization_status",
    "terminology_mapping_version",
    "content_specificity",
    "value_numeric",
    "value_text",
    "value_structured_json",
    "unit",
    "abnormal_flag",
    "normalized_value_numeric",
    "normalized_value_text",
    "normalized_unit",
    "unit_normalization_status",
    "source_module",
    "source_table",
    "source_array_index",
    "jsonl_line_number",
    "raw_row_ref",
    "source_action",
    "quality_flags",
    "supporting_source_row_ids",
    "supporting_raw_row_refs",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _fingerprint(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _update_digest(digest: Any, value: Any) -> None:
    digest.update(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )
    digest.update(b"\n")


def _time_expectation(value: str | None) -> dict[str, Any]:
    if value is None:
        return {"present": False, "sha256": None}
    return {"present": True, "sha256": _fingerprint(value)}


def _iter_parquet_rows(path: Path, columns: Iterable[str] | None = None):
    parquet = pq.ParquetFile(path)
    for batch in parquet.iter_batches(batch_size=5000, columns=columns):
        yield from batch.to_pylist()


def _snapshot_case(rows: list[dict[str, Any]]) -> dict[str, Any]:
    first = rows[0]
    identity = {
        "subject_id": first["subject_id"],
        "hadm_id": first["hadm_id"],
    }
    event_snapshots = []
    allowed_flags: set[str] = set()
    for row in rows:
        flags = sorted(row.get("quality_flags") or [])
        allowed_flags.update(flags)
        event_snapshots.append(
            {
                "event_id": row["event_id"],
                "event_kind": row["event_kind"],
                "evidence_phase": row["evidence_phase"],
                "event_time": _time_expectation(row.get("event_time")),
                "source_available_time": _time_expectation(
                    row.get("source_available_time")
                ),
                "available_time": _time_expectation(row.get("available_time")),
                "recorded_time": _time_expectation(row.get("recorded_time")),
                "time_resolution_status": row["time_resolution_status"],
                "time_precision": row["time_precision"],
                "time_policy_id": row["time_policy_id"],
                "time_resolution_reasons": row["time_resolution_reasons"],
                "expected_quality_flags": flags,
            }
        )
    return {
        "raw_row_ref": first["raw_row_ref"],
        "source_table": first["source_table"],
        "source_row_id": first["source_row_id"],
        "identity_sha256": _fingerprint(identity),
        "expected_event_count": len(rows),
        "allowed_quality_flags": sorted(allowed_flags),
        "events": sorted(event_snapshots, key=lambda item: item["event_id"]),
    }


class _CaseSelector:
    def __init__(self) -> None:
        self.first_by_kind: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self.max_fanout_by_table: dict[str, list[dict[str, Any]]] = {}

    def add(self, rows: list[dict[str, Any]]) -> None:
        table = rows[0]["source_table"]
        for kind in sorted({row["event_kind"] for row in rows}):
            self.first_by_kind.setdefault((table, kind), rows)
        current = self.max_fanout_by_table.get(table)
        if current is None or (len(rows), rows[0]["raw_row_ref"]) > (
            len(current),
            current[0]["raw_row_ref"],
        ):
            self.max_fanout_by_table[table] = rows

    def snapshots(self) -> list[dict[str, Any]]:
        selected: dict[str, list[dict[str, Any]]] = {}
        for rows in [
            *self.first_by_kind.values(),
            *self.max_fanout_by_table.values(),
        ]:
            selected[rows[0]["raw_row_ref"]] = rows
        return [
            _snapshot_case(selected[raw_ref])
            for raw_ref in sorted(
                selected,
                key=lambda value: (
                    selected[value][0]["source_table"],
                    value,
                ),
            )
        ]


def _select_cases(groups: Iterable[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    selector = _CaseSelector()
    for rows in groups:
        selector.add(rows)
    return selector.snapshots()


def summarize_cleaning(cleaning_directory: Path) -> dict[str, Any]:
    cleaning_directory = Path(cleaning_directory)
    event_path = cleaning_directory / "cleaned_events.parquet"
    rejected_path = cleaning_directory / "cleaning_rejected.parquet"
    manifest_path = cleaning_directory / "run_manifest.json"
    for path in (event_path, rejected_path, manifest_path):
        if not path.is_file():
            raise FileNotFoundError(path)

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    event_id_digest = hashlib.sha256()
    source_row_id_digest = hashlib.sha256()
    event_semantic_digest = hashlib.sha256()
    previous_source_row_id: str | None = None
    event_rows = 0
    source_rows = 0
    selector = _CaseSelector()
    current_group: list[dict[str, Any]] = []
    current_ref: str | None = None

    for row in _iter_parquet_rows(event_path, EVENT_COLUMNS):
        event_rows += 1
        _update_digest(event_id_digest, row["event_id"])
        if row["source_row_id"] != previous_source_row_id:
            source_rows += 1
            _update_digest(source_row_id_digest, row["source_row_id"])
            previous_source_row_id = row["source_row_id"]
        _update_digest(event_semantic_digest, row)

        raw_ref = row["raw_row_ref"]
        if current_ref is not None and raw_ref != current_ref:
            selector.add(current_group)
            current_group = []
        current_ref = raw_ref
        current_group.append(row)
    if current_group:
        selector.add(current_group)

    rejected_digest = hashlib.sha256()
    rejected_rows = 0
    for row in _iter_parquet_rows(rejected_path):
        rejected_rows += 1
        _update_digest(rejected_digest, row)

    return {
        "run_id": manifest["run_id"],
        "counts": manifest["counts"],
        "event_kind_counts": manifest["event_kind_counts"],
        "evidence_phase_counts": manifest["evidence_phase_counts"],
        "observed_event_rows": event_rows,
        "observed_accepted_source_rows": source_rows,
        "observed_rejected_rows": rejected_rows,
        "event_id_sequence_sha256": event_id_digest.hexdigest(),
        "source_row_id_sequence_sha256": source_row_id_digest.hexdigest(),
        "event_semantics_sha256": event_semantic_digest.hexdigest(),
        "rejected_semantics_sha256": rejected_digest.hexdigest(),
        "cases": selector.snapshots(),
    }


def _capture_batch(repository: Path, definition: BatchDefinition) -> dict[str, Any]:
    input_path = repository / definition.input_path
    cleaning_directory = repository / definition.accepted_cleaning_directory
    summary = summarize_cleaning(cleaning_directory)
    run_manifest_path = cleaning_directory / "run_manifest.json"
    run_manifest = json.loads(run_manifest_path.read_text(encoding="utf-8"))
    input_sha256 = _sha256(input_path)
    if input_sha256 != run_manifest["input"]["sha256"]:
        raise ValueError(
            f"{definition.batch_id}: input SHA-256 does not match run manifest"
        )
    return {
        "batch_id": definition.batch_id,
        "input_path": definition.input_path.as_posix(),
        "accepted_cleaning_directory": definition.accepted_cleaning_directory.as_posix(),
        "input_bytes": input_path.stat().st_size,
        "input_sha256": input_sha256,
        "accepted_run_manifest_sha256": _sha256(run_manifest_path),
        "expected": summary,
    }


def capture_fixture(repository: Path, definitions: Iterable[BatchDefinition]) -> dict[str, Any]:
    return {
        "schema": FIXTURE_SCHEMA,
        "acceptance_basis": (
            "User-confirmed batch-level manual testing; representative raw rows are "
            "selected deterministically from the accepted outputs."
        ),
        "privacy": {
            "patient_and_admission_values": "sha256_fingerprint_only",
            "time_values": "presence_and_sha256_fingerprint_only",
            "raw_patient_level_values": "remain_in_gitignored_local_data",
        },
        "selection": {
            "event_kind_coverage": "first source row for every source_table/event_kind",
            "one_to_many_coverage": "maximum event fan-out source row for every source_table",
        },
        "batches": [_capture_batch(repository, definition) for definition in definitions],
    }


def _compare_time(
    batch_id: str,
    raw_ref: str,
    event_id: str,
    field: str,
    expected: dict[str, Any],
    actual: str | None,
    errors: list[str],
) -> None:
    present = actual is not None
    if present != expected["present"]:
        errors.append(f"{batch_id}:{raw_ref}:{event_id}:{field}: presence changed")
        return
    fingerprint = _fingerprint(actual) if present else None
    if fingerprint != expected["sha256"]:
        errors.append(f"{batch_id}:{raw_ref}:{event_id}:{field}: value changed")


def _verify_cases(
    batch_id: str,
    expected_cases: list[dict[str, Any]],
    cleaning_directory: Path,
) -> list[str]:
    errors: list[str] = []
    by_ref = {case["raw_row_ref"]: case for case in expected_cases}
    observed: dict[str, list[dict[str, Any]]] = defaultdict(list)
    columns = (
        "event_id",
        "source_row_id",
        "subject_id",
        "hadm_id",
        "event_kind",
        "event_time",
        "source_available_time",
        "available_time",
        "recorded_time",
        "time_resolution_status",
        "time_precision",
        "time_policy_id",
        "time_resolution_reasons",
        "evidence_phase",
        "quality_flags",
        "raw_row_ref",
    )
    for row in _iter_parquet_rows(
        cleaning_directory / "cleaned_events.parquet", columns
    ):
        if row["raw_row_ref"] in by_ref:
            observed[row["raw_row_ref"]].append(row)

    for raw_ref, expected_case in by_ref.items():
        rows = observed.get(raw_ref, [])
        if len(rows) != expected_case["expected_event_count"]:
            errors.append(
                f"{batch_id}:{raw_ref}: event count "
                f"{len(rows)} != {expected_case['expected_event_count']}"
            )
            continue
        if not rows:
            continue
        identity = {
            "subject_id": rows[0]["subject_id"],
            "hadm_id": rows[0]["hadm_id"],
        }
        if _fingerprint(identity) != expected_case["identity_sha256"]:
            errors.append(f"{batch_id}:{raw_ref}: patient/admission identity changed")
        if any(row["source_row_id"] != expected_case["source_row_id"] for row in rows):
            errors.append(f"{batch_id}:{raw_ref}: source_row_id changed")
        allowed = set(expected_case["allowed_quality_flags"])
        actual_by_id = {row["event_id"]: row for row in rows}
        expected_by_id = {
            event["event_id"]: event for event in expected_case["events"]
        }
        if set(actual_by_id) != set(expected_by_id):
            errors.append(f"{batch_id}:{raw_ref}: event_id set changed")
            continue
        for event_id, expected_event in expected_by_id.items():
            actual = actual_by_id[event_id]
            if actual["event_kind"] != expected_event["event_kind"]:
                errors.append(f"{batch_id}:{raw_ref}:{event_id}: event_kind changed")
            if actual["evidence_phase"] != expected_event["evidence_phase"]:
                errors.append(f"{batch_id}:{raw_ref}:{event_id}: evidence_phase changed")
            for field in (
                "time_resolution_status",
                "time_precision",
                "time_policy_id",
                "time_resolution_reasons",
            ):
                if actual[field] != expected_event[field]:
                    errors.append(
                        f"{batch_id}:{raw_ref}:{event_id}: {field} changed"
                    )
            actual_flags = sorted(actual.get("quality_flags") or [])
            if not set(actual_flags).issubset(allowed):
                errors.append(
                    f"{batch_id}:{raw_ref}:{event_id}: disallowed quality flag"
                )
            if actual_flags != expected_event["expected_quality_flags"]:
                errors.append(
                    f"{batch_id}:{raw_ref}:{event_id}: quality flags changed"
                )
            for field in (
                "event_time",
                "source_available_time",
                "available_time",
                "recorded_time",
            ):
                _compare_time(
                    batch_id,
                    raw_ref,
                    event_id,
                    field,
                    expected_event[field],
                    actual.get(field),
                    errors,
                )
    return errors


def _without_cases(summary: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in summary.items() if key != "cases"}


def verify_batch(
    repository: Path,
    batch: dict[str, Any],
    *,
    rerun: bool,
) -> dict[str, Any]:
    batch_id = batch["batch_id"]
    input_path = repository / batch["input_path"]
    accepted_directory = repository / batch["accepted_cleaning_directory"]
    errors: list[str] = []
    if not input_path.is_file():
        return {"batch_id": batch_id, "passed": False, "errors": ["input missing"]}
    if input_path.stat().st_size != batch["input_bytes"]:
        errors.append(f"{batch_id}: input byte size changed")
    if _sha256(input_path) != batch["input_sha256"]:
        errors.append(f"{batch_id}: input SHA-256 changed")

    if rerun and not errors:
        with tempfile.TemporaryDirectory(prefix=f"event-regression-{batch_id}-") as root:
            cleaning_directory = Path(root) / "cleaning"
            run_cleaning(input_path, cleaning_directory)
            actual = summarize_cleaning(cleaning_directory)
            if _without_cases(actual) != _without_cases(batch["expected"]):
                errors.append(f"{batch_id}: full logical cleaning summary changed")
            errors.extend(
                _verify_cases(batch_id, batch["expected"]["cases"], cleaning_directory)
            )
    elif not errors:
        actual = summarize_cleaning(accepted_directory)
        if _without_cases(actual) != _without_cases(batch["expected"]):
            errors.append(f"{batch_id}: accepted logical cleaning summary changed")
        manifest_path = accepted_directory / "run_manifest.json"
        if _sha256(manifest_path) != batch["accepted_run_manifest_sha256"]:
            errors.append(f"{batch_id}: accepted run manifest SHA-256 changed")
        errors.extend(
            _verify_cases(batch_id, batch["expected"]["cases"], accepted_directory)
        )
    return {"batch_id": batch_id, "passed": not errors, "errors": errors}


def verify_fixture(
    repository: Path,
    fixture: dict[str, Any],
    *,
    batch_ids: set[str] | None = None,
    rerun: bool = False,
) -> dict[str, Any]:
    if fixture.get("schema") != FIXTURE_SCHEMA:
        raise ValueError(f"unsupported fixture schema: {fixture.get('schema')!r}")
    available = {batch["batch_id"] for batch in fixture["batches"]}
    requested = batch_ids or available
    unknown = requested - available
    if unknown:
        raise ValueError(f"unknown batch ids: {sorted(unknown)}")
    results = [
        verify_batch(repository, batch, rerun=rerun)
        for batch in fixture["batches"]
        if batch["batch_id"] in requested
    ]
    return {
        "mode": "rerun" if rerun else "accepted_artifacts",
        "passed": all(result["passed"] for result in results),
        "batches": results,
    }


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _selected_definitions(batch_ids: list[str]) -> tuple[BatchDefinition, ...]:
    if not batch_ids:
        return DEFAULT_BATCHES
    requested = set(batch_ids)
    definitions = tuple(
        definition
        for definition in DEFAULT_BATCHES
        if definition.batch_id in requested
    )
    missing = requested - {definition.batch_id for definition in definitions}
    if missing:
        raise ValueError(f"unknown batch ids: {sorted(missing)}")
    return definitions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    capture = subparsers.add_parser("capture", help="Capture accepted local artifacts")
    capture.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    capture.add_argument("--batch", action="append", default=[])
    verify = subparsers.add_parser("verify", help="Verify accepted artifacts or rerun")
    verify.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    verify.add_argument("--batch", action="append", default=[])
    verify.add_argument("--rerun", action="store_true")
    args = parser.parse_args(argv)

    repository = _repository_root()
    fixture_path = args.fixture
    if not fixture_path.is_absolute():
        fixture_path = repository / fixture_path

    if args.command == "capture":
        fixture = capture_fixture(repository, _selected_definitions(args.batch))
        fixture_path.parent.mkdir(parents=True, exist_ok=True)
        fixture_path.write_text(
            json.dumps(fixture, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        result = {
            "captured": str(fixture_path),
            "batches": [batch["batch_id"] for batch in fixture["batches"]],
        }
    else:
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        result = verify_fixture(
            repository,
            fixture,
            batch_ids=set(args.batch) if args.batch else None,
            rerun=args.rerun,
        )

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("passed", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
