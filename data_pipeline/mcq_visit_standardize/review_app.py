"""Review UI: original vs agent proposal vs human edit. Not question generation."""

from __future__ import annotations

import argparse
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .mappings import SYMPTOM_ALIASES
from .synonyms import (
    append_decision,
    catalog_entries,
    compile_table_from_decisions,
    concept_id_from_standard,
    load_jsonl,
    load_reviewed_synonyms,
    write_synonym_table,
)
from .context import build_context_index
from .text import lookup_key

HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>标准化审核：原文 → 建议 → 确认</title>
<style>
:root{color-scheme:dark;--bg:#0b1020;--card:#151c30;--line:#293553;--text:#edf2ff;--muted:#91a0bf;--ok:#50d890;--run:#69a7ff;--bad:#ff718b}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:system-ui,"Microsoft YaHei",sans-serif}
.wrap{display:grid;grid-template-columns:380px 1fr;min-height:100vh}
aside{border-right:1px solid var(--line);padding:16px;display:flex;flex-direction:column;gap:10px}
main{padding:22px 28px}h1{margin:0 0 6px;font-size:22px}.muted{color:var(--muted);font-size:13px;line-height:1.5}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin:14px 0}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px}
.value{font-size:22px;font-weight:700;margin-top:4px}.label{font-size:12px;color:var(--muted)}
input,select,button{font:inherit;color:var(--text)}
input,select{background:#0f1628;border:1px solid var(--line);border-radius:8px;padding:8px 10px;width:100%}
button{border:0;border-radius:8px;padding:9px 12px;cursor:pointer;background:#2a3d66}
button.ok{background:#1f6b45}button.warn{background:#6b3a22}button.ghost{background:#263450}
.list{overflow:auto;flex:1;border:1px solid var(--line);border-radius:10px}
.item{padding:10px 12px;border-bottom:1px solid var(--line);cursor:pointer}
.item:hover{background:#1b2440}.item.active{background:#24345c}
.item .src{font-size:13px;line-height:1.35;word-break:break-word}
.freq{float:right;color:var(--run);font-size:12px}
.badge{display:inline-block;margin-top:4px;font-size:11px;color:#9ec2ff}
.compare{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin:12px 0}
.box{background:#0f1628;border:1px solid var(--line);border-radius:10px;padding:12px;min-height:88px;white-space:pre-wrap;word-break:break-word}
.box.suggest{border-color:#3d6cb0}
.actions{display:flex;gap:8px;margin-top:14px;flex-wrap:wrap}
kbd{background:#263450;border-radius:4px;padding:1px 6px}
.note{background:#1d2b4d;border:1px solid var(--line);border-radius:10px;padding:12px;margin:12px 0;font-size:13px;line-height:1.55}
.row{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.conf-high{color:var(--ok)}.conf-medium{color:#e6c07b}.conf-low{color:var(--bad)}
@media(max-width:980px){.wrap,.compare,.row,.stats{grid-template-columns:1fr}}
</style></head>
<body>
<div class="wrap">
<aside>
  <b>待审队列</b>
  <div class="muted">先看「原文 / 建议改成」，确认或改成你的写法。</div>
  <select id="field">
    <option value="chief_complaint">主诉（出院小结）</option>
    <option value="ed_chief_complaint">主诉（急诊）</option>
    <option value="radiology.exam_name">影像检查名</option>
    <option value="lab.label">化验名称</option>
    <option value="lab.valueuom">化验单位</option>
    <option value="medications">药物</option>
    <option value="allergies">过敏</option>
    <option value="rhythm">心律</option>
  </select>
  <input id="search" placeholder="搜索原文…">
  <label class="muted"><input type="checkbox" id="hideDecided" checked> 隐藏已处理</label>
  <label class="muted"><input type="checkbox" id="onlyProposed" checked> 只看已有建议的条目</label>
  <div class="list" id="list"></div>
</aside>
<main>
  <h1>标准化审核</h1>
  <div class="muted">不是出题。流程：原文 → 我的建议 → 你确认，或改成 xx 后再确认。</div>
  <div class="note" id="methodNote"></div>
  <div class="stats">
    <div class="card"><div class="label">待审</div><div class="value" id="remaining">—</div></div>
    <div class="card"><div class="label">已确认</div><div class="value" id="accepted">—</div></div>
    <div class="card"><div class="label">建议条数</div><div class="value" id="proposed">—</div></div>
    <div class="card"><div class="label">同义词表</div><div class="value" id="tableSize">—</div></div>
  </div>
  <div class="compare">
    <div>
      <div class="label">原文</div>
      <div class="box" id="source">选择左侧一条</div>
    </div>
    <div>
      <div class="label">建议改成 <span id="conf"></span></div>
      <div class="box suggest" id="proposal">—</div>
    </div>
  </div>
  <div class="muted" id="reason"></div>
  <div class="label" style="margin-top:16px">上下文样例（完整主诉 + 现病史摘录，不是全文出院小结）</div>
  <div id="examples"></div>
  <div class="row" style="margin-top:12px">
    <div>
      <div class="label">确认后的标准名（可改成 xx）</div>
      <input id="standard" placeholder="你确认或改成的英文标准名">
    </div>
    <div>
      <div class="label">concept_id</div>
      <input id="concept" placeholder="symptom:chest_pain">
    </div>
  </div>
  <div class="actions">
    <button class="ok" id="confirm">确认建议</button>
    <button class="ok" id="confirmEdit">改成上面内容并确认</button>
    <button class="ghost" id="skip">跳过</button>
    <button class="warn" id="na">不适用</button>
  </div>
  <div class="muted" style="margin-top:10px">快捷键：<kbd>J</kbd>/<kbd>K</kbd> 下/上 · <kbd>D</kbd> 确认建议 · <kbd>S</kbd> 跳过</div>
  <div class="muted" id="msg" style="margin-top:10px"></div>
</main>
</div>
<script>
let state={items:[],decisions:{},index:0,method_note:''};
const $=id=>document.getElementById(id);
function slug(name){return 'symptom:'+(name||'').toLowerCase().replace(/[^a-z0-9]+/g,'_').replace(/^_|_$/g,'')}
function clampIndex(index){
  const n=visibleItems().length;
  if(!n) return 0;
  return Math.max(0, Math.min(index, n-1));
}
async function load(keepIndex){
  const field=$('field').value;
  const r=await fetch('/api/state?field='+encodeURIComponent(field),{cache:'no-store'});
  const payload=await r.json();
  state=payload;
  state.index=clampIndex(typeof keepIndex==='number'?keepIndex:0);
  $('methodNote').textContent=state.method_note||'';
  render();
  const active=$('list').querySelector('.item.active');
  if(active) active.scrollIntoView({block:'nearest'});
}
function visibleItems(){
  const q=($('search').value||'').toLowerCase();
  const hide=$('hideDecided').checked;
  const only=$('onlyProposed').checked;
  return state.items.filter(it=>{
    if(hide && state.decisions[it.lookup_key]) return false;
    if(only && !it.proposal) return false;
    if(q && !(it.source||'').toLowerCase().includes(q)) return false;
    return true;
  });
}
function current(){return visibleItems()[state.index]||null}
function render(){
  $('remaining').textContent=state.stats.remaining;
  $('accepted').textContent=state.stats.accepted;
  $('proposed').textContent=state.stats.with_proposal;
  $('tableSize').textContent=state.stats.table_size;
  const items=visibleItems();
  $('list').innerHTML=items.map((it,i)=>`<div class="item ${i===state.index?'active':''}" data-i="${i}">
    <span class="freq">${it.frequency}</span>
    <div class="src">${esc(it.source||'')}</div>
    ${it.proposal?`<div class="badge">${esc(it.proposal.proposed_standard||it.proposal.proposed_action)} · ${it.proposal.confidence||''}</div>`:''}
  </div>`).join('')||'<div class="muted" style="padding:12px">没有待审项</div>';
  [...$('list').querySelectorAll('.item')].forEach(el=>el.onclick=()=>{state.index=+el.dataset.i;render()});
  const it=current();
  if(!it){
    $('source').textContent='没有选中项';
    $('proposal').textContent='—';
    $('reason').textContent='';
    $('examples').innerHTML='';
    return;
  }
  const p=it.proposal||{};
  $('source').textContent=it.source;
  $('proposal').textContent=p.proposed_standard||p.proposed_action||'（暂无自动建议，请在下方填写 xx）';
  $('conf').textContent=p.confidence?('· '+p.confidence):'';
  $('conf').className=p.confidence?('conf-'+p.confidence):'';
  $('reason').textContent=p.reason||'';
  const decided=state.decisions[it.lookup_key];
  $('standard').value=(decided&&decided.standard)||p.proposed_standard||'';
  $('concept').value=(decided&&decided.concept_id)||p.proposed_concept_id||'';
  loadContext();
}
async function loadContext(){
  const box=$('examples');
  const it=current();
  if(!it){box.innerHTML='';return}
  box.innerHTML='<div class="muted">正在加载上下文…</div>';
  const r=await fetch('/api/context?field='+encodeURIComponent($('field').value)+'&lookup_key='+encodeURIComponent(it.lookup_key),{cache:'no-store'});
  const d=await r.json();
  if(!d.examples||!d.examples.length){
    box.innerHTML='<div class="muted">没有找到包含该短语的住院样例。可能是切开残片，或该字段在样例库中未命中。</div>';
    return;
  }
  box.innerHTML=d.examples.map((ex,i)=>`<div class="box" style="margin-top:8px">
    <div class="label">样例 ${i+1}${ex.hadm_id?' · hadm_id '+esc(ex.hadm_id):''}</div>
    <div><b>完整字段</b>：${esc(ex.full_field||'')}</div>
    ${ex.matched_span?`<div class="muted">命中片段：${esc(ex.matched_span)}</div>`:''}
    ${ex.hpi_excerpt?`<div style="margin-top:6px"><b>现病史摘录</b>：${esc(ex.hpi_excerpt)}</div>`:''}
    ${ex.other_exams&&ex.other_exams.length?`<div class="muted" style="margin-top:6px">同次住院其他影像：${esc(ex.other_exams.join('； '))}</div>`:''}
    ${ex.fluid?`<div class="muted">化验上下文：${esc(ex.fluid||'')} / ${esc(ex.category||'')}</div>`:''}
  </div>`).join('');
}
function esc(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
async function decide(action, useEdited){
  const it=current(); if(!it) return;
  const p=it.proposal||{};
  const standard=useEdited?$('standard').value.trim():(p.proposed_standard||$('standard').value.trim());
  const concept=useEdited?$('concept').value.trim():(p.proposed_concept_id||$('concept').value.trim());
  const body={action, domain:it.domain, field:$('field').value, source:it.source, lookup_key:it.lookup_key, frequency:it.frequency, standard, concept_id:concept};
  if(action==='accept' && p.proposed_action==='not_applicable' && !useEdited) body.action='not_applicable';
  if(body.action==='accept' && !body.standard){$('msg').textContent='请填写「改成 xx」的标准名，或点确认建议';return}
  const r=await fetch('/api/decision',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const out=await r.json();
  if(!r.ok){$('msg').textContent=out.error||'失败';return}
  $('msg').textContent=body.action==='accept'?'已确认并写入同义词表':'已记录';
  const hide=$('hideDecided').checked;
  const nextIndex=hide?state.index:state.index+1;
  await load(nextIndex);
}
$('confirm').onclick=()=>decide('accept', false);
$('confirmEdit').onclick=()=>decide('accept', true);
$('skip').onclick=()=>decide('skip', true);
$('na').onclick=()=>decide('not_applicable', true);
$('field').onchange=()=>load(0);
$('search').oninput=()=>{state.index=0;render()};
$('hideDecided').onchange=()=>{state.index=0;render()};
$('onlyProposed').onchange=()=>{state.index=0;render()};
document.addEventListener('keydown',e=>{
  if(['INPUT','TEXTAREA','SELECT'].includes(e.target.tagName)) return;
  if(e.key==='j'||e.key==='J'){state.index=Math.min(state.index+1,visibleItems().length-1);render();e.preventDefault()}
  if(e.key==='k'||e.key==='K'){state.index=Math.max(state.index-1,0);render();e.preventDefault()}
  if(e.key==='d'||e.key==='D'){decide('accept', false);e.preventDefault()}
  if(e.key==='s'||e.key==='S') decide('skip', true);
});
load();
</script>
</body></html>
"""

MAX_BODY = 64 * 1024
METHOD_NOTE = (
    "化验：10,000 例里 736 个 itemid 各只有一个官方 label，几乎没有「同一化验多个名字」；"
    "需要审的主要是单位 N/A 和个别大小写。影像：大量 PORT / IN O.R. 是同一检查的技术后缀，"
    "对比剂有无、左右侧不能合并。"
    "出院小结长文本：更合适的顺序是先做实体抽取（定位 span 与否定），再对抽到的实体做术语标准化。"
    "主诉短字段可以现在先审同义词。本页不出题。"
)

FIELD_DOMAIN = {
    "chief_complaint": "symptom",
    "ed_chief_complaint": "symptom",
    "radiology.exam_name": "radiology",
    "lab.label": "lab",
    "lab.valueuom": "unit",
    "medications": "drug",
    "allergies": "allergy",
    "rhythm": "rhythm",
}


class ReviewStore:
    def __init__(
        self,
        queue_path: Path,
        decisions_path: Path,
        table_path: Path,
        proposals_path: Path | None = None,
        visits_path: Path | None = None,
    ) -> None:
        self.queue_path = queue_path
        self.decisions_path = decisions_path
        self.table_path = table_path
        self._lock = threading.Lock()
        self.context_index = build_context_index(visits_path) if visits_path else {}
        self.queue = load_jsonl(queue_path)
        for row in self.queue:
            row["lookup_key"] = lookup_key(row.get("source")) or row.get("lookup_key") or ""
        self.proposals = {
            (str(row.get("domain")), str(row.get("lookup_key"))): row
            for row in (load_jsonl(proposals_path) if proposals_path else [])
            if row.get("lookup_key")
        }
        extra_items = []
        seen = {(str(row.get("domain")), str(row.get("lookup_key"))) for row in self.queue}
        for key, proposal in self.proposals.items():
            if key in seen:
                continue
            extra_items.append(
                {
                    "domain": proposal.get("domain"),
                    "field": proposal.get("field"),
                    "source": proposal.get("source"),
                    "frequency": proposal.get("frequency") or 0,
                    "lookup_key": proposal.get("lookup_key"),
                    "status": "unresolved",
                }
            )
        self.queue.extend(extra_items)

    def _decisions(self) -> list[dict[str, Any]]:
        return load_jsonl(self.decisions_path)

    def latest_decisions(self) -> dict[str, dict[str, Any]]:
        latest: dict[str, dict[str, Any]] = {}
        for row in self._decisions():
            key = row.get("lookup_key")
            if key:
                latest[str(key)] = row
        return latest

    def state(self, field: str) -> dict[str, Any]:
        domain = FIELD_DOMAIN.get(field, "symptom")
        with self._lock:
            extra = load_reviewed_synonyms(self.table_path)
            latest = self.latest_decisions()
            items = []
            for row in self.queue:
                if row.get("field") != field or not row.get("lookup_key"):
                    continue
                lookup = str(row["lookup_key"])
                proposal = self.proposals.get((domain, lookup)) or self.proposals.get(
                    (str(row.get("domain")), lookup)
                )
                items.append(
                    {
                        "source": row.get("source"),
                        "frequency": int(row.get("frequency") or 0),
                        "lookup_key": lookup,
                        "field": field,
                        "domain": domain,
                        "status": row.get("status"),
                        "proposal": proposal,
                    }
                )
            remaining = sum(1 for item in items if item["lookup_key"] not in latest)
            accepted = [row for row in latest.values() if row.get("action") == "accept"]
            return {
                "field": field,
                "items": items,
                "decisions": latest,
                "catalog": catalog_entries(extra) if domain == "symptom" else [],
                "method_note": METHOD_NOTE,
                "stats": {
                    "remaining": remaining,
                    "accepted": len(accepted),
                    "with_proposal": sum(1 for item in items if item.get("proposal")),
                    "table_size": len(extra) + len(SYMPTOM_ALIASES),
                    "queue_items": len(items),
                },
            }

    def decide(self, payload: dict[str, Any]) -> dict[str, Any]:
        action = payload.get("action")
        source = str(payload.get("source") or "").strip()
        field = str(payload.get("field") or "chief_complaint")
        domain = FIELD_DOMAIN.get(field, str(payload.get("domain") or "symptom"))
        if action not in {"accept", "skip", "not_applicable"}:
            raise ValueError("action must be accept, skip, or not_applicable")
        if not source:
            raise ValueError("source is required")
        key = str(payload.get("lookup_key") or lookup_key(source) or "")
        if not key:
            raise ValueError("lookup_key is empty")
        standard = str(payload.get("standard") or "").strip()
        concept_id = str(payload.get("concept_id") or "").strip()
        if action == "accept":
            if not standard:
                raise ValueError("standard is required for accept")
            if not concept_id:
                if domain == "symptom":
                    existing = {
                        item["standard"].casefold(): item["concept_id"] for item in catalog_entries()
                    }
                    concept_id = existing.get(standard.casefold()) or concept_id_from_standard(standard)
                else:
                    concept_id = f"{domain}:{lookup_key(standard)}"
        decision = {
            "action": action,
            "domain": domain,
            "field": field,
            "source": source,
            "lookup_key": key,
            "standard": standard or None,
            "concept_id": concept_id or None,
            "frequency": payload.get("frequency"),
        }
        with self._lock:
            append_decision(self.decisions_path, decision)
            compiled = compile_table_from_decisions(self._decisions())
            write_synonym_table(self.table_path, compiled)
        return {"ok": True, "table_rows": len(compiled), "decision": decision}

    def examples(self, field: str, lookup: str) -> list[dict[str, Any]]:
        return list(self.context_index.get((field, lookup), []))


def create_handler(store: ReviewStore) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path in ("/", "/index.html"):
                payload = HTML.encode("utf-8")
                content_type = "text/html; charset=utf-8"
            elif parsed.path == "/api/state":
                field = parse_qs(parsed.query).get("field", ["chief_complaint"])[0]
                if field not in FIELD_DOMAIN:
                    field = "chief_complaint"
                payload = json.dumps(store.state(field), ensure_ascii=False).encode("utf-8")
                content_type = "application/json; charset=utf-8"
            elif parsed.path == "/api/context":
                query = parse_qs(parsed.query)
                field = query.get("field", ["chief_complaint"])[0]
                lookup = query.get("lookup_key", [""])[0]
                payload = json.dumps(
                    {"examples": store.examples(field, lookup)},
                    ensure_ascii=False,
                ).encode("utf-8")
                content_type = "application/json; charset=utf-8"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/api/decision":
                self.send_error(404)
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > MAX_BODY:
                self.send_error(400)
                return
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw.decode("utf-8"))
                result = store.decide(payload)
                body = json.dumps(result, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
            except (ValueError, json.JSONDecodeError) as exc:
                body = json.dumps({"error": str(exc)}, ensure_ascii=False).encode("utf-8")
                self.send_response(400)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    return Handler


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Review original vs proposed standard names")
    parser.add_argument(
        "--queue",
        type=Path,
        default=Path("data/derived/mcq_visit_standardize/random10k_dev20_v1.0.9/review_queue.jsonl"),
    )
    parser.add_argument(
        "--decisions",
        type=Path,
        default=Path("data/derived/mcq_visit_standardize/synonym_decisions.jsonl"),
    )
    parser.add_argument(
        "--table",
        type=Path,
        default=Path("data/derived/mcq_visit_standardize/reviewed_synonyms.jsonl"),
    )
    parser.add_argument(
        "--proposals",
        type=Path,
        default=Path("data/derived/mcq_visit_standardize/agent_proposals.jsonl"),
    )
    parser.add_argument(
        "--visits",
        type=Path,
        default=Path("data/derived/mcq_visit_extract/random10k_dev20/visits.json"),
        help="extract visits.json used only to show short context snippets",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8767)
    parser.add_argument("--open-browser", action="store_true")
    args = parser.parse_args(argv)
    if not args.queue.is_file():
        print(f"review queue missing: {args.queue}")
        return 1
    if args.visits.is_file():
        print(f"indexing context from {args.visits} …", flush=True)
    store = ReviewStore(args.queue, args.decisions, args.table, args.proposals, args.visits)
    server = ThreadingHTTPServer((args.host, args.port), create_handler(store))
    url = f"http://{args.host}:{args.port}/"
    print(url, flush=True)
    print(f"proposals={args.proposals}", flush=True)
    print(f"synonym_table={args.table}", flush=True)
    if args.open_browser:
        webbrowser.open(url)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
