# RWD Clinical Benchmark 检查检验选择题生成设计

## 1. 文档定位

本文定义 RWD Clinical Benchmark 中 **Clinical Investigation Selection** 题型的目标生成方案。目标产物是英文 A-D 四选一、单项最佳答案的检查检验选择题，并具备可复现的统计依据、固定选项、隐私保护、自动审题、人工审核和 gold 发布流程。

本文是目标实现规范，不是对现有代码的逐行说明。实现可以沿用 `code/investigation_selection` 的模块边界，但必须满足本文规定的数据契约、阶段门禁、失败语义和验收条件。

### 1.1 固定题目语义

题目询问的是：

> Which investigation is most likely to be selected?

标准答案表示在源真实世界数据中，给定患者特征组合 `X` 后最可能被选择的检查项目 `y`，即条件分布 `P(y | X)` 排名第一的检查。

该语义与以下问题不同：

- 临床指南推荐的最佳检查；
- 理想诊疗路径中的第一项检查；
- 急诊处置中的最高优先级动作；
- 用于确诊某疾病的金标准检查。

题干、理由、自动审题 prompt 和人工审核说明都必须使用“真实世界选择预测”语义，不得改写成 `most appropriate`、`best next step` 或其他规范性医疗建议。若某条统计规则虽然成立，但生成题目可能暗示危险或明显不合理的诊疗行为，应淘汰该题，而不是擅自更换统计答案。

### 1.2 目标与非目标

目标：

- 从 visit-level RWD 中构造患者特征与检查医嘱之间的统计关系；
- 只从统计证据充分、答案区分度明确的关系生成题目；
- 由程序固定正确答案、干扰项和选项位置；
- 由模型仅生成合成题干和简短统计理由；
- 通过程序校验、独立自动审题和人工审核形成 gold 数据；
- 使每道 gold 题可以追溯到来源规则、统计量、模型、prompt 和审核记录。

非目标：

- 不重建或复述某个真实患者的完整病历；
- 不以出院诊断或检查结果反向推断当时应开立的检查；
- 不让生成模型自行决定正确答案或修改选项；
- 不将观察性共现直接解释为因果关系或指南推荐；
- 不在本题型中考查诊断、治疗、转诊或离院管理；
- 不把开发子集或宽松 demo 阈值生成的题目作为正式 gold。

## 2. 设计原则

1. **统计答案先于语言生成。** 先确定可靠的 `X -> y` 规则，再生成题干；不能先让模型写题，再从文本中猜答案。
2. **选项由程序锁定。** 模型不得增加、删除、改写、重排选项，也不得改变正确答案位置。
3. **最小化模型输入。** 生成阶段只发送标准化条件特征、固定选项和必要的聚合统计量，不发送患者标识或病历原文。
4. **题干必须是合成场景。** 题干只包含规则中已有的 2-4 个决策相关特征，不复制真实病历片段。
5. **严格发布门禁。** 生成成功不等于合格；只有程序校验、自动审题和人工审核均通过的题目才能进入 gold。
6. **确定性与可追溯性。** 在输入、配置、目录、模型输出和版本均不变时，ID、规则排名、选项集合及答案位置必须稳定。
7. **失败关闭。** 缺少统计证据、干扰项不足、模型输出非法、隐私校验失败或审核状态不完整时，题目不得进入下游正式产物。

## 3. 总体架构

```text
rwd_benchmark_visits.csv
        |
        v
Stage 0  Validate and Privacy Gate
        |
        v
Stage 1  Extract and Normalize Clinical Features
        |                         |
        |                         +--> clinical_concept_catalog.json
        v
Stage 2  Normalize Investigation Concepts
        |                         |
        |                         +--> investigation_catalog.json
        v
Stage 3  Build Visit Transactions
        |
        +--> visit_transactions.jsonl
        v
Stage 4  Mine X -> Investigation Rules
        |
        +--> conditional_rules.jsonl
        +--> conditional_rules_rejected.jsonl
        v
Stage 5  Select Distractors and Lock A-D Options
        |
        v
Stage 6  Generate Synthetic Stem and Rationale
        |
        v
Stage 7  Deterministic Validation and Privacy Checks
        |
        +--> questions_candidates.jsonl
        v
Stage 8  Independent Automatic Review
        |
        +--> questions_reviewed.jsonl
        v
Stage 9  Human Review
        |
        +--> human_review_queue.csv
        v
Stage 10 Export Approved Gold Questions
        |
        +--> questions_gold.jsonl
```

每个阶段必须读取上一阶段已发布的结构化产物，不得依赖进程内未持久化状态。正式文件使用原子替换写入，避免中断时留下半写入文件。

## 4. 输入契约与隐私边界

### 4.1 输入文件

默认输入：

```text
dataset/rwd_benchmark/rwd_benchmark_visits.csv
```

输入遵循项目既有的 17 列 visit-level 契约：

