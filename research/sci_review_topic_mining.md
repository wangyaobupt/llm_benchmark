# SCI 综述选题挖掘报告

> 泛主题：RWD / EHR 临床 LLM 评测基准
> 文献池：Zotero「文献调研」集合（K3GSQR4X）去重后 289 篇唯一文献
> 分析技能：`$sci-review-topic-mining`
> 生成日期：2026-08-06

---

## 1. 文献池整体判断

### 1.1 泛主题解释

泛主题"RWD/EHR 临床 LLM 评测基准"涵盖三条交汇的研究主线：

1. **真实世界数据（RWD）/ 电子病历（EHR）**：以 MIMIC-IV 为代表的结构化临床数据，用作数据源和证据基底。
2. **大语言模型（LLM）评测**：包括考试式 MCQ benchmark（MedQA、MedMCQA 等）和 EHR 衍生的临床任务 benchmark。
3. **临床决策与检查检验预测**：实验室检查医嘱预测、CDS 系统、关联规则挖掘——本项目的题型 1 直接落在此线。

该泛主题本身**偏宽**：它横跨"AI 评测方法学"和"临床信息学应用"两个学科域，且包含从统计方法（关联规则）到系统工程（CPOE）到教育评测（AIG）的多个子领域。必须通过文献池收窄到可操作的综述选题。

### 1.2 文献池整体特征

| 维度 | 数据 | 判断 |
|---|---|---|
| 文献数量 | 289 篇 | 充足，可支撑多个方向的选题挖掘 |
| 年份分布 | 2026:48, 2025:62, 2024:60, 2023:32, 2022:32（2010-2026 跨度） | **2022-2026 年占 81%（234/289）**，显示领域正处于爆发期 |
| 文献类型 | 期刊 173 / 预印本文档 90 / 会议 26 | 以期刊和预印本为主，反映快速发表节奏 |
| 主题集中度 | 8 个主题簇，最大簇 B（77-104 篇），最小簇 G（2-15 篇） | 高度集中在 EHR/RWD 和 benchmark 两大主题，交叉地带多 |
| 技术路线分支 | 考试式 benchmark vs EHR 衍生 benchmark vs MCQ 自动生成 vs 数据污染防护 | 存在清晰的技术路线分化和交叉融合 |
| 主要限制 | WoS 因反爬未纳入；部分文献仅有标题和摘要，无全文；未做施引网络分析 | 可能遗漏部分高被引经典文献（已在 GS 补搜中部分弥补） |

**整体判断**：文献池质量高、时效性强，主题覆盖从"批判现有 benchmark"到"构建新 benchmark"到"防护数据污染"的完整链条，足以支撑 5-8 个差异化选题。

---

## 2. 文献主题归类

基于标题、摘要、关键词和年份分布，将 289 篇文献归入 8 个主题簇。各簇文献数量按"相关性命中"计算（一篇文献可归入多簇）。

