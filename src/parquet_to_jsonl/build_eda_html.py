"""Generate a self-contained HTML EDA report with 18 charts embedded as base64."""
from __future__ import annotations
import base64
import logging
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
def img64(filename: str) -> str:
    p = EDA_DIR / filename
    data = base64.b64encode(p.read_bytes()).decode("ascii")
    return "data:image/png;base64," + data
def build():
    logger.info("Reading 18 charts and encoding base64...")
    imgs = [img64(f) for f in CHART_FILES]
    logger.info("Building HTML...")
    html = render(imgs)
    OUTPUT.write_text(html, encoding="utf-8")
    size_mb = len(html.encode("utf-8")) / (1024 * 1024)
    logger.info("Written %s (%.1f MB)", OUTPUT, size_mb)
def render(imgs: list[str]) -> str:
    c = imgs
    parts = []
    parts.append("<!DOCTYPE html>")
    parts.append('<html lang="zh-CN">')
    parts.append("<head>")
    parts.append('<meta charset="UTF-8">')
    parts.append('<meta name="viewport" content="width=device-width, initial-scale=1.0">')
    parts.append("<title>MIMIC-IV RWD Benchmark EDA</title>")
    parts.append("<style>")
    parts.append(STYLE)
    parts.append("</style>")
    parts.append("</head>")
    parts.append("<body>")
    parts.append(HERO)
    parts.append('<div class="container">')
    parts.append(TOC)
    parts.append(section("1", "数据总览", OVERVIEW_HTML))
    parts.append(section_img("2", "人口学特征", DEMO_HTML, c[0], "图 1: 人口学特征 — 年龄分布、性别比例、入院类型 Top 10、年龄段构成"))
    parts.append(section_img("3", "生命体征", VITALS_HTML, c[1], "图 2: 生命体征分布 — 7 项指标直方图 + 心律 Top 8"))
    parts.append(section_img("4", "叙事文本", NARRATIVE_HTML, c[2], "图 3: 叙事文本长度分布 — 9 个字段的字符数直方图和填充率"))
    parts.append(section_dx(c[3], c[16], c[15]))
    parts.append(section_img("6", "检查检验", INVEST_HTML, c[4], "图 7: 检查检验 — 检验项目数分布、最常见检验 Top 20、微生物和影像数量分布"))
    parts.append(section_img("7", "微生物与影像", MICRORAD_HTML, c[5], "图 8: 微生物与影像 — 标本类型 Top 15、病原体 Top 15、检查类型 Top 15"))
    parts.append(section_img("8", "治疗处置", TREAT_HTML, c[6], "图 9: 治疗处置 — 5 类记录数量分布 + 最常处方药物 Top 20"))
    parts.append(section_img("9", "去向与转科", DISP_HTML, c[7], "图 10: 去向与转科 — 出院去向、入院来源、负责科室、DRG/ICU 覆盖、转科路径"))
    parts.append(section_img("10", "数据完整性与质量", COMP_HTML, c[8], "图 11: 数据完整性矩阵 — 20 个字段填充率"))
    parts.append(section_corr(c[9], c[10]))
    parts.append(section_disease(c[11], c[12], c[13], c[17], c[14]))
    parts.append("</div>")
    parts.append(FOOTER)
    parts.append("</body>")
    parts.append("</html>")
    return "\n".join(parts)
def card(title: str, body: str) -> str:
    return '<div class="card"><h2>' + title + "</h2>" + body + "</div>"
def fig(src: str, caption: str, full: bool = False) -> str:
    klass = "chart-full" if full else "chart"
    return '<figure class="' + klass + '"><img src="' + src + '" alt="' + caption + '" loading="lazy"><figcaption>' + caption + "</figcaption></figure>"
def two_col(left: str, right: str) -> str:
    return '<div class="two-col">' + left + right + "</div>"
def section(num: str, title: str, body: str) -> str:
    return card(num + ". " + title, body)
