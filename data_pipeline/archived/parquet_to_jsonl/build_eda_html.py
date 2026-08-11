"""Generate a self-contained HTML EDA report with 18 charts embedded as base64."""
from __future__ import annotations
import base64, logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

EDA_DIR = Path("D:/Projects/llm_benchmark/data/eda")
OUTPUT = Path("D:/Projects/llm_benchmark/data/EDA分析报告.html")

CHART_FILES = [
    "01_demographics.png", "02_vitals.png", "03_narrative.png",
    "04_diagnoses.png", "05_investigations.png", "06_microbiology_radiology.png",
    "07_treatments.png", "08_disposition.png", "09_completeness.png",
    "10_correlation.png", "11_data_density.png", "12_disease_chapters.png",
    "13_chapter_by_age.png", "14_chapter_by_sex.png", "15_top_dx_per_chapter.png",
    "16_comorbidity.png", "17_top50_diagnoses.png", "18_chapter_age_heatmap.png",
]

SECTIONS = [
    ("s1",  "1. 数据总览"),
    ("s2",  "2. 人口学特征"),
    ("s3",  "3. 生命体征"),
    ("s4",  "4. 叙事文本"),
    ("s5",  "5. 疾病诊断分布"),
    ("s6",  "6. 检查检验"),
    ("s7",  "7. 微生物与影像"),
    ("s8",  "8. 治疗处置"),
    ("s9",  "9. 去向与转科"),
    ("s10", "10. 数据完整性与质量"),
    ("s11", "11. 指标相关性"),
    ("s12", "12. 疾病章节深度分析"),
]

def img64(fn):
    p = EDA_DIR / fn
    return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode("ascii")

def build():
    logger.info("Encoding 18 charts...")
    imgs = [img64(f) for f in CHART_FILES]
    logger.info("Building HTML...")
    html = render(imgs)
    OUTPUT.write_text(html, encoding="utf-8")
    logger.info("Done: %s (%.1f MB)", OUTPUT, len(html.encode("utf-8")) / 1048576)

def fig(src, caption, full=False):
    klass = "chart-full" if full else "chart"
    return ('<figure class="' + klass + '"><img src="' + src + '" alt="' + caption +
            '" loading="lazy"><figcaption>' + caption + "</figcaption></figure>")

def two_col(l, r):
    return '<div class="two-col">' + l + r + "</div>"

def card(title, body):
    return '<div class="card"><h2>' + title + "</h2>" + body + "</div>"

def anchor(sid, html):
    return '<section id="' + sid + '">' + html + "</section>"