| 编号 | 主题名称 | 中文解释 | 与泛主题的关系 | 文献数 | 代表性文献 | 判断依据 | 研究趋势 |
|---|---|---|---|---|---|---|---|
| T1 | Medical LLM exam-style benchmarks | 医疗 LLM 执业考试式 MCQ 评测 | 核心相关 | ~42 | MedQA (Singhal 2023, Nature); USMLE 系统综述 (JMIR 2024); KorMedMCQA (2024); PersianMedQA (2025) | 标题+摘要均明确涉及 benchmark/exam/USMLE | 2024-2026 年爆发，趋近饱和 |
| T2 | EHR-derived clinical benchmarks | 基于 EHR/RWD 的临床 LLM benchmark | 核心相关 | ~23 | EHRNoteQA (2024); LLMEval-Med (2025); EHR-Complex (2026); CliniQ (2025); EHRSQL (2022); MIMIC-IV Benchmark (2017/2025) | 标题含 benchmark + EHR/MIMIC/real-world | **增长最快的新兴方向**，2024-2026 年集中出现 |
| T3 | Automated MCQ generation & distractor construction | 医疗 MCQ 自动生成与干扰项构建 | 高度相关 | ~50 | AIG 综述 (2022); LLM distractor generation (2023/2025); KG-guided distractor (2025); MCQG-SRefine (2025) | 标题含 MCQ/distractor/question generation | 2022 起持续增长，方法从规则转向 LLM |
| T4 | EHR knowledge graph & association rule mining | EHR 知识图谱与关联规则挖掘 | 高度相关 | ~37 | Li et al. 2020 (项目根基); Robustly Extracting Medical KG from EHRs (2019); Roque et al. 2011; cSPADE 疾病序列 (2025) | 标题含 knowledge graph/association rule/pattern mining + EHR | 2020 前后有经典，近期 LLM+KG 融合回升 |
| T5 | Lab test ordering prediction & lab CDS | 检查检验医嘱预测与实验室决策支持 | 高度相关 | ~27 | OrderRex (2016/2020); Lab test ordering prediction in ED (2022); 重复检验 CDS (2023); SmartAlert lab utilization (2025) | 标题含 lab test ordering/laboratory/CDS | **作为 benchmark 任务文献空白**；作为 CDS 组件有基础 |
| T6 | Data contamination & benchmark integrity | benchmark 数据污染与完整性 | 核心相关 | ~18 | NLP Evaluation in Trouble (2023); LiveMedBench (2026); LiveClin (2026); CONFIDE (2024); Balloccu 综述 (2024) | 标题含 contamination/leak/memorization | **2023 起新兴**，2025-2026 年密集产出，增速最快 |
| T7 | Synthetic EHR data generation | 合成 EHR 数据生成 | 间接相关 | ~12 | SynEHRgy (2024); TarDiff (2025); 合成 EHR 方法学综述 (2025); GAN for EHR (2017) | 标题含 synthetic EHR/generation | 稳步增长，与 benchmark 质量评估交叉 |
| T8 | Benchmark critique & construct validity | benchmark 批判与建构效度 | 核心相关 | ~15 | Pattern Recognition or Medical Knowledge (2024); Beyond the Leaderboard (2025/2026); Construct Validity (2025); Inflated Excellence (2025); BenchMarker (2026) | 标题含 rethinking/critique/validity/benchmark flaws | **批判性反思正在形成独立方向**，2024 起密集出现 |

### 主题间逻辑关系

**三条主线**串联八个簇：

- **评测主线**：T1（考试式）→ T2（EHR 式）→ T8（效度批判）。文献从"LLM 能考多少分"演进到"分数意味着什么"，T2 和 T8 是当前增长前沿。
- **生成主线**：T3（MCQ 生成）+ T4（知识挖掘）。T4 的关联规则/知识图谱为 T3 的干扰项构建和 T5 的答案逻辑提供方法基础。
- **防护主线**：T6（数据污染）+ T7（合成数据）。T7 的合成 EHR 为 T6 的防泄漏提供技术路径。

**T5（检查检验预测）是结构性的"桥梁簇"**：连接评测主线（可做 benchmark 任务）、生成主线（条件概率来自 T4 的关联规则）和临床应用主线（CDS 系统）。但作为独立 benchmark 任务，文献几乎空白——既是选题机会，也是文献不足的警示。

---

## 3. 候选 Review Paper 选题（8 个）

以下 8 个选题从泛主题收窄而来，按从聚焦 benchmark 方法到聚焦临床应用的顺序排列。

### 选题 1

**英文标题**：From Real-World Data to Evaluation: A Review of EHR-Derived Benchmarks for Medical Large Language Models

**中文解释**：综述从电子病历/真实世界数据构建的 LLM 临床评测基准，区别于考试式 MCQ benchmark，聚焦 EHR 衍生 benchmark 的数据源、任务设计、答案来源和效度论证。

**从泛主题收窄路径**：从"评测"维度收窄到 EHR 衍生 benchmark（排除考试式），再从"数据源"维度收窄到 MIMIC-IV 等结构化 EHR。

**核心研究问题**：
1. EHR 衍生 benchmark 与考试式 benchmark 在答案语义上有何本质区别？
2. 现有 EHR benchmark 的任务类型（死亡率预测、文本 QA、SQL 查询、检索）如何分类？
3. EHR benchmark 的答案来源（金标准结局 vs 专家标注 vs RWD 统计）如何影响效度？
4. EHR benchmark 面临哪些特有挑战（数据质量、隐私、泄漏、临床对齐）？