def section_img(num: str, title: str, body: str, img: str, caption: str) -> str:
    return card(num + ". " + title, body + fig(img, caption))
def section_dx(img4: str, img17: str, img16: str) -> str:
    body = DX_HTML
    body += fig(img4, "图 4: 诊断分析 — ICD 版本饼图、合并症数量分布、主诊断 Top 20")
    body += fig(img17, "图 5: 主诊断 Top 50 完整排名", full=True)
    body += fig(img16, "图 6: 合并症分布与最常见共病 Top 20")
    return card("5. 疾病诊断分布", body)
def section_corr(img10: str, img11: str) -> str:
    body = CORR_HTML
    body += fig(img10, "图 12: Visit 级指标相关性热力图")
    body += fig(img11, "图 13: 数据密度与年龄趋势 — 每 visit 事件总数分布 + 年龄 vs 合并症散点")
    return card("11. 指标相关性", body)
def section_disease(img12: str, img13: str, img14: str, img18: str, img15: str) -> str:
    body = DISEASE_HTML
    body += fig(img12, "图 14: ICD 章节分布总览 — 柱图 + 饼图")
    body += two_col(
        fig(img13, "图 15: 章节x年龄堆叠条形图"),
        fig(img14, "图 16: 章节x性别对比图"),
    )
    body += fig(img18, "图 17: 章节内年龄分布热力图")
    body += fig(img15, "图 18: 各主要章节内 Top 5 具体诊断", full=True)
    return card("12. 疾病章节深度分析", body)
