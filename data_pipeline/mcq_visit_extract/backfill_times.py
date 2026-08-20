"""Attach fillable source times without overwriting the frozen extract.

Covers prescription start/stop, procedure chartdate, lab/radiology storetime,
medrecon charttime, and encounter/ED/rhythm clocks already in staging.
"""

from __future__ import annotations

import argparse
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Sequence

import pyarrow.parquet as pq

from data_pipeline.mcq_visit_extract.atomic import atomic_write_json, file_sha256
from data_pipeline.mcq_visit_extract.columns import (
    LAB_RESULT_CORE_KEYS,
    MEDRECON_CORE_KEYS,
    PROCEDURE_CORE_KEYS,
    RADIOLOGY_CORE_KEYS,
    SCHEMA_NAME,
    SCHEMA_VERSION,
)
from data_pipeline.mcq_visit_extract.extract import (
    _lab_items,
    _latest_edstay,
    _medications,
    _or_none,
    _procedures,
    _radiology,
    _text,
    medication_core,
)
from data_pipeline.mcq_visit_standardize.io import iter_json_array, write_json_array

CoreFn = Callable[[dict[str, Any]], tuple[Any, ...]]


class BackfillError(ValueError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _assert_output_dir(extract_dir: Path, output_dir: Path) -> Path:
    extract_dir = extract_dir.resolve()
    output_dir = output_dir.resolve()
    if output_dir == extract_dir or extract_dir in output_dir.parents:
        raise BackfillError("refusing to write into the frozen extract directory")
    return output_dir


def _hadm(row: dict[str, Any]) -> str:
    return str(row.get("hadm_id") or row.get("_sel_hadm_id") or "").strip()


def load_rows_by_hadm(
    path: Path,
    columns: Sequence[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    if not path.is_file():
        return {}
    table = pq.read_table(path, columns=list(columns) if columns else None)
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in table.to_pylist():
        hadm_id = _hadm(row)
        if hadm_id:
            grouped[hadm_id].append(row)
    return grouped


def _norm_number(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return float(value)
    return value


def _tuple_from_keys(item: dict[str, Any], keys: Sequence[str]) -> tuple[Any, ...]:
    return tuple(_norm_number(item.get(key)) for key in keys)


def medication_key(item: dict[str, Any]) -> tuple[Any, ...]:
    core = medication_core(item)
    core["doses_per_24_hrs"] = _norm_number(core.get("doses_per_24_hrs"))
    return tuple(core[key] for key in core)


def procedure_key(item: dict[str, Any]) -> tuple[Any, ...]:
    payload = {key: item.get(key) for key in PROCEDURE_CORE_KEYS}
    version = payload.get("icd_version")
    if isinstance(version, str) and version.isdigit():
        payload["icd_version"] = int(version)
    return tuple(payload[key] for key in PROCEDURE_CORE_KEYS)


def medrecon_key(item: dict[str, Any]) -> tuple[Any, ...]:
    return _tuple_from_keys(item, MEDRECON_CORE_KEYS)


def lab_result_key(item: dict[str, Any]) -> tuple[Any, ...]:
    return _tuple_from_keys(item, LAB_RESULT_CORE_KEYS)


def radiology_key(item: dict[str, Any]) -> tuple[Any, ...]:
    return _tuple_from_keys(item, RADIOLOGY_CORE_KEYS)


def overlay_times(
    published: list[dict[str, Any]] | None,
    rebuilt: list[dict[str, Any]],
    core_fn: CoreFn,
    time_keys: Sequence[str],
    *,
    sort_key: Callable[[dict[str, Any]], Any] | None = None,
    label: str,
) -> list[dict[str, Any]]:
    buckets: dict[tuple[Any, ...], deque[dict[str, Any]]] = defaultdict(deque)
    for item in rebuilt:
        buckets[core_fn(item)].append(item)
    timed: list[dict[str, Any]] = []
    for item in published or []:
        key = core_fn(item)
        if not buckets[key]:
            raise BackfillError(f"{label} core mismatch against frozen extract")
        source = buckets[key].popleft()
        patched = dict(item)
        for field in time_keys:
            patched[field] = source.get(field)
        timed.append(patched)
    leftover = sum(len(queue) for queue in buckets.values())
    if leftover:
        raise BackfillError(f"{label} core mismatch against frozen extract")
    if sort_key is not None:
        timed.sort(key=sort_key)
    return timed


def attach_times(
    published: list[dict[str, Any]] | None,
    prescription_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return overlay_times(
        published,
        _medications(prescription_rows),
        medication_key,
        ("starttime", "stoptime"),
        sort_key=lambda item: (item.get("starttime") or "", item.get("drug") or ""),
        label="medication",
    )


def _stay_id(edstay: dict[str, Any] | None) -> str:
    return _text(edstay.get("stay_id")) if edstay else ""


def _filter_stay(rows: list[dict[str, Any]], stay_id: str) -> list[dict[str, Any]]:
    if not stay_id:
        return list(rows)
    return [row for row in rows if _text(row.get("stay_id")) == stay_id]


def _rhythm_charttime(rows: list[dict[str, Any]]) -> str | None:
    ordered = sorted(rows, key=lambda row: _text(row.get("charttime")))
    for row in ordered:
        if _or_none(row.get("rhythm")):
            return _or_none(row.get("charttime"))
    return None


def _overlay_lab_items(
    published: list[dict[str, Any]] | None,
    lab_rows: list[dict[str, Any]],
    lab_dictionary: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rebuilt = {str(item.get("itemid")): item for item in _lab_items(lab_rows, lab_dictionary)}
    timed: list[dict[str, Any]] = []
    for item in published or []:
        rebuilt_item = rebuilt.get(str(item.get("itemid")))
        if rebuilt_item is None:
            raise BackfillError("laboratory itemid mismatch against frozen extract")
        patched = dict(item)
        patched["results"] = overlay_times(
            item.get("results"),
            rebuilt_item.get("results") or [],
            lab_result_key,
            ("storetime",),
            label="laboratory result",
        )
        timed.append(patched)
        del rebuilt[str(item.get("itemid"))]
    if rebuilt:
        raise BackfillError("laboratory itemid mismatch against frozen extract")
    return timed


def _overlay_radiology(
    published: list[dict[str, Any]] | None,
    notes: list[dict[str, Any]],
    details: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    stripped = []
    for note in notes:
        row = dict(note)
        row["text"] = None
        stripped.append(row)
    rebuilt = _radiology(stripped, details)
    return overlay_times(
        published,
        rebuilt,
        radiology_key,
        ("storetime",),
        sort_key=lambda item: (item.get("charttime") or "", item.get("exam_name") or ""),
        label="radiology",
    )


def patch_visit(
    visit: dict[str, Any],
    *,
    prescriptions: list[dict[str, Any]],
    procedures: list[dict[str, Any]],
    procedure_dictionary: dict[tuple[str, str], str],
    labevents: list[dict[str, Any]],
    lab_dictionary: dict[str, dict[str, Any]],
    radiology: list[dict[str, Any]],
    radiology_detail: list[dict[str, Any]],
    medrecon: list[dict[str, Any]],
    admissions: list[dict[str, Any]],
    edstays: list[dict[str, Any]],
    vitalsign: list[dict[str, Any]],
) -> dict[str, Any]:
    patched = dict(visit)
    patched["medications"] = attach_times(visit.get("medications"), prescriptions)
    patched["procedures"] = overlay_times(
        visit.get("procedures"),
        _procedures(procedures, procedure_dictionary),
        procedure_key,
        ("chartdate",),
        sort_key=lambda item: (
            item.get("chartdate") or "",
            str(item.get("icd_version") or ""),
            str(item.get("icd_code") or ""),
        ),
        label="procedure",
    )
    investigations = dict(visit.get("investigations") or {})
    if "laboratory" in investigations or labevents:
        investigations["laboratory"] = _overlay_lab_items(
            investigations.get("laboratory"),
            labevents,
            lab_dictionary,
        )
    if "radiology" in investigations or radiology:
        investigations["radiology"] = _overlay_radiology(
            investigations.get("radiology"),
            radiology,
            radiology_detail,
        )
    patched["investigations"] = investigations
    edstay = _latest_edstay(edstays)
    stay_id = _stay_id(edstay)
    rebuilt_medrecon = [
        {
            "name": _or_none(row.get("name")),
            "gsn": _or_none(row.get("gsn")),
            "ndc": _or_none(row.get("ndc")),
            "etcdescription": _or_none(row.get("etcdescription")),
            "charttime": _or_none(row.get("charttime")),
        }
        for row in _filter_stay(medrecon, stay_id)
    ]
    rebuilt_medrecon.sort(key=lambda item: (item.get("charttime") or "", item.get("name") or ""))
    patched["medrecon"] = overlay_times(
        visit.get("medrecon"),
        rebuilt_medrecon,
        medrecon_key,
        ("charttime",),
        sort_key=lambda item: (item.get("charttime") or "", item.get("name") or ""),
        label="medrecon",
    )
    admission = admissions[0] if admissions else {}
    patched["admittime"] = _or_none(admission.get("admittime"))
    patched["dischtime"] = _or_none(admission.get("dischtime"))
    patched["deathtime"] = _or_none(admission.get("deathtime"))
    patched["edregtime"] = _or_none(admission.get("edregtime"))
    patched["edouttime"] = _or_none(admission.get("edouttime"))
    patched["ed_intime"] = _or_none(edstay.get("intime")) if edstay else None
    patched["ed_outtime"] = _or_none(edstay.get("outtime")) if edstay else None
    patched["rhythm_charttime"] = _rhythm_charttime(_filter_stay(vitalsign, stay_id))
    return patched


def _load_procedure_dictionary(extract_dir: Path) -> dict[tuple[str, str], str]:
    path = extract_dir / "reference_tables" / "d_icd_procedures.parquet"
    if not path.is_file():
        return {}
    mapping: dict[tuple[str, str], str] = {}
    for row in pq.read_table(path).to_pylist():
        code = str(row.get("icd_code") or "").strip()
        version = str(row.get("icd_version") or "").strip()
        title = str(row.get("long_title") or "").strip()
        if code and version and title:
            mapping[(code, version)] = title
    return mapping


def _load_lab_dictionary(extract_dir: Path) -> dict[str, dict[str, Any]]:
    path = extract_dir / "reference_tables" / "d_labitems.parquet"
    if not path.is_file():
        return {}
    mapping: dict[str, dict[str, Any]] = {}
    for row in pq.read_table(path).to_pylist():
        itemid = str(row.get("itemid") or "").strip()
        if itemid:
            mapping[itemid] = row
    return mapping


def _count_times(values: Sequence[dict[str, Any]], field: str) -> tuple[int, int]:
    total = len(values)
    filled = sum(1 for item in values if item.get(field))
    return total, filled


def run(
    *,
    extract_dir: Path,
    output_dir: Path,
    expected_count: int,
    write_visits: bool = True,
) -> dict[str, Any]:
    extract_dir = extract_dir.resolve()
    visits_path = extract_dir / "visits.json"
    if not visits_path.is_file():
        raise BackfillError(f"visits.json missing: {visits_path}")
    output_dir = _assert_output_dir(extract_dir, output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    staging = extract_dir / "staging"

    prescriptions = load_rows_by_hadm(staging / "prescriptions.parquet")
    procedures = load_rows_by_hadm(staging / "procedures_icd.parquet")
    labevents = load_rows_by_hadm(
        staging / "labevents.parquet",
        columns=(
            "hadm_id",
            "itemid",
            "charttime",
            "storetime",
            "value",
            "valuenum",
            "valueuom",
            "ref_range_lower",
            "ref_range_upper",
            "flag",
            "comments",
        ),
    )
    radiology = load_rows_by_hadm(
        staging / "radiology.parquet",
        columns=("hadm_id", "note_id", "note_type", "charttime", "storetime"),
    )
    radiology_detail = load_rows_by_hadm(
        staging / "radiology_detail.parquet",
        columns=("_sel_hadm_id", "note_id", "field_name", "field_value", "field_ordinal"),
    )
    medrecon = load_rows_by_hadm(staging / "medrecon.parquet")
    admissions = load_rows_by_hadm(staging / "admissions.parquet")
    edstays = load_rows_by_hadm(staging / "edstays.parquet")
    vitalsign = load_rows_by_hadm(staging / "vitalsign.parquet")
    procedure_dictionary = _load_procedure_dictionary(extract_dir)
    lab_dictionary = _load_lab_dictionary(extract_dir)

    counts = {
        "visits": 0,
        "medications": 0,
        "medications_starttime": 0,
        "procedures": 0,
        "procedures_chartdate": 0,
        "lab_results": 0,
        "lab_storetime": 0,
        "radiology": 0,
        "radiology_storetime": 0,
        "medrecon": 0,
        "medrecon_charttime": 0,
        "admittime": 0,
        "rhythm_charttime": 0,
    }

    def patched_visits() -> Iterator[dict[str, Any]]:
        for visit in iter_json_array(visits_path):
            hadm_id = str(visit.get("hadm_id") or "").strip()
            try:
                patched = patch_visit(
                    visit,
                    prescriptions=prescriptions.get(hadm_id, []),
                    procedures=procedures.get(hadm_id, []),
                    procedure_dictionary=procedure_dictionary,
                    labevents=labevents.get(hadm_id, []),
                    lab_dictionary=lab_dictionary,
                    radiology=radiology.get(hadm_id, []),
                    radiology_detail=radiology_detail.get(hadm_id, []),
                    medrecon=medrecon.get(hadm_id, []),
                    admissions=admissions.get(hadm_id, []),
                    edstays=edstays.get(hadm_id, []),
                    vitalsign=vitalsign.get(hadm_id, []),
                )
            except BackfillError as error:
                raise BackfillError(f"{error} hadm_id={hadm_id}") from error
            counts["visits"] += 1
            med_total, med_filled = _count_times(patched.get("medications") or [], "starttime")
            counts["medications"] += med_total
            counts["medications_starttime"] += med_filled
            px_total, px_filled = _count_times(patched.get("procedures") or [], "chartdate")
            counts["procedures"] += px_total
            counts["procedures_chartdate"] += px_filled
            lab_rows = [
                result
                for item in (patched.get("investigations") or {}).get("laboratory") or []
                for result in item.get("results") or []
            ]
            lab_total, lab_filled = _count_times(lab_rows, "storetime")
            counts["lab_results"] += lab_total
            counts["lab_storetime"] += lab_filled
            rad_total, rad_filled = _count_times(
                (patched.get("investigations") or {}).get("radiology") or [],
                "storetime",
            )
            counts["radiology"] += rad_total
            counts["radiology_storetime"] += rad_filled
            recon_total, recon_filled = _count_times(patched.get("medrecon") or [], "charttime")
            counts["medrecon"] += recon_total
            counts["medrecon_charttime"] += recon_filled
            if patched.get("admittime"):
                counts["admittime"] += 1
            if patched.get("rhythm_charttime"):
                counts["rhythm_charttime"] += 1
            yield patched

    visits_json_sha = None
    consumed = 0
    if write_visits:
        visits_json_sha = write_json_array(output_dir / "visits.json", patched_visits())
        consumed = counts["visits"]
    else:
        for _ in patched_visits():
            consumed += 1

    if expected_count and consumed != expected_count:
        raise BackfillError(f"visit count {consumed} != expected {expected_count}")

    def _rate(filled: int, total: int) -> float | None:
        if not total:
            return None
        return round(filled / total, 4)

    summary = {
        "schema_name": SCHEMA_NAME,
        "schema_version": SCHEMA_VERSION,
        "kind": "visit_time_backfill",
        "extract_dir": str(extract_dir),
        "extract_visits_sha256": file_sha256(visits_path),
        "visits": consumed,
        "medication_rows": counts["medications"],
        "medication_starttime_rate": _rate(
            counts["medications_starttime"], counts["medications"]
        ),
        "procedure_rows": counts["procedures"],
        "procedure_chartdate_rate": _rate(
            counts["procedures_chartdate"], counts["procedures"]
        ),
        "lab_result_rows": counts["lab_results"],
        "lab_storetime_rate": _rate(counts["lab_storetime"], counts["lab_results"]),
        "radiology_rows": counts["radiology"],
        "radiology_storetime_rate": _rate(
            counts["radiology_storetime"], counts["radiology"]
        ),
        "medrecon_rows": counts["medrecon"],
        "medrecon_charttime_rate": _rate(
            counts["medrecon_charttime"], counts["medrecon"]
        ),
        "visits_with_admittime": counts["admittime"],
        "visits_with_rhythm_charttime": counts["rhythm_charttime"],
        "visits_json_sha256": visits_json_sha,
        "does_not_overwrite_extract": True,
        "gold_status": "exploratory_unreviewed",
        "time_fields": [
            "medications.starttime/stoptime",
            "procedures.chartdate",
            "investigations.laboratory.results.storetime",
            "investigations.radiology.storetime",
            "medrecon.charttime",
            "admittime/dischtime/deathtime",
            "ed_intime/ed_outtime/edregtime/edouttime",
            "rhythm_charttime",
        ],
        "not_added": [
            "eMAR charttime (administration; extract uses prescriptions only)",
            "ICU procedureevents (not in visit extract sources)",
            "discharge note charttime (lineage, not a result column)",
        ],
        "written_at_utc": _utc_now(),
    }
    atomic_write_json(output_dir / "summary.json", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill fillable timestamps onto visit rows. "
            "Writes a new directory; never overwrites the frozen extract."
        )
    )
    parser.add_argument("--extract-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-count", type=int, default=10_000)
    parser.add_argument("--skip-visits-json", action="store_true")
    args = parser.parse_args(argv)
    try:
        summary = run(
            extract_dir=args.extract_dir,
            output_dir=args.output_dir,
            expected_count=args.expected_count,
            write_visits=not args.skip_visits_json,
        )
    except BackfillError as error:
        print(f"mcq_visit_extract backfill failed: {error}")
        return 1
    print(
        f"complete visits={summary['visits']} "
        f"procedures={summary['procedure_rows']} "
        f"chartdate_rate={summary['procedure_chartdate_rate']} "
        f"output={args.output_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
