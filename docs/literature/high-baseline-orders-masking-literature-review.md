# 高基线常规医嘱掩盖高特异性检查 — 文献检索报告

**研究问题**：在基于 EHR 医嘱序列识别诊断或筛查路径时，是否因高基线频率的常规医嘱（CXR、Telemetry、BMP 等）占据相似度、注意力或排名，而降低低频但高特异性检查的可检出性？逆频率、relative risk、PMI/lift 或监督式判别权重能否改善？

**检索日期**：2026-08-18（经本机系统时钟核实，UTC+8）
**检索方式**：web_search 元搜索引擎多轮检索（覆盖 PubMed/PMC、Google Scholar、ACM DL、arXiv、出版社站点）。**注意**：未直接在 PubMed/Scopus 执行布尔检索——正式系统检索请使用文末附录检索式。

**概念框架**（三支 + 两支补充）：
- A. 医嘱推荐中的频率/流行度偏倚（popularity bias / baseline-frequency bias）
- B. 临床事件长尾与类别不平衡（long-tail clinical events / rare-item recall）
- C. 序列/路径挖掘中的通用项目支配（common-item dominance / general-item filtering）
- D. 补充：常规医嘱过度使用与低诊断产出实证（验证"高基线、低产出"前提）
- E. 补充：推荐系统流行度偏倚与去偏方法学（可迁移）

## 检索总览（全部完成）

五条检索线全部完成（A 线亲自检索 + B/C/D/E 四条并行子线，合计约 115 轮 web_search），共收录去重后约 **55 篇**文献（A 线 13、B 线 14、C 线 10、D 线 14 含种子、E 线去重后 7 独立 + 3 交叉命中）。

**三条核心结论**：
1. **研究问题有直接对应的成熟临床研究线**——Stanford VA 的 OrderRex 谱系（2015《Tyranny of the Mob?》→ 2016 OrderRex → 2017 主题模型 → 2018 分层评估 → 2022 门诊 workup），但其方法学在 2022 年后停滞；生成式模型时代（Foresight 2024）该评估问题重新悬空——**这是你研究的空位**
2. **"common-item dominance" 在文献中没有术语化命名**——最近的三组锚点已定位：RecSys 的 popularity bias（E 线）、process mining 的 chaotic/infrequent activity filtering（C7/C8）、判别模式挖掘的 low-support discriminative patterns（C10）
3. **最大空白 = 医嘱序列层面的长尾/逆频率加权评估**——现有临床长尾研究集中在 ICD 编码与诊断/用药预测，order set / lab panel 层面几乎无人做（G#5）——**这既是检索空白也是研究定位点**

---

## A. 种子线：医嘱推荐中的频率偏倚（Stanford OrderRex 谱系）✅ 已完成

用户给定的种子已全部核实并扩展为完整谱系（Chen JH / Altman RB / Goldstein MK 团队，Stanford VA）：