```text
subject_id
hadm_id
age_at_encounter
sex
chief_complaint
history_of_present_illness
past_medical_history
medications_on_admission
investigation_orders
investigation_reports
primary_icd_code
primary_diagnosis_name
primary_icd_version
other_diagnoses
medication_prescriptions
procedures
discharge_record
```

本题型第一版只使用以下信息：

| 用途 | 输入字段 |
|---|---|
| 患者条件特征 | `age_at_encounter`、`sex`、`chief_complaint`、`history_of_present_illness`、`past_medical_history`、`medications_on_admission` |
| 检查结果标签 | `investigation_orders` |
| visit 内部连接与去重 | `subject_id`、`hadm_id`，只在本地使用 |

`investigation_reports`、诊断、处方、操作和出院记录不得用于构造本题型的 `X` 或 `y`。这样可以避免使用检查后信息、最终诊断或治疗经过泄漏答案。

### 4.2 输入验证

进入模型调用或规则挖掘前必须验证：

- 文件存在、非空且列名、列顺序符合输入契约；
- `subject_id`、`hadm_id` 非空，visit 键满足项目定义的唯一性要求；
- `age_at_encounter` 是有效成人年龄；
- `sex` 为允许值；
- 所有 JSON 字段可由标准 JSON parser 解析；
- `investigation_orders` 是非空字符串组成的 JSON 数组或空数组；
- 输入行数、visit 顺序和输入内容摘要已记录；
- 任何全局契约错误都会终止流程，不发布新的下游文件。

### 4.3 外部 API 禁止字段

任何外部模型请求及其嵌套对象均不得包含：

```text
subject_id
hadm_id
stay_id
note_id
primary_icd_code
primary_icd_version
primary_diagnosis_name
other_diagnoses
investigation_reports
medication_prescriptions
procedures
discharge_record
```

模型调用前必须对完整 payload 递归执行禁止键校验。真实 API 调用还必须同时满足：

```text
execute_api = true
MIMIC_EXTERNAL_API_APPROVED = YES
DEEPSEEK_API_KEY is not empty
```

API key 只允许由运行环境提供，不得写入脚本、配置文件、日志、缓存或文档示例。

## 5. 临床特征与检查目录

### 5.1 临床特征标准化

从允许的患者信息中提取并标准化以下特征类型：

```text
age_band
sex
symptom
sign
physiologic_flag
past_condition
medication
absent
```

特征使用 `feature_id` 表示稳定身份，使用 `display_name` 生成题干。当前症状、体征和生理异常只允许来自 `current_initial_presentation`；既往疾病和用药只允许来自决策前已经存在的信息。

`uncertain` 和 `not_mentioned` 不进入特征集合。明确否定的当前症状、体征或生理异常可以表示为 `absent`，但涉及否定特征的组合至少需要 8 个支持 visit。

年龄采用预定义年龄段，不向模型发送精确年龄。性别使用标准化显示值。特征 ID 不应包含患者或 visit 标识。

### 5.2 检查目录

所有原始 `investigation_orders` 名称必须映射到 `InvestigationConcept`：

```json
{
  "schema_version": "1.0.0",
  "investigation_id": "inv_0123456789abcdef01234567",
  "canonical_name": "12-lead electrocardiography",
  "raw_names": ["12 Lead ECG", "ECG 12 Lead"],
  "investigation_family": "cardiac electrophysiology",
  "granularity": "specific",
  "is_orderable": true,
  "source_visit_count": 1240
}
```

目录构建规则：

- `investigation_id` 由 `schema_version + canonical_name.casefold()` 的稳定哈希生成；
- 每个原始名称必须恰好映射一次，缺失或意外增加映射时整批失败；
- canonical name 按大小写不敏感方式合并；
- `raw_names` 去重并稳定排序；
- 同一 canonical group 中只要有一项不可开立，合并后的 `is_orderable` 即为 false；
- 只有 `specific` 且 `is_orderable=true` 的检查可以成为结果标签或题目选项；
- `generic` 和 `unknown` 项目保留在目录中供审计，但不进入正式题目。

## 6. Visit 事务构建

每个合格 visit 转换为一个 `VisitTransaction`：

```json
{
  "schema_version": "1.0.0",
  "visit_key": "visit_0123456789abcdef01234567",
  "features": [
    {
      "feature_id": "age_band:40-64",
      "feature_type": "age_band",
      "display_name": "age 40-64"
    },
    {
      "feature_id": "symptom:concept_chest_pain",
      "feature_type": "symptom",
      "display_name": "chest pain"
    }
  ],
  "outcomes": ["inv_0123456789abcdef01234567"]
}
```

事务构建要求：

