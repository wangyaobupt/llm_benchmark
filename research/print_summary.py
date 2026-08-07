#!/usr/bin/env python3
import json, sys

with open('research/literature_search_results.json', encoding='utf-8') as f:
    data = json.load(f)

show = int(sys.argv[1]) if len(sys.argv) > 1 else 8

for key, c in data['clusters'].items():
    print()
    print('=== {} : {} ==='.format(key, c['description']))
    pm = c.get('pubmed', {})
    ax = c.get('arxiv', {})
    print('  PubMed total={}, arXiv total={}'.format(pm.get('total_found', '?'), ax.get('total_found', '?')))
    for src_label, src_data in [('P', pm), ('A', ax)]:
        recs = src_data.get('records', [])
        for i, r in enumerate(recs[:show]):
            yr = r.get('year', '')
            t = r.get('title', '')[:120]
            doi = r.get('doi', '') or r.get('arxiv_id', '')
            print('  [{}{}] {} | {}'.format(src_label, i + 1, yr, t))
            if doi:
                print('        {}'.format(doi))