**为什么适合写 Review Paper**：T2 簇 23 篇文献且集中在 2024-2026 年，方向刚成形但尚无系统综述。文献足够支撑分类框架，且正处于增长期。

**潜在创新点**：提出"考试式 vs EHR 式"二分法分类框架；系统梳理答案来源谱系；将效度批判（T8）与 EHR benchmark 设计整合。

**范围判断**：适中。EHR 衍生 benchmark 文献边界清晰，需排除纯预测建模（非 benchmark）文献。

---

### 选题 2

**英文标题**：Automated Medical Multiple-Choice Question Generation: Methods, Evaluation Frameworks, and Quality Assurance

**中文解释**：综述医疗领域 MCQ 自动生成方法（从规则式 AIG 到 LLM 生成），重点覆盖答案确定、干扰项构建、难度控制和质量评估。

**从泛主题收窄路径**：从"评测"收窄到"题目生成"（benchmark 的构建方法而非使用方法），再从泛 AI 收窄到医疗领域。

**核心研究问题**：
1. 医疗 MCQ 自动生成经历了哪些技术阶段（规则→检索→LLM）？
2. 干扰项生成有哪些策略（同族混淆、语义近似、知识图谱引导）？
3. 如何评估自动生成 MCQ 的质量（心理测量学指标 vs LLM-as-Judge vs 专家审核）？
4. 答案确定与题目生成的分离如何影响质量？

**为什么适合写 Review Paper**：T3 簇约 50 篇文献，数量充分且方法论多元，但尚缺乏将"答案逻辑""干扰项策略""质量保证"三层整合的综述。

**潜在创新点**：提出"答案先验→干扰项锁定→语言生成"三阶段分类框架；整合教育测量学与 NLP 的评估方法。

**范围判断**：适中偏宽。50 篇需进一步按"生成方法"vs"质量评估"vs"教育应用"切割。

---

### 选题 3

**英文标题**：Data Contamination and Integrity in Medical LLM Benchmarks: Detection, Impact, and Mitigation

**中文解释**：综述医疗 LLM benchmark 的数据污染问题，包括检测方法、对评估结果的影响量级、以及防泄漏设计（合成数据、时间窗口、私有 benchmark）。

**从泛主题收窄路径**：从"评测"收窄到"评测可信度"，再从泛 NLP 收窄到医疗领域 benchmark。

**核心研究问题**：
1. 医疗 benchmark 的数据污染有多严重？（有哪些量化证据）
2. 污染检测有哪些方法？（n-gram 匹配、成员推理、时间分割）
3. 防泄漏设计有哪些技术路径？（合成场景、持续更新、私有评测）
4. 动态评估如何揭示"虚高表现"？

**为什么适合写 Review Paper**：T6 簇 18 篇，2023 年起出现，2025-2026 年密集产出，增速最快。尚无专门聚焦医疗领域的污染综述。

**潜在创新点**：聚焦医疗 benchmark 特有的污染场景（MIMIC 等公开数据集已被训练）；提出医疗 benchmark 防泄漏设计清单。

**范围判断**：适中偏窄。18 篇文献偏少，建议补充通用 LLM 污染文献。

---

### 选题 4

**英文标题**：Laboratory Test Ordering Prediction from Electronic Health Records: From Clinical Decision Support to Benchmark Design

**中文解释**：综述从 EHR 预测检查检验医嘱的方法，覆盖 CDS 系统、推荐算法、预测建模，并讨论其作为 benchmark 任务的潜力。

**从泛主题收窄路径**：从"临床决策"收窄到"检查检验预测"这一具体任务，从"CDS 应用"收窄到"预测建模方法"。

**核心研究问题**：
1. 检查检验医嘱预测有哪些方法范式？（规则→统计→机器学习→LLM）
2. 现有方法的答案/推荐逻辑是什么？（指南驱动 vs RWD 统计 vs 混合）
3. 检查检验预测与检查检验推荐有何方法学差异？
4. 该任务作为 LLM benchmark 有哪些设计考虑？