- `visit_key` 是本地 `subject_id + hadm_id` 的单向哈希，不暴露原始 ID；
- features 在 visit 内按 `feature_id` 去重；
- outcomes 在 visit 内去重并稳定排序；
- outcomes 只包含目录中 `specific` 且可开立的检查；
- 没有有效 outcome 的 visit 可以保留用于计算总样本及特征支持度，但不会增加任何 `n_y` 或 `n_xy`；
- 不从 `investigation_reports`、诊断或治疗信息补全 outcome；
- 缺少标准化 phenotype 的 visit 不得静默生成空特征事务，应记录失败或按预先声明的阶段策略排除。

## 7. 条件规则挖掘

### 7.1 规则定义

对每个合法条件组合 `X` 和检查项目 `y` 计算：

```text
n_total = 事务总数
n_x     = 包含全部条件 X 的事务数
n_y     = 包含检查 y 的事务数
n_xy    = 同时包含 X 和 y 的事务数
```

条件组合默认包含 2-4 个特征，并满足：

- 至少包含一个 `symptom`、`sign`、`physiologic_flag` 或 `absent` 特征；
- 最多包含一个年龄段；
- 最多包含一个性别；
- 条件按 `feature_id` 稳定排序；
- 使用 Apriori 子集剪枝，只有频繁子集的更高阶组合才继续统计。

### 7.2 统计量

对每个 `X -> y` 计算：

```text
conditional_probability = n_xy / n_x
smoothed_probability    = (n_xy + 1) / (n_x + 2)
baseline_probability    = (n_y + 1) / (n_total + 2)
lift                    = smoothed_probability / baseline_probability
```

同时计算：

- `wilson_lower`：`n_xy / n_x` 的双侧 95% Wilson 区间下界；
- `fisher_p`：正相关方向的单侧 Fisher exact p-value；
- `fdr_q`：对全部已测试 `X -> y` 假设执行 Benjamini-Hochberg 校正；
- `bootstrap_stability`：使用固定种子进行 bootstrap 后，`y` 独占平滑概率第一名的迭代占比；
- `score`：用于稳定排序，不代替硬门槛。

默认 score：

```text
association = max(0, log2(lift))
score = wilson_lower
        * association
        * log(1 + n_xy)
        * bootstrap_stability
```

检查按以下键排序：

```text
1. smoothed_probability descending
2. score descending
3. investigation_id ascending
```

第一名为 target，第二名为 runner-up。进一步计算：

```text
probability_gap = target.smoothed_probability
                  - runner_up.smoothed_probability

score_ratio = target.score / runner_up.score
```

当 runner-up score 为 0 且 target score 大于 0 时，`score_ratio` 使用约定的有限上界值；当两者都为 0 时使用 0。只有一个可用 outcome 时不能生成四选一题，应在后续目录/干扰项门禁中淘汰。

### 7.3 默认正式阈值

| 参数 | 默认值 | 含义 |
|---|---:|---|
| `min_x_support` | 5 | 条件组合最少支持 visit 数 |
| `min_xy_support` | 4 | 条件和目标检查最少共同出现数 |
| `min_smoothed_probability` | 0.60 | 最低平滑条件概率 |
| `min_lift` | 1.20 | 相对基线最低提升 |
| `min_wilson_lower` | 0.35 | 95% Wilson 下界最低值 |
| `max_fdr_q` | 0.05 | 最大 FDR q-value |
| `min_bootstrap_stability` | 0.80 | bootstrap 第一名稳定性下限 |
| `min_probability_gap` | 0.15 | 与第二名的最低概率差 |
| `min_score_ratio` | 1.25 | 与第二名的最低 score 比率 |
| `bootstrap_iterations` | 200 | bootstrap 迭代次数 |
| `random_seed` | 20260720 | 确定性随机种子 |
| `min_conditions` | 2 | 最少条件数 |
| `max_conditions` | 4 | 最多条件数 |

正式 benchmark 只能使用预先登记的严格阈值配置。宽松阈值可以用于开发和故障定位，但其结果必须标记为 exploratory，且不得导出 gold。

### 7.4 规则状态

任何硬门槛未通过时，规则状态为 `rejected`，并记录一个或多个稳定原因码：

```text
low_x_support
low_xy_support
low_conditional_probability
low_lift
low_wilson_lower
fdr_not_significant
low_bootstrap_stability
ambiguous_probability_gap
ambiguous_score_ratio
```

只有 `status="accepted"` 的规则能够进入出题阶段。目标检查必须始终是该条件下排序第一的检查。

### 7.5 条件规则 Schema

accepted 和 rejected 规则使用同一严格 Schema，通过状态和拒绝原因区分：

