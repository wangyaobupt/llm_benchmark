# -*- coding: utf-8 -*-
"""Build self-contained HTML EDA report from normalized_events_eda_metrics.json."""
from __future__ import annotations

import json
import sys
from pathlib import Path

OUT_DIR = Path(r"D:\Projects\llm_benchmark\eda\coronary_all_three_modules_full")
METRICS = OUT_DIR / "normalized_events_eda_metrics.json"
HTML_OUT = OUT_DIR / "normalized_events_EDA报告.html"


def safe_json(value) -> str:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        .replace("</", "<\\/")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


TEMPLATE = r'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>冠心病三模块 · 标准化临床事件 EDA</title>
<style>
:root{--ink:#17212b;--muted:#5c6875;--paper:#f4f7f9;--card:#fff;--line:#dce3e8;--blue:#0072B2;--sky:#56B4E9;--green:#009E73;--orange:#E69F00;--verm:#D55E00;--purple:#CC79A7;--nav:#102b3a}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.65 system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
.layout{display:grid;grid-template-columns:248px minmax(0,1fr);min-height:100vh}
aside{position:sticky;top:0;height:100vh;background:var(--nav);color:#fff;padding:26px 18px;overflow:auto}
aside h1{font-size:17px;line-height:1.4;margin:0 0 6px}aside p{font-size:12px;color:#b9cad3;margin:0 0 18px}
nav a{display:block;color:#d9e7ed;text-decoration:none;padding:6px 9px;border-radius:6px;font-size:13px}
nav a:hover{background:#1d465b;color:#fff}
main{width:min(1420px,100%);padding:34px 42px 70px}
.hero{background:linear-gradient(125deg,#08324a,#0072B2);color:#fff;padding:28px 30px;border-radius:14px}
.hero h2{font-size:28px;line-height:1.3;margin:0 0 8px}.hero p{margin:5px 0;color:#d9edf6;font-size:14px}
.tag{display:inline-block;padding:3px 9px;border-radius:99px;background:#dceff7;color:#07587f;font-size:12px;font-weight:700;margin-right:6px}
.hero .tag{background:#fff3;color:#fff}
section{scroll-margin-top:18px;margin-top:36px}h2{font-size:22px;margin:0 0 12px}h3{font-size:16px;margin:22px 0 8px}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px}
.card,.panel{background:var(--card);border:1px solid var(--line);border-radius:10px;box-shadow:0 2px 8px #182c3a0a}
.card{padding:14px 16px}.card .value{font-size:23px;font-weight:750;line-height:1.25;color:#07587f}.card .label{font-size:12px;color:var(--muted);margin-top:3px}
.panel{padding:16px 18px;margin-top:12px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:12px}.grid3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px}
@media(max-width:1100px){.grid2,.grid3{grid-template-columns:1fr}}
.chart{min-height:200px;overflow:auto}.chart svg{width:100%;min-width:430px}
.axis{stroke:#89949d;stroke-width:1}.grid{stroke:#e8edf0;stroke-width:1}
.bar{transition:opacity .15s}.bar:hover{opacity:.72}
.tick{font:11px system-ui;fill:#5c6875}.label{font:11.5px system-ui;fill:#28323c}
.muted{color:var(--muted);font-size:13px}.mono{font-family:ui-monospace,Consolas,monospace;font-size:12px}
.note{background:#eef6fb;border:1px solid #cfe4f0;border-radius:8px;padding:10px 14px;margin-top:12px;font-size:13.5px}
.note.warn{background:#fdf6e9;border-color:#f0dfb8}.note.ok{background:#eefaf2;border-color:#cde9d6}
.table-wrap{overflow:auto;margin-top:10px;border:1px solid var(--line);border-radius:8px;background:#fff}
table{border-collapse:collapse;width:100%;font-size:13px}th{position:sticky;top:0;background:#f0f4f7;text-align:left;padding:7px 10px;border-bottom:2px solid var(--line);cursor:pointer;white-space:nowrap}
td{padding:6px 10px;border-bottom:1px solid #ecf0f3;white-space:nowrap}tr:hover td{background:#f7fafc}
th.nos{cursor:default}
.controls{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-top:10px}
.controls input,.controls select{padding:6px 9px;border:1px solid var(--line);border-radius:6px;font-size:13px}
button.act{padding:5px 12px;border-radius:6px;border:1px solid var(--line);background:#fff;cursor:pointer;font-size:13px}
button.act.on{background:#07587f;color:#fff;border-color:#07587f}
.tooltip{display:none;position:fixed;background:#102b3a;color:#fff;padding:5px 9px;border-radius:6px;font-size:12px;pointer-events:none;z-index:9}
.metric{display:flex;justify-content:space-between;gap:12px;border-bottom:1px dashed var(--line);padding:5px 0;font-size:13.5px}
.metric:last-child{border-bottom:none}.metric strong{color:#07587f}
.footer{margin-top:44px;color:var(--muted);font-size:12.5px;border-top:1px solid var(--line);padding-top:14px}
.num{text-align:right;font-variant-numeric:tabular-nums}
</style></head><body><div class="layout"><aside><h1>冠心病三模块<br>标准化事件 EDA</h1><p>normalized_events.parquet · 27.3M 事件</p><nav>
<a href="#overview">① 总览与规模</a>
<a href="#investigation">② 检查（检验/影像）</a>
<a href="#diagnosis">③ 诊断</a>
<a href="#treatment">④ 治疗 T1-T3</a>
<a href="#linkage">⑤ T1↔T2 开立-执行链接</a>
<a href="#referral">⑥ 转诊与流转</a>
<a href="#time">⑦ 时间与质量标记</a>
<a href="#norm">⑧ 术语标准化</a>
<a href="#methods">⑨ 口径与限制</a>
</nav></aside><main>
<header class="hero"><span class="tag">描述性全量 EDA</span><span class="tag">自包含离线报告</span><h2 id="title">冠心病三模块 · 标准化临床事件探索性分析</h2><p id="sub"></p><p id="generated"></p></header>

<section id="overview"><h2>① 总览与规模</h2><div class="cards" id="ovCards"></div>
<div class="grid2"><div class="panel"><h3>事件类型 × 领域（点击表头排序）</h3><div class="controls"><input id="kindSearch" placeholder="搜索事件类型/领域"><select id="domFilter"><option value="">全部领域</option></select></div><div class="table-wrap" style="max-height:520px"><table id="kindTable"><thead><tr><th data-k="kind">事件类型</th><th data-k="domain">领域</th><th class="num" data-k="n">事件数</th><th class="num" data-k="share">占比</th><th class="num" data-k="hadm_cov">覆盖住院</th><th class="num" data-k="hadm_cov_rate">覆盖率</th><th class="num" data-k="mapped_rate">映射率</th><th class="num" data-k="et">事件时间率</th><th class="num" data-k="vnum">数值率</th></tr></thead><tbody></tbody></table></div></div>
<div><div class="panel"><h3>来源模块分布</h3><div id="modChart" class="chart"></div></div>
<div class="panel"><h3>每次住院事件数分布</h3><div id="ephChart" class="chart"></div><div id="ephMetrics" class="muted"></div></div></div></div>
<div class="grid2"><div class="panel"><h3>来源表 Top 20（module.table）</h3><div id="tblChart" class="chart"></div></div>
<div class="panel"><h3>生命周期动作 Top（POE 状态时间线 create/change/discontinue）</h3><div id="lifeChart" class="chart"></div></div></div>
<div class="panel"><h3>领域汇总（各领域事件量 / 覆盖住院 / 每住院分位数）</h3><div class="table-wrap"><table id="domTable"><thead><tr><th class="nos">领域</th><th class="num nos">事件数</th><th class="num nos">占比</th><th class="num nos">覆盖住院</th><th class="num nos">覆盖率</th><th class="num nos">均值/住院</th><th class="num nos">P50</th><th class="num nos">P95</th><th class="num nos">P99</th><th class="num nos">最大</th></tr></thead><tbody></tbody></table></div></div></section>

<section id="investigation"><h2>② 检查（检验 / 影像 / 微生物）</h2><div class="cards" id="invCards"></div>
<div class="grid2"><div class="panel"><h3>Top 30 检验项目（laboratory_resulted）</h3><div id="labTop" class="chart"></div></div>
<div class="panel"><h3>检验结果标志（正常/异常）</h3><div id="labAbn" class="chart"></div><h3>检验单位 Top</h3><div id="labUnit" class="chart"></div></div></div>
<div class="grid2"><div class="panel"><h3>开立 vs 回报（检验/影像）</h3><div id="ordRes"></div><p class="muted">检验医嘱（laboratory_ordered，来源 hosp.poe_timeline）为<b>类别级</b>：99.99% 无具体项目标签（CATEGORY_ONLY），具体项目信息只在 laboratory_resulted；POE 生命周期 create 862k / change 82k / discontinue 26k。</p></div>
<div class="panel"><h3>影像医嘱亚型 Top（imaging_ordered）</h3><div id="imgTop" class="chart"></div></div></div>
<div class="grid2"><div class="panel"><h3>医嘱 order_type / order_subtype Top（POE）</h3><div id="ordType" class="chart"></div></div>
<div class="panel"><h3>Top 15 微生物检测（microbiology_resulted）</h3><div id="micTop" class="chart"></div></div></div></section>

<section id="diagnosis"><h2>③ 诊断（编码诊断 / 主诉）</h2><div class="cards" id="dxCards"></div>
<div class="grid2"><div class="panel"><h3>Top 30 编码诊断（condition_recorded_post_hoc，preferred_name 优先）</h3><div id="dxTop" class="chart"></div></div>
<div class="panel"><h3>诊断编码系统构成（来源：hosp.diagnoses_icd 711k + ed.diagnosis 83k）</h3><div id="dxCs" class="chart"></div><h3>每住院编码诊断条数</h3><div id="dxPer"></div></div></div>
<div class="grid2"><div class="panel"><h3>Top 20 ED 主诉/症状（symptom_reported，ED triage 原始串）</h3><div id="symTop" class="chart"></div></div>
<div class="panel"><h3>主诉未解析术语 Top 15（术语映射缺口）</h3><div id="symUnres" class="chart"></div></div></div>
<div class="note warn">诊断事件 evidence_phase=post_hoc（出院后编码），且 <b>event_time 全部为空</b>（策略 post_hoc_no_time_v1）——不可作为决策时点前的信息直接进入前瞻题干；主诉/症状来自 ED triage（同样无时刻，仅日期粒度策略 triage_no_time）。DRG 分组（administrative_group_recorded）在本事件表中为 0 行，未纳入。</div></section>

<section id="treatment"><h2>④ 治疗 T1-T3（开立 / 执行 / 手术操作）</h2>
<div class="note ok">任务口径：<b>T1</b>=medication_ordered（prescriptions，开立/处方·决策意图）；<b>T2</b>=medication_administered（eMAR，执行·可识别 held/refused）；<b>T3</b>=procedure_performed + procedure_recorded_post_hoc（手术/操作）。T1/T2 不合并——「开了没给」的分歧本身是题目素材。注意：POE 中 order_type=Medications 的 2.30M 行进入 <b>clinical_ordered</b>（通用医嘱状态时间线），不与 T1 混算。</div>
<h3>T1 开立医嘱</h3><div class="cards" id="t1Cards"></div>
<div class="grid2"><div class="panel"><h3>Top 30 开立用药（medication_ordered，100% 来源 hosp.prescriptions）</h3><div id="t1Top" class="chart"></div></div>
<div class="panel"><h3>医嘱结构化链接与内容特异性</h3><div id="t1Link"></div><div id="t1Spec" class="chart"></div></div></div>
<h3>T2 执行情况</h3><div class="cards" id="t2Cards"></div>
<div class="grid2"><div class="panel"><h3>Top 30 执行给药（medication_administered，来源 hosp.emar）</h3><div id="t2Top" class="chart"></div></div>
<div class="panel"><h3>执行溯源解析（eMAR→POE / 药名来源）</h3><div id="t2Res" class="chart"></div><h3>未给药事件 Top（medication_not_administered，含 held/refused）</h3><div id="t2No" class="chart"></div></div></div>
<h3>T3 手术/操作</h3><div class="cards" id="t3Cards"></div>
<div class="grid2"><div class="panel"><h3>Top 20 ICU 床旁操作（procedure_performed，icu.procedureevents）</h3><div id="t3Icu" class="chart"></div></div>
<div class="panel"><h3>Top 20 编码操作（procedure_recorded_post_hoc，procedures_icd 61k + hcpcs 9k）</h3><div id="t3Code" class="chart"></div><h3>编码系统构成</h3><div id="t3Cs" class="chart"></div></div></div>
<div class="panel"><h3>医嘱生命周期与药房状态</h3><div class="grid2"><div id="ordStatus" class="chart"></div><div id="pharmStatus" class="chart"></div></div><p class="muted">左：POE 医嘱生命周期（create/change/discontinue）；右：药房状态跟踪（medication_order_status_recorded）。</p></div></section>

<section id="linkage"><h2>⑤ T1↔T2 开立-执行链接（「开了没给」）</h2><div class="cards" id="lnkCards"></div>
<div class="note">按住院（hadm）对 T1 开立用药集合与 T2 执行给药集合做<b>标签级</b>（小写全等）匹配；<b>概念级</b>（concept_id）匹配在本数据不可用——medication_administered 的术语映射率为 0%（eMAR 药名未进入术语表），需先补 eMAR 映射才能做概念级对齐。不匹配含命名差异（aspirin vs aspirin 81mg tablet、flush/mini-bag 等剂型变体），匹配率应视为下界。</div>
<div class="grid2"><div class="panel"><h3>开立但未见执行 Top 20（按出现住院数）</h3><div id="oNa" class="chart"></div></div>
<div class="panel"><h3>执行但未见开立 Top 20（按出现住院数）</h3><div id="aNo" class="chart"></div></div></div>
<div class="grid2"><div class="panel"><h3>每住院 T1 匹配比例分布（标签级）</h3><div id="lnkDist"></div></div>
<div class="panel"><h3>链接缺口提示</h3><div id="lnkGap"></div></div></div></section>

<section id="referral"><h2>⑥ 转诊与流转（服务变更 / 床位转移 / 模块旅程）</h2><div class="cards" id="refCards"></div>
<div class="grid2"><div class="panel"><h3>Top 30 服务团队变更路径（prev → curr，含入院首团队）</h3><div id="svcPairs" class="chart"></div></div>
<div class="panel"><h3>床位/病区 Top 20（patient_transferred，careunit）</h3><div id="cuTop" class="chart"></div><h3>转移事件类型（eventtype）</h3><div id="cuType" class="chart"></div></div></div>
<div class="panel"><h3>模块旅程（每住院出现的来源模块组合）</h3><div id="journey" class="chart"></div><p class="muted">任务口径 R1=service_changed（住院场景，本表 44.5k 行、覆盖 100%）；patient_transferred（R3）中 eventtype=ED/admit/discharge 为骨架事件（各 ~39k），真正床位间 transfer 44.8k 行，含床位管理噪声，未纳入行为 gold。</p></div></section>

<section id="time"><h2>⑦ 时间与质量标记</h2><div class="cards" id="tmCards"></div>
<div class="grid2"><div class="panel"><h3>事件时间年份分布（event_time 非空行，MIMIC 年份整体偏移至 2100s）</h3><div id="yearChart" class="chart"></div></div>
<div class="panel"><h3>时间解析状态（整体）</h3><div id="trsChart" class="chart"></div><h3>时间精度</h3><div id="precChart" class="chart"></div></div></div>
<div class="panel"><h3>各事件类型时间字段覆盖（非空率）</h3><div class="table-wrap" style="max-height:420px"><table id="timeTable"><thead><tr><th class="nos">事件类型</th><th class="num nos">事件数</th><th class="num nos">event_time</th><th class="num nos">source_available</th><th class="num nos">available</th><th class="num nos">recorded</th></tr></thead><tbody></tbody></table></div></div>
<div class="grid2"><div class="panel"><h3>质量标记 Top 20（行级展开）</h3><div id="qfChart" class="chart"></div></div>
<div class="panel"><h3>时间策略 Top（time_policy_id）</h3><div id="polChart" class="chart"></div></div></div></section>

<section id="norm"><h2>⑧ 术语标准化（映射 / 单位）</h2><div class="cards" id="nmCards"></div>
<div class="grid2"><div class="panel"><h3>各事件类型映射率（mapped / 全部行）</h3><div class="table-wrap" style="max-height:460px"><table id="normTable"><thead><tr><th class="nos">事件类型</th><th class="num nos">事件数</th><th class="num nos">mapped</th><th class="num nos">unresolved</th><th class="num nos">映射率</th></tr></thead><tbody></tbody></table></div></div>
<div class="panel"><h3>未解析术语 Top（选择事件类型）</h3><div class="controls"><select id="unresSel"></select></div><div id="unresChart" class="chart"></div><h3>单位标准化状态（整体）</h3><div id="unitStat" class="chart"></div></div></div></section>

<section id="methods"><h2>⑨ 口径、溯源与限制</h2>
<div class="grid2"><div class="panel"><h3>数据与运行</h3><div id="runMeta"></div></div>
<div class="panel"><h3>与 manifest 交叉核对</h3><div class="table-wrap"><table id="xcheck"><thead><tr><th class="nos">指标</th><th class="num nos">manifest</th><th class="num nos">本次扫描</th><th class="nos">一致</th></tr></thead><tbody></tbody></table></div></div></div>
<div class="panel"><h3>事件类型 → 领域映射表</h3><div class="table-wrap"><table id="mapTable"><thead><tr><th class="nos">event_kind</th><th class="nos">领域</th></tr></thead><tbody></tbody></table></div></div>
<div class="note"><b>限制</b>：① 本报告为全量描述统计，不构成抽样推断；② T1↔T2 匹配为字符串全等匹配，未做剂型/剂量归并，匹配率是下界；③ T2 概念级对齐因 eMAR 映射率 0% 不可用；④ 床位转移含骨架与噪声事件；⑤ 「覆盖率」均以全部 39,036 住院为分母；⑥ 检验/生命体征的数值分布与参考范围合规性未在本报告展开（关注点为事件结构分布）。</div></section>

<footer class="footer">分析代码：eda/coronary_all_three_modules_full/profile_normalized_events.py · 报告代码：build_normalized_events_eda_html.py · 数据：data/derived/coronary_all_three_modules_full/event_pipeline/normalization/normalized_events.parquet（schema clinical_event/1.2.0，run_id b99943d63eab2540b96339f1）· 页面不加载任何外部资源。</footer>
</main></div><div class="tooltip" id="tooltip"></div>
<script id="metrics" type="application/json">__METRICS__</script>
<script>
const M=JSON.parse(document.getElementById('metrics').textContent);
const C=['#0072B2','#56B4E9','#009E73','#E69F00','#D55E00','#CC79A7'];
const fmt=n=>new Intl.NumberFormat('zh-CN',{maximumFractionDigits:2}).format(n);
const pct=x=>(100*x).toFixed(1)+'%';
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const tip=document.getElementById('tooltip');
const $=id=>document.getElementById(id);
function cards(id,items){$(id).innerHTML=items.map(x=>`<div class="card"><div class="value">${x[1]}</div><div class="label">${x[0]}</div></div>`).join('')}
function metricsEl(id,items){$(id).innerHTML=items.map(x=>`<div class="metric"><span>${x[0]}</span><strong>${x[1]}</strong></div>`).join('')}
function barChart(id,data,opt={}){const el=$(id),horizontal=opt.horizontal!==false,top=opt.top||data.length;data=[...data].sort((a,b)=>b.value-a.value).slice(0,top);if(!data.length){el.innerHTML='<p class="muted">（无数据）</p>';return}const W=760,row=horizontal?27:1,H=horizontal?Math.max(200,data.length*row+40):270,p={l:horizontal?236:44,r:52,t:12,b:horizontal?26:64};const max=Math.max(...data.map(d=>d.value),1);let s=`<svg viewBox="0 0 ${W} ${H}" role="img">`;if(horizontal){data.forEach((d,i)=>{const y=p.t+i*row,w=(W-p.l-p.r)*(d.value/max),col=d.color||C[i%C.length];s+=`<text class="label" x="${p.l-7}" y="${y+15}" text-anchor="end">${esc(String(d.label)).slice(0,36)}</text><rect class="bar" data-label="${esc(d.label)}" data-value="${d.display||fmt(d.value)}" x="${p.l}" y="${y+3}" width="${Math.max(w,1)}" height="16.5" rx="2" fill="${col}"/><text class="tick" x="${Math.min(p.l+w+5,W-46)}" y="${y+15}">${d.display||fmt(d.value)}</text>`})}else{const gap=(W-p.l-p.r)/data.length,bw=gap*.68;data.forEach((d,i)=>{const h=(H-p.t-p.b)*(d.value/max),x=p.l+i*gap+gap*.16,y=H-p.b-h;s+=`<rect class="bar" data-label="${esc(d.label)}" data-value="${d.display||fmt(d.value)}" x="${x}" y="${y}" width="${bw}" height="${Math.max(h,1)}" rx="2" fill="${d.color||C[i%C.length]}"/><text class="tick" transform="translate(${x+bw/2},${H-p.b+6}) rotate(45)" text-anchor="start">${esc(String(d.label).slice(0,14))}</text>`})}s+='</svg>';el.innerHTML=s;el.querySelectorAll('.bar').forEach(b=>{b.onmousemove=e=>{tip.style.display='block';tip.style.left=e.clientX+12+'px';tip.style.top=e.clientY+12+'px';tip.textContent=b.dataset.label+': '+b.dataset.value};b.onmouseleave=()=>tip.style.display='none'})}

/* ---------- 总览 ---------- */
const O=M.overview,tt=M.time.kind_time_fields;
const etN=Object.values(tt).reduce((a,x)=>a+x.event_time,0);
const kindBy={};O.kinds.forEach(k=>kindBy[k.kind]=k);
const kindN=k=>kindBy[k]?kindBy[k].n:0, kindCov=k=>kindBy[k]?kindBy[k].hadm_cov_rate:0, kindMap=k=>kindBy[k]?kindBy[k].mapped_rate:0;
$('generated').textContent='指标生成：'+M.meta.generated_at+' ｜ 扫描 '+fmt(M.meta.rows_scanned)+' 行 / '+M.meta.scan_seconds+'s ｜ 报告数据直接嵌入页面，可离线查看';
$('sub').textContent='mimic-admission · 冠心病疾病谱（ICD-9 410–414 / ICD-10 I20–I25）· ED + HOSP + ICU(+NOTE) 模块 · 事件粒度 clinical_event/1.2.0';
cards('ovCards',[['事件总数',fmt(O.rows)],['住院数 hadm',fmt(O.hadms)],['患者数',fmt(O.subjects)],['事件类型',O.kinds.length],['来源模块/源表',Object.keys(O.modules).length+' / '+O.tables.length],['术语映射率',pct(M.normalization.status.mapped/O.rows)],['event_time 覆盖',pct(etN/O.rows)],['平均事件/住院',fmt(O.rows/O.hadms)]]);
let doms=[...new Set(O.kinds.map(k=>k.domain))];const df=$('domFilter');doms.forEach(d=>{const o=document.createElement('option');o.textContent=d;o.value=d;df.appendChild(o)});
let kSort=['n',-1],kRows=O.kinds.map(k=>({...k,et:k.event_time_rate,vnum:k.value_numeric_rate}));
function renderKinds(){const q=$('kindSearch').value.toLowerCase(),dm=df.value;let rows=kRows.filter(k=>k.kind.includes(q)&&(!dm||k.domain===dm));rows.sort((a,b)=>(a[kSort[0]]>b[kSort[0]]?1:a[kSort[0]]<b[kSort[0]]?-1:0)*kSort[1]);document.querySelector('#kindTable tbody').innerHTML=rows.map(k=>`<tr><td class="mono">${k.kind}</td><td>${k.domain}</td><td class="num">${fmt(k.n)}</td><td class="num">${pct(k.share)}</td><td class="num">${fmt(k.hadm_cov)}</td><td class="num">${pct(k.hadm_cov_rate)}</td><td class="num">${pct(k.mapped_rate)}</td><td class="num">${pct(k.et)}</td><td class="num">${pct(k.vnum)}</td></tr>`).join('')}
renderKinds();$('kindSearch').oninput=df.onchange=renderKinds;
document.querySelectorAll('#kindTable th[data-k]').forEach(th=>th.onclick=()=>{const k=th.dataset.k;kSort=[k,kSort[0]===k?-kSort[1]:-1];renderKinds()});
barChart('modChart',Object.entries(O.modules).map(([label,value],i)=>({label,value,color:C[i]})));
barChart('ephChart',Object.entries(O.events_per_hadm.hist).map(([label,value])=>({label,value})),{horizontal:false});
metricsEl('ephMetrics',[['均值',fmt(O.events_per_hadm.mean)],['P50',fmt(O.events_per_hadm.p50)],['P90',fmt(O.events_per_hadm.p90)],['P95',fmt(O.events_per_hadm.p95)],['P99',fmt(O.events_per_hadm.p99)],['最大',fmt(O.events_per_hadm.max)]]);
barChart('tblChart',O.tables.map(r=>({label:r.f0+'.'+r.f1,value:r.v})),{top:20});
barChart('lifeChart',O.kind_lifecycle.map(r=>({label:r.f0.replace('_ordered','')+' · '+(r.f1||'-'),value:r.v})),{top:12});
document.querySelector('#domTable tbody').innerHTML=Object.entries(M.domains).sort((a,b)=>b[1].n-a[1].n).map(([d,x])=>`<tr><td>${d}</td><td class="num">${fmt(x.n)}</td><td class="num">${pct(x.share)}</td><td class="num">${fmt(x.hadm_cov)}</td><td class="num">${pct(x.hadm_cov_rate)}</td><td class="num">${fmt(x.per_hadm.mean||0)}</td><td class="num">${fmt(x.per_hadm.p50||0)}</td><td class="num">${fmt(x.per_hadm.p95||0)}</td><td class="num">${fmt(x.per_hadm.p99||0)}</td><td class="num">${fmt(x.per_hadm.max||0)}</td></tr>`).join('');

/* ---------- 检查 ---------- */
const L=M.labels;
const labTop=k=>(L[k]?L[k].top:[]).map(([label,value])=>({label,value}));
cards('invCards',[['检验结果行',fmt(kindN('laboratory_resulted'))],['检验覆盖住院',pct(kindCov('laboratory_resulted'))],['检验医嘱行（类别级）',fmt(kindN('laboratory_ordered'))],['影像医嘱行',fmt(kindN('imaging_ordered'))],['影像报告行',fmt(kindN('imaging_reported'))],['微生物行',fmt(kindN('microbiology_resulted'))],['检验项目去重数',fmt(L.laboratory_resulted?L.laboratory_resulted.n_distinct:0)],['检验映射率',pct(kindMap('laboratory_resulted'))]]);
barChart('labTop',labTop('laboratory_resulted'),{top:30});
barChart('labAbn',M.quality.kind_abnormal.filter(r=>r.f0==='laboratory_resulted').map(r=>({label:r.f1,value:r.v})));
barChart('labUnit',M.quality.kind_unit.filter(r=>r.f0==='laboratory_resulted').map(r=>({label:r.f1,value:r.v})),{top:14});
metricsEl('ordRes',[['laboratory_ordered',fmt(kindN('laboratory_ordered'))+' 行 / 覆盖 '+pct(kindCov('laboratory_ordered'))],['laboratory_resulted',fmt(kindN('laboratory_resulted'))+' 行 / 覆盖 '+pct(kindCov('laboratory_resulted'))],['imaging_ordered',fmt(kindN('imaging_ordered'))+' 行 / 覆盖 '+pct(kindCov('imaging_ordered'))],['imaging_reported',fmt(kindN('imaging_reported'))+' 行 / 覆盖 '+pct(kindCov('imaging_reported'))],['结果:医嘱（检验）',(kindN('laboratory_resulted')/Math.max(kindN('laboratory_ordered'),1)).toFixed(2)+'×'],['报告:医嘱（影像）',(kindN('imaging_reported')/Math.max(kindN('imaging_ordered'),1)).toFixed(2)+'×']]);
barChart('imgTop',labTop('imaging_ordered'),{top:15});
barChart('ordType',[...M.treatment.order_type,...M.treatment.order_subtype].map(r=>({label:r.f0.replace('_ordered','')+' · '+r.f1,value:r.v})),{top:18});
barChart('micTop',labTop('microbiology_resulted'),{top:15});

/* ---------- 诊断 ---------- */
const dph=M.domains['诊断·编码诊断']?M.domains['诊断·编码诊断'].per_hadm:{};
cards('dxCards',[['编码诊断行',fmt(kindN('condition_recorded_post_hoc'))],['覆盖住院',pct(kindCov('condition_recorded_post_hoc'))],['诊断术语去重',fmt(L.condition_recorded_post_hoc?L.condition_recorded_post_hoc.n_distinct:0)],['映射率',pct(kindMap('condition_recorded_post_hoc'))],['每住院均值/P95',fmt(dph.mean||0)+' / '+fmt(dph.p95||0)],['ED 主诉/症状行',fmt(kindN('symptom_reported'))],['主诉映射率',pct(kindMap('symptom_reported'))],['DRG 分组行','0（未纳入）']]);
barChart('dxTop',labTop('condition_recorded_post_hoc'),{top:30});
barChart('dxCs',M.coding_systems.filter(r=>r.f0==='condition_recorded_post_hoc').map(r=>({label:r.f1,value:r.v})));
metricsEl('dxPer',[['均值',fmt(dph.mean||0)],['P50',fmt(dph.p50||0)],['P90',fmt(dph.p90||0)],['P95',fmt(dph.p95||0)],['P99',fmt(dph.p99||0)],['最大',fmt(dph.max||0)]]);
barChart('symTop',labTop('symptom_reported'),{top:20});
barChart('symUnres',(L.symptom_reported?L.symptom_reported.top_unresolved:[]).map(([label,value])=>({label,value})),{top:15});

/* ---------- 治疗 ---------- */
const ml=M.treatment.med_order_link,lnk=M.treatment.linkage_t1_t2;
cards('t1Cards',[['T1 用药医嘱',fmt(kindN('medication_ordered'))],['T1 覆盖住院',pct(kindCov('medication_ordered'))],['T1 映射率',pct(kindMap('medication_ordered'))],['溯源含 pharmacy_id','100%'],['溯源含 poe_id',ml.n?pct(ml.has_poe_id/ml.n):'-'],['内容特异性','100% entity_specific']]);
barChart('t1Top',labTop('medication_ordered'),{top:30});
metricsEl('t1Link',[['结构化解析行',fmt(ml.n)],['含 poe_id',fmt(ml.has_poe_id)+'（'+(ml.n?pct(ml.has_poe_id/ml.n):'-')+'）'],['含 pharmacy_id',fmt(ml.has_pharmacy_id)+'（'+(ml.n?pct(ml.has_pharmacy_id/ml.n):'-')+'）'],['来源表','hosp.prescriptions（100%）'],['lifecycle=create',fmt(kindN('medication_ordered'))]]);
barChart('t1Spec',M.overview.kind_content_specificity.filter(r=>r.f0==='medication_ordered').map(r=>({label:r.f1,value:r.v})));
const t2per=M.domains['治疗T2·给药执行']?M.domains['治疗T2·给药执行'].per_hadm:{};
cards('t2Cards',[['T2 执行给药',fmt(kindN('medication_administered'))],['T2 覆盖住院',pct(kindCov('medication_administered'))],['每住院 P50/P95',fmt(t2per.p50||0)+' / '+fmt(t2per.p95||0)],['未给药事件',fmt(kindN('medication_not_administered'))],['给药记录 documented',fmt(kindN('medication_administration_documented'))],['ICU 输注 input',fmt(kindN('input_administered'))],['ED 发药/核对',fmt(kindN('medication_dispensed'))+' / '+fmt(kindN('medication_reconciled'))],['T2 映射率','0%（eMAR 未入术语表）']]);
barChart('t2Top',labTop('medication_administered'),{top:30});
barChart('t2Res',M.treatment.resolution.map(r=>({label:r.f0.replace('medication_','').replace('_documented','·doc')+' · '+r.f1.replace('_resolution',' 溯源')+'='+r.f2,value:r.v})),{top:14});
barChart('t2No',labTop('medication_not_administered'),{top:12});
const t3per=M.domains['治疗T3·编码操作']?M.domains['治疗T3·编码操作'].per_hadm:{};
cards('t3Cards',[['ICU 床旁操作',fmt(kindN('procedure_performed'))],['ICU 操作覆盖住院',pct(kindCov('procedure_performed'))],['编码操作 post_hoc',fmt(kindN('procedure_recorded_post_hoc'))],['编码操作覆盖住院',pct(kindCov('procedure_recorded_post_hoc'))],['每住院编码操作 P50/P95',fmt(t3per.p50||0)+' / '+fmt(t3per.p95||0)],['操作术语去重（两类合计）',fmt((L.procedure_performed?L.procedure_performed.n_distinct:0)+(L.procedure_recorded_post_hoc?L.procedure_recorded_post_hoc.n_distinct:0))]]);
barChart('t3Icu',labTop('procedure_performed'),{top:20});
barChart('t3Code',labTop('procedure_recorded_post_hoc'),{top:20});
barChart('t3Cs',M.coding_systems.filter(r=>r.f0==='procedure_recorded_post_hoc').map(r=>({label:r.f1,value:r.v})));
barChart('ordStatus',O.kind_lifecycle.filter(r=>['clinical_ordered','laboratory_ordered','imaging_ordered'].includes(r.f0)).map(r=>({label:r.f0.replace('_ordered','')+' '+r.f1,value:r.v})),{top:12});
barChart('pharmStatus',O.kind_status.filter(r=>r.f0==='medication_order_status_recorded').map(r=>({label:r.f1,value:r.v})),{top:12});

/* ---------- 链接 ---------- */
const ll=lnk.label_level,cl=lnk.concept_level;
cards('lnkCards',[['有 T1 开立的住院',fmt(lnk.hadm_with_t1)],['有 T2 执行的住院',fmt(lnk.hadm_with_t2)],['两者皆有',fmt(lnk.hadm_both)],['标签级匹配率',pct(ll.match_rate_labels)],['每住院匹配比例 P50',pct(ll.per_hadm_match_frac.p50||0)],['存在「开立未执行」用药的住院',ll.any_unmatched_t1_hadms+'（'+pct(ll.any_unmatched_t1_hadms/Math.max(ll.t1_hadms_compared,1))+'）'],['仅开立无任何执行',fmt(lnk.hadm_t1_no_any_t2)],['概念级匹配','不可用（T2 映射 0%）']]);
barChart('oNa',ll.top_ordered_not_administered.map(([label,value])=>({label,value})),{top:20});
barChart('aNo',ll.top_administered_not_ordered.map(([label,value])=>({label,value})),{top:20});
metricsEl('lnkDist',[['比较住院数',fmt(ll.t1_hadms_compared)],['T1 标签总数',fmt(ll.t1_labels_total)],['已匹配',fmt(ll.t1_labels_matched)+'（'+pct(ll.match_rate_labels)+'）'],['每住院匹配比例 均值',pct(ll.per_hadm_match_frac.mean||0)],['每住院匹配比例 P90',pct(ll.per_hadm_match_frac.p90||0)],['每住院匹配比例 P95',pct(ll.per_hadm_match_frac.p95||0)]]);
metricsEl('lnkGap',[['T1 标签级缺口','含剂型/包装词噪声：flush、bag、vial、soln、sw、ns、d5w 等非药品标签混入'],['高频「开立未执行」','sodium chloride 0.9% flush（23.4k 住院）、glucagon（12.3k）、glucose gel（11.8k）、dextrose 50%（10.6k）——多为备用/急救开立'],['高频「执行未开立」','ICU/ED 静脉推注与 sliding scale 用药（magnesium sulfate replacement 2.1k、morphine sulfate 1.6k）——处方与执行命名体系不一致'],['改进方向','① eMAR 药名补术语映射（当前 0%）→ 概念级对齐；② 处方侧按剂型归并；③ 过滤非药品标签后再计算缺口']]);

/* ---------- 转诊 ---------- */
const sper=M.domains['转诊·服务团队变更']?M.domains['转诊·服务团队变更'].per_hadm:{},uper=M.domains['转诊·床位转移']?M.domains['转诊·床位转移'].per_hadm:{};
cards('refCards',[['服务团队变更',fmt(kindN('service_changed'))],['服务变更覆盖住院',pct(kindCov('service_changed'))],['每住院服务变更 P50/P95',fmt(sper.p50||0)+' / '+fmt(sper.p95||0)],['床位转移行',fmt(kindN('patient_transferred'))],['其中真床位间 transfer','44,789'],['床位转移覆盖住院',pct(kindCov('patient_transferred'))],['每住院转移 P50/P95',fmt(uper.p50||0)+' / '+fmt(uper.p95||0)]]);
barChart('svcPairs',M.referral.service_pairs.map(([label,value])=>({label,value})),{top:30});
barChart('cuTop',labTop('patient_transferred'),{top:20});
barChart('cuType',O.kind_status.filter(r=>r.f0==='patient_transferred').map(r=>({label:'eventtype='+r.f1,value:r.v})));
barChart('journey',Object.entries(O.module_journey).map(([label,value])=>({label,value})));

/* ---------- 时间 ---------- */
const years=Object.entries(M.time.year).filter(([y])=>/^\d{4}$/.test(y)).sort((a,b)=>a[0]<b[0]?-1:1);
cards('tmCards',[['event_time 覆盖',pct(etN/O.rows)],['resolved',pct(M.time.resolution_status.resolved/O.rows)],['partially_resolved',pct((M.time.resolution_status.partially_resolved||0)/O.rows)],['unresolved',pct((M.time.resolution_status.unresolved||0)/O.rows)],['事件年份范围',(years[0]?years[0][0]:'?')+' – '+(years[years.length-1]?years[years.length-1][0]:'?')],['秒级精度占比',pct(M.time.precision.second/O.rows)]]);
barChart('yearChart',years.slice(-40).map(([label,value])=>({label,value})),{horizontal:false});
barChart('trsChart',Object.entries(M.time.resolution_status).map(([label,value])=>({label,value})));
barChart('precChart',Object.entries(M.time.precision).map(([label,value])=>({label,value})));
document.querySelector('#timeTable tbody').innerHTML=O.kinds.map(k=>{const t=tt[k.kind]||{n:0};return `<tr><td class="mono">${k.kind}</td><td class="num">${fmt(t.n)}</td><td class="num">${pct(t.event_time/(t.n||1))}</td><td class="num">${pct(t.source_available/(t.n||1))}</td><td class="num">${pct(t.available/(t.n||1))}</td><td class="num">${pct(t.recorded/(t.n||1))}</td></tr>`}).join('');
barChart('qfChart',Object.entries(M.quality.flags).map(([label,value])=>({label,value})),{top:20});
barChart('polChart',Object.entries(M.time.policy).map(([label,value])=>({label,value})),{top:12});

/* ---------- 标准化 ---------- */
const nstat=M.normalization.status;
cards('nmCards',[['mapped',fmt(nstat.mapped||0)],['unresolved',fmt(nstat.unresolved||0)],['映射率',pct((nstat.mapped||0)/O.rows)],['review_queue 行',fmt(M.manifest.normalization.counts.review_queue_rows)],['单位 mapped',fmt(M.normalization.unit_status.mapped||0)],['单位 unresolved',fmt(M.normalization.unit_status.unresolved||0)]]);
const ks={};M.normalization.kind_status.forEach(r=>{ks[r.f0]=ks[r.f0]||{mapped:0,unresolved:0,not_applicable:0,n:0};ks[r.f0][r.f1]=r.v;ks[r.f0].n+=r.v});
document.querySelector('#normTable tbody').innerHTML=O.kinds.map(k=>{const s=ks[k.kind]||{mapped:0,unresolved:0,not_applicable:0,n:k.n};return `<tr><td class="mono">${k.kind}</td><td class="num">${fmt(s.n)}</td><td class="num">${fmt(s.mapped)}</td><td class="num">${fmt(s.unresolved)}</td><td class="num">${pct(s.mapped/(s.n||1))}</td></tr>`}).join('');
const unresKinds=Object.keys(L).filter(k=>L[k].top_unresolved.length);const us=$('unresSel');unresKinds.forEach(k=>{const o=document.createElement('option');o.value=k;o.textContent=k;us.appendChild(o)});
function drawUnres(){barChart('unresChart',(L[us.value].top_unresolved).map(([label,value])=>({label,value})),{top:20})}if(unresKinds.length){us.onchange=drawUnres;drawUnres()}
barChart('unitStat',Object.entries(M.normalization.unit_status).map(([label,value])=>({label,value})));

/* ---------- 口径 ---------- */
metricsEl('runMeta',[['输入文件',M.meta.events_path],['文件体积',(M.meta.file_bytes/1073741824).toFixed(2)+' GiB'],['扫描行数',fmt(M.meta.rows_scanned)+' / 预期 '+fmt(M.meta.rows_expected)],['扫描耗时',M.meta.scan_seconds+' s'],['结构化 JSON 解析失败',fmt(M.meta.json_parse_errors)],['生成时间',M.meta.generated_at]]);
const mc=M.manifest.normalization;
const xrows=[['normalization.counts.events',mc.counts.events,M.meta.rows_scanned],['mapped',mc.normalization_status_counts.mapped,nstat.mapped||0],['unresolved',mc.normalization_status_counts.unresolved,nstat.unresolved||0],['cleaning admissions',M.manifest.workflow.stages.cleaning.counts.admissions,O.hadms]];
document.querySelector('#xcheck tbody').innerHTML=xrows.map(([n,a,b])=>`<tr><td>${n}</td><td class="num">${fmt(a)}</td><td class="num">${fmt(b)}</td><td>${a===b?'✓':'✗'}</td></tr>`).join('');
document.querySelector('#mapTable tbody').innerHTML=Object.entries(M.meta.domain_map).map(([k,v])=>`<tr><td class="mono">${k}</td><td>${v}</td></tr>`).join('');
</script></body></html>
'''


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    metrics = json.loads(METRICS.read_text(encoding="utf-8"))
    # 构建前自检
    kinds = {k["kind"] for k in metrics["overview"]["kinds"]}
    assert metrics["meta"]["rows_scanned"] == metrics["manifest"]["normalization"]["counts"]["events"]
    assert metrics["normalization"]["status"]["mapped"] == metrics["manifest"]["normalization"]["normalization_status_counts"]["mapped"]
    print("cleaning_status:", metrics["overview"]["cleaning_status"])
    print("kinds present:", len(kinds), "| administrative_group_recorded present:", "administrative_group_recorded" in kinds)
    html = TEMPLATE.replace("__METRICS__", safe_json(metrics))
    HTML_OUT.write_text(html, encoding="utf-8")
    print(f"written: {HTML_OUT} ({HTML_OUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
