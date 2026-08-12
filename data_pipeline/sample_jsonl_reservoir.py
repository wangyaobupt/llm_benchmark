"""Reproducibly sample JSONL records without loading the archive into memory."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


class JsonlSamplingError(ValueError):
    """Raised when a JSONL source cannot be sampled without guessing."""


@dataclass(frozen=True)
class SelectedRecord:
    line_number: int
    byte_offset: int
    byte_length: int
    line_sha256: str
    subject_id: Any
    hadm_id: Any


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _partial_path(path: Path) -> Path:
    return path.with_name(path.name + ".partial")


def _validate_paths(input_path: Path, output_path: Path, manifest_path: Path) -> None:
    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    if len({input_path, output_path, manifest_path}) != 3:
        raise ValueError("input, output and manifest paths must differ")
    for target in (output_path, manifest_path):
        if target.exists():
            raise FileExistsError(f"refusing to overwrite existing output: {target}")
        partial = _partial_path(target)
        if partial.exists():
            raise FileExistsError(f"refusing to overwrite incomplete output: {partial}")


def _parse_record(raw_line: bytes, line_number: int, byte_offset: int) -> dict[str, Any]:
    if not raw_line.strip():
        raise JsonlSamplingError(
            f"line {line_number}, byte offset {byte_offset}: blank JSONL record"
        )
    try:
        record = json.loads(raw_line)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise JsonlSamplingError(
            f"line {line_number}, byte offset {byte_offset}: {error}"
        ) from error
    if not isinstance(record, dict):
        raise JsonlSamplingError(
            f"line {line_number}, byte offset {byte_offset}: record must be an object"
        )
    return record


def reservoir_sample_jsonl(
    input_path: Path,
    output_path: Path,
    manifest_path: Path,
    *,
    sample_size: int,
    seed: int,
    progress_every: int = 0,
) -> dict[str, Any]:
    """Sample records uniformly without replacement and preserve their source bytes.

    The reservoir stores only source offsets and audit metadata. Selected source
    lines are read again by offset after the complete archive has been scanned.
    """
    if sample_size <= 0:
        raise ValueError("sample_size must be greater than zero")
    if progress_every < 0:
        raise ValueError("progress_every must be non-negative")

    input_path = input_path.resolve()
    output_path = output_path.resolve()
    manifest_path = manifest_path.resolve()
    _validate_paths(input_path, output_path, manifest_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    output_partial = _partial_path(output_path)
    manifest_partial = _partial_path(manifest_path)
    rng = random.Random(seed)
    reservoir: list[SelectedRecord] = []
    input_digest = hashlib.sha256()
    input_size = input_path.stat().st_size
    started_at = _now_iso()
    started = time.monotonic()
    record_count = 0
    created_output = False

    try:
        with input_path.open("rb") as source:
            while True:
                byte_offset = source.tell()
                raw_line = source.readline()
                if not raw_line:
                    break
                record_count += 1
                input_digest.update(raw_line)
                record = _parse_record(raw_line, record_count, byte_offset)
                selected = SelectedRecord(
                    line_number=record_count,
                    byte_offset=byte_offset,
                    byte_length=len(raw_line),
                    line_sha256=hashlib.sha256(raw_line).hexdigest(),
                    subject_id=record.get("subject_id"),
                    hadm_id=record.get("hadm_id"),
                )
                if record_count <= sample_size:
                    reservoir.append(selected)
                else:
                    replacement_index = rng.randrange(record_count)
                    if replacement_index < sample_size:
                        reservoir[replacement_index] = selected

                if progress_every and record_count % progress_every == 0:
                    elapsed = max(time.monotonic() - started, 1e-9)
                    progress = source.tell() * 100 / input_size if input_size else 100.0
                    speed_mib = source.tell() / elapsed / (1024 * 1024)
                    print(
                        f"scanned={record_count:,} progress={progress:.2f}% "
                        f"speed={speed_mib:.2f} MiB/s",
                        file=sys.stderr,
                        flush=True,
                    )

            if record_count < sample_size:
                raise JsonlSamplingError(
                    f"source contains {record_count} records, fewer than requested "
                    f"sample size {sample_size}"
                )

            selected_records = sorted(reservoir, key=lambda item: item.line_number)
            output_digest = hashlib.sha256()
            with output_partial.open("xb") as output:
                for selected in selected_records:
                    source.seek(selected.byte_offset)
                    raw_line = source.read(selected.byte_length)
                    if hashlib.sha256(raw_line).hexdigest() != selected.line_sha256:
                        raise JsonlSamplingError(
                            "source changed while sampling at line "
                            f"{selected.line_number}"
                        )
                    preserved_line = raw_line if raw_line.endswith(b"\n") else raw_line + b"\n"
                    output.write(preserved_line)
                    output_digest.update(preserved_line)
                output.flush()
                os.fsync(output.fileno())

        elapsed_seconds = time.monotonic() - started
        manifest = {
            "algorithm": "reservoir_sampling_without_replacement",
            "started_at": started_at,
            "completed_at": _now_iso(),
            "elapsed_seconds": elapsed_seconds,
            "seed": seed,
            "sample_size": sample_size,
            "source": {
                "path": str(input_path),
                "byte_size": input_size,
                "record_count": record_count,
                "sha256": input_digest.hexdigest(),
            },
            "output": {
                "path": str(output_path),
                "byte_size": output_partial.stat().st_size,
                "record_count": sample_size,
                "sha256": output_digest.hexdigest(),
                "ordering": "ascending_source_line_number",
            },
            "selected_records": [
                {
                    "output_record_number": output_number,
                    "source_line_number": selected.line_number,
                    "source_byte_offset": selected.byte_offset,
                    "source_byte_length": selected.byte_length,
                    "source_line_sha256": selected.line_sha256,
                    "subject_id": selected.subject_id,
                    "hadm_id": selected.hadm_id,
                }
                for output_number, selected in enumerate(selected_records, start=1)
            ],
        }
        with manifest_partial.open("x", encoding="utf-8", newline="\n") as file:
            json.dump(manifest, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())

        os.replace(output_partial, output_path)
        created_output = True
        os.replace(manifest_partial, manifest_path)
        return manifest
    except Exception:
        for partial in (output_partial, manifest_partial):
            partial.unlink(missing_ok=True)
        if created_output:
            output_path.unlink(missing_ok=True)
        raise


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Uniformly sample a complete JSONL file with reservoir sampling"
    )
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--sample-size", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=20260812)
    parser.add_argument("--progress-every", type=int, default=1000)
    return parser


def main() -> None:
    args = create_parser().parse_args()
    manifest = reservoir_sample_jsonl(
        args.input,
        args.output,
        args.manifest,
        sample_size=args.sample_size,
        seed=args.seed,
        progress_every=args.progress_every,
    )
    print(
        json.dumps(
            {
                "algorithm": manifest["algorithm"],
                "seed": manifest["seed"],
                "sample_size": manifest["sample_size"],
                "source": manifest["source"],
                "output": manifest["output"],
                "manifest_path": str(args.manifest.resolve()),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
