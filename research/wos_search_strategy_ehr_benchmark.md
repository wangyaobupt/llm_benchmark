# WoS 检索策略设计：EHR 衍生医疗 LLM Benchmark 综述

> 综述主题：From Real-World Data to Evaluation: A Review of EHR-Derived Benchmarks for Medical Large Language Models
> 技能：`$wos-review-search-strategy`
> 目标数据库：Web of Science Core Collection
> 综述类型：Scoping Review / Narrative Review
> 设计日期：2026-08-06

---

## 1. 综述问题理解

### 核心研究对象

从电子病历（EHR）/真实世界数据（RWD）构建的大语言模型（LLM）临床评测基准。综述聚焦于"数据来源是 EHR/RWD 结构化或半结构化临床数据"的 benchmark，区别于考试式 MCQ benchmark（如 MedQA、USMLE）。

### 核心研究问题

1. 从 EHR/RWD 构建 LLM benchmark 的方法论有哪些？（数据源选择、任务设计、答案来源）
2. EHR benchmark 的答案来源有哪些范式？（金标准结局变量 vs 专家标注 vs RWD 统计分布）
3. EHR benchmark 的任务格式有哪些类型？（预测/QA/SQL/检索/Agent）
4. EHR benchmark 面临哪些特有挑战？（数据质量、隐私、训练数据泄漏、临床对齐）

### 合理假设

- 综述类型假设为 Scoping Review（文献池显示方向刚成形，适合范围界定而非系统筛选）。
- 时间范围不设硬性限制，但重点关注 2022-2026 年（LLM 时代），早期 EHR benchmark（如 2017 年 MIMIC-IV Benchmark）作为背景纳入。
- 不排除预印本，但在 WoS 中预印本自然较少。
- 医学/临床领域由 EHR 概念隐含限定，不单独设强制概念模块，但在高精确率方案中作为可选增强。

### 需确认的边界

- 是否纳入"EHR 数据挖掘/预测建模"但不产出 benchmark 的文献？假设不纳入主检索式（可用增强模块补充）。
- 是否纳入"合成 EHR 数据用于 benchmark"的文献？假设纳入（属于 benchmark 构建的技术路径）。

---

## 2. 概念模块与关键词矩阵

| 模块 | 概念模块 | 核心英文关键词 | 可选扩展词 | 可能产生噪声的词 | 使用说明 |
|---|---|---|---|---|---|
| A | EHR/RWD 数据源 | "electronic health record*" OR EHR OR "electronic medical record*" OR EMR OR MIMIC OR "real-world data" OR "real world data" OR RWD | "clinical data*" OR "health record*" OR "real-world evidence" OR RWE OR "clinical database" OR "medical record*" | "clinical data"（过于宽泛）；"health record*"（可能命中非电子化研究） | 核心词纳入主检索式；扩展词在高召回方案中使用 |
| B | Benchmark/评测 | benchmark* OR "evaluation dataset" OR "evaluation framework" OR "evaluation harness" OR "test suite" | evaluat* OR "assessment framework" OR "question answering dataset" OR "QA benchmark" OR "multiple-choice question*" OR MCQ | evaluat*（医学文献中极高频，如"clinical evaluation"）；assessment（同理过宽） | 核心词纳入主检索式；evaluat* 仅在高召回方案中配合 AND C 限定 |
| C | 大语言模型 | "large language model*" OR LLM OR LLMs OR GPT OR ChatGPT | "language model*" OR "foundation model*" OR "generative AI" OR "transformer model*" | "language model*"（可命中传统 NLP/语音模型）；"transformer model*"（过于宽泛） | 核心词纳入主检索式；扩展词在高召回方案中使用 |
| D（可选）| 医学/临床领域 | medical OR clinical OR healthcare OR biomedical | "health AI" OR "clinical AI" OR "medical AI" | medical/clinical 在医学文献中几乎全覆盖，作为 AND 限定无区分度 | 仅在高精确率方案中作为 NEAR 限定使用，不作独立 AND 模块 |

### 术语扩展说明

- **EHR/EMR**：两者在文献中经常互换使用，均需纳入。WoS 的 `*` 可覆盖 "record" 和 "records"。
- **MIMIC**：作为具体数据集名，检索 MIMIC 可命中大量 MIMIC-III/IV 相关工作，但也会命中非 benchmark 的预测建模论文（依赖 Module B 限定）。
- **"real-world data" vs "real world data"**：两种拼写形式均常见（有无连字符），WoS 的 `$` 通配符可覆盖部分变体，但最安全是两个都写。
- **LLM/LLMs**：WoS 中 `LLM` 作为独立词检索时，`$` 可覆盖复数。建议写 `LLM$` 或 `LLM OR LLMs`。
- **GPT/ChatGPT**：GPT 泛指 GPT 系列模型，ChatGPT 特指产品。两者需同时纳入以覆盖早期和近期文献。
- **benchmark\***：`*` 覆盖 "benchmark"、"benchmarks"、"benchmarking"，是 Module B 最核心的单一词。

