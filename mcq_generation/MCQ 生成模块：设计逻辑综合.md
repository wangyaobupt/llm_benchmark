# MCQ 生成模块：设计逻辑综合

> 本文档综合 `README.md`、`architecture_overview.md`、`mcq_generation_design.md` 与 `question_types.md` 四份文档，还原该模块的完整设计逻辑。读者如需要字段级细节，仍应回到各原始文档。

## 1. 模块定位

MCQ 生成模块的目标：从真实世界数据（RWD）底座生成**英文 A-D 四选一、单项最佳答案**的临床选择题，用于评测 LLM 的临床判断能力。

- 答案必须来自真实世界数据中的统计证据，而不是指南文本或模型记忆；
- 每道题必须可追溯到：来源规则 → 统计量 → 生成模型与 prompt → 审核记录 → 人工决定；
- 现状：题型 1 有完整 10 阶段设计但无实现代码；题型 2-5 仅有题型规范；上游 standardization 模块代码缺失（详见第 8 节）。

## 2. 顶层框架：一条临床决策链拆成五道题

五类题型沿着临床就诊的自然时间线排布，每道题锁住流程中的一个决策点：

```text
患者信息 → ① 检查检验选择 → ② 临床诊断 → ③ 治疗处置 → ④ 转诊科室 → ⑤ 离院指导
```

| # | 题型 | 考查内容 | 答案来源字段 |
|---|---|---|---|
| 1 | Clinical investigation selection | 根据症状、病史等选择最可能被选用的下一项检查检验 | 检查医嘱、实验室检验医嘱 |
| 2 | Clinical diagnosis | 整合症状、体征、关键检查检验结果做鉴别诊断 | 门诊/出院诊断 |
| 3 | Treatment and management | 选择当前阶段最适当的治疗或处置（药物/手术/紧急处置/住院） | 药物处方、手术记录 |
| 4 | Referral and specialty selection | 选择应前往/会诊/转介的最适当医疗服务或科室 | 科室或转诊记录 |
| 5 | Discharge advice and follow-up | 选择最适当的离院指导或随访计划（含危险信号识别） | 出院记录 |

**关键规则：答案来源字段与题干信息字段严格分离。** 答案来源字段绝不泄漏进题干。例如题型 1 的答案是 `investigation_orders`，则诊断、检查结果、治疗方案等"后验信息"一律不能进题干，否则等于提前泄露答案。

## 3. 底层设计原则

### 3.1 统计答案先于语言生成（核心判断）

题目问的不是"指南推荐什么"，而是：

> 给定这组患者特征，真实世界数据中最可能被选择的是哪项？（即 P(y|X) 排名第一）

这一选择带来三个架构后果：

1. **答案由数据统计决定，不由 LLM 决定**：先从 visit 数据中挖掘条件规则 X→y，经统计检验确认为稳健关联后，rank-1 即正确答案；
2. **LLM 被严格隔离在答案确定之外**：模型只输出 `stem`（题干）和 `rationale`（一句话理由），不能增删选项、改答案位置、添加规则之外的患者事实、把观察性关联说成指南推荐或因果关系；
3. **最小化模型输入**：payload 只有标准化条件特征名、固定选项和少量聚合统计量——无患者标识、无病历原文、无可识别信息。

### 3.2 其余通用原则

- **选项由程序锁定**：正确答案位置由确定性算法分配（sha256 循环分配 A-D），模型不得改动；
- **题干必须是合成场景**：只含规则中已有的 2-4 个决策相关特征，不复制真实病历片段，不出现真实患者标识、精确日期、脱敏占位符；
- **确定性与可复现性**：相同输入 + 相同配置 → 相同的 rule_id、question_id、选项集合、答案位置；
- **失败关闭（fail-closed）**：缺少统计证据、干扰项不足、模型输出非法、隐私校验失败或审核状态不完整时，题目不得进入 gold；
- **医疗安全优先**：对生命体征不稳定、意识改变等危险情况，不得把常规门诊检查或延迟处理设为最佳答案。

## 4. 数据基础：EHR 字段与实体

### 4.1 背景参照（Li et al. 2020）

题型规范引用了 Li 等（2020）《Real-world data medical knowledge graph: construction and applications》构建的医学知识图谱：从 1620 万次就诊、376 万患者中建立 9 类实体（疾病、年龄段、性别、症状、检查、检验组合、检验项目、药物、手术）与 579,094 个四元组。