| # | 文献 | 出处 | 相关性 | 要点 |
|---|------|------|--------|------|
| A0 | **Data-Mining Electronic Medical Records for Clinical Order Recommendations: Wisdom of the Crowd or Tyranny of the Mob?** | Chen JH, Altman RB, 2015（PMID 26306281；PMC4525236；刊名待核，疑为 AMIA 年会论文集） | 🔴直接（★E 线新发现） | **谱系起点、与研究问题几乎同题**：医嘱推荐中"群体智慧"vs"高频医嘱暴政"的张力——该问题最早的临床侧表述 |
| A1 | **OrderRex: Clinical order decision support and outcome predictions by data-mining electronic medical records** | Chen JH et al., *JAMIA* 2016;23(2):339-348 | 🔴直接（种子） | 排除生命体征、常规饮食、转运等 routine process orders；用逆基线频率给少见特异医嘱更高权重；relative risk 方法使 inverse-frequency weighted recall 从 4% 提高到 16% |
| A2 | **Dynamically Evolving Clinical Practices and Implications for Predicting Medical Decisions** | Chen JH et al., *PSB 2016*（PMID 26776186, PMC4719775） | 🔴直接（种子） | 明确区分"预测最可能出现的常见医嘱"vs"找出较少见但更有特异性的医嘱"；普通准确率会奖励常见但平庸的建议 |
| A3 | **Predicting inpatient clinical order patterns with probabilistic topic models vs conventional order sets** | Chen JH et al., *JAMIA* 2017;24(3):472-480（PMID 27655861） | 🔴直接 | OrderRex 的方法学前作：LDA 主题模型学习医嘱共现模式；按 top-k 评估；为后续逆频率加权的动机来源 |
| A4 | **Decaying relevance of clinical data towards future decisions in data-driven inpatient clinical order sets** | Chen JH et al., *IJMI* 2017（PMID 28495350, PMC5459355） | 🟡方法可迁移 | 历史训练数据时效性衰减——流行度本身随时间漂移，加剧"追认常见医嘱"问题 |
| A5 | **Inpatient Clinical Order Patterns Machine-Learned From Teaching Versus Attending-Only Medical Services** | Wang et al., *AMIA Jt Summits* 2018（PMC5961816） | 🟡方法可迁移 | 不同临床家队列学到的医嘱模式差异——医嘱流行度是人群/机构依赖的 |
| A6 | **An Evaluation of Clinical Order Patterns Machine-Learned from Clinician Cohorts Stratified by Patient Mortality Outcomes** | Chen JH, Altman RB et al., *AMIA* 2018（PMC6250126） | 🟡方法可迁移 | 按患者结局分层评估医嘱模式——分层评估思想的先例 |
| A7 | **A Data-Driven Algorithm to Recommend Initial Clinical Workup for Outpatient Specialty Referral** | Ip W, Prahalad P, Palma J, Chen JH, *JMIR Med Inform* 2022;10(3):e30104 | 🔴直接（种子） | 常见但与专科无关的检查预测力低；逆频率 + 专科 relative risk 加权改善 precision 与 recall |
| A8 | **ClinicNet: machine learning for personalized clinical order set recommendations** | Wang JK et al., *JAMIA Open* 2016;3(2):216-226（doi:10.1093/jamiaopen/ooaa021） | 🟡方法可迁移 | 个性化 order set 推荐；个性化本身可部分缓解全局流行度支配 |
| A9 | **SuperOrder: Provider order recommendation system for outpatient clinics** | *J Health Inform* 2020;26(2):999-1016（PMID 31266390） | 🟡方法可迁移 | 门诊医嘱预测（类似商业推荐系统）；用 co-occurrence network 找回 base 预测漏掉的医嘱；以 micro-P/R 评估——恰好缺少分层/加权评估的例子 |
| A10 | **Doctor AI: Predicting Clinical Events via Recurrent Neural Networks** | Choi et al., *PMLR v56* 2016（ML4HC） | 🔴直接（种子） | "最常见标签"基线已很强；少见病输入时输出回落常见代码——头部标签支配的典型证据 |
| A11 | **Foresight — a generative pretrained transformer for modelling of patient timelines using EHR** | Kraljevic et al., *Lancet Digital Health* 2024;6(4):e281-e290（PMID 38519155） | 🔵背景 | 生成式"下一事件/医嘱"预测的最新代表；评估仍以常规 top-k 为主、未见流行度偏倚分层——说明该问题在新一代模型中仍未被系统处理 |
| A12 | **Assessment of Machine Learning-Based Medical Directives to Expedite Care in Pediatric Emergency Medicine** | *JAMA Netw Open* 2022（PMC8928004） | 🔵背景 | ML 预测并自动开立常见检查以加速分诊——常规医嘱高基线频率的下游制度化现象 |

链接：
- A0: https://pubmed.ncbi.nlm.nih.gov/26306281/ ｜ 全文 https://pmc.ncbi.nlm.nih.gov/articles/PMC4525236/
- A1: https://pubmed.ncbi.nlm.nih.gov/26198303/ ｜ 全文 https://pmc.ncbi.nlm.nih.gov/articles/PMC5009921/
- A2: https://pubmed.ncbi.nlm.nih.gov/26776186/ ｜ https://pmc.ncbi.nlm.nih.gov/articles/PMC4719775/
- A3: https://pubmed.ncbi.nlm.nih.gov/27655861/ ｜ https://academic.oup.com/jamia/article/24/3/472/2631517
- A4: https://pubmed.ncbi.nlm.nih.gov/28495350/ ｜ https://pmc.ncbi.nlm.nih.gov/articles/PMC5459355/
- A5: https://pmc.ncbi.nlm.nih.gov/articles/PMC5961816/
- A6: https://pmc.ncbi.nlm.nih.gov/articles/PMC6250126/
- A7: https://medinform.jmir.org/2022/3/e30104
- A8: https://academic.oup.com/jamiaopen/article/3/2/216/5864422
- A9: https://pubmed.ncbi.nlm.nih.gov/31266390/ ｜ https://journals.sagepub.com/doi/full/10.1177/1460458219857383
- A10: https://proceedings.mlr.press/v56/Choi16.pdf
- A11: https://pubmed.ncbi.nlm.nih.gov/38519155/
- A12: https://pmc.ncbi.nlm.nih.gov/articles/PMC8928004/

**A 线小结**：这是与你的问题最直接对应的一条成熟研究线（Stanford VA 系，2015–2022，起点 A0 的标题几乎就是你的研究问题的同义表述）。核心可复用设计：①排除 routine process orders 的纳入标准；②逆基线频率加权输入医嘱；③relative risk（疾病组 vs 对照组的医嘱条件频率比）作为特异度权重；④inverse-frequency weighted recall 作为报告指标。谱系在 2022 年后未再明显推进，生成式模型（A11）出现后该评估问题重新悬空——这正是你研究的空位。

