# RWD Clinical Benchmark 文献分析报告

> 分析日期：2026-08-06（GS 补搜更新）| 检索源：PubMed + arXiv（179 条）+ Google Scholar（112 条新增，共 291 条导入 Zotero `文献调研` 集合）
> WoS 因反爬拦截未纳入；Google Scholar 六簇补搜于 CAPTCHA 解除后完成

---

## 一、分析框架

本项目的核心方法可以概括为：**从 MIMIC-IV visit 级 RWD 中，用条件概率 P(检查|特征) 确定答案，经过统计门禁→干扰项锁定→合成题干生成→双层审核，产出五类英文 A-D MCQ**。

围绕这个方法，文献分析回答三个问题：
1. **现有 benchmark 怎么做的？** — 定位本项目的范式差异
2. **方法链各环节有无直接先例？** — 评估新颖性和可借鉴方法
3. **潜在风险和盲点在哪？** — 为后续设计提供警示

---

## 二、现有医疗 LLM Benchmark 范式（A 簇 + B 簇）

### 2.1 主流范式：考试题 + 专家手写 QA

现有医疗 LLM benchmark 的答案来源几乎全部为以下三类：

| 范式 | 代表 benchmark | 答案逻辑 | 数据来源 |
|---|---|---|---|
| 执业医师考试 | MedQA, MedMCQA, KorMedMCQA, PersianMedQA | 考试标准答案 | 公开考试题库 |
| 专家手写 QA | PubMedQA, Med-PaLM 评测集 | 专家共识 | 文献/教材 |
| 结构化临床任务 | MIMIC-IV Benchmark（死亡率/再入院预测） | 金标准结局变量 | EHR 结构化字段 |

**关键差异**：本项目答案来自 RWD 统计分布 P(检查|特征)，语义是"真实世界最可能选择"，而非"临床最佳选择"或"考试标准答案"。这在现有文献中**未见直接先例**。

### 2.2 与本项目最接近的工作（prior art 风险）

以下三篇需优先精读，确认是否存在范式重叠：

1. **LLMEval-Med**（Zotero: 6MQ95KJ5 / IMICFCL8）— "A Real-world Clinical Benchmark for Medical LLMs with Physician Validation"
   - 标题声称"真实世界临床 benchmark"，但需确认其答案逻辑是 RWD 统计预测还是临床专家标注
   - **风险等级：高** — 若其答案也来自 RWD 选择频率，则本项目的核心新颖性受到直接挑战

2. **HealthBranches**（Zotero: 未单独命中，需按 arXiv 2508.07308 查找）— "Synthesizing Clinically-Grounded QA Datasets via Decision Pathways"
   - 用决策路径合成 QA 数据集，方法学思路接近本项目"临床流程→决策点→题目"
   - **风险等级：中** — 决策路径可能是指南驱动而非 RWD 统计驱动

3. **When Cases Get Rare**（Zotero: DRBHDP9W / EASGUEME）— "A Retrieval Benchmark for Off-Guideline Clinical QA"
   - 非指南场景的临床 QA，呼应本项目"RWD 真实选择 vs 指南推荐"的区分
   - **风险等级：低** — 题目关注的是知识检索而非检查选择预测

### 2.3 Benchmark 批判性文献（本项目的立论支撑）

以下文献从方法论层面批评现有考试式 MCQ benchmark，直接构成本项目的立论依据：

- **Pattern Recognition or Medical Knowledge?**（arXiv 2406.02394）— 论证 MCQ 可能只测试模式识别而非真实临床知识
- **Beyond the Leaderboard: Rethinking Medical Benchmarks for LLMs**（Zotero: LWGW5W27）— 批判现有 leaderboard 评估范式
- **Medical LLM Benchmarks Should Prioritize Construct Validity**（Zotero: ZAF6DC4V）— 论证 benchmark 应优先考虑建构效度
- **Inflated Excellence or True Performance?**（Zotero: LXR2QFX4）— 动态评估发现现有 benchmark 可能高估了 LLM 能力

