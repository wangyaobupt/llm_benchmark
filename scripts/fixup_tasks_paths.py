"""One-shot fixup: after moving the 5 dimensions into tasks/, rewrite hardcoded
absolute paths and parents[N] bootstraps so imports and file references work.

Rules:
- absolute path prefix D:\\Projects\\llm_benchmark\\<dim> -> ...\\tasks\\<dim>
- parents[N]: a file at tasks/<dim>/src/<k-subdirs>/x.py pointed at the project
  root via parents[2+k]; now it is parents[3+k]. So bump parents[2+k] -> parents[3+k].
"""
import sys
from pathlib import Path

TASKS = Path(r"D:\Projects\llm_benchmark\tasks")

ABS_REPL = {
    r"D:\Projects\llm_benchmark\investigation_selection":
        r"D:\Projects\llm_benchmark\tasks\investigation_selection",
    r"D:\Projects\llm_benchmark\clinical_diagnosis":
        r"D:\Projects\llm_benchmark\tasks\clinical_diagnosis",
    r"D:\Projects\llm_benchmark\treatment":
        r"D:\Projects\llm_benchmark\tasks\treatment",
    r"D:\Projects\llm_benchmark\referral":
        r"D:\Projects\llm_benchmark\tasks\referral",
    r"D:\Projects\llm_benchmark\discharge_followup":
        r"D:\Projects\llm_benchmark\tasks\discharge_followup",
}


def main() -> int:
    changed = []
    for py in sorted(TASKS.rglob("*.py")):
        rel = py.relative_to(TASKS)
        parts = rel.parts  # e.g. ('treatment', 'src', 'run.py')
        text = py.read_text(encoding="utf-8")
        orig = text
        for old, new in ABS_REPL.items():
            text = text.replace(old, new)
        # parents[N] bump only for files under <dim>/src/... (skip dim-root scripts)
        if len(parts) >= 3 and parts[1] == "src":
            k = len(parts) - 3  # 0 = direct src child, 1 = src/explore child, ...
            text = text.replace(f"parents[{2 + k}]", f"parents[{3 + k}]")
        if text != orig:
            py.write_text(text, encoding="utf-8")
            changed.append(str(rel))
    print(f"changed {len(changed)} files")
    for c in changed:
        print("  ", c)
    return 0


if __name__ == "__main__":
    sys.exit(main())
