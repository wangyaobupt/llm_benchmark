# MIMIC 评测数据集构建方法学

> 文档版本：2026-08-06
> 描述 MIMIC 临床评测基准数据集的完整构建流程，包括数据来源、全诊疗过程聚合、评测数据提取、清洗、标准化设计与题目生成设计。
> 已完成的阶段如实描述实际过程；设计阶段标注"（设计中）"或"（待实现）"。

---

## 1. 数据来源

### 1.1 数据集

本评测基准基于以下 MIMIC 系列数据集构建，均从 PhysioNet 合规获取：

| 数据集 | 版本 | SHA-256 校验 | 核心规模 | 用途 |
|---|---|---|---|---|
| MIMIC-IV | 3.1 | 33/33 通过 | 364,627 患者 / 546,028 住院 / 94,458 ICU stay | 核心住院与 ICU 数据 |
| MIMIC-IV-Note | 2.2 | 5/5 通过 | 331,793 份出院小结 / 2,321,355 份放射报告 | 临床文本（出院小结、放射报告） |
| MIMIC-IV-ED | 2.2 | 8/8 通过 | 425,087 次 ED 就诊 | 急诊数据 |

此外，MIMIC-III 1.4（30/30 通过）已下载备用，但当前聚合与评测数据提取未使用该数据集。MIMIC-CXR 2.1.0、MIMIC-IV-ECG 1.0、MIMIC-IV-ECHO 1.0 等多模态扩展尚未下载，为后续多模态评测预留。

### 1.2 源表清单

全诊疗过程聚合共使用上述三个数据集的 **41 张源表**：

| 数据包 | 子模块 | 表数 | 表名 |
|---|---|---:|---|
| MIMIC-IV 3.1 | hosp | 22 | patients, admissions, transfers, services, labevents, d_labitems, microbiologyevents, omr, poe, poe_detail, pharmacy, prescriptions, emar, emar_detail, diagnoses_icd, d_icd_diagnoses, procedures_icd, d_icd_procedures, hcpcsevents, d_hcpcs, drgcodes, provider |
| MIMIC-IV 3.1 | icu | 9 | icustays, chartevents, datetimeevents, ingredientevents, inputevents, outputevents, procedureevents, d_items, caregiver |
| MIMIC-IV-ED 2.2 | ed | 6 | edstays, triage, vitalsign, diagnosis, medrecon, pyxis |
| MIMIC-IV-Note 2.2 | note | 4 | discharge, discharge_detail, radiology, radiology_detail |

每张源表的表头在聚合前经过锁定 schema 校验（[source_catalog.py](../mimic_pipeline/source_catalog.py)），确保字段名、顺序与预期完全一致；不一致则终止聚合，不兜底跳过。

## 2. 全诊疗过程聚合

### 2.1 目标

将 41 张分散的 MIMIC 源表整合为统一的 episode 级全诊疗数据底座，使每一次就诊（episode）拥有完整的跨系统临床事件时间线，供下游评测任务使用。

### 2.2 Episode 与 Contact 定义

- **Episode**：一次完整的就诊周期。住院使用 `H:<hadm_id>` 标识；没有有效住院关联的独立急诊就诊使用 `E:<stay_id>` 标识。急诊后入院的合并为同一个住院 episode。
- **Care Contact**：episode 内的一次接触记录，包括急诊、住院、ICU、转科等。各接触分别保留，不合并。

### 2.3 两阶段落盘策略

聚合采用"两阶段落盘"以控制内存占用：

1. **Stage 1（解压转换）**：逐张读取压缩 CSV，转为临时 Parquet，然后关闭源文件读取连接。避免同时打开多张大表导致解压缓冲叠加溢出。
2. **Stage 2（跨表关联）**：在临时 Parquet 基础上执行跨系统 SQL 关联与事件归并，产出最终 parquet。此阶段不重新打开原始 CSV。

### 2.4 产物结构

聚合产出 9 张 parquet（存放于 G 盘，总计约 48.9 GB）：

| 表 | 内容 | 行数 |
|---|---|---:|
| episode_index | 就诊主索引（患者、时间段、关联标识） | 767,971 |
| care_contacts | 急诊/住院/ICU/转科接触 | 3,069,421 |
| timeline_events | 跨系统临床事件（化验、医嘱、用药、操作等） | 238,203,827 |
| event_items | 事件的原始明细行（检验值、药物剂量等） | 892,073,791 |
| evidence_links | 事件/文书到原始行位置的证据锚点 | 900,934,909 |
| documents | 放射报告与出院小结原文 | 2,652,892 |
| unresolved_events | 无法唯一归入某次就诊的事件 | 13,067,505 |
| patient_history_refs | 患者既往资料窗口（不限定期限） | 767,971 |
| episode_coverage | 各 episode 的数据类型覆盖情况 | 767,971 |

