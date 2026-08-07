# RWD Clinical Benchmark 文献检索综述（草稿）

> 生成日期：2026-08-06 | 检索源：PubMed E-utilities + arXiv API | 检索式见 `research/literature_search.py`
> Semantic Scholar 因限速未纳入首轮，可后续补充

## 1. 检索概览

六主题簇 × 双源（PubMed + arXiv），每簇取 Top 15，另对 C 簇做术语补搜（CPOE / order recommendation）。

| 簇 | 主题 | PubMed 命中 | arXiv 命中 | 命中质量 |
|---|---|---:|---:|---|
| A | 医疗 LLM 评测基准 | 789 | 690 | ★★★★ 高，覆盖 Med-PaLM/Med-Gemini/DeepSeek + 真实世界 benchmark |
| B | EHR/RWD/MIMIC 构建评测 | 1099 | 5570 | ★★★ 中高，MIMIC benchmark 专门文献命中好 |
| C | 检查医嘱预测 | 1199+865 | 59+15 | ★★ 偏低，确认该子领域文献稀少 |
| D | 关联规则/知识图谱临床挖掘 | 2317 | 226 | ★★★ 中，知识图谱+诊断预测命中好 |
| E | 自动 MCQ 生成与干扰项 | 551 | 95 | ★★★★ 高，AIG + LLM 干扰项方法命中好 |
| F | 评测质量保证与数据泄漏 | 16275 | 4000 | ★★★ PubMed 过宽，arXiv 命中关键污染/质量文献 |

**核心发现**：C 簇（检查医嘱预测）作为独立 benchmark 任务在文献中几乎没有直接先例——多数工作散落在 CPOE 系统实现、检验推荐、检查协议自动化中。这本身就是本项目"RWD 条件概率驱动的检查选择 benchmark"的方法学新颖性证据。

---

## 2. A 簇：医疗 LLM 评测基准

**与本项目的关系**：定新颖性。现有医疗 LLM benchmark 几乎全部基于考试题（USMLE/执业医师）或专家手写 QA，答案逻辑是"临床指南最佳选择"。本项目用 RWD 统计 `P(检查|特征)` 做"真实世界选择预测"，答案逻辑根本不同。

### 核心文献

1. **Singh et al. 2023, Nature** — Large language models encode clinical knowledge（Med-PaLM）
   DOI: 10.1038/s41586-023-06291-2 | Google 的医疗 LLM 里程碑，基于 USMLE/PMC 题目评估

2. **Toward expert-level medical question answering with large language models** (Nature Medicine 2025)
   DOI: 10.1038/s41591-024-03423-7 | Med-Gemini，专家级医学 QA，仍基于考试题范式

3. **Comparative benchmarking of the DeepSeek LLM on medical tasks and clinical reasoning** (Nature Medicine 2025)
   DOI: 10.1038/s41591-025-03726-3 | DeepSeek 医学评测，与本项目 LLM 后端（deepseek-v4-flash）直接相关

4. **LLM Influence on Diagnostic Reasoning: A Randomized Clinical Trial** (JAMA Netw Open 2024)
   DOI: 10.1001/jamanetworkopen.2024.40969 | RCT 评估 LLM 对诊断推理的影响，评估方法学参考

5. **LLMEval-Med: A Real-world Clinical Benchmark for Medical LLMs with Physician Validation** (arXiv 2506.04078)
   ★**最相关**：标题即"真实世界临床 benchmark + 医师验证"，需精读其答案逻辑是否与本项目重叠

6. **HealthBranches: Synthesizing Clinically-Grounded QA Datasets via Decision Pathways** (arXiv 2508.07308)
   ★决策路径驱动 QA 合成，方法学思路接近本项目"临床流程→决策点→题目"

7. **Pattern Recognition or Medical Knowledge? The Problem with MCQs in Medicine** (arXiv 2406.02394)
   ★MCQ 评估的批判性分析，论证为何考试式 MCQ 不能反映真实临床能力——本项目用 RWD 数据正是回应此批评

8. **It is Too Many Options: Pitfalls of MCQs in Generative AI and Medical Education** (arXiv 2503.13508)
   MCQ 格式在生成式 AI 评估中的陷阱

9. **When Cases Get Rare: A Retrieval Benchmark for Off-Guideline Clinical Question Answering** (arXiv 2605.21807)
   非指南场景的临床 QA，呼应本项目"RWD 真实选择"vs"指南推荐"的区分

---

## 3. B 簇：EHR / RWD / MIMIC 构建评测任务

**与本项目的关系**：证明从 MIMIC-IV 构建评测任务有先例，但现有 MIMIC benchmark 多做临床预测（死亡率/再入院/生存），无人做过 MCQ 题目生成。

### 核心文献

