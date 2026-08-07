"""Debug: inspect Follow-up section in a real DS note."""
import gzip
import csv
import re
from pathlib import Path

path = Path(r"D:\Projects\llm_benchmark\data\RawData\mimic-iv-note-2.2\note\discharge.csv.gz")

KNOWN = [
    "Chief Complaint", "History of Present Illness", "Past Medical History",
    "Social History", "Family History", "Physical Exam", "Pertinent Results",
    "Studies", "Brief Hospital Course", "Medications on Admission",
    "Discharge Medications", "Discharge Diagnosis", "Discharge Condition",
    "Discharge Instructions", "Follow-up Instructions", "Followup Instructions",
    "Follow Up Instructions",
]

# Reproduce the exact regex from discharge.py
pattern = re.compile(
    r"^[ \t]*(?P<title>"
    + "|".join(re.escape(title) for title in sorted(KNOWN, key=len, reverse=True))
    + r")[ \t]*:?[ \t]*$",
    flags=re.IGNORECASE | re.MULTILINE,
)

# Now test with SECTION_ALIASES logic
ALIASES = ["Follow-up Instructions", "Followup Instructions", "Follow Up Instructions"]
alias_set = {alias.casefold() for alias in ALIASES}

count = 0
with gzip.open(path, "rt", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        if row.get("note_type") != "DS":
            continue
        count += 1
        if count > 5:
            break

        text = (row.get("text") or "").replace("\r\n", "\n").replace("\r", "\n")
        headings = list(pattern.finditer(text))

        # Find Follow-up heading
        found_followup = False
        for idx, h in enumerate(headings):
            title_cf = h.group("title").casefold()
            if title_cf in alias_set:
                found_followup = True
                end = headings[idx + 1].start() if idx + 1 < len(headings) else len(text)
                content = text[h.end():end].strip()
                print(f"[note {count}] Follow-up heading matched: {h.group('title')!r}")
                print(f"  content length: {len(content)}")
                print(f"  content preview: {content[:200]!r}")
                break

        if not found_followup:
            # Check: does the text contain "Follow" at all?
            follow_lines = [l for l in text.split("\n") if "follow" in l.lower()]
            print(f"[note {count}] NO Follow-up match. Lines containing 'follow': {len(follow_lines)}")
            for fl in follow_lines[:3]:
                print(f"    {fl.strip()[:120]!r}")
        print()
"""Debug: compare Followup vs Discharge Instructions content."""
import gzip
import csv
import re
from pathlib import Path

path = Path(r"D:\Projects\llm_benchmark\data\RawData\mimic-iv-note-2.2\note\discharge.csv.gz")

KNOWN = [
    "Discharge Instructions", "Followup Instructions",
    "Follow-up Instructions", "Discharge Medications",
]
pattern = re.compile(
    r"^[ \t]*(?P<title>"
    + "|".join(re.escape(t) for t in sorted(KNOWN, key=len, reverse=True))
    + r")[ \t]*:?[ \t]*$",
    flags=re.IGNORECASE | re.MULTILINE,
)

stats = {"Discharge Instructions": 0, "Followup Instructions": 0,
          "Follow-up Instructions": 0}
real_content = {"Discharge Instructions": 0, "Followup Instructions": 0,
                 "Follow-up Instructions": 0}

count = 0
with gzip.open(path, "rt", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        if row.get("note_type") != "DS":
            continue
        count += 1
        if count > 1000:
            break
        text = (row.get("text") or "").replace("\r\n", "\n").replace("\r", "\n")
        headings = list(pattern.finditer(text))
        for idx, h in enumerate(headings):
            title = h.group("title")
            if title not in stats:
                continue
            end = headings[idx + 1].start() if idx + 1 < len(headings) else len(text)
            content = text[h.end():end].strip()
            compact = re.sub(r"\s+", "", content)
            stats[title] = stats.get(title, 0) + 1
            if not re.fullmatch(r"_+", compact) and len(compact) > 10:
                real_content[title] = real_content.get(title, 0) + 1

print(f"DS notes scanned: {count}")
print()
print(f"{'Section':30s} {'Found':>6s} {'Has real content':>16s}")
for k in stats:
    print(f"{k:30s} {stats[k]:>6} {real_content[k]:>16}")