另发现相邻但未深入的路标（供后续人工判断）：
- **Mining for Clinical Expertise in (Undocumented) Order Sets to Power an Order Suggestion System**（Chen-Altman，Semantic Scholar https://www.semanticscholar.org/paper/3c01097402b2e5616046aa944431635a203bce46 ）——同组从"未文档化 order set"中挖掘临床专长驱动医嘱建议，元数据待核
- Using EHR Audit Logs to Capture Diagnostic Pathways and Time to Diagnosis（Kaiser Permanente，DOR 研究 https://divisionofresearch.kaiserpermanente.org/studies/using-ehr-audit-logs-to-capture-diagnostic-pathways-and-time-to-diagnosis/）——审计日志捕获诊断路径的方法学，与你"医嘱序列→诊断路径"设定相关
- Predicting Laboratory Test Ordering in ED Using Integrated Structured and Unstructured EHR（JMIR Med Inform，https://medinform.jmir.org/2026/1/e85255 / https://www.sciencedirect.com/org/science/article/pii/S2291969426001742）——检验医嘱预测的最新例子

---

## B. 长尾临床事件与类别不平衡（子检索线）✅ 已完成（18 轮检索）

| # | 文献 | 出处 | 相关性 | 要点 |
|---|------|------|--------|------|
| B1 | **GRAM: Graph-based Attention Model for Healthcare Representation Learning** | Choi et al., *KDD 2017* | 🔴直接 | Doctor AI 同团队后续：用 ICD 本体层级注意力让罕见诊断"借力"祖先节点表征；动机即"不常见疾病数据不足"；**按代码频率分层评估诊断预测**——分层评估协议的先例 |
| B2 | **Enhancing Rare Codes via Probability-Biased Directed Graph Attention for Long-Tail ICD Coding** | Chen & Chen, arXiv 2025 (2511.09559) | 🔴直接 | 有向二部图上"概率偏置"注意力，显式把注意力向低频码倾斜——与"逆频率加权注意力/排名"同构，报告稀有码 recall 提升 |
| B3 | **Learning Under Extreme Label Imbalance in EHRs: A Dependency-Aware Loss for Multi-Label Classification** | Ho et al., *PMLR v333* (~2025-26) | 🔴直接 | EHR 多标签极端不平衡的依赖感知损失——与"逆频率加权 vs 监督判别权重"对比实验最接近的一篇，值得精读损失形式与分层评测 |
| B4 | **Labels matter: Incorporating label knowledge into dual branch knowledge distillation for long-tailed ICD code assignment** | *IPM* 2026 (S0306457326002931) | 🔴直接 | 双分支知识蒸馏 + 标签知识注入，训练侧缓解长尾 |
| B5 | **Enhancing ICD classification with semantic embedding rectification and long-tail refinement** | *KBS* 2025 (doi 10.1016/j.knosys.2025.114530) | 🔴直接 | 两阶段：先纠正常见/罕见码表征偏移再长尾细化——直接对应"高频码挤占表征空间" |
| B6 | **Bridging the Version Gap: Multi-version Training Improves ICD Code Prediction, Especially for Rare Codes** | Liu–Nguyen et al., *BioNLP 2026* (2026.bionlp-1.29) | 🔴直接 | 标题即"尤其改善稀有码"；在稀有码子集分层报告——head/tail 分层评估协议参考实现 |
| B7 | **StratMed: Relevance stratification between biomedical entities for sparsity on medication recommendation** | *KBS* 2024;v284 | 🔴直接 | 用药/医嘱推荐侧长尾：按"相关度分层"缓解尾部稀疏——与医嘱 head/mid/tail 分层同源 |
| B8 | **Large-scale long-tailed disease diagnosis on radiology images** | *Nat Commun* 2024;15 (10.1038/s41467-024-54424-6) | 🔴直接 | 影像多标签长尾诊断基准，按频率分层评测——"胸片等高频检查挤占排名"的影像侧对应物 |
| B9 | **Performance of weakly-supervised EHR-based phenotyping methods in rare-outcome settings** | Hong–Nelson et al., arXiv 2026 (2604.09913) | 🔴直接 | 系统比较弱监督表型算法（含逆频率型评分）在罕见结局下的 PPV/灵敏度——直接命中"低频高特异性能否被检出" |
| B10 | **Synthetic Clinical Notes for Rare ICD Codes: A Data-Centric Framework for Long-Tail Medical Coding** | arXiv 2025 (2511.14112) | 🟡缓解-数据侧 | 为稀有码合成文本平衡长尾，与损失侧方案互补 |
| B11 | **Class imbalance correction in AI models leads to miscalibrated clinical predictions: a real-world evaluation** | medRxiv 2026 (26347634) | ⚠️方法学警示 | 类不平衡校正（重加权/重采样）改善少数类识别但**破坏校准**——评估逆频率加权时必须监控阈值/排名副作用 |
| B12 | **A survey of automated ICD coding: development, challenges, and applications** | Wang K et al., *Intelligent Medicine* 2022 | 🔵背景 | "码分布极端不平衡"为该任务第二大挑战——综述引文枢纽 |
| B13 | **Creating a computer assisted ICD coding system: performance metric choice and use of the ICD hierarchy** | medRxiv 2024 (24301382) | 🟡方法可迁移 | 幂律标签下指标选择：micro 指标被头部主导，macro/层级指标更合适——直接呼应"不要只用 micro-AUC" |
| B14 | **Automated Medical Coding on MIMIC-III and MIMIC-IV: A Critical Review and Replicability Study** | Edin, Junge et al., *SIGIR '23* | 🔵背景 | 自动编码评估综述（arXiv 2304.10909） |

