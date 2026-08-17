# 检查检验选择任务 — gold 构建方法（探索性草案 v0）

> 状态：**draft，待临床审核后冻结**。本文档记录截至 2026-08 的端到端方法、
> 参数与结果，供临床评审后升级为正式协议。所有数值均为占位/探索性，不冒充正式 gold。

## 1. 任务定义

- 任务：`investigation_selection`（检查检验选择）。
- 题干：一名患者因某主诉（ED chief complaint）就诊。
- 问题：该主诉**最该做哪个检查**（影像 / 临床监护 / 化验）。
- 答案语义：**行为 gold**（真实临床里最判别地选择），不是规范性最佳决策。

## 2. 数据与划分

- 数据：MIMIC-IV 冠状动脉疾病谱全队列，39,036 住院、20,136 患者，已清洗+标准化（workflow v1.1.0）。
- 划分（按**患者**，SHA256 排序 + 最大余数，占位比例 70/15/15）：

| 集合 | 患者 | 住院 | 用途 |
|---|---|---|---|
| development | 14,095 | 27,443 | 算 gold、出题 |
| validation | 3,021 | 5,800 | 验证规则稳定性 |
| final_test | 3,020 | 5,793 | 盲测（全程不碰） |

## 3. gold 语义

- **selectivity（特异性/lift）** = P(候选|主诉) / P(候选)，衡量"该主诉把该候选的概率抬升几倍"。
- 经 4 版对比（likelihood / selectivity / PSR / specificity×reliability），**selectivity 最优**；PSR 因概率项偏向普适候选而回退，更适合"诊断类"（答案=疾病、低先验）题目。
- **一线白名单**（影像）：gold 只在 `{General Xray, CT Scan, Ultrasound}` 内取"最判别"，排除 MRI / Nuclear Med / Noninvasive Vascular / Interventional* / Angio 等次级检查。干扰项仍用全候选池。
- 临床监护白名单：`{Telemetry, ECG, Echo, Blood tests}`（排除 Vitals/Monitoring 普适医嘱）。
- 化验：507 项归入 16 个临床 panel（`LAB_PANEL_MAP`），候选=panel，gold=selectivity 最高。

## 4. 噪声清理

- 垃圾主诉黑名单：`unknown-cc`、`___`、单字符/纯标点等。
- 缩写归一化：`c/p`→chest pain、`cva`→stroke、`sbo`/`gib`/`chf`/`pe`/`dvt`、`l/r`→left/right、`ruq/luq` 等（`_SINGLE_TOKEN_SYNONYMS` + 词级映射）。

## 5. 参数（占位，待冻结）

| 参数 | 值 | 说明 |
|---|---|---|
| min_condition_support | 10 | 主诉最少住院数 |
| max_baseline_share | 0.85 | 剔除普适候选（BMP/CBC/Telemetry） |
| min_baseline_share | 0.02 | 剔除稀有候选（Angio 等 <2%） |
| min_candidate_support | 10 | 候选绝对下限 |
| fdr_q | 0.10 | BH-FDR（按 condition 分组） |
| score_ratio_minimum | 1.5 | selectivity 下限 |

## 6. 验证方法

development 规则 → 在 validation 独立患者上重算候选 ranking，看 gold 候选是否仍排第一（rank-1）或前三（top-3）。

## 7. 结果

| 阶段 | 数值 |
|---|---|
| development 题目 | 350（影像117 / 临床79 / 化验154） |
| validation rank-1 一致率 | **67.65%**（影像 86.67% / 临床 68.18% / 化验 56.0%） |
| validation top-3 一致率 | 90.2% |
| 验证通过（rank-1 / top-3） | 69 / 92 题 |
| DeepSeek（flash）69 题 rank-1 | **43.5%**（影像 65.4% / 临床 33.3% / 化验 28.6%） |
| DeepSeek（flash）385 题全量 | 33.3% |

关键发现：一线影像白名单同时**提升稳定性**（影像 rank-1 61.7%→86.7%）和**模型准确率**（影像 27.6%→65.4%），证明"检查检验选择"的临床本义是"一线检查"而非"最特异检查"。

## 8. 待冻结（需临床审核）

1. 划分比例 70/15/15（validation 偏小，266 条规则无法验证，长尾主诉被弃）。
2. 一线影像白名单 `{CXR, CT, US}` 是否完整（如是否加 MRI 用于神经类主诉）。
3. 化验 panel 映射（16 类）与临床监护白名单。
4. 主诉缩写词表 + 垃圾黑名单。
5. 各统计阈值。

## 9. 可复现性

- 输入 `normalized_events.parquet` SHA-256 与 workflow_manifest fail-closed 校验。
- 划分 `subject_split.parquet` SHA-256 绑定。
- 每次运行输出 `run_manifest.json`（输入哈希 + 划分哈希 + 全部参数 + 计数）。
- 纯 pandas、无随机数、无 LLM 参与生成。

## 10. 产物位置

- 划分：`artifacts/investigation_selection_full_cohort_split/`
- 出题：`artifacts/investigation_selection_full_cohort_gold_selectivity/`
- 验证：`artifacts/investigation_selection_full_cohort_validation/`
- 验证题集 + 评测：`artifacts/investigation_selection_full_cohort_validated/`
- 代码：`evaluation_pipeline/investigation_selection/{pipeline,evaluate}.py`、`scripts/{build_full_cohort_split,run_full_cohort_selectivity,validate_full_cohort,build_validated_questions}.py`