```json
{
  "schema_version": "1.0.0",
  "rule_version": "1.0.0",
  "rule_id": "rule_0123456789abcdef01234567",
  "condition_feature_ids": [
    "symptom:concept_chest_pain",
    "symptom:concept_diaphoresis"
  ],
  "condition_display_names": ["chest pain", "diaphoresis"],
  "target_investigation_id": "inv_0123456789abcdef01234567",
  "target_investigation_name": "12-lead electrocardiography",
  "n_total": 1000,
  "n_x": 120,
  "n_y": 260,
  "n_xy": 92,
  "conditional_probability": 0.7667,
  "smoothed_probability": 0.7623,
  "baseline_probability": 0.2605,
  "lift": 2.9263,
  "wilson_lower": 0.6828,
  "fisher_p": 0.000001,
  "fdr_q": 0.00001,
  "bootstrap_stability": 0.96,
  "score": 2.51,
  "runner_up_investigation_id": "inv_89abcdef0123456701234567",
  "runner_up_probability": 0.4523,
  "probability_gap": 0.31,
  "score_ratio": 2.40,
  "status": "accepted",
  "rejection_reasons": []
}
```

Schema 必须校验条件 ID 与显示名称数量相同、计数关系合法、概率位于 `[0, 1]`，并保证 accepted rule 的 `rejection_reasons` 为空。`rule_version` 标识规则构造、排名和门槛解释的版本；修改任一统计定义或规则资格逻辑时必须升级该版本。

## 8. 干扰项与选项锁定

### 8.1 候选过滤

对每条 accepted rule，从检查目录选择三个干扰项。候选项必须同时满足：

- `investigation_id != target_investigation_id`；
- `is_orderable=true`；
- `granularity == target.granularity`；
- canonical name 与目标及其他候选按大小写不敏感方式不重复；
- 不属于目标的直接同义词或同一检查的别名；
- 与目标是可比较的检查项目，而不是检查家族、科室、治疗或诊断；
- 不包含 `generic` 或 `unknown` 粒度项目。

目录标准化负责消除主要同义词。程序还应对 canonical alias group 做最终防重。不能可靠判定可比较性的项目不得作为干扰项。

### 8.2 排序策略

合格候选按以下键稳定排序：

```text
1. 是否与 target 属于同一 investigation_family：同家族优先
2. abs(candidate.source_visit_count - target.source_visit_count)：差值小者优先
3. candidate.canonical_name.casefold()：升序
4. candidate.investigation_id：升序
```

取前 3 个作为干扰项。该策略使干扰项具备一定临床迷惑性，同时不依赖模型临时创造选项。

若不足三个合格干扰项：

```json
{
  "rule_id": "rule_...",
  "stage": "question_generation",
  "error_type": "insufficient_distractors",
  "error": "Fewer than three orderable same-granularity distractors"
}
```

该规则跳过，不调用题干生成模型。

### 8.3 正确答案位置

为降低 A-D 位置偏置，先按 `sha256(rule_id)` 对全部待生成规则稳定排序，再循环分配 A、B、C、D。干扰项内部顺序由 `sha256(rule_id + investigation_id)` 决定。

选项位置必须：

- 对相同规则集合可复现；
- 在大样本上近似均衡；
- 不依赖检查名称、正确答案频次或模型输出；
- 在题干生成前锁定。

## 9. 模型生成题干

### 9.1 模型职责

生成模型只返回：

```json
{
  "schema_version": "1.0.0",
  "stem": "A patient presents with ... Which investigation is most likely to be selected?",
  "rationale": "In the source data, this presentation is most strongly associated with selection of the keyed investigation."
}
```

模型不得：

- 输出、改写或重排选项；
- 决定 `correct_option` 或 `correct_answer`；
- 增加规则未提供的患者事实；
- 将问题改成诊断、治疗或规范性临床决策；
- 在题干中出现答案或直接同义词；
- 声称观察性统计关系是因果关系或指南建议。

### 9.2 请求 payload

```json
{
  "condition_features": ["chest pain", "diaphoresis"],
  "question_language": "English",
  "question_type": "real-world investigation selection prediction",
  "question_semantics": "most likely to be selected",
  "options": {
    "A": "12-lead electrocardiography",
    "B": "electroencephalography",
    "C": "pulmonary function testing",
    "D": "abdominal ultrasonography"
  },
  "correct_option": "A",
  "correct_answer": "12-lead electrocardiography",
  "rule_statistics": {
    "n_x": 120,
    "n_xy": 92,
    "smoothed_probability": 0.7623,
    "lift": 2.18
  }
}
```

题干包含 2-4 个决定预测结果的特征。若规则只有两个特征，模型不得为了达到自然语言长度而补充新事实。年龄段和性别只有在 condition features 中存在时才能出现。

`rationale` 必须是一句话，只说明来源数据中的选择关联，不使用 `indicated`、`recommended`、`gold standard` 或 `most appropriate` 等规范性表述。

### 9.3 结构化调用与重试

- 请求使用 JSON response mode；
- 非审核生成请求使用确定性生成参数；
- 返回值先由标准 JSON parser 解析，再由严格 Schema 校验；
- 空响应、非法 JSON 和 Schema 不匹配属于可重试错误；
- 默认初次请求加最多 5 次重试，并使用指数退避和抖动；
- 重试时最多带入截断后的上一次非法输出，并明确要求返回完整修复 JSON；
- 非可重试的客户端错误立即失败；
- 所有重试耗尽后记录失败，当前规则不生成 candidate；
- 缓存键必须覆盖 task type、model、prompt version、schema version、system prompt、payload、response model 和生成参数。