---

## 3. 首选检索式：平衡型方案

兼顾查全率和查准率。三个概念模块用 AND 连接，每个模块内部用 OR 连接同义词。

```text
TS=(("electronic health record*" OR EHR OR "electronic medical record*" OR EMR OR MIMIC OR "real-world data" OR "real world data" OR RWD) AND (benchmark* OR "evaluation dataset" OR "evaluation framework" OR "evaluation harness" OR "test suite") AND ("large language model*" OR LLM OR LLMs OR GPT OR ChatGPT))
```

### 模块说明

- **Module A**（EHR/RWD）：覆盖 7 个核心数据源术语。文献池中 "electronic health record" 出现 67 次、"EHR" 44 次、"MIMIC" 9 次、"real-world" 19 次，合计覆盖 T2 簇绝大多数文献。
- **Module B**（Benchmark）：以 `benchmark*` 为核心词（文献池中出现 66 次），辅以 4 个评测方法变体。不使用裸 `evaluat*` 以避免医学文献中的海量噪声。
- **Module C**（LLM）：覆盖 5 个 LLM 术语。"large language model" 出现 59 次、"LLM" 31 次、"GPT" 3 次、"ChatGPT" 12 次。不使用 "language model*" 以避免传统 NLP 论文噪声。

### 预估结果量

三个模块 AND 交叉后，预估 WoS Core Collection 命中 200-500 篇。该方向 2022 年后才爆发，实际结果可能偏低（WoS 对预印本覆盖有限）。

---

## 4. 扩展检索式：高召回率方案

增加同义词、旧术语和拼写变体，减少限制条件。将 Module A 和 Module C 扩展到全部可选词，Module B 放宽到 `evaluat*`。

```text
TS=(("electronic health record*" OR EHR OR "electronic medical record*" OR EMR OR MIMIC OR "real-world data" OR "real world data" OR RWD OR "real-world evidence" OR RWE OR "clinical data*" OR "health record*" OR "clinical database" OR "medical record*") AND (benchmark* OR evaluat* OR "assessment framework" OR "question answering dataset" OR "QA benchmark" OR "test suite" OR "multiple-choice question*" OR MCQ) AND ("large language model*" OR LLM OR LLMs OR GPT OR ChatGPT OR "language model*" OR "foundation model*" OR "generative AI"))
```

### 与平衡型的差异

- Module A 新增 6 个扩展词（"clinical data*"、"health record*"、"real-world evidence" 等），可能命中纯数据挖掘但不产出 benchmark 的论文（依赖 Module B 限定）。
- Module B 从 `benchmark*` 核心词扩展到 `evaluat*`，会引入大量噪声（如 "clinical evaluation of treatment"），但配合 AND C 可大幅过滤。
- Module C 新增 "language model*"和 "foundation model*"，可能命中传统 NLP 论文。

### 噪声风险

预估命中 800-2000 篇，其中可能包含 40-60% 的不相关文献（EHR 预测建模、临床评估研究、NLP 通用方法）。需在结果页面中按学科类别（"Computer Science" 或 "Medical Informatics"）和年份（2022-2026）二次筛选。

---

## 5. 聚焦检索式：高精确率方案

使用 `NEAR/x` 限定共现距离，`TI=` 限定标题，减少噪声。

### 5.1 标题聚焦检索式

```text
TI=((EHR OR "electronic health record*" OR MIMIC OR "real-world" OR clinical OR medical) AND (benchmark* OR evaluation) AND (LLM OR "language model*" OR GPT))
```

标题中同时出现三模块术语的文献，相关性极高。预估命中 50-150 篇。

### 5.2 摘要聚焦检索式

```text
TS=((EHR OR "electronic health record*" OR MIMIC OR "real-world data" OR RWD) AND benchmark* AND ("large language model*" OR LLM OR LLMs OR GPT))
```

去掉 `evaluat*` 的宽泛扩展，只保留 `benchmark*` 作为 Module B，确保任务类型明确为 benchmark 而非泛化评估。预估命中 100-300 篇。

### 5.3 NEAR 邻近检索式

```text
TS=((EHR OR "electronic health record*" OR MIMIC) NEAR/5 (benchmark* OR "evaluation dataset") NEAR/5 ("large language model*" OR LLM OR GPT))
```

三个核心概念在 5 词窗口内共现，进一步排除松散相关文献。预估命中 30-80 篇。

---

## 6. 可选的专题增强模块

以下模块可按需附加到主检索式末尾，用于在特定子方向上补充文献。每个模块独立使用，不建议同时叠加多个。

