# RWD/EHR 临床 LLM 评测基准 —— 领域全景分析

> 分析技能：`$sci-review-landscape`
> 文献池：Zotero「文献调研」集合（K3GSQR4X）去重后 289 篇唯一文献
> 检索来源：PubMed + arXiv（179 条）+ Google Scholar（112 条新增）
> WoS 因反爬拦截未纳入
> 生成日期：2026-08-06

---

## 1. 文献池画像

### 1.1 总数与类型分布

| 指标 | 数值 |
|---|---|
| 文献总数 | 289 |
| 期刊论文 journalArticle | 173（59.9%）|
| 预印本/文档 document | 90（31.1%）|
| 会议论文 conferencePaper | 26（9.0%）|
| 学位论文 thesis | 0 |
| 数据来源 | Zotero 集合「文献调研」（K3GSQR4X），路径 博士→2026_08→Hongkong |

### 1.2 年份分布

```
2010: 1  │
2011: 2  ││
2012: 1  │
2014: 1  │
2016: 3  │││
2017: 9  ││││││││││
2018: 4  ││││
2019: 11 │││││││││││││
2020: 11 │││││││││││││
2021: 12 ││││││││││││││
2022: 32 ││││││││││││││││││││││││││││││││││
2023: 32 ││││││││││││││││││││││││││││││││││
2024: 60 │││││││││││││││││││││││││││││││││││││││││││││││││││││││││││││││││
2025: 62 │││││││││││││││││││││││││││││││││││││││││││││││││││││││││││││││││
2026: 48 ││││││││││││││││││││││││││││││││││││││││││││││││││││││││││
```

**峰值年份**：2025（62 篇）。**爆发拐点**：2024 年（从 32→60，+87.5%）。2022-2026 年合计 234 篇，占 81%，显示该领域正处于加速期。

### 1.3 期刊分布

| 排名 | 期刊/来源 | 文献数 |
|---|---|---|
| 1 | JMIR AI | 5 |
| 2 | npj Digital Medicine | 4 |
| 2 | Clinical Chemistry | 4 |
| 4 | Nature Medicine | 3 |
| 4 | Clinical Biochemistry | 3 |
| 4 | J Physical Therapy Science | 3 |
| 4 | BMC Medical Informatics & Decision Making | 3 |
| 4 | Journal of Nursing Measurement | 3 |
| 4 | Annals of the Rheumatic Diseases | 3 |
| 4 | Academic Radiology | 3 |

132 个唯一期刊/来源，Top 10 仅覆盖 11%（34/289）。**高度分散**——这是新兴交叉领域的典型信号，尚无单一期刊成为发表中心。

### 1.4 摘要覆盖率

| 指标 | 数值 |
|---|---|
| 有摘要 | 182 篇（62%）|
| 无摘要 | 107 篇（38%）|

**警告**：摘要覆盖率 62%，低于 70% 阈值。主题聚类对约 38% 的文献仅依赖标题判断，该部分归类的不确定性较高。后续如需精确分类，建议补充全文或扩展摘要。

### 1.5 影响因子分布

| IF 区间 | 文献数 | 占比 |
|---|---|---|
| 高 IF（≥10）| 24 | 8.3% |
| 中 IF（3-9.9）| 51 | 17.6% |
| 低 IF（<3）| 27 | 9.3% |
| 无 IF 数据 | 187 | 64.7% |

中科院分区：Z1 26 篇、Z2 26+4 篇、Z3 29+2 篇、Z4 15 篇、无分区 187 篇。高 IF 文献（≥10）包括 Nature (x2)、Nature Medicine (x3)、JAMA Network Open (x2)、NEJM AI、npj Digital Medicine (x4) 等。

### 1.6 关键信号

该文献池集中于 2023-2026 年的 RWD/EHR 临床 LLM 评测研究，期刊高度分散（132 种），预印本占比高（31%），反映该领域正处于快速成形的早期爆发阶段。高 IF 文献集中在 Nature 系和 JAMA 系，但 65% 的文献无 IF 数据（多为 arXiv/preprint），说明大量最新工作尚未进入正式期刊流程。摘要覆盖率偏低（62%），部分方向判断受限于标题信息。

---

## 2. 研究主题地图

从 289 篇文献的标题和摘要中聚类出 8 个主要研究方向。

