"""P4 sign track — run the physical-exam-finding NER (DeepSeek Flash).

Extracts the Physical Exam section per admission, calls DeepSeek Flash with the
focused ``sign_physical_exam.md`` prompt, and writes a sign sidecar
(hadm_id -> sorted physical-exam-finding phrases). Dry-run by default; pass
``--execute`` plus the ``TEXT_NER_*`` environment to make real calls.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_pipeline.archived.phenotype.progress import write_progress  # noqa: E402
from data_pipeline.archived.phenotype.sign_ner import build_physical_exam_frame  # noqa: E402

DOCUMENTS = Path(r"D:\Projects\llm_benchmark\data\ner_v2_v2\documents.parquet")
PROMPT = Path(__file__).resolve().parent / "config" / "prompts" / "sign_physical_exam.md"
OUT = Path(r"D:\Projects\llm_benchmark\data\phenotype\sign_features.parquet")


def _parse_mentions(raw: str) -> list[str]:
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(obj, dict):
        return []
    return [str(m.get("surface_text")) for m in obj.get("mentions", [])
            if isinstance(m, dict) and m.get("entity_type") == "physical_exam_finding"
            and m.get("surface_text")]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--documents", type=Path, default=DOCUMENTS)
    ap.add_argument("--prompt", type=Path, default=PROMPT)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--max-docs", type=int, default=None)
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--env-file", type=Path, default=ROOT / ".env")
    args = ap.parse_args(argv)

    frame = build_physical_exam_frame(args.documents)
    if args.max_docs is not None:
        frame = frame.head(args.max_docs)
    prompt = args.prompt.read_text(encoding="utf-8")

    if not args.execute:
        print(json.dumps({
            "mode": "dry-run",
            "n_admissions": len(frame),
            "prompt": str(args.prompt),
            "hint": "pass --execute with TEXT_NER_* env to make real calls",
        }, ensure_ascii=False, indent=2))
        return 0

    # Load the .env file (project root) into the process environment.
    if args.env_file.exists():
        for line in args.env_file.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

    required = ("TEXT_NER_API_KEY", "TEXT_NER_BASE_URL", "TEXT_NER_MODEL")
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        print("ERROR: missing env: " + ", ".join(missing), file=sys.stderr)
        return 2

    from openai import OpenAI
    client = OpenAI(api_key=os.environ["TEXT_NER_API_KEY"],
                    base_url=os.environ["TEXT_NER_BASE_URL"], timeout=60)
    model = os.environ["TEXT_NER_MODEL"]

    rows: list[dict] = []
    n_total = len(frame)
    t0 = time.time()
    write_progress("sign_ner", {
        "status": "running", "n_total": n_total, "n_done": 0,
        "n_with_signs": 0, "elapsed_s": 0, "recent": [],
    })
    for i, rec in enumerate(frame.itertuples(index=False), 1):
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": rec.physical_exam_text},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
            extra_body={"thinking": {"type": "disabled"}},
        )
        signs = sorted(set(_parse_mentions(resp.choices[0].message.content or "")))
        if signs:
            rows.append({"hadm_id": rec.hadm_id, "features": signs})
        write_progress("sign_ner", {
            "status": "running", "n_total": n_total, "n_done": i,
            "n_with_signs": len(rows), "elapsed_s": round(time.time() - t0, 1),
            "recent": [
                {"hadm_id": r["hadm_id"], "n_signs": len(r["features"])}
                for r in rows[-5:]
            ],
        })
        print(f"[{i}/{n_total}] {rec.hadm_id}: {len(signs)} signs", flush=True)

    out = pd.DataFrame(rows, columns=["hadm_id", "features"])
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(args.out, index=False)
    write_progress("sign_ner", {
        "status": "done", "n_total": n_total, "n_done": n_total,
        "n_with_signs": len(rows), "elapsed_s": round(time.time() - t0, 1),
        "recent": [{"hadm_id": r["hadm_id"], "n_signs": len(r["features"])}
                   for r in rows[-5:]],
    })
    print(json.dumps({
        "mode": "execute", "n_admissions": n_total,
        "n_with_signs": len(rows), "out": str(args.out),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
