# EHR 临床 LLM 评测 —— 领域全景分析

> 分析技能：`$sci-review-landscape`
> 文献池：Zotero「基于EHR评测」集合（3PHB664K），97 篇
> 全部来自 2026 年，全部期刊论文
> 生成日期：2026-08-06

---

## 1. 文献池画像

### 1.1 总数与类型分布

| 指标 | 数值 |
|---|---|
| 文献总数 | 97 |
| 期刊论文 journalArticle | 97（100%）|
| 会议论文 / 预印本 / 学位论文 | 0 |
| 数据来源 | Zotero 集合「基于EHR评测」（3PHB664K）|

### 1.2 年份分布

```
2026: 97  |||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||||
```

**100% 集中在 2026 年**。这是一个刚从 WoS/期刊检索获取的最新文献池，不存在历史纵深。无法从该文献池判断年份趋势——需与前一个文献池（289 篇，2010-2026 跨度）对照理解趋势。

### 1.3 期刊分布

| 排名 | 期刊 | 文献数 | IF |
|---|---|---|---|
| 1 | IEEE Access | 9 | 4.2 |
| 2 | Expert Systems with Applications | 7 | 9.4 |
| 3 | npj Digital Medicine | 5 | 18 |
| 4 | JAMIA | 4 | 7.1 |
| 4 | JAMIA Open | 4 | 4.7 |
| 6 | IEEE Trans. PAMI | 2 | 20.4 |
| 6 | JCO Clinical Cancer Informatics | 2 | 3.6 |
| 6 | Applied Sciences-Basel | 2 | 2.9 |
| 6 | Healthcare | 2 | 3.4 |
| 6 | JMIR | 2 | 8.2 |
| 6 | Scientific Data | 2 | 7.2 |
| 6 | Knowledge-Based Systems | 2 | 8 |
| 6 | Int. J. Medical Informatics | 2 | 5 |

65 个唯一期刊，Top 10 覆盖 40%（39/97）。比前一个文献池（132 种期刊，Top10 仅 11%）更集中，但仍属多元分布。

### 1.4 摘要覆盖率

| 指标 | 数值 |
|---|---|
| 有摘要 | 97 篇（100%）|
| 无摘要 | 0 |

**摘要覆盖率 100%**，远优于前一个文献池（62%）。主题聚类可靠性高。

### 1.5 影响因子分布

| IF 区间 | 文献数 | 占比 |
|---|---|---|
| 高 IF（>=10）| 15 | 15.5% |
| 中 IF（3-9.9）| 66 | 68.0% |
| 低 IF（<3）| 15 | 15.5% |
| 无 IF 数据 | 1 | 1.0% |

中科院分区：Z1（含 CCF）28 篇、Z2（含 CCF）23 篇、Z3（含 CCF）36 篇、Z4 8 篇。**83% 文献有明确分区数据**，文献质量可追溯性高。

### 1.6 关键信号

该文献池是 2026 年最新检索的 EHR 临床 LLM 评测文献，全部期刊论文，摘要覆盖率 100%，IF 数据完整度高。与前一个文献池（289 篇，含大量预印本和历史文献）形成互补——前者提供趋势纵深，本池提供最新截面。**需注意**：约 16 篇（17%）非医疗领域的 LLM 论文混入了该集合（来自检索噪声），后续分析中已标注。

---

## 2. 研究主题地图

从 97 篇文献的标题和摘要中聚类出 7 个主要方向（另含噪声组）。由于文献池规模在 50-150 篇区间，目标 5-8 个主题。

