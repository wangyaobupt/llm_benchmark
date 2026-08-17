# 临床文本实体+关系抽取如何开展：人工标注与质量门禁证据笔记

**日期**：2026-08-16
**定位**：为 MIMIC-IV-Note 上的 NER v2 流水线（OpenAI-compatible API 多模型实体+关系抽取、确定性 span 回填、分块、断点续跑已实现；已产出 300 例约 12,596 实体 / 919 关系的 `unreviewed_model_output`）设计**人工标注与质量门禁**：A/B 双人独立标注 → 第三人裁决 → 一致性门禁 → 解锁评测。抽取的下游用途：(a) 为决策时点快照提供文本事实证据；(b) 防未来信息泄漏的语义层工具（文本内容发生在决策时点前/后、是否成立、是否属于患者本人）。文本类型：lab/micro comments、ED 主诉、放射报告、出院小结（约 64,509 个文本单元）。
**写法**：证据笔记。带锚点符号的数字引自项目内另一份方法学笔记（已核实，本文不重复核实，只扩展）；新检证据附内联链接；查不到的明确写"未找到/未核实"；推断性建议一律标注【推断】。

> 状态：已完成（v1.0，2026-08-16）。锚点数字与本次新核实数字在文内分别标注；推断性建议均带【推断】。

## 1. 类型系统（schema）设计应该怎么做

### 1.1 临床 NER 类型系统的四条已验证主路线