| EHR 源字段 | 生成的图谱实体 |
|---|---|
| 人口统计信息 | 年龄段、性别 |
| 主诉 | 症状 |
| 门诊诊断、出院诊断 | 疾病 |
| 检查医嘱 | 检查 |
| 实验室检验医嘱 | 检验组合 |
| 实验室检验结果 | 检验项目 |
| 药物处方 | 药物 |
| 手术记录 | 手术 |

### 4.2 字段扩展与术语统一

在论文字段之外补充：生命体征、检查报告、科室或转诊记录、出院记录。

术语统一（避免混淆）：

- **既往史**：当前临床决策前已存在的疾病及相关历史；
- **用药史**：当前决策前已使用或正在使用的药物；
- **诊断**：本次就诊过程中形成的诊断；
- **药物处方**：本次诊疗过程中产生的处方或治疗结果。

字段用途三分类：**题干信息**（可作合成场景输入）、**条件题干信息**（仅影响答案时加入）、**答案来源**（构造答案/候选项，不得提前泄漏在题干）。

图谱属性（共现次数、条件概率、特异性、可靠性等）只用于选题/排序/构造候选/排除弱关系，不作为题干字段。

### 4.3 题型 1 的输入契约

默认输入 `rwd_benchmark_visits.csv`，遵循 17 列 visit 契约（subject_id, hadm_id, age_at_encounter, sex, chief_complaint, history_of_present_illness, past_medical_history, medications_on_admission, investigation_orders, investigation_reports, primary_icd_code, primary_diagnosis_name, primary_icd_version, other_diagnoses, medication_prescriptions, procedures, discharge_record）。

题型 1 只使用：

- 条件特征：`age_at_encounter`、`sex`、`chief_complaint`、`history_of_present_illness`、`past_medical_history`、`medications_on_admission`
- 结果标签：`investigation_orders`
- 本地连接：`subject_id`、`hadm_id`（仅本地，单向哈希为 visit_key）

**`investigation_reports`、诊断、处方、操作、出院记录禁止用于构造 X 或 y**（避免后验泄漏）。

### 4.4 外部 API 禁止字段

任何外部模型请求不得包含：subject_id、hadm_id、stay_id、note_id、primary_icd_code、primary_icd_version、primary_diagnosis_name、other_diagnoses、investigation_reports、medication_prescriptions、procedures、discharge_record。调用前递归校验整个 payload。

真实 API 调用还须满足：`execute_api = true`、`MIMIC_EXTERNAL_API_APPROVED = YES`、`DEEPSEEK_API_KEY` 非空（key 只由环境提供，不得写入脚本/配置/日志/文档）。

## 5. 题型 1 管线：10 个阶段，3 层门禁

```text
                    数据层（确定性，不碰 LLM）
rwd_benchmark_visits.csv
  │
  ├─ Stage 0  隐私校验 + 输入契约验证
  ├─ Stage 1  临床特征标准化（年龄→age_band，主诉→symptom 等）
  ├─ Stage 2  检查目录标准化（raw_names → InvestigationConcept）
  ├─ Stage 3  构建 visit 事务（features + outcomes）
  ├─ Stage 4  条件规则挖掘（8 道统计硬门槛）
  ├─ Stage 5  干扰项选择 + A-D 位置锁定
  │
  │           生成层（LLM 调用，严格约束）
  ├─ Stage 6  LLM 生成合成题干 + 理由（只输出 stem + rationale）
  ├─ Stage 7  程序级生成校验（12 条检查）
  │
  │           审核层（独立隔离）
  ├─ Stage 8  独立自动审题（独立请求 + 独立 prompt，返回结构化裁定）
  ├─ Stage 9  人工审核队列（human_review_queue.csv）
  └─ Stage 10 导出 gold（fail-closed 门禁）
```

### 5.1 数据层要点

- **Stage 1 特征标准化**：特征类型包括 age_band、sex、symptom、sign、physiologic_flag、past_condition、medication、absent。`uncertain` 和 `not_mentioned` 不进入特征集；明确否定特征（absent）组合至少需 8 个支持 visit；年龄用年龄段、不发送精确年龄；
- **Stage 2 检查目录**：所有 raw_name 必须恰好映射到一个 `InvestigationConcept`（含 canonical_name、investigation_family、granularity、is_orderable 等），缺失/意外增加映射整批失败；只有 `specific` 且 `is_orderable=true` 的检查可作结果标签或选项；
- **Stage 3 事务构建**：visit_key 为本地单向哈希；features/outcomes 去重稳定排序；不从检查报告、诊断、治疗信息补全 outcome；
- **Stage 4 规则挖掘**：见第 6 节；
- **Stage 5 选项锁定**：见第 7 节。

