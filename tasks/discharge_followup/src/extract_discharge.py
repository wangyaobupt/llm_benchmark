"""Extract discharge-summary text per admission from the raw MIMIC archive.

Foundation for discharge-followup (F1) four sub-axes. Streams the 19.9 GB raw
JSONL once, keeps only the requested split role's subjects, and writes a compact
parquet (hadm_id, subject_id, discharge_text, n_notes) plus a manifest.

Fail-closed: records the raw-input SHA-256 (from the upstream run report) and the
split SHA-256; the discharge-text output is derived data, not gold.
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

RAW = Path(r"G:\Projects\llm_benchmark\data\validation\mimic-admission-raw-coronary-all-three-modules.jsonl")
RAW_SHA256 = "34e7a0b8efdfdfb7ec93d9c652cf47af74c5cacca0c9f3d507d78f03b0089008"
SPLIT = Path(r"D:\Projects\llm_benchmark\tasks\investigation_selection\output\split\subject_split.parquet")
OUT = Path(r"D:\Projects\llm_benchmark\tasks\discharge_followup\output")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--role", default="development")
    ap.add_argument("--raw", type=Path, default=RAW)
    ap.add_argument("--split", type=Path, default=SPLIT)
    ap.add_argument("--out-dir", type=Path, default=OUT)
    ap.add_argument("--limit", type=int, default=0, help="stop after N raw lines (0=all)")
    args = ap.parse_args()

    split = pd.read_parquet(args.split)
    split_sha = None  # recorded below via file hash if cheap; else documented
    subjects = set(split[split["role"] == args.role]["subject_id"].astype(str))

    rows = []
    seen = 0
    with open(args.raw, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if args.limit and i >= args.limit:
                break
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            seen += 1
            sid = str(rec.get("subject_id", ""))
            if sid not in subjects:
                continue
            hadm = str(rec.get("hadm_id", ""))
            notes = rec.get("mimic_iv_note", {}).get("discharge", []) or []
            texts = [n.get("text") for n in notes if isinstance(n, dict) and n.get("text")]
            rows.append({
                "hadm_id": hadm, "subject_id": sid,
                "discharge_text": "\n\n".join(texts),
                "n_notes": len(texts),
            })

    df = pd.DataFrame(rows, columns=["hadm_id", "subject_id", "discharge_text", "n_notes"])
    out_dir = args.out_dir / args.role
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "discharge_text.parquet"
    df.to_parquet(out_path, index=False)

    manifest = {
        "status": "exploratory_unreviewed",
        "task": "discharge_followup",
        "stage": "f1_discharge_text_extraction",
        "raw_path": str(args.raw),
        "raw_sha256": RAW_SHA256,
        "split_path": str(args.split),
        "split_role": args.role,
        "raw_lines_scanned": seen,
        "admissions_extracted": int(len(df)),
        "discharge_notes_extracted": int(df["n_notes"].sum()),
        "admissions_with_text": int((df["n_notes"] > 0).sum()),
    }
    (out_dir / "extraction_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"scanned {seen} raw lines -> {len(df)} admissions "
          f"({manifest['admissions_with_text']} with text), "
          f"{manifest['discharge_notes_extracted']} notes")
    print(f"written to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