> 上述行数为删除 154 个负时长 episode 后的预期值；当前 G 盘文件尚未完成就地修正（见 §2.6）。

### 2.5 事件归并规则

每张源表在单线程顺序读取时附加物理源行号（`_source_row_number`），用于构造全局唯一的 `item_event_id`，不替换原始业务键。即使两条原始记录内容完全相同，也作为两个独立明细保留。

ICU `chartevents` 按"同一 ICU stay + 同一 `charttime`"形成一个事件组，组内全部原始行进入 `event_items`，避免事件碎片化。

文书（出院小结、放射报告）通过 `hadm_id` 直接关联到住院 episode；无 `hadm_id` 的文书尝试按患者 + 时间窗口唯一匹配 episode，匹配不唯一则标记为 unresolved。

### 2.6 质量检查

质量检查区分两类：

- **一致性检查**：episode/contact/患者一致性、事件与 item 唯一性、item 父事件关系、evidence 父目标关系。前者通过输出回读精确统计，后者由构造规则保证并在质量报告中记录依据。
- **质量报告**（`quality_report.json`）：仅含汇总计数和硬性质量检查结果，不含患者级数据。全量运行结果为 duplicate/orphan/subject 冲突均 0。

**已知待修正**：154 个负时长 episode（0.02%，源于原始数据中 `deathtime < admittime` 等时间逻辑缺陷）。删除脚本的 SQL 源码已修改（`build_episodes.sql` 加入时长过滤），后处理脚本 `scripts/remove_negative_episodes.py` 已编写但尚未成功运行，G 盘 parquet 未就地修正。

### 2.7 数据画像

对聚合产物进行了 8 维度数据画像（[data-profiling-report.md](data-profiling-report.md)），关键发现：

- 诊断覆盖率 99.9%，化验覆盖率 81.9%，出院小结覆盖率 43.2%。
- 空文本文档 0；出院小结文本长度中位数 9,847 字符。
- 48 个完全空壳 episode（0.006%），可忽略。
- 事件 unresolved 率按类型差异大：outpatient_measurement_group 100%、laboratory_panel 37.8%、medication_administration 3.3%、provider_order 0.0%。

## 3. 评测数据提取

### 3.1 目标

从 MIMIC 原始数据中提取 visit 级结构化数据，每个就诊为一行，字段覆盖临床流程各环节，供标准化和题目生成使用。

### 3.2 纳入与排除标准

一次就诊（visit）纳入评测数据集需同时满足：

- 年龄 ≥ 18 岁（由 `patients.anchor_age` + `admissions.admittime` 计算）；
- 性别有效（`patients.gender` 为 M 或 F）；
- 有有效主诊断（`diagnoses_icd` 中 `seq_num = 1` 的记录）；
- 有包含 Chief Complaint 章节的 DS（Discharge Summary）出院小结。

任一条件不满足，整条 visit 排除。

### 3.3 提取字段（17 列）

| # | 字段 | 来源表 | 内容 |
---:|---|---|---|
| 1 | subject_id | admissions | 患者标识 |
| 2 | hadm_id | admissions | 住院标识 |
| 3 | age_at_encounter | patients + admissions | 就诊时年龄 |
| 4 | sex | patients | 性别 |
| 5 | chief_complaint | discharge（DS Chief Complaint 章节） | 主诉（文本） |
| 6 | history_of_present_illness | discharge（DS HPI 章节） | 现病史（文本） |
| 7 | past_medical_history | discharge（DS PMH 章节） | 既往史（文本） |
| 8 | medications_on_admission | discharge（DS Meds on Admission 章节） | 入院用药（文本） |
| 9 | investigation_orders | poe + poe_detail | 检查医嘱（JSON 数组） |
| 10 | investigation_reports | labevents + d_labitems + radiology | 检查报告（JSON 对象） |
| 11 | primary_icd_code | diagnoses_icd（seq_num=1） | 主诊断 ICD 编码 |
| 12 | primary_diagnosis_name | d_icd_diagnoses | 主诊断名称 |
| 13 | primary_icd_version | diagnoses_icd | ICD 版本（9 或 10） |
| 14 | other_diagnoses | diagnoses_icd（seq_num>1）+ 字典 | 其他诊断（JSON 数组） |
| 15 | medication_prescriptions | prescriptions | 处方（JSON 数组） |
| 16 | procedures | procedures_icd + d_icd_procedures | 操作（JSON 数组） |
| 17 | discharge_record | discharge（DS Follow-up Instructions 章节） | 离院指导（文本） |

### 3.4 出院小结章节解析

字段 5–8 和 17 来自出院小结文本的章节解析（[discharge.py](../rwd_extraction/discharge.py)）。解析逻辑：