链接：B1 https://www.kdd.org/kdd2017/papers/view/gram-graph-based-attention-model-for-healthcare-representation-learning ｜ B2 https://arxiv.org/abs/2511.09559 ｜ B3 https://proceedings.mlr.press/v333/ho26a.html ｜ B4 https://www.sciencedirect.com/science/article/abs/pii/S0306457326002931 ｜ B5 https://www.sciencedirect.com/science/article/abs/pii/S0950705125015692 ｜ B6 https://aclanthology.org/2026.bionlp-1.29/ ｜ B7 https://www.sciencedirect.com/science/article/abs/pii/S0950705123009887 ｜ B8 https://browse.arxiv.org/abs/2312.16151 ｜ B9 https://ar5iv.labs.arxiv.org/html/2604.09913 ｜ B10 https://ar5iv.labs.arxiv.org/html/2511.14112 ｜ B11 https://www.medrxiv.org/content/10.64898/2026.03.04.26347634v1.full ｜ B12 https://www.sciencedirect.com/science/article/pii/S2667102622000092 ｜ B13 https://www.medrxiv.org/content/10.1101/2024.01.16.24301382v1.full ｜ B14 https://dl.acm.org/doi/10.1145/3539618.3591918

另两条元数据不全的线索：SCALE（药物组合推荐长尾，Semantic Scholar: https://www.semanticscholar.org/paper/abd5aa89c0f773e1d1586b69b7058968cb0944d0 ）、Theoretically Grounded Adaptive Sampling for Imbalanced Multi-Label Classification in Medical Text（https://ieeexplore.ieee.org/document/11296761 ）。

**B 线小结**：临床侧长尾研究集中在 ICD 编码与诊断/用药预测；"医嘱序列层面的长尾"几乎空白（见 G#5）；B11 提示逆频率加权需同时报告校准指标。

## C. 序列/路径挖掘中的通用项目支配（子检索线）✅ 已完成（~30 轮检索）

| # | 文献 | 出处 | 相关性 | 要点 |
|---|------|------|--------|------|
| C1 | **Methods for Analyzing Medical-Order Sequence Variants in Sequential Pattern Mining for EMR Systems** | Le HH, Yasumitsu, Yokota 等，ACM（DOI 10.1145/3561825） | 🔴直接（种子） | 过滤"几乎出现在每条序列中的高频通用医嘱"，以免其主导序列变体与路径分析——与研究表述最接近的一篇 |
| C2 | **Detection and Visualization of Variants in Typical Medical Treatment Sequences** | Honda, Kushima, Yamazaki, Araki, Yokota, *DMAMH/LNCS 10494* 2017 | 🔴直接 | 种子前驱：先检测"典型序列"（共同主干），再把偏离主干的部分作为变体检测与可视化——"公共主干 vs 变体"分离 |
| C3 | **Extraction and Graph Structuring of Variants By Detecting Common Parts of Frequent Clinical Pathways** | Kushima et al., 2018（T2R2/Semantic Scholar 收录） | 🔴直接 | 显式检测高频临床路径的公共部分、剩余变体结构化为图——与"高频通用项目过滤"最同构的临床路径工作 |
| C4 | **Analysis of Transitions in Differences between Frequent Medical-order Sequences for COVID-19** | Zhao et al., *IEEE CBMS 2023* | 🔴直接 | 种子同团队后续：对 COVID-19 各阶段/机构的高频医嘱序列做差异与转移分析 |
| C5 | **A Clustering-based Sequence Variants Analysis Method for EMRs of Multimedical Institutions** | Le et al., *IEEE* 2024 | 🔴直接 | 系列最新：跨多医疗机构 EMR 的医嘱序列变体聚类——"机构间共性医嘱 vs 变体"权衡 |
| C6 | **Mining and exploring care pathways from EMRs with visual analytics (CarePath)** | Perer et al., *JBI* 2015（PMID 26146159） | 🟡方法可迁移 | 事件序列聚类 + 路径变体可视化探索；含按频率聚合/简化路径的交互手段 |
| C7 | **Discovering more precise process models from event logs by filtering out chaotic activities** | Tax et al., *JIIS* 2019;52(1) | 🟡方法可迁移 | 定义并过滤 "chaotic activities"（无处不在且与后续活动无稳定依赖）——与"几乎人人都开的常规医嘱"问题同构，过滤准则可直接迁移 |
| C8 | **Cherry-Picking from Spaghetti: Multi-range Filtering of Event Logs** | Vidgof et al., *CAiSE 2020 Workshops*（LNCS） | 🟡方法可迁移 | 多区间频率过滤：只保留活动频率落在指定区间内的事件（同时压掉过高频与过低频）——逆频率加权的"硬过滤"版本，最直接可操作 |
| C9 | **Supervised Descriptive Rule Discovery: A Unifying Survey of Contrast Set, Emerging Pattern and Subgroup Discovery** | Kralj Novak et al., *JMLR* 2009;10:377-403 | 🟡方法可迁移 | contrast set / emerging patterns / subgroup discovery 统一综述——"监督判别权重 / RR 式指标"的方法论基础框架 |
| C10 | **Mining Low-Support Discriminative Patterns from Dense and High-Dimensional Data** | Fang et al., *IEEE TKDE* 2012 | 🟡方法可迁移 | 稠密高维数据中"低支持度×强判别性"模式挖掘——与"低频高特异检查被高频常规医嘱淹没"**完全同构**；支持度×判别力联合评价思路可直接借鉴 |