**为什么适合写 Review Paper**：T5 簇 27 篇，横跨 CDS 和检查预测。该任务作为 benchmark 尚无先例，作为 CDS 组件有扎实文献。

**潜在创新点**：提出"检查检验预测从 CDS 工具到 benchmark 任务"的范式演进框架；系统对比 OrderRex 等先例与 MCQ 评测的方法学差异。

**范围判断**：适中。27 篇分布在临床信息学和 ML 两个社区，需跨社区整合。

---

### 选题 5

**英文标题**：Construct Validity in Medical LLM Evaluation: Critiques, Current Gaps, and a Research Agenda

**中文解释**：综述对医疗 LLM benchmark 的效度批判，梳理建构效度缺失的表现、现有批评的理论框架、以及改进方向。

**核心研究问题**：
1. 现有医疗 LLM benchmark 存在哪些效度缺陷？（模式识别 vs 真实知识、leaderboard 失真）
2. 建构效度在医疗 AI 语境下如何定义和测量？
3. 动态评估、LLM-as-Judge 等新方法如何弥补效度缺口？
4. 未来 benchmark 设计应遵循哪些效度原则？

**为什么适合写 Review Paper**：T8 簇 15 篇批判性文献集中在 2024-2026 年，领域正在反思。适合做观点驱动的综述并提出研究议程。

**潜在创新点**：首次将心理测量学的建构效度框架系统引入医疗 LLM benchmark 评估；提出 benchmark 效度评估清单。

**范围判断**：偏窄。批判性文献数量有限（15 篇），需整合 T1/T2 簇中被批判的 benchmark 文献。

---

### 选题 6

**英文标题**：Knowledge Graphs and Association Rule Mining from Electronic Health Records: Methods, Clinical Applications, and Integration with Language Models

**中文解释**：综述从 EHR 构建知识图谱和挖掘关联规则的方法，及其在诊断预测、药物推荐、题目生成中的临床应用。

**核心研究问题**：
1. EHR→知识图谱有哪些构建方法？（共现统计、嵌入学习、LLM 增强）
2. 关联规则挖掘在临床场景中有哪些应用？（共病模式、检查预测、风险分层）
3. 知识图谱与 LLM 如何融合？（KG-enhanced LLM、LLM-enhanced KG）

**为什么适合写 Review Paper**：T4 簇 37 篇，文献量充足，方法论成熟（2011-2026 跨度）。缺乏 KG+LLM 融合的整合视角。

**潜在创新点**：提出"统计关联→知识图谱→LLM 推理"的方法演进框架；连接关联规则挖掘与 MCQ 答案逻辑。

**范围判断**：适中偏宽。37 篇需按"方法"vs"应用"切割。

---

### 选题 7

**英文标题**：Synthetic Electronic Health Record Data for Clinical AI: Generation Methods, Benchmarking, and Privacy-Utility Trade-offs

**中文解释**：综述合成 EHR 数据的生成方法（GAN→Transformer→Diffusion）、质量评估框架、以及隐私-效用权衡。

**核心研究问题**：
1. 合成 EHR 经历了哪些技术阶段？
2. 如何评估合成 EHR 的质量？（保真度、效用、隐私）
3. 合成 EHR 在 benchmark 构建中扮演什么角色？（防泄漏、隐私保护）

**为什么适合写 Review Paper**：T7 簇 12 篇，已有方法学综述（2025），但缺乏聚焦"合成 EHR 用于 benchmark 构建"的角度。

**范围判断**：偏窄。文献量偏少（12 篇），需补充通用合成数据文献。

---

### 选题 8

**英文标题**：Benchmark Design Paradigms for Medical AI: A Comparative Review of Answer Sources, Task Formats, and Clinical Alignment

**中文解释**：从 benchmark 设计的方法学角度，系统对比医疗 AI benchmark 的答案来源（考试标准答案 vs 专家共识 vs RWD 统计 vs 金标准结局）、任务格式（MCQ vs QA vs 检索 vs 预测）和临床对齐程度。