1. 按 MIMIC 出院小结的标准章节标题（Chief Complaint、History of Present Illness、Past Medical History、Medications on Admission、Follow-up Instructions 等）做正则匹配，要求标题独占一行。
2. 取标题到下一个已知标题之间的文本作为该章节内容。
3. 同一患者有多份出院小结时，按 `note_seq`（降序）、`charttime`（降序）、`storetime`（降序）选择信息最完整的一份。
4. 若某就诊的出院小结未解析出 Chief Complaint，该就诊排除。

### 3.5 产物规模

提取产出 `rwd_benchmark_visits.csv`（254 MB），包含 **11,687 次就诊**，涉及 **5,328 位患者**，人均 2.19 次就诊。

### 3.6 已知问题

| 优先级 | 问题 | 影响 |
|---|---|---|
| P0 | `discharge_record`（字段 17）在 raw 和 cleaned 产物中均 100% 空 | 疑为 Follow-up Instructions 章节解析未命中；题型 5（离院指导）完全无数据来源 |
| P1 | `investigation_orders` 中 `poe_detail` 99.99% 空 | 医嘱仅存分类标签（如 "Lab"），无具体检查项；题型 1 须依赖 investigation_reports |
| P1 | 157 条就诊 `chief_complaint` 为空 | 违反纳入标准（主诉缺失应排除），需确认来源 |
| P2 | ICD-9（63%）与 ICD-10（37%）混用 | 标准化需处理版本差异 |
| P2 | `procedures` 缺失率 41% | 影响题型 3 操作类题目样本量 |

## 4. 数据清洗

### 4.1 目标

对提取产物中的 4 个自由文本字段进行 LLM 实体抽取，将非结构化文本转为结构化 JSON 字符串数组，使下游可做统计分析和标准化。

### 4.2 清洗字段与规则

| 字段 | 清洗前 | 清洗后 | 处理 |
|---|---|---|---|
| chief_complaint | 自由文本 | `["entity1","entity2",...]` | LLM 抽取主诉实体 |
| history_of_present_illness | 自由文本 | JSON 数组 | LLM 抽取病程实体 |
| past_medical_history | 自由文本 | JSON 数组 | LLM 抽取既往临床实体 |
| medications_on_admission | 自由文本 | JSON 数组 | LLM 抽取入院药物名称 |

其余 13 列逐值原样复制，不做任何修改。输出保持 17 列、行数、行顺序、ID 逐行一致。

### 4.3 LLM 实体抽取流程

使用 DeepSeek 模型（`deepseek-v4-flash`，Base URL `https://api.deepseek.com`），每个字段配有专属 system prompt（[prompts.py](../rwd_cleaning/prompts.py)）。关键规则：

- **去标识化预处理**：调 LLM 前删除 MIMIC 的 `[**...**]` 和 `___` 占位符。
- **输出格式**：JSON 对象 `{"entities": ["...", "..."]}`，`temperature=0`，禁用 thinking 模式。
- **否定实体不输出**，不展开缩写，不翻译，不合并同义词；仅做表面重复去重。
- **失败重试**：LLM 返回含占位符、空实体、截断或非法 JSON 时判定无效并重试，最多 5 次（指数退避）。
- **校验**：输出逐行校验——13 个非清洗列必须与输入逐字节一致，4 个清洗列必须为合法 JSON 字符串数组。

### 4.4 断点续跑

清洗按"行索引 × 字段"维度做 checkpoint（JSONL），每条记录包含输入文本 SHA-256 和配置 SHA-256。中断后重跑时，输入未变的条目直接复用结果，输入变更的条目重新请求。这避免了 11,687 行 × 4 字段 = 46,748 次请求的中断重跑成本。

### 4.5 产物

清洗产出 `rwd_benchmark_visits_cleaned.csv`（235 MB），行数与行顺序与提取产物一致。

## 5. 标准化设计（待实现）

### 5.1 目标

将清洗产物中的医学命名（诊断、药物、操作、检查项等）映射为标准名称，消除同义异写、版本差异（ICD-9/10）和单位不一致，产出标准化的 15 列评测数据。

### 5.2 字段流转

标准化从 17 列合并/标准化为 15 列，主要变化：

- `primary_icd_code` + `primary_diagnosis_name` + `primary_icd_version` 合并为 `primary_diagnosis` 一列。
- 4 个清洗字段（chief_complaint 等）按字段专属映射标准化为标准名称。
- `investigation_orders` 逐字节原样复制，不做标准化。
- `investigation_reports` 做实验室/放射结果标准化（单位等价、检验结构固定）。
- `medication_prescriptions` 做成分映射 + 剂量解析（single/range/text/missing）+ 结构固定。

### 5.3 双阶段 LLM 映射（设计中）

标准化设计采用双阶段架构：

