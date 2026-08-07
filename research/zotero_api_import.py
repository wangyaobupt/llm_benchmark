#!/usr/bin/env python3
"""
Import literature into Zotero via local API (bypasses connector timeout).
Converts literature_search_results.json records to Zotero item templates.
"""
import urllib.request, json, time, re, sys

BASE = "http://127.0.0.1:23119"
COLLECTION_KEY = "K3GSQR4X"
TAG = "RWD-Benchmark-LitReview"
BATCH_SIZE = 10


def api_post(path, payload, timeout=30):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}{path}", data=data, method="POST",
        headers={"Content-Type": "application/json"},
    )
    r = urllib.request.urlopen(req, timeout=timeout)
    return r.status, json.loads(r.read())


def parse_authors_bibtex(au_str):
    authors = []
    for part in au_str.split(" and "):
        part = part.strip()
        if "," in part:
            ln, fn = part.split(",", 1)
            authors.append({"creatorType": "author", "lastName": ln.strip(), "firstName": fn.strip()})
        elif part:
            words = part.split()
            if len(words) >= 2:
                authors.append({"creatorType": "author", "lastName": words[-1], "firstName": " ".join(words[:-1])})
            else:
                authors.append({"creatorType": "author", "lastName": part})
    return authors


def pubmed_to_items(records):
    items = []
    for r in records:
        item = {
            "itemType": "journalArticle",
            "title": r.get("title", ""),
            "tags": [{"tag": TAG}, {"tag": "PubMed"}],
            "collections": [COLLECTION_KEY],
        }
        if r.get("doi"):
            item["DOI"] = r["doi"]
        if r.get("year"):
            item["date"] = r["year"]
        if r.get("journal"):
            item["publicationTitle"] = r["journal"]
        if r.get("authors"):
            item["creators"] = parse_authors_bibtex(r["authors"])
        if r.get("pmid"):
            item["extra"] = f"PMID: {r['pmid']}"
        items.append(item)
    return items


def arxiv_to_items(records):
    items = []
    for r in records:
        item = {
            "itemType": "preprint",
            "title": r.get("title", ""),
            "tags": [{"tag": TAG}, {"tag": "arXiv"}],
            "collections": [COLLECTION_KEY],
            "repository": "arXiv",
            "archiveID": r.get("arxiv_id", ""),
        }
        if r.get("year"):
            item["date"] = r["year"]
        if r.get("abstract"):
            item["abstractNote"] = r["abstract"]
        if r.get("authors"):
            item["creators"] = parse_authors_bibtex(r["authors"])
        if r.get("arxiv_id"):
            item["url"] = f"https://arxiv.org/abs/{r['arxiv_id']}"
        items.append(item)
    return items


def main():
    with open("research/literature_search_results.json", encoding="utf-8") as f:
        data = json.load(f)

    all_items = []
    for key, c in data["clusters"].items():
        pm_recs = c.get("pubmed", {}).get("records", [])
        ax_recs = c.get("arxiv", {}).get("records", [])
        items = pubmed_to_items(pm_recs) + arxiv_to_items(ax_recs)
        for it in items:
            it["tags"].append({"tag": key})
        all_items.extend(items)
        print(f"  {key}: {len(pm_recs)} PubMed + {len(ax_recs)} arXiv = {len(items)} items", flush=True)

    print(f"\nTotal items to import: {len(all_items)}", flush=True)

    success_count = 0
    fail_count = 0
    for i in range(0, len(all_items), BATCH_SIZE):
        batch = all_items[i:i + BATCH_SIZE]
        try:
            status, result = api_post("/api/users/0/items", batch)
            s = len(result.get("success", {}))
            f_count = len(result.get("failed", {}))
            success_count += s
            fail_count += f_count
            failed_details = result.get("failed", {})
            errs = []
            for idx, info in list(failed_details.items())[:2]:
                errs.append(f"  [{idx}] {info.get('message', str(info))[:100]}")
            print(f"  Batch {i//BATCH_SIZE+1}: {s} ok, {f_count} fail", flush=True)
            if errs:
                for e in errs:
                    print(f"    {e}", flush=True)
        except Exception as e:
            fail_count += len(batch)
            print(f"  Batch {i//BATCH_SIZE+1} ERROR: {e}", flush=True)
        time.sleep(1)

    print(f"\nDone: {success_count} imported, {fail_count} failed", flush=True)


if __name__ == "__main__":
    main()
