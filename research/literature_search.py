#!/usr/bin/env python3
"""
RWD Clinical Benchmark -- six-cluster literature search.
Sources: PubMed E-utilities + arXiv API.
Output: research/literature_search_results.json
"""
import urllib.request, urllib.parse, json, time, ssl, re
import xml.etree.ElementTree as ET
from datetime import datetime

ctx = ssl.create_default_context()
UA = "Codex-LitSearch/1.0 (academic research)"

CLUSTERS = {
    "A_medical_llm_benchmark": {
        "desc": "Medical LLM evaluation benchmarks (novelty positioning)",
        "pubmed": '(("large language model"[tiab] OR "LLM"[tiab] OR GPT[tiab] OR ChatGPT[tiab] OR "generative AI"[tiab] OR "foundation model"[tiab]) AND ("medical"[tiab] OR clinical[tiab] OR healthcare[tiab]) AND (benchmark*[tiab] OR evaluation[tiab] OR assessment[tiab]) AND ("multiple choice"[tiab] OR "question answering"[tiab] OR "clinical reasoning"[tiab] OR "medical reasoning"[tiab])) AND ("2022"[dp]:"2026"[dp])',
        "arxiv": '(abs:"large language model" AND abs:medical AND (abs:benchmark OR abs:evaluation) AND (abs:"multiple choice" OR abs:reasoning))',
    },
    "B_ehr_rwd_benchmark": {
        "desc": "EHR / RWD / MIMIC benchmark construction",
        "pubmed": '(("electronic health record"[tiab] OR EHR[tiab] OR MIMIC[tiab] OR "real-world data"[tiab] OR "real world evidence"[tiab]) AND (benchmark*[tiab] OR "question generation"[tiab] OR "evaluation dataset"[tiab] OR "test set"[tiab] OR "clinical question"[tiab]) AND (clinical[tiab] OR medical[tiab])) AND ("2020"[dp]:"2026"[dp])',
        "arxiv": '(abs:MIMIC OR abs:"electronic health record" OR abs:"real-world data") AND (abs:benchmark OR abs:"question generation" OR abs:evaluation)',
    },
    "C_lab_test_order_prediction": {
        "desc": "Lab/test order prediction (Q1 core method reference)",
        "pubmed": '(("laboratory test"[tiab] OR "lab order"[tiab] OR "test order"[tiab] OR "medical order"[tiab] OR "order set"[tiab] OR "clinical order"[tiab] OR "investigation order"[tiab]) AND (predict*[tiab] OR recommend*[tiab] OR anticipat*[tiab] OR "order entry"[tiab]) AND ("electronic health record"[tiab] OR EHR[tiab] OR clinical[tiab] OR "clinical decision support"[tiab])) AND ("2019"[dp]:"2026"[dp])',
        "arxiv": '(abs:"laboratory test" OR abs:"lab order" OR abs:"test order" OR abs:"order prediction") AND (abs:predict OR abs:recommend) AND (abs:"electronic health record" OR abs:EHR OR abs:clinical)',
    },
    "D_association_rule_clinical": {
        "desc": "Association rule / conditional prob / knowledge graph mining from EHR (answer logic basis)",
        "pubmed": '(("association rule"[tiab] OR "conditional probability"[tiab] OR "frequent itemset"[tiab] OR "knowledge graph"[tiab] OR "co-occurrence"[tiab]) AND (clinical[tiab] OR medical[tiab] OR "electronic health record"[tiab] OR EHR[tiab] OR "real-world data"[tiab]) AND (mining[tiab] OR pattern*[tiab] OR learning[tiab])) AND ("2018"[dp]:"2026"[dp])',
        "arxiv": '(abs:"association rule" OR abs:"knowledge graph" OR abs:"conditional probability") AND (abs:clinical OR abs:medical OR abs:"electronic health record" OR abs:EHR) AND (abs:mining OR abs:learning)',
    },
    "E_automatic_mcq_generation": {
        "desc": "Automatic MCQ generation + distractor construction",
        "pubmed": '(("multiple choice question"[tiab] OR MCQ[tiab] OR "question generation"[tiab] OR "item generation"[tiab]) AND (automatic*[tiab] OR generat*[tiab] OR "distractor"[tiab] OR automated[tiab]) AND (medical[tiab] OR clinical[tiab] OR education[tiab] OR "health profession"[tiab])) AND ("2019"[dp]:"2026"[dp])',
        "arxiv": '(abs:"question generation" OR abs:"multiple choice" OR abs:MCQ OR abs:distractor) AND (abs:medical OR abs:clinical OR abs:education) AND (abs:generat OR abs:automat)',
    },
    "F_benchmark_quality_leakage": {
        "desc": "Benchmark QA / data leakage / contamination in medical LLM eval",
        "pubmed": '((benchmark[tiab] OR evaluation[tiab] OR "gold standard"[tiab]) AND ("data leakage"[tiab] OR contamination[tiab] OR validity[tiab] OR "inter-rater"[tiab] OR annotation[tiab] OR reliability[tiab]) AND (medical[tiab] OR clinical[tiab] OR "natural language processing"[tiab] OR NLP[tiab])) AND ("2021"[dp]:"2026"[dp])',
        "arxiv": '(abs:benchmark OR abs:evaluation) AND (abs:"data leakage" OR abs:contamination OR abs:validity) AND (abs:medical OR abs:clinical OR abs:"natural language processing")',
    },
}