| 主题 | 主题名称 | English label | 代表性关键词 | 文献数 | 典型文献 | 判断依据 |
|---|---|---|---|---|---|---|
| T1 | 医疗 LLM 执业考试评测 | Medical LLM exam benchmarks | MedQA, USMLE, MedMCQA, licensing exam | ~42 | Large language models encode clinical knowledge (2023, Nature); Performance of ChatGPT on USMLE (2024, JMIR); PersianMedQA (2025) | 摘要+标题聚类 |
| T2 | EHR 衍生临床 benchmark | EHR-derived clinical benchmarks | EHR, MIMIC, real-world, benchmark | ~23 | EHRNoteQA (2024); LLMEval-Med (2025); EHR-Complex (2026); CliniQ (2025) | 摘要聚类，标题含 benchmark+EHR |
| T3 | MCQ 自动生成与干扰项 | Automated MCQ generation | MCQ, distractor, question generation, AIG | ~50 | AIG in Medical Assessment (2022); KG-guided distractor (2025); MCQG-SRefine (2025); 医学 MCQ 生成综述 (2024) | 摘要聚类 |
| T4 | EHR 知识图谱与关联规则 | EHR knowledge graph & pattern mining | knowledge graph, association rule, data mining | ~37 | Li et al. 2020; Robustly Extracting Medical KG from EHRs (2019); Roque et al. 2011; cSPADE 疾病序列 (2025) | 摘要+标题聚类 |
| T5 | 检查检验医嘱预测 | Lab test ordering prediction | lab test, ordering, CDS, recommendation | ~27 | OrderRex (2016/2020); Lab test ordering prediction in ED (2022); SmartAlert lab utilization (2025) | 标题聚类，部分摘要 |
| T6 | benchmark 数据污染 | Data contamination & integrity | contamination, leakage, memorization | ~18 | NLP Evaluation in Trouble (2023); LiveMedBench (2026); CONFIDE (2024); Balloccu 综述 (2024) | 标题聚类 |
| T7 | 合成 EHR 数据生成 | Synthetic EHR data | synthetic EHR, GAN, diffusion, generation | ~12 | SynEHRgy (2024); TarDiff (2025); 合成 EHR 方法学综述 (2025) | 摘要聚类 |
| T8 | benchmark 批判与效度 | Benchmark critique & construct validity | construct validity, rethinking, leaderboard | ~15 | Pattern Recognition or Medical Knowledge (2024); Beyond the Leaderboard (2025); Construct Validity (2025) | 摘要聚类 |

### 主题间逻辑关联

三条主线串联八个主题：

1. **评测主线**：T1（考试式）→ T2（EHR 式）→ T8（效度批判）。从"LLM 考多少分"演进到"分数意味着什么"，T2 和 T8 是增长前沿。
2. **生成主线**：T3（MCQ 生成）← T4（知识挖掘）→ T5（检查预测）。T4 的关联规则/知识图谱为 T3 干扰项构建和 T5 答案逻辑提供方法基础。
3. **防护主线**：T6（数据污染）← T7（合成数据）。T7 合成 EHR 为 T6 防泄漏提供技术路径。

**T5 是结构性桥梁**：连接评测主线（可做 benchmark 任务）、生成主线（条件概率来自 T4 的关联规则）和临床应用（CDS 系统）。

**边缘性主题**：Z_other 中约 46 篇涉及具体疾病（甲状腺急症、纤维肌痛、败血症预测）、非 LLM 临床工具开发（步态分析、运动捕捉）、护理教育等，与泛主题间接相关，不构成独立研究方向。

---

## 3. 研究成熟度评估

| 主题 | 主题名称 | 成熟度 | 文献密度 | 年份趋势 | 方法趋同度 | 判断依据 | 成熟度说明 |
|---|---|---|---|---|---|---|---|
| T1 | 执业考试评测 | 成长中→接近成熟 | 高（42）| 快速增长后趋稳 | 高（均用 USMLE/MCQ 跑模型）| 2024-2026 集中爆发，多篇系统综述已发表 | 方向明确，方法路线趋同（考试题→跑模型→报告准确率），但持续有新模型/新语言版本出现 |
| T2 | EHR 衍生 benchmark | 成长中 | 中（23）| 快速增长 | 低（任务类型高度分化：预测/QA/SQL/检索/Agent）| 2024-2026 年集中出现，尚无统一分类框架 | 方向刚成形，方法路线在分化，系统梳理空间大 |
| T3 | MCQ 自动生成 | 成长中 | 高（50）| 稳定增长 | 中（规则→LLM 两条路线）| 2022 起持续增长，已有 2+ 篇综述 | 方法从 AIG 转向 LLM 生成，干扰项策略仍在分化 |
| T4 | KG 与关联规则 | 成熟 | 高（37）| 波动（经典→近期回升）| 高（共现统计→嵌入学习为主路线）| 2011-2026 跨度，多篇综述已存在 | 方法论成熟，近期 LLM+KG 融合带来新增长 |
| T5 | 检查检验预测 | 零星探索→新兴 | 低中（27）| 平稳（分布散）| 低（CDS 工程/推荐算法/预测建模三条路线分散）| 27 篇分散在临床信息学和 ML 两社区，作为 benchmark 任务文献空白 | 作为 CDS 组件有基础，作为独立 benchmark 任务无先例 |
| T6 | 数据污染 | 新兴 | 低中（18）| 快速增长（增速最快）| 中（检测+防护两条路线）| 2023 年起步，2025-2026 密集产出 | 先发优势明显，医疗专用污染综述空白 |
| T7 | 合成 EHR | 成长中 | 低（12）| 稳定增长 | 中（GAN→Transformer→Diffusion 演进）| 已有方法学综述（2025）| 技术路线在演进，与 benchmark 质量评估交叉 |
| T8 | benchmark 批判与效度 | 新兴 | 低（15）| 快速增长 | 低（批判角度多元：效度/污染/leaderboard）| 2024 起密集出现，尚无统一理论框架 | 批判性反思正在形成独立方向，适合观点驱动综述 |