## 10. 程序级生成校验

模型返回通过结构化 Schema 后，还必须执行以下校验：

1. `stem` 和 `rationale` 去除首尾空白后满足最小长度；
2. 题干包含约定的 `most likely to be selected` 预测语义；
3. 题干不出现 target canonical name 或其登记的直接同义词；
4. 题干不出现精确日期、机构、患者标识或 MIMIC 脱敏占位符；
5. 英文题不得包含 CJK 字符；
6. 题干和理由不得出现诊断、检查结果、治疗或住院经过等未提供事实；
7. 题干与任一源文本的 5-word shingle Jaccard overlap 不得超过 `0.55`；
8. `options` 必须恰好包含 A、B、C、D；
9. 四个选项必须非空且唯一；
10. `options[correct_option] == correct_answer`；
11. `correct_answer` 必须等于来源 accepted rule 的 rank-1 investigation；
12. `condition_features` 必须与来源规则一致且顺序不变。

未通过时记录稳定错误码，例如：

```text
answer_leaked_in_stem
answer_synonym_leaked_in_stem
missing_prediction_semantics
contains_exact_date
contains_deidentification_placeholder
contains_linkage_identifier
contains_non_english_cjk_text
unsupported_clinical_fact
source_overlap
invalid_option_set
correct_answer_mismatch
condition_feature_mismatch
```

失败题不得写入 `questions_candidates.jsonl`。生成阶段可以发布部分成功的 candidates，但报告必须记录预期数、成功数、跳过数和各原因计数；正式 gold 导出不受失败 candidate 污染。

## 11. 题目 Schema

`InvestigationQuestion` 至少包含：

```json
{
  "schema_version": "1.0.0",
  "rule_version": "1.0.0",
  "question_id": "iq_0123456789abcdef01234567",
  "question_type": "clinical_investigation_selection",
  "language": "en",
  "semantics": "most_likely_selected_in_rwd",
  "stem": "A patient presents with ... Which investigation is most likely to be selected?",
  "options": {
    "A": "...",
    "B": "...",
    "C": "...",
    "D": "..."
  },
  "correct_option": "A",
  "correct_answer": "...",
  "rationale": "...",
  "condition_features": ["...", "..."],
  "target_investigation_id": "inv_...",
  "source_rule_id": "rule_...",
  "statistics": {
    "n_total": 0,
    "n_x": 0,
    "n_y": 0,
    "n_xy": 0,
    "conditional_probability": 0.0,
    "smoothed_probability": 0.0,
    "baseline_probability": 0.0,
    "lift": 0.0,
    "wilson_lower": 0.0,
    "fisher_p": 0.0,
    "fdr_q": 0.0,
    "bootstrap_stability": 0.0,
    "probability_gap": 0.0,
    "score_ratio": 0.0
  },
  "generator_model": "deepseek-v4-flash",
  "reviewer_model": "deepseek-v4-flash",
  "prompt_version": "1.0.0",
  "automatic_review_status": "pending",
  "human_review_status": "pending"
}
```

ID 规则：

```text
rule_id     = "rule_" + sha256(sorted_condition_ids + target_id)[:24]
question_id = "iq_"   + sha256("question" + rule_id)[:24]
```

允许状态：

```text
automatic_review_status = pending | candidate_passed | candidate_rejected
human_review_status     = pending | approved | rejected
```

## 12. 独立自动审题

### 12.1 隔离要求

自动审题必须使用独立请求和独立 prompt。审核请求可以看到完整候选题、来源条件和聚合统计量，但不能访问患者标识或病历原文。审核器不得修改题目，只返回结构化裁定。

生成与审核可以使用同一基础模型，但必须使用不同调用、不同 task type 和隔离的上下文。正式发布时应记录生成模型和审核模型，允许未来切换为异构模型复核。

### 12.2 审核 Schema

```json
{
  "schema_version": "1.0.0",
  "question_id": "iq_...",
  "is_investigation_selection": true,
  "uses_rwd_prediction_semantics": true,
  "single_best_answer": true,
  "clinically_plausible": true,
  "safe_priority": true,
  "no_answer_leakage": true,
  "options_same_granularity": true,
  "statistically_supported": true,
  "synthetic_case": true,
  "english_quality": true,
  "recommendation": "accept",
  "concise_reason": "The question consistently asks for the most likely real-world selection and has one statistically keyed answer."
}
```

审核器重点确认：

- 题目确实预测 RWD 中的检查选择，而非询问规范性最佳检查；
- 四个选项在当前题干下可比较，且统计标签唯一；
- 题干不通过措辞、长度或同义词泄露答案；
- 场景在医学上自洽，没有明显危险或荒谬组合；
- 若患者表现提示必须立即稳定生命体征，题目不会把常规检查包装成应优先采取的医疗建议；
- 统计量满足配置中登记的正式门槛；
- 场景是合成的，语言自然且没有真实患者痕迹。