def render(c):
    p = []
    p.append("<!DOCTYPE html><html lang='zh-CN'><head><meta charset='UTF-8'>")
    p.append("<meta name='viewport' content='width=device-width,initial-scale=1.0'>")
    p.append("<title>MIMIC-IV RWD Benchmark EDA</title>")
    p.append("<style>" + CSS + "</style></head><body>")
    p.append(HERO)
    p.append(build_nav())
    p.append("<div class='container'>")
    p.append(build_toc())
    # Section 1
    p.append(anchor("s1", card("1. 数据总览", OVERVIEW)))
    # Section 2
    p.append(anchor("s2", card("2. 人口学特征", DEMO + fig(c[0], "图 1: 人口学特征 — 年龄分布、性别比例、入院类型 Top 10、年龄段构成"))))
    # Section 3
    p.append(anchor("s3", card("3. 生命体征", VITALS + fig(c[1], "图 2: 生命体征分布 — 7 项指标直方图 + 心律 Top 8"))))
    # Section 4
    p.append(anchor("s4", card("4. 叙事文本", NARRATIVE + fig(c[2], "图 3: 叙事文本长度分布 — 9 个字段的字符数直方图和填充率"))))
    # Section 5
    dx = DX + fig(c[3], "图 4: 诊断分析 — ICD 版本饼图、合并症数量分布、主诊断 Top 20")
    dx += fig(c[16], "图 5: 主诊断 Top 50 完整排名", full=True)
    dx += fig(c[15], "图 6: 合并症分布与最常见共病 Top 20")
    p.append(anchor("s5", card("5. 疾病诊断分布", dx)))
    # Section 6
    p.append(anchor("s6", card("6. 检查检验", INVEST + fig(c[4], "图 7: 检查检验 — 检验项目数分布、最常见检验 Top 20、微生物和影像数量分布"))))
    # Section 7
    p.append(anchor("s7", card("7. 微生物与影像", MICRORAD + fig(c[5], "图 8: 微生物与影像 — 标本类型 Top 15、病原体 Top 15、检查类型 Top 15"))))
    # Section 8
    p.append(anchor("s8", card("8. 治疗处置", TREAT + fig(c[6], "图 9: 治疗处置 — 5 类记录数量分布 + 最常处方药物 Top 20"))))
    # Section 9
    p.append(anchor("s9", card("9. 去向与转科", DISP + fig(c[7], "图 10: 去向与转科 — 出院去向、入院来源、负责科室、DRG/ICU 覆盖、转科路径"))))
    # Section 10
    p.append(anchor("s10", card("10. 数据完整性与质量", COMP + fig(c[8], "图 11: 数据完整性矩阵 — 20 个字段填充率"))))
    # Section 11
    corr = CORR + fig(c[9], "图 12: Visit 级指标相关性热力图")
    corr += fig(c[10], "图 13: 数据密度与年龄趋势 — 每 visit 事件总数分布 + 年龄 vs 合并症散点")
    p.append(anchor("s11", card("11. 指标相关性", corr)))
    # Section 12
    dis = DISEASE + fig(c[11], "图 14: ICD 章节分布总览 — 柱图 + 饼图")
    dis += two_col(
        fig(c[12], "图 15: 章节x年龄堆叠条形图"),
        fig(c[13], "图 16: 章节x性别对比图"),
    )
    dis += fig(c[17], "图 17: 章节内年龄分布热力图")
    dis += fig(c[14], "图 18: 各主要章节内 Top 5 具体诊断", full=True)
    p.append(anchor("s12", card("12. 疾病章节深度分析", dis)))
    p.append("</div>")
    p.append(BACK_TOP)
    p.append("</body></html>")
    return "\n".join(p)

def build_nav():
    links = "".join(
        '<a href="#' + sid + '">' + title.split(". ", 1)[1].split(" ")[0] + "</a>"
        for sid, title in SECTIONS
    )
    return "<nav class='topnav' id='topnav'>" + links + "</nav>"

def build_toc():
    links = "".join(
        '<a href="#' + sid + '">' + title + "</a>"
        for sid, title in SECTIONS
    )
    return "<div class='toc'><h2>目录</h2><div class='toc-grid'>" + links + "</div></div>"