### 6.1 答案来源与金标准构建

```text
AND TS=("ground truth" OR "gold standard" OR "answer source" OR "reference standard" OR "annotat*" OR "expert consensus")
```

适用场景：综述第 4 章"答案来源与金标准构建"需要补充文献时。

### 6.2 数据污染与防泄漏

```text
AND TS=("data contamination" OR "data leakage" OR memorization OR "training data" OR "test set contamination")
```

适用场景：综述第 6 章"数据质量、隐私与污染"需要补充文献时。

### 6.3 合成 EHR 数据

```text
AND TS=("synthetic data" OR "synthetic EHR" OR "data augmentation" OR "privacy-preserving" OR de-identif*)
```

适用场景：综述中讨论合成 EHR 用于 benchmark 防泄漏时。

### 6.4 临床决策支持与检查检验

```text
AND TS=("clinical decision support" OR CDS OR "lab test" OR "laboratory test" OR "test ordering" OR "order set*")
```

适用场景：综述中涉及检查检验预测作为 benchmark 任务时。

### 6.5 效度与评测方法论批判

```text
AND TS=("construct validity" OR "face validity" OR "benchmark critique" OR "evaluation framework" OR "rethinking" OR "leaderboard")
```

适用场景：综述第 7 章"评估指标与效度"需要补充批判性文献时。

---

## 7. 分步检索方案

在 Query Builder 中逐步观察结果数量，按以下集合操作：

```text
#1 TS=("electronic health record*" OR EHR OR "electronic medical record*" OR EMR OR MIMIC OR "real-world data" OR "real world data" OR RWD)

#2 TS=(benchmark* OR "evaluation dataset" OR "evaluation framework" OR "evaluation harness" OR "test suite")

#3 TS=("large language model*" OR LLM OR LLMs OR GPT OR ChatGPT)
```

### 组合建议

| 组合 | 检索式 | 预期结果量 | 适用阶段 |
|---|---|---|---|
| #1 AND #2 | EHR 数据 + benchmark | 500-1500 篇 | 了解 EHR benchmark 全貌（含非 LLM 工作） |
| #1 AND #3 | EHR 数据 + LLM | 1000-3000 篇 | 了解 EHR+LLM 全貌（含非 benchmark 工作） |
| #2 AND #3 | benchmark + LLM | 2000-5000 篇 | 了解 LLM benchmark 全貌（含非 EHR 工作） |
| **#1 AND #2 AND #3** | 三模块交集 | **200-500 篇** | **首选起始检索（= 平衡型方案）** |

### 起始建议

- **第一轮**：直接运行 `#1 AND #2 AND #3`（= 平衡型方案），观察命中量和 Top 20 结果的相关性。
- **如果结果太少**（<100 篇）：切换到高召回率方案（Section 4），或尝试 `#1 AND #3` 然后在结果中筛选 benchmark 相关论文。
- **如果结果太多**（>800 篇）：切换到高精确率方案（Section 5.2），或加 NEAR 限定（Section 5.3）。
- **不建议第一轮加入**：Module D（medical/clinical 限定词），因为 EHR 已隐含医学领域，额外加 medical/clinical 会因高频词产生反向噪声。

---

## 8. 结果数量异常时的调整建议

### 结果过多（>800 篇）

1. Module B 只保留 `benchmark*`，移除 "evaluation dataset/framework/harness"
2. 使用 `NEAR/5` 限定三模块共现距离（Section 5.3）
3. 将部分 Module A 词限定为 `TI=`：`TI=(EHR OR MIMIC OR "electronic health record*")`
4. 在结果页面按文献类型筛选 "Article" + "Review"，排除 "Editorial" 和 "Meeting Abstract"
5. 按学科类别筛选 "Medical Informatics" 或 "Computer Science Interdisciplinary Applications"

### 结果过少（<100 篇）

1. 检查 Module A 是否遗漏缩写——补充 "clinical data*" 和 "health record*"
2. 检查 Module C 是否遗漏模型名——补充 "Med-PaLM" OR "ClinicalBERT" OR "BioBERT" OR "MedGPT"
3. 放宽 Module B 到 `evaluat*`（配合 AND C 过滤）
4. 尝试两模块组合 `#1 AND #3`，在结果中手动筛选 benchmark 论文
5. 移除可能的 `NOT` 限定（本方案未使用 NOT，但如果用户自行添加了排除词，先移除）
6. 扩大 NEAR 距离：`NEAR/5` → `NEAR/10` 或 `NEAR/15`

### 结果相关性差

