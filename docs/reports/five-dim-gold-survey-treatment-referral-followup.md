# 治疗处置 · 转诊与科室选择 · 离院指导与随访：gold 标准证据笔记

**日期**：2026-08-16
**定位**：MIMIC-IV v3.1 + ED + Note"单次就诊全流程临床决策 MCQ 评测集"项目中，本笔记负责**治疗处置、转诊与科室选择、离院指导与随访**三个维度的文献深挖。核心方法学问题：区分**行为一致性 gold**（实际发生了什么，来自 EHR 事件：POE / prescriptions / eMAR / services / transfers / 出院文书）与**规范性 gold**（专家+指南裁定应该做什么），以及两轨各自的陷阱。决策时点快照禁止未来信息泄漏；患者级 split；后续香港 RWD 适配时美国单中心服务路径不能直接当香港规范性 gold。
**与已有内部材料的关系**：EHRNoteQA (NeurIPS 2024)、MIMIC-CDM (Nat Med 2024)、CliBench、EHRBench、npj DM 2025 (Gaber et al.)、npj DM 2024 (Ayre et al.)、label leakage 框架、i2b2/n2c2、RadGraph/CheXpert、EHRXQA/EHRSQL/DrugEHRQA、MedBench、LLM 构念效度批评 (Alaa ICML 2025) 已被内部材料整体综述，本笔记只做一句话定位引用；增量在于：(a) 关键图表转录与细数字读出；(b) 新检索到的评测体系；(c) 规范性 gold 工具箱核实；(d) 每维 gold 方案。姐妹笔记（检查检验+诊断维度）已深读 MIMIC-CDM 自主 vs 全信息表、EHRNoteQA 修改漏斗、AMIE DDx、Optimization Paradox (arXiv 2506.06574)、ClinDiag、MediTOD/LabTOP——引用这些时一句话定位即可。

---

## 一、规范性 gold 工具箱（任务二）

MIMIC 只能提供行为轨道；规范性 gold 必须借助**外部标准载体**。以下按"隐式判断工具（implicit，专家逐药/逐案打分）"与"显式清单工具（explicit，可规则化/半自动的清单）"和"过程度量（process measures）"三类核实 6 个工具。每个给出：出处、度量什么、怎么打分、报告过的信度/效度数字、对本项目的可用方式与跨体系（香港）适用性。

### 1.1 Medication Appropriateness Index (MAI) —— 隐式、逐药 10 条目