**核心研究问题**：
1. 医疗 benchmark 的答案来源有哪些范式？各自有何效度假设？
2. 不同任务格式（MCQ/open-ended/agent/SQL）测的是 LLM 的什么能力？
3. benchmark 与真实临床工作流的距离如何衡量？

**为什么适合写 Review Paper**：该选题横跨 T1/T2/T3/T8 四个簇，是对整个文献池最高层的整合。适合做视角型综述。

**潜在创新点**：提出"答案来源 × 任务格式 × 临床对齐"三维 benchmark 分类框架。

**范围判断**：偏宽。覆盖面太大，需明确聚焦在"设计方法学"。

---

## 4. 候选选题评分

评分维度 1-5 分（5 为最优）。评分依据严格基于文献池中的文献数量、质量、时效性和文献覆盖度。

| 排名 | 英文题目 | Novelty | Timeliness | Lit Support | Scope Clarity | SCI Potential | Interdiscip | Specificity | 综合 | 主要理由 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | EHR-Derived Benchmarks (选题1) | 4 | 5 | 4 | 5 | 5 | 5 | 5 | **33** | 方向刚成形（2024-2026 集中），文献充足（23+），分类框架空白，与项目最直接对齐 |
| 2 | Data Contamination (选题3) | 5 | 5 | 3 | 5 | 4 | 4 | 5 | **31** | 增速最快的新兴热点，医疗专用污染综述空白，但文献量偏少（18） |
| 3 | Lab Test Ordering Prediction (选题4) | 5 | 4 | 3 | 4 | 4 | 5 | 5 | **30** | 作为 benchmark 任务文献空白=高新颖性，CDS 方向有基础，跨学科价值高 |
| 4 | Automated MCQ Generation (选题2) | 3 | 4 | 5 | 4 | 4 | 4 | 4 | **28** | 文献最充足（50），但方向已部分被现有综述覆盖，需找准差异化角度 |
| 5 | Construct Validity (选题5) | 5 | 4 | 2 | 4 | 4 | 4 | 4 | **27** | 观点新颖但文献支撑偏弱（15），适合做 perspective 而非全面综述 |
| 6 | Benchmark Design Paradigms (选题8) | 4 | 4 | 4 | 2 | 3 | 5 | 2 | **24** | 视角最高但范围过宽，易写成泛泛综述 |
| 7 | EHR KG & Association Rule (选题6) | 2 | 3 | 5 | 3 | 4 | 4 | 3 | **24** | 文献充足但方向成熟，已有综述，需靠 KG+LLM 融合找新意 |
| 8 | Synthetic EHR Data (选题7) | 3 | 4 | 2 | 4 | 3 | 3 | 4 | **23** | 文献量不足（12），已有方法学综述（2025），空间有限 |

**排序逻辑**：选题 1 综合得分最高（33），在时效性、范围清晰度、SCI 潜力、交叉学科价值和具体性上均得满分。选题 3 和 4 的新颖性得分最高（5），但文献支撑受限。选题 2 文献最充足但差异化空间被压缩。

---

## 5. 推荐最优选题

| 推荐优先级 | 英文题目 | 推荐理由 | 适合期刊方向 | 潜在亮点 | 风险或不足 | 强化建议 |
|---|---|---|---|---|---|---|
| **1（首选）** | From RWD to Evaluation: EHR-Derived Benchmarks | 方向 2024-2026 年刚成形但无系统综述；文献池中 23+ 篇直接命中；与本项目研究方向完全对齐 | JAMIA; npj Digital Medicine; J Biomedical Informatics; BMC Med Inform Decis Mak | "考试式 vs EHR 式"二分法分类框架；答案来源谱系梳理；效度批判与设计整合 | T2 簇 23 篇偏少，需整合 T1 簇中被批判的考试式 benchmark 做对比 | 补充 T1 簇经典 benchmark（MedQA、MedMCQA）做对比锚点；补充 T8 效度批判文献做理论框架 |
| **2（备选）** | Data Contamination in Medical Benchmarks | 2023 年起新兴、增速最快；医疗专用污染综述空白；与项目防泄漏设计直接相关 | J Biomedical Informatics; BMC Med Res Methodol; npj Digital Medicine | 医疗特有污染场景（MIMIC 等公开数据集已被训练）；防泄漏设计清单 | T6 簇仅 18 篇，需补充通用 NLP 污染文献 | 补充通用 LLM 污染综述做方法学背景 |
| **3（备选）** | Lab Test Ordering Prediction: From CDS to Benchmark | 作为 benchmark 任务文献空白=最高新颖性；跨学科（信息学+ML+临床检验）；与项目题型 1 直接对齐 | JAMIA; J Clinical Bioinformatics; Clinical Chemistry; J Biomedical Informatics | "CDS 工具→benchmark 任务"范式演进框架；OrderRex 等先例系统对比 | T5 簇 27 篇分布散（CDS 工程占多数），纯预测建模文献少 | 补充实验室医学 CDS 文献和 ML 医嘱预测文献 |