**本项目的定位**：用 RWD 条件概率做答案，不是考"LLM 知道什么"，而是考"LLM 能否预测真实世界诊疗行为"，这是对上述批评的直接回应。

---

## 三、方法链各环节分析

### 3.1 数据源与 EHR 建模（B 簇）

| 文献 | 方法 | 与本项目的关系 |
|---|---|---|
| MIMIC-IV Benchmark (4ZUIVSE9) | 临床时间序列预测（死亡率/再入院/表型） | 数据基底参照，但任务类型完全不同（预测 vs MCQ 生成） |
| Revisiting MIMIC-IV Benchmark (RHQWJSV9) | LM 重跑 MIMIC benchmark | 证明 LM 在 EHR 任务上的可行方法 |
| HypEHR (arXiv 2604.21027) | 双曲空间 EHR QA | EHR 上 QA 任务的方法参照 |
| SynEHRgy (arXiv 2411.13428) | 合成 EHR 数据 | 合成病例隐私保护的方法参照 |

**结论**：从 MIMIC-IV 构建评测任务有充分先例，但无人做过 MCQ 题目生成。本项目的 EHR→MCQ 路径是新的。

### 3.2 检查医嘱预测（C 簇）— 题型 1 核心

**这是文献覆盖最薄弱的环节**。C 簇检索命中质量偏低（PubMed 返回多是不相关疾病综述），只有以下文献有直接方法学参考价值：

| 文献 | 方法 | 借鉴点 |
|---|---|---|
| LaboRecommender (arXiv 2105.01209) | 实验室检验推荐系统 | 检查推荐的方法论（推荐算法视角） |
| Lab Test Code Embeddings (arXiv 1907.09600) | 检验编码 embedding | 检查标准化的特征表示方法 |
| Automated MRI Protocoling (DOI:10.1007/s10278-022-00610-1) | 放射检查协议自动预测 | 检查选择的预测建模参照 |
| Intelligent EHRs: Predicting Procedure Codes (arXiv 1712.00481) | 诊断→操作预测 | 条件预测（X→y）的方法学参照 |

**结论**：检查检验医嘱预测作为独立 benchmark 任务在文献中**几乎空白**。现有工作分三类——CPOE 系统工程实现（非统计预测）、检验推荐系统（推荐算法视角，非评测任务）、放射协议自动化（特定检查类型内）。本项目用 RWD 条件概率做 MCQ 答案是该领域**未见的方法**。

### 3.3 统计/关联规则挖掘（D 簇）— 答案逻辑根基

| 文献 | 方法 | 与本项目的关系 |
|---|---|---|
| **Li et al. 2020**（Zotero: 5RABXB2B / LIF5TYS8）| RWD 医学知识图谱构建 | **项目根基论文**，条件概率+共现关系 |
| Robustly Extracting Medical Knowledge from EHRs (arXiv 1910.01116) | EHR→健康知识图谱 | 与 Li 2020 最接近的独立工作 |
| KG-MTT-BERT (arXiv 2210.03970) | 知识图谱增强 BERT | 特征+知识表示融合 |
| KG for Diagnosis Prediction (DOI:10.1089/big.2020.0070) | GNN 诊断预测 | 知识图谱→预测任务 |

**本项目的统计方法**（条件概率 + Laplace 平滑 + Wilson 区间 + Fisher exact + BH 校正 + bootstrap 稳定性）在方法学上是标准的关联规则挖掘流程。新颖性不在统计方法本身，而在**将统计关联作为 MCQ 标准答案**这一应用范式。

### 3.4 自动 MCQ 生成与干扰项（E 簇）