- **出处**：Hanlon JT, et al. [A method for assessing drug therapy appropriateness](https://pubmed.ncbi.nlm.nih.gov/1474400/). *J Clin Epidemiol*. 1992;45(10):1045-1051. doi:10.1016/0895-4356(92)90144-C。
- **度量什么**：单一药物使用的适当性（indication、effectiveness、dosage、directions、drug-drug interaction、drug-disease interaction、practicality、cost、duplication、duration 共 **10 条**）。
- **怎么打分**：每条目 3 级（appropriate=0 / marginally appropriate=1 / inappropriate=2），逐药求和 0–18，可跨药累加；评分者需看病历+做临床判断（隐式）。
- **信度数字（原文）**：药师 vs 老年病学医师独立评 10 例老年患者用药：总体 κ=0.83（ppos 0.88 / pneg 0.95）；评分者内 κ=0.92；**两位不同药师之间 κ 只有 0.59**（ppos 0.76）——同专业背景不同个体间一致性明显下降。
- **本项目可用方式**：治疗维规范性裁定的**逐药打分 rubric**（尤其出院带药/长期用药题）；每题附 MAI 式判定表可把"专家认为不该这样开"变成可复核的分数。
- **局限/香港**：条目是通用药理学原则，跨体系可用，但 cost/practicality 条目依赖当地药价与剂型；原效度研究在老年门诊慢病人群，急症住院场景需重新校准；**双人裁定必须同专业背景**（0.59 的跨个体 κ 是预算人工成本的关键数字）。

### 1.2 AGS Beers Criteria（2023 版）—— 显式、负面清单（≥65 岁）

- **出处**：American Geriatrics Society. [2023 updated AGS Beers Criteria](https://agsjournals.onlinelibrary.wiley.com/doi/10.1111/jgs.18372). *J Am Geriatr Soc*. 2023;71(7):2052-2081（[PubMed 37139824](https://pubmed.ncbi.nlm.nih.gov/37139824/)）。
- **度量什么**：老年人**应避免**的药物：约 40 种药物/类别（多数老人避免）、30 类疾病-综合征组合避免用药、慎用药清单、应避免的药物-药物相互作用；2023 版新增"替代方案清单"。2019→2023：28 种药物被评审移除（15 种因使用量低）。
- **怎么打分**：二元标记（每个用药×每条标准），无总分心理测量结构；可经 RxNorm/ATC 映射**半自动化**。
- **信度/效度数字**：作为显式清单无评分者信度问题；效度证据为大量观察性关联研究（PIM 暴露与不良结局关联），未核实到单一汇总数字。
- **本项目可用方式**：治疗维"不应开"类 MCQ 的**自动出题器**（MIMIC 处方里命中 Beers 的真实案例→考"最应停/换哪一个"）；也是专家裁定的先验证据。
- **局限/香港**：美国处方集与剂量规格（如 combined dosage forms）与香港 HA 药物目录不同，需本地药师做映射；仅适用 ≥65 岁；不含"漏开"维度（见 STOPP/START）。

### 1.3 STOPP/START v3 —— 显式、负面+正面（遗漏）双轴

- **出处**：O'Mahony D, et al. [STOPP/START criteria for potentially inappropriate prescribing in older people: version 3](https://pmc.ncbi.nlm.nih.gov/articles/PMC10447584/). *Eur Geriatr Med*. 2023;14(4):625-632。
- **度量什么**：老年人 PIM（STOPP，**133 条**）与**处方遗漏**（START，**57 条**），共 **190 条**，按生理系统组织；v3 新增 major geriatric syndromes 专节。
- **怎么打分**：逐条二元判定；Delphi 共识（**11 位欧洲 8 国老年医学/药学专家、4 轮**）产生；相比 v2（2015，114 条）扩容 66.7%。
- **信度/效度数字**：原文为共识方法学论文，未报告统一 κ；v2 时代应用的评分者间 κ 文献报告多在 0.6-0.9 区间（未逐一核实，标注【未核实到汇总数字】）。
- **本项目可用方式**：**唯一同时覆盖"不该开"与"该开未开"的显式工具**——START 条目是治疗维"规范性 gold 里行为轨道系统性缺失"的直接证据来源（行为 gold 永远打不出"漏开"分）。
- **局限/香港**：欧洲版（爱尔兰起源）；肾功能阈值、药物可得性需按香港调整；仅 ≥65 岁（v3 提及部分条目可延伸）。

### 1.4 Choosing Wisely —— 显式、"不做清单"（各专科协会）

- **出处**：ABIM Foundation 2012 年发起（初始 9 个专科协会，"Five Things Physicians and Patients Should Question"）；十年回顾见 [JAMA Health Forum 2022](https://jamanetwork.com/journals/jama-health-forum/fullarticle/2793643)（扩展到 80+ 协会、500+ 条建议）；官方入口 [choosingwisely.org](https://www.choosingwisely.org/)。
- **度量什么**：低价值诊疗（commonly ordered but unnecessary tests/procedures）——**否定式建议**，覆盖检查与治疗两维。
- **怎么打分**：无打分体系；条目强度异质（有的基于 RCT，有的仅共识）。
- **本项目可用方式**：治疗/检查维"不应做"正例与干扰项素材库；为专家裁定提供跨专科的"过度医疗"判据。
- **局限/香港**：美国协会条目；加拿大/英国/澳洲有本地化 Choosing Wisely，**未核实到香港官方本地化版本**；条目不可直接当"错误"判据（多为"常见但常不需要"）。

### 1.5 NCCN/指南 concordance 方法学 —— 时间窗+分期的依从判定模板

- **出处**：方法学源头之一为 NCCN Outcomes Database：[Concordance with NCCN colorectal cancer guidelines and ASCO/NCCN quality measures](https://jnccn.org/downloadpdf/journals/jnccn/7/8/article-p895.pdf). *JNCCN*. 2009;7(8):895-903。综述性应用见 [NCCN Guideline Concordance in Colon and Rectal Cancer Patients (2025)](https://pmc.ncbi.nlm.nih.gov/articles/PMC11745911/)。
- **度量什么**：实际给予的治疗（方式、方案、顺序、时限）是否匹配分期对应的指南推荐；**"guideline-concordant"操作定义 = 模式匹配 + 时间窗**（如诊断→治疗间隔）。
- **怎么打分**：逐例二元（concordant/non-concordant），按治疗环节（手术/化疗/放疗）分项；**临床试验治疗计为 concordant**。
- **报告过的数字**：结肠/直肠癌 concordance 率随研究与度量定义在 **22%–92%** 间波动（PMC11745911 及其引用 7-10）；一项研究显示其 concordant 案例中 42% 因"入组临床试验"被计入（[Annals 综述](https://www.sciencedirect.com/science/article/pii/S0006497118447672)）。
- **本项目可用方式**：治疗维规范性 gold 的**操作定义模板**：gold = 指南版本 + 分期锚点 + 时间窗 + 逐环节判定；"临床试验/个体化理由"需显式规定算不算 concordant。
- **局限/香港**：22%-92% 的巨大波动本身就是警示——concordance 结果高度依赖操作定义，写 gold 规范时必须锁定指南版本与时间窗；NCCN 是美国panel产物，香港肿瘤路径另有 HA/本地指南版本（需替换，方法论可复用）。

### 1.6 Sepsis bundle / process measures（SEP-1、SSC bundle、NQF/HEDIS 类）

- **出处**：CMS [SEP-1 Severe Sepsis and Septic Shock Management Bundle](https://www.cms.gov/priorities/innovation/media/document/bpci-advanced-alt-fs-my4-sepsis) 规范页；依从-结局争议见 [Complex Sepsis Presentations, SEP-1 Compliance, and Outcomes (JAMA Netw Open 2025)](https://jamanetwork.com/journals/jamanetworkopen/fullarticle/2831700) 与 [CMI 综述](https://www.sciencedirect.com/science/article/pii/S1198743X24006062)。
- **度量什么**：脓毒症 3 小时 bundle（测乳酸、抗生素前血培养、广谱抗生素）与 6 小时 bundle（脓毒症低血压/乳酸≥4 予 30 mL/kg 晶体、持续低血压用升压药并复测乳酸）的执行；**all-or-none 计分**。
- **怎么打分**：每例二元（全做=合规）；CMS HVBP 自 FY2026 起纳入支付。
- **报告过的数字**：全国医院平均合规率长期在约 50% 上下（[行业汇总](https://prenosis.com/sep-1-bundle-compliance-getting-value-for-the-care-provided/)，量级与文献一致）；合规组 vs 不合规组死亡率约 22.2% vs 26.3%（[Sepsis Alliance 引 CMS 数据](https://www.sepsis.org/protect-sep-1/)）；但 2025 JAMA Netw Open 研究提示该关联可能是复杂病例的混杂。
- **本项目可用方式**：急重症治疗维的**逐元素规范性 gold**——bundle 每个元素天然对应一道"检查/治疗"MCQ，且自带时间窗（3h/6h）与剂量标准（30 mL/kg），是三维中唯一"规范性 gold 可几乎全自动判定"的场景（输入是结构化事件流）。
- **局限/香港**：SEP-1 是美国医保度量（billing 驱动的 sepsis 定义），香港应改用 SSC bundle 定义的本地化版本；all-or-none 计分对 MCQ 反而友好（每个元素独立成题）。

### 1.7 工具箱小结：三维适配矩阵

| 工具 | 类型 | 治疗处置 | 转诊/科室 | 离院随访 | 香港可直接用 |
| --- | --- | --- | --- | --- | --- |
| MAI (Hanlon 1992) | 隐式逐药 | **核心**（逐药适当性 rubric） | – | 出院带药适当性 | 可（通用原则），cost 条目需本地化 |
| Beers 2023 | 显式负面 | **核心**（≥65 岁"不应开"出题器） | – | 出院带药负面清单 | 需 HA 药物目录映射 |
| STOPP/START v3 | 显式负面+正面 | **核心**（START=漏开判定） | – | 出院带药遗漏 | 需本地阈值校准 |
| Choosing Wisely | 显式否定式 | 素材库 | 素材库（低价值转诊/检查） | – | 无官方 HK 版（未核实到） |
| NCCN concordance 方法学 | 方法模板 | 时间窗+分期判定模板 | （专科路径锚点思路可借） | surveillance interval 同思路 | 方法可复用，指南须换本地版 |
| SEP-1/SSC bundle | process measure | **唯一可自动化**（急症场景） | – | – | 用 SSC 定义而非 CMS 定义 |

**结构性结论**：(a) 治疗维的规范性工具最成熟，但全部集中在老年用药与急症 bundle 两个细分场景（niche）；(b) **转诊维没有任何国际通用的适当性量表**——只有指南中的转诊指征和专家小组裁定（见 §三）；(c) 随访维的规范性依据分散在各病种 surveillance 指南中，无统一工具（见 §四）。

## 二、治疗处置维度

### 2.1 现有评测体系（任务一）

**已定位（一句话）**：[MIMIC-CDM](https://www.nature.com/articles/s41591-024-03097-1)（Nat Med 2024）治疗任务（本次已核原文方法，见 2.2）；CliBench/EHRBench 内部已综述，本节只做增量深读。

**新发现/深读的评测体系**：

#### 2.1.1 传统药物推荐评测：SafeDrug / GAMENet 家族（行为 gold 的原型）

- **出处**：SafeDrug：Yang C, et al. [SafeDrug: Dual Molecular Graph Encoders for Recommending Effective and Safe Drug Combinations](https://arxiv.org/abs/2105.02711). IJCAI 2021（[proceedings](https://www.ijcai.org/proceedings/2021/514)）；GAMENet：Shang J, et al. [GAMENet: Graph Augmented Memory Networks for Recommending Medication Combination](https://arxiv.org/abs/1910.06562). AAAI 2020。
- **数据来源**：MIMIC-III（SafeDrug 基准含 MIMIC-III 处理子集，后续工作扩到 MIMIC-IV）。
- **任务设定**：给历史就诊（诊断+用药），预测本次就诊药物组合——**推荐模型评测**（非 LLM MCQ）。
- **gold 构建**：**本次就诊"实际处方集"**（MIMIC 处方记录，行为 gold）；DDI 相互作用矩阵来自 DrugBank，作为唯一规范性元素。
- **指标**：Jaccard / PRAUC / F1（对行为 gold 的复现度）+ **DDI rate**（推荐组合中的禁忌共存率）。
- **规模与结果**：SafeDrug 相对降低 DDI rate 19.43%、Jaccard +2.88%（[arXiv 摘要](https://arxiv.org/abs/2105.02711)原文数字）。
- **局限（对 gold 设计的含义）**：把"实际开的药"当正确答案——行为 gold 的全部问题在此原型化：(a) 实际处方包含不适当用药（Beers/STOPP 能命中的部分被当正例）；(b) **漏开（START 类）永远不算错**；(c) 处方受医保/剂量规格/患者偏好影响；(d) DDI 率只是安全下界，非适当性判定。这一家族延续工作（DrugDoctor/REFINE/PAUP，见 [DrugDoctor PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC11418268/)）均沿用同一行为 gold，未解决规范性问题。

#### 2.1.2 CliBench 的 prescriptions / procedures 任务（LLM 时代、结构化行为 gold）

- **出处**：Ma MD, et al. [CliBench: Multifaceted Evaluation of Large Language Models in Clinical Decisions on Diagnoses, Procedures, Lab Tests Orders and Prescriptions](https://arxiv.org/html/2406.09923v1). arXiv 2406.09923（ML4H workshop）。内部材料已综述整体，本笔记深读其表格（见 2.3）。
- **gold 构建（关键）**：医嘱/处方 gold = **入院 24h 内"第一批"决策**（同批时间戳的所有 orders/prescriptions），按 ICD-10-PCS / LOINC / ATC 编码对齐。
- **含义**："第一批决策"是一个**结构性近似**的决策时点——无需专家标注即获得行为 gold，但批内决策可能互相依赖（先开检查还是先开药取决于医生习惯），且 24h 截断是任意参数。

#### 2.1.3 肿瘤 guideline concordance 评测（规范性 gold 的操作化样本）

- **出处**（代表）：[NCCN Guideline Concordance in Colon and Rectal Cancer Patients: An Analysis from the Ohio Colorectal Cancer Prevention Initiative (OCCPI)](https://pmc.ncbi.nlm.nih.gov/articles/PMC11745911/)（2025，16 医院 2,324 例）；方法学源头：[NCCN Outcomes Database](https://jnccn.org/downloadpdf/journals/jnccn/7/8/article-p895.pdf)（JNCCN 2009）。
- **任务设定**：非 LLM benchmark，而是"实际治疗 vs 指南推荐"的质量度量研究——**它就是治疗维规范性 gold 的实战场**。
- **gold 构建**：按最新 NCCN/同类研究制定 quality indicators，分 major（治疗方式组合）/minor（CEA、MSI、切缘、淋巴结清扫数）；concordance 逐例二元判定；时间窗：诊断→首治疗 ≤60 天。
- **深读见 2.3**。

#### 2.1.4 Sepsis bundle 依从性（process measure 作为规范性 gold 工具）

- **出处**：CMS [SEP-1](https://www.cms.gov/priorities/innovation/media/document/bpci-advanced-alt-fs-my4-sepsis) 规范；结局争议：[Complex Sepsis Presentations, SEP-1 Compliance, and Outcomes (JAMA Netw Open 2025)](https://jamanetwork.com/journals/jamanetworkopen/fullarticle/2831700)；综述批评：[CMI 2024](https://www.sciencedirect.com/science/article/pii/S1198743X24006062)。
- **任务设定**：3h/6h bundle 元素逐项核对（乳酸、血培养、广谱抗生素、30 mL/kg 晶体、升压药、复测乳酸），all-or-none 计分。
- **数字**：全美医院平均合规率长期约 50% 上下（[行业汇总](https://prenosis.com/sep-1-bundle-compliance-getting-value-for-the-care-provided/)）；合规 vs 不合规死亡率约 22.2% vs 26.3%（[Sepsis Alliance 引 CMS](https://www.sepsis.org/protect-sep-1/)）；但 JAMA Netw Open 2025 提示关联可能是混杂（复杂病例更难合规）。
- **对本项目**：约 50% 的基线不合规率 = **行为与规范在治疗维分裂的直接证据**——用行为 gold 评 LLM 会把半数不合规实践当正确答案；用 bundle 做规范性 gold 则天然自带时间窗与剂量标准，可半自动判定。

#### 2.1.5 MIMIC-IV-Ext-CDM（MIMIC-CDM 数据集的官方发布形态）

- **出处**：[PhysioNet MIMIC-IV-Ext-CDM v1.0/1.1](https://physionet.org/content/mimic-iv-ext-cdm/1.0/)（DOI 10.13026/2pfq-5b68）。2,400 例四类腹部病变；治疗 gold = 实际 procedures（ICD 表 + 出院小结 free-text procedures 段，见 2.2 引文）；credentialed 访问。**是我们治疗维可直接复用的数据基础设施**。

### 2.2 gold 方案分析（任务三）

#### 2.2.1 行为轨道：POE / prescriptions / eMAR / procedures 的选择依据

MIMIC-IV v3.1 中与治疗相关的表语义（按 [MIMIC-IV 官方文档](https://mimic.mit.edu/docs/iv/modules/hosp/)）：[poe](https://mimic.mit.edu/docs/iv/modules/hosp/poe/)（医生开立医嘱的意图，含药物与非药物医嘱，recorded at order time）、[prescriptions](https://mimic.mit.edu/docs/iv/modules/hosp/prescriptions/)（药房维度的处方记录，以出院带药/住院期间处方为主）、[emar](https://mimic.mit.edu/docs/iv/modules/hosp/emar/)（床旁给药执行记录）、[procedures_icd](https://mimic.mit.edu/docs/iv/modules/hosp/procedures_icd/)（计费编码的手术/操作）。

**文献先例**：
- **MIMIC-CDM（Nat Med 2024）的治疗 gold 选择（已核原文）**：手术/操作类治疗用 **"实际发生的 operations"**，数据源为 **procedures ICD 表 + 出院小结 procedures 段 free text**，原文明说："The free-text extraction from the discharge summary was required as many essential procedures, including surgeries, were often not included in the procedures table"——**ICD procedures 表会漏掉大量手术，必须用出院小结文本补齐**，这是治疗维 gold 抽取的直接工程先例。
- **MIMIC-CDM 的治疗判定是"指南 × 行为"混合**（已核原文 Methods："we used the aforementioned guidelines to extract the possible treatments for each pathology and then to classify each treatment as either essential or case specific. For each patient, we then determined if the case-specific treatment was appropriate by matching against the actual operations performed"）：essential 治疗（抗生素、支持治疗）由**指南**判定；case-specific 治疗（阑尾切除等）是否"适用于该患者"由**患者实际接受的手术**锚定。这实际上承认了纯规范性判定的困难，用行为做了代理。
- **传统推荐评测**（SafeDrug/GAMENet）：药物 gold = 当次就诊处方集（prescriptions 行为）。
- **Ayre 2024**：出院带药 gold = 出院小结文本（文书内容行为）。
- **选择依据小结**：考"开立决策"用 POE（决策意图，时间即开立时刻）；考"出院用药方案"用 prescriptions + 出院小结带药段；考"实际用药"用 eMAR（可识别 held/refused）；考"手术/操作"用 procedures_icd + 出院小结文本（MIMIC-CDM 先例）。**eMAR 与 POE 的分歧本身可作为题目素材**（开了没给 = 临床理由或系统事件，需专家裁定）。【推断：MIMIC-IV v3.1 的 poe/emar 覆盖率有限（约 2014 年后数据），治疗维需先做每表覆盖率审计再定规模——文档层面成立，具体比例未核实】

#### 2.2.2 规范性轨道

工具箱适配（详见 §一）：MAI（逐药适当性 rubric）、Beers/STOPP/START（≥65 岁负面/遗漏清单，可半自动）、SEP-1/SSC bundle（急症可自动判）、NCCN concordance 方法学（时间窗+分期模板）、Choosing Wisely（过度治疗素材）。专家裁定证据包最低配置：**指南版本号 + 病例锚点（分期/严重度）+ 决策时点快照 + 既往治疗与禁忌证据（过敏/肾肝功能/合并用药）+ 当地路径（香港阶段替换为 HA 路径）**。MIMIC 缺结构化过敏表（Ayers 等需从文本抽取）——禁忌证据主要靠 notes，专家裁定时必须提供原始 note 段落。【推断：无过敏/禁忌证据的病例不能出"为什么没开 X"类规范性题目】

#### 2.2.3 两轨陷阱（文献证据）

1. **行为 gold 把不合规当正确**：SEP-1 全美合规率仅约 50%（§2.1.4）——若用 EHR 实际事件当 gold，一半的 sepsis 病例"正确答案"本身不合规。
2. **行为 gold 无法计漏开**：SafeDrug 家族与 CliBench 均只对"已开立"打分；START 类遗漏只能靠规范性轨道（§1.3）。
3. **治疗受禁忌/偏好/阶段影响**：MIMIC-CDM 原文发现 LLM"drastically undertreat appendicitis with regard to the necessity of antibiotics and providing support, undertreat diverticulitis with the need for a colonoscopy in the future… undertreat pancreatitis with sufficient support"且"especially for patients with more severe forms"——重症患者的规范性治疗更复杂；反向地，NCCN concordance 研究显示 22%-92% 的巨大定义敏感性（§1.5），说明"该做什么"本身依赖操作化。
4. **编码 gold 的粒度陷阱**：CliBench prescriptions ATC L4 F1 只有 45-47（§2.3），说明即使行为 gold 也难"对齐"——自由文本答案 vs 编码 gold 的映射损失是评测噪声源。
5. **文书 gold 含错误**：Ayre 2024 中原文书自身即含剂量错误（carbamazepine 例），以文书为 gold 会把文书错误法定为正确（§4.3）。

#### 2.2.4 推荐 gold 方案（治疗处置）

- **标签定义**：双轨并行、分开报告。行为轨按事件类型分层：T1 处方/医嘱（POE+prescriptions）、T2 给药执行（eMAR）、T3 手术/操作（procedures_icd+出院小结文本）。规范性轨按工具分层：N1 bundle/指南 essential（可自动）、N2 清单命中（Beers/STOPP/START，半自动）、N3 逐药/逐案专家裁定（MAI rubric，双人）。
- **时间窗**：决策时点=接诊/分诊后 X 小时或关键事件（如培养回报）后；gold 事件窗=决策时点至出院+72h；**禁止把出院后复诊的处方调整计入**。MIMIC-CDM"住院 <1 天限制"（Gaber 引用）与 OCCPI"≤60 天"是两个极端先例，我们取"单次就诊内+出院带药"。
- **排除规则**：入院前已在用的长期药（需区分"继续"与"新开"，MIMIC-CDM treatment 任务同样区分 init/discontinue）；无禁忌证据（过敏/肾肝功能缺失）病例不做规范性"为什么没开"题；<18 岁、住院 <4h、HT（hospice/comfort care only）患者排除规范性轨。
- **人工审核**：N3 全部双人+仲裁；N1/N2 抽 10% 复核；行为轨抽 5% 验证抽取正确性。
- **文献直接支持**：MIMIC-CDM 的 procedures 双源抽取与 essential/case-specific 混合判定；SEP-1 的元素级判定；OCCPI 的 major/minor 分层与时间窗；MAI 双人 κ 数字（0.83 药师-医师 / 0.59 药师-药师）做人力预算。
- **【推断】**：POE 开立 vs eMAR 执行的分歧审查流程；ATC 粒度选择（L4 为默认判定粒度）。

### 2.3 关键图表深析（任务四）

#### 2.3.1 CliBench（arXiv 2406.09923）——治疗相关任务的 gold 构成与结果

**Table 2（原文转录）**：[Tasks and gold 构成](https://arxiv.org/html/2406.09923v1)：

| Task | Evaluation Cases | Description | Formulation | Gold Annotation |
| --- | --- | --- | --- | --- |
| Discharge Diagnosis | 1,000 | first ICD-10-CM codes from discharge summaries | generation | billing ICD-10-CM codes |
| Procedures | 1,000 | procedures within 24 hours of admission | generation | billing ICD-10-PCS codes |
| Lab Test Orders | 1,000 | lab orders within 24 hours of admission | generation | LOINC codes |
| Prescriptions | 1,000 | medication prescriptions within 24 hours of admission | generation | ATC codes |
| Drug Choice (Yes/No) | 1,000 | binary efficacy check of golden drugs | boolean | golden drugs = all medicines prescribed to the patient |
| Drug Tests (Yes/No) | 1,000 | binary safety check of golden drugs | boolean | "Do the golden drugs pose potential risks to patients?" |

**Table 4（原文转录）**：Procedure / Lab Test / Prescription 三任务在 ATC/LOINC/ICD-10 各编码层级的 F1：

| Model | Procedure L1 | Procedure L2 | Procedure L3 | Procedure Full | Lab Order L1 | Lab Order L4 | Prescription ATC L1 | Prescription ATC L4 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GPT-3.5 | 30.22 | 24.59 | 12.62 | 0.85 | 99.86 | 16.34 | 74.83 | 43.47 |
| GPT-4 | 36.33 | 28.16 | 10.32 | 1.45 | 99.86 | 17.95 | 78.25 | 47.44 |
| GPT-4o | 33.93 | 27.28 | 10.63 | 0.67 | 99.86 | 17.18 | 77.09 | 47.42 |
| LLaMA3 8B | 31.61 | 25.67 | 12.98 | 1.57 | 99.82 | 15.16 | 73.05 | 41.99 |
| LLaMA3 70B | 31.71 | 25.30 | 12.35 | 1.57 | 99.86 | 16.71 | 78.07 | 45.22 |
| Mixtral 8×7B | 31.49 | 24.15 | 13.50 | 1.61 | 99.80 | 15.76 | 72.91 | 43.21 |

**深入分析**：

1. **"第一批决策"gold 的结构脆弱性**：procedures/lab/prescriptions 的 gold 都是"入院 24h 内同批时间戳的 orders"——这是一个**时间结构性近似**：不问"该不该开"，只问"医生第一批开了什么"。对 MCQ 评测的直接含义：这类 gold 只能考"复现惯例"，不能考"正确决策"；我们的题目若照搬此构造，测的是 LLM 拟合行为分布的能力（与构念效度批评一致）。
2. **编码层级敏感到荒谬**：Prescription ATC L1 F1 ≈ 73-78，L4 掉到 42-47；Procedure full code F1 ≈ 0.67-1.61（近乎全错）。**同一行为 gold，换编码粒度结论天差地别**——我们的 MCQ 必须预先声明判定粒度（药名级？类级？剂量级？），并报告粒度敏感性。CliBench 的 Lab L1=99.86 更极端：L1 只有 2 个候选（几十个具体检验的顶层），几乎免费得分——**层级化指标里"简单层"毫无区分度**。
3. **Drug Tests 任务的 gold 是"golden drugs 是否有风险"**——把安全性问题退化为给定药物组合的二元判断（DDI 检测），且 gold 由问题构造给出而非专家判定；这是"规范性问题用玩具化行为 gold 替代"的样本，不应效仿。
4. **"Drug Choice"任务的循环性**：gold = "该患者实际被开的所有药"，问"此药是否有效"——行为 gold 被当作疗效证据。我们设计治疗 MCQ 时必须避免"因为开了所以是对的"的循环。
5. **数据泄漏与 split 的自曝**：作者承认 MIMIC 公开数据可能进入预训练，且 train/eval 只按 admissions 划分、患者级有少量重叠——**我们坚持患者级 split + 污染探针（n-gram/语义检索）是对此的直接修正**。
6. **对维度拆分的含义**：CliBench 把 procedures 与 prescriptions 分开任务是正确的（临床决策语义不同：手术决策 vs 用药决策）；但其 gold 同为"24h 首批"，说明**事件类型分层（T1/T2/T3）比时间窗更能区分维度**。

#### 2.3.2 NCCN concordance 实战样本：OCCPI 结直肠癌研究（PMC11745911）

**主结果（原文数字转录）**：16 医院、2011-2021、n=2,324（结肠 1,585 / 直肠 739；排除 IV 期、>85 岁、拒治、信息缺失）：

| 分层 | 数字（原文照抄） |
| --- | --- |
| 完全 concordant | 24.7% (n=573) |
| 仅 Minor 不 concordant | 63.3% (n=1,471) |
| Major 不 concordant | 12.4% (n=280)（注：280/2324=12.05%，原文百分比与 n 之间存在舍入不一致，照抄并加注） |
| Major 不 concordant 按部位 | 结肠 7.6% / 直肠 21.5% |
| Major 不 concordant 按分期 | I 期 14.6% (41) / II 期 24.3% (68) / III 期 61.1% (171) |
| 结肠最常见 Major 偏差 | III 期未接受化疗 29.3% (n=82) |
| 直肠最常见 Major 偏差 | ≥2 项主要治疗不 concordant 24.3% (n=68) |
| 诊断→治疗 >60 天 | Major 不 concordant 组 22.9% vs 全体 10.2% |
| 结肠 Major 不 concordant 多因素 OR | II 期 3.10 (1.21–7.96)；III 期 22.07 (9.43–51.70)；Charlson-Deyo>1 1.66 (1.05–2.64)；>60 天 3.04 (1.58–5.85)；>1 家医院网络 0.47 (0.24–0.91) |
| 直肠 Major 不 concordant 多因素 OR | >60 天 2.73 (1.76–4.22)；>1 设施 0.49 (0.31–0.77) |

**深入分析**：

1. **行为与规范的偏离率本身就是分层证据**：只有 24.7% 完全合规——若用行为 gold 出题，约 3/4 病例至少在 minor 层面"答案不合规"；Major 层面 12.4%（直肠高达 21.5%）。**治疗维的"行为 gold 陷阱率"第一次有了可引用的具体分布**（肿瘤场景）。
2. **major/minor 分层设计可直接移植**：major=治疗方式组合（手术/化疗/放疗），minor=检查与文书（CEA、MSI、切缘、淋巴结数）——恰好对应我们的治疗维与检查维的边界；把 minor 错误计入治疗题会污染维度拆分。
3. **时间窗是规范性判定的核心参数**：>60 天治疗延迟与 Major 不合规强相关（OR 3.04/2.73）——MCQ 的时间窗选择（我们的"决策时点→gold 事件窗"）不是技术细节而是效度变量。
4. **registry-based 裁定的天花板被作者自曝**："it may be difficult to understand the exact reason that a patient received guideline non-concordant care from registry data"——**没有 notes 的行为数据解释不了"为什么没做"**（禁忌？患者拒绝？转诊丢失？）。我们的优势（有全量 notes）应转化为裁定证据包的一部分，这正是行为轨无法单独回答的问题。
5. **III 期结肠癌 OR 22.07 的阶段效应**：分期锚点错误会让 concordance 判定全错——规范性 gold 必须锁定"判定所依据的分期/严重度来自决策时点之前的信息"，否则又是未来信息泄漏（III 期由术后病理确定，而化疗决策在术后——这类循环在肿瘤 concordance 研究里普遍存在）。
6. **跨体系警示**：OCCPI 是美国 16 医院系统；香港 HA 肿瘤路径与转诊时限不同（如肠癌化疗启动时限、直肠癌新辅助指征差异），concordance 百分比不可直接搬，但 major/minor+时间窗的**判定架构**可复用。

#### 2.3.3 MIMIC-CDM 治疗任务结果（Nat Med 2024，已核原文）

原文以图 4 报告治疗建议（非表格）：例如 957 例阑尾炎中 808 例实际接受阑尾切除；Chat 类模型在正确诊断的 603 例中 97.5% 正确推荐阑尾切除；而对抗生素+支持治疗、 diverticulitis 后结肠镜（随访维！）、感染性胰腺坏死引流、穿孔性憩室炎结肠切除等场景显著**治疗不足**，且重症患者更差。**含义**：对"高共识、高发生率"的治疗（阑尾切除）行为 gold≈规范 gold；对"低共识、情境依赖"的治疗两者分叉——MCQ 应优先在高共识区出行为 gold 题、在低共识区做专家双轨题。

## 三、转诊与科室选择维度

### 3.1 现有评测体系（任务一）

**已定位（一句话，不重复综述）**：[MIMIC-CDM](https://www.nature.com/articles/s41591-024-03097-1)（Nat Med 2024）treatment management 任务族中的 **referral 任务**（模型判断是否需要专科转诊及转哪科，gold 来自后续实际发生的专科参与）——内部材料与姐妹笔记已综述，此处仅定位。

**新发现/深读的评测体系**：

#### 3.1.1 Gaber et al. 2025, npj Digital Medicine —— LLM 临床决策工作流 benchmark（triage + 转诊专科 + 诊断）

- **出处**：[Evaluating large language model workflows in clinical decision support for triage and referral and diagnosis](https://www.nature.com/articles/s41746-025-01684-1), npj Digit Med 8 (2025)，doi:10.1038/s41746-025-01684-1。
- **数据来源**：MIMIC-IV-ED v2.2 + MIMIC-IV-Note（出院小结中抽取 HPI 段落与主要诊断列表）， curated 2,000 例；排除死亡病例、缺失 triage、重复 stay、HPI 长度 <50 或 >2000 字符、>15 个主要诊断的病例。
- **任务设定**：两种用户场景——general user（仅症状+人口学，模拟患者居家自评）与 clinical user（加 triage 生命体征），让 LLM 预测：(a) ESI triage 级别；(b) top-3 转诊专科；(c) top-3 诊断。模型为 Claude 3.5 Sonnet / Claude 3 Sonnet / Claude 3 Haiku + RAG-assisted Claude 3.5 Sonnet（3000 万 PubMed 摘要知识库）。
- **gold 构建（关键）**：triage gold = MIMIC-IV-ED triage 表中分诊护士记录的 ESI（**行为 gold，单一护士的现场判断**）；**专科 gold = 用 Claude 3.5 Sonnet 把出院主要诊断映射到"最可能负责的专科"生成**（数据集无真实转诊记录可用），再由 4 名临床医生抽 400 例审查；诊断 gold = 出院主要诊断列表，用 Claude 3.5 Sonnet 当 LLM judge 判定预测与 gold 的语义等价，同样有 4 名临床医生子集校验。
- **指标**：ESI exact match 与 "range" 准确率（预测恰好高一级也算对、ESI 1 必须精确命中——只容忍过度分诊不容忍漏分诊的非对称计分）；专科 matched（按较短列表长度归一）与 "at least one"；诊断 matched / at least one；另有 inter-model agreement。
- **规模**：2,000 例；临床医生校验 400 例（两对各审 200 例）。
- **访问**：数据集"curated 非公开"（作者以此论证抗污染），未随文发布；只有论文与补充材料。
- **局限**（对 gold 设计最重要）：专科 gold 是 LLM 生成的映射而非真实转诊行为，存在自我同源（生成 gold 与被评模型同家族）；ESI gold 是单人行为判定；HPI 取自出院小结而非分诊时刻文书，作者自己承认引入偏倚；ESI 分布重度失衡（几乎全是 2-3 级，无 5 级）。

#### 3.1.2 ESI 作为 gold 的效度/信度证据（非 benchmark，但决定 triage gold 可用性）

- **Meta-analysis**：[Reliability of the Emergency Severity Index: meta-analysis](https://pmc.ncbi.nlm.nih.gov/articles/PMC4318610/)（Ann Emerg Med 2015 系）。**ESI 评分者间合并系数 0.791**（正文 CI 0.752–0.825）；最新版 ESI 0.833 vs 旧版 0.808；成人 0.815 vs 儿童 0.769；**评分者内 0.873 > 评分者间 0.786；护士-专家间只有 0.732，专家-专家 0.900**。六项有列联表的研究合并原始一致率 78.55%，其中各级别贡献（1-5 级）分别为 1.12% / 23.40% / 19.55% / 18.81% / 15.67%（合计 78.55%），~80% 的分歧发生在 3-5 级。
- **情景准确率研究**：Ann Emerg Med 2016（35 名 ED 护士）总体 triage 准确率 58.7%、under-triage 28.8%、over-triage 12.3%；Ann Emerg Med 2017（3 国 87 名受训护士，标准情景）平均准确率 59.2%（[2016 文献页](https://www.annemergmed.com/article/S0196-0644%2816%2930636-9/fulltext)、[2017 文献页](https://www.ovid.com/journals/aemmed/fulltext/10.1016/j.annemergmed.2017.09.036)，数字来自检索快照，未逐字核对正文）。
- **2025 系统综述**：ESI 对死亡/ICU 收入等结局有强预测效度（[Systematic review 2025](https://www.sciencedirect.com/science/article/pii/S2211419X25000825)）。
- **含义**：ESI 这个"行为 gold"本身的评分者间天花板约 κ0.79、真实情景准确率 ~59%——**护士敲定的 ESI 只能当"参考行为"，不能当规范性真值**；MCQ 里相邻级别的干扰项设计必须与此相容（见 3.3 分析 1）。

#### 3.1.3 转诊适当性评价研究（规范性 gold 的专家小组先例）

- **影像/专科转诊适当性**：Lehnert & Bree 分析初级保健门诊 CT/MRI，**26% 不适当**（被后续大量 stewardship 文献引用）；Krogh et al. 2022：**75.5% 的 GP 腰椎 MRI 转诊不符合 ACR appropriateness criteria**；Venturelli et al. 2021：**37% 转诊单被判定不适当**（胃镜与 CT 最差，[PMC7847028](https://pmc.ncbi.nlm.nih.gov/articles/PMC7847028/)）。急诊转诊适当性：[Anwar et al. 2024](https://pmc.ncbi.nlm.nih.gov/articles/PMC10906761/)（定义"错误分级为急诊/未转对科/未按紧急度"为不适当）。
- **专科转诊预测（行为预测非规范）**：Abdalla et al. 2022 [Predicting the target specialty of referral notes](https://pmc.ncbi.nlm.nih.gov/articles/PMC9098074/)（logistic regression 标注转诊单目标专科）；Moreno-Sánchez et al. 2024（ED triage 时预测住院与所需专科，[SAGE](https://journals.sagepub.com/doi/10.1177/20552076241264194)）。
- **含义**：(a) "转诊是否适当"在文献里一贯由**显式标准（ACR 类）或专家小组**裁定，不适当率随模态在 26%-75% 间摆动——转诊维两轨的偏离幅度与治疗维相当；(b) **不存在国际通用的"转诊适当性量表"**，工具箱在转诊维是空缺的（§1.7 结论）。

### 3.2 gold 方案分析（任务三）

#### 3.2.1 行为轨道：services vs transfers vs consults 的选择

MIMIC-IV v3.1 相关表（[官方文档](https://mimic.mit.edu/docs/iv/modules/hosp/)）：[services](https://mimic.mit.edu/docs/iv/modules/hosp/services/)（患者当前由哪个专科团队**负责**，按 hospital admission 记录，含 curr_service/prev_service）、[transfers](https://mimic.mit.edu/docs/iv/modules/icu/transfers/)（ICU 及普通病房的**物理床位移动**事件流）、ED 的 triage 表（ESI）；consult 医嘱藏在 poe 表 ordercategory='Consult'（文档口径）。

- **考"该找谁"** → services（负责团队变更=R1）与 consult 医嘱（R2，会诊请求=转诊决策的直接行为痕迹）；**考"该去哪"**（床位/监护级别）→ transfers（R3，含 ward↔ICU 方向）。
- **文献先例**：Gaber et al.（§3.1.1）因数据集中无真实转诊事件而被迫用 LLM 造专科 gold——这是**反面先例**；我们的数据里有 services/poe-consults/transfers，应直接用真实事件。MIMIC-CDM referral 任务以"后续实际发生的专科参与"为 gold（姐妹笔记已深读）。
- **【推断】**：ED 场景首选 R2（consult 医嘱，时点=开立时刻，天然是"决策"）；住院场景首选 R1（services 变更）；transfers 混杂床位管理因素（感染控制、容量），作 gold 噪声大，只作辅助特征。

#### 3.2.2 规范性轨道

工具箱空缺（§1.7）：转诊维没有 MAI/Beers 级别的工具。可用替代：(a) **指南内嵌的转诊指征**（如 sepsis→ICU、STEMI→PCI 中心、创伤分级标准；Gaber 引用的 ACS field triage ≤5% under-triage/≤35% over-triage 目标是少数有量化阈值的）；(b) **ACR appropriateness criteria 类显式标准**（影像转诊）；(c) **本地路径**（香港 HA 的专科门诊转介指引/急症分流协议）。专家裁定证据包：转诊时点快照 + 请求方角色（GP/ED/病房）+ 被转科室的本地可得性说明（美国单中心的科室结构与 HA 不同——**美国"该转的科"在香港可能不存在或名称不同**，这是香港适配的核心风险点）。

#### 3.2.3 两轨陷阱（文献证据）

1. **LLM 造 gold 的失败模式已被量化**：Gaber Table 4——医生对 LLM 生成专科 gold 的"彻底错误"率 0-9.15%（均 2.63%），Accurate 率医生间 68.94%-93.77%（§3.3）。
2. **ESI 行为 gold 的天花板**：κ≈0.79、情景准确率 ~59%（§3.1.2）——任何把护士 ESI 当唯一真值的评测都被这个噪声下界锁死。
3. **多专科合理性是常态**：Gaber "at least one" 比 "matched" 高 ~10pp（§3.3 分析 3）——单一正确答案在转诊维天然稀缺，必须做唯一性工程。
4. **时点错位**：用出院文书信息考分诊时刻决策（Gaber 自认的偏倚）；转诊决定常在检查结果回报前做出，gold 若用"最终诊断对应的专科"会把"先转错再纠正"的流程污染进来。

#### 3.2.4 推荐 gold 方案（转诊与科室选择）

- **标签定义**：行为轨三层——R1 services 团队变更（科室名规范化到受控词表）、R2 poe consult 医嘱、R3 transfers 床位事件（方向：普通↔ICU）。规范性轨分两类——N1 显式指征命中（指南转诊指征，如脓毒症→ICU、STEMI→导管室；可半自动）；N2 专家裁定（"该不该转/转哪个科/多急"），双人+仲裁，判定表含"转诊必要性/目标科室/紧急度"三个轴。
- **时间窗**：决策时点=ED 到达/评估完成/关键检查回报；gold 事件窗=决策时点至本次住院结束（services 变更）或出院后 30 天（门诊转介，若数据支持；MIMIC 不含出院后门诊数据——**门诊转介 gold 在 MIMIC 内不可得，只能考住院内会诊与 ED 转科**）。
- **排除规则**：多专科并列负责病例做唯一性过滤后才可入 MCQ； transfers 中因感染控制/容量的移动标记为噪声排除【推断：需 review note 抽样确认移动原因】；入院时已由外院转诊入院（转诊决策发生在院外）排除。
- **人工审核**：所有 MCQ 化转诊题需专家确认"选项间互斥"（Gaber 数据说明多专科合理性高达 ~10pp 差距）；N2 双人 κ 预算参照 MAI 0.59-0.83 经验。
- **文献直接支持**：Gaber（专科 gold 风险量化）、ESI meta（噪声下界）、ACR/转诊适当性研究（专家裁定先例）、MIMIC-CDM referral（真实事件 gold 先例）。
- **【推断】**：R2 consult 医嘱优先级、门诊转介不可得需在香港 RWD 阶段才能补（HA 有 SOPC 转介数据）。

### 3.3 关键图表深析（任务四）：Gaber et al. 2025

**Table 1（原文转录）**：[Model performance comparison across tasks and evaluation methods](https://www.nature.com/articles/s41746-025-01684-1/tables/1)，单位为准确率 [%]：

| User setting | Model | Triage exact | Triage range | Specialty matched | Specialty ≥1 | Dx matched | Dx ≥1 | Average |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| General User | RAG-Assisted LLM | **64.10** | 78.20 | 77.12 | 86.35 | 69.43 | 80.85 | 76.01 |
| General User | Claude 3.5 Sonnet | 62.20 | **82.80** | **78.26** | **88.05** | **70.22** | **82.00** | **77.26** |
| General User | Claude 3 Sonnet | 58.35 | 74.40 | 78.10 | 87.70 | 70.17 | 81.55 | 75.05 |
| General User | Claude 3 Haiku | 57.70 | 71.80 | 77.86 | 87.10 | 67.39 | 79.60 | 73.58 |
| Clinical User | RAG-Assisted LLM | **65.75** | 77.15 | 77.28 | 86.45 | 69.77 | 81.70 | 76.35 |
| Clinical User | Claude 3.5 Sonnet | 64.40 | **82.40** | **78.86** | **88.55** | 70.26 | **82.10** | **77.76** |
| Clinical User | Claude 3 Sonnet | 61.65 | 74.55 | 77.72 | 87.15 | **70.51** | 82.05 | 75.61 |
| Clinical User | Claude 3 Haiku | 59.00 | 66.15 | 78.02 | 87.05 | 67.46 | 79.30 | 72.83 |

**Table 2（原文转录）**：[Clinical vs. general user settings](https://www.nature.com/articles/s41746-025-01684-1/tables/2)，从 general 到 clinical（加生命体征）的性能变化（百分点）：

| Model | Triage exact | Triage range | Specialty matched | Specialty ≥1 | Dx matched | Dx ≥1 | Average |
| --- | --- | --- | --- | --- | --- | --- | --- |
| RAG-Assisted LLM | 1.65 | −1.05 | 0.16 | 0.10 | 0.34 | 0.85 | 0.34 |
| Claude 3.5 Sonnet | 2.20 | −0.40 | 0.60 | 0.50 | 0.04 | 0.10 | 0.51 |
| Claude 3 Sonnet | 3.30 | 0.15 | −0.38 | −0.55 | 0.34 | 0.50 | 0.56 |
| Claude 3 Haiku | 1.30 | −5.65 | 0.16 | −0.05 | 0.07 | −0.30 | −0.75 |

**Table 4（原文转录）**：[Clinician validation of LLM-generated specialties](https://www.nature.com/articles/s41746-025-01684-1/tables/4)——4 名临床医生审查 LLM 生成的专科 gold：

| Clinician | Accurate [%] | Acceptable [%] | Accurate & Acceptable [%] | Error Rate [%] |
| --- | --- | --- | --- | --- |
| Clinician 1 | 93.77 | 6.23 | 100 | 0 |
| Clinician 2 | 82.05 | 8.79 | 90.84 | 9.15 |
| Clinician 3 | 81.91 | 17.06 | 98.98 | 1.02 |
| Clinician 4 | 68.94 | 30.34 | 98.98 | 1.02 |
| **Average** | **81.5** | **15.53** | **97.03** | **2.63** |

（正文另报：诊断评价中 LLM judge 与临床医生的"union"一致率 Claude 3.5 Sonnet 95.62% / RAG 94.91%，"intersection"（双医生一致才算对）降到 70.74% / 69.86%；单个临床医生与 LLM 的一致率范围 76%–90%。）

**深入分析（对 gold / 题目 / 维度拆分的直接含义）**：

1. **ESI 的 range 计分本身就是一个"规范性叠加层"**：exact match 用的是行为 gold（分诊护士敲定的 ESI），而 "允许高一级算对、ESI 1 必须精确" 的规则是作者叠加的规范选择（宁可过度分诊不可漏诊，呼应创伤系统 ≤5% under-triage / ≤35% over-triage 目标）。对我们：ED triage MCQ 若以护士 ESI 为 gold，相邻级别的干扰项不能被当作"明确错误"，除非另做专家裁定；或直接采用"非对称部分分"设计。
2. **专科 gold 是 LLM 生成而非 EHR 行为，且与被评模型同家族**——这是转诊维度最典型的两轨混淆样本。Table 4 显示四位医生对同一批 gold 的 "Accurate" 从 68.94% 到 93.77%，最严格的医生给出 9.15% 的彻底错误率；论文用平均 97.03% "准确或可接受"掩盖了这一分歧幅度。**结论：我们的转诊 gold 必须来自 services/consults 等真实事件（行为轨），规范性裁定交给本地专家+路径，绝不用 LLM 映射诊断→专科来造 gold。**
3. **"at least one specialty" 与 "matched" 差约 10 个百分点**（86–89% vs 77–79%）——同一病例多个专科都合理是常态（作者也承认单一诊断常可由多专科管理）。对 MCQ：转诊题要么改为"最应优先转诊/会诊的科室"并做唯一性过滤，要么把多专科均可的病例排除/改写成多选题，否则 gold 不唯一。
4. **Table 2 的信息效应不对称**：加生命体征使 triage exact +1.3~+3.3pp，但 triage range 多数模型反而下降（Haiku −5.65），专科任务甚至出现负增益（Claude 3 Sonnet −0.38/−0.55）。信息越多未必单调变好，尤其对序数/安全类任务——支持我们"决策时点快照 + 按维度定制信息集"的设计，而不是一股脑给全量表。
5. **gold 的时点错位**：HPI 抽自出院小结（回顾性文书），而 ESI 是分诊时刻做的决定；作者明确承认这引入偏倚。我们的 ED 转诊/triage 题应使用分诊时刻可得的 chief complaint/ED note，而非出院 HPI——这是与 Gaber 设计的关键差异点，也直接影响未来信息泄漏。
6. **类别失衡**：数据几乎全为 ESI 2–3 级、无 5 级，accuracy 被多数类主导；混淆矩阵显示极端级别（1 级、4 级）最差，但没有 1↔4/5 级的致命混淆。MCQ 抽样需按 ESI 级别分层，并单独报告 I 级（需立即干预）病例的子集表现。
7. **诊断 gold 的"intersection"陷阱**：LLM judge 与双医生一致的符合率只有 ~70%，说明"诊断正确"的判定本身在专家间只有中等共识——支持姐妹笔记的结论（诊断维度 gold 用 MCQ 缩小判定空间），同样提示我们转诊/治疗维的判定词表要预先离散化。
8. **诊断任务被限制在住院 <1 天的病例**以避免"住院后期才出现的诊断"污染——这是我们"决策时点快照 + 排除规则"可直接引用的先例（同维度思路：gold 事件必须落在决策窗内）。

## 四、离院指导与随访维度

### 4.1 现有评测体系（任务一）

**已定位（一句话）**：[MIMIC-CDM](https://www.nature.com/articles/s41591-024-03097-1) transitions of care 任务（disposition + 随访时间）、[Ayre et al. npj DM 2024](https://www.nature.com/articles/s41746-024-01336-w) 已在内部材料综述；本节深读 Ayre 表格并补检索。

**新发现/深读的评测体系**：

#### 4.1.1 Stanceski/Ayre et al. 2024, npj Digital Medicine —— AI 出院指导安全性评价（深读）

- **出处**：[The quality and safety of using generative AI to produce patient-centred discharge instructions](https://www.nature.com/articles/s41746-024-01336-w), npj Digit Med 7:329（2024-11-20，Brief Communication）。
- **数据来源**：MIMIC-IV v2.2 出院小结随机抽样 100 份（另有 10 份用于 prompt 开发），仅英文、存活出院；**未使用** MIMIC 其他表格数据。
- **任务设定**：GPT-3.5-turbo-16k 基于整份出院小结生成患者版出院指导（用药+随访动作），三位 prompt 策略中选 "direct"；医生/药师双人独立比对 AI 输出 vs 原文书。
- **gold 构建（关键）**：**以原文书（医生写的出院小结）为参照的行为 gold**——"正确"被定义为忠实转录原文书的用药/动作（剂量、途径、频次、疗程），另设安全性判定（omission / commission / hallucination 的新增内容、严重度、来源）由医生组讨论裁定。注意：这里的行为 gold 是"文书里写了什么"，**不是"患者应该被交代什么"（规范性 gold）**。
- **指标**：完整性（all included）、无添加（no additional）、正确百分比、UMS 格式比例；安全性问题率（可归因于 AI 的潜在有害问题 18%，其中幻觉 6%、新增药物 3%；较轻问题 28%）；inter-rater kappa。
- **规模**：100 例；双人评分（医学/药学背景），分歧组内讨论。
- **访问**：补充材料提供所用出院小结的 MIMIC note_id（可复现）。
- **局限**：单中心 MIMIC、GPT-3.5 旧模型、100 例小样本；以原文书为参照意味着"原文书本身有错/缺"无法被发现（作者也承认评估受限于此）。

#### 4.1.2 出院小结质量构成清单（Wimsett et al. 系统综述）

- **出处**：Wimsett J, Harper A, Jones P. Review article: components of a good quality discharge summary: a systematic review. Emerg Med Australas. 2014;26(5):430-438（[PubMed 检索定位](https://pubmed.ncbi.nlm.nih.gov/?term=Wimsett+components+of+a+good+quality+discharge+summary)；经 Ayre 2024 参考文献核实存在）。
- **用途**：给出"高质量出院小结应包含什么"的条目构成（主诉/诊断/检查/治疗/随访安排等），可作为**随访维规范性 gold 的条目清单来源**（专家打分表的底稿）。
- **局限**：条目级 checklist，不是心理测量学量表，无总分截断。

#### 4.1.3 出院信"成功/不成功"的医生判定研究（Weetman et al. 2021）

- **出处**：Weetman K, et al. [What makes a "successful" or "unsuccessful" discharge letter? Hospital clinician and General Practitioner assessments of the quality of discharge letters](https://bmchealthservicesresearch.biomedcentral.com/articles/10.1186/s12913-021-06345-z). BMC Health Serv Res. 2021;21:349（经 Ayre 2024 参考文献核实）。
- **用途**：证明"出院文书质量"的判定者间差异与要素权重（临床医生 vs GP 视角不同）——对随访维 gold 的含义：规范性裁定必须固定判定者角色与视角。

#### 4.1.4 出院用药重整（MedRec）评价研究（行为-规范分歧的核心证据）

- **出处**：Michaelsen MH, et al. [Systematic review of medication reconciliation at discharge](https://pmc.ncbi.nlm.nih.gov/articles/PMC5597088/)（2015，J Clin Pharm Ther 系）；[Prevalence and severity of discharge medication discrepancies](https://accpjournals.onlinelibrary.wiley.com/doi/10.1002/jac5.1737)（JACcP）；[AHRQ MedRec Primer](https://psnet.ahrq.gov/primer/medication-reconciliation)。
- **数字**：**约 41% 出院患者至少 1 项非故意用药不一致**（Michaelsen 系统综述，均值 1.2 项/人）；区间 40–50%（JACcP）；**omission（漏写）最常见**；≥10 种用药是主要风险因素。
- **对 gold 的含义**：出院文书（行为 gold）相对"真实用药清单"本身就有 ~40% 不一致率——文书 gold 是有噪底座的；MedRec 的"best possible medication history"方法（比对来源清单+访谈）就是随访维规范性裁定的现成方法学。

#### 4.1.5 随访间隔的规范性依据：surveillance interval 指南与依从性研究

- **出处**：结肠镜随访——US Multi-Society Task Force [共识更新](https://gastro.org/clinical-guidance/follow-up-after-colonoscopy-and-polypectomy-a-consensus-update-by-the-u-s-multi-society-task-force-on-colorectal-cancer/)；依从性：2019 系统综述/meta **指南推荐间隔依从仅 48.8% (95% CI 37.3%–60.4%)**（经 [ACG Evidence-Based GI 2024](https://gi.org/journals-publications/ebgi/zhou_nov2024/) 引用）；部分高质量场景 85–90%（[Menees et al. 2014](https://pmc.ncbi.nlm.nih.gov/articles/PMC4114302/)）；**过度（间隔过短）是不依从的主导形式**，医生理由：担心漏息肉 59%、检查便宜 26% 等（[Gut and Liver 2021](https://www.gutnliver.org/journal/view.html?doi=10.5009/gnl201666)，数字来自检索快照，未逐字核对全文）。
- **对 gold 的含义**：随访间隔有**量化级规范性标准**（3/5/10 年）且**实际行为只有 ~49% 依从**——这是随访维"行为 gold 大面积偏离规范"的最干净证据；间隔离散化（即刻/2 周/3 月/1 年/3-5 年）天然适合 MCQ。

### 4.2 gold 方案分析（任务三）

#### 4.2.1 行为轨道："文书内容 gold" vs "最佳随访 gold"的分裂

MIMIC 内随访相关信息只有两种形态：(a) **出院小结/出院指导文书**（discharge_summary 中的 follow-up 段、meds 段——"交代了什么"）；(b) **转诊/预约事件**（若有门诊预约记录——MIMIC 基本没有出院后门诊数据）。因此行为 gold 必须分两层定义：
- **F1 文书内容 gold**：出院文书实际写了什么（随访科室、时间窗、带药、警示症状）——这是 Ayre 2024 用的参照层（κ 用药 0.85+ / 随访动作 0.52-0.57，§4.3）。
- **F2 约定事件 gold**：实际发生的随访安排（appointments 表若覆盖；MIMIC-IV 无出院后门诊随访数据——**F2 在 MIMIC 内基本不可得**，只能靠 F1 文书转述）。
- **"最佳随访 gold"（规范性）**与 F1/F2 是**不同构念**：F1/F2 是"医院做了什么交代"，规范性是"该交代什么/该约多久"——Ayre 的 18% 有害率证明 AI 生成的"看起来更完整的交代"反而引入错误；MedRec 的 41% 不一致率证明文书本身偏离真实用药；surveillance 依从 48.8% 证明医生约定的间隔偏离指南。**三层（文书-真实-规范）两两都有 40-50% 级别的分歧**。

#### 4.2.2 规范性轨道

工具适配：surveillance interval 类指南（间隔离散化，可半自动，按病种锁定）；Wimsett 清单（条目级专家打分底稿）；MedRec 方法（best possible medication history 作为出院带药规范性比对的采集方法）；Beers/STOPP-START（出院带药的负面/遗漏判定，§一）。专家裁定证据包：出院时点诊断+治疗摘要+用药清单（含入院前用药以判"该停未停/该续未续"）+指南版本；**随访维没有通用量表，必须逐病种建间隔表**。

#### 4.2.3 两轨陷阱（文献证据）

1. **Ayre 18%**：生成"更好的出院指导"反而 18% 潜在有害（6% 幻觉、3% 新增药物）——随访维的自然语言生成题极其危险，MCQ 化是控险手段（§4.3）。
2. **文书-真实-规范三重分歧**：MedRec 41%、surveillance 48.8%（§4.1.4/4.1.5）。
3. **随访动作的专家间一致性最低**：κ 0.52-0.57（Ayre）vs 用药 0.85+——裁定人力成本最高。
4. **患者理解是第三层噪声**：出院指导仅 58% 患者正确复述（Hoek 1992 经 Ayre 引用）、22% 不理解用药——MCQ 评的是"交代内容"而非"患者理解"，构念要声明清楚。

#### 4.2.4 推荐 gold 方案（离院指导与随访）

- **标签定义**：F1 文书内容 gold 按 MCQ 离散化拆四个子轴——随访科室、随访时间窗（离散档：≤1 周 / 1-4 周 / 1-3 月 / 3-12 月 / 3-5 年）、出院带药变更（新开/停用/调整，锚 prescriptions+文书双源）、警示症状/返回指征（是否覆盖关键红旗）。规范性轨 N1：病种 surveillance 间隔表命中（可半自动）；N2：MedRec 式带药比对（入院前用药×出院带药，专家双人）；N3：Wimsett 条目完整性打分（抽样质量监测用，不作 MCQ gold）。
- **时间窗**：决策时点=出院医嘱签发时刻；gold 事件窗=本次住院末 24h 内的出院文书+出院带药处方；**禁止**用出院后事件（再入院等）做 gold（那是结局预测，不是指导质量）。
- **排除规则**：非存活出院、转院病例（随访责任移交）、文书无随访段病例（F1 缺失）；带药 ≥10 种病例标注多药风险层（MedRec 风险因素）。
- **人工审核**：F1 抽取验证 5%；N2 全部双人+仲裁；MCQ 化后每题需专家确认"干扰项无争议"（随访维 κ 最低，此环节不可省）。
- **文献直接支持**：Ayre（18%/κ 结构、以原文书为参照的方法）、Michaelsen（41% 噪底）、surveillance meta（48.8% 依从）、Wimsett/Weetman（清单与判定者差异）。
- **【推断】**：时间窗离散档位设计；香港阶段用 HA 出院信/药物清单重建 F1（结构不同，需重新验证抽取器）。

### 4.3 关键图表深析（任务四）：Stanceski/Ayre et al. 2024

**Table 1（原文转录）**：[Performance of the AI-generated patient discharge instructions](https://www.nature.com/articles/s41746-024-01336-w/tables/1)（N=100）：

| Measure | Result (N = 100) |
| --- | --- |
| Medications | |
| all medications were included in the response, % | 90 |
| no additional medications were included in the response, % | 97 |
| mean percentage of medications correct in the response, % (std) | 85% (25%) |
| percentage of medications that were correctly specified by type, dose, route, frequency and duration, median (IQR) | 100% (81–100%) |
| Follow-up actions | |
| all actions were included in the response, % | 50 |
| no additional actions were included in the response, % | 58 |
| mean percentage of actions that were correct in the response, % (std) | 78% (26%) |
| percentage of actions that were correctly specified, median (IQR) | 86% (67–100%) |

**正文安全性数字（原文转录）**：可归因于 AI 的潜在有害安全问题 **18% (18/100)**，其中幻觉 6%、新增药物 3%；较轻且不太可能致害的问题 28% (28/100)。原文实例：AI 输出 "Carbamazepine 400 mg: Take 2 tablets by mouth twice daily"，原文书为 "one 400 mg tablet twice daily"（剂量加倍错误）。**评分者间信度（正文转录）**：用药完整性 Cohen's κ=0.889、无新增用药 κ=0.852、UMS 格式 ICC=0.738；**随访动作**完整性 κ=0.521、无新增动作 κ=0.569、用药正确比例 ICC=0.438、动作正确比例 ICC=0.512。

**深入分析（对 gold / 题目 / 维度拆分的直接含义）**：

1. **"文书内容 gold"与"最佳随访 gold"的分裂在这张表上被量化**：用药维度的复制相对可靠（90% 完整、97% 无添加、κ 0.85+），但**随访动作维度只有 50% 完整、58% 无添加、κ 只有 0.52-0.57**——即连"原文书里写了哪些随访动作"这一行为 gold 的提取，专家间都只有中等一致。**含义：随访维 gold 若以文书内容为参照，必须双标注+仲裁，且应优先考离散 MCQ 化（随访科室/时间窗/是否需要）而非自由文本比对。**
2. **"新增动作"是随访维最大陷阱**：42% 的 AI 回答新增了原文书没有的随访动作。这些新增项很多可能临床上"更正确"（原文书漏写），但在该评价框架下被计为错误——这正是行为 gold 的天花板问题：**参照文书≠应做的事**。对我们的启示：随访 MCQ 的行为 gold 只能锚定"实际约定的随访（appointments/出院医嘱）"，规范性 gold 需另建。
3. **18% 有害率是"生成任务"的风险，不是"判别任务"的风险**——对 MCQ 评测的含义是反向的：它证明出院指导的内容空间里存在大量"看似合理实则有害"的选项素材（剂量加倍、幻觉药物、住院期用药误写入出院带药），**这些天然就是高质量干扰项的来源**。
4. **评分者信度随"规范性程度"升高而下降**：用药（规则性强）κ≈0.85-0.89；随访动作（依赖情境判断）κ≈0.52-0.57。这为三维难度排序提供依据：随访维的人工裁定成本最高、一致性最低。
5. **原文书为参照的单中心局限被作者点名**——香港出院文书结构不同（如 HA 出院信面向 GP），Ayre 的 checklist 不能直接搬，但"用药 vs 动作"的信度差结构大概率成立。
6. **UMS 格式只有 25% 可表达**：输出格式合规性是独立于正确性的测量轴——若我们的 MCQ 考"出院指导生成"，需把"内容正确"与"格式合规"拆成两个计分轴，避免混在一起。

## 五、三维对比小结

### 5.1 gold 可靠性/可自动化难度排序（从易到难：治疗 > 转诊 > 随访）

| 维度 | 行为 gold 数据源 | 规范性工具 | 行为-规范偏离基线 | 专家间一致 | 主要陷阱 |
| --- | --- | --- | --- | --- | --- |
| 治疗处置 | POE/prescriptions/eMAR/procedures 多源可交叉（§2.2.1） | 最成熟：MAI、Beers、STOPP/START、SEP-1/SSC、NCCN concordance 方法（§一） | sepsis bundle 合规仅 ~50%；肿瘤 Major 不合规 12.4%/minor 层 75% 不合规 | MAI κ 0.83（药师-医师）/0.59（药师-药师） | 行为 gold 把不合规当正确；漏开不计分；禁忌/偏好不可见 |
| 转诊与科室 | services/consults/transfers（真实事件存在） | **无国际量表**；指南转诊指征+本地路径（§3.2.2） | 影像/转诊不适当率 26%-75%；ESI κ≈0.79 天花板 | Gaber：LLM 生成专科 gold 医生"彻底错误"0-9.15% | LLM 造 gold（Gaber 反例）；多专科合理性 ~10pp；美国科室结构≠香港 |
| 离院随访 | 只剩出院文书（F1）；真实随访事件缺失 | 病种 surveillance 间隔表+MedRec 方法+清单（§4.2.2） | MedRec 41%；surveillance 依从 48.8%；AI 生成 18% 有害 | 随访动作 κ 0.52-0.57（最低） | 文书-真实-规范三层分裂；生成题高风险 |

**排序理由**：治疗维唯一存在"可自动判定的规范性 gold"（bundle 元素+显式清单），且行为 gold 多源可交叉验证；转诊维行为事件真实存在但规范性裁定完全依赖本地路径；随访维连行为 gold 都只有文书一层，且所有已知一致率数字都是三维最低。

### 5.2 人工成本（以双轨审核为口径）

- **治疗维**：N1/N2 可半自动（bundle、清单命中），N3 双人裁定（预算按 MAI 经验：跨专业 0.83、同专业跨个体 0.59 → **建议药师+医师配对**而非双药师）；行为轨抽 5%。
- **转诊维**：N2（该不该转/转哪科）无自动工具，全量双人+仲裁；MCQ 唯一性过滤是额外一道人工工序（Gaber 数据证明不能省）。
- **随访维**：κ 最低（0.52-0.57）→ 单题裁定轮次最多；N2 MedRec 式比对需先重建"入院前用药×出院带药"两份清单，采集成本前置。**单位题目人工成本：随访 > 转诊 > 治疗**。

### 5.3 香港适配风险

1. **转诊维风险最高**：MIMIC 的美国单中心服务路径（科室设置、会诊文化、ICU 收治习惯）与 HA 专科结构不同——**规范性 gold 必须整体重建**（以 HA 转介指引/急症分流协议替代美国指南条目），行为 gold 事件源也要换成 HA 转介/会诊记录；Gaber 式"LLM 把诊断映射到专科"的做法在跨体系场景绝对不可用。
2. **治疗维风险中等**：SSC bundle 等国际规范可直接换算，但药物目录/剂量规格（HA formulary）、老年用药清单（Beers 需映射）、肿瘤路径时限（OCCPI 的 60 天窗不可搬）需本地化；MAI 类隐式工具跨体系可用但 cost 条目要重校。
3. **随访维风险中等偏低但工作量前置**：HA 出院信结构（面向 GP）与美国 discharge summary 不同，F1 抽取器需重写并重验；surveillance 间隔表需换本地指南版本；**机会**：HA 有门诊（SOPC）预约与再入院数据，可补上 MIMIC 缺失的 F2（真实随访事件）——随访维在香港 RWD 阶段反而可能反超为数据最全的一维。

### 5.4 共同结构结论（三条）

1. **双轨并行、分开报告是三维共同要求**——行为轨全部存在 40-50% 级别的"行为≠规范"基线偏离（sepsis 50%、MedRec 41%、surveillance 48.8%、转诊适当性 26-75%），只报任一轨都会系统性误导。
2. **高共识区出行为题、低共识区出专家双轨题**——MIMIC-CDM 的 97.5%（阑尾切除推荐）与 Gaber 的 10pp（多专科）分别定义了两端；MCQ 题库应按"共识度"分层而非按维度一刀切。
3. **规范性裁定的证据包最小公分母**：指南版本+决策时点快照+既往治疗/禁忌证据+当地路径说明——四者缺一即退化为不可复核的"专家品味"（OCCPI registry 数据无法解释"为什么没做"的教训，§2.3.2）。