---

## 4. 研究空白与机会方向

| 编号 | 方向描述 | English label | 空白类型 | 支撑文献 | 成熟度 | 机会窗口 |
|---|---|---|---|---|---|---|
| O1 | 用 RWD 条件概率 P(检查|特征) 排名第一做 MCQ 答案 | RWD conditional probability as MCQ answer | 方法-场景空白 | OrderRex (2016/2020) 做推荐排序非 MCQ；Li et al. 2020 做条件概率+知识图谱非评测 | 零星探索 | **最大窗口**——文献中无直接先例；OrderRex 是最近的方法参照但不构成直接竞争 |
| O2 | 检查检验选择作为独立 benchmark 评测任务 | Lab test ordering as benchmark task | 评测空白 | T5 簇 27 篇均为 CDS 工具或推荐系统，无人构建 MCQ 评测集 | 零星探索 | **高新颖性**——该任务作为 benchmark 文献空白；CDS 领域有方法基础可迁移 |
| O3 | EHR benchmark 的答案来源谱系与效度论证 | Answer source taxonomy for EHR benchmarks | 评测空白 | T2 簇 benchmark 答案来源各异（金标准结局/专家标注/RWD 统计），无人系统比较效度差异 | 成长中 | **中等窗口**——T2 方向刚成形，尚无统一分类框架 |
| O4 | 医疗 benchmark 数据污染检测的医疗专用方法 | Medical-specific contamination detection | 时效性机会 | T6 簇 18 篇方法偏通用 NLP，MIMIC 等公开 EHR 已被 LLM 训练但缺乏医疗专用污染研究 | 新兴 | **快速收窄**——2025-2026 年密集产出，先发窗口在缩小 |
| O5 | EHR benchmark 建构效度理论框架 | Construct validity framework for EHR benchmarks | 被忽视的问题 | T8 簇 15 篇批判性文献指出 benchmark 可能只测模式识别，但无人将心理测量学建构效度系统引入 EHR benchmark | 新兴 | **中等窗口**——批判声量在增大但理论框架空白 |
| O6 | EHR 关联规则→知识图谱→LLM 推理的方法演进整合 | EHR KG → LLM reasoning integration | 跨学科空白 | T4 经典关联规则（2011-2020）与近期 LLM+KG（2025-2026）分属不同社区，缺乏整合视角 | 成熟+新兴交叉 | **长期窗口**——方法成熟但整合综述空白 |
| O7 | 合成 EHR 用于 benchmark 防泄漏的技术路径 | Synthetic EHR for contamination-free benchmark | 方法-场景空白 | T7 合成 EHR 文献关注数据质量评估，未聚焦"防 benchmark 泄漏"应用 | 成长中 | **中等窗口**——两条技术线尚未对接 |
| O8 | EHR benchmark 与真实临床工作流的距离衡量 | Clinical workflow alignment metrics | 被忽视的问题 | T2/T8 多篇文献讨论 benchmark 临床真实性，但无人提出系统的临床对齐度量指标 | 成长中 | **中等窗口**——需求明确但方法空白 |

**最大机会**：O1（RWD 条件概率做 MCQ 答案）和 O2（检查检验选择作为 benchmark 任务）构成一组协同机会——O1 提供 O2 的答案逻辑方法，O2 提供 O1 的评测任务载体。两者在文献池中均无直接先例，与本项目方向完全对齐。

**快速收窄的窗口**：O4（医疗数据污染）的先发窗口正在缩小——2025-2026 年该方向文献密集产出，如不尽快切入，医疗专用污染综述可能被他人先发。

---

## 5. 高影响力文献速览

按推荐阅读顺序排列，综合影响因子、时效性、方法论贡献和多主题交叉度筛选。