所有布尔检查均为 true 且 `recommendation="accept"` 时，题目状态才变为 `candidate_passed`。`reject`、`revise`、审核异常或 `question_id` 不一致均产生 `candidate_rejected`。

自动审题不得因另一项检查在指南中更合适而直接替换正确答案；如果 RWD 标签与题目场景之间无法形成安全、清晰的预测问题，应拒绝整题。

## 13. 人工审核与 Gold 发布

### 13.1 人工审核队列

只有 `automatic_review_status="candidate_passed"` 的题目进入 `human_review_queue.csv`。固定列顺序：

```csv
question_id,stem,option_a,option_b,option_c,option_d,correct_option,correct_answer,automatic_status,automatic_reason,human_decision,reviewer_id,reviewed_at,notes
```

人工可填写：

```text
human_decision = approved | rejected | revise
reviewer_id     = 项目定义的审核者标识
reviewed_at     = ISO 8601 时间
notes           = 简洁、可审计的理由
```

重新生成队列时，以 `question_id` 合并并保留已有人工填写字段。若题目内容或来源规则发生变化，必须产生新的 ID 或显式使旧审核决定失效，不能静默沿用旧批准。

### 13.2 Gold 门禁

只有同时满足以下条件的题目进入 `questions_gold.jsonl`：

```text
source rule status == accepted
generation validation == passed
automatic_review_status == candidate_passed
human_decision == approved
schema and prompt versions are allowed for the release
run profile is not exploratory
```

导出时将 `human_review_status` 设置为 `approved`。未审核、拒绝、要求修改、自动审核失败或审核记录缺失的题目不得进入 gold。

`questions_gold.jsonl` 只包含题目对象，不混入审核器内部输出。审核记录通过 `question_id` 在 `questions_reviewed.jsonl` 和人工队列中追溯。

## 14. 核心接口

### 14.1 干扰项选择

```python
def select_distractors(
    rule: ConditionalInvestigationRule,
    catalog: list[InvestigationConcept],
) -> list[InvestigationConcept]:
    """Return exactly three deterministic eligible distractors or an empty/short result."""
```

### 14.2 题目生成

```python
def generate_questions(
    rules: list[ConditionalInvestigationRule],
    catalog: list[InvestigationConcept],
    client: StructuredLLMClient,
    prompt_path: Path,
    source_texts: list[str],
    model: str,
) -> tuple[list[InvestigationQuestion], list[dict[str, str]]]:
    """Generate validated candidates and structured per-rule failures."""
```

`rules` 可以包含 accepted 和 rejected 记录，但函数必须在内部再次过滤，只处理 accepted rules。`source_texts` 只在本地用于重合检测，不得加入外部 API payload。

### 14.3 自动审题

```python
def review_questions(
    questions: list[InvestigationQuestion],
    client: StructuredLLMClient,
    prompt_path: Path,
) -> tuple[
    list[InvestigationQuestion],
    list[QuestionReview],
    list[dict[str, str]],
]:
    """Return status-updated questions, review records, and failures."""
```

### 14.4 Gold 导出

```python
def export_gold(
    reviewed_questions: list[InvestigationQuestion],
    human_decisions: dict[str, HumanReviewDecision],
    release_policy: ReleasePolicy,
) -> list[InvestigationQuestion]:
    """Export only fully approved, non-exploratory questions."""
```

所有接口都应使用严格、禁止额外字段的版本化 Schema。未知字段、非法枚举或计数不一致必须显式失败。

## 15. 输出文件与审计

### 15.1 主要产物

| 文件 | 格式 | 内容 | 发布条件 |
|---|---|---|---|
| `clinical_concept_catalog.json` | JSON | 标准化临床概念目录 | 临床标准化完整成功 |
| `investigation_catalog.json` | JSON | 检查项目目录 | 全部原始名称映射成功 |
| `visit_transactions.jsonl` | JSONL | visit 特征和检查 outcomes | 事务构建完成 |
| `conditional_rules.jsonl` | JSONL | accepted rules | 规则挖掘完成 |
| `conditional_rules_rejected.jsonl` | JSONL | rejected rules 及原因 | 规则挖掘完成 |
| `questions_candidates.jsonl` | JSONL | 程序校验通过的候选题 | 生成阶段完成 |
| `questions_reviewed.jsonl` | JSONL | 候选题及自动审核记录 | 自动审题完成 |
| `human_review_queue.csv` | UTF-8-SIG CSV | 自动通过题目的人工队列 | 自动审题完成 |
| `questions_gold.jsonl` | JSONL | 最终批准题目 | gold 门禁通过 |

### 15.2 报告与审计

```text
validation_report.json
normalization_report.json
rule_mining_report.json
question_generation_report.json
question_review_report.json
manifest.json
audit/api_calls.jsonl
audit/stage_failures.jsonl
audit/cache/<cache_key>.json
```