**为什么不选选题 2（MCQ 生成）作为首选**：虽然文献量最大（50 篇），但已有至少 2 篇 2024-2025 年的 scoping review / narrative review 覆盖了该方向，差异化空间被压缩。除非找到独特切入角度（如"答案逻辑分离"或"知识图谱引导干扰项"），否则增量贡献有限。

---

## 6. 最优选题 Review Paper 结构

为排名第一的选题 **"From Real-World Data to Evaluation: A Review of EHR-Derived Benchmarks for Medical Large Language Models"** 设计文章框架。

| 章节 | 英文标题 | 中文说明 | 本节重点讨论内容 | 可对应的文献类型 |
|---|---|---|---|---|
| 1 | Introduction | 引言 | EHR 数据丰富性 vs 考试式 benchmark 局限性；引出 EHR 衍生 benchmark 动机；界定综述范围和二分法分类框架 | T1/T2/T8 文献 |
| 2 | Background: From Exam Benchmarks to EHR Benchmarks | 背景 | 简述 MedQA/MedMCQA 等考试式 benchmark 的范式和局限；MIMIC-IV 等公开 EHR 数据集的可用性；LLM 临床能力评估需求的转变 | MedQA (Singhal 2023); MIMIC-IV Benchmark (2017); USMLE 系统综述 (2024) |
| 3 | Taxonomy of EHR-Derived Benchmarks | 分类体系 | **核心贡献章**。提出分类框架：按答案来源（金标准结局 / 专家标注 / RWD 统计）× 任务格式（预测 / QA / SQL / 检索 / Agent）× 数据模态（结构化 / 文本 / 多模态）三维分类 | EHRNoteQA; LLMEval-Med; EHR-Complex; CliniQ; EHRSQL; MIMIC-IV Benchmark |
| 4 | Answer Sources and Ground Truth Construction | 答案来源与金标准构建 | 系统对比不同答案范式的效度假设：金标准结局变量 vs 专家共识 vs RWD 统计分布 P(检查|特征)；讨论"真实世界最可能选择"vs"临床最佳选择"的语义差异 | OrderRex (2016); LLMEval-Med (2025); Li et al. 2020; 关联规则挖掘文献 (T4) |
| 5 | Task Design and Clinical Alignment | 任务设计与临床对齐 | 分析 EHR benchmark 任务的临床真实性：从离线预测到 agent 模拟；讨论 benchmark 任务与真实临床工作流的距离 | EHR-Complex (2026); ClinicalLab (2024); MediQ (2024); MedQA-CS (2024) |
| 6 | Data Quality, Privacy, and Contamination | 数据质量、隐私与污染 | EHR 特有挑战：数据质量评估、隐私保护（合成数据）、训练数据泄漏（公开 EHR 已被 LLM 训练） | LiveMedBench (2026); LiveClin (2026); SynEHRgy (2024); CONFIDE (2024); T6/T7 文献 |
| 7 | Evaluation Metrics and Validity | 评估指标与效度 | 讨论 EHR benchmark 评估指标（准确率/F1/ROUGE/LLM-as-Judge）；建构效度问题；动态评估揭示的虚高表现 | Construct Validity (2025); Inflated Excellence (2025); LLM-as-Judge (2026); Beyond the Leaderboard (2025) |
| 8 | Challenges and Future Directions | 挑战与未来方向 | 综合：数据污染防护、效度论证标准化、多模态 EHR benchmark、持续更新机制、RWD 统计答案新范式 | T6/T7/T8 全簇文献 |
| 9 | Conclusion | 结论 | 总结分类框架和主要发现；EHR 衍生 benchmark 从"数据可用性驱动"向"效度驱动"的演进趋势 | — |