| 路线 | 实体层 | 属性层 | 关系层 | 规模/质量锚点（均为系统最优 F1 或人类 IAA，见第 5 节深读） |
|---|---|---|---|---|
| i2b2 2010（通用临床概念） | 3 个粗类：problem / treatment / test | assertion 独立层，6 值（present/absent/possible/conditional/hypothetical/他人） | 8 类（TrIP/TrWP/TrCP/TrAP/TrNAP/TeRP/TeCP/PIP） | 系统评测：实体 exact F1 0.852 / inexact 0.924；断言最优 F 0.936；关系 TrIP 系最优 F 0.737（锚点） |
| [n2c2 2018 T2](https://pmc.ncbi.nlm.nih.gov/articles/PMC7489085/)（药物域细粒度） | 9 类：Drug, ADE, Dosage, Duration, Form, Frequency, Route, Strength, Reason | 无独立属性层（属性全部实体化） | 8 类：Drug–ADE, Drug–Reason, Drug–Dosage, Drug–Duration, Drug–Form, Drug–Frequency, Drug–Route, Drug–Strength | 505 份（303 train / 202 test）；概念 0.9418 / 关系分类 0.9630 / 端到端 0.8905；端到端 ADE–Drug 0.4755、Reason–Drug 0.5961 最差（本次核实+锚点） |
| [RadGraph](https://arxiv.org/abs/2106.14463)（放射专科） | Anatomy + Observation（按确定性分 3 子类：Definitely Present / Uncertain / Definitely Absent） | 确定性编入实体类型；PhysioNet 发布版另含否定/不确定/时间变化等属性（锚点） | 3 类有向关系：Modify, Located At, Suggestive Of | dev 500 份 14,579 实体 + 10,889 关系；模型关系 F1 0.82（MIMIC-CXR）/0.73（CheXpert）（本次核实+锚点） |
| [THYME 2014 TACL](https://pmc.ncbi.nlm.nih.gov/articles/PMC5657277/)（时间域） | EVENT / TIMEX3（UMLS 语义类型锚定） | DocTimeRel（BEFORE/OVERLAP/AFTER）、上下文 aspect、modality | TLINK / ALINK | 人类 IAA：Event 0.8038；DocTimeRel 0.7189；TLINK 0.4506–0.5630（本次核实+锚点） |

设计含义：
- **粗类+独立属性层（i2b2 2010）与细类无属性（n2c2 2018）是两个极端**。i2b2 证明 3 个粗概念即可承载断言与关系两个独立维度并分别评测；n2c2 证明药物域细到 9 类在出院小结上仍可拿到 0.94 的概念 F1——但最难的恰是最"语义"的类型（ADE/Reason）。
- **RadGraph 展示了第二种属性建模**：把确定性直接编进实体类型（3 个 Observation 子类），或作为属性（PhysioNet 版 NEG/UNC/时间变化）。两种都可行，关键是确定性/否定信息必须进入 schema，不能只标裸实体。
- **THYME 展示了"任务驱动的时间三分法"**：DocTimeRel（BEFORE/OVERLAP/AFTER 相对文档时间）正是本项目"决策时点前后"属性的直接先例——THYME 用它替代了全局 TLINK 体系，IAA（0.7189）显著高于自由 TLINK（0.4506–0.5630）。

### 1.2 UMLS/SNOMED 语义类型作为类型空间的选择依据

- THYME 的先例：实体层不自创类型，而是锚定 UMLS 语义类型——原文："we made the decision to annotate all UMLS entities of the types **Disorder, Chemical/Drug, Procedure and Sign/Symptom** as Events"（[THYME 2014](https://pmc.ncbi.nlm.nih.gov/articles/PMC5657277/)）。好处：判据外部化（标注员可查 UMLS），粒度有公开参照，避免自创类型的主观性。
- i2b2 2010 的反例也是证据：3 个粗类（problem/treatment/test）是纯语用分类（"临床叙事里这三类支撑决策"），不与 UMLS 对齐；换来的是极简判据和高 IAA，代价是类型内部高度异质。作为平面实体 schema 双标 IAA 的可比性参照：2014 i2b2/UTHealth 去身份语料 entity/token micro F1 0.895/0.930（[Stubbs & Uzuner 2015, PMC4978170](https://pmc.ncbi.nlm.nih.gov/articles/PMC4978170/)——注意该文是去身份语料论文，非 i2b2 2010 关系任务，见参考资料清单的更正说明）。
- RadGraph 的中间路线：实体类型源自 CheXpert 标注器的 14 个观察目标词表（域内受控词表），而非 UMLS。
- **对本案的建议**【推断】：顶层类型用 UMLS semantic groups 锚定（Chemicals & Drugs / Disorders / Procedures / Sign or Symptom / Anatomy / Physiology 中的 lab & vital），每类在 guideline 里写明"对应 UMLS semantic type 清单"，给标注员一个可查询的判据源；本项目不必照抄 n2c2 的 9 类药物细分（药物属性实体化会放大关系数量与标注负担），除非下游查询确实需要。

### 1.3 类型粒度与 IAA 关系的证据（越"语义/推理型"越难一致）

- THYME：TLINK 只对端点（participants only）IAA 0.5012，加上关系类型后降到 0.4506——**同一层任务，类型维度引入 ~0.05 的一致性损失**（[THYME 2014 Table 3](https://pmc.ncbi.nlm.nih.gov/articles/PMC5657277/)）。
- i2b2 2012：TLINK 文本跨度 IAA 仅 0.39，组织者被迫把 7 类时间关系合并为 3 类（BEFORE/AFTER/OVERLAP），且两版语料都发布（[Sun et al. 2013](https://pmc.ncbi.nlm.nih.gov/articles/PMC3756273/)，锚点）。合并是官方对"粒度超出人类一致性上限"的正式响应。
- n2c2 2018 T2：概念层 Drugs/Strength/Form/Dosage/Frequency/Route 的最优 F1 均 >0.89，**Duration、Reason、ADE 最差**；端到端关系 ADE–Drug 0.4755、Reason–Drug 0.5961。原文归因："These were often missed because local context is insufficient to identify them"，错误"most often caused by the need for inference, or usage of ambiguous language"（[Henry 2020](https://pmc.ncbi.nlm.nih.gov/articles/PMC7489085/)）——**需要跨句推理或语义推断的类型，一致性与 F1 天然塌陷**。
- 边界粒度对指标的影响同样显著：i2b2 2010 系统评测 exact 0.852 vs inexact 0.924（锚点），~0.07 的差距全部来自 span 边界（该对数字是系统 F1，用于说明边界是一等公民误差源，非人类 IAA）。
- 近期证据：韩国 ED 注记研究中"Test Result showed poor agreement"，归因于边界难度（[Jang 2025, JAMIA Open](https://academic.oup.com/jamiaopen/article/8/6/ooaf157/8343919)）——检查结果类是跨数据集的边界困难户。

### 1.4 属性层（断言/时间/主体）与实体层分离的论证

- **分离才能分别评测、分别设门禁**：THYME 把 Event span（0.8038）、DocTimeRel（0.7189）、modality（0.9547）分开报告 IAA；i2b2 2010 把断言单独算（最优 F 0.936，锚点）。若烧进实体类型，一个维度不稳就拖垮整个实体类。
- **反例的教训**：RadGraph 把确定性编入实体类型后，MIMIC-CXR 上 Obs-Uncertain 一致性 0.953，迁移到 CheXpert 语料只有 0.757（radiologist 对 radiologist，[RadGraph Table 4](https://arxiv.org/abs/2106.14463)）——"类型内嵌属性"在不同书写风格间比"属性层"更脆弱。
- **本项目属性层是产品核心，不是锦上添花**：下游 (a) 决策时点快照需要 assertion（这条文本事实是否成立）+ 时点（在决策时点之前是否已成立）；下游 (b) 泄漏防控需要时点（前/后）+ 主体（患者本人/他人）+ 否定/不确定。三个属性维度各自直接对应一个下游查询，应各自有独立类型学定义与独立 IAA 门禁。
- 建议取值【推断，均有先例】：assertion 6 值照抄 i2b2 2010（present/absent/possible/conditional/hypothetical/present-in-other）；时点 3 值照抄 THYME DocTimeRel（BEFORE/OVERLAP/AFTER，以"决策时点"替代"文档时间"，即 document-creation-time → decision-time 的直接平移）；主体 3 值（patient/other-person/family，i2b2 2010 的"他人"断言值扩展）。

### 1.5 类型系统设计操作流程（8 步）

1. **下游反推**：做两张"下游查询 → 必需信息"映射表。快照表：决策时点需要哪些事实类别（诊断/症状、检查与结果、用药与剂量、生命体征、操作、时间表达）；泄漏表：判定"前/后/是否成立/是否本人"各需要哪个属性。凡两表都不出现的类型不进 schema——这是防类型清单膨胀的第一道闸。
2. **UMLS 锚定**：每个候选类型注明对应的 UMLS semantic type/group（THYME 先例，1.2），命名避免自创词。
3. **数量控制在 8–12 个实体类型**【推断：参照 n2c2 9 类、Jang 6 类、i2b2 3 类】；超过即合并或降为属性值。
4. **每类写条款**：纳入条款（什么算）、排除条款（什么不算、归到哪类）、边界条款（最小充分文本/最长匹配）、缩写条款（缩写本身是 span，不展开）——模板见第 2 节。
5. **属性层独立设计**：断言/时点/主体三个维度分开定义取值空间（1.4），并规定"属性挂在实体上，不占 span"。
6. **关系最小化**：只设下游会用到的关系（如"药物–适应症""药物–ADE""检查–发现""发现–部位""时间包含"）；n2c2 的教训是 Drug–属性关系里 Reason/ADE 两类推理型关系贡献了绝大多数错误。每条关系类型在 guideline 里给"为什么需要它"的下游查询例。
7. **灰区预演**：正式定稿前，取 20–30 个覆盖 4 种文本类型（lab/micro comment、ED 主诉、放射报告、出院小结）的真实样本走查，凡出现"无法归类的 span"就修 schema 或补条款，直到走查零新增灰区。
8. **版本化与合并判据**：schema 版本号进每个标注文件；pilot 中某类型 IAA 连续两轮低于门禁、且合并后不损害下游用途 → 执行合并并保留映射表（i2b2 2012 的 7→3 是先例，两版映射发布）。

## 2. 标注规范文档应该包含什么

### 2.1 可核实的已发布 guideline 资源

| 资源 | 位置与可核实性 | 对本项目的用途 |
|---|---|---|
| i2b2 2010 concepts/assertions/relations 指南 | 官方托管在 [i2b2.org/NLP/Relations/assets/](https://www.i2b2.org/NLP/Relations/assets/Evaluation%20methods%20for%202010%20Challenge.pdf)（"Evaluation methods for 2010 Challenge"已核实存在；assertion/relation 的标注指南 PDF 同目录，本次目录页访问 500/搜索引见，未逐一核实）。挑战总览：[Uzuner et al. 2011, PMC3168320](https://pmc.ncbi.nlm.nih.gov/articles/PMC3168320/) | 三任务（概念/断言/关系）分层指南结构的模板；断言 6 值定义原文 |
| THYME 时间标注指南 | GitHub [stylerw/thymedata](https://github.com/stylerw/thymedata)（语料+指南），方法学论文 [Styler et al. 2014 TACL](https://pmc.ncbi.nlm.nih.gov/articles/PMC5657277/)（正文含指南设计论证） | "从 TimeML 裁剪到临床域"的指南改造方法；DocTimeRel 定义 |
| n2c2 2018 T2 指南 | 挑战官网 [n2c2.dbmi.hms.harvard.edu/2018-track-2](https://n2c2.dbmi.hms.harvard.edu/2018-track-2/)（本次访问 403，未直接核实下载；类型学与流程以 [Henry 2020 overview](https://pmc.ncbi.nlm.nih.gov/articles/PMC7489085/) 转述） | 药物域 9 类+8 关系的条款写法 |
| RadGraph 标注协议 | 论文附录+[arXiv 2106.14463](https://arxiv.org/abs/2106.14463) 正文协议描述；数据在 [PhysioNet/radgraph](https://physionet.org/content/radgraph/) | 放射报告专科协议（受控观察词表、Modify/Located At 关系规则） |
| 标注方法学一般文献 | Pustejovsky & Stubbs《Natural Language Annotation for Machine Learning》的 MATTER 循环（Model–Annotate–Train–Evaluate–Revise）；Artstein & Poesio 2008《Inter-Annotator Agreement in Computational Linguistics》 | 指南迭代流程与 IAA 方法学总纲 |

THYME 论文对"指南应回答什么"给出了直接可用的检查单：一个形式化标注规范必须明确 (a) 标注什么实体、(b) 如何结构化连接（链接层）、(c) 判据条款（guideline criteria）、(d) 术语与结构细节；并强调"**as much as possible, annotation decisions should be well-motivated by, and consistent with, the goal of the overall annotation task**"（[Styler 2014](https://pmc.ncbi.nlm.nih.gov/articles/PMC5657277/)）。i2b2 系的做法是每个任务一份独立指南（概念指南/断言指南/关系指南），与"分层评测"配套。

### 2.2 标注指南必备章节清单（13 章）与每章写作要点

1. **快速参考卡（1 页）**：类型表（类型名/一句定义/最常见触发词）、属性取值表、5 条最易错规则。写作要点：标注员日常只翻这一页，正例只在训练期读；每次指南改版必须同步改这张卡。
2. **任务定位与范围**：为什么标（快照证据+泄漏防控两个下游用途各一段）、标哪些文档类型、标注单位（文档/分块）。要点：把"下游会拿这个标注做什么查询"写成具体例句——THYME 明确要求标注决策服从任务目标。
3. **类型清单与逐类条款**（指南主体，每类一小节）：定义 / 纳入条款（什么算）/ 排除条款（什么不算、应归入哪类）/ 与易混类型的判别规则 / 正例 3 个 + 反例 3 个（反例须注明"正确做法是什么"）。要点：正反例 ≥1:1 配比，反例从 pilot 分歧里回收（见第 3 节分歧分类学）；每个反例锚定一条条款，禁止"孤儿反例"。
4. **span 边界规范**：最小充分文本原则（"chest X-ray" 整体、"X-ray" 单用也算？——条款化）；数值+单位+比较词的归属；标点/连字符/换行处理；缩写**不展开**（span 就是缩写本身，如 "SOB"、"CHF"），但 guideline 里维护缩写→类型映射表。要点：i2b2 2010 exact 0.852 vs inexact 0.924 的 ~0.07 差距全部来自边界（锚点），本项目用"exact 为主口径 + partial 为诊断口径"双轨，条款必须能回答"exact 为什么差"。
5. **嵌套与不连续实体政策**：是否允许嵌套 span（如"acute respiratory distress syndrome" 里嵌 "respiratory distress syndrome"）；不连续实体（"pre-diabetes and -insulin-dependent"）用重复标注还是 discontinuous span。要点：**默认不标嵌套、不标不连续**【推断：主流临床语料（i2b2/n2c2/THYME）均为平面 span，嵌套会显著增加 IAA 计算与裁决复杂度】；确需嵌套时在指南单列白名单。
6. **属性层规则**（断言/时点/主体三小节）：每维度的取值定义 + 线索词表（否定词、不确定词、假设标记、家庭史标记）+ 默认值规则（无线索时的默认取值）+ 线索作用范围（句内/从句内）。要点：断言取值抄 i2b2 2010 六值定义原文；时点取值抄 THYME DocTimeRel 三值并明确"决策时点"的定义（用 note 的 charttime 还是订单时间，写死一个）。
7. **关系层规则**：候选对生成范围（默认同句；跨句仅当共指/列表结构明确）、关系端点必须是已标实体、方向定义、"何时显式标否定关系"（本项目不标，只标存在的）。要点：关系 IAA 天然低（THYME 0.4506–0.5630、i2b2 2012 span 0.39），指南里要把候选对收窄规则写成可执行的硬规则，别留给标注员判断。
8. **"不标注"的三态语义**（本项目特有，泄漏工具的核心）：(i) **显式否定提及**——标实体 + assertion=absent（如"no evidence of pneumonia"里的 pneumonia 要标）；(ii) **未提及**——不产生任何标注；(iii) **不适用/模板噪声**——结构化模板、自动生成的 boilerplate（如放射报告正常模板），规定跳过或标 N/A。要点：三态区分决定泄漏工具对"报告说没有"和"根本没说"的判定，指南必须各给 2 个例句。
9. **分文档类型条款**：放射报告（分节解析、Impression 优先级）、ED 主诉（短语碎片、无完整句法）、lab/micro comment（电报体、缩写密集）、出院小结（长文、时序复杂）。详见第 4 节。
10. **分块接缝政策**：本项目流水线先分块后抽取，标注以"原始文档坐标"为准；接缝处实体/关系处理规则（详见 4.3）。
11. **工具与数据格式**：标注工具（如 doccano/LightTag/brat）、输出 JSON schema（与 `unreviewed_model_output` 同构以便对齐评估）、字符偏移编码（UTF-8 offset 规则）。
12. **质量控制流程摘要**：双人独立、IAA 报告口径（第 3 节）、裁决 SOP、何时停线修指南。要点：这一章是给"未来的裁决者与审计者"看的，不是给标注员的。
13. **FAQ 与案例库 + 版本变更记录**：每个 pilot 轮次结束把新裁决结果沉淀进 FAQ；指南带语义版本号，每次变更记录"改了什么、为什么、对已标注数据是否追溯重标"。要点：i2b2 2012 的 7→3 合并之所以能执行，是因为两版语料都保留并给出映射——变更记录里必须包含新旧类型映射表。

## 3. 双标-裁决-迭代循环怎么跑

### 3.1 IAA 计算的具体口径

**先例口径**。THYME 的做法最完整（[Styler 2014, §5](https://pmc.ncbi.nlm.nih.gov/articles/PMC5657277/)）：每份双标文档 IAA **同时**报 F1 与 Krippendorff's Alpha（"with closure"——把链接的传递闭包纳入比对）；实体层用 exact span（Timex3 因过短改用 overlapping span 比对）；**属性层只在两人重叠实体集合上算**（先解决"标没标对上"，再看"值给没给对"）。i2b2 系报 token-level 与 entity-level 双轨（去身份语料：entity micro F1 0.895 / token 0.930，[Stubbs & Uzuner 2015, PMC4978170](https://pmc.ncbi.nlm.nih.gov/articles/PMC4978170/)）。当不存在 gold standard 时，把一方当 reference 算另一方的 P/R/F1 在方法学上是成立的（[Hripcsak & Rothschild 2005](https://pubmed.ncbi.nlm.nih.gov/15802422/)）。

**本项目口径建议**：

- **实体层（主口径）**：A→B 与 B→A 各算一次 exact-span P/R/F1，报对称平均 F1 = (F(A→B)+F(B→A))/2；THYME 同款加报 Krippendorff α。**辅助口径**：token-level F1（与 i2b2 系可比）；partial/overlap span F1 仅做诊断（区分"没看见"vs"边界差一截"）。
- **属性层（断言/时点/主体）**：在重叠实体集合上逐属性算 Cohen's κ（双人）或 Krippendorff α（多人）；判读锚点：α≥0.8 可靠、≥0.667 暂定可用（Krippendorff，锚点）。注意 κ 的流行率偏倚：断言里"present"占绝对多数时 κ 会被低估，需补报按取值的 positive agreement（Hripcsak 2005 的标准提醒）。
- **关系层（两级）**：L1 = 端点对齐前提下的关系类型 κ（把 gold 实体对给两人，只看类型判断）；L2 = 端点识别+类型全对的 span-level F1。THYME 的"participants only 0.5012 vs participants+type 0.4506"两行就是 L1/L2 的原型；i2b2 2012 报的 TLINK span 0.39 是 L2 口径（[Sun 2013](https://pmc.ncbi.nlm.nih.gov/articles/PMC3756273/)）。两级差值 = "端点找错"贡献的损失。
- **exact vs inexact 双口径**：所有实体指标同时报 exact 与 partial（i2b2 2010 系统评测 0.852 vs 0.924 的差距证明边界是一等公民误差源，锚点）。

### 3.2 Pilot 的规模与退出条件

先例：THYME 用 107 份 / 35 患者的开发集做完整个双标-裁决循环后才冻结指南（[Styler 2014](https://pmc.ncbi.nlm.nih.gov/articles/PMC5657277/)）；Jang 2025 用 **3 轮、每轮约 20 份** 的轻量循环，每轮后修指南并复算 pairwise span-F1 + relaxed α（[JAMIA Open 2025](https://academic.oup.com/jamiaopen/article/8/6/ooaf157/8343919)）；i2b2 2012 在训练集部分文档上双标后触发 7→3 合并。

**建议流程**【规模为推断，阈值锚点校准】：每轮 20–30 份，按 4 种文档类型分层抽样（每类 5–8 份），双标→算 IAA→裁决→归因→修指南→下一轮。**退出条件（全部满足）**：
1. 指南变更数连续一轮为 0（或仅措辞级、无判据变化）；
2. 实体 exact F1（对称平均）≥0.85 且连续两轮不下降；属性 α：断言 ≥0.75、时点 ≥0.70、主体 ≥0.70；关系 L1 κ ≥0.60【推断——锚点校准：这些值取在 THYME 人类 IAA（Event 0.8038 / DocTimeRel 0.7189 / TLINK 0.4506–0.5630）的邻近区间，门禁不得高于领域人类水平】；
3. 分歧归因里"指南缺陷"类占比 <10% 且连续两轮下降；
4. 每类实体在 pilot 累计出现 ≥30 个实例（稀有类不达标则补抽样该类富集文档）。

### 3.3 裁决 SOP

- **第三人资质**：未参与该批双标的资深标注者/指南共同作者，临床文本经验 ≥ A/B；THYME 的裁决者明确为领域专家、n2c2 2018 T2 为"2 independent annotators + third resolved conflicts"（锚点），Stubbs 去身份语料的终审是"资深研究员 + MD 通读"（[PMC4978170](https://pmc.ncbi.nlm.nih.gov/articles/PMC4978170/)）。
- **裁决界面要求**：两版标注以 diff/overlay 同屏并列（span 高亮按标注者着色）；分歧项按类型分组排序（先边界后类型后属性后关系）；每个分歧一键记录"接受 A / 接受 B / 重标 / 升级为指南问题"；显示上下文窗口可扩到全文（时点/主体判定常需看 section header）。
- **分歧原因分类学（4 类，每条裁决打一个标签）**：
  1. span 边界（类型一致、边界不一致）→ 修边界条款；
  2. 类型混淆（两类判据不清）→ 修判别规则；
  3. 遗漏 vs 多标（一方漏/多）→ 检查是否线索词表缺项；
  4. 指南缺陷（无法用现有条款裁决）→ 进 FAQ 与指南修订队列。
- **裁决后的全局一致性复查**：i2b2 2011 有两轮裁决先例（锚点）；Stubbs 的操作化先例：脚本自动找"同一实体在别处标过、此处漏标"的模式，迭代"直到不再发现漏标"，最后独立终审通读（[PMC4978170](https://pmc.ncbi.nlm.nih.gov/articles/PMC4978170/)）。本项目对应物：裁决后跑一致性 linter——(a) 文档内同字符串不同类型；(b) 同实体不同属性值；(c) 关系方向冲突（A–B 与 B–A 同型共存）；(d) 违反候选对硬规则的关系。linter 零告警才冻结该批 gold。

### 3.4 LLM 预标注的正确用法（隔离原则与实证）

**隔离原则**：A/B 两名标注员一律从空白文档开始，`unreviewed_model_output` 不进入标注界面。证据：(a) South et al. 的预标注实验未提高 IAA（锚点；Stubbs 2015 引 South 2014 同结论，本次核实）；(b) [Wang et al. CHI 2024](https://dl.acm.org/doi/fullHtml/10.1145/3613904.3641960) 的受控实验：**错误的 LLM 标签会显著降低人类标注准确率**，且给 LLM 解释反而增加认知负荷与用时（13.20s vs 12.06s/条）——预标注会把模型错误传染进 gold。模型输出的合法用途只有三个：裁决阶段的"第三票"参考（加速，不影响独立性——裁决本身就是在破坏独立性之后的信息增补步骤）、逐类型分歧率→人工成本估算、以及第 6 节阶段 4 的对齐评估输入。

**2024–2026 实证研究对照表**（检索到的对标注速度/一致性有数字的研究）：

| 研究 | 设置 | 关键数字 | 对本项目的含义 |
|---|---|---|---|
| Fort, Adda & Cohen（经典非 LLM 基线，[PubMed 24001514](https://pubmed.ncbi.nlm.nih.gov/24001514/)） | 临床试验公告、字典预标注、对照实验 | 每一对实验中预标注组都更快；IAA 93.4–95.5%，未引入显著偏置 | 速度收益是真的；但这是"高准确率字典"场景 |
| [Wang et al. CHI 2024](https://dl.acm.org/doi/fullHtml/10.1145/3613904.3641960) | LLM 标签+验证器选低置信子集重标（SNLI/SemEval 等） | 重标 15% 可提升整体准确率至少 10%；错误 LLM 标签降低人类准确率；解释增加用时（13.20s vs 12.06s） | 验证式（verify-then-fix）优于全量预标注；LLM 标签必须带不确定性分层 |
| Chen et al. 2025（[PMC12481989](https://pmc.ncbi.nlm.nih.gov/articles/PMC12481989/)） | GPT-3.5 预标注 + 人工只复核 LLM 阳性（系统综述筛查，非 NER） | 工作量降约 80%（274/1800 需人工）；人机协同 F1 0.9583 vs LLM 单独 0.6053；双人 κ 类指标 α=0.65、"percentage of agreement 96.50%" | "只验证阳性"模式在高召回预标注下可行；但阴性未复核——对 gold 质量要求高的本案不可直接用 |
| SDoH-GPT（GPT-4 独立标注，[JAMIA 2026;33(1):67](https://academic.oup.com/jamia/article/33/1/67/8159915)） | GPT-4 few-shot 直接标注 EHR 社会决定因素，与人比对 | 与人类标注 Cohen's κ 最高 0.92；宣称时间/成本降 10 倍/20 倍 | LLM-as-annotator 上限可以很高，但**任务特异性极强**：Hu 2024 在另一临床 NER 上 GPT-4 exact F1 仅 0.593（锚点）——不可把单篇高κ外推为本案 GPT-4 可当标注员 |

综合：LLM 在标注循环中的定位是**加速裁决与估算成本**，不是提高 IAA（South 锚点）也不是替代双标（任务间性能方差过大：0.593 vs κ0.92）。

## 4. 分文档类型与分块的标注策略

### 4.1 是否应分型设计标注规范与 IAA 门禁：证据说"是"

- **放射报告：专科协议 + 受控词表 → 高一致性，但跨模板脆弱**。RadGraph 两位放射科医生在 MIMIC-CXR 上实体 micro F1 0.988 / 关系 0.947；同一对医生在 CheXpert 语料上掉到 0.928 / 0.745（[RadGraph Tables 4–5](https://arxiv.org/abs/2106.14463)）——放射报告内部高度模板化、一致性极高，但**换一套模板（机构/短语风格）就显著掉**。启示：放射类可以设更高门禁，但抽取器/规范过拟合 MIMIC-CXR 风格的风险要写进局限。
- **出院小结：推理型关系是主要塌陷点**。n2c2 2018 T2（出院小结）概念层 0.9418，但端到端 ADE–Drug 0.4755、Reason–Drug 0.5961（[Henry 2020](https://pmc.ncbi.nlm.nih.gov/articles/PMC7489085/)）；i2b2 2012（出院小结）TLINK span IAA 0.39（[Sun 2013](https://pmc.ncbi.nlm.nih.gov/articles/PMC3756273/)）。长文的时序与共指使**关系层**（尤其跨句、需推理的关系）一致性天然低——分型门禁主要差异应出现在关系层和时点属性层。
- **ED 主诉/现病史：短语碎片、边界是主要矛盾**。Jang 2025（韩国 ED notes）选择**短语级+属性**的标注单元而非词级，多数类 IAA 0.6–0.8 或以上，"Test Result"类因边界困难一致性差（[JAMIA Open 2025](https://academic.oup.com/jamiaopen/article/8/6/ooaf157/8343919)）。ED 主诉（一两句话的碎片文本）没有完整句法，候选对/属性线索常不在"句内"——句子级硬规则在这里失效，需降为"分号/逗号/换行段"级。
- **lab/micro comments：未找到专门的双标语料或 IAA 报告**（检索未命中电报体检验评论的标注研究）。仅知此类文本极度缩写密集、无句法。按【推断】处理：参照 ED 主诉的分段级规则 + 强制缩写映射表，IAA 门禁先按 ED 档设、pilot 后校准。
- **门禁分型建议**【推断，锚点校准】：实体层 exact F1 门禁分两档——放射报告 ≥0.90、其余 ≥0.85（RadGraph 人人 0.988 vs THYME 人人 0.8038 的中间取值）；关系层与属性层全员同档（难度由类型学而非文档类型主导，4.1 第二点证据）。

### 4.2 长文档与结构化分节的标注单元

- THYME 的先例：语料标注带 **SECTIONTIME**（章节时间）与 DOCTIME，实体的 DocTimeRel 判定依赖章节头部信息（[stylerw/thymedata](https://github.com/stylerw/thymedata)、[Styler 2014](https://pmc.ncbi.nlm.nih.gov/articles/PMC5657277/)）。启示：出院小结/放射报告按**自然章节切分标注批次**，标注界面必须把章节头（如 "Hospital Course:"、"IMPRESSION:"）与正文一起呈现，否则时点/主体属性无从判。
- 本项目文档类型天然分两档处理：**长文**（出院小结、放射报告）按章节为标注单元、按文档为裁决单元；**短碎片**（ED 主诉、lab comment）整条为一个单元，直接以文档为单位双标。

### 4.3 分块（chunking）对接缝处实体/关系的处理规范

**证据状态：未找到**直接研究"分块边界对人工 span 标注/IAA 影响"的文献。模型侧有间接证据：chunk 边界会切断上下文依赖（late chunking，[arXiv 2409.04701](https://arxiv.org/html/2409.04701v3)），边界噪声可由边界平滑缓解（[Boundary Smoothing, ACL 2022](https://aclanthology.org/2022.acl-long.490.pdf)）——但都不能外推到人工标注场景。以下为保守操作建议【推断】：

1. **标注永远在原文档坐标系进行**：标注员看到的与标注的是整篇文档（或整章节），不是 chunk；`unreviewed_model_output` 的 chunk 内偏移由流水线回填到文档坐标后参与对齐评估（本项目已实现确定性回填，正好复用）。
2. **chunk 生成端加两条硬约束**：(a) 相邻 chunk 重叠 ≥ 最长常见实体长度+一个线索窗口【推断：建议 64–128 token】；(b) chunk 边界只落在句末/分号/换行，不落在实体内部。
3. **接缝关系规则**：跨 chunk 的关系在裁决阶段于文档级视图统一处理（双标在文档级做，天然覆盖跨 chunk 关系）；模型输出在 chunk 内自限定的关系，跨 chunk 合并只允许"同实体对同型关系去重"，不允许裁决者发明 chunk 间新关系——防止把流水线 artifact 带进 gold。
4. **接缝 linter**：同一表面字符串在相邻 chunk 重复出现时类型/属性必须一致（并入 3.3 的全局一致性 linter）。
5. **量化接缝损失**：阶段 4 对齐评估时单独报"距 chunk 边界 ≤k token 的实体"召回差，作为分块参数调优依据【推断】。

## 5. 关键图表深析

> 转录说明：以下数字均为本次从原文（PMC / ar5iv 全文）转录，转录工具为页面级抓取；分概念类的精确值凡原文置于图中（非表格）的，一律注明"未转录"并只给正文文字口径，避免数字失真。

### 表 5-A：THYME 2014 (TACL) 分层 IAA 表（核心：哪层任务一致性天然低）

来源：[Styler et al. 2014, Tables 3–4](https://pmc.ncbi.nlm.nih.gov/articles/PMC5657277/)。背景：107 份临床记录 / 35 名患者（THYME 结肠/直肠癌开发集），每份双标+第三人（领域专家）裁决；语料量级 Table 1：EVENT 15,769 / TIMEX3 1,426 / TLINK 7,935。IAA 口径：F1 + Krippendorff α（含闭包）。

**Table 3（任务层 IAA）**

| 任务层 | F1 | Alpha |
|---|---|---|
| Event | 0.8038 | 0.7899 |
| Timex3 | 0.8047 | 0.6705 |
| LINK（仅端点，participants only） | 0.5012 | 0.4999 |
| LINK（端点+类型） | 0.4506 | 0.4503 |
| LINK（仅 CONTAINS 类） | 0.5630 | 0.5626 |

**Table 4（Event 属性 IAA，重叠实体集合上）**

| Event 属性 | F1 | Alpha |
|---|---|---|
| DocTimeRel | 0.7189 | 0.6889 |
| Contextual Aspect | 0.9947 | 0.9930 |
| Contextual Modality | 0.9547 | 0.9420 |

分析：
1. **语义深度-一致性梯度**：实体 0.8038 → 简单时间属性 0.7189 → 自由时序关系 0.4506–0.5630。每往语义深一层掉 0.08–0.26。质量门禁必须分层设，单一总门禁会在关系层把项目卡死、在实体层形同虚设。
2. **DocTimeRel（0.7189）比任意成对 TLINK（≤0.5630）高约 0.16**："相对文档时间的三值判断"远比"两事件间关系"可判。本项目"时点前后"属性应直接采用 DocTimeRel 式设计（相对决策时点 BEFORE/OVERLAP/AFTER），**不要**引入成对时序关系层。
3. **有触发词的属性接近天花板**（aspect 0.9947、modality 0.9547）：线索词可枚举的属性（假设/提议类语言标记）几乎不产生分歧 → 断言层的否定/不确定线索词表一旦写全，门禁可设 0.9 档。
4. **Timex3 的 F1（0.8047）与 α（0.6705）差 0.13**：小类别流行率使 κ/α 被低估 → 属性层必须 α 与 per-value agreement 双报（3.1）。
5. THYME 自己的对比：Event 0.8038 低于 i2b2 的 0.87（partial-match 口径）——**IAA 数字跨研究不可直接比**，本项目门禁文件里必须写死口径（exact、对称平均、α 版本）。
6. 对本项目门禁校准：双标预期区间 = 实体 ~0.80±0.05、时点属性 ~0.70、成对关系 0.45–0.60；门禁设在预期区间下沿，而不是 0.9 一刀切。

### 表 5-B：i2b2 2012 overview 的 span IAA 与 TLINK 合并（核心：粒度超出人类一致的官方响应）

来源：[Sun et al. 2013 JAMIA, Table 1](https://pmc.ncbi.nlm.nih.gov/articles/PMC3756273/)。语料：310 份出院小结（约 178,000 tokens）。转录注：该表给出 EVENT/TIMEX3 的 exact 与 partial 两列、TLINK 仅一列（论文叙述含合并前后，表中数值按抓取转录如下）。

| 对象 | Exact span | Partial span |
|---|---|---|
| EVENT | 0.83 | 0.87 |
| TIMEX3 | 0.73 | 0.89 |
| TLINK | 0.39 | – |

TLINK 合并：7 类 → 3 类：BEFORE（并 BEFORE、ENDED_BY、BEFORE_OVERLAP）、AFTER（并 BEGUN_BY、AFTER）、OVERLAP（并 SIMULTANEOUS、OVERLAP、DURING）；合并前后两版语料均发布。合并后最优系统 F1：0.6932（Vanderbilt）。

分析：
1. **同一批标注员，端点 0.83、关系 0.39**：关系层损失主要在"类型语义"而非"端点识别"→ 本项目裁决资源与指南篇幅应集中在关系类型判据，端点交给边界条款。
2. **TIMEX3 exact 0.73 vs partial 0.89（差 0.16）**：时间表达的边界是全任务最难 → 本项目时间表达实体需要最长的边界条款与最多的正反例。
3. **0.39 是"合并触发器"**：低于 ~0.4 的类型学应判定为超出人类一致判能力，执行合并或砍掉（官方先例）。
4. **合并=分层发布而非回滚**：两版+映射表都保留 → 本项目 schema 版本化照此办理（1.5 第 8 步）。
5. 合并后最优系统也只有 0.6932：**时间关系的可学习上限 ~0.7**。下游若需高可靠时序，用 DocTimeRel 式属性（人类 0.7189）而非成对关系——与表 5-A 第 2 条互证。
6. 语料规模参照：310/505/107 份级别的双标语料支撑了历届共享任务——本项目 300 例的 gold 规模在领域惯例区间内，但 64,509 文本单元意味着必须定义抽样扩展路径（第 6 节）。

### 表 5-C：n2c2 2018 T2 overview 分任务最优 F1（核心：推理型类型为何难、对类型清单的启示）

来源：[Henry, Buchbinder & Uzuner 2020, JAMIA Open](https://pmc.ncbi.nlm.nih.gov/articles/PMC7489085/)（Europe PMC 镜像核实）。505 份出院小结（303 train / 202 test）。转录注：分概念精确最优值在原文 Figure 1（图，未转录）；下表数字为正文文字与汇总表口径。

| 任务 | 最优 F1 | 备注 |
|---|---|---|
| 概念抽取（9 类微平均） | **0.9418** | 最优队 Alibaba/Ali |
| 关系分类（端点给定） | **0.9630** | UTH（P/R/F 三项均第一） |
| 端到端（实体+关系） | **0.8905** | UTH |
| 端到端 ADE–Drug | **0.4755** | 全部关系类型中最差 |
| 端到端 Reason–Drug | **0.5961** | 次差 |
| 端到端 Duration–Drug | 0.7861 | |
| 其余关系类型 | 端到端 >0.86 | 除 Dosage–Drug、Reason–Drug、ADE–Drug 外，关系分类口径最高 F1 >0.94 |
| 概念分类型 | 见 Figure 1（未转录） | 正文：Drugs/Strength/Form/Dosage/Frequency/Route 最优 F1 均 >0.89；**Duration、Reason、ADE 三类最差** |

原文归因（直引）："These were often missed because **local context is insufficient** to identify them"；错误 "most often caused by the **need for inference, or usage of ambiguous language**"。

分析：
1. **关系分类 0.9630 vs 端到端 0.8905（差 ~0.07）**：端点识别独立贡献 0.07 的损失 → 本项目对齐评估与门禁都要分"给定实体的关系准确率"与"端到端"两个口径（与 3.1 的 L1/L2 分层同构）。
2. **推理型关系端到端不到 0.6**（ADE–Drug 0.4755、Reason–Drug 0.5961）：本项目的"药物–适应症/–不良事件"同类关系预期为最弱环节，裁决与案例库优先覆盖。
3. **形态学信号决定概念难度**：>0.89 的六类（Drug/Strength/Form/Dosage/Frequency/Route）都有词典化形态；最差三类（Reason/ADE/Duration）没有固定形态、依赖语境推理。**类型清单设计时给每类做"形态学信号评估"**——无形态信号的类型要么设计触发模式，要么接受低门禁。
4. **隐含语义是 IAA/F1 双杀**：原文"local context is insufficient"意味着句子级规则救不了 Reason/ADE——指南应规定跨句推理的显式证据链（如"适应症=给药目的从上下文可陈述"），否则双标一致性同塌。
5. 本项目快照的"事实成立性"属性多为推理型（n2c2 的 Reason 同类）→ 属性层门禁预期低于实体层，0.7 档而非 0.85 档（与表 5-A 校准一致）。
6. 引用纪律：分概念精确值在 Figure 1，转述时用">0.89 / 最差三类"文字口径，防止把图表数字口耳相传搞错。

### 表 5-D：RadGraph 人类双标 F1 与模型 F1 对照（核心：放射专科天花板与模型-人类差距）

来源：[Jain et al., RadGraph, Tables 3–5](https://arxiv.org/abs/2106.14463)。设置：dev 500 份 MIMIC-CXR（14,579 实体 + 10,889 关系，即 ~29 实体/份）；test 100 份（50 MIMIC-CXR + 50 CheXpert）每份两位放射科医生独立标注（平均每位 2,766 实体 + 2,009 关系），一位为 gold、另一位作对照。

**人类 vs 人类（test，F1）**

| 指标 | MIMIC-CXR | CheXpert |
|---|---|---|
| Anatomy | 0.994 | 0.944 |
| Obs: Definitely Present | 0.981 | 0.917 |
| Obs: Uncertain | 0.953 | 0.757 |
| Obs: Definitely Absent | 0.996 | 0.960 |
| 实体 micro / macro | **0.988 / 0.981** | 0.928 / 0.894 |
| Modify | 0.952 | 0.741 |
| Located At | 0.949 | 0.779 |
| Suggestive Of | 0.830 | 0.592 |
| 关系 micro / macro | **0.947 / 0.910** | 0.745 / 0.704 |

**模型（DyGIE++ PubMedBERT，"RadGraph Benchmark"）**

| 指标 | MIMIC-CXR | CheXpert |
|---|---|---|
| 实体 micro F1 | 0.94 | 0.91 |
| Anatomy | 0.968 | 0.941 |
| Obs: Definitely Present | 0.922 | 0.884 |
| Obs: Uncertain | 0.700 | 0.714 |
| Obs: Definitely Absent | 0.952 | 0.910 |
| 关系 micro F1 | 0.82 | 0.73 |
| Modify | 0.804 | 0.709 |
| Located At | 0.861 | 0.779 |
| Suggestive Of | 0.685 | 0.588 |

分析：
1. **放射报告的实体一致性天花板 ~0.99、关系 ~0.95**（模板化文本）→ 本项目放射类文档实体门禁可设 0.90 档（4.1），显著高于出院小结档。
2. **Obs: Uncertain 在 MIMIC 0.953、换 CheXpert 语料掉到 0.757（-0.196）**：不确定表达的判读对短语风格最敏感 → 本项目"不确定"属性值必须按文档类型分别给线索词表（放射的"cannot exclude" vs 出院小结的"likely/possible"）。
3. **结构型关系（Modify/Located At ~0.95）vs 推理型关系（Suggestive Of 0.830/0.592）**：与 n2c2 的 ADE/Reason、THYME 的自由 TLINK 同构——**推理型关系一致性跨语料地低 ~0.1–0.2**，这是三个语料交叉验证出的最稳规律。
4. **模型-人类差距分层**：实体 0.94 vs 0.988（-0.05）、关系 0.82 vs 0.947（-0.13）→ 关系层的模型-人类差距约是实体层 2.6 倍。本项目 `unreviewed_model_output`（12,596 实体/919 关系）对齐评估预期：实体对齐好于关系对齐，评测设计要分开解读。
5. **模型最难处与人类同构**：模型 Obs: Uncertain 0.700 为实体最差值，与人类的 Uncertain 掉分点一致 → 阶段 4 对齐评估必须按属性值分层报（"模型在哪个属性值上系统性偏弱"直接指导 prompt/类型学修订）。
6. **跨语料漂移 ~0.09**（模型关系 MIMIC 0.82 vs CheXpert 0.73）：同一模型换书写风格就掉 → 本项目跨 4 种文档类型的对齐评估天然要分层，这与分型门禁（4.1）互为印证。
7. 人类标注产能参照：平均 ~29 实体/份（dev 14,579/500）——本项目 300 例产出 12,596 实体（~42/份）密度更高（多文档类型混合），人工双标的每份耗时预估应按此密度外推【推断】。

### 表 5-E：LLM 预标注/协同标注研究对照表

见 3.4 的四研究对照表（Fort/Cohen 经典基线、[Wang CHI 2024](https://dl.acm.org/doi/fullHtml/10.1145/3613904.3641960)、[Chen 2025](https://pmc.ncbi.nlm.nih.gov/articles/PMC12481989/)、[SDoH-GPT](https://academic.oup.com/jamia/article/33/1/67/8159915)）。深读要点：
1. 速度收益方向一致（预标注组每对实验更快；工作量 -80%；时间/成本 10x/20x），**但没有任何一篇证明预标注提高 IAA**（South 锚点 + Wang 的错误传染证据）→ 隔离原则不可动摇。
2. 质量证据分层：verify 模式（人工复核 LLM 阳性）能把 F1 从 0.6053 拉回 0.9583，但**阴性未复核**是结构性缺口——gold 生产不可用，裁决加速可用。
3. LLM-as-annotator 的任务间方差极大（exact F1 0.593 vs κ 0.92）：**任何"用模型替代标注员"的提议都必须先在本地 50–100 例上做锚定验证**【推断】。

## 6. 汇总：项目 NER/RE 开展的分阶段执行方案

> 阈值凡未标注出处者均为【推断】的项目建议值，已按第 5 节领域人类 IAA 区间校准；标注锚点者为已核实文献值。

### 阶段 0：类型系统与指南 v0（预计 1–2 周【推断】）
- **输入**：下游需求两张映射表（快照证据→事实类别；泄漏防控→前/后/成立/本人属性）；UMLS semantic groups 清单；4 种文档类型各 20–30 例真实样本；`unreviewed_model_output` 的类型×文档类型分布统计（仅作参考信号，不作 schema 依据）。
- **操作**：执行 1.5 节 8 步（下游反推→UMLS 锚定→8–12 类→逐类条款→属性层独立→关系最小化→灰区走查→版本化）；指南按 2.2 十三章写 v0；标注工具与输出 JSON schema 定稿（与 `unreviewed_model_output` 同构）；IAA 脚本三件套（对称 exact/partial F1、属性 κ/α+per-value agreement、关系 L1/L2）先行写好并用合成数据自测。
- **产出**：schema v0.x、guideline v0.x（含快速参考卡）、IAA 脚本、缩写映射表 v0。
- **量化退出条件**：灰区走查零新增灰区；每类正例≥3 且反例≥3 且反例各锚定一条条款；走查样本中出现的全部缩写进入映射表。

### 阶段 1：pilot 双标循环（预计 3–5 轮【推断】）
- **输入**：guideline v0；按文档类型分层的抽样框；标注员 A/B（空白文档起步）+裁决者 C。
- **操作**：每轮 20–30 份双标（4 类文档各 5–8 份）→IAA 全口径计算→裁决（每条分歧打 4 类归因标签：边界/类型/遗漏/指南缺陷）→修指南与 FAQ→下一轮。`unreviewed_model_output` 全程不进标注界面。
- **产出**：逐轮 IAA 趋势表、分歧归因统计、guideline v1、FAQ 库 v1、裁决 SOP 实操版。
- **量化退出条件**（3.2 节，全部满足）：(1) 指南变更数连续一轮为 0；(2) 实体 exact F1（对称平均）放射 ≥0.90、其余 ≥0.85 且两轮不降；(3) 断言 α≥0.75、时点 α≥0.70、主体 α≥0.70；(4) 关系 L1 κ≥0.60；(5) "指南缺陷"归因占比 <10% 且连续两轮下降；(6) 每实体类累计 ≥30 实例。

### 阶段 2：正式双标 + 裁决（gold 生产）
- **输入**：guideline v1、冻结 schema v1、按 pilot 校准的抽样计划（4 类文档配额+难类富集）、裁决界面（span diff 并列+模型第三票开关）。
- **操作**：批量双标；批次裁决（模型票仅加速，不约束裁决者）；每批跑全局一致性 linter（文档内同串不同类型/同实体不同属性/关系方向冲突/跨 chunk 重复不一致）；每 100 份插入 1 份 pilot 已裁决"锚文档"监控标注漂移【推断】。
- **产出**：adjudicated gold（首批建议 300–500 例，与现有 300 例模型输出对齐评估配套【推断】）、完整裁决日志。
- **量化退出条件**：每批 IAA 达阶段 3 门禁；linter 零告警；锚文档上的裁决符合率 ≥0.95【推断】。

### 阶段 3：IAA 门禁与解锁
- **输入**：正式批全量 IAA 报告（按 3.1 口径）。
- **操作**：分型分层判定门禁；未达标类型走小循环（补充条款+局部重标 50 例复检）或执行合并（i2b2 2012 的 7→3 先例，保留映射）；冻结 gold、打版本号、发布说明与局限声明。
- **量化门禁（解锁条件）**：实体 exact F1 放射 ≥0.90、其余 ≥0.85；token F1 ≥0.90（辅助）；断言 α≥0.75、时点 α≥0.70、主体 α≥0.70；关系 L1 κ≥0.60、L2 F1≥0.50；判读总纲 α≥0.8 可靠 / ≥0.667 暂定可用（Krippendorff，锚点）——**低于 0.667 的层降级为"辅助层"**，在评测使用说明中强制标注不可单独作为结论依据。
- **产出**：unlocked gold（v1.0）+ 门禁报告 + 使用限制清单。

### 阶段 4：与模型输出的对齐评估（评测解锁后的第一个消费方）
- **输入**：frozen gold、`unreviewed_model_output`（同构 schema、chunk 元数据、模型/参数信息）。
- **操作**：双口径（exact/partial）× 双任务（实体/属性/关系、端到端 vs 给定实体的关系分类）× 分层（实体类型/属性值/文档类型/距 chunk 边界 ≤k token）；错误分类学复用裁决 4 类归因；对照 RadGraph 的模型-人类差距先例（实体 -0.05 vs 关系 -0.13）解读结果。
- **产出**：模型对齐报告（可用类型清单、系统性弱点、prompt/schema 修订建议）、下一轮标注扩展的抽样优先级（64,509 单元中的增量方向）。
- **量化退出条件**：报告完成且明确"可用于评测解锁的实体/属性/关系白名单"；对齐 F1 低于门禁 0.10 以上的类型进入下一轮迭代或从评测声明中排除【推断】。

## 参考资料清单

**已核实全文（本次抓取转录）**
- THYME：Styler IV et al. *Temporal Annotation in the Clinical Domain*, TACL 2014 — [PMC5657277](https://pmc.ncbi.nlm.nih.gov/articles/PMC5657277/) / [ACL Q14-1012](https://aclanthology.org/Q14-1012/)；语料与指南 [github.com/stylerw/thymedata](https://github.com/stylerw/thymedata)
- i2b2 2012：Sun et al. *Evaluating temporal relations in clinical text: 2012 i2b2 Challenge*, JAMIA 2013 — [PMC3756273](https://pmc.ncbi.nlm.nih.gov/articles/PMC3756273/)
- n2c2 2018 T2：Henry, Buchbinder & Uzuner, JAMIA Open 2020 — [PMC7489085](https://pmc.ncbi.nlm.nih.gov/articles/PMC7489085/)（[Europe PMC 镜像](https://europepmc.org/article/MED/33603239)）
- RadGraph：Jain et al. — [arXiv 2106.14463](https://arxiv.org/abs/2106.14463) / [PhysioNet](https://physionet.org/content/radgraph/)
- Stubbs & Uzuner 2015（2014 i2b2/UTHealth 去身份语料，注意：PMC4978170 是去身份语料论文）— [PMC4978170](https://pmc.ncbi.nlm.nih.gov/articles/PMC4978170/)
- i2b2/VA 2010 总览：Uzuner et al. 2011 — [PMC3168320](https://pmc.ncbi.nlm.nih.gov/articles/PMC3168320/)；2010 挑战材料目录 [i2b2.org/NLP/Relations/assets](https://www.i2b2.org/NLP/Relations/assets/Evaluation%20methods%20for%202010%20Challenge.pdf)
- Wang et al. *Human-LLM Collaborative Annotation Through Effective Verification of LLM Labels*, CHI 2024 — [ACM DL](https://dl.acm.org/doi/fullHtml/10.1145/3613904.3641960)
- Chen et al. 2025 human-LLM 协同标注 — [PMC12481989](https://pmc.ncbi.nlm.nih.gov/articles/PMC12481989/)
- SDoH-GPT, JAMIA 2026;33(1):67–78 — [OUP](https://academic.oup.com/jamia/article/33/1/67/8159915)（摘要口径）
- Jang et al. *Span-based annotation framework for LLM-based clinical NER（韩国 ED notes）*, JAMIA Open 2025 — [OUP](https://academic.oup.com/jamiaopen/article/8/6/ooaf157/8343919)
- Fort, Adda & Cohen 预标注速度/偏置经典实验 — [PubMed 24001514](https://pubmed.ncbi.nlm.nih.gov/24001514/)
- Hripcsak & Rothschild 2005，F-measure 作为一致性 — [PubMed 15802422](https://pubmed.ncbi.nlm.nih.gov/15802422/)
- Late chunking — [arXiv 2409.04701](https://arxiv.org/html/2409.04701v3)；Boundary Smoothing — [ACL 2022](https://aclanthology.org/2022.acl-long.490.pdf)

**锚点数字来源（项目内方法学笔记，已核实，本文直接引用）**
- n2c2 2018 T2 "2 independent annotators + third resolved conflicts"、505=303/202；THYME event 0.8038/TLINK 0.4506–0.5630；Stubbs & Uzuner 2015 entity/token 0.895/0.930；i2b2 2010 exact 0.852 vs inexact 0.924、断言 6 值最优 F 0.936、关系最优 F 0.737；i2b2 2012 TLINK span IAA 0.39 与 7→3 合并两版发布；Krippendorff α≥0.8/0.667；South et al. 预标注未提高 IAA；Hu 2024（PMC11339492）GPT-4 exact F1 0.593；RadGraph dev 500 份 14,579 实体+10,889 关系、关系 F1 0.82/0.73、含否定/不确定/时间变化属性；THYME DocTimeRel 三值。

**未核实/未找到**
- i2b2 2010 assertion/relation 指南 PDF：目录页本次 500/超时，仅核实到 assets 目录下"Evaluation methods for 2010 Challenge.pdf"存在；
- n2c2 2018 T2 官网指南下载：403；
- 分块边界对人工 span 标注影响的直接实证文献：未找到（4.3 给推断建议）；
- lab/micro comments 类电报体文本的双标 IAA 研究：未找到；
- i2b2 2011 两轮裁决先例：沿用任务书锚点，本次未另行核实原文。