PER_CLUSTER = 15


def http_get(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=timeout, context=ctx).read()


def search_pubmed(term, limit):
    enc = urllib.parse.quote(term)
    search_url = (
        f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        f"?db=pubmed&term={enc}&retmax={limit}&retmode=json&sort=relevance"
    )
    data = json.loads(http_get(search_url))
    id_list = data.get("esearchresult", {}).get("idlist", [])
    total = int(data.get("esearchresult", {}).get("count", "0"))
    if not id_list:
        return total, []
    ids_str = ",".join(id_list)
    summ_url = (
        f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
        f"?db=pubmed&id={ids_str}&retmode=json"
    )
    sdata = json.loads(http_get(summ_url))
    recs = []
    for pmid in id_list:
        item = sdata.get("result", {}).get(pmid, {})
        if not item:
            continue
        authors = "; ".join(a.get("name", "") for a in item.get("authors", [])[:4])
        doi = ""
        for aid in item.get("articleids", []):
            if aid.get("idtype") == "doi":
                doi = aid.get("value", "")
        recs.append({
            "source": "PubMed",
            "pmid": pmid,
            "title": item.get("title", "").rstrip("."),
            "authors": authors,
            "journal": item.get("fulljournalname") or item.get("source", ""),
            "year": item.get("pubdate", "")[:4],
            "doi": doi,
        })
    return total, recs


def search_arxiv(query, limit):
    enc = urllib.parse.quote(query)
    url = (
        f"http://export.arxiv.org/api/query?search_query={enc}"
        f"&start=0&max_results={limit}&sortBy=relevance"
    )
    raw = http_get(url)
    root = ET.fromstring(raw)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    total_el = root.find("{http://a9.com/-/spec/opensearch/1.1/}totalResults")
    total = int(total_el.text) if total_el is not None else 0
    recs = []
    for e in root.findall("atom:entry", ns):
        arxiv_id = (e.find("atom:id", ns).text or "").rsplit("/", 1)[-1]
        title = (e.find("atom:title", ns).text or "").strip().replace("\n", " ")
        title = re.sub(r"\s+", " ", title)
        authors = "; ".join(
            (a.find("atom:name", ns).text or "")
            for a in e.findall("atom:author", ns)[:4]
        )
        published = (e.find("atom:published", ns).text or "")[:4]
        summary = (e.find("atom:summary", ns).text or "").strip().replace("\n", " ")
        summary = re.sub(r"\s+", " ", summary)[:250]
        recs.append({
            "source": "arXiv",
            "arxiv_id": arxiv_id,
            "title": title,
            "authors": authors,
            "year": published,
            "abstract": summary,
        })
    return total, recs


def main():
    output = {
        "search_date": datetime.now().isoformat(timespec="seconds"),
        "per_cluster_limit": PER_CLUSTER,
        "clusters": {},
    }
    for key, spec in CLUSTERS.items():
        print(f"\n=== Cluster {key}: {spec['desc']} ===", flush=True)
        cluster = {"description": spec["desc"], "pubmed": {}, "arxiv": {}}
        try:
            pm_total, pm_recs = search_pubmed(spec["pubmed"], PER_CLUSTER)
            cluster["pubmed"] = {"total_found": pm_total, "returned": len(pm_recs), "records": pm_recs}
            print(f"  PubMed: {pm_total} found, {len(pm_recs)} fetched", flush=True)
        except Exception as e:
            cluster["pubmed"] = {"error": str(e)}
            print(f"  PubMed FAIL: {e}", flush=True)
        time.sleep(0.5)
        try:
            ax_total, ax_recs = search_arxiv(spec["arxiv"], PER_CLUSTER)
            cluster["arxiv"] = {"total_found": ax_total, "returned": len(ax_recs), "records": ax_recs}
            print(f"  arXiv:  {ax_total} found, {len(ax_recs)} fetched", flush=True)
        except Exception as e:
            cluster["arxiv"] = {"error": str(e)}
            print(f"  arXiv FAIL: {e}", flush=True)
        output["clusters"][key] = cluster
        time.sleep(1.0)
    outpath = "research/literature_search_results.json"
    with open(outpath, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nWritten to {outpath}", flush=True)
    grand_pm = sum(c.get("pubmed", {}).get("returned", 0) for c in output["clusters"].values())
    grand_ax = sum(c.get("arxiv", {}).get("returned", 0) for c in output["clusters"].values())
    print(f"Totals: PubMed {grand_pm} records, arXiv {grand_ax} records across 6 clusters", flush=True)


if __name__ == "__main__":
    main()