| 主题 | 主题名称 | English label | 代表性关键词 | 文献数 | 典型文献 | 判断依据 |
|---|---|---|---|---|---|---|
| S1 | EHR 编码与基础模型 | EHR encoding & foundation models | EHR encoder, EHRSHOT, embedding, foundation model | ~10 | LLMs are powerful EHR encoders (npj DM, IF=18); Clinical LLM centered on EMR (npj DM, IF=18); Bridging clinical narratives and structured phenotypes (JGG, IF=7.9) | 摘要聚类，核心是"EHR 数据→LLM 嵌入→下游预测" |
| S2 | 临床 NLP 信息抽取 | Clinical NLP & information extraction | NER, relation extraction, concept normalization, information extraction | ~17 | Information extraction from clinical notes: ready for LLMs? (JAMIA); Benchmarking GPT-5 for Clinical NER (TVST); CUI-Curate GraphRAG (JAMIA); Medical concept normalization survey (JBI) | 摘要聚类 |
| S3 | 临床 Agent 与工具使用 | Clinical agents & tool use | agent, agentic, tool-using, multi-agent | ~8 | AgentClinic multimodal benchmark (npj DM, IF=18); Benchmarking LLM agent systems for clinical decision (npj DM, IF=18); CARE clinical agentic reasoning engine (ESWA, IF=9.4); Agentic AI 7-dimensional taxonomy (IEEE Access) | 标题+摘要聚类 |
| S4 | 临床决策支持与推理 | Clinical reasoning & decision support | decision support, diagnostic reasoning, clinical reasoning | ~10 | Domain-adapted LLM for psychiatric practice (Nature MI, IF=29.8); AIDx clinical decision support (Sci Rep); DETERIO-LLM risk scores (JAMIA Open); PKFAR psychiatry reasoning (HISS) | 摘要聚类 |
| S5 | 多模态医学 AI | Multimodal medical AI | X-ray, multimodal, ECG, vision-language, radiology | ~12 | Sparsity-guided multi-task chest X-ray (ESWA, IF=9.4); DoKE multimodal chest X-ray (BSP); MEETI multimodal ECG from MIMIC-IV-ECG (Sci Data); VLM systematic review (ARRAY) | 摘要聚类 |
| S6 | 去标识化与隐私 | De-identification & privacy | de-identification, anonymization, PHI, HIPAA | ~6 | De-Identification of EHR using DL (Applied Sci); Agentic LLM for anonymizing healthcare data (KBS); ASQ-PHI adversarial synthetic benchmark (Data in Brief) | 标题聚类 |
| S7 | 临床文本摘要与文档生成 | Clinical text summarization & documentation | discharge summary, report generation, clinical documentation | ~10 | Zero-shot thoracic oncologic history (Radiology, IF=17.6); GoT-HCS hospital course summarization (IEEE Access); NICU discharge summary (Healthcare); AI-assisted clinical documentation error detection (JCO) | 摘要聚类 |
| S8（噪声）| 非医疗 LLM 论文 | Non-medical LLM papers | driving, inventory, fake news, recipe, coding, audiobook | ~16 | EV-STLLM charging forecasting; Driving behavior mimicry; Fake news detection; Recipe recommendation; AI coding; Quantum fine-tuning | 标题明确非医疗 |

### 主题间逻辑关联

**核心主线**：S1（EHR 编码）→ S2（信息抽取）→ S4（决策推理）→ S3（Agent 整合）。文献展示了一条从"如何用 LLM 理解 EHR 数据"到"如何用 Agent 模拟临床工作流"的技术递进链。

**辅助主线**：S5（多模态）与 S7（文本生成）是临床 LLM 的两个输出端——S5 对接影像，S7 对接文本。S6（隐私）贯穿所有主题。

**噪声组 S8**：16 篇非医疗论文（电动汽车充电预测、驾驶行为、假新闻检测、菜谱推荐、编程竞赛、量子微调等）混入本集合，来自检索宽泛（可能用 "LLM benchmark" 等泛化词检索时命中非医疗领域）。这些文献与"基于EHR评测"主题无关，建议清理。

---

## 3. 研究成熟度评估

