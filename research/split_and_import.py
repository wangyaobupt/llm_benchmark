#!/usr/bin/env python3
"""Split BibTeX into chunks and import each into Zotero via connector."""
import subprocess, sys, re, time, os

BIB = "research/rwd_benchmark_refs.bib"
CHUNK = 25
ZPY = r"C:\Users\Fan\.codex\plugins\cache\openai-curated-remote\zotero\0.1.2\skills\zotero\scripts\zotero.py"

with open(BIB, encoding="utf-8") as f:
    content = f.read()

# Split into individual entries
entries = re.split(r"\n(?=@)", content)
entries = [e.strip() for e in entries if e.strip()]
print(f"Total entries: {len(entries)}", flush=True)

chunks = [entries[i:i+CHUNK] for i in range(0, len(entries), CHUNK)]
print(f"Chunks: {len(chunks)} (size={CHUNK})", flush=True)

tmpdir = "research/_bib_chunks"
os.makedirs(tmpdir, exist_ok=True)

success = 0
fail = 0
for idx, chunk in enumerate(chunks):
    chunk_path = os.path.join(tmpdir, f"chunk_{idx:02d}.bib")
    with open(chunk_path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(chunk))
    print(f"  Chunk {idx+1}/{len(chunks)}: {len(chunk)} entries -> {chunk_path}", flush=True)
    r = subprocess.run(
        [sys.executable, ZPY, "import-bibtex", "--file", os.path.abspath(chunk_path), "--yes"],
        capture_output=True, text=True, timeout=120, env={**os.environ, "PYTHONUTF8": "1"}
    )
    if r.returncode == 0:
        success += len(chunk)
        print(f"    OK", flush=True)
    else:
        fail += len(chunk)
        # Show last 200 chars of stderr/stdout
        detail = (r.stderr or r.stdout or "")[-200:]
        print(f"    FAIL: {detail.strip()}", flush=True)
    time.sleep(2)

print(f"\nDone: {success} imported, {fail} failed", flush=True)
