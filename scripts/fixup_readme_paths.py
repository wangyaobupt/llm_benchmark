"""One-shot fixup: update README run-command paths after moving dims into tasks/."""
import sys
from pathlib import Path

TASKS = Path(r"D:\Projects\llm_benchmark\tasks")

# (readme_path, [(old, new), ...])
PLANS = {
    "treatment/README.md": [
        ("treatment/src/", "tasks/treatment/src/"),
    ],
    "referral/README.md": [
        ("referral/src/", "tasks/referral/src/"),
    ],
    "investigation_selection/README.md": [
        (".\\investigation_selection\\src\\", ".\\tasks\\investigation_selection\\src\\"),
    ],
    "clinical_diagnosis/README.md": [
        (".\\clinical_diagnosis\\src\\", ".\\tasks\\clinical_diagnosis\\src\\"),
    ],
    "discharge_followup/README.md": [
        ("discharge_followup/src/", "tasks/discharge_followup/src/"),
    ],
}


def main() -> int:
    for rel, repls in PLANS.items():
        p = TASKS / rel
        text = p.read_text(encoding="utf-8")
        for old, new in repls:
            n = text.count(old)
            text = text.replace(old, new)
            print(f"{rel}: replaced {n} x {old!r}")
        p.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
