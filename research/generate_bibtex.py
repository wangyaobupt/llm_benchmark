#!/usr/bin/env python3
"""
Convert literature_search_results.json to BibTeX for Zotero import.
PubMed: fetch via eutils efetch (rettype=medline, parse to BibTeX).
arXiv: construct BibTeX from API metadata.
"""
import json, urllib.request, urllib.parse, re, time, ssl

ctx = ssl.create_default_context()
UA = "Codex-LitSearch/1.0"


def http_get(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=timeout, context=ctx).read()


def pubmed_to_bibtex(pmids):
    """Batch fetch PubMed records and convert to BibTeX entries."""
    if not pmids:
        return []
    ids = ",".join(pmids)
    # Use efetch to get full records in XML
    url = (
        f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        f"?db=pubmed&id={ids}&rettype=abstract&retmode=xml"
    )
    raw = http_get(url)
    import xml.etree.ElementTree as ET
    root = ET.fromstring(raw)
    entries = []
    for art in root.findall(".//PubmedArticle"):
        pmid_el = art.find(".//PMID")
        pmid = pmid_el.text if pmid_el is not None else ""
        title_el = art.find(".//ArticleTitle")
        title = "".join(title_el.itertext()).strip() if title_el is not None else ""
        title = title.rstrip(".")

        # Year
        year = ""
        for yp in [".//PubDate/Year", ".//PubDate/MedlineDate"]:
            el = art.find(yp)
            if el is not None and el.text:
                m = re.search(r"\d{4}", el.text)
                if m:
                    year = m.group()
                    break

        # Journal
        journal_el = art.find(".//Journal/Title")
        journal = journal_el.text.strip() if journal_el is not None and journal_el.text else ""

        # Authors
        authors = []
        for au in art.findall(".//Author"):
            ln = au.find("LastName")
            fn = au.find("ForeName")
            if ln is not None and ln.text:
                name = ln.text
                if fn is not None and fn.text:
                    name += ", " + fn.text
                authors.append(name)

        # DOI
        doi = ""
        for aid in art.findall(".//ArticleId"):
            if aid.get("IdType") == "doi":
                doi = aid.text.strip()
                break
        if not doi:
            for eid in art.findall(".//ELocationID"):
                if eid.get("EIdType") == "doi":
                    doi = eid.text.strip()
                    break

        # Volume, issue, pages
        vol_el = art.find(".//Volume")
        vol = vol_el.text if vol_el is not None and vol_el.text else ""
        iss_el = art.find(".//Issue")
        iss = iss_el.text if iss_el is not None and iss_el.text else ""
        pages_el = art.find(".//MedlinePgn")
        pages = pages_el.text if pages_el is not None and pages_el.text else ""

        # Abstract
        abs_parts = []
        for ap in art.findall(".//Abstract/AbstractText"):
            abs_parts.append("".join(ap.itertext()).strip())
        abstract = " ".join(abs_parts)[:500] if abs_parts else ""

        cite_key = re.sub(r"[^a-zA-Z0-9]", "",
                          (authors[0].split(",")[0] if authors else "anon")) + year + "pm"
        cite_key = cite_key.lower()

        lines = [f"@article{{{cite_key},"]
        lines.append(f"  title = {{{title}}},")
        if authors:
            au_str = " and ".join(authors[:6])
            lines.append(f"  author = {{{au_str}}},")
        if journal:
            lines.append(f"  journal = {{{journal}}},")
        if year:
            lines.append(f"  year = {{{year}}},")
        if vol:
            lines.append(f"  volume = {{{vol}}},")
        if iss:
            lines.append(f"  number = {{{iss}}},")
        if pages:
            lines.append(f"  pages = {{{pages}}},")
        if doi:
            lines.append(f"  doi = {{{doi}}},")
        if abstract:
            lines.append(f"  abstract = {{{abstract}}},")
        lines.append(f"  pubmed_id = {{{pmid}}},")
        lines.append("}")
        entries.append("\n".join(lines))
    return entries


def arxiv_to_bibtex(records):
    """Construct BibTeX from arXiv API metadata."""
    entries = []
    for r in records:
        arxiv_id = r.get("arxiv_id", "")
        title = r.get("title", "").rstrip(".")
        authors_raw = r.get("authors", "")
        year = r.get("year", "")
        abstract = r.get("abstract", "")

        # Build cite key
        first_author = authors_raw.split(";")[0].strip() if authors_raw else "anon"
        last_name = first_author.split()[-1] if first_author != "anon" else "anon"
        cite_key = re.sub(r"[^a-zA-Z0-9]", "", last_name).lower() + year + "arx"

        # Parse authors for BibTeX
        au_list = [a.strip() for a in authors_raw.split(";") if a.strip()]
        au_str = " and ".join(au_list[:6])

        lines = [f"@misc{{{cite_key},"]
        lines.append(f"  title = {{{title}}},")
        if au_str:
            lines.append(f"  author = {{{au_str}}},")
        if year:
            lines.append(f"  year = {{{year}}},")
        lines.append(f"  eprint = {{{arxiv_id}}},")
        lines.append(f"  archiveprefix = {{arXiv}},")
        lines.append(f"  url = {{https://arxiv.org/abs/{arxiv_id}}},")
        if abstract:
            lines.append(f"  abstract = {{{abstract}}},")
        lines.append("}")
        entries.append("\n".join(lines))
    return entries


def main():
    with open("research/literature_search_results.json", encoding="utf-8") as f:
        data = json.load(f)

    all_pmids = []
    arxiv_recs = []
    cluster_map = {}  # pmid/arxivid -> cluster

    for key, c in data["clusters"].items():
        for r in c.get("pubmed", {}).get("records", []):
            pmid = r.get("pmid", "")
            if pmid:
                all_pmids.append(pmid)
                cluster_map[pmid] = key
        for r in c.get("arxiv", {}).get("records", []):
            aid = r.get("arxiv_id", "")
            if aid:
                arxiv_recs.append(r)
                cluster_map[aid] = key

    print(f"PMIDs to fetch: {len(all_pmids)}", flush=True)
    print(f"arXiv records: {len(arxiv_recs)}", flush=True)

    # Fetch PubMed in batches of 20
    pm_entries = []
    for i in range(0, len(all_pmids), 20):
        batch = all_pmids[i:i+20]
        try:
            entries = pubmed_to_bibtex(batch)
            pm_entries.extend(entries)
            print(f"  PubMed batch {i//20+1}: {len(entries)} entries", flush=True)
        except Exception as e:
            print(f"  PubMed batch {i//20+1} FAIL: {e}", flush=True)
        time.sleep(0.5)

    # arXiv entries
    ax_entries = arxiv_to_bibtex(arxiv_recs)
    print(f"arXiv entries: {len(ax_entries)}", flush=True)

    # Deduplicate cite keys
    seen_keys = set()
    all_entries = []
    for entry in pm_entries + ax_entries:
        m = re.match(r"@\w+\{([^,]+),", entry)
        key = m.group(1) if m else ""
        if key in seen_keys:
            key = key + "_" + str(len(seen_keys))
            entry = re.sub(r"(@\w+\{)([^,]+),", rf"\g<1>{key},", entry, count=1)
        seen_keys.add(key)
        all_entries.append(entry)

    bib_content = "\n\n".join(all_entries)
    outpath = "research/rwd_benchmark_refs.bib"
    with open(outpath, "w", encoding="utf-8") as f:
        f.write(bib_content)
    print(f"\nWritten {len(all_entries)} entries to {outpath}", flush=True)


if __name__ == "__main__":
    main()