链接：C1 https://dl.acm.org/doi/10.1145/3561825 ｜ C2 https://link.springer.com/chapter/10.1007/978-3-319-67186-4_8 ｜ C3 https://www.semanticscholar.org/paper/7e81eb653ab7c849c77e1b972a22d93f90d2d60a ｜ C4 https://ieeexplore.ieee.org/document/10178829 ｜ C5 https://ieeexplore.ieee.org/document/10708019 ｜ C6 https://www.sciencedirect.com/science/article/pii/S1532046415001306 ｜ C7 https://link.springer.com/article/10.1007/s10844-018-0507-6 ｜ C8 https://link.springer.com/chapter/10.1007/978-3-030-49418-6_9 ｜ C9 https://jmlr.csail.mit.edu/papers/v10/kralj-novak09a.html ｜ C10 https://ieeexplore.ieee.org/document/5645630

背景路标：Modelling and Mining of Patient Pathways: A Scoping Review（arXiv 2206.01980，https://arxiv.org/abs/2206.01980 ，署名待核）；MEDICON 2007 contrast sets 脑缺血应用（https://kt.ijs.si/PetraKralj/publications/medicon2007-LavracEtAl.pdf ，署名排序未核实）

**C 线小结**：种子文献属于东京工业大学 Yokota 组"医嘱序列变体分析"系列（Honda 2017 → Kushima 2018 → C1 种子 → Zhao 2023 → Le 2024），方法核心=**提取公共主干 + 只分析变体**；通用侧最接近的概念是 process mining 的 chaotic/infrequent activity filtering（C7/C8）与判别模式挖掘的 low-support discriminative patterns（C10）。**"common-item dominance" 在文献中没有术语化命名**——检索与写作时应以这三组锚点词定位。

## D. 常规医嘱过度使用与低诊断产出（子检索线）✅ 已完成（23 轮检索）

用户 3 篇种子 + 扩展实证：

| # | 文献 | 出处 | 相关性 | 要点 |
|---|------|------|--------|------|
| D0a | **住院遥测过度使用**（种子） | PMID 33196281 | 🔴直接（种子） | 遥测过度使用实证 |
| D0b | **日常 BMP 可减少**（种子） | PMID 25696797 | 🔴直接（种子） | 日常 BMP 减少安全性 |
| D0c | **常规 CXR 低产出**（种子） | PMID 8873504 | 🔴直接（种子） | 常规 CXR 低诊断产出经典研究 |
| D1 | **Abandoning daily routine chest radiography in the ICU: meta-analysis** | Oba Y, *Radiology* 2010 | 🔴直接 | ICU 每日常规胸片 meta 分析：不改善结局，支持放弃（ICU 场景证据充足） |
| D2 | **Routine chest radiography in uncomplicated suspected ACS rarely yields significant pathology** | Ng, *EMJ* 2008;25(12):807-810 | 🔴直接 | 急诊疑似 ACS 常规 CXR"极少发现显著病变"——补种子未覆盖的急诊/入院场景 |
| D3 | **ACR Appropriateness Criteria: Routine Chest Radiography** | ACR 委员会，2016 起（J Thorac Imaging / 持续更新） | 🔵背景 | 指南级："无心肺疾病者住院常规胸部影像通常不适宜" |
| D4 | **Don't order daily chest radiography in hospitalized patients unless there are specific clinical indications** | AAFP Choosing Wisely | 🔵背景 | "无特定指征不开每日胸片" |
| D5 | **Decreasing unnecessary use of continuous cardiac monitoring (telemetry) in hospitalised patients** | Silverstein et al., *BMJ* 2024;386:e077499 | 🔴直接 | 系统干预（含限制遥测医嘱时长）实质削减住院不必要遥测——2015 后高质量实证 |
| D6 | **Are We Monitoring Too Much? A Critical Review of Telemetry Overuse in Inpatient Medicine** | Tran H, *Cardiology in Review* 2025 | 🔵背景 | 最新住院遥测过度使用综述（比种子更新） |
| D7 | **Update to Practice Standards for ECG Monitoring in Hospital Settings (AHA)** | Sandau KE et al., *Circulation* 2017 | 🔵背景 | AHA 适应证分层：多数低风险住院患者不需持续监测 |
| D8 | **A Multidisciplinary Housestaff-Led Initiative to Safely Reduce Daily Laboratory Testing** | Iams W et al., *Academic Medicine* 2016;91(6):813-820 | 🔴直接 | 住院医主导 QI 安全减少每日化验——与 BMP 种子 RCT 互补 |
| D9 | **Initiative to reduce unnecessary routine daily testing of CBC across 11 safety net hospitals** | 含 Cho HJ 等，*Am J Clin Pathol* 2024;161(4):388 | 🔴直接 | 11 家安全网医院规模减少常规每日 CBC |
| D10 | **How to decrease routine and repetitive blood tests in hospitalized patients** | 含 Moriates C 等，*Canadian Family Physician* 2024;70(11-12):701 | 🔵背景 | 减少常规/重复抽血实践综述（免费全文） |
| D备 | Routine chest x-rays in ICU: systematic review and meta-analysis | Ganapathy，期刊待核（PMID 22541022） | 🟡 | 9 RCT、39,358 张胸片、9,611 例：未见获益或危害 |