1. **build-mappings 阶段**：从清洗数据中收集所有待标准化名称，调用 DeepSeek 生成候选标准名，再由独立调用做等价复核（双盲一致性检查）。产出 mappings 文件 + review 文件。
2. **transform 阶段**：纯查表执行，映射缺项即终止，不在运行时调 LLM。

manifest 文件记录模型版本、规则版本和映射 SHA-256，确保换模型必须重建映射并升版本。

**当前状态**：设计文档（[standardization_spec.md](../rwd_benchmark_standardization_spec.md)）与测试契约（[test_standardization.py](../tests/test_standardization.py)）已完备，`rwd_standardization/` 模块代码尚未实现。

## 6. 题目生成设计

### 6.1 五类临床题型

评测基准包含五类临床 MCQ，围绕统一临床流程组织：

| # | 题型 | 临床流程环节 | 语义 |
|---:|---|---|---|
| 1 | Clinical investigation selection | 检查检验 | 预测真实世界中最可能被选择的检查项，即 P(检查项 \| 特征) 排名第一 |
| 2 | Clinical diagnosis | 临床诊断 | 根据患者信息与关键检查检验结果作出诊断 |
| 3 | Treatment and management | 治疗处置 | 基于已确定诊断选择正确的治疗方案 |
| 4 | Referral and specialty selection | 转诊科室 | 根据诊断或病情判断应转诊的服务方向或科室 |
| 5 | Discharge advice and follow-up | 离院指导 | 对治疗后病情稳定、准备离院的患者给出随访与生活指导 |

所有题目均为英文 A–D 四选一单项最佳答案格式。

### 6.2 通用出题原则

- 题干使用合成患者场景，不直接复制真实病历。
- 题干只保留 2–4 项决定答案的关键信息，删除不影响判断的冗余信息。
- 生命体征和检验结果以定性描述为主，只有具体数值本身决定答案时才保留数值。
- 尊重气道、呼吸、循环等紧急临床优先级，不将延迟处理设为最佳答案。

### 6.3 题型 1 生成方案（设计中）

题型 1（Clinical Investigation Selection）有完整的设计文档（[mcq_generation_design.md](../rwd_benchmark_mcq_generation_design.md)），核心设计原则：

1. **统计答案先于语言生成**：先确定可靠的"患者特征 → 检查项"统计关系，再生成题干。
2. **选项由程序锁定**：模型不得增加、删除、改写或重排选项，也不得改变正确答案位置。
3. **最小化模型输入**：生成阶段只发送标准化条件特征和聚合统计量，不发送患者标识或病历原文。
4. **严格发布门禁**：程序校验 + 独立自动审题 + 人工审核均通过才能进入 gold 数据集。
5. **失败关闭**：统计证据不足、干扰项不足、模型输出非法或隐私校验失败时，题目不得进入下游。

**当前状态**：题型 1 有 Stage 0–10 的完整生成设计；题型 2–5 仅有题型规范（[Question Types.md](../Hong%20Kong%20RWD%20Clinical%20Benchmark%20Question%20Types.md)），尚无出题设计。

## 7. 数据安全与合规

- **PhysioNet DUA**：不提交原始 CSV、影像、波形、Parquet、DuckDB 或病例 JSON；这些文件均已在 `.gitignore` 中排除。
- **LLM 使用边界**：不将 MIMIC 患者级内容发送到普通在线 LLM/API。清洗阶段的 DeepSeek 调用仅发送经去标识化预处理后的单字段文本，不发送完整病历或患者标识。
- **公开成果限制**：公开成果只包含代码、配置、字段定义、汇总结果和合规文档。
- **审计脚本**：数据画像与审计脚本（`scripts/audit_mimic_download.ps1`、`scripts/profile_*.py`）只输出汇总计数和分布统计，不输出患者级数据行。

## 8. 当前完成度汇总

| 环节 | 状态 | 产物 |
|---|---|---|
| 原始数据获取与校验 | 完成 | MIMIC-IV 3.1 / Note 2.2 / ED 2.2，SHA 全通过 |
| 全诊疗过程聚合 | 基本完成 | 9 张 episode parquet（48.9 GB），待修正 154 个负时长 episode |
| 数据画像 | 完成 | 聚合层 8 维度画像 + RWD 层 7 维度 EDA |
| 评测数据提取 | 完成 | rwd_benchmark_visits.csv（11,687×17） |
| 数据清洗 | 完成 | rwd_benchmark_visits_cleaned.csv（235 MB） |
| 标准化 | 待实现 | 设计文档 + 测试契约已就绪，模块代码缺失 |
| 题目生成（题型 1） | 设计中 | Stage 0–10 设计文档完成，无代码 |
| 题目生成（题型 2–5） | 设计中 | 仅题型规范，无出题设计 |