**文献充足性说明**：第 3、4 章是核心贡献章，T2 簇 23 篇 + T1 簇对比文献支撑充分。第 6 章需整合 T6/T7 文献（约 30 篇），支撑充足。第 7 章依赖 T8 效度批判文献（15 篇），需适当补充心理测量学理论文献。

---

## 7. 补充文献建议

当前文献池（289 篇）对首选选题的支撑评估：

| 需要补充的方向 | 当前覆盖 | 是否需要补充 | 建议补充类型 |
|---|---|---|---|
| 近 3-5 年 EHR benchmark 文献 | 2024-2026 年文献占 81%，时效性好 | **部分需要** | 补充 2025-2026 年最新 benchmark（可能有投稿中/刚发表的未覆盖） |
| 高被引经典 benchmark 文献 | MedQA、MIMIC-IV Benchmark 已覆盖 | 不需要 | — |
| 基础理论（建构效度/心理测量学） | 仅 15 篇批判性文献 | **需要** | 补充心理测量学经典文献（Messick 1995 建构效度理论）和 AI 公平性文献 |
| 方法类文献（EHR→知识图谱→MCQ） | T4 簇 37 篇覆盖较好 | 不需要 | — |
| 数据污染/防泄漏方法文献 | T6 簇 18 篇，偏少 | **需要** | 补充通用 NLP/LLM 污染综述（Balloccu 2024、Xu 2024 等） |
| EHR benchmark 临床验证文献 | 仅有 LLMEval-Med 做了医师验证 | **需要** | 补充 benchmark 临床效度验证的方法论文献 |
| 跨学科文献（临床信息学标准） | 部分覆盖 | **部分需要** | 补充 OMOP/FHIR 等 EHR 标准化和互操作性文献 |

**总结**：文献池对首选选题总体支撑充分，主要缺口在建构效度理论文献和数据污染方法文献，建议各补充 5-10 篇。备选选题 2（污染）和 3（检查预测）的文献缺口更大，需补充 15-20 篇。

---

## 8. 最终建议

**当前文献池最适合支撑的综述类型**：Narrative Review 或 Scoping Review。文献池覆盖面广（横跨评测、生成、挖掘、防护），但各子方向的原始研究质量参差，适合做范围界定和分类框架式的 Scoping Review，而非严格筛选的 Systematic Review。

**最值得优先考虑的选题**：选题 1 —— "From Real-World Data to Evaluation: A Review of EHR-Derived Benchmarks for Medical Large Language Models"。

**收窄的核心逻辑**：从泛主题"RWD/EHR 临床 LLM 评测基准"出发，沿"评测"维度收窄到 EHR 衍生 benchmark（排除考试式），沿"数据源"维度收窄到结构化 EHR（排除纯文本 QA），形成聚焦于"EHR 数据→benchmark 任务→答案来源→效度论证"方法学链条的综述。这一收窄逻辑避开了已被多篇综述覆盖的考试式 benchmark 和 MCQ 生成方向，切入了一个 2024 年才成形、尚无系统综述的新兴交叉地带。

**文献池优势**：时效性极强（81% 文献在 2022-2026 年）；覆盖完整方法链（从数据源到效度批判）；交叉学科覆盖好（信息学+NLP+教育测量学）。

**文献池不足**：WoS 未纳入（可能遗漏经典高被引文献）；建构效度理论文献薄弱；检查检验预测方向文献分散。

**是否需要补充文献**：需要，但补充量可控（约 10-20 篇），集中在建构效度理论和数据污染方法两个方向。

**下一步**：确认选题后，从选题进入正式写作的路径为：(1) 精读 T2 簇核心文献（约 15 篇），提取 benchmark 设计要素；(2) 构建分类框架；(3) 补充理论文献；(4) 撰写大纲和各章节。
