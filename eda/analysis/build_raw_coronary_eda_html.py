from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path
from typing import Any

from data_pipeline.mimic_raw_archive.field_dictionary import (
    build_field_dictionary,
    validate_dictionary,
)


REQUIRED_KEYS = {
    "generated_at", "input", "input_bytes", "records", "subjects", "schema",
    "line_bytes", "cad", "patient_level", "admission_level", "disease_spectrum",
    "benchmark_source_readiness", "module_coverage", "tables", "time_quality",
    "orphan_child_rows", "largest_admissions", "shards", "comparison_to_reference",
}


def validate_metrics(metrics: dict[str, Any]) -> None:
    missing = sorted(REQUIRED_KEYS - metrics.keys())
    if missing:
        raise ValueError(f"metrics 缺少字段: {', '.join(missing)}")
    if metrics["records"] <= 0 or metrics["subjects"] <= 0:
        raise ValueError("records 和 subjects 必须大于 0")
    if metrics["cad"]["admissions"] != metrics["records"]:
        raise ValueError("疾病谱队列中 cad.admissions 必须等于 records")
    if len(metrics["tables"]) != 32:
        raise ValueError(f"预期 32 张源表，实际 {len(metrics['tables'])}")
    if len(metrics["time_quality"]) != 52:
        raise ValueError(f"预期 52 个时间字段，实际 {len(metrics['time_quality'])}")


def safe_json(value: Any) -> str:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        .replace("</", "<\\/")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def render_report(
    metrics: dict[str, Any], metrics_sha256: str,
    field_rows: list[dict[str, Any]],
) -> str:
    validate_metrics(metrics)
    validate_dictionary(field_rows)
    title = "MIMIC 冠状动脉疾病谱原始住院归档 EDA"
    template = r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__</title>
