#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GS supplementary results: dedup, BibTeX, Zotero import."""
import json, re, os, sys, time, urllib.request, ssl

HERE = os.path.dirname(os.path.abspath(__file__))

GS_DATA = {}  # populated by load below

def normalize_title(t):
    return re.sub(r'[^a-z0-9]', '', t.lower())[:80]

def extract_arxiv_id(href, journal):
    m = re.search(r'(2[0-9]{3}\.[0-9]{4,5})', (href or '') + ' ' + (journal or ''))
    return m.group(1) if m else ''

def extract_doi(href):
    m = re.search(r'(10\.\d{4,}/[^\s"\'<>]+)', href or '')
    return m.group(1).rstrip(').') if m else ''

def make_key(authors, year, title):
    fa = re.sub(r'[^a-z]', '', (authors or 'anon').split(',')[0].strip().split()[-1].lower())
    w = re.sub(r'[^a-z]', '', (title or 'x').lower().split()[0])
    return f"{fa}{year}{w}"

def to_bib(rec):
    key = make_key(rec['authors'], rec['year'], rec['title'])
    authors = ' and '.join(a.strip() for a in rec['authors'].split(','))
    aid = extract_arxiv_id(rec.get('href',''), rec.get('journal',''))
    doi = extract_doi(rec.get('href',''))
    jl = rec.get('journal','').lower()
    confs = ['neurips','naacl','eacl','iclr','aaai','findings','ecir','icce','sbie','biostec','sedu','amia','acl ']
    etype = '@inproceedings' if any(c in jl for c in confs) else '@article'
    L = [f"{etype}{{{key},", f"  title = {{{rec['title']}}},", f"  author = {{{authors}}},",
         f"  year = {{{rec['year']}}},", f"  journal = {{{rec['journal']}}},"]
    if doi: L.append(f"  doi = {{{doi}}},")
    if aid: L += [f"  eprint = {{{aid}}},", "  archiveprefix = {arXiv},"]
    if rec.get('href'): L.append(f"  url = {{{rec['href']}}},")
    L.append(f"  note = {{GS cited:{rec.get('citedBy','0')} cluster:{rec['cluster']}}},")
    L.append("}")
    return '\n'.join(L)

def import_to_zotero(bib_path):
    """Import BibTeX to Zotero via connector with extended timeout."""
    with open(bib_path, 'r', encoding='utf-8') as f:
        bib_text = f.read()
    # Split into chunks of ~30 entries
    entries = re.split(r'\n\n+', bib_text.strip())
    chunks = [entries[i:i+30] for i in range(0, len(entries), 30)]
    ctx = ssl.create_default_context()
    total_imported = 0
    for ci, chunk in enumerate(chunks):
        payload = json.dumps({"text": '\n\n'.join(chunk)}).encode('utf-8')
        req = urllib.request.Request(
            "http://127.0.0.1:23119/connector/import",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST")
        try:
            resp = urllib.request.urlopen(req, timeout=120, context=ctx)
            result = json.loads(resp.read())
            n = len(result) if isinstance(result, list) else 1
            total_imported += n
            print(f"  Chunk {ci+1}/{len(chunks)}: imported {n} items")
        except Exception as e:
            print(f"  Chunk {ci+1}/{len(chunks)}: ERROR {e}")
        time.sleep(2)
    return total_imported

def main():
    raw_path = os.path.join(HERE, 'gs_supplementary_results.json')
    with open(raw_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    new_records = data['new']
    print(f"Processing {len(new_records)} new GS records")

    # Generate BibTeX
    bib_path = os.path.join(HERE, 'gs_supplementary_refs.bib')
    seen_keys = {}
    with open(bib_path, 'w', encoding='utf-8') as f:
        for r in new_records:
            entry = to_bib(r)
            k = make_key(r['authors'], r['year'], r['title'])
            if k in seen_keys:
                seen_keys[k] += 1
                entry = entry.replace('{' + k + ',', '{' + k + '_' + str(seen_keys[k]) + ',', 1)
            else:
                seen_keys[k] = 0
            f.write(entry + '\n\n')
    print(f"BibTeX written: {bib_path}")

    # Import to Zotero
    if '--no-import' not in sys.argv:
        print("Importing to Zotero...")
        n = import_to_zotero(bib_path)
        print(f"Total imported to Zotero: {n}")

    # Summary
    for c in sorted(set(r['cluster'] for r in new_records)):
        n = sum(1 for r in new_records if r['cluster'] == c)
        print(f"  {c}: {n}")

if __name__ == '__main__':
    main()
