"""DeepSeek MCQ evaluation over generated investigation-selection questions.

Exploratory / unreviewed. Sends only the question stem (short symptom
descriptors) and option labels to the configured OpenAI-compatible endpoint;
it does NOT send MIMIC free text, notes, or identifiers.

Options are deterministically shuffled per question (seeded by question_id)
so the gold letter is not always "A".
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
from pathlib import Path

DEFAULT_QUESTIONS = (
    Path(__file__).resolve().parents[3]
    / "tasks" / "investigation_selection" / "output" / "validated" / "validated_rank1.jsonl"
)
DEFAULT_ENV = Path(__file__).resolve().parents[3] / ".env"


def _load_env_file(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def _resolve(key: str, env_file: dict[str, str], default: str | None = None) -> str | None:
    return os.environ.get(key) or env_file.get(key) or default


def _parse_letter(text: str) -> str | None:
    """Extract the first standalone A/B/C/D letter from a model reply."""
    if not text:
        return None
    m = re.search(r"\b([A-D])\b", text.upper())
    return m.group(1) if m else None


def _shuffle_options(options: list[str], seed: int) -> tuple[list[str], int]:
    """Deterministic shuffle; returns (shuffled, correct_index)."""
    idx = list(range(len(options)))
    rng = random.Random(seed)
    rng.shuffle(idx)
    shuffled = [options[i] for i in idx]
    return shuffled, idx.index(0)


def build_prompt(stem: str, options: list[str]) -> str:
    letters = "ABCDEFGH"
    lines = [f"{letters[i]}. {options[i]}" for i in range(len(options))]
    return (
        "You are answering a single multiple-choice question about clinical "
        "decision-making.\n\n"
        f"Question: {stem}\n\n" + "\n".join(lines)
        + "\n\nAnswer with only the single letter (A, B, C, or D) of the best "
          "option."
    )


def evaluate(questions: list[dict], client, model: str,
             provider: str, max_questions: int | None = None) -> list[dict]:
    results: list[dict] = []
    for q in questions[:max_questions]:
        seed = int.from_bytes(q["question_id"].encode("utf-8"), "big") % (2**32)
        shuffled, correct_idx = _shuffle_options(q["options"], seed)
        correct_letter = "ABCDEFGH"[correct_idx]
        rec = {
            "question_id": q["question_id"],
            "class": q["comparison_class"],
            "condition": q["condition"],
            "gold": q["answer"],
            "correct_letter": correct_letter,
            "gold_basis": q.get("gold_basis"),
        }
        try:
            kwargs: dict = dict(
                model=model,
                messages=[{"role": "user", "content": build_prompt(q["stem"], shuffled)}],
                temperature=0.0,
                max_tokens=64,
            )
            if provider == "deepseek":
                kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
            resp = client.chat.completions.create(**kwargs)
            content = (resp.choices[0].message.content or "").strip()
            letter = _parse_letter(content)
            rec["model_answer"] = content
            rec["parsed_letter"] = letter
            rec["correct"] = (letter == correct_letter)
            rec["usage"] = {
                "prompt_tokens": getattr(resp.usage, "prompt_tokens", None),
                "completion_tokens": getattr(resp.usage, "completion_tokens", None),
            }
        except Exception as e:  # noqa: BLE001
            rec["error"] = repr(e)
            rec["correct"] = None
        results.append(rec)
    return results


def _accuracy(results: list[dict]) -> dict:
    scored = [r for r in results if r.get("correct") is not None]
    by_class: dict[str, list[dict]] = {}
    for r in scored:
        by_class.setdefault(r["class"], []).append(r)
    out = {
        "total_scored": len(scored),
        "total_errors": sum(1 for r in results if r.get("correct") is None),
        "accuracy": round(sum(r["correct"] for r in scored) / len(scored), 4)
                    if scored else None,
        "by_class": {},
    }
    for cls, rs in sorted(by_class.items()):
        out["by_class"][cls] = {
            "n": len(rs),
            "accuracy": round(sum(r["correct"] for r in rs) / len(rs), 4),
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS)
    ap.add_argument("--env-file", type=Path, default=DEFAULT_ENV)
    ap.add_argument("--max-questions", type=int, default=None)
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--base-url", type=str, default=None)
    ap.add_argument("--model", type=str, default=None)
    ap.add_argument("--provider", type=str, default=None)
    args = ap.parse_args()

    if not args.questions.exists():
        print(f"missing questions: {args.questions}")
        return 2
    env = _load_env_file(args.env_file)
    base_url = args.base_url or _resolve("TEXT_NER_BASE_URL", env, "https://api.deepseek.com")
    model = args.model or _resolve("TEXT_NER_MODEL", env, "deepseek-v4-flash")
    provider = args.provider or _resolve("TEXT_NER_PROVIDER", env, "deepseek")
    api_key = _resolve("TEXT_NER_API_KEY", env)
    if not api_key:
        print("no TEXT_NER_API_KEY (set it in .env or process env)")
        return 2

    questions = [json.loads(l) for l in args.questions.read_text(encoding="utf-8").splitlines() if l.strip()]

    from openai import OpenAI
    client = OpenAI(api_key=api_key, base_url=base_url)

    results = evaluate(questions, client, model, provider, args.max_questions)
    acc = _accuracy(results)

    print("=" * 78)
    print("MCQ EVALUATION — exploratory (unreviewed)")
    print("=" * 78)
    print(f"questions scored : {acc['total_scored']}")
    print(f"errors           : {acc['total_errors']}")
    print(f"overall accuracy : {acc['accuracy']}")
    print("per class:")
    for cls, v in acc["by_class"].items():
        print(f"  {cls:<16} n={v['n']:<3} acc={v['accuracy']}")

    if args.out_dir is not None:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        (args.out_dir / "eval_results.json").write_text(
            json.dumps({"accuracy": acc, "results": results},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        (args.out_dir / "eval_results.jsonl").write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in results) + "\n",
            encoding="utf-8")
        print(f"\nresults written to {args.out_dir}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