### 5.2 生成层要点

- LLM 只看到条件特征名、固定选项、少量聚合统计量（n_x、n_xy、smoothed_probability、lift）和 `correct_option`（用于校验，模型不得输出选项）；
- 请求用 JSON response mode + 确定性生成参数（temperature=0），初始请求 + 最多 5 次重试（指数退避 + 抖动）；非法 JSON/Schema 不匹配可重试；重试耗尽记失败、不生成 candidate；
- 缓存键覆盖 task type、model、prompt version、schema version、system prompt、payload、response model、生成参数。

### 5.3 程序级生成校验（12 条）

1. stem/rationale 去空白后满足最小长度；
2. 题干含约定的 `most likely to be selected` 预测语义；
3. 题干不出现 target canonical name 或其登记同义词；
4. 题干无精确日期、机构、患者标识、MIMIC 脱敏占位符；
5. 英文题无 CJK 字符；
6. 题干/理由无未提供的临床事实（诊断、检查结果、治疗、住院经过）；
7. 与任一源文本的 5-word shingle Jaccard overlap ≤ 0.55；
8. options 恰好为 A/B/C/D；
9. 四选项非空且唯一；
10. `options[correct_option] == correct_answer`；
11. correct_answer == accepted rule 的 rank-1 检查项；
12. condition_features 与来源规则一致且顺序不变。

失败题记录稳定错误码（answer_leaked_in_stem、source_overlap、contains_exact_date 等），不写入 candidates。

### 5.4 审核层要点

- **自动审题（Stage 8）**：独立请求 + 独立 prompt（可与生成同模型但不同调用、不同 task type、隔离上下文）；审核器只返回结构化裁定（9 个布尔项 + recommendation + concise_reason），不得修改题目；所有布尔为 true 且 accept 才置 `candidate_passed`，否则 `candidate_rejected`；审核失败自动拒绝，不能保持 pending；
- **人工审核（Stage 9）**：只有 `candidate_passed` 的题进入队列（UTF-8-SIG CSV）；`human_decision = approved | rejected | revise`；重建队列按 question_id 合并保留已有人工字段；题目内容变化必须产生新 ID 或显式作废旧决定；
- **Gold 门禁（Stage 10）**：同时满足——source rule accepted、生成校验通过、自动审核 candidate_passed、人工 approved、schema/prompt 版本允许发布、run profile 非 exploratory。任何缺失即不发布（fail-closed）。

## 6. 规则挖掘：统计量与 8 道硬门槛

### 6.1 统计量定义

对每个条件组合 X（默认 2-4 个特征）与检查 y：

```text
conditional_probability = n_xy / n_x
smoothed_probability    = (n_xy + 1) / (n_x + 2)
baseline_probability    = (n_y + 1) / (n_total + 2)
lift                    = smoothed_probability / baseline_probability
score                   = wilson_lower × max(0, log2(lift)) × log(1 + n_xy) × bootstrap_stability
```

另计算：`wilson_lower`（95% Wilson 区间下界）、`fisher_p`（单侧 Fisher exact）、`fdr_q`（Benjamini-Hochberg 校正）、`bootstrap_stability`（固定种子 bootstrap 中 y 独占第一名的占比）、`probability_gap` 与 `score_ratio`（与 runner-up 的区分度）。

排序键：smoothed_probability 降序 → score 降序 → investigation_id 升序。第一名 = target，第二名 = runner-up。

条件组合规则：至少含一个 symptom/sign/physiologic_flag/absent；至多一个年龄段、一个性别；feature_id 稳定排序；Apriori 子集剪枝。

### 6.2 8 道统计硬门槛（默认正式阈值）

| 门槛 | 默认值 | 防的是什么 |
|---|---|---|
| `min_x_support` | 5 | 条件样本太少 |
| `min_xy_support` | 4 | 共现太少 |
| `min_smoothed_probability` | 0.60 | 条件概率不够高 |
| `min_lift` | 1.20 | 不比基线好 |
| `min_wilson_lower` | 0.35 | 小样本区间太宽 |
| `max_fdr_q` | 0.05 | 多重检验后不显著 |
| `min_bootstrap_stability` | 0.80 | 第一名不稳定 |
| `min_probability_gap` + `min_score_ratio` | 0.15 / 1.25 | 与第二名区分度不足 |