<style>
:root{--ink:#17212b;--muted:#5c6875;--paper:#f4f7f9;--card:#fff;--line:#dce3e8;--blue:#0072B2;--sky:#56B4E9;--green:#009E73;--orange:#E69F00;--verm:#D55E00;--purple:#CC79A7;--nav:#102b3a}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.6 system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif}.layout{display:grid;grid-template-columns:245px minmax(0,1fr);min-height:100vh}aside{position:sticky;top:0;height:100vh;background:var(--nav);color:#fff;padding:26px 18px;overflow:auto}aside h1{font-size:18px;line-height:1.35;margin:0 0 8px}aside p{font-size:12px;color:#b9cad3;margin:0 0 20px}nav a{display:block;color:#d9e7ed;text-decoration:none;padding:7px 9px;border-radius:6px;font-size:13px}nav a:hover{background:#1d465b;color:#fff}main{width:min(1420px,100%);padding:36px 42px 70px}.hero{background:linear-gradient(125deg,#08324a,#0072B2);color:#fff;padding:30px;border-radius:14px}.hero h2{font-size:30px;line-height:1.25;margin:0 0 8px}.hero p{margin:5px 0;color:#d9edf6}.tag{display:inline-block;padding:3px 8px;border-radius:99px;background:#dceff7;color:#07587f;font-size:12px;font-weight:700;margin-right:5px}.hero .tag{background:#fff2;color:#fff}section{scroll-margin-top:20px;margin-top:34px}h2{font-size:22px;margin:0 0 12px}h3{font-size:16px;margin:22px 0 8px}.cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.card,.panel{background:var(--card);border:1px solid var(--line);border-radius:10px;box-shadow:0 2px 8px #182c3a0a}.card{padding:16px}.card .value{font-size:25px;font-weight:750;line-height:1.25;color:#07587f}.card .label{font-size:12px;color:var(--muted);margin-top:4px}.panel{padding:18px;margin-top:12px}.grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px}.chart{min-height:260px;overflow:auto}.chart svg{width:100%;min-width:460px}.axis{stroke:#89949d;stroke-width:1}.grid{stroke:#e8edf0;stroke-width:1}.bar{transition:opacity .15s}.bar:hover{opacity:.72}.tick{font-size:11px;fill:#5c6875}.label{font-size:11px;fill:#26333d}.tooltip{position:fixed;pointer-events:none;background:#17212b;color:#fff;padding:7px 9px;border-radius:5px;font-size:12px;display:none;z-index:20;max-width:280px}.controls{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}.controls input,.controls select,.controls button{border:1px solid #bdc9d0;background:#fff;border-radius:6px;padding:7px 9px;font:inherit}.controls button.active{background:var(--blue);color:#fff;border-color:var(--blue)}table{width:100%;border-collapse:collapse;font-variant-numeric:tabular-nums}th,td{text-align:left;padding:8px;border-bottom:1px solid #e8edf0;white-space:nowrap}th{position:sticky;top:0;background:#edf3f6;font-size:12px;cursor:pointer}td{font-size:12px}.table-wrap{max-height:520px;overflow:auto;border:1px solid var(--line);border-radius:7px}.field-table td{white-space:normal;min-width:125px;vertical-align:top}.field-table td:first-child{min-width:290px}.note{border-left:4px solid var(--orange);background:#fff7df;padding:10px 13px;margin:12px 0}.ok{border-left-color:var(--green);background:#e9f7f2}.warn{border-left-color:var(--verm);background:#fff0eb}.muted{color:var(--muted);font-size:13px}.legend{display:flex;gap:14px;flex-wrap:wrap;font-size:12px;color:var(--muted)}.dot{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px}.metric{display:flex;justify-content:space-between;gap:15px;padding:7px 0;border-bottom:1px solid #edf0f2}.metric:last-child{border:0}.mono{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;word-break:break-all}details{margin-top:12px}summary{cursor:pointer;color:#07587f;font-weight:650}.footer{margin-top:36px;padding-top:18px;border-top:1px solid var(--line);color:var(--muted);font-size:12px}@media(max-width:900px){.layout{display:block}aside{position:relative;height:auto}nav{columns:2}main{padding:22px 14px}.cards{grid-template-columns:repeat(2,1fr)}.grid2{grid-template-columns:1fr}}@media print{aside,.controls{display:none}.layout{display:block}main{padding:0}.panel,.card{break-inside:avoid;box-shadow:none}.hero{background:#fff;color:#000;border:1px solid #aaa}.hero p{color:#333}}
</style></head><body><div class="layout"><aside><h1>冠状动脉疾病谱 EDA</h1><p>原始住院归档 · 全量队列</p><nav>
<a href="#overview">结论与规模</a><a href="#patients">患者与住院</a><a href="#spectrum">疾病谱</a><a href="#sources">数据源覆盖</a><a href="#tables">32 张源表</a><a href="#time">52 个时间字段</a><a href="#benchmark">五维题型准备度</a><a href="#shards">分片与极端值</a><a href="#comparison">与 10K 对照</a><a href="#dictionary">JSONL 字段说明</a><a href="#methods">口径与限制</a></nav></aside><main>
<header class="hero"><span class="tag">描述性全队列 EDA</span><span class="tag">自包含离线报告</span><h2>__TITLE__</h2><p>ICD-9 410–414 / ICD-10 I20–I25 · 一行一次住院 · 不含 ICU chartevents</p><p id="generated"></p></header>
<section id="overview"><h2>结论与规模</h2><div class="cards" id="overviewCards"></div><div class="note ok" id="qualityGate"></div><div class="note">本报告回答“原始归档中有什么、覆盖多少、数据量如何”，不把来源覆盖率解释为可直接发布的题目数量，也不替代决策时点快照和未来信息泄漏测试。</div></section>
<section id="patients"><h2>患者与住院</h2><div class="grid2"><div class="panel"><h3>患者画像</h3><div id="patientMetrics"></div></div><div class="panel"><h3>住院类型</h3><div id="admissionType" class="chart"></div></div><div class="panel"><h3>出院去向</h3><div id="discharge" class="chart"></div></div><div class="panel"><h3>开发集与最终测试集</h3><div id="partitions" class="chart"></div><p class="muted">按患者隔离；患者跨分区冲突数必须为 0。</p></div></div></section>
<section id="spectrum"><h2>疾病谱构成</h2><div class="controls"><button id="groupBtn" class="active">临床分组</button><button id="codeBtn">ICD 三位码</button></div><div class="panel"><div id="spectrumChart" class="chart"></div></div><div class="grid2"><div class="panel"><h3>诊断位置</h3><div id="cadPosition"></div></div><div class="panel"><h3>每次住院相关诊断码数</h3><div id="codeMultiplicity" class="chart"></div></div></div><p class="muted">同一次住院可同时属于多个临床分组，因此分组住院数不可相加为队列总数；“原发/继发”也不是互斥统计。</p></section>
<section id="sources"><h2>数据源覆盖</h2><div class="panel"><div id="moduleCoverage" class="chart"></div></div><p class="muted">HOSP 为队列定义与住院骨架；ED、NOTE、ICU 仅在原表存在原生住院关联时纳入。ICU 高频监护表 chartevents 明确排除。</p></section>
<section id="tables"><h2>32 张源表探索</h2><div class="controls"><input id="tableSearch" placeholder="搜索表名"><select id="moduleFilter"><option value="">全部模块</option><option>mimic_iv_hosp</option><option>mimic_iv_ed</option><option>mimic_iv_note</option><option>mimic_iv_icu</option></select><button id="linearBtn" class="active">线性轴</button><button id="logBtn">对数轴</button></div><div class="panel"><div id="tableChart" class="chart"></div></div><div class="table-wrap"><table id="tableTable"><thead><tr><th data-key="table">源表</th><th data-key="rows">总行数</th><th data-key="nonempty_admissions">非空住院</th><th data-key="coverage">覆盖率</th><th data-key="rows_per_admission">行/住院均值</th><th data-key="rows_p50">P50</th><th data-key="rows_p95">P95</th><th data-key="rows_p99">P99</th></tr></thead><tbody></tbody></table></div></section>
<section id="time"><h2>52 个时间字段完整性</h2><div class="controls"><input id="timeSearch" placeholder="搜索时间字段"><label>最低缺失率 <input id="missingThreshold" type="range" min="0" max="100" value="0"><span id="missingValue">0%</span></label></div><div class="panel"><div id="timeChart" class="chart"></div></div><div class="table-wrap"><table><thead><tr><th>时间字段</th><th>出现</th><th>缺失</th><th>缺失率</th></tr></thead><tbody id="timeBody"></tbody></table></div></section>
<section id="benchmark"><h2>五个题型维度的来源准备度</h2><div class="panel"><div id="readiness" class="chart"></div></div><div class="note warn">这些是“具备相关来源”的宽松代理指标，不是候选题、gold label 或可回答率。正式 benchmark 还需按题型构建决策快照、屏蔽决策后的字段，并逐题执行未来信息泄漏检测。</div></section>
<section id="shards"><h2>分片与极端值</h2><div class="grid2"><div class="panel"><h3>218 个输出分片</h3><div id="shardChart" class="chart"></div></div><div class="panel"><h3>最大单条住院记录</h3><div id="largest"></div></div></div><details><summary>展开全部分片清单（记录数、字节数、SHA-256）</summary><div class="table-wrap"><table><thead><tr><th>Shard</th><th>记录</th><th>大小</th><th>SHA-256</th></tr></thead><tbody id="shardBody"></tbody></table></div></details></section>
<section id="comparison"><h2>与一般 10K 样本对照</h2><div class="cards" id="comparisonCards"></div><div class="panel"><div id="comparisonChart" class="chart"></div></div><p class="muted">10K 是此前的一般住院验证样本，仅用于工程体积与模块覆盖对照，不是病例对照研究，也不用于推断疾病相关性。</p></section>
<section id="dictionary"><h2>JSONL 字段与层级说明</h2><div class="note ok"><strong>一行 JSON = 一次住院（一个 hadm_id）。</strong>表键固定存在，无数据时为 <span class="mono">[]</span>；表内对象保留 MIMIC 原始 CSV 字段名和源字符串，空单元格为 <span class="mono">null</span>。</div>
<h3>顶层字段</h3><div class="table-wrap"><table><thead><tr><th>字段</th><th>类型</th><th>说明</th></tr></thead><tbody>
<tr><td class="mono">schema</td><td>object</td><td>归档格式标识，固定为 mimic_admission_raw 1.0.0；不是临床派生字段。</td></tr><tr><td class="mono">subject_id</td><td>string</td><td>原始患者标识，来自 admissions.subject_id。</td></tr><tr><td class="mono">hadm_id</td><td>string</td><td>原始住院主键，也是本行 JSON 的归档单位。</td></tr><tr><td class="mono">mimic_iv_hosp</td><td>object</td><td>住院、检验、医嘱、用药、编码和转科等 HOSP 原始表。</td></tr><tr><td class="mono">mimic_iv_icu</td><td>object</td><td>具有原生 hadm_id 的 ICU 事件；明确排除 chartevents。</td></tr><tr><td class="mono">mimic_iv_ed</td><td>object</td><td>经 edstays.hadm_id 原生关联的急诊及其子表。</td></tr><tr><td class="mono">mimic_iv_note</td><td>object</td><td>具有原生 hadm_id 的出院和放射文书及 detail 行。</td></tr>
</tbody></table></div>
<h3>32 张住院内源表</h3><div class="controls"><input id="dictionarySearch" placeholder="搜索表名、字段、模块或说明"></div><div class="table-wrap"><table><thead><tr><th>JSON 路径</th><th>原始字段</th><th>内容与用途</th><th>主要连接键</th></tr></thead><tbody id="dictionaryBody"></tbody></table></div>
<h3>逐字段数据字典</h3><div class="controls"><input id="fieldSearch" placeholder="搜索路径、字段名或中文含义"><select id="fieldScope"><option value="archive">JSONL内字段</option><option value="top_level">顶层字段</option><option value="external_reference">外置公共字典</option><option value="">全部</option></select><select id="fieldModule"><option value="">全部模块</option><option value="mimic_iv_hosp">HOSP</option><option value="mimic_iv_icu">ICU</option><option value="mimic_iv_ed">ED</option><option value="mimic_iv_note">NOTE</option><option value="root">顶层</option></select><span id="fieldCount" class="tag"></span></div><div class="table-wrap"><table class="field-table"><thead><tr><th>JSON路径</th><th>JSON存储类型</th><th>源类型/约束</th><th>中文含义</th><th>键角色</th><th>时间语义</th><th>信息阶段</th><th>Benchmark使用限制</th></tr></thead><tbody id="fieldBody"></tbody></table></div>
<h3>不进入 JSONL 的内容</h3><div class="grid2"><div class="panel"><strong>独立公共字典</strong><p class="muted">d_labitems、d_icd_diagnoses、d_icd_procedures、d_hcpcs、provider、d_items、caregiver。它们不是某次住院事件，单独保存可避免每次住院重复复制。</p></div><div class="panel"><strong>明确排除</strong><p class="muted">ICU chartevents：大规模床旁监护和护理记录；OMR：没有原生 hadm_id，纳入需依赖时间推断。两者均不进入本归档。</p></div></div><p class="muted">逐字段原始表头、时间字段和连接规则见 docs/design/mimic-admission-raw-jsonl-schema.md。</p></section>
<section id="methods"><h2>口径、溯源与限制</h2><div class="panel"><div class="metric"><span>输入文件</span><span class="mono" id="inputPath"></span></div><div class="metric"><span>指标文件 SHA-256</span><span class="mono">__SHA__</span></div><div class="metric"><span>统计口径</span><span>队列全量描述统计，无抽样置信区间</span></div><div class="metric"><span>数据层边界</span><span>保留原始 MIMIC 字段；派生统计只存在于本报告</span></div></div><div class="note">疾病谱由住院诊断 ICD 范围筛选，诊断本身属于后验资料。它可用于定义开发队列，但不能未经时间屏蔽直接进入前瞻性临床决策题干。</div></section>
<footer class="footer">分析代码：eda/analysis/profile_raw_admission_archive.py · 报告代码：eda/analysis/build_raw_coronary_eda_html.py · 页面不加载任何外部脚本、字体或患者级原文。</footer>
</main></div><div class="tooltip" id="tooltip"></div><script id="metrics" type="application/json">__METRICS__</script><script id="fieldRows" type="application/json">__FIELD_ROWS__</script><script>
const M=JSON.parse(document.getElementById('metrics').textContent);const FIELD_ROWS=JSON.parse(document.getElementById('fieldRows').textContent);const C=['#0072B2','#56B4E9','#009E73','#E69F00','#D55E00','#CC79A7'];const fmt=n=>new Intl.NumberFormat('zh-CN',{maximumFractionDigits:2}).format(n);const pct=n=>(100*n).toFixed(1)+'%';const bytes=n=>n>=1073741824?(n/1073741824).toFixed(2)+' GiB':n>=1048576?(n/1048576).toFixed(1)+' MiB':fmt(n)+' B';const tip=document.getElementById('tooltip');
function cards(id,items){document.getElementById(id).innerHTML=items.map(x=>`<div class="card"><div class="value">${x[1]}</div><div class="label">${x[0]}</div></div>`).join('')}
function metrics(id,items){document.getElementById(id).innerHTML=items.map(x=>`<div class="metric"><span>${x[0]}</span><strong>${x[1]}</strong></div>`).join('')}
function barChart(id,data,opt={}){const el=document.getElementById(id),horizontal=opt.horizontal!==false,log=!!opt.log,top=opt.top||data.length;data=[...data].sort((a,b)=>b.value-a.value).slice(0,top);const W=760,row=horizontal?30:1,H=horizontal?Math.max(235,data.length*row+45):280,p={l:horizontal?245:45,r:35,t:15,b:horizontal?30:70};const max=Math.max(...data.map(d=>d.value),1),scale=v=>log?Math.log10(v+1)/Math.log10(max+1):v/max;let s=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${opt.aria||'条形图'}">`;if(horizontal){data.forEach((d,i)=>{const y=p.t+i*row,w=(W-p.l-p.r)*scale(d.value),col=d.color||C[i%C.length];s+=`<text class="label" x="${p.l-8}" y="${y+17}" text-anchor="end">${String(d.label).slice(0,34)}</text><rect class="bar" data-label="${d.label}" data-value="${d.display||fmt(d.value)}" x="${p.l}" y="${y+4}" width="${Math.max(w,1)}" height="18" rx="2" fill="${col}"/><text class="tick" x="${Math.min(p.l+w+6,W-50)}" y="${y+17}">${d.display||fmt(d.value)}</text>`})}else{const bw=(W-p.l-p.r)/data.length*.72,gap=(W-p.l-p.r)/data.length;data.forEach((d,i)=>{const h=(H-p.t-p.b)*scale(d.value),x=p.l+i*gap+gap*.14,y=H-p.b-h;s+=`<rect class="bar" data-label="${d.label}" data-value="${d.display||fmt(d.value)}" x="${x}" y="${y}" width="${bw}" height="${Math.max(h,1)}" rx="2" fill="${d.color||C[i%C.length]}"/><text class="tick" transform="translate(${x+bw/2},${H-p.b+8}) rotate(45)" text-anchor="start">${String(d.label).slice(0,18)}</text>`})}s+='</svg>';el.innerHTML=s;el.querySelectorAll('.bar').forEach(b=>{b.onmousemove=e=>{tip.style.display='block';tip.style.left=e.clientX+12+'px';tip.style.top=e.clientY+12+'px';tip.textContent=b.dataset.label+': '+b.dataset.value};b.onmouseleave=()=>tip.style.display='none'})}
document.getElementById('generated').textContent='指标生成：'+M.generated_at+'｜报告数据直接嵌入页面，可离线查看';document.getElementById('inputPath').textContent=M.input;
cards('overviewCards', [['住院次数',fmt(M.records)],['患者人数',fmt(M.subjects)],['JSONL 体积',bytes(M.input_bytes)],['平均每条',bytes(M.line_bytes.mean)],['P95 每条',bytes(M.line_bytes.p95)],['源表','32'],['时间字段','52'],['输出分片',fmt(M.shards.length)]]);
const orphanTotal=Object.values(M.orphan_child_rows).reduce((a,b)=>a+b,0);document.getElementById('qualityGate').innerHTML=`<strong>归档结构门禁通过：</strong>无效记录 ${fmt(M.schema.invalid_records)}；禁入 chartevents 行 ${fmt(M.schema.forbidden_chartevents)}；未知顶层字段 ${fmt(Object.keys(M.schema.unexpected_top_fields).length)}；父子孤立行 ${fmt(orphanTotal)}。`;
metrics('patientMetrics',[['每患者住院均值',fmt(M.patient_level.admissions_per_subject_mean)],['住院次数 P50 / P95 / 最大值',`${fmt(M.patient_level.admissions_per_subject_p50)} / ${fmt(M.patient_level.admissions_per_subject_p95)} / ${fmt(M.patient_level.admissions_per_subject_max)}`],['多次住院患者',`${fmt(M.patient_level.subjects_with_multiple_admissions)} (${pct(M.patient_level.subjects_with_multiple_admissions/M.subjects)})`],['女性 / 男性',`${fmt(M.patient_level.gender.F)} / ${fmt(M.patient_level.gender.M)}`],['年龄均值 / P50 / P95',`${fmt(M.patient_level.anchor_age.mean)} / ${fmt(M.patient_level.anchor_age.p50)} / ${fmt(M.patient_level.anchor_age.p95)}`],['住院日均值 / P50 / P95',`${fmt(M.admission_level.length_of_stay_days.mean)} / ${fmt(M.admission_level.length_of_stay_days.p50)} / ${fmt(M.admission_level.length_of_stay_days.p95)}`],['人口学冲突',fmt(M.patient_level.demographic_conflicts)]]);
barChart('admissionType',Object.entries(M.admission_level.admission_type).map(([label,value])=>({label,value})),{top:12});barChart('discharge',Object.entries(M.admission_level.discharge_location).map(([label,value])=>({label,value})),{top:12});barChart('partitions',Object.entries(M.patient_level.partitions).map(([label,value],i)=>({label,value,color:C[i]})),{});
function drawSpectrum(mode){const d=mode==='group'?M.disease_spectrum.clinical_groups.map(x=>({label:x.group.replaceAll('_',' '),value:x.admissions,display:fmt(x.admissions)+' 次住院'})):M.disease_spectrum.code3.map(x=>({label:x.code,value:x.admissions,display:fmt(x.admissions)+' 次住院'}));barChart('spectrumChart',d,{top:20})}drawSpectrum('group');document.getElementById('groupBtn').onclick=()=>{drawSpectrum('group');groupBtn.classList.add('active');codeBtn.classList.remove('active')};document.getElementById('codeBtn').onclick=()=>{drawSpectrum('code');codeBtn.classList.add('active');groupBtn.classList.remove('active')};
metrics('cadPosition',[['队列标准',M.cad.criteria],['主诊断含 CAD',fmt(M.disease_spectrum.primary_cad_admissions)],['任一继发位含 CAD',fmt(M.disease_spectrum.secondary_cad_admissions)]]);barChart('codeMultiplicity',Object.entries(M.disease_spectrum.relevant_codes_per_admission).map(([label,value])=>({label:label+' 个码',value})),{horizontal:false});
barChart('moduleCoverage',Object.entries(M.module_coverage).map(([label,value],i)=>({label,value,display:pct(value),color:C[i]})),{});
let tableRows=[...M.tables],tableLog=false,tableSort=['rows',-1];function renderTables(){const q=tableSearch.value.toLowerCase(),mod=moduleFilter.value;let rows=tableRows.filter(r=>r.table.toLowerCase().includes(q)&&(!mod||r.table.startsWith(mod+'.')));rows.sort((a,b)=>(a[tableSort[0]]>b[tableSort[0]]?1:a[tableSort[0]]<b[tableSort[0]]?-1:0)*tableSort[1]);document.querySelector('#tableTable tbody').innerHTML=rows.map(r=>`<tr><td>${r.table}</td><td>${fmt(r.rows)}</td><td>${fmt(r.nonempty_admissions)}</td><td>${pct(r.coverage)}</td><td>${fmt(r.rows_per_admission)}</td><td>${fmt(r.rows_p50)}</td><td>${fmt(r.rows_p95)}</td><td>${fmt(r.rows_p99)}</td></tr>`).join('');barChart('tableChart',rows.map(r=>({label:r.table,value:r.rows})),{log:tableLog,top:15})}renderTables();tableSearch.oninput=moduleFilter.onchange=renderTables;document.querySelectorAll('#tableTable th').forEach(th=>th.onclick=()=>{const k=th.dataset.key;tableSort=[k,tableSort[0]===k?-tableSort[1]:-1];renderTables()});linearBtn.onclick=()=>{tableLog=false;linearBtn.classList.add('active');logBtn.classList.remove('active');renderTables()};logBtn.onclick=()=>{tableLog=true;logBtn.classList.add('active');linearBtn.classList.remove('active');renderTables()};
function renderTime(){const q=timeSearch.value.toLowerCase(),min=+missingThreshold.value/100;missingValue.textContent=missingThreshold.value+'%';const rows=M.time_quality.filter(r=>r.field.toLowerCase().includes(q)&&r.missing_rate>=min).sort((a,b)=>b.missing_rate-a.missing_rate);timeBody.innerHTML=rows.map(r=>`<tr><td>${r.field}</td><td>${fmt(r.present)}</td><td>${fmt(r.missing)}</td><td>${pct(r.missing_rate)}</td></tr>`).join('');barChart('timeChart',rows.map(r=>({label:r.field,value:r.missing_rate,display:pct(r.missing_rate)})),{top:15})}renderTime();timeSearch.oninput=missingThreshold.oninput=renderTime;
const readyNames={investigation_selection:'检查检验选择',clinical_diagnosis:'临床诊断',treatment_disposition:'治疗与处置',referral_service:'转诊与科室',discharge_followup:'离院指导与随访'};barChart('readiness',Object.entries(M.benchmark_source_readiness).map(([k,v],i)=>({label:readyNames[k],value:v.coverage,display:`${pct(v.coverage)} · ${fmt(v.admissions)} 次`,color:C[i]})),{});
barChart('shardChart',M.shards.map(x=>({label:'shard '+x.shard_id,value:x.bytes,display:bytes(x.bytes),color:C[0]})),{horizontal:false});shardBody.innerHTML=M.shards.map(x=>`<tr><td>${x.shard_id}</td><td>${fmt(x.records)}</td><td>${bytes(x.bytes)}</td><td class="mono">${x.sha256}</td></tr>`).join('');document.getElementById('largest').innerHTML=M.largest_admissions.slice(0,10).map((x,i)=>`<div class="metric"><span>#${i+1} subject ${x.subject_id} / hadm ${x.hadm_id}</span><strong>${bytes(x.bytes)}</strong></div>`).join('');
const R=M.comparison_to_reference;cards('comparisonCards',[['当前平均记录',R.current_mean_kib.toFixed(1)+' KiB'],['10K 平均记录',R.reference_mean_kib.toFixed(1)+' KiB'],['体积比',R.mean_size_ratio.toFixed(2)+'×'],['10K 记录数',fmt(R.reference_records)]]);barChart('comparisonChart',Object.entries(R.module_coverage).flatMap(([k,v],i)=>[{label:k+' · 疾病谱',value:v.current,display:pct(v.current),color:C[i]},{label:k+' · 10K',value:v.reference,display:pct(v.reference),color:C[i]}]),{});
const dictionary=[
['mimic_iv_hosp.patients','患者人口学、锚定年龄/年份和死亡日期','subject_id'],['mimic_iv_hosp.admissions','住院行政骨架、入出院时间、来源去向和院内死亡标志','subject_id + hadm_id'],['mimic_iv_hosp.transfers','院内床位或病区流转、care unit 与起止时间','subject_id + hadm_id'],['mimic_iv_hosp.services','负责医疗服务的变更及前后 service','subject_id + hadm_id'],
['mimic_iv_hosp.labevents','原始检验结果、单位、参考范围、异常标志及 chart/store time','subject_id + hadm_id'],['mimic_iv_hosp.microbiologyevents','标本、培养菌、分离株、药敏及原始时间','subject_id + hadm_id'],['mimic_iv_hosp.poe','Provider order、类型、状态、创建/变更/停止关系','subject_id + hadm_id'],['mimic_iv_hosp.poe_detail','POE 的 EAV 明细，保留原始 field_name/value','subject_id + poe_id + poe_seq'],
['mimic_iv_hosp.pharmacy','药房处理、核验、途径、频次、输注和调剂','subject_id + hadm_id'],['mimic_iv_hosp.prescriptions','处方药名/代码、规格、剂量、剂型、频次和途径','subject_id + hadm_id'],['mimic_iv_hosp.emar','电子给药父记录、执行文本及计划/记录时间','subject_id + hadm_id'],['mimic_iv_hosp.emar_detail','实际给药剂量、制品、输注、途径和部位等完整明细','subject_id + emar_id + emar_seq'],
['mimic_iv_hosp.diagnoses_icd','住院 ICD 诊断及原始顺序；属于后验编码资料','subject_id + hadm_id'],['mimic_iv_hosp.procedures_icd','住院 ICD 操作编码、顺序和日期','subject_id + hadm_id'],['mimic_iv_hosp.hcpcsevents','HCPCS 编码事件及源描述','subject_id + hadm_id'],['mimic_iv_hosp.drgcodes','DRG 编码、描述、严重度和死亡风险；属于后验资料','subject_id + hadm_id'],
['mimic_iv_icu.icustays','ICU stay、首末 care unit、起止时间和 LOS','subject_id + hadm_id'],['mimic_iv_icu.datetimeevents','ICU 中以日期/时间为值的事件','subject_id + hadm_id + stay_id'],['mimic_iv_icu.ingredientevents','ICU 输入成分、数量、速率、医嘱关系和状态','subject_id + hadm_id + stay_id'],['mimic_iv_icu.inputevents','ICU 输液、药物、营养等输入与总量/速率','subject_id + hadm_id + stay_id'],['mimic_iv_icu.outputevents','尿量、引流等 ICU 输出记录','subject_id + hadm_id + stay_id'],['mimic_iv_icu.procedureevents','ICU 操作、位置、医嘱关系、状态和原始值','subject_id + hadm_id + stay_id'],
['mimic_iv_ed.edstays','ED 起止时间、到院交通方式和 disposition','subject_id + hadm_id'],['mimic_iv_ed.triage','分诊生命体征、疼痛、acuity 和原始主诉','subject_id + stay_id'],['mimic_iv_ed.vitalsign','ED 期间重复生命体征、节律和疼痛','subject_id + stay_id'],['mimic_iv_ed.diagnosis','ED ICD 诊断、顺序和源标题','subject_id + stay_id'],['mimic_iv_ed.medrecon','ED 用药核对药名、代码和治疗类别','subject_id + stay_id'],['mimic_iv_ed.pyxis','ED Pyxis 发药记录','subject_id + stay_id'],
['mimic_iv_note.discharge','完整原始出院文书；不预拆分章节，属于后验资料','subject_id + hadm_id'],['mimic_iv_note.discharge_detail','出院文书 detail EAV 行及原始顺序','subject_id + note_id'],['mimic_iv_note.radiology','完整原始放射报告及 chart/store time','subject_id + hadm_id'],['mimic_iv_note.radiology_detail','放射报告 detail EAV 行及原始顺序','subject_id + note_id']];
const fieldSets={
'mimic_iv_hosp.patients':'subject_id, gender, anchor_age, anchor_year, anchor_year_group, dod',
'mimic_iv_hosp.admissions':'subject_id, hadm_id, admittime, dischtime, deathtime, admission_type, admit_provider_id, admission_location, discharge_location, insurance, language, marital_status, race, edregtime, edouttime, hospital_expire_flag',
'mimic_iv_hosp.transfers':'subject_id, hadm_id, transfer_id, eventtype, careunit, intime, outtime',
'mimic_iv_hosp.services':'subject_id, hadm_id, transfertime, prev_service, curr_service',
'mimic_iv_hosp.labevents':'labevent_id, subject_id, hadm_id, specimen_id, itemid, order_provider_id, charttime, storetime, value, valuenum, valueuom, ref_range_lower, ref_range_upper, flag, priority, comments',
'mimic_iv_hosp.microbiologyevents':'microevent_id, subject_id, hadm_id, micro_specimen_id, order_provider_id, chartdate, charttime, spec_itemid, spec_type_desc, test_seq, storedate, storetime, test_itemid, test_name, org_itemid, org_name, isolate_num, quantity, ab_itemid, ab_name, dilution_text, dilution_comparison, dilution_value, interpretation, comments',
'mimic_iv_hosp.poe':'poe_id, poe_seq, subject_id, hadm_id, ordertime, order_type, order_subtype, transaction_type, discontinue_of_poe_id, discontinued_by_poe_id, order_provider_id, order_status',
'mimic_iv_hosp.poe_detail':'poe_id, poe_seq, subject_id, field_name, field_value',
'mimic_iv_hosp.pharmacy':'subject_id, hadm_id, pharmacy_id, poe_id, starttime, stoptime, medication, proc_type, status, entertime, verifiedtime, route, frequency, disp_sched, infusion_type, sliding_scale, lockout_interval, basal_rate, one_hr_max, doses_per_24_hrs, duration, duration_interval, expiration_value, expiration_unit, expirationdate, dispensation, fill_quantity',
'mimic_iv_hosp.prescriptions':'subject_id, hadm_id, pharmacy_id, poe_id, poe_seq, order_provider_id, starttime, stoptime, drug_type, drug, formulary_drug_cd, gsn, ndc, prod_strength, form_rx, dose_val_rx, dose_unit_rx, form_val_disp, form_unit_disp, doses_per_24_hrs, route',
'mimic_iv_hosp.emar':'subject_id, hadm_id, emar_id, emar_seq, poe_id, pharmacy_id, enter_provider_id, charttime, medication, event_txt, scheduletime, storetime',
'mimic_iv_hosp.emar_detail':'subject_id, emar_id, emar_seq, parent_field_ordinal, administration_type, pharmacy_id, barcode_type, reason_for_no_barcode, complete_dose_not_given, dose_due, dose_due_unit, dose_given, dose_given_unit, will_remainder_of_dose_be_given, product_amount_given, product_unit, product_code, product_description, product_description_other, prior_infusion_rate, infusion_rate, infusion_rate_adjustment, infusion_rate_adjustment_amount, infusion_rate_unit, route, infusion_complete, completion_interval, new_iv_bag_hung, continued_infusion_in_other_location, restart_interval, side, site, non_formulary_visual_verification',
'mimic_iv_hosp.diagnoses_icd':'subject_id, hadm_id, seq_num, icd_code, icd_version',
'mimic_iv_hosp.procedures_icd':'subject_id, hadm_id, seq_num, chartdate, icd_code, icd_version',
'mimic_iv_hosp.hcpcsevents':'subject_id, hadm_id, chartdate, hcpcs_cd, seq_num, short_description',
'mimic_iv_hosp.drgcodes':'subject_id, hadm_id, drg_type, drg_code, description, drg_severity, drg_mortality',
'mimic_iv_icu.icustays':'subject_id, hadm_id, stay_id, first_careunit, last_careunit, intime, outtime, los',
'mimic_iv_icu.datetimeevents':'subject_id, hadm_id, stay_id, caregiver_id, charttime, storetime, itemid, value, valueuom, warning',
'mimic_iv_icu.ingredientevents':'subject_id, hadm_id, stay_id, caregiver_id, starttime, endtime, storetime, itemid, amount, amountuom, rate, rateuom, orderid, linkorderid, statusdescription, originalamount, originalrate',
'mimic_iv_icu.inputevents':'subject_id, hadm_id, stay_id, caregiver_id, starttime, endtime, storetime, itemid, amount, amountuom, rate, rateuom, orderid, linkorderid, ordercategoryname, secondaryordercategoryname, ordercomponenttypedescription, ordercategorydescription, patientweight, totalamount, totalamountuom, isopenbag, continueinnextdept, statusdescription, originalamount, originalrate',
'mimic_iv_icu.outputevents':'subject_id, hadm_id, stay_id, caregiver_id, charttime, storetime, itemid, value, valueuom',
'mimic_iv_icu.procedureevents':'subject_id, hadm_id, stay_id, caregiver_id, starttime, endtime, storetime, itemid, value, valueuom, location, locationcategory, orderid, linkorderid, ordercategoryname, ordercategorydescription, patientweight, isopenbag, continueinnextdept, statusdescription, originalamount, originalrate',
'mimic_iv_ed.edstays':'subject_id, hadm_id, stay_id, intime, outtime, gender, race, arrival_transport, disposition',
'mimic_iv_ed.triage':'subject_id, stay_id, temperature, heartrate, resprate, o2sat, sbp, dbp, pain, acuity, chiefcomplaint',
'mimic_iv_ed.vitalsign':'subject_id, stay_id, charttime, temperature, heartrate, resprate, o2sat, sbp, dbp, rhythm, pain',
'mimic_iv_ed.diagnosis':'subject_id, stay_id, seq_num, icd_code, icd_version, icd_title',
'mimic_iv_ed.medrecon':'subject_id, stay_id, charttime, name, gsn, ndc, etc_rn, etccode, etcdescription',
'mimic_iv_ed.pyxis':'subject_id, stay_id, charttime, med_rn, name, gsn_rn, gsn',
'mimic_iv_note.discharge':'note_id, subject_id, hadm_id, note_type, note_seq, charttime, storetime, text',
'mimic_iv_note.discharge_detail':'note_id, subject_id, field_name, field_value, field_ordinal',
'mimic_iv_note.radiology':'note_id, subject_id, hadm_id, note_type, note_seq, charttime, storetime, text',
'mimic_iv_note.radiology_detail':'note_id, subject_id, field_name, field_value, field_ordinal'};
function renderDictionary(){const q=dictionarySearch.value.toLowerCase();dictionaryBody.innerHTML=dictionary.filter(r=>(r.join(' ')+' '+fieldSets[r[0]]).toLowerCase().includes(q)).map(r=>`<tr><td class="mono">${r[0]}[]</td><td class="mono">${fieldSets[r[0]]}</td><td>${r[1]}</td><td class="mono">${r[2]}</td></tr>`).join('')}renderDictionary();dictionarySearch.oninput=renderDictionary;
function renderFields(){const q=fieldSearch.value.toLowerCase(),scope=fieldScope.value,module=fieldModule.value;const rows=FIELD_ROWS.filter(r=>(!scope||r.scope===scope)&&(!module||r.module===module)&&Object.values(r).join(' ').toLowerCase().includes(q));fieldCount.textContent=fmt(rows.length)+' 个字段';fieldBody.innerHTML=rows.map(r=>`<tr><td class="mono">${r.json_path}</td><td>${r.archive_type}</td><td>${r.source_type}<br><span class="muted">${r.source_constraint}</span></td><td>${r.description_zh}</td><td>${r.key_role}</td><td>${r.time_semantics}</td><td>${r.information_phase}</td><td>${r.benchmark_restriction}</td></tr>`).join('')}renderFields();fieldSearch.oninput=fieldScope.onchange=fieldModule.onchange=renderFields;
if(location.hash){requestAnimationFrame(()=>requestAnimationFrame(()=>document.querySelector(location.hash)?.scrollIntoView()))}
</script></body></html>'''
    return (
        template.replace("__TITLE__", html.escape(title))
        .replace("__SHA__", metrics_sha256)
        .replace("__METRICS__", safe_json(metrics))
        .replace("__FIELD_ROWS__", safe_json(field_rows))
    )


def build_report(
    metrics_path: Path, output_path: Path,
    reference_root: Path | None = None,
) -> None:
    raw = metrics_path.read_bytes()
    metrics = json.loads(raw)
    if reference_root is None:
        reference_root = Path(__file__).resolve().parents[2] / "docs/reference/mimic_reference"
    field_rows = build_field_dictionary(reference_root)
    report = render_report(
        metrics, hashlib.sha256(raw).hexdigest().upper(), field_rows,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成冠状动脉疾病谱原始归档交互式 EDA HTML")
    parser.add_argument("--metrics", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reference-root", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    build_report(args.metrics, args.output, args.reference_root)
    print(args.output.resolve())


if __name__ == "__main__":
    main()