STYLE = """
:root { --bg:#f8fafc; --card-bg:#fff; --accent:#2563eb; --accent-light:#dbeafe;
    --text:#1e293b; --text2:#64748b; --border:#e2e8f0; --green:#059669; --red:#dc2626; --orange:#d97706; }
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:"Microsoft YaHei","PingFang SC","Helvetica Neue",sans-serif; background:var(--bg); color:var(--text); line-height:1.7; }
.hero { background:linear-gradient(135deg,#1e3a5f 0%,#2563eb 100%); color:#fff; padding:60px 40px 40px; text-align:center; }
.hero h1 { font-size:28px; font-weight:700; margin-bottom:12px; }
.hero .sub { font-size:15px; opacity:.85; }
.hero .stats { display:flex; flex-wrap:wrap; justify-content:center; gap:32px; margin-top:28px; }
.hero .stat { text-align:center; }
.hero .stat .num { font-size:28px; font-weight:700; }
.hero .stat .label { font-size:12px; opacity:.75; margin-top:2px; }
.container { max-width:1200px; margin:0 auto; padding:32px 24px; }
.card { background:var(--card-bg); border-radius:12px; padding:28px; margin-bottom:28px; box-shadow:0 1px 3px rgba(0,0,0,.06); border:1px solid var(--border); }
.card h2 { font-size:20px; font-weight:700; margin-bottom:16px; padding-bottom:10px; border-bottom:2px solid var(--accent); }
.card p { margin-bottom:12px; font-size:14px; }
.two-col { display:grid; grid-template-columns:1fr 1fr; gap:20px; align-items:start; }
@media(max-width:768px){ .two-col{ grid-template-columns:1fr; } }
figure { margin:16px 0; }
figure img { width:100%; border-radius:8px; border:1px solid var(--border); display:block; }
figcaption { font-size:12px; color:var(--text2); text-align:center; margin-top:8px; }
.chart img { max-height:600px; object-fit:contain; }
.chart-full img { max-height:800px; object-fit:contain; }
table { width:100%; border-collapse:collapse; margin:12px 0; font-size:13px; }
th { background:var(--accent-light); font-weight:600; padding:8px 12px; text-align:left; border:1px solid var(--border); }
td { padding:7px 12px; border:1px solid var(--border); }
tr:nth-child(even){ background:#f8fafc; }
.badge { display:inline-block; padding:2px 10px; border-radius:12px; font-size:12px; font-weight:600; }
.badge-green { background:#d1fae5; color:var(--green); }
.badge-orange { background:#fef3c7; color:var(--orange); }
.insight { background:#eff6ff; border-left:4px solid var(--accent); padding:12px 16px; margin:16px 0; border-radius:0 8px 8px 0; font-size:14px; }
.insight strong { color:var(--accent); }
.toc { background:var(--card-bg); border-radius:12px; padding:24px 28px; margin-bottom:28px; border:1px solid var(--border); }
.toc h2 { font-size:18px; border-bottom:2px solid var(--accent); padding-bottom:8px; margin-bottom:12px; }
.toc ol { margin-left:20px; }
.toc a { color:var(--accent); text-decoration:none; }
.footer { text-align:center; padding:32px; color:var(--text2); font-size:13px; }
"""
HERO = """
<div class="hero">
<h1>MIMIC-IV RWD Benchmark — 全量 EDA 分析报告</h1>
<div class="sub">数据源: rwd_benchmark_visits.jsonl | 生成时间: 2026-08-07 | 320,267 条 visit | 27.37 GB</div>
<div class="stats">
<div class="stat"><div class="num">320K</div><div class="label">总 visit 数</div></div>
<div class="stat"><div class="num">27.4 GB</div><div class="label">数据体积</div></div>
<div class="stat"><div class="num">47</div><div class="label">字段数</div></div>
<div class="stat"><div class="num">18</div><div class="label">分析图表</div></div>
<div class="stat"><div class="num">61.7</div><div class="label">平均年龄</div></div>
</div>
</div>
"""
TOC = """
<div class="toc">
<h2>目录</h2>
<ol>
<li><a href="#s1">数据总览</a></li>
<li><a href="#s2">人口学特征</a></li>
<li><a href="#s3">生命体征</a></li>
<li><a href="#s4">叙事文本</a></li>
<li><a href="#s5">疾病诊断分布</a></li>
<li><a href="#s6">检查检验</a></li>
<li><a href="#s7">微生物与影像</a></li>
<li><a href="#s8">治疗处置</a></li>
<li><a href="#s9">去向与转科</a></li>
<li><a href="#s10">数据完整性与质量</a></li>
<li><a href="#s11">指标相关性</a></li>
<li><a href="#s12">疾病章节深度分析</a></li>
</ol>
</div>
"""
OVERVIEW_HTML = """
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
DEMO_HTML = """
<p>年龄分布呈典型的住院人群特征：以 60-74 岁（30.7%）和 75 岁以上（26.8%）为主力群体，合计占比 57.5%。18-44 岁仅占 18.3%。性别分布均衡，女性略多（51.0%）。</p>
<p>入院类型以急诊为主导：<strong>EW EMER.</strong>（急诊）占 43.4%，加上海外观察病房（OBSERVATION ADMIT 15.5%、EU OBSERVATION 9.7%），超过 68% 的入院与急诊流程相关。</p>
<div class="insight"><strong>解读:</strong> 年龄和入院类型分布决定了 triage 生命体征的覆盖率（45.5%）——仅 ED 就诊患者有分诊数据。择期手术和直接入院患者没有 triage 记录，这不是数据缺失而是 MIMIC 结构性特征。</div>
"""
VITALS_HTML = """
<p>7 项 triage 生命体征的分布均在生理合理范围内。中位体温 98F、心率 85 bpm、呼吸 18 次/分、血氧 98%、收缩压 132 mmHg、舒张压 75 mmHg，ESI 分级中位 2（对应"不应等待"级别）。</p>
<div class="insight"><strong>注意:</strong> Triage 数据的填充率约 42-45%，仅 ED 就诊患者有此数据。心律（rhythm）填充率极低（约 1%），因 ED vital signs 表中 rhythm 大多为空值。</div>
"""
NARRATIVE_HTML = """
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
DX_HTML = """
<p>ICD 版本分布：<strong>ICD-9-CM 63.6%</strong>（203,803 条）与 <strong>ICD-10-CM 36.4%</strong>（116,464 条）共存。这与 MIMIC-IV 的数据采集时间跨度有关——早期数据使用 ICD-9，后期转为 ICD-10。</p>
<p>Top 5 个体诊断覆盖了内科急诊的核心病种：急性肾衰竭、化疗就诊、冠状动脉粥样硬化、尿路感染、肺炎。合并症负担重：平均每条 visit 有 11.6 个其他诊断，中位 10 个。</p>
"""
INVEST_HTML = """
<p>实验室检验覆盖率极高：93.8% 的 visit 有检验记录，平均每条 51.8 个检验项目。最常见的检验项目覆盖近 30 万条 visit——血常规全套（Hematocrit、Hemoglobin、Platelet、WBC、MCV、MCH、MCHC、RDW、RBC）和基础代谢面板（Glucose、Creatinine、BUN、Potassium、Sodium、Chloride）几乎成为入院标配。</p>
"""
MICRORAD_HTML = """
<p><strong>微生物学:</strong> 60.9% 的 visit 有微生物学记录。最常见标本为血培养（46.3 万）、尿培养（41.6 万）和痰培养（13.5 万）。最常见病原体依次为大肠杆菌（17.7 万）、凝固酶阳性葡萄球菌（10.5 万）和肺炎克雷伯菌（6.0 万），与脓毒症和尿路感染的主诊断分布一致。</p>
<p><strong>影像报告:</strong> 82.5% 的 visit 有影像记录，以胸片为主（PORTABLE AP、PA/LAT、Radiograph），其次为头部 CT。</p>
"""
TREAT_HTML = """
<p>处方和药房医嘱几乎覆盖全部 visit（99.8%），平均每条 44 个处方记录和 39 个药房医嘱。给药记录（emar）覆盖 47.9%，平均 73 条/visit。操作记录（ICD 编码）覆盖 58.5%。</p>
<p>最常处方药物以住院常规用药为主：Insulin（56.6 万）、0.9% NaCl（53.8 万）、KCl（43.4 万）、Acetaminophen（39.3 万），反映了血糖管理、液体平衡和症状缓解的核心地位。</p>
"""
DISP_HTML = """
<p>出院去向以回家为主（HOME 39.6%、HOME HEALTH CARE 22.0%），但 12.9% 转入专业护理机构（SNF），3.2% 进入康复。入院来源中急诊室占 53.4%，门诊医生转诊 25.1%。</p>
<p>负责科室以内科（MED）占绝对主导（13.9 万），其次外科（SURG 3.3 万）、社区内科（CMED 3.0 万）。平均转科 3.8 次/visit。</p>
"""
COMP_HTML = """
<p>20 个核心字段的填充率矩阵如下。绿色（>=90%）字段构成出题的可靠数据基础，蓝色（50-89%）需注意条件覆盖，红色（<50%）为 ED 专有数据。</p>
<div class="insight"><strong>质量评估:</strong> 核心临床字段（主诉、主诊断、处方、出院小结全文）填充率 >=95%，满足出题需求。Triage 生命体征（45%）和入院前用药 medrecon（~35%）的低覆盖率由 ED 专属数据源决定，出题时可作为可选上下文而非必需字段。</div>
"""
CORR_HTML = """
<p>Visit 级别的 12 个指标（年龄、合并症数、检验项目数、微生物数、影像数、处方数等）的 Pearson 相关性矩阵。处方数、药房医嘱、给药记录三者高度正相关（r > 0.9），反映药物管理流程的联动性。DS 文本长度与检验项目数正相关（r ~ 0.5），说明病情复杂的患者倾向于产生更长的出院小结。</p>
"""
DISEASE_HTML = """
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
FOOTER = """
<div class="footer">
<p>MIMIC-IV RWD Benchmark &middot; EDA 分析报告 &middot; 2026-08-07</p>
<p>320,267 visits &middot; 27.37 GB JSONL &middot; 18 charts &middot; Generated by Codex</p>
</div>
"""
if __name__ == "__main__":
    build()