每个阶段至少记录：

- 输入数量；
- 成功输出数量；
- 跳过或失败数量；
- 按稳定错误码聚合的失败原因；
- schema version；
- rule version；
- pipeline version；
- prompt version；
- model 和 reviewer model；
- 阈值 profile 及完整阈值；
- 开始和完成时间；
- 输入内容摘要或 run ID；
- 是否为 exploratory run。

API 审计记录每次逻辑请求的 task type、cache key、模型、prompt 版本、尝试次数、token 使用、缓存状态、验证状态和错误类型，不记录 API key。

## 16. 阶段状态与失败语义

manifest 中每个阶段使用：

```text
initialized
running
completed
failed
```

流程规则：

- 输入契约错误、目录映射不完整或上游正式产物缺失属于阶段级失败；
- 单条规则统计不足属于正常 rejected rule，不导致规则挖掘阶段失败；
- 单题干扰项不足、生成失败或校验失败属于 item-level failure，记录后继续其他规则；
- 审核调用失败时该题自动拒绝，不能保持 pending 后进入人工队列；
- gold 导出是 fail-closed：任何状态不完整都视为不满足发布条件；
- 重跑不得覆盖人工决定，除非题目身份或内容版本发生变化；
- 所有主要 JSON/JSONL 产物使用 UTF-8，CSV 使用 UTF-8-SIG；
- 主要产物使用临时文件加原子替换，append-only 审计日志除外。

## 17. 可复现性与版本管理

以下内容共同定义一次可复现运行：

```text
input content hash
pipeline version
schema version
rule version
prompt version
model identifier
rule threshold profile
bootstrap seed and iterations
investigation catalog content hash
```

确定性要求：

- 相同事务和配置产生相同 accepted/rejected rules；
- 相同规则产生相同 `rule_id` 和 `question_id`；
- 相同规则集合和检查目录产生相同干扰项与答案位置；
- 缓存命中返回经过当前 Schema 再校验的结构化对象；
- prompt、模型或 Schema 变化必须改变缓存键；
- 题干文本本身只有在模型响应或缓存不变时才承诺一致；
- gold release 必须保存 manifest，不能只发布孤立题目文件。

## 18. 测试方案

### 18.1 单元测试

输入与隐私：

- 缺列、错序、重复 visit、非法年龄、非法性别和错误 JSON 被拒绝；
- payload 顶层或嵌套包含禁止字段时被拒绝；
- 没有显式外部处理许可或 API key 时真实 API 阶段不能执行；
- source texts 只用于本地重合检查，不出现在模型请求。

目录与事务：

- 原始检查名称全部且仅映射一次；
- 同义原始名称合并到同一稳定 ID；
- generic、unknown 和不可开立项目不进入 outcomes；
- feature 和 outcome 在 visit 内去重并稳定排序；
- 后验诊断、检查报告和治疗信息不进入事务特征。

规则挖掘：

- `n_xy <= n_x` 且 `n_xy <= n_y`；
- 条件概率、平滑概率、baseline、lift、Wilson、Fisher 和 BH 校正有已知答案测试；
- bootstrap 在固定 seed 下可复现；
- 条件组合满足临床特征、年龄和性别限制；
- 每个硬门槛产生对应 rejection reason；
- rank-1、runner-up、probability gap 和 score ratio 计算正确。

选项与生成：

- 干扰项不包含 target、同义词、重复项、不可开立项或不同粒度项；
- 候选不足三个时记录 `insufficient_distractors` 且不调用模型；
- 同样规则集合产生相同选项和正确答案位置；
- A-D 位置在足够大规则集合上近似均衡；
- 模型不能改变固定选项和答案；
- 非法 JSON、空响应和 Schema 错误按策略重试并留痕；
- 答案泄露、同义词泄露、错误语义、精确日期、脱敏占位符、CJK 字符和源文本高重合被拒绝。

审核与发布：

- review `question_id` 不一致时自动拒绝；
- 任一审核布尔项失败或 recommendation 非 accept 时自动拒绝；
- 自动拒绝题不进入人工队列；
- 没有人工批准时 `questions_gold.jsonl` 为空；
- 只有自动通过且人工批准的题进入 gold；
- exploratory run 即使人工批准也不能导出正式 gold；
- 重建人工队列时保留同一题目的已有人工字段。

### 18.2 集成测试

使用 Fake client 构造至少四类检查和足够事务，完整执行：

```text
validate
extract/normalize
build transactions
mine rules
generate
review
export gold
```

集成测试不得访问真实网络。必须验证所有主要产物存在、manifest 计数一致、失败记录可追溯，并验证人工批准前后 gold 数量的变化。

### 18.3 回归测试

- 对固定 fixture 保存 accepted rule IDs、选项映射和 gold question IDs；
- prompt 或 Schema 有意升级时显式更新回归基线；
- 禁止以忽略顺序或模糊字符串包含替代关键身份和选项断言；
- 对真实 API 仅做隔离的可选 smoke test，不作为普通 CI 的必要条件。