| 序号 | 标题 | 年份 | 期刊 | IF | 推荐理由 | 优先级 |
|---|---|---|---|---|---|---|
| 1 | Large language models encode clinical knowledge | 2023 | Nature | 56.1 | MedQA/MultiMedQA benchmark 奠基论文，T1 簇起点 | P0 |
| 2 | Toward expert-level medical question answering with LLMs | 2025 | Nature Medicine | — | AM-GPT 医学推理 SOTA，benchmark 表现上限 | P0 |
| 3 | LLMEval-Med: A Real-world Clinical Benchmark for Medical LLMs | 2025 | — | — | **Prior art 风险**——"真实世界临床 benchmark"措辞重叠，需精读确认答案逻辑 | P0 |
| 4 | Medical LLM Benchmarks Should Prioritize Construct Validity | 2025 | — | — | T8 效度批判的核心理论框架文献 | P0 |
| 5 | Beyond the Leaderboard: Rethinking Medical Benchmarks for LLMs | 2025/2026 | — | — | 56 个 benchmark 实证审计，T8 旗舰 | P0 |
| 6 | OrderRex: clinical order decision support by data-mining EMR | 2016 | JAMIA | — | **答案逻辑直接先例**——P(医嘱|上下文) 推荐系统 | P0 |
| 7 | Multitask learning and benchmarking with clinical time series data | 2017 | — | — | MIMIC-IV Benchmark 奠基论文，T2 数据源起点 | P1 |
| 8 | EHRNoteQA: An LLM Benchmark for Real-World Clinical Practice | 2024 | — | — | T2 簇代表性 EHR benchmark | P1 |
| 9 | Pattern Recognition or Medical Knowledge? The Problem with MCQs in Medicine | 2024 | — | — | T8 批判性文献，论证 MCQ 可能只测模式识别 | P1 |
| 10 | LiveMedBench: A Contamination-Free Medical Benchmark | 2026 | — | — | T6 簇无污染 benchmark 代表，防泄漏设计参照 | P1 |
| 11 | EHR-Complex: benchmarking medical agents for complex clinical reasoning | 2026 | — | — | T2 最新 benchmark，Agent 范式 | P1 |
| 12 | Enhancing clinical MCQ benchmarks with KG guided distractor generation | 2025 | arXiv | — | T3∩T4 交叉，干扰项构建直接方法参考 | P1 |
| 13 | Robustly Extracting Medical Knowledge from EHRs | 2019 | — | — | T4 簇 EHR→知识图谱核心方法论文，项目根基参照 | P1 |
| 14 | A survey on evaluating quality and trustworthiness in LLM-generated data | 2026 | arXiv | — | 综述类，适合先读建立框架 | P2 |
| 15 | Generating synthetic EHR data: a methodological scoping review | 2025 | — | — | T7 综述类，合成 EHR 方法学全景 | P2 |

**建议阅读顺序**：先读 P0 系列中 #1-2 建立 benchmark 范式认知，#3-5 确认 prior art 和效度框架，#6 确认答案逻辑先例；再读 P1 系列 #7-8 理解 EHR benchmark 方法，#9-12 理解批判/防护/生成交叉；最后读 P2 综述补全背景。

---

## 6. 后续行动建议

**判断**：该文献池满足"主题清晰、文献充足、已识别出明确空白"的条件（289 篇，8 个主题簇，8 个机会方向），**适合直接进入选题挖掘**。

根据全景分析，建议优先深挖以下 2-3 个方向：

| 优先级 | 方向 | 理由 | 建议路径 |
|---|---|---|---|
| 1 | EHR 衍生 benchmark（T2 + T8 + O3）| 增速最快的新兴前沿，23 篇文献，分类框架空白，与项目完全对齐 | 进入 `$sci-review-topic-mining`，泛主题="EHR-derived medical LLM benchmark" |
| 2 | 数据污染与 benchmark 完整性（T6 + O4）| 增速最快且窗口快速收窄，医疗专用综述空白 | 进入 `$sci-review-topic-mining`，但需先补充通用 NLP 污染文献 |
| 3 | 检查检验预测（T5 + O1 + O2）| 最高新颖性，与项目题型 1 直接对齐，但文献分散需跨社区整合 | 进入 `$sci-review-topic-mining`，需补充实验室医学 CDS 文献 |

**预期风险**：
- T2 簇 23 篇偏少，综述选题可能偏窄，需整合 T1 簇考试式 benchmark 做对比锚点
- T6 簇 18 篇文献不足，选题挖掘后可能需要补充 15-20 篇通用 LLM 污染文献才能达到全面综述门槛
- T5 簇文献分散在临床信息学和 ML 两社区，跨社区整合难度较高
- LLMEval-Med（#3）是最高 prior art 风险——若其答案也来自 RWD 统计，本项目的核心新颖性需要重新论证

**已完成的下游步骤**：`$sci-review-topic-mining` 已对 T2 方向执行完毕（见 [sci_review_topic_mining.md](sci_review_topic_mining.md)），产出 8 个候选选题和推荐首选"EHR-Derived Benchmarks"综述。