链接：D1 https://pubmed.ncbi.nlm.nih.gov/20413752/ ｜ D2 https://pubmed.ncbi.nlm.nih.gov/19033495/ ｜ D3 https://acsearch.acr.org/docs/69451/Narrative ｜ D4 https://www.aafp.org/pubs/afp/collections/choosing-wisely/514.html ｜ D5 https://pubmed.ncbi.nlm.nih.gov/39074876/ ｜ D6 https://pubmed.ncbi.nlm.nih.gov/41004710/ ｜ D7 https://pubmed.ncbi.nlm.nih.gov/28974521/ ｜ D8 https://pubmed.ncbi.nlm.nih.gov/27028031/ ｜ D9 https://pubmed.ncbi.nlm.nih.gov/38041859/ ｜ D10 https://pmc.ncbi.nlm.nih.gov/articles/PMC11634256/ ｜ D备 https://pubmed.ncbi.nlm.nih.gov/22541022/

**D 线小结——各常规项目证据状态**：
| 项目 | 证据状态 | 缺口 |
|------|----------|------|
| ICU 每日 CXR | ✅ 充足（meta + ACR/AAFP + 种子） | — |
| 非 ICU 入院/急诊常规 CXR | 🟡 指南明确低价值 | 2015 后大样本定量产出（异常率/改变管理比例）研究缺——需自有队列 |
| 遥测 | ✅ 充足（AHA 2017 + BMJ 2024 + CIR 2025 + 种子） | "可行动警报率"具体数字缺可靠定量来源 |
| 日常 BMP/CBC | ✅ 充足（种子 RCT + Iams 2016 + AJCP 2024 + CFP 2024） | 具体减少幅度需全文提取 |
| 高基线频率分布本身 | ⚠️ 无跨机构固定数字 | **必须用自有 EHR 队列医嘱发生率验证** |

## E. 推荐系统流行度偏倚与去偏方法学（子检索线）✅ 已完成（22 轮检索）

| # | 文献 | 出处 | 相关性 | 要点 |
|---|------|------|--------|------|
| E1 | **A survey on popularity bias in recommender systems** | Klimashevskaia, Jannach, Elahi, Trattner, *UMUAI* 2024 | 🟡方法可迁移 | 迄今最系统的 popularity bias 综述：偏倚来源、度量、去偏方法分类——"医嘱推荐偏倚评估"的方法学总纲 |
| E2 | **Unbiased Recommender Learning from Missing-Not-At-Random Implicit Feedback** | Saito et al., *WSDM 2020*（会议信息待核） | 🟡方法可迁移 | IPS/倾向得分去偏里程碑："未点击≠不喜欢" ↔ 临床"**未下单≠不需要**"的 MNAR 结构，可迁移为医嘱倾向加权评估 |
| E3 | **Model-Agnostic Counterfactual Reasoning for Eliminating Popularity Bias (MACR)** | Wei et al., *KDD 2021* | 🟡方法可迁移 | 反事实推理剥离"流行度→打分"直接通路，模型无关——临床类比：剥离"常规医嘱基线频率"通路，保留患者特异性证据 |
| E4 | **Contrastive Learning for Debiased Candidate Generation (CLRec/DCL)** | Zhou et al., *KDD 2021* | 🟡方法可迁移 | 对比学习惩罚表示向头部热门物品坍缩，保持长尾可检出——与"常规医嘱占据相似度/注意力"**同构** |
| E5 | **Managing Popularity Bias in Recommender Systems with Personalized Re-ranking** | Abdollahpouri et al., *RecSys 2020*（待核） | 🟡方法可迁移 | 精度-偏倚多目标重排 + 按用户流行度偏好分组分层评估——head/tail 分组报告的直接蓝本 |
| E6 | **Incorporating System-Level Objectives into Recommender Systems** | Abdollahpouri et al., arXiv 2019（1906.01435，正式版待核） | 🟡方法可迁移 | 提出 **ARP（Average Recommendation Popularity）** 系统级偏倚度量并做受约束优化——最易移植的单一医嘱偏倚指标 |
| E7 | **Causal Inference in Recommender Systems: A Survey and Future Directions** | Gao et al., *ACM TOIS* 2024;42(4) | 🟡方法可迁移 | 去混杂/反事实/IPS 统一框架——把"医嘱开立频率混杂"显式建成因果图的文献入口 |
| E8 | **Wisdom of the Crowd or Tyranny of the Mob?** | 同 A0（Chen & Altman 2015） | 🔴直接 | E 线独立检索命中的唯一临床场景论文，恰好验证 A0 的中心地位（已去重并入 A 线） |
| E9 | **StratMed** | 同 B7（arXiv 2308.16781 → KBS 2024） | 🔴直接 | 两个子线交叉命中，去重 |
| E10 | **SCALE: Sharpness-Aware Correction for Long-Tail Effects in Combinatorial Medication Recommendation** | Feng 等（元数据待核，Semantic Scholar 收录） | 🔴直接 | 锐度感知修正处理组合用药长尾（罕见组合被高频组合压制）——去偏方法落地临床组合推荐的例证 |