| 主题 | 主题名称 | 成熟度 | 文献密度 | 年份趋势 | 方法趋同度 | 判断依据 | 成熟度说明 |
|---|---|---|---|---|---|---|---|
| S1 | EHR 编码与基础模型 | 新兴 | 中（10）| 仅 2026 数据点，无法判趋势 | 低（通用 LLM 嵌入 vs 专用 EHR 基础模型两条路线竞争）| EHRSHOT benchmark 论文是旗舰，但路线尚未收敛 | 方向刚成形，"通用 LLM 能否替代专用 EHR 基础模型"是核心争议 |
| S2 | 临床 NLP 信息抽取 | 成长中 | 高（17）| 数据不足（仅 2026）| 中（LLM vs 微调 vs RAG 三条路线）| 已有综述（medical concept normalization survey），但"LLM 是否已准备好替代传统 NLP"仍在争论 | 方向成熟度较高，已有方法比较综述 |
| S3 | 临床 Agent | 新兴 | 中（8）| 数据不足 | 低（单 Agent vs 多 Agent vs 工具增强三条路线）| AgentClinic 和 clinical agent benchmark 是两篇旗舰，方向刚成形 | 临床 Agent benchmark 是最新增长点，先发优势明显 |
| S4 | 临床决策支持与推理 | 成长中 | 中（10）| 数据不足 | 中（微调 vs RAG vs Agent 三条路线）| 多篇使用不同方法做疾病特异性 CDS | 各专科都在做，但缺乏跨疾病统一框架 |
| S5 | 多模态医学 AI | 成长中 | 高（12）| 数据不足 | 中（影像+文本融合是主流路线）| 已有 VLM 系统综述 | 方向成熟度高，但与 EHR 评测的交叉较少 |
| S6 | 去标识化与隐私 | 成长中 | 低（6）| 数据不足 | 低（DL 去标识 vs 合成数据 vs Agent 去标识）| 多种技术路线并存，无收敛迹象 | 方向稳定但碎片化，缺乏统一评测标准 |
| S7 | 临床文本摘要 | 成长中 | 中（10）| 数据不足 | 高（均用 LLM 生成 + 人工评估）| Radiology 和 JAMIA Open 论文是典型 | 方法趋同（LLM+RAG 生成+人工评估），但评估标准不统一 |
| S8 | 噪声 | — | 高（16）| — | — | 与主题无关 | 建议清理 |

**关键限制**：由于文献池 100% 来自 2026 年，所有"年份趋势"判断均标注为"数据不足"。成熟度评估主要基于文献密度和方法趋同度。

---

## 4. 研究空白与机会方向