CSS = """
:root{--bg:#f1f5f9;--card-bg:#fff;--accent:#1d4ed8;--accent-light:#dbeafe;
--text:#0f172a;--text2:#475569;--text3:#94a3b8;--border:#e2e8f0;
--green:#059669;--red:#dc2626;--orange:#d97706;--nav-bg:rgba(15,23,42,.92)}
*{margin:0;padding:0;box-sizing:border-box}
html{scroll-behavior:smooth;scroll-padding-top:52px}
body{font-family:"Microsoft YaHei","PingFang SC","Helvetica Neue",sans-serif;background:var(--bg);color:var(--text);line-height:1.75}
.topnav{position:sticky;top:0;z-index:100;background:var(--nav-bg);backdrop-filter:blur(12px);
height:44px;display:flex;align-items:center;gap:2px;padding:0 16px;
overflow-x:auto;white-space:nowrap;scrollbar-width:thin}
.topnav::-webkit-scrollbar{height:3px}
.topnav::-webkit-scrollbar-thumb{background:rgba(255,255,255,.2);border-radius:2px}
.topnav a{color:rgba(255,255,255,.6);text-decoration:none;font-size:12px;font-weight:500;
padding:6px 11px;border-radius:6px;transition:color .15s,background .15s;flex-shrink:0}
.topnav a:hover,.topnav a.active{color:#fff;background:rgba(255,255,255,.12)}
.hero{background:linear-gradient(135deg,#0f172a 0%,#1e3a5f 40%,#1d4ed8 100%);
color:#fff;padding:56px 40px 44px;text-align:center}
.hero h1{font-size:30px;font-weight:800;margin-bottom:10px;letter-spacing:-.5px}
.hero .sub{font-size:14px;opacity:.65}
.hero .stats{display:flex;flex-wrap:wrap;justify-content:center;gap:36px;margin-top:32px}
.hero .stat{text-align:center}
.hero .stat .num{font-size:30px;font-weight:800}
.hero .stat .label{font-size:11px;opacity:.55;text-transform:uppercase;letter-spacing:.5px;margin-top:2px}
.container{max-width:1100px;margin:0 auto;padding:28px 20px}
.card{background:var(--card-bg);border-radius:14px;padding:32px;margin-bottom:24px;
box-shadow:0 1px 2px rgba(0,0,0,.04),0 4px 12px rgba(0,0,0,.03);border:1px solid var(--border)}
.card h2{font-size:21px;font-weight:700;margin-bottom:18px;padding-bottom:12px;
border-bottom:1px solid var(--border);display:flex;align-items:center;gap:8px}
.card h2::before{content:"";width:4px;height:22px;background:var(--accent);border-radius:2px;flex-shrink:0}
.card p{margin-bottom:12px;font-size:14px;color:var(--text2);line-height:1.8}
.two-col{display:grid;grid-template-columns:1fr 1fr;gap:20px;align-items:start;margin:16px 0}
@media(max-width:820px){.two-col{grid-template-columns:1fr}}
figure{margin:20px 0}
figure img{width:100%;height:auto;display:block;border-radius:10px;border:1px solid var(--border);
box-shadow:0 2px 8px rgba(0,0,0,.06);transition:box-shadow .2s,transform .2s}
figure img:hover{box-shadow:0 8px 24px rgba(0,0,0,.12);transform:translateY(-2px)}
figcaption{font-size:12px;color:var(--text3);text-align:center;margin-top:8px;font-style:italic}
table{width:100%;border-collapse:collapse;margin:14px 0;font-size:13px}
th{background:#f8fafc;font-weight:600;padding:9px 14px;text-align:left;border-bottom:2px solid var(--border);
font-size:12px;text-transform:uppercase;letter-spacing:.3px}
td{padding:8px 14px;border-bottom:1px solid var(--border);color:var(--text2)}
tr:last-child td{border-bottom:none}
tr:hover td{background:#f8fafc}
.badge{display:inline-block;padding:2px 10px;border-radius:6px;font-size:11px;font-weight:600}
.badge-green{background:#d1fae5;color:var(--green)}
.badge-orange{background:#fef3c7;color:var(--orange)}
.insight{background:#f0f7ff;border-left:3px solid var(--accent);padding:14px 18px;margin:16px 0;
border-radius:0 10px 10px 0;font-size:14px;color:var(--text)}
.insight strong{color:var(--accent);font-weight:600}
.toc{background:var(--card-bg);border-radius:14px;padding:28px 32px;margin-bottom:24px;
border:1px solid var(--border);box-shadow:0 1px 2px rgba(0,0,0,.04)}
.toc h2{font-size:17px;font-weight:700;margin-bottom:14px}
.toc-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px 24px}
@media(max-width:700px){.toc-grid{grid-template-columns:repeat(2,1fr)}}
.toc-grid a{color:var(--accent);text-decoration:none;font-size:13px;padding:4px 0}
.toc-grid a:hover{color:var(--text);text-decoration:underline}
.back-top{position:fixed;bottom:28px;right:28px;z-index:90;width:44px;height:44px;border-radius:50%;
background:var(--nav-bg);color:#fff;border:none;cursor:pointer;font-size:18px;
display:flex;align-items:center;justify-content:center;opacity:0;pointer-events:none;
transition:opacity .3s;box-shadow:0 4px 16px rgba(0,0,0,.15)}
.back-top.visible{opacity:1;pointer-events:auto}
.back-top:hover{background:#1d4ed8}
.footer{text-align:center;padding:36px 24px;color:var(--text3);font-size:13px}
"""