- 任一门槛未过 → `rejected`，记录稳定原因码（low_x_support、fdr_not_significant 等）；
- 正式 benchmark 只能使用预先登记的严格阈值；宽松阈值跑出的结果标记 `exploratory`，不得导出 gold；
- 只有一个可用 outcome 时无法生成四选一题，后续门禁淘汰。

## 7. 干扰项与选项锁定

- **候选过滤**：investigation_id ≠ target、is_orderable、granularity 与 target 相同、名称不重复、非同义词/别名、可比较的检查项目、排除 generic/unknown；
- **排序**：同 investigation_family 优先 → |source_visit_count 差值| 小优先 → canonical_name 升序 → investigation_id 升序；取前 3 个作干扰项（同家族优先保证临床迷惑性）；
- **不足三个** → 记录 `insufficient_distractors`，跳过该规则，不调用模型；
- **位置锁定**：按 `sha256(rule_id)` 稳定排序后循环分配 A-D；干扰项内部顺序由 `sha256(rule_id + investigation_id)` 决定；不依赖模型输出，题干生成前锁定，大样本上近似均衡。

## 8. 模块职责划分与红线

| 子系统 | 主要职责 |
|---|---|
| `schemas` | 全部版本化严格数据契约（禁止额外字段） |
| `source` / `phenotype` | 输入解析 + 临床特征提取/标准化 |
| `catalog` | 检查名称标准化 + 别名组 |
| `mining` | 事务构建 + 统计量 + 规则排名 + 门槛 |
| `generation` | 干扰项 + 答案位置 + LLM 题干 + 生成校验 |
| `privacy` | payload 最小化 + 禁止字段 + 文本隐私检查 |
| `review` | 独立结构化自动审题 |
| `pipeline` | 阶段编排 + 状态 + 人工队列 + gold 导出 |
| `audit` / `client` | 原子产物 + 缓存 + 重试 + API 审计 |

**关键红线：统计规则选择、模型语言生成、审核裁定三者不得合并到同一个不可审计的调用中。** 每一步可独立追溯、独立复现、独立审计。

可复现性由以下共同定义：input content hash、pipeline/schema/rule/prompt version、model identifier、rule threshold profile、bootstrap seed & iterations、investigation catalog hash。gold release 必须保存 manifest（数据哈希、模型 ID、阈值配置、prompt/schema 版本）。

## 9. 题型 2-5 规范要点（摘要）

通用出题原则（五类题共享）：

- 每题只问当前临床阶段的一个决策；必要时信息（题干只保留 2-4 项决定答案的关键信息）；
- 生命体征/检验结果以定性描述为主，数值仅在决定答案时保留；
- 诊断题保留至少一项关键检查/检验结果；治疗题保留已确定诊断和影响治疗的关键条件；转诊题保留诊断或足以判断服务方向的信息；离院题保留病情稳定/准备离院的状态；
- 合成病例：不得含直接身份信息；不得通过罕见特征组合重建真实患者；须经临床与语言审核；
- 医疗安全：尊重 ABC 紧急优先级，危险情况不得把常规门诊处理设为最佳答案；
- 医学依据控制为一句话，只说明决定答案的核心医学关系。

审核要点四组：临床完整性（题干足以支撑唯一答案、无遗漏关键安全信息）、选项质量（同层级、干扰项合理、无措辞泄露）、本地化与表达（香港医疗环境术语）、隐私与安全。

## 10. 当前缺口与推进瓶颈

```text
题型 1（检查检验选择）：  完整统计管线设计，零实现代码
题型 2-5（诊断/治疗/转诊/离院）：  题型规范 + EHR 字段表，无管线设计
上游 rwd_standardization 模块：  spec + test 就绪，代码缺失
```

题型 1 的实现是项目第一块代码，但依赖上游数据管线（standardization）落地——这是当前推进的物理瓶颈。

## 11. 文档导航

| 想了解 | 去哪份文档 |
|---|---|
| 五类题型完整规范 + EHR 字段表 + 审核要点 | `question_types.md` |
| 题型 1 十阶段设计全量细节（契约/公式/阈值/Schema/测试/验收） | `mcq_generation_design.md` |
| 跨文档架构总览（原则、骨架、缺口） | `architecture_overview.md` |
| 模块状态与文件索引 | `README.md` |