| 编号 | 方向描述 | English label | 空白类型 | 支撑文献 | 成熟度 | 机会窗口 |
|---|---|---|---|---|---|---|
| O1 | EHR 结构化数据→LLM 嵌入→临床预测的统一 benchmark | Unified EHR-LLM benchmark for structured prediction | 评测空白 | S1 簇中 EHRSHOT benchmark（#1）是目前唯一系统比较 LLM 嵌入 vs 专用 EHR 基础模型的 benchmark，但只覆盖 15 个任务且数据源单一 | 新兴 | **最大窗口**——EHRSHOT 刚发表(2026)，后续 benchmark 设计的方法学空白大 |
| O2 | 临床 Agent benchmark 的标准化评估框架 | Standardized evaluation for clinical AI agents | 评测空白 | S3 簇 AgentClinic(#65) 和 clinical agent benchmark(#80) 是仅有的两篇 Agent benchmark，任务定义各异，无统一评估协议 | 新兴 | **快速收窄**——Agent benchmark 2026 年刚出现，但已有多篇竞争 |
| O3 | 临床 NLP 从传统方法向 LLM 迁移的就绪度标准 | Migration readiness criteria for clinical NLP | 被忽视的问题 | S2 簇 #5"are we ready to switch to LLMs?"明确提出迁移问题，但无系统就绪度框架 | 成长中 | **中等窗口**——问题已被提出但无人系统回答 |
| O4 | EHR 数据质量对 LLM 评测结果的影响 | EHR data quality impact on LLM evaluation | 被忽视的问题 | S1 簇 #11 验证 EHR 衍生数据的准确性，#92 Clinical-ShiftEval 模拟数据偏移，但无系统研究数据质量如何影响 benchmark 排名 | 成长中 | **中等窗口**——需求明确但方法空白 |
| O5 | 多模态 EHR benchmark（影像+文本+结构化数据）| Multimodal EHR benchmark | 方法-场景空白 | S5 簇多模态工作集中在影像+报告，S1 簇集中在结构化 EHR，两者交叉（影像+结构化 EHR+文本的统一 benchmark）文献空白 | 成长中 | **长期窗口**——技术可行但整合综述/benchmark 空白 |
| O6 | 临床 LLM 去标识化的统一评测标准 | Unified de-identification benchmark | 评测空白 | S6 簇 6 篇使用不同数据集和指标，ASQ-PHI(#88) 是唯一提出 adversarial benchmark 的，但无跨方法统一比较 | 成长中 | **中等窗口**——碎片化严重，统一 benchmark 有价值 |
| O7 | 临床环境模拟器用于动态 AI 评估 | Clinical environment simulator for dynamic evaluation | 时效性机会 | S1 簇 #72（Nature Medicine, IF=52.5）提出"临床环境模拟器"概念，与项目"合成场景防泄漏"设计直接呼应 | 新兴 | **中等窗口**——概念刚提出，后续应用空间大 |

**最大机会**：O1（统一 EHR-LLM benchmark）与项目方向直接对齐。EHRSHOT（#1, IF=18, npj DM）是目前唯一系统比较 LLM 嵌入和专用 EHR 基础模型的 benchmark，但仅覆盖 15 个任务且数据源单一——项目用 MIMIC-IV 条件概率做 benchmark 答案是差异化切入点。

**时效性最强**：O7（临床环境模拟器），#72 在 Nature Medicine（IF=52.5）发表，提出"动态 AI 评估"概念，与项目防泄漏+持续更新设计理念一致。这是本文献池中 IF 最高的论文，方向影响力大。

---

## 5. 高影响力文献速览

按推荐阅读顺序排列，综合影响因子、期刊地位、摘要内容贡献和多主题交叉度筛选。已排除 S8 噪声组。

| 序号 | 标题 | 年份 | 期刊 | IF | 推荐理由 | 优先级 |
|---|---|---|---|---|---|---|
| 1 | A clinical environment simulator for dynamic AI evaluation | 2026 | Nature Medicine | 52.5 | **IF 最高**——动态评估范式，与项目防泄漏设计直接呼应；提出"临床环境模拟器"概念 | P0 |
| 2 | A domain-adapted large language model to support clinicians in psychiatric clinical practice | 2026 | Nature Machine Intelligence | 29.8 | 专科领域 LLM 适配的旗舰论文，S4 核心参照 | P0 |
| 3 | BRIDGE: benchmarking LLMs for understanding real-world clinical practice texts | 2026 | Nature Biomedical Engineering | 26.3 | **Prior art 风险**——"real-world clinical practice" benchmark，需精读答案逻辑 | P0 |
| 4 | LLMs are powerful electronic health record encoders | 2026 | npj Digital Medicine | 18 | S1 簇旗舰——LLM 做 EHR 编码 vs 专用基础模型，EHRSHOT benchmark 核心论文 | P0 |
| 5 | AgentClinic: a multimodal benchmark for tool-using clinical AI agents | 2026 | npj Digital Medicine | 18 | S3 簇旗舰——临床 Agent benchmark 的代表性工作 | P0 |
| 6 | Benchmarking LLM-based agent systems for clinical decision tasks | 2026 | npj Digital Medicine | 18 | S3 簇第二篇 npj DM——Agent 系统做临床决策任务的 benchmark | P0 |
| 7 | Zero-shot thoracic oncologic history generation for radiologists | 2026 | Radiology | 17.6 | S7 簇旗舰——零样本生成放射学历史，RAG 方法学参照 | P1 |
| 8 | Information extraction from clinical notes: are we ready to switch to LLMs? | 2026 | JAMIA | 7.1 | S2 簇核心——临床 NLP 迁移就绪度的关键问题论文 | P1 |
| 9 | Clinical-ShiftEval: simulating and evaluating model adaptation in dynamic clinical NLP | 2026 | BMC Med Inform | 5.5 | S1/O4——数据偏移对模型评估的影响，方法论参照 | P1 |
| 10 | Beyond the Leaderboard: Survey of Evaluation, Benchmarking, and Methodologies for LLMs | 2026 | IEEE Access | 4.2 | 综述类——benchmark 方法论的系统综述，适合先读建立框架 | P1 |
| 11 | ClinicRealm: Re-evaluating LLMs with conventional ML for non-generative clinical tasks | 2026 | npj Digital Medicine | 18 | **关键对照**——论证 LLM 在非生成式临床任务上不一定优于传统 ML | P1 |
| 12 | Clinical agents fail silently on patient identity | 2026 | Int J Med Inform | 5 | S3——Agent 在患者身份任务上静默失败，安全风险参照 | P1 |
| 13 | ASQ-PHI: adversarial synthetic data benchmark for clinical de-identification | 2026 | Data in Brief | 1.9 | S6——去标识化对抗性 benchmark，与项目隐私保护设计呼应 | P2 |
| 14 | Large language models in healthcare and biomedical informatics: A comprehensive review | 2026 | Innovation & Emerging Tech | 2.3 | 综述类——LLM 医疗应用全景，适合背景阅读 | P2 |
| 15 | A systematic review of vision language models | 2026 | ARRAY | 5.3 | 综述类——VLM 架构/应用/数据集系统综述，S5 背景文献 | P2 |

**建议阅读顺序**：先读 #1-3（P0 最高 IF，确认 prior art 和方法范式），再读 #4-6（npj DM 三连，S1/S3 核心方法），然后 #7-12（各子方向 P1），最后 #13-15 综述补全背景。

**注意**：#3（BRIDGE, Nature Biomedical Engineering, IF=26.3）标题含"real-world clinical practice"和"benchmarking"，是最高 prior art 风险——需优先精读，确认其答案逻辑是否也来自 RWD 统计。

---

## 6. 后续行动建议

### 文献池质量评估

| 维度 | 评估 |
|---|---|
| 主题聚焦度 | 中等——74 篇医疗相关 + 16 篇噪声（17%）|
| 时效性 | 极高——100% 来自 2026 年 |
| 摘要覆盖率 | 100%，聚类可靠性高 |
| IF 完整性 | 99% 有 IF 数据，质量可追溯 |
| 是否适合直接进入选题挖掘 | **适合，但建议先清理噪声** |

### 建议路径

| 步骤 | 行动 | 理由 |
|---|---|---|
| 1 | **清理 S8 噪声组**（16 篇非医疗论文）| 17% 噪声率会干扰下游选题挖掘和文献筛选 |
| 2 | **与 289 篇文献池合并** | 本池（97 篇 2026 年最新）+ 前池（289 篇 2010-2026 跨度）= 完整的时间纵深 |
| 3 | **优先精读 P0 文献**（#1-6）| BRIDGE(#3) 是最高 prior art 风险，必须优先确认答案逻辑 |
| 4 | **进入 `$sci-review-topic-mining`** | 合并后的文献池（约 380 篇去重后）可支撑深度选题挖掘 |

### 预期风险

- **噪声未清理**：16 篇非医疗论文会干扰主题聚类和评分，建议在 Zotero 中移至单独集合或打标签标记
- **BRIDGE prior art**：#3（IF=26.3, Nature Biomedical Engineering）的答案逻辑需优先确认——若其也使用 RWD 统计做答案，项目核心新颖性需重新论证
- **时间维度缺失**：本文献池全 2026 年，无法独立判断趋势，必须与前池合并使用
- **Agent benchmark 竞争**：S3 簇已有两篇 npj DM（IF=18）Agent benchmark，若项目也做 Agent 评测，需明确差异化