HERO = """
<div class="hero">
<h1>MIMIC-IV RWD Benchmark — EDA 分析报告</h1>
<div class="sub">rwd_benchmark_visits.jsonl &nbsp;|&nbsp; 2026-08-07 &nbsp;|&nbsp; 320,267 visits &nbsp;|&nbsp; 27.37 GB</div>
<div class="stats">
<div class="stat"><div class="num">320K</div><div class="label">Visits</div></div>
<div class="stat"><div class="num">27.4GB</div><div class="label">Volume</div></div>
<div class="stat"><div class="num">47</div><div class="label">Fields</div></div>
<div class="stat"><div class="num">18</div><div class="label">Charts</div></div>
<div class="stat"><div class="num">61.7</div><div class="label">Mean Age</div></div>
</div>
</div>
"""

OVERVIEW = """
<table>
<tr><th>指标</th><th>数值</th></tr>
<tr><td>总 visit 数</td><td><strong>320,267</strong></td></tr>
<tr><td>文件大小</td><td>27.37 GB (JSONL)</td></tr>
<tr><td>平均每条</td><td>~90 KB</td></tr>
<tr><td>年龄（均值/中位）</td><td>61.7 / 63 岁</td></tr>
<tr><td>性别（F/M）</td><td>163,476 / 156,791（51.0% / 49.0%）</td></tr>
<tr><td>Triage 覆盖</td><td>145,607（45.5%）<span class="badge badge-orange">仅 ED</span></td></tr>
<tr><td>ICU 入住</td><td>62,886（19.6%）</td></tr>
<tr><td>DRG 覆盖</td><td>274,250（85.6%）</td></tr>
<tr><td>检验项目/visit</td><td>均值 51.8，中位 50</td></tr>
<tr><td>合并症/visit</td><td>均值 11.6，中位 10</td></tr>
</table>
<div class="insight"><strong>要点:</strong> 数据集以中老年住院患者为主（60+ 占 57.5%），性别均衡，接近半数经过急诊流程。每条 visit 的临床信息密度高（平均 52 个检验项目 + 11 个合并症 + 出院小结全文），适合作为 LLM 临床推理 benchmark 的数据基础。</div>
"""

DEMO = """
<p>年龄分布呈典型的住院人群特征：以 60-74 岁（30.7%）和 75 岁以上（26.8%）为主力群体，合计占比 57.5%。18-44 岁仅占 18.3%。性别分布均衡，女性略多（51.0%）。</p>
<p>入院类型以急诊为主导：<strong>EW EMER.</strong>（急诊）占 43.4%，加上海外观察病房（OBSERVATION ADMIT 15.5%、EU OBSERVATION 9.7%），超过 68% 的入院与急诊流程相关。</p>
<div class="insight"><strong>解读:</strong> 年龄和入院类型分布决定了 triage 生命体征的覆盖率（45.5%）——仅 ED 就诊患者有分诊数据。择期手术和直接入院患者没有 triage 记录，这不是数据缺失而是 MIMIC 结构性特征。</div>
"""

VITALS = """
<p>7 项 triage 生命体征的分布均在生理合理范围内。中位体温 98F、心率 85 bpm、呼吸 18 次/分、血氧 98%、收缩压 132 mmHg、舒张压 75 mmHg，ESI 分级中位 2（对应"不应等待"级别）。</p>
<div class="insight"><strong>注意:</strong> Triage 数据的填充率约 42-45%，仅 ED 就诊患者有此数据。心律（rhythm）填充率极低（约 1%），因 ED vital signs 表中 rhythm 大多为空值。</div>
"""