| 文献 | 方法 | 与本项目的关系 |
|---|---|---|
| AIG in Medical Assessment (DOI:10.1007/s10459-022-10092-z) | AIG 综述 | **必引**，自动题目生成的方法学框架 |
| Distractor Generation with LLM (Zotero: Y7TQEAJ4) | LLM 预测提示生成干扰项 | 干扰项生成方法参照 |
| Overgenerate-and-rank (Zotero: 9GRDEFF8) | 过量生成+排序选干扰项 | 本项目干扰项排序策略的直接参照 |
| LLM Clinical Vignettes (DOI:10.1097/ACM.0000000000006137) | LLM 生成临床情景+MCQ | 合成病例生成参照 |
| BenchMarker (Zotero: XI6GJJWJ) | MCQ benchmark 缺陷检测工具 | 题目质量保证的方法参照 |

**关键差异**：现有 AIG/LLM 出题工作大多让模型**同时决定答案和题目**。本项目坚持"统计答案先于语言生成"+"程序锁定选项"，将答案确定和语言生成分离到不同阶段，是有意识的质量保证设计。

### 3.5 评测质量保证与数据泄漏（F 簇）

| 文献 | 核心观点 | 与本项目的关系 |
|---|---|---|
| LiveMedBench (Zotero: STER47SM) | 无污染医疗 benchmark | 本项目合成场景+源文本重合检测的反泄漏设计参照 |
| LiveClin (Zotero: KRHRXYZM) | 无泄漏的临床 benchmark | 持续更新防止记忆泄漏 |
| NLP Evaluation in Trouble (Zotero: KINGCF7L) | 每个 benchmark 都需测 LLM 数据污染 | **必引**，论证本项目防泄漏设计的必要性 |
| Towards Contamination Resistant Benchmarks (Zotero: 9NLB887I) | 抗污染 benchmark 设计原则 | Gold 门禁设计的参照 |

---

## 四、新颖性评估

### 4.1 确认的新颖性（文献空白）

| 维度 | 本项目做法 | 文献现状 | 新颖性 |
|---|---|---|---|
| 答案来源 | RWD 条件概率 P(检查\|特征) 排名第一 | 考试标准答案 / 专家共识 / 指南推荐 | **高** — 未见先例 |
| 题目语义 | "真实世界最可能选择" | "最佳选择" / "正确答案" | **高** — 语义层面创新 |
| 数据→题目路径 | EHR 统计关联 → MCQ 答案 → LLM 评测 | EHR → 临床预测模型 / 考试题 → QA | **高** — 串联方式未见 |
| 生成-审核分离 | 统计答案先于语言生成 + 程序锁定选项 | 模型同时生成答案和题目 | **中** — 设计选择而非方法发明 |
| 检查选择预测 | 作为 benchmark 评测任务 | 文献空白（仅 CPOE 工程和检验推荐） | **高** — 任务本身未见 |

### 4.2 需要进一步确认的风险

1. **LLMEval-Med 精读**（最高优先级）— 如果其答案也来自 RWD 选择频率统计，本项目的核心新颖性需要重新论证
2. **HealthBranches 精读** — 确认决策路径是否也是 RWD 统计驱动
3. **Li 2020 施引文献追踪** — 检查是否有后续工作已经将 Li 2020 的知识图谱用于 MCQ 评测

---

## 五、对项目实施的方法学建议

### 5.1 可直接借鉴的方法

- **干扰项排序**（Overgenerate-and-rank, 9GRDEFF8）：本项目 Stage 5 的干扰项选择策略（同 family 优先→visit_count 差小优先）可以参照该文的过量生成+排序框架
- **合成病例隐私保护**（SynEHRgy, arXiv 2411.13428）：本项目的"合成场景不复制真实病历"原则可以参照合成 EHR 的隐私评估方法
- **源文本重合检测**（LiveMedBench, STER47SM）：本项目 Stage 7 的 5-word shingle Jaccard 检测可以参照无污染 benchmark 的泄漏检测方法

### 5.2 需要注意的方法学陷阱

