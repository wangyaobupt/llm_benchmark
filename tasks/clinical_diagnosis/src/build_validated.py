"""Filter diagnosis questions to validation-stable gold rules."""
import argparse
import json
import sys
from pathlib import Path

QUESTIONS = Path(r"D:\Projects\llm_benchmark\tasks\clinical_diagnosis\output\development\questions.jsonl")
VALIDATION = Path(r"D:\Projects\llm_benchmark\tasks\clinical_diagnosis\output\validation\validation_results.jsonl")
OUT = Path(r"D:\Projects\llm_benchmark\tasks\clinical_diagnosis\output\validated")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--questions", type=Path, default=QUESTIONS)
    ap.add_argument("--validation", type=Path, default=VALIDATION)
    ap.add_argument("--out-dir", type=Path, default=OUT)
    args = ap.parse_args()

    val = [json.loads(l) for l in args.validation.read_text(encoding="utf-8").splitlines() if l.strip()]
    val_by_key = {(r["condition"], r["gold_candidate"]): r for r in val}
    qs = [json.loads(l) for l in args.questions.read_text(encoding="utf-8").splitlines() if l.strip()]

    rank1, top3, dropped = [], [], []
    for q in qs:
        v = val_by_key.get((q["condition"], q["answer"]))
        if v is None or v.get("status") != "checked":
            dropped.append(("uncheckable", q))
            continue
        q = dict(q)
        q["validation_status"] = "rank1_stable" if v["concordant_rank1"] else "top3_stable"
        q["validation_gold_rank"] = v["gold_rank"]
        if v["concordant_rank1"]:
            rank1.append(q); top3.append(q)
        elif v["concordant_top3"]:
            top3.append(q)
        else:
            dropped.append(("discordant", q))

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for name, subset in (("validated_rank1.jsonl", rank1), ("validated_top3.jsonl", top3)):
        (args.out_dir / name).write_text(
            "\n".join(json.dumps(x, ensure_ascii=False) for x in subset) + "\n", encoding="utf-8")
    (args.out_dir / "validated_manifest.json").write_text(json.dumps({
        "status": "exploratory_unreviewed",
        "n_development_questions": len(qs),
        "n_rank1_validated": len(rank1),
        "n_top3_validated": len(top3),
        "n_dropped_uncheckable": sum(1 for s, _ in dropped if s == "uncheckable"),
        "n_dropped_discordant": sum(1 for s, _ in dropped if s == "discordant"),
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"development questions : {len(qs)}")
    print(f"rank-1 validated      : {len(rank1)}")
    print(f"top-3 validated       : {len(top3)}")
    print(f"dropped uncheckable   : {sum(1 for s,_ in dropped if s=='uncheckable')}")
    print(f"dropped discordant    : {sum(1 for s,_ in dropped if s=='discordant')}")
    print("\n=== rank-1 validated ===")
    for q in rank1:
        print(f"  {q['condition']} -> {q['answer']} (rank={q['validation_gold_rank']})")
    print(f"\nwritten to {args.out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
