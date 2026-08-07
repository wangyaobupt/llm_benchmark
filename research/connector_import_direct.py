#!/usr/bin/env python3
"""Import BibTeX to Zotero via connector with extended timeout."""
import urllib.request, urllib.parse, json, time, os, re, sys, uuid

BASE = "http://127.0.0.1:23119"
BIB_FILE = "research/rwd_benchmark_refs.bib"
BATCH = 5
TIMEOUT = 90


def connector_import(bibtex_text):
    session = f"codex-{uuid.uuid4().hex}"
    path = f"/connector/import?session={session}"
    data = bibtex_text.encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}{path}", data=data, method="POST",
        headers={"Content-Type": "text/plain;charset=UTF-8"},
    )
    r = urllib.request.urlopen(req, timeout=TIMEOUT)
    return json.loads(r.read())


def get_selected_collection():
    req = urllib.request.Request(
        f"{BASE}/connector/getSelectedCollection",
        data=b"{}", method="POST",
        headers={"Content-Type": "application/json"},
    )
    r = urllib.request.urlopen(req, timeout=10)
    return json.loads(r.read())


def split_bibtex(content):
    entries = re.split(r"\n(?=@)", content)
    return [e.strip() for e in entries if e.strip()]


def main():
    try:
        coll = get_selected_collection()
        print(f"Collection: {coll.get('name', '?')} (id={coll.get('id', '?')})", flush=True)
    except Exception as e:
        print(f"Connector unreachable: {e}", flush=True)
        return
    with open(BIB_FILE, encoding="utf-8") as f:
        content = f.read()
    entries = split_bibtex(content)
    print(f"Entries: {len(entries)}, batch={BATCH}, timeout={TIMEOUT}s", flush=True)
    ok = 0
    fail = 0
    for i in range(0, len(entries), BATCH):
        batch = entries[i:i + BATCH]
        num = i // BATCH + 1
        total = (len(entries) + BATCH - 1) // BATCH
        try:
            result = connector_import("\n\n".join(batch))
            items = result.get("items", [])
            ok += len(items)
            print(f"  Batch {num}/{total}: {len(items)} ok", flush=True)
        except Exception as e:
            fail += len(batch)
            print(f"  Batch {num}/{total} FAIL: {e}", flush=True)
        time.sleep(1)
    print(f"\nDone: {ok} imported, {fail} failed", flush=True)


if __name__ == "__main__":
    main()