链接：E1 https://link.springer.com/article/10.1007/s11257-024-09406-0 ｜ E2 https://arxiv.org/abs/1909.03601 ｜ E3 https://dl.acm.org/doi/10.1145/3447548.3467289 ｜ E4 https://dl.acm.org/doi/10.1145/3447548.3467102 ｜ E5 https://arxiv.org/abs/1901.07555 ｜ E6 https://arxiv.org/abs/1906.01435 ｜ E7 https://dl.acm.org/doi/10.1145/3639048 ｜ E10 https://www.semanticscholar.org/paper/abd5aa89c0f773e1d1586b69b7058968cb0944d0

**E 线小结——可移植到"医嘱推荐偏倚评估"的指标/方法清单**：
- **Head/Tail 分层 Recall@K（tail recall）**：按医嘱基线开立频率分组分别报告，head-tail 差值为偏倚度（E1/E5）
- **Macro-recall / per-item 等权召回**：低频高特异检查不被常规医嘱摊薄
- **Coverage@K**：推荐覆盖的医嘱种类比例——检测坍缩到少数 order set
- **ARP（平均推荐流行度）**：直接量化"推荐=常规医嘱"程度（E6）
- **Novelty/自信息量（-log 开立频率）**：低频特异检查应贡献更高新颖性
- **患者亚组分层评估**：对低医嘱强度亚组单独报告（类比 E5 的按流行度偏好分组）
- **IPS/SNIPS 倾向性加权（训练+评估双端）**：把"未开立医嘱"视为 MNAR（E2）
- **反事实去流行度通路（MACR 式 do- 操纵）** 作用于打分层；**对比学习去表示坍缩（CLRec 式）** 作用于表示层（E3/E4）
- 临床侧先例（A0/E9/E10）证明该问题在真实 EHR 医嘱/用药推荐中已被识别并有修正方案——可作动机引用与对照基线

---

## F. 评估指标建议（基于已确认文献）

| 指标 | 出处/依据 | 说明 |
|------|-----------|------|
| inverse-frequency weighted recall | OrderRex（A1） | 直接对应目标问题的主指标 |
| relative risk / lift / PMI | OrderRex（A1）、Workup（A7） | 医嘱特异度权重 |
| macro recall / macro-F1 | ICD 编码指标选择论文（B 线） | 对头部标签不敏感 |
| head/mid/tail 分层 recall | B 线长尾文献 | 按医嘱基线频率分层报告 |
| rare-item recall@k | RecSys（E 线）+ B 线 | 少见高特异检查的召回 |
| 移除常规项目后的路径稳定性 | C 线序列挖掘 | 稳健性/可解释性检验 |
| 校准指标（ECE / 校准曲线 / 阈值敏感性） | B11（类不平衡校正 → miscalibration） | 逆频率/重加权改善少数类召回的同时可能破坏校准——必须作为副作用监控项一并报告 |
| ARP（平均推荐流行度）/ Coverage@K / Novelty(-log f) | RecSys E 线（E1/E5/E6） | 量化"推荐=常规医嘱"程度、目录坍缩与新颖性——RecSys 标准偏倚度量移植 |
| IPS/SNIPS 倾向性加权（训练+评估双端） | RecSys E2 | 把"未开立医嘱"视为 MNAR（未下单≠不需要）校正训练与评估 |
| 模式支持度 × 判别力联合评价 | C 线（C9/C10, contrast set / emerging pattern / subgroup discovery 框架） | 低支持度×强判别性模式的筛选准则——监督判别权重的方法论基础 |

## G. 检索空白与后续动作（随检索线完成持续更新）