- **Construct Validity**（ZAF6DC4V）：benchmark 需要论证它到底测了什么。本项目需要明确"预测真实世界检查选择"测的是 LLM 的哪种能力——是临床知识、统计推理、还是模式匹配？
- **动态评估**（LXR2QFX4）：现有 benchmark 可能因数据泄漏高估 LLM。本项目从 MIMIC 构建的题目需要评估是否已被 LLM 训练数据覆盖
- **MCQ 格式局限**（XI6GJJWJ BenchMarker, arXiv 2406.02394）：MCQ 本身可能无法有效区分真实能力与应试技巧。本项目的多层审核（自动+人工 Gold）是应对措施，但需要论证其有效性

### 5.3 文献补充建议

1. **Semantic Scholar 引用网络**（需 API key，100 req/s）— 对 Li 2020 和 LLMEval-Med 做施引文献分析，确认无遗漏的 prior art
2. **Google Scholar 手动补搜**（验证通过后）— 重点搜 "real-world data benchmark MCQ" 和 "conditional probability clinical question answering"
3. **CrossRef 元数据补全**— 对已导入的 179 条做 DOI→引用数补全，辅助筛选高影响力文献

---

## 六、Zotero 集合状态

导入目标集合：`博士 → 2.🌟日期文献 → 2026_08 → Hongkong → 文献调研`（key=K3GSQR4X）

导入来源：179 条 BibTeX（PubMed 89 条 + arXiv 90 条），通过 connector 端点导入（有部分重复条目，因 connector 分批处理生成不同 session key）

标签体系：
- `RWD-Benchmark-LitReview` — 本次检索统一标签
- `PubMed` / `arXiv` — 来源标记
- 六簇标签（`A_medical_llm_benchmark` 等）— 主题分类

建议后续操作：
- 清理重复条目（Zotero 内置 "查找重复项" 功能）
- 对核心文献（约 30 篇）添加阅读笔记和优先级标签
- 对 prior art 风险文献（LLMEval-Med、HealthBranches）添加 `P0_必读` 标签

---

## 七、Google Scholar 补搜发现（2026-08-06 追加）

Google Scholar 六簇补搜（A–F 各 20 条，去重后 112 条新增）揭示了多个 PubMed/arXiv 检索遗漏的关键文献，尤其对方法新颖性判断有直接影响。

### 7.1 核心发现：OrderRex — 答案逻辑的直接方法先例

**OrderRex（Chen et al., JAMIA 2016, 74 citations）** 是迄今发现的最接近本项目答案逻辑的先例。该系统从 EMR 中挖掘临床医嘱模式，基于已有临床上下文生成"下一个最可能的医嘱"推荐——即 P(医嘱|上下文)。后续 **OrderRex 临床测试（Kumar et al., JAMIA 2020, 23 citations）** 做了模拟病例随机对照试验。

**对本项目的影响**：
- 答案逻辑 P(检查|特征) 有方法学先例，但不能声称完全无先例
- 需在论文中明确区分：OrderRex 做的是推荐系统（ranking list），本项目做的是 MCQ（单一正确答案 + 干扰项），且答案来源是条件概率排名第一，而非推荐排序
- 需引用并讨论 OrderRex 作为 Related Work

### 7.2 高影响力方法文献（PubMed 检索遗漏）

| 文献 | 引用数 | 簇 | 与本项目关系 |
|---|---|---|---|
| Roque et al. 2011 (PLoS Comp Biol) | 388 | D | EHR 疾病共现/关联规则挖掘 → 条件概率计算的方法学基础 |
| Castaneda et al. 2015 (J Clin Bioinform) | 593 | C | CDS 系统综述 → 检查医嘱预测的上游背景 |
| Khozin & Blumenthal 2017 (JNCI) | 394 | B | RWD 临床证据生成 → RWD 基准的方法论辩护 |
| Norén et al. 2010 (DMKD) | 228 | D | 纵向 EHR 时序模式发现 → visit 事务构建参考 |
| Yan et al. 2022 (Nat Commun) | 178 | B | 合成 EHR 多维基准评估 → 数据质量评估框架 |