NARRATIVE = """
<p>出院小结（DS）是数据集中最核心的叙事文本来源。各章节的解析填充率如下：</p>
<table>
<tr><th>字段</th><th>填充率</th><th>中位长度</th><th>最大长度</th></tr>
<tr><td>主诉 Chief Complaint</td><td><span class="badge badge-green">100%</span></td><td>19 字符</td><td>8,635</td></tr>
<tr><td>现病史 HPI</td><td><span class="badge badge-green">98.9%</span></td><td>1,299</td><td>19,717</td></tr>
<tr><td>既往史 PMH</td><td><span class="badge badge-green">95.2%</span></td><td>240</td><td>21,778</td></tr>
<tr><td>入院用药</td><td><span class="badge badge-green">94.3%</span></td><td>310</td><td>26,568</td></tr>
<tr><td>过敏史</td><td><span class="badge badge-green">100%</span></td><td>61</td><td>927</td></tr>
<tr><td>体格检查</td><td><span class="badge badge-green">94.2%</span></td><td>810</td><td>14,018</td></tr>
<tr><td>出院小结全文</td><td><span class="badge badge-green">100%</span></td><td>9,879</td><td>58,596</td></tr>
</table>
<div class="insight"><strong>文本质量:</strong> DS 全文保留了完整的出院小结原文（中位近 1 万字符），即使章节解析失败的 3.5% 也有全文兜底。现病史是最长的结构化章节（中位 1,299 字符），提供了丰富的临床推理上下文。</div>
"""

DX = """
<p>ICD 版本分布：<strong>ICD-9-CM 63.6%</strong>（203,803 条）与 <strong>ICD-10-CM 36.4%</strong>（116,464 条）共存。这与 MIMIC-IV 的数据采集时间跨度有关——早期数据使用 ICD-9，后期转为 ICD-10。</p>
<p>Top 5 个体诊断覆盖了内科急诊的核心病种：急性肾衰竭、化疗就诊、冠状动脉粥样硬化、尿路感染、肺炎。合并症负担重：平均每条 visit 有 11.6 个其他诊断，中位 10 个。</p>
"""

INVEST = """
<p>实验室检验覆盖率极高：93.8% 的 visit 有检验记录，平均每条 51.8 个检验项目。最常见的检验项目覆盖近 30 万条 visit——血常规全套（Hematocrit、Hemoglobin、Platelet、WBC、MCV、MCH、MCHC、RDW、RBC）和基础代谢面板（Glucose、Creatinine、BUN、Potassium、Sodium、Chloride）几乎成为入院标配。</p>
"""

MICRORAD = """
<p><strong>微生物学:</strong> 60.9% 的 visit 有微生物学记录。最常见标本为血培养（46.3 万）、尿培养（41.6 万）和痰培养（13.5 万）。最常见病原体依次为大肠杆菌（17.7 万）、凝固酶阳性葡萄球菌（10.5 万）和肺炎克雷伯菌（6.0 万），与脓毒症和尿路感染的主诊断分布一致。</p>
<p><strong>影像报告:</strong> 82.5% 的 visit 有影像记录，以胸片为主（PORTABLE AP、PA/LAT、Radiograph），其次为头部 CT。</p>
"""

TREAT = """
<p>处方和药房医嘱几乎覆盖全部 visit（99.8%），平均每条 44 个处方记录和 39 个药房医嘱。给药记录（emar）覆盖 47.9%，平均 73 条/visit。操作记录（ICD 编码）覆盖 58.5%。</p>
<p>最常处方药物以住院常规用药为主：Insulin（56.6 万）、0.9% NaCl（53.8 万）、KCl（43.4 万）、Acetaminophen（39.3 万），反映了血糖管理、液体平衡和症状缓解的核心地位。</p>
"""