1. web_search 无法执行布尔/截词/字段限定——正式检索需到 PubMed/Scopus/WoS/ACM DL/IEEE Xplore 执行附录检索式
2. Forward citation chase：在 Scopus/WoS 对 OrderRex（2016）和 ACM 序列变体论文（10.1145/3561825）做前向引文追踪——A 线谱系 2022 年后的延伸最可能藏在这里
3. "几乎人人都做"应以自有队列发生率验证，不作跨机构固定假设（D 线定量证据只能作为先验）
4. **（B 线）**"fallback to frequent codes"现象在临床文献中几乎不以此措辞出现，多存在于 RecSys 文献——建议在 SIGIR/KDD/RecSys、OpenReview 用 "popularity bias" + healthcare/sequential recommendation 补检
5. **（B 线）**医嘱序列层面（order set / lab panel）的长尾研究几乎空白，现有工作集中在 ICD 编码与诊断/用药预测——建议在 AMIA/JAMIA/JMIR 用 "order set" prediction / clinical order recommendation 补检；**这个空白本身就是你研究的定位依据**
6. **（B 线）**PMI/lift/relative risk 等有趣度度量在临床序列挖掘中缺乏直接对比评估——建议 PubMed/Embase 用 association rule mining EHR interestingness measures 补检
7. **（B 线）**head/mid/tail 分层 recall 报告口径不统一（训练频次分位 vs 出现次数阈值）——需人工核对 PLM-ICD、GATIC 等标准 ICD 基准的评测协议，并对 Doctor AI / GRAM 做 Semantic Scholar / Connected Papers 引文追溯
8. **（C 线）**"common-item dominance" 在文献中**没有术语化命名**——检索与写作应以三组锚点词定位：process mining 的 chaotic/infrequent activity filtering（C7/C8）、判别模式挖掘的 low-support discriminative patterns（C10）、临床侧 Yokota 组医嘱序列变体分析系列（C1–C5）
9. **（C 线）**医嘱序列挖掘中的逆频率/TF-IDF 式项目加权几乎无直接命中（TF-IDF + clinical events 命中的多为临床文本表型）；PMI/lift/interestingness 用于医嘱/检查关联的结果稀薄（多为基因数据或疾病-用药关联）——**这两个角度正是你研究的增量贡献空间**
10. **（C 线）**引文滚动：种子文献 ACM 页（10.1145/3561825）citing articles（Scopus 显示近百篇施引）+ Tax 2019 / Fang 2012 的施引文献；IEEE Xplore 上 CBMS/BIBM/BIBE + "event log filtering" 主题
11. **（D 线）**非 ICU 入院/急诊常规 CXR 的 2015 后大样本定量产出研究缺；遥测可行动警报率缺定量来源；"高基线频率"分布必须用自有 EHR 队列验证（与 #3 呼应）

## H. 跨线 Top 12 最相关文献（按直接程度排序）

**第一梯队（直接命中研究问题）**
1. **A0** Wisdom of the Crowd or Tyranny of the Mob?（Chen & Altman 2015）——问题的最早临床侧表述，标题即问题
2. **A1** OrderRex（JAMIA 2016）——核心方法论文：排除 routine orders + 逆频率加权 + RR + weighted recall（4%→16%）
3. **A2** Dynamically Evolving Clinical Practices（PSB 2016）——"预测常见医嘱"≠"找出特异医嘱"的概念区分
4. **A7** Data-Driven Workup Recommendation（JMIR 2022）——RR+逆频率在专科转诊检查推荐的应用
5. **C1** Medical-Order Sequence Variants（ACM，Yokota 组）——高频通用医嘱过滤的直接实现（用户种子）
6. **A10** Doctor AI（PMLR 2016）——头部标签支配/输出回落常见代码的典型证据

**第二梯队（方法直接同构，可迁移）**
7. **C7** Tax et al. chaotic activities 过滤（JIIS 2019）——"无处不在且无稳定依赖的活动"过滤准则
8. **C10** Fang et al. low-support discriminative patterns（TKDE 2012）——低频×强判别模式挖掘，完全同构
9. **B1** GRAM（KDD 2017）——按代码频率分层评估的先例协议
10. **E2** Saito IPS/MNAR（WSDM 2020）——"未下单≠不需要"的评估校正框架
11. **E1** Popularity bias 综述（UMUAI 2024）——偏倚度量与去偏方法总纲
12. **B11** 类不平衡校正→校准失衡（medRxiv 2026）——逆频率加权副作用的方法学警示

**前提验证梯队（支撑"高基线、低产出"）**：D1（ICU CXR meta）、D5（BMJ 2024 遥测）、D8/D9（化验减少 QI）+ 用户 3 篇种子

---

## 附录：正式数据库检索式（用户提供 + 本轮适配）

（见用户原始三段式检索式；执行时可按各库语法调整 NEAR/截词）

**PubMed / Scopus 核心式**：
```text
("clinical order*" OR "medical order*" OR "diagnostic test*" OR "order recommender*" OR "clinical pathway*")
AND
("inverse frequency" OR "baseline frequency" OR "relative risk" OR "weighted recall" OR "popularity bias" OR "long tail" OR "common item*" OR "general item*" OR "class imbalance")
AND
(predict* OR recommend* OR "pattern mining" OR discriminat* OR specific* OR informative)
```

**序列/流程挖掘式**：
```text
("medical-order sequence*" OR "clinical event sequence*" OR "clinical pathway mining" OR "sequential pattern mining")
AND
(frequent OR ubiquitous OR routine OR "common item*")
AND
(filter* OR downweight* OR variant* OR discriminative OR "information gain" OR "inverse frequency")
```

**常规医嘱基线验证式**：
```text
("chest radiograph*" OR telemetry OR "basic metabolic panel" OR "routine laboratory test*")
AND
("diagnostic yield" OR "low-value" OR overuse OR unnecessary OR routine)
AND
(inpatient* OR hospital* OR "emergency department")
```