1. Top 20 中大量 EHR 预测建模论文（非 benchmark）：说明 Module B 的 `evaluat*` 过宽，收紧到 `benchmark*`
2. Top 20 中大量通用 NLP benchmark（非医疗）：说明 Module A 的 "clinical data*" 过宽，收紧到 EHR/MIMIC/RWD
3. Top 20 中大量医学教育评估论文（非 AI）：说明 Module B 的 "assessment" 过宽，收紧到 `benchmark*`

---

## 9. 后续筛选建议

检索完成后，在 WoS 结果页面中进一步设置以下筛选条件。以下均为结果页面操作，不写入核心检索式。

| 筛选维度 | 建议设置 | 理由 |
|---|---|---|
| 时间范围 | 2017-2026（MIMIC-IV Benchmark 发表年至今）| 2017 年前 EHR benchmark 概念尚未成形 |
| 文献类型 | Article + Review + Proceedings Paper | 排除 Editorial、Meeting Abstract、News Item |
| 学科类别 | Medical Informatics; Computer Science Interdisciplinary Applications; Health Care Sciences Services | 三者覆盖该交叉领域核心期刊 |
| 语言 | English | 该领域几乎所有核心文献为英文 |
| 开放获取 | 可选筛选 OA 文献优先获取全文 | 非强制，仅用于全文获取阶段 |
| 高被引 | 可选按 "Highly Cited" 排序浏览 | 用于识别领域里程碑 |
| 综述优先 | 可选按 "Document Type: Review" 筛选 | 先读已有综述建立框架 |

### 引文追踪建议

- **向后追踪（Cited References）**：对 EHRNoteQA (2024)、LLMEval-Med (2025)、MIMIC-IV Benchmark (2017) 做"参考文献回溯"，找到它们引用的基础方法论文献。
- **向前追踪（Times Cited）**：对 MIMIC-IV Benchmark (2017) 做"被引文献追踪"，找到所有引用它的后续 benchmark 论文——这是发现 T2 簇遗漏文献的最有效方法。
- **相关记录（Related Records）**：对核心文献使用 WoS 的"相关记录"功能，基于共享参考文献找到相似论文。

---

## 10. 检索质量核查

### 核查清单

| 核查项 | 状态 | 说明 |
|---|---|---|
| 覆盖核心研究对象（EHR/RWD） | 通过 | Module A 含 9 个核心词 + 扩展词，覆盖文献池中全部高频术语 |
| 覆盖 benchmark/评测术语 | 通过 | Module B 以 `benchmark*` 为核心，辅以 4 个评测方法变体 |
| 覆盖 LLM 缩写和全称 | 通过 | Module C 含 LLM/LLMs + "large language model*" + GPT/ChatGPT |
| 考虑拼写差异 | 通过 | "real-world data" 和 "real world data" 两种形式均纳入 |
| 考虑缩写全称配对 | 通过 | EHR/EMR/RWD/RWE/MIMIC 缩写 + "electronic health record*"全称 |
| 歧义关键词控制 | 通过 | "language model*"和 "evaluat*"仅在扩展方案中使用，平衡方案中未使用 |
| AND 模块数量合理 | 通过 | 三模块 AND（A AND B AND C），未过度限定 |
| NOT 使用谨慎 | 通过 | 全部方案未使用 NOT，避免误删 |
| 代表性文献覆盖核查 | 部分 | 文献池中 EHRNoteQA、LLMEval-Med、MIMIC-IV Benchmark 标题均含 EHR/MIMIC + benchmark + LLM/clinical，预估可被检索式命中。但 LLMEval-Med 标题用 "Real-world Clinical Benchmark" 而非 "EHR"，需确认 Module A 的 "real-world data" 能否命中其摘要 |

### 下一轮需向用户反馈的信息

1. **WoS 实际命中数量**：运行平衡型方案后，记录 `#1 AND #2 AND #3` 的结果数
2. **Top 20 结果的相关性判断**：人工浏览前 20 条，标注"高度相关""间接相关""不相关"的比例
3. **核心文献是否命中**：检查文献池中的 6 篇 T2 核心文献（EHRNoteQA、LLMEval-Med、EHR-Complex、CliniQ、EHRSQL、MIMIC-IV Benchmark）是否出现在 WoS 结果中
4. **明显不相关文献的特征**：如果不相关文献集中在某个模式（如"clinical evaluation of drug efficacy"），反馈后可在下一轮调整 Module B

### 已知限制

- WoS 对预印本的覆盖有限——文献池中 31% 是 arXiv/preprint（document 类型），这些在 WoS Core Collection 中可能缺失。建议 WoS 检索完成后，用 PubMed + Google Scholar 补充预印本。
- WoS 此前因反爬拦截无法使用（交接摘要中记录）。如 WoS 仍不可用，可改用 PubMed Advanced Search（语法类似）或 Scopus Advanced Search（支持 NEAR 运算符）执行相同检索逻辑。
