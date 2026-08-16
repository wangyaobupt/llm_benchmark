"""Filter development questions to validation-stable gold rules.

A question is "validated" if its gold rule (class, condition, candidate) is
concordant in the independent validation set (rank-1, or top-3 relaxed).
"""
import argparse
import json
import sys
from pathlib import Path

QUESTIONS = Path(r"D:\Projects\llm_benchmark\tasks\investigation_selection\output\development\questions.jsonl")
VALIDATION = Path(r"D:\Projects\llm_benchmark\tasks\investigation_selection\output\validation\validation_results.jsonl")
OUT = Path(r"D:\Projects\llm_benchmark\tasks\investigation_selection\output\validated")


def _key(r: dict) -> tuple[str, str, str]:
    return (r["class"], r["condition"], r["gold_candidate"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--questions", type=Path, default=QUESTIONS)
    ap.add_argument("--validation", type=Path, default=VALIDATION)
    ap.add_argument("--out-dir", type=Path, default=OUT)
    args = ap.parse_args()

    val = [json.loads(l) for l in args.validation.read_text(encoding="utf-8").splitlines() if l.strip()]
    val_by_key = {_key(r): r for r in val}

    qs = [json.loads(l) for l in args.questions.read_text(encoding="utf-8").splitlines() if l.strip()]

    rank1, top3, dropped = [], [], []
    for q in qs:
        key = (q["comparison_class"], q["condition"], q["answer"])
        v = val_by_key.get(key)
        if v is None or v.get("status") != "checked":
            dropped.append((q, "uncheckable"))
            continue
        q = dict(q)
        q["validation_status"] = "rank1_stable" if v["concordant_rank1"] else "top3_stable"
        q["validation_gold_rank"] = v["gold_rank"]
        q["validation_support"] = v["validation_support"]
        if v["concordant_rank1"]:
            rank1.append(q)
            top3.append(q)
        elif v["concordant_top3"]:
            top3.append(q)
        else:
            dropped.append((q, "discordant"))

    args.out_dir.mkdir(parents=True, exist_ok=True)
    for name, subset in (("validated_rank1.jsonl", rank1),
                         ("validated_top3.jsonl", top3)):
        (args.out_dir / name).write_text(
            "\n".join(json.dumps(x, ensure_ascii=False) for x in subset) + "\n",
            encoding="utf-8")

    manifest = {
        "status": "exploratory_unreviewed",
        "n_development_questions": len(qs),
        "n_rank1_validated": len(rank1),
        "n_top3_validated": len(top3),
        "n_dropped": len(dropped),
        "dropped_uncheckable": sum(1 for _, s in dropped if s == "uncheckable"),
        "dropped_discordant": sum(1 for _, s in dropped if s == "discordant"),
    }
    (args.out_dir / "validated_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print("=" * 78)
    print("VALIDATED QUESTION SET (exploratory)")
    print("=" * 78)
    print(f"development questions : {manifest['n_development_questions']}")
    print(f"rank-1 validated      : {manifest['n_rank1_validated']}")
    print(f"top-3 validated       : {manifest['n_top3_validated']}")
    print(f"dropped               : {manifest['n_dropped']}")
    print(f"  uncheckable         : {manifest['dropped_uncheckable']}")
    print(f"  discordant          : {manifest['dropped_discordant']}")

    by_cls = {}
    for q in rank1:
        by_cls[q["comparison_class"]] = by_cls.get(q["comparison_class"], 0) + 1
    print("rank-1 by class:", by_cls)

    print("\n=== sample validated questions (rank-1) ===")
    for q in rank1[:15]:
        print(f"[{q['comparison_class']}] {q['condition']} -> {q['answer']} "
              f"(rank={q['validation_gold_rank']}, val_support={q['validation_support']})")
    print(f"\nwritten to {args.out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
