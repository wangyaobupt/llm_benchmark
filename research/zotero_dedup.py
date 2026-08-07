#!/usr/bin/env python3
"""Deduplicate Zotero items in C246 imported on 2026-08-06."""
import json, urllib.request, re, time, os

BASE = "http://127.0.0.1:23119/api/users/0"
COLLECTION = "C246"
TARGET_DATE = "2026-08-06"

def norm_title(t):
    return re.sub(r'[^a-z0-9]', '', (t or '').lower())[:80]

def fetch_all_items():
    all_items = []
    start = 0
    while True:
        url = f"{BASE}/collections/{COLLECTION}/items/top?limit=100&start={start}&format=json"
        batch = json.loads(urllib.request.urlopen(url, timeout=15).read())
        if not batch:
            break
        all_items.extend(batch)
        start += len(batch)
    return all_items

def metadata_richness(it):
    d = it.get('data', {})
    fields = ['title', 'creators', 'abstractNote', 'date', 'DOI', 'url',
              'publicationTitle', 'volume', 'pages', 'issue', 'itemType',
              'tags', 'extra', 'libraryCatalog']
    return sum(1 for f in fields if d.get(f))

def find_duplicates(items):
    groups = {}
    for it in items:
        d = it.get('data', {})
        nt = norm_title(d.get('title', ''))
        if not nt:
            continue
        groups.setdefault(nt, []).append(it)
    to_delete = []
    audit = []
    for nt, group in groups.items():
        if len(group) <= 1:
            continue
        group.sort(key=lambda it: (metadata_richness(it), it.get('data', {}).get('dateAdded', '')),
                   reverse=True)
        keep = group[0]
        dups = group[1:]
        to_delete.extend(it['key'] for it in dups)
        audit.append({
            'title': keep.get('data', {}).get('title', '')[:100],
            'keep_key': keep['key'],
            'dup_count': len(group),
            'deleted_keys': [it['key'] for it in dups]
        })
    return to_delete, audit

def delete_item(key):
    req = urllib.request.Request(f"{BASE}/items/{key}", method='DELETE')
    try:
        r = urllib.request.urlopen(req, timeout=10)
        return r.status in (200, 204)
    except Exception as e:
        print(f"  DELETE {key} failed: {e}")
        return False

def main():
    print(f"Fetching items from C246 dated {TARGET_DATE}...")
    all_items = fetch_all_items()
    ours = [it for it in all_items if it.get('data', {}).get('dateAdded', '')[:10] == TARGET_DATE]
    print(f"  Total in C246: {len(all_items)}, on {TARGET_DATE}: {len(ours)}")

    to_delete, audit = find_duplicates(ours)
    print(f"  Duplicate groups: {len(audit)}")
    print(f"  Items to delete: {len(to_delete)}")
    if not to_delete:
        print("No duplicates found.")
        return

    here = os.path.dirname(os.path.abspath(__file__))
    audit_path = os.path.join(here, 'zotero_dedup_audit.json')
    with open(audit_path, 'w', encoding='utf-8') as f:
        json.dump({'date': TARGET_DATE, 'collection': COLLECTION,
                   'total_scanned': len(ours), 'dup_groups': len(audit),
                   'deleted_count': len(to_delete), 'details': audit}, f,
                  indent=2, ensure_ascii=False)
    print(f"Audit saved: {audit_path}")

    print("\nDeleting duplicate items...")
    ok, fail = 0, 0
    for i, key in enumerate(to_delete):
        if delete_item(key):
            ok += 1
        else:
            fail += 1
        if (i + 1) % 50 == 0:
            print(f"  Progress: {i+1}/{len(to_delete)} ({ok} ok, {fail} fail)")
        time.sleep(0.1)

    print(f"\nDone: {ok} deleted, {fail} failed")
    print(f"Remaining unique items from {TARGET_DATE}: {len(ours) - ok}")

if __name__ == '__main__':
    main()