1. **Benchmarking with MIMIC-IV, an irregular, spare clinical time series dataset** (arXiv 2401.15290)
   MIMIC-IV benchmark 任务集合（预测类），本项目的数据基底参照

2. **Revisiting the MIMIC-IV Benchmark: Experiments Using Language Models for EHR** (arXiv 2504.20547)
   用 LM 重跑 MIMIC-IV benchmark，方法学参照

3. **Benchmarking Foundation Models with Multimodal Public Electronic Health Records** (arXiv 2507.14824)
   多模态 EHR 基础模型 benchmark

4. **HypEHR: Hyperbolic Modeling of EHR for Efficient Question Answering** (arXiv 2604.21027)
   EHR 上的 QA 任务，与本项目"从 EHR 生成题目"方向最接近

5. **Large Language Model Benchmarks in Medical Tasks** (arXiv 2410.21348)
   综述，适合做 Related Work 的分类框架参照

6. **A survey of using EHR as real-world evidence for discovering and validating new drug indications** (arXiv 2505.24767)
   EHR 作为 RWE 的方法学综述

---

## 4. C 簇：检查检验医嘱预测（题型 1 核心）

**与本项目的关系**：题型 1 的答案逻辑 `P(检查|特征)` 直接依赖此领域。文献稀少本身是新颖性证据——现有工作集中在 CPOE 系统实现和检验推荐，无人用条件概率分布做 benchmark 答案。

### 核心文献

1. **LaboRecommender: A recommender system for laboratory tests** (arXiv 2105.01209)
   ★**最直接相关**：实验室检验推荐系统，与题型 1 "预测最可能选择的检查"高度对应

2. **Evaluation of Embeddings of Laboratory Test Codes for Patients at a Cancer Center** (arXiv 1907.09600)
   实验室检验编码的 embedding，题型 1 检查标准化的参考

3. **Computerized physician order entry and online decision support** (Ann Emerg Med 2004)
   DOI: 10.1197/j.aem.2004.08.007 | CPOE 领域奠基，历史参照

4. **Automated Protocoling for MRI Exams — Challenges and Solutions** (J Digit Imaging 2022)
   DOI: 10.1007/s10278-022-00610-1 | 检查协议自动化预测

5. **Feature importance analysis for patient management decisions** (arXiv 2605.04666)
   患者管理决策的特征重要性分析

### C 簇的关键结论

"检查检验医嘱预测"作为独立研究/benchmark 任务在文献中极度稀少。已有工作分三类：
- **CPOE 系统+决策支持**：偏工程实现，非统计预测
- **检验推荐系统**（LaboRecommender）：推荐算法视角，非 benchmark
- **检查协议自动化**（放射）：特定检查类型内的协议选择

本项目用 RWD 条件概率 `P(检查|特征)` 做 MCQ 答案，是该领域未见的方法。

---

## 5. D 簇：关联规则/知识图谱/条件概率临床挖掘

**与本项目的关系**：题型 1 的统计答案逻辑（条件概率 + lift + Wilson + Fisher）的方法学根基。Li 2020 是项目根基论文，需顺藤查施引文献。

### 核心文献

1. **Robustly Extracting Medical Knowledge from EHRs: A Case Study of Learning a Health Knowledge Graph** (arXiv 1910.01116)
   ★**最接近 Li 2020**：从 EHR 学习健康知识图谱，条件概率+共现关系构建

2. **Leveraging Medical Knowledge Graphs Into LLMs for Diagnosis Prediction** (JMIR 2025)
   DOI: 10.2196/58670 | 知识图谱+LLM 做诊断预测

3. **Intelligent EHRs: Predicting Procedure Codes From Diagnosis Codes** (arXiv 1712.00481)
   ★诊断→操作预测，接近本项目"特征→检查"的条件预测逻辑

4. **Modeling EHR data using a knowledge-graph-embedded topic model** (arXiv 2206.01436)
   知识图谱嵌入的 EHR 建模

5. **Graph Neural Network-Based Diagnosis Prediction** (Big Data 2020)
   DOI: 10.1089/big.2020.0070 | GNN 诊断预测

6. **Building a PubMed knowledge graph** (Scientific Data 2020)
   DOI: 10.1038/s41597-020-0543-2 | 文献级知识图谱构建方法

---

## 6. E 簇：自动 MCQ 生成与干扰项构造

**与本项目的关系**：题型 1 的 Stage 6（模型生成题干）和 Stage 5（干扰项选择）的方法学参照。本项目创新在于"统计答案先于语言生成"+"程序锁定选项"，现有 AIG 工作多让模型同时决定答案和题目。

### 核心文献

