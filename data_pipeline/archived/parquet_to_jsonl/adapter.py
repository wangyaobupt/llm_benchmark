"""Main adapter: G drive parquet -> visit-level JSONL.

Architecture:
    Phase 0: Load patients.csv.gz (age/sex)
    Phase 1: Find eligible hospital episodes (has diagnosis + DS)
    Phase 2-4: For each batch of episodes:
        - Populate batch_eps temp table
        - Run all aggregators (lab, dx, micro, rad, rx, etc.)
        - Load + select DS discharge summaries
        - Assemble visit JSON objects and write JSONL

Usage:
    python -m data_pipeline.archived.parquet_to_jsonl.adapter
    python -m data_pipeline.archived.parquet_to_jsonl.adapter --limit 100
    python -m data_pipeline.archived.parquet_to_jsonl.adapter --limit 100 --output path.jsonl
"""

from __future__ import annotations
import argparse
import json
import logging
import time
from pathlib import Path

import duckdb

from .config import Config
from .eligibility import load_patients, find_eligible_episodes, compute_age
from .ds_parser import select_ds
from .aggregators import (
    aggregate_laboratory,
    aggregate_diagnoses,
    aggregate_microbiology,
    aggregate_radiology,
    aggregate_ed_triage,
    aggregate_ed_vital_signs,
    aggregate_generic_events,
    aggregate_transfers,
    aggregate_icu_stays,
    aggregate_provider_orders,
    aggregate_medication_administrations,
    aggregate_encounter_context,
    aggregate_patient_baseline,
    aggregate_longitudinal_refs,
    create_raw_context_views,
)
from .assembler import assemble_visit
from .validate_archive import validate_archive

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def run(config: Config) -> None:
    t0 = time.time()
    base = str(config.parquet_dir) + "/"

    # Phase 0: Load patients
    logger.info("Phase 0: Loading patients...")
    patients = load_patients(config)

    con = duckdb.connect()
    con.execute("PRAGMA threads=8;")
    con.execute("PRAGMA memory_limit='16GB';")
    create_raw_context_views(con, config)

    # Phase 1: Find eligible episodes
    logger.info("Phase 1: Finding eligible episodes...")
    t1 = time.time()
    episodes = find_eligible_episodes(con, config)
    logger.info("Phase 1 done: %d candidates in %.1fs", len(episodes), time.time() - t1)

    if not episodes:
        logger.error("No eligible episodes found!")
        return

    # Filter by age >= 18 and valid sex
    eligible = []
    for ep in episodes:
        p = patients.get(ep["subject_id"])
        if p is None:
            continue
        age = compute_age(patients, ep["subject_id"], ep["episode_start_time"])
        if age is None or age < 18:
            continue
        if p["gender"] not in ("M", "F"):
            continue
        ep["_age"] = age
        ep["_sex"] = p["gender"]
        eligible.append(ep)

    logger.info("After age/sex filter: %d eligible episodes", len(eligible))

    if not eligible:
        logger.error("No episodes passed age/sex filter!")
        return

    # Phase 2-4: Batch processing
    batch_size = config.batch_size
    total_batches = (len(eligible) + batch_size - 1) // batch_size
    written = 0
    skipped = 0
    total_bytes = 0

    config.output_path.parent.mkdir(parents=True, exist_ok=True)

    temporary_output = config.output_path.with_suffix(config.output_path.suffix + ".tmp")
    if temporary_output.exists():
        temporary_output.unlink()
    with open(temporary_output, "w", encoding="utf-8") as f:
        for bi in range(total_batches):
            batch_start = bi * batch_size
            batch = eligible[batch_start : batch_start + batch_size]
            t_batch = time.time()

            # Populate batch_eps temp table
            con.execute("DROP TABLE IF EXISTS batch_eps;")
            con.execute("CREATE TEMP TABLE batch_eps(episode_id VARCHAR);")
            con.executemany(
                "INSERT INTO batch_eps VALUES (?)",
                [[ep["episode_id"]] for ep in batch],
            )

            # Phase 2: Aggregate all event types for this batch
            lab_data = aggregate_laboratory(con, base)
            dx_data = aggregate_diagnoses(con, base)
            micro_data = aggregate_microbiology(con, base)
            rad_data = aggregate_radiology(con, base)
            triage_data = aggregate_ed_triage(con, base)
            ed_vitals_data = aggregate_ed_vital_signs(con, base)
            transfer_data = aggregate_transfers(con, base)
            icu_data = aggregate_icu_stays(con, base)
            order_data = aggregate_provider_orders(con, base)
            encounter_context = aggregate_encounter_context(con, base)
            omr_data = aggregate_patient_baseline(con, base)
            longitudinal_data = aggregate_longitudinal_refs(con, base)

            rx_data = aggregate_generic_events(
                con, base, "prescription",
                ["drug", "prod_strength", "form_rx", "dose_val_rx", "dose_unit_rx",
                 "route", "doses_per_24_hrs", "starttime"],
                source_filter="%/prescriptions",
            )
            pharm_data = aggregate_generic_events(
                con, base, "pharmacy_order",
                ["medication", "starttime", "stoptime", "route", "frequency",
                 "status", "doses_per_24_hrs"],
                source_filter="%/pharmacy",
            )
            emar_data = aggregate_medication_administrations(con, base)
            proc_data = aggregate_generic_events(
                con, base, "procedure_code",
                ["icd_code", "icd_version"],
                source_filter="%/procedures_icd",
            )
            ed_dx_data = aggregate_generic_events(
                con, base, "ed_diagnosis_code",
                ["seq_num", "icd_code", "icd_version", "icd_title"],
                source_filter="%/diagnosis",
            )
            drg_data = aggregate_generic_events(
                con, base, "drg_code",
                ["drg_code", "description", "drg_severity", "drg_mortality"],
                source_filter="%/drgcodes",
            )
            service_data = aggregate_generic_events(
                con, base, "service_transfer",
                [],
                source_filter="%/services",
            )
            medrecon_data = aggregate_generic_events(
                con, base, "medication_reconciliation",
                ["name", "gsn", "ndc", "etcdescription"],
                source_filter="%/medrecon",
            )
            hcpcs_data = aggregate_generic_events(
                con, base, "hcpcs_event",
                ["hcpcs_cd", "short_description", "chartdate"],
                source_filter="%/hcpcsevents",
            )

            # Phase 3: Load DS documents for this batch
            ds_rows = con.execute(f"""
                SELECT d.episode_id, d.note_id, d.note_seq, d.event_time,
                       d.available_time, d.recorded_time, d.text
                FROM read_parquet('{base}documents.parquet') d
                JOIN batch_eps ON d.episode_id = batch_eps.episode_id
                WHERE d.note_type = 'DS' AND length(d.text) > 0
                ORDER BY d.episode_id, d.note_seq DESC, d.event_time DESC
            """).fetchall()

            ds_by_episode: dict[str, list[dict]] = {}
            for ep_id, note_id, note_seq, event_time, available_time, recorded_time, text in ds_rows:
                ds_by_episode.setdefault(str(ep_id), []).append({
                    "note_id": note_id,
                    "note_seq": note_seq,
                    "event_time": event_time,
                    "available_time": available_time,
                    "recorded_time": recorded_time,
                    "text": text,
                })

            # Phase 4: Assemble and write
            batch_written = 0
            batch_skipped = 0
            for ep in batch:
                ep_id = str(ep["episode_id"])
                ds_note = None
                notes = ds_by_episode.get(ep_id)
                if notes:
                    ds_note = select_ds(notes)

                visit = assemble_visit(
                    episode=ep,
                    patients=patients,
                    age=ep["_age"],
                    sex=ep["_sex"],
                    ds_note=ds_note,
                    lab_data=lab_data,
                    dx_data=dx_data,
                    micro_data=micro_data,
                    rad_data=rad_data,
                    rx_data=rx_data,
                    pharm_data=pharm_data,
                    emar_data=emar_data,
                    proc_data=proc_data,
                    ed_dx_data=ed_dx_data,
                    transfer_data=transfer_data,
                    icu_data=icu_data,
                    drg_data=drg_data,
                    triage_data=triage_data,
                    service_data=service_data,
                    medrecon_data=medrecon_data,
                    omr_data=omr_data,
                    hcpcs_data=hcpcs_data,
                    ed_vitals_data=ed_vitals_data,
                    order_data=order_data,
                    encounter_context=encounter_context,
                    longitudinal_data=longitudinal_data,
                )

                if visit is None:
                    batch_skipped += 1
                    continue

                line = json.dumps(visit, ensure_ascii=False)
                f.write(line + "\n")
                total_bytes += len(line.encode("utf-8"))
                batch_written += 1

            written += batch_written
            skipped += batch_skipped

            con.execute("DROP TABLE IF EXISTS batch_eps;")

            elapsed_batch = time.time() - t_batch
            logger.info(
                "Batch %d/%d: %d written, %d skipped (%.1fs, total %d)",
                bi + 1, total_batches, batch_written, batch_skipped,
                elapsed_batch, written,
            )

    logger.info("Validating complete temporary archive before atomic replacement...")
    validation = validate_archive(temporary_output)
    if validation["invalid_records"] != 0:
        raise RuntimeError(
            f"archive validation failed: {validation['invalid_records']} invalid records"
        )
    if validation["patient_partition_conflicts"] != 0:
        raise RuntimeError(
            "archive validation failed: patient partition conflicts detected"
        )
    temporary_output.replace(config.output_path)

    total_elapsed = time.time() - t0
    stats = {
        "candidate_episodes": len(episodes),
        "eligible_after_age_sex": len(eligible),
        "written": written,
        "skipped": skipped,
        "total_bytes": total_bytes,
        "total_mb": round(total_bytes / (1024 * 1024), 1),
        "avg_bytes_per_visit": total_bytes // written if written else 0,
        "total_elapsed_seconds": round(total_elapsed, 1),
        "validation": validation,
    }
    logger.info("Stats: %s", json.dumps(stats, indent=2))

    config.stats_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config.stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)

    logger.info("Output: %s", config.output_path)
    logger.info("Stats: %s", config.stats_path)
    con.close()


def main():
    parser = argparse.ArgumentParser(
        description="G drive parquet -> visit-level JSONL adapter"
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Limit eligible episodes (0 = no limit)",
    )
    parser.add_argument(
        "--output", type=str, default="",
        help="Output JSONL path override",
    )
    args = parser.parse_args()

    config = Config(limit=args.limit)
    if args.output:
        output_path = Path(args.output)
        config = Config(
            limit=args.limit,
            output_path=output_path,
            stats_path=output_path.with_suffix(".stats.json"),
        )

    run(config)


if __name__ == "__main__":
    main()