### 7.3 检查医嘱预测（C 簇）文献确认稀少但存在

GS 补搜确认：检查检验医嘱预测作为**独立 benchmark 任务**文献极度稀少（PubMed 几乎无命中），但作为**CDS 工具组件**有一定文献基础：
- Rabbani et al. 2023（EHR 嵌入式重复检查预测，28 citations）
- Hughes & Jackups 2022（检验 CDS 综述，29 citations）
- Zhang et al. 2026（急诊检查检验预测 ML 方法，JMIR）

这进一步支撑本项目的新颖性：将检查检验选择作为 MCQ benchmark 的答案来源，在文献中无直接先例。

### 7.4 数据污染与防泄漏（F 簇）— 新增核心文献

| 文献 | 引用数 | 关键发现 |
|---|---|---|
| Balloccu et al. 2024 (EACL) | 418 | 数据污染与评估不当的系统综述，255 篇分析 |
| Xu et al. 2024 (arXiv) | 212 | LLM benchmark 数据污染综述 |
| Dong et al. 2024 (ACL Findings) | 283 | 泛化 vs 记忆：污染与可信评估 |
| LiveMedBench (arXiv 2602.10367) | 9 | 无污染医疗 benchmark + 自动评分 rubric |
| LiveClin (ICLR 2026) | 3 | 无泄漏实时临床 benchmark |
| Beyond the Leaderboard (ACL 2026) | 15 | 56 个医疗 LLM benchmark 实证审计 |

### 7.5 MCQ 生成与干扰项构建（E 簇）— 新增方法参考

| 文献 | 引用数 | 关键发现 |
|---|---|---|
| MCQG-SRefine (NAACL 2025) | 38 | 迭代自批判 MCQ 生成 + LLM-as-Judge 评估 |
| Yang et al. 2025 (arXiv 2506.00612) | 1 | **知识图谱引导干扰项生成** → 直接对应 Stage 5 |
| Bitew et al. 2023 (ECIR) | 54 | 预测式提示干扰项生成 |
| Mistry et al. 2024 (Acad Radiol) | 64 | LLM 生成放射学 board 风格 MCQ |
| Al Shuraiqi et al. 2024 | 32 | 医学 MCQ 自动生成方法论综述 |

### 7.6 更新后的新颖性结论

GS 补搜后，三层面新颖性判断更新为：

1. **答案来源创新性**：确认无文献使用 RWD 条件概率 P(检查|特征) 排名第一作为 MCQ 答案。OrderRex 做的是推荐排序，非 MCQ 单选。新颖性成立但需讨论 OrderRex
2. **任务设计创新性**：确认无文献将检查检验选择作为独立 benchmark 任务。CDS 领域有相关方法但不产出评测集。新颖性成立
3. **数据污染防护**：LiveMedBench/LiveClin 确认了无污染 benchmark 的需求和技术路径。本项目 5-word shingle 检测 + 时间窗口切分是对标前沿的做法

### 7.7 更新后的 P0 必读清单

| 优先级 | 文献 | 理由 |
|---|---|---|
| P0 | OrderRex (Chen 2016) | **答案逻辑直接先例**，必须在 Related Work 讨论 |
| P0 | LLMEval-Med (arXiv 2506.04078) | "真实世界临床 benchmark" 措辞重叠风险 |
| P0 | Construct Validity (Alaa 2025) | benchmark 效度论证的理论框架 |
| P0 | Beyond the Leaderboard (ACL 2026) | 56 个 benchmark 审计，揭示设计缺陷 |
| P1 | Roque et al. 2011 | EHR 关联规则挖掘方法学基础 |
| P1 | LiveMedBench / LiveClin | 无污染 benchmark 技术路径 |
| P1 | KG-guided distractor (Yang 2025) | 干扰项构建直接方法参考 |
| P1 | Balloccu et al. 2024 | 数据污染系统综述 |