1. **Feasibility assurance: a review of automatic item generation in medical assessment** (Adv Health Sci Educ 2022)
   DOI: 10.1007/s10459-022-10092-z | ★AIG 在医学评估中的综述，必引

2. **Using Automatic Item Generation to Create MCQs for Pharmacy Assessment** (Am J Pharm Educ 2023)
   DOI: 10.1016/j.ajpe.2023.100081 | AIG 具体方法实现

3. **LLM Clinical Vignettes and MCQs for Postgraduate Medical Education** (Acad Med 2025)
   DOI: 10.1097/ACM.0000000000006137 | LLM 生成临床情景+MCQ

4. **The Generation and Use of Medical MCQs: A Narrative Review** (Adv Med Educ Pract 2025)
   DOI: 10.2147/AMEP.S513119 | 医学 MCQ 生成综述

5. **Distractor generation for MCQs with predictive prompting and LLMs** (arXiv 2307.16338)
   ★LLM 干扰项生成方法，直接对应 Stage 5

6. **Improving Automated Distractor Generation with Overgenerate-and-rank** (arXiv 2405.05144)
   ★overgenerate-and-rank 干扰项策略，本项目干扰项排序策略的方法参照

7. **Generating AI Literacy MCQs: A Multi-Agent LLM Approach** (arXiv 2412.00970)
   多 Agent LLM 出题方法

---

## 7. F 簇：评测质量保证与数据泄漏

**与本项目的关系**：题型 1 的多层审核（自动审题+人工审核+Gold 门禁）和数据安全（禁止字段校验、源文本重合检测）的质量保证学理基础。

### 核心文献

1. **LiveMedBench: A Contamination-Free Medical Benchmark for LLMs** (arXiv 2602.10367)
   ★无污染医疗 benchmark，直接对应本项目"合成场景+源文本重合检测"的反泄漏设计

2. **NLP Evaluation in trouble: On the Need to Measure LLM Data Contamination for each Benchmark** (arXiv 2310.18018)
   ★关键文献：论证每个 benchmark 都需测量 LLM 数据污染

3. **Towards Contamination Resistant Benchmarks** (arXiv 2508.08389)
   抗污染 benchmark 设计原则

4. **Beyond the Leaderboard: Rethinking Medical Benchmarks for LLMs** (arXiv 2508.04325)
   ★批判性分析：重新思考医疗 LLM benchmark 设计，呼应本项目"真实世界选择预测"vs"考试题"的范式转变

5. **ClinicalLab: Aligning Agents for Multi-Departmental Clinical Diagnostics in the Real World** (arXiv 2406.13890)
   真实世界多科室临床诊断 agent，方法学+评测参照

6. **The DRAGON benchmark for clinical NLP** (JAMIA 2025)
   DOI: 10.1038/s41746-025-01626-x | 临床 NLP benchmark 质量设计

7. **Development and validation of the provider documentation summarization quality instrument for LLMs** (JAMIA 2025)
   DOI: 10.1093/jamia/ocaf068 | LLM 医疗文本质量评估工具验证方法

---

## 8. 对 benchmark 新颖性的初步判断

综合六簇文献，本项目的方法学新颖性体现在三个层面：

1. **答案逻辑创新**：现有医疗 LLM benchmark 答案几乎全部来自专家共识/考试标准答案/指南推荐。本项目用 RWD 条件概率 `P(检查|特征)` 排名第一做答案，语义是"真实世界最可能选择"而非"最佳选择"。A 簇文献（尤其 Pattern Recognition or Medical Knowledge? 和 Beyond the Leaderboard）已批评考试式 MCQ 不能反映真实临床能力，本项目正面回应。

2. **数据源-任务耦合创新**：B 簇文献证实 MIMIC-IV benchmark 普遍做临床预测（死亡率/再入院），无人从 MIMIC visit 数据生成 MCQ。C 簇证实检查医嘱预测作为独立任务文献稀少。本项目首次将"RWD 统计关联→MCQ 答案→LLM 评测"串联。

3. **生成-审核分离架构创新**：E 簇文献中 AIG/LLM 出题多让模型同时决定答案和题目。本项目坚持"统计答案先于语言生成"+"程序锁定选项"+"独立自动审题+人工 Gold 门禁"，在 F 簇的污染/质量文献框架下是有意识的设计选择。

## 9. 待补充

- **Semantic Scholar 引用网络**：S2 限速未跑通，后续可用 API key（100 req/s）补做 Li 2020 施引文献分析和 citation graph 扩展
- **LLMEval-Med / HealthBranches 精读**：这两篇标题与本项目重叠度最高，需精读确认是否有 prior art 风险
- **CrossRef 补充**：可做 DOI 元数据补全和引用计数核对
- **Zotero 集合**：将核心文献导入 Zotero `RWD Benchmark 文献`集合管理