DISP = """
<p>出院去向以回家为主（HOME 39.6%、HOME HEALTH CARE 22.0%），但 12.9% 转入专业护理机构（SNF），3.2% 进入康复。入院来源中急诊室占 53.4%，门诊医生转诊 25.1%。</p>
<p>负责科室以内科（MED）占绝对主导（13.9 万），其次外科（SURG 3.3 万）、社区内科（CMED 3.0 万）。平均转科 3.8 次/visit。</p>
"""

COMP = """
<p>20 个核心字段的填充率矩阵如下。绿色（>=90%）字段构成出题的可靠数据基础，蓝色（50-89%）需注意条件覆盖，红色（<50%）为 ED 专有数据。</p>
<div class="insight"><strong>质量评估:</strong> 核心临床字段（主诉、主诊断、处方、出院小结全文）填充率 >=95%，满足出题需求。Triage 生命体征（45%）和入院前用药 medrecon（~35%）的低覆盖率由 ED 专属数据源决定，出题时可作为可选上下文而非必需字段。</div>
"""

CORR = """
<p>Visit 级别的 12 个指标（年龄、合并症数、检验项目数、微生物数、影像数、处方数等）的 Pearson 相关性矩阵。处方数、药房医嘱、给药记录三者高度正相关（r > 0.9），反映药物管理流程的联动性。DS 文本长度与检验项目数正相关（r ~ 0.5），说明病情复杂的患者倾向于产生更长的出院小结。</p>
"""

DISEASE = """
<p>ICD 编码归入 17+ 个章节后，疾病谱的宏观结构清晰可见：</p>
<table>
<tr><th>章节</th><th>人数</th><th>占比</th></tr>
<tr><td>循环系统疾病</td><td>61,393</td><td>19.2%</td></tr>
<tr><td>消化系统疾病</td><td>44,136</td><td>13.8%</td></tr>
<tr><td>损伤与中毒</td><td>27,017</td><td>8.4%</td></tr>
<tr><td>肿瘤</td><td>23,102</td><td>7.2%</td></tr>
<tr><td>症状/体征/不确定</td><td>21,681</td><td>6.8%</td></tr>
<tr><td>呼吸系统疾病</td><td>19,679</td><td>6.1%</td></tr>
<tr><td>泌尿生殖系统疾病</td><td>19,171</td><td>6.0%</td></tr>
<tr><td>感染与寄生虫病</td><td>17,176</td><td>5.4%</td></tr>
<tr><td>肌肉骨骼系统疾病</td><td>15,995</td><td>5.0%</td></tr>
</table>
<div class="insight"><strong>疾病谱:</strong> 循环系统（19.2%）居首，涵盖冠心病、心衰、心梗、心律失常等高发病种。消化系统（13.8%）包含胆道疾病、胰腺炎、消化道出血。损伤中毒（8.4%）和肿瘤（7.2%）紧随其后。该分布与三级医院住院构成一致，为多病种临床推理 benchmark 提供了均衡的疾病覆盖。</div>
"""

BACK_TOP = """
<button class="back-top" onclick="window.scrollTo({top:0,behavior:'smooth'})" title="回到顶部">&#8593;</button>
<script>
var nav=document.getElementById('topnav');
var links=nav?nav.querySelectorAll('a'):[];
var secs=document.querySelectorAll('section[id]');
function onScroll(){
  var b=document.querySelector('.back-top');
  if(window.scrollY>600){b.classList.add('visible')}else{b.classList.remove('visible')}
  var cur='';
  secs.forEach(function(s){if(window.scrollY>=s.offsetTop-80){cur=s.id}});
  links.forEach(function(a){
    var href=a.getAttribute('href');
    if(href==='#'+cur){a.classList.add('active')}
    else{a.classList.remove('active')}
  });
}
window.addEventListener('scroll',onScroll,{passive:true});
onScroll();
</script>
"""

if __name__ == "__main__":
    build()