## 19. 验收标准

实现只有同时满足以下条件才可视为完成：

1. 每道 candidate 和 gold 题恰好包含 A、B、C、D 四个唯一、非空选项；
2. 正确答案始终是 accepted rule 的 rank-1 investigation；
3. 正确选项位置由确定性算法分配，且不会被模型改变；
4. 所有题干明确使用 `most likely to be selected` 的 RWD 预测语义；
5. 题干不出现正确答案、直接同义词或未提供临床事实；
6. 题目不包含真实患者标识、精确日期、脱敏占位符或可识别的原始病历片段；
7. 规则、生成、校验、自动审核和人工审核状态可以通过 ID 完整追溯；
8. 任一生成或审核失败都不会污染 gold；
9. 没有人工批准时 gold 文件为空；
10. exploratory 阈值产生的题目不能发布为正式 gold；
11. 相同输入和版本配置可以复现规则 ID、题目 ID、选项集合和正确答案位置；
12. 全部单元、集成和回归测试通过；
13. 输出 manifest 完整记录数据、模型、prompt、Schema、阈值和运行状态；
14. 正式 gold 中每道题都能恢复其来源规则和完整统计证据。

## 20. 命令行目标

建议提供以下独立命令：

```text
prepare
extract-phenotypes
normalize
mine-rules
generate
review
export-gold
run-all
```

默认行为：

- 不带 `--execute-api` 时只执行不发送数据的 dry run/prepare；
- API 阶段缺少显式许可时立即失败；
- `run-all` 依次执行全部阶段，但 gold 仍受人工批准门禁约束；
- `export-gold` 不调用模型，只读取已审核题目和人工决定；
- CLI 输出主要产物数量和输出目录，不打印敏感 payload 或 API key。

示例：

```powershell
$env:DEEPSEEK_API_KEY = "<set-locally>"
$env:MIMIC_EXTERNAL_API_APPROVED = "YES"

python -s code/investigation_main.py run-all --execute-api
python -s code/investigation_main.py export-gold
```

## 21. 完整题目示例

以下示例只说明目标结构，不代表真实规则统计结果：

```json
{
  "schema_version": "1.0.0",
  "rule_version": "1.0.0",
  "question_id": "iq_example000000000000000001",
  "question_type": "clinical_investigation_selection",
  "language": "en",
  "semantics": "most_likely_selected_in_rwd",
  "stem": "A patient presents with chest pain and diaphoresis. Which investigation is most likely to be selected?",
  "options": {
    "A": "12-lead electrocardiography",
    "B": "electroencephalography",
    "C": "pulmonary function testing",
    "D": "abdominal ultrasonography"
  },
  "correct_option": "A",
  "correct_answer": "12-lead electrocardiography",
  "rationale": "In the source data, chest pain with diaphoresis is most strongly associated with selection of the keyed investigation.",
  "condition_features": ["chest pain", "diaphoresis"],
  "target_investigation_id": "inv_example000000000000000001",
  "source_rule_id": "rule_example00000000000000001",
  "statistics": {
    "n_total": 1000,
    "n_x": 120,
    "n_y": 260,
    "n_xy": 92,
    "conditional_probability": 0.7667,
    "smoothed_probability": 0.7623,
    "baseline_probability": 0.2605,
    "lift": 2.9263,
    "wilson_lower": 0.6828,
    "fisher_p": 0.000001,
    "fdr_q": 0.00001,
    "bootstrap_stability": 0.96,
    "probability_gap": 0.31,
    "score_ratio": 2.40
  },
  "generator_model": "deepseek-v4-flash",
  "reviewer_model": "deepseek-v4-flash",
  "prompt_version": "1.0.0",
  "automatic_review_status": "candidate_passed",
  "human_review_status": "approved"
}
```

示例中的题干没有声称 A 是指南推荐的最佳检查；它只要求预测在给定表现下真实世界中最可能被选择的检查。正式题目的所有数值都必须来自其 `source_rule_id`，不得人工编造或由生成模型改写。

## 22. 实现映射建议

建议保持以下职责分离：

| 子系统 | 主要职责 |
|---|---|
| source / phenotype / normalization | 输入解析、临床特征提取和标准化 |
| catalog | 检查名称标准化、目录和别名组 |
| mining | 事务构建、统计量、规则排名和门槛 |
| generation | 干扰项、答案位置、模型题干和生成校验 |
| privacy | payload 最小化、禁止字段和文本隐私检查 |
| review | 独立结构化自动审题 |
| pipeline | 阶段编排、状态、人工队列和 gold 导出 |
| audit / client | 原子产物、缓存、重试和 API 审计 |
| schemas | 全部版本化严格数据契约 |

模块可以调整，但不得把统计规则选择、模型语言生成和审核裁定合并到同一个不可审计调用中。
