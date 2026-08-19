# phenotype：历史 visit 级类型化临床特征空间构建层（已归档）

> 本包现位于 `data_pipeline/archived/phenotype/`。旧导入 `data_pipeline.phenotype` 会立即 fail-closed。W0 已将本模块及其“8 类 phenotype 特征”设计标记为历史失效材料。不得作为新管线输入；`run_generation.py --profile formal` 会 fail-closed。新实现不得从本模块复制逻辑，详见 [`docs/plans/20260819_Benchmark-问题复核与实施计划.md`](../../../docs/plans/20260819_Benchmark-问题复核与实施计划.md)。

> 从已验证的事件级 `normalized_events.parquet` + 原始归档 `patients` 表出发，为每次住院构建**类型化的条件特征空间**（`age_band / sex / symptom / sign / physiologic_flag / past_condition / medication / absent` 共 8 类），并枚举满足设计约束的**特征条件组合**，供下游 v2 MCQ 规则挖掘（`versions/v2-llm-stem/mcq/mining.py`）在多特征条件上「统计定答案」。

---

## 1. 在流水线中的位置（完成什么事情）

本模块是 MIMIC-IV 流水线中「事件」到「规则」的翻译器：上游事件层产出的是**逐事件**的归一化记录，下游挖掘需要的是**逐 visit 的特征事务表**（哪些症状/体征/用药/人口学特征同时出现在同一次住院上）。phenotype 负责这中间的全部语义加工：时间门禁（决策时刻前瞻性）、体征阈值化、用药类别化、既往史抽取、显式否定、特征编码与条件组合枚举。

```text
MIMIC 原始 CSV.GZ
   │  mimic_raw_archive
   ▼
mimic-admission-raw-*.jsonl（admission 原始 JSONL）
   │  内嵌 mimic_iv_hosp.patients[0]（gender/anchor_age/anchor_year）
   │  与 admissions[0].admittime
   │
   │  P1  demographics.py / run_demographics.py
   ▼
hadm_demographics.parquet（+ hadm_demographics.manifest.json）
   │                                    clean_clinical_archive
   │                                            │  event_pipeline（事件化+归一化）
   │                                            ▼
   │                            normalized_events.parquet
   │                            （+ event_pipeline/workflow_manifest.json，
   │                               SHA-256 fail-closed 校验）
   │                                            │
   │                     + subject_split.parquet（--role development 按 subject 切分）
   │                                            │
   └──────────────┬─────────────────────────────┘
                  ▼
   ┌──────────────── run_phenotype.py（P6 编排，全流程在此组装）────────────────┐
   │  P0 temporal_gate：index=首个检查医嘱时间；仅保留 source_event 且早于 index │
   │  P2 vital_flags（config/vital_flag_rules.yaml 阈值）                       │
   │  P3 medication_features（medication_categories 类别表）                    │
   │  P5 absent_features（assertion=absent）                                    │
   │  P4 past_condition：ICD 轨（读【未门禁】的 post-hoc 诊断）                  │
   │                    + NER 轨（--past-condition-ner，可选并入）               │
   │                    + sign 轨（--sign-features ← run_sign_ner.py，可选）     │
   │  phenotype.build_feature_frame  → visit_features_{role}.parquet（长表）    │
   │  condition_space.enumerate_conditions（Apriori L1 剪枝）                   │
   │                                → visit_conditions_{role}.parquet           │
   │  产物清单：phenotype_manifest_{role}.json                                  │
   └───────────────────────────────────────────────────────────────────────────┘
                  │
                  ▼  run_mining_verification.py（本目录提供的端到端验证入口）
   versions/v2-llm-stem/mcq/mining.py::mine_rules(events, conditions, catalog,
   thresholds, ...) —— 多项统计门槛 + 支持度短路（n_x < min_x_support 直接
   cheap 拒绝、跳过 bootstrap）
                  │
                  ▼
   conditional_rules_development.jsonl
                  │  dedup_rules.py（B1 子sumption 去重 / B2 上下文变体收敛）
                  ▼
   run_generation.py（锁 A-D 选项 → LLM 写题干 → 程序检查 → 自动评审 →
                     人工审核队列 / fail-closed gold）
                  │
                  ▼
   make_review_html.py / make_review_md.py（人工审阅页面与清单）
```

**与 mining.py 的接口**：本模块产出 `visit_conditions_{role}.parquet`，其 `condition`（规范化排序 key）、`condition_feature_ids` / `condition_features`（同排序列表）与 `n_features` 字段即 `mine_rules` 的条件输入；`run_mining_verification.py` 展示了完整调用方式。

---

## 2. 目录结构与职责

### 2.1 文件 → 职责 → 关键函数/类

| 文件 | 职责 | 关键函数 / 类 |
|---|---|---|
| `__init__.py` | 模块声明（自述为此前缺失的 rwd_standardization / Stage-1 层） | — |
| `demographics.py` | P1 人口学 sidecar：流式读原始归档 JSONL，计算年龄与分段 | `age_band`、`parse_admission`、`extract_demographics` |
| `run_demographics.py` | P1 CLI 入口（可复现） | `main` |
| `temporal_gate.py` | P0 决策时刻门禁：index 时间与前瞻可用性 | `index_times`、`is_available`、`gate_events`、`ORDER_EVENT_KINDS` |
| `vital_flags.py` | P2 体征阈值化：`vital_measured` 事件 → `physiologic_flag` | `load_flag_rules`、`flags_for_visit`、`extract_vital_flags`、`_resolve_value`、`_temperature_c` |
| `config/vital_flag_rules.yaml` | P2 九个 flag 的阈值规则（`phenotype-vital-flag-rules/1.0.0`） | — |
| `medication_categories.py` | P3 药名→临床类别映射表（复用 v1 treatment 已验证映射） | `medication_category`（v1 语义）、`medication_feature`（本模块语义）、`_match_category` |
| `medication_features.py` | P3 入院用药特征：`medication_reconciled` → 类别集合 | `extract_medication_features` |
| `past_condition.py` | P4 既往史双轨 + sign 轨（阻塞中） | `extract_past_condition_icd`、`_past_condition_from_icd`、`_normalize_icd_name`、`extract_past_condition_ner`、`_normalize_past_condition`、`extract_signs_ner`（no-op） |
| `compare_past_condition.py` | P4 双轨覆盖/一致性探针 | `compare` |
| `sign_ner.py` | P4 sign 轨解锁件：体格检查章节切分 + 正常发现停用词 | `extract_physical_exam`、`build_physical_exam_frame`、`filter_sign_features`、`SIGN_STOPLIST` |
| `run_sign_ner.py` | P4 sign NER 执行器（DeepSeek Flash，默认 dry-run） | `main`、`_parse_mentions` |
| `config/prompts/sign_physical_exam.md` | sign NER 的 system 提示词（严格 JSON schema） | — |
| `absent_features.py` | P5 显式否定特征 | `extract_absent_features` |
| `phenotype.py` | P6 特征帧组装 + feature_id 编码 + 在场症状 | `feature_id`、`extract_present_symptoms`、`build_feature_frame`、`_split_phrases`、`_VITAL_SIGN_WORDS` |
| `condition_space.py` | P6 条件组合枚举 + Apriori L1 剪枝 | `enumerate_conditions`、`_valid_combination`、`CLINICAL_TYPES`、`SINGLETON_TYPES` |
| `run_phenotype.py` | P6 端到端 CLI：加载/校验/门禁/特征/枚举/落盘/manifest | `load_events`、`build`、`_union_past_condition`、`main` |
| `run_mining_verification.py` | 全量 development 条件 → v2 规则挖掘端到端验证 | `main` |
| `dedup_rules.py` | B1 规则子sumption 去重 + B2 上下文变体收敛（--converge） | `dedup_rules`、`converge_rules`、`_core_features` |
| `run_generation.py` | Stage 5-8：accepted 规则 → 候选题目（FakeClient 默认） | `main`、`load_rules`、`build_client` |
| `make_review_html.py` | 人工审核交互 HTML（单选 + 导出决策 JSON） | `main`、`_score` |
| `make_review_md.py` | 人工审核 Markdown 清单（表格 + 逐题详情） | `main`、`_score` |
| `progress.py` | 原子进度 JSON 写入（供 HTML 监视器轮询） | `write_progress`、`PROGRESS_DIR` |
| `serve_progress.py` | 进度静态 HTTP 服务（绕过 file:// fetch 限制） | `main` |
| `tests/test_phenotype.py`（仓库 `tests/` 下） | 单元测试（307 行，覆盖全部 P 阶段） | — |

### 2.2 P0-P6 阶段总览

| 阶段 | 模块 | 输入事件（event_kind） | 语义与产物 |
|---|---|---|---|
| P0 时间门禁 | `temporal_gate.py` | `imaging_ordered` / `clinical_ordered` / `laboratory_ordered` 定 index；其余按 `evidence_phase` 判 | index=首个检查**医嘱**时间；只有严格早于 index 的 `source_event` 可用（无时间戳的主诉视为可用；post_hoc 永不可用） |
| P1 人口学 | `demographics.py` | 原始归档 JSONL（非事件表） | `age_at_encounter = anchor_age + (admit_year − anchor_year)`；`age_band` 五段；`sex` |
| P2 体征 | `vital_flags.py` + yaml | `vital_measured` | 9 个 `physiologic_flag`；°F→°C 换算；BP 取 `value_structured_json.systolic` |
| P3 用药 | `medication_categories.py` + `medication_features.py` | `medication_reconciled` | 药名 → 32 个临床类别（保留慢病家用药类别） |
| P4 既往史/体征 | `past_condition.py`（+ `sign_ner.py`） | ICD 轨：`condition_recorded_post_hoc`（**不门禁**）；NER 轨：text_ner_v2 sidecar | ICD 轨（Z-code + 23 个慢病关键词）∪ NER 轨（`clinical_problem` 且 `historical`）；sign 轨默认阻塞 |
| P5 否定 | `absent_features.py` | `symptom_reported`（assertion=absent） | 「no chest pain」类显式否定 → `absent` 特征 |
| P6 组装 | `phenotype.py` + `condition_space.py` + `run_phenotype.py` | 上述全部 | 长表 `visit_features_{role}.parquet`；组合表 `visit_conditions_{role}.parquet` |

---

## 3. 工作原理深度解析

### 3.1 P0 时间门禁（`temporal_gate.py`）

**目的**：MCQ 的「条件 → 检查决策」必须是决策时刻前瞻可知的，杜绝用事后信息（出院诊断、事后检验结果）泄露答案。

**输入**：整个 events DataFrame（含 `event_kind / event_time / evidence_phase / hadm_id`）。

**处理步骤**：

1. **index 时间**（`index_times`）：对每个 `hadm_id` 取三类**检查医嘱**事件的最小 `event_time`：
   - `ORDER_EVENT_KINDS = ("imaging_ordered", "clinical_ordered", "laboratory_ordered")`；
   - 刻意**排除** `laboratory_resulted`（出结果是更晚的时刻，不能定义决策点）；
   - 无医嘱事件的住院没有 index（后续被 fail-closed 丢弃）。
2. **可用性判定**（`is_available` / `gate_events`）：
   - `evidence_phase != "source_event"`（即 post_hoc）→ **永不可用**；
   - `source_event` 且 `event_time` 缺失 → **视为可用**（ED 主诉的分诊时间戳未记录，但其内容必然先于任何检查医嘱）；
   - 否则要求 `event_time < index_time`（字符串比较前统一把 `T` 替换为空格，对齐 ISO 与空格两种格式）；
   - `gate_events` 用 inner merge 连接 index 映射：**没有 index 的住院整段丢弃**（fail-closed）。

**输出**：门禁后的 events 子集，供 P2/P3/P5/P6 使用。人口学（无时间维度）不经过此门，单独由 sidecar 注入。

**关键代码**：`temporal_gate.py: index_times / is_available / gate_events`。

### 3.2 P1 人口学（`demographics.py`）

**目的**：为每次住院提供 `age_band` 与 `sex` 两个「单例」型条件特征。

**输入**：`mimic-admission-raw-*.jsonl`（原始归档），逐行流式解析，不整载内存。

**处理步骤**：

1. `parse_admission` 取 `record["mimic_iv_hosp"]["patients"][0]` 的 `gender / anchor_age / anchor_year / anchor_year_group` 与 `admissions[0].admittime`；
2. 年龄公式：**`age_at_encounter = anchor_age + (admit_year − anchor_year)`**（MIMIC anchor 机制的确定性推算；`admit_year` 取 `admittime` 前 4 字符，`_admit_year`）；
3. 分段（`age_band`，硬编码 `AGE_BANDS`）：`<18 / 18-39 / 40-64 / 65-79 / 80+`（边界：18、40、65、80；`<18` 是为未成年行保留的显式兜底段）；
4. 行按 `hadm_id` 排序后写 Parquet（确定性），并写 SHA-256 manifest。

**输出**：`hadm_demographics.parquet`（字段见 §4）+ `hadm_demographics.manifest.json`。

**关键代码**：`demographics.py: age_band / parse_admission / extract_demographics`。

### 3.3 P2 体征阈值化（`vital_flags.py` + `config/vital_flag_rules.yaml`）

**目的**：把结构化生命体征测量转为定性 `physiologic_flag`，与症状文本解耦。

**输入**：门禁后的 `vital_measured` 事件（`source_label / value_numeric / value_structured_json / unit`）。

**处理步骤**：

1. **来源映射**（`_SOURCE_KEY`）：`Heart rate→heart_rate`、`Temperature→temperature`、`Respiratory rate→respiratory_rate`、`Oxygen saturation→oxygen_saturation`、`Blood pressure→systolic_bp`；
2. **取值**（`_resolve_value`）：多数体征取 `value_numeric`；**血压特殊**——解析 `value_structured_json` 里的 `systolic` 字段（舒张压不参与规则）；
3. **温度换算**（`_temperature_c`）：unit 为 `°F / degF / f`（含大小写变体）时 `(value − 32) × 5/9`，阈值一律按摄氏比较；
4. **阈值规则**（yaml，schema `phenotype-vital-flag-rules/1.0.0`）：

   | flag | source | 判定 | 阈值 |
   |---|---|---|---|
   | tachycardia | heart_rate | > | 100 /min |
   | bradycardia | heart_rate | < | 60 /min |
   | fever | temperature | ≥ | 37.0 °C |
   | hypothermia | temperature | < | 35.0 °C |
   | hypoxia | oxygen_saturation | < | 92 % |
   | tachypnea | respiratory_rate | > | 20 /min |
   | bradypnea | respiratory_rate | < | 12 /min |
   | hypotension | systolic_bp | < | 90 mmHg |
   | hypertension | systolic_bp | ≥ | 140 mmHg |

5. **极值取向**（`_extreme` / `flags_for_visit`）：`>`/`≥` 规则取该 visit 内**最大值**，`<` 规则取**最小值**（即「取最异常值撞阈值一次即命中」）；同一 visit 输出去重排序后的 flag 列表。

**输出**：`hadm_id → physiologic_flags`（`extract_vital_flags`）。

**关键代码**：`vital_flags.py: flags_for_visit / _resolve_value / _temperature_c`。

### 3.4 P3 用药（`medication_categories.py` + `medication_features.py`）

**目的**：「入院用药清单」本身就是诊断线索（如二甲双胍→糖尿病），转为 `medication` 类别特征。

**输入**：门禁后的 `medication_reconciled`（家用药重整）事件的 `source_label`（药名）。

**处理步骤**（`_match_category` + `extract_medication_features`）：

1. 先过**非药品排除表** `_NON_TREATMENT`（器械/包装 + IV 载体子串：syringe、vial、bag、cassette、flush、sodium chloride、dextrose、lactated ringers、sterile water、saline、d5、d10、d30）与占位词（`ns / sw / nan / none`）；
2. 再对 **32 个临床类别**词典做**子串匹配**（按词典声明顺序，先命中先得）：anticoagulant、antiplatelet、statin、beta_blocker、ace_arb、diuretic、analgesic、laxative、ppi、h2_blocker、antibiotic、antidiabetic、bronchodilator、antiemetic、antidepressant、vitamin、mineral、electrolyte、vasopressor、antiarrhythmic、nitrate、steroid、vaccine、thyroid、sedative、sleep_aid、antihypertensive_other、anticonvulsant、antigout、antacid、local_anesthetic、phosphate_binder；
3. **两种语义并存**（映射表逐字复用自 v1 `tasks/treatment/src/run.py` 已验证版本）：
   - `medication_feature`（本模块用）：**保留**慢病家用药类别（`_CHRONIC_HOME_MED` = vaccine / sleep_aid / antidepressant / antigout / thyroid / vitamin），因为「入院带药」正是要捕获的共存病信号；
   - `medication_category`（v1 答案语义）：把上述慢性类别从**答案空间**排除——仅供兼容，本模块不使用。

**输出**：`hadm_id → medications`（排序去重的类别列表）。

**关键代码**：`medication_categories.py: _match_category / medication_feature`；`medication_features.py: extract_medication_features`。

### 3.5 P4 既往史双轨 + sign 轨（`past_condition.py`、`sign_ner.py`、`compare_past_condition.py`、`run_sign_ner.py`）

#### ICD 轨（确定性、全量队列）

**输入**：**未门禁**的全量 `condition_recorded_post_hoc` 事件（`run_phenotype.build` 里刻意传 `events` 而非 `gated`——出院诊断是共存病/既往史的**来源**，不是受决策时刻约束的表现特征）。

**判定规则**（`_past_condition_from_icd`），满足任一即视为既往史：

1. **Z-code**：`concept_id` 冒号后的 ICD-10 码以 `z8` 或 `z9` 开头（Z80-Z99「个人/家族史」段）；
2. **慢病关键词**（23 个，对诊断名小写子串匹配）：diabetes、hypertension、copd、chronic obstructive、asthma、heart failure、chronic kidney、renal failure、atrial fibrillation、coronary artery、hyperlipidemia、hypothyroid、gout、osteoporosis、epilepsy、cirrhosis、anemia of chronic、depression、anxiety、obesity、stroke、cerebrovascular、peripheral vascular。

命中后经 `_normalize_icd_name` 归一化：

- 循环剥离 ICD-10 尾部限定词（`_ICD_QUALIFIER_RE`：unspecified / NOS / without complications / initial-subsequent encounter / sequela / stage / NEC 等；`_ICD_WITHOUT_RE`、`_ICD_WITH_RE`（不改变共病概念的 with X 后缀，如 with exacerbation）、`_ICD_SPACE_SUFFIX_RE`、`_ICD_UNSPECIFIED_PREFIX_RE`）；
- 约 60 条人工整理的 `_ICD_CONCEPT_MAP`：冗长/缩写诊断名 → 简洁概念（如 "atherosclerotic heart disease of native coronary artery"→"coronary artery disease"、"S/P admn tpa …"→"recent tpa administration"）；
- Z89「获得性缺失」类状态码统一坍缩为粗粒度 `"amputation/organ absence status"`。

#### NER 轨（text_ner_v2 sidecar，pilot 规模）

**输入**：`--past-condition-ner` 指向的 `entity_mentions.parquet`（存在才启用；`extract_past_condition_ner`）。

**判定规则**：`entity_type == "clinical_problem"` **且** `temporality == "historical"`（出院总结文本里的既往提及）。surface text 经 `_normalize_past_condition` 轻量归一化：剥离 5 个史前缀（`pmhx of / pmh of / h/o / history of / hx of`）+ 20 个缩写映射（cad→coronary artery disease、chf→congestive heart failure、htn→hypertension、dm→diabetes mellitus、afib→atrial fibrillation、esrd→end-stage renal disease、bph→benign prostatic hyperplasia 等）。

**双轨合并**（`run_phenotype._union_past_condition`）：按 `hadm_id` 做**排序集合并集**——两轨粒度/归一化不一致，合并是保守的「宁多勿漏」。

**双轨比较**（`compare_past_condition.py`）：在共同住院集上报告各轨覆盖、概念全集与逐住院 icd_only / ner_only / shared 重叠（默认 `--max-admissions 1500`）。此前一次实测：ICD 轨 1493 住院 / 444 概念，NER 轨 52 住院（pilot sidecar）/ 748 概念——两轨粒度差异大，有意义对比前需概念归一化层。

#### sign 轨（默认阻塞，已有解锁通道）

**「sign 阻塞」的含义**：全文档 NER pilot 把体格检查发现混标成 `symptom_or_sign / clinical_problem`，sidecar 中 **`physical_exam_finding` 实体数为零**；`past_condition.extract_signs_ner` 因此被写成**文档化 no-op**（返回空表）——宁可没有 sign 特征，也不从无此类型的来源里「发明」特征。

**解锁件**（`sign_ner.py` + `run_sign_ner.py` + `config/prompts/sign_physical_exam.md`）：

1. `build_physical_exam_frame`：从 `documents.parquet` 取 `source_text_kind == "discharge_summary"` 的 chunk，按 `chunk_index` 拼回全文，用 `_EXAM_HEADER_RE`（Physical Exam(ination) / Admission Exam / Exam on Admission / Exam on Discharge / Discharge Exam 等标题变体）定位章节起点，用 `_NEXT_SECTION_RE`（Discharge Diagnosis/Medications/Labs/Instructions/Disposition/Follow-up、Primary/Secondary Diagnosis、Plan、Assessment、Impression、Hospital Course、Active Problems、Procedures 等后续标题）截断；
2. `run_sign_ner.py --execute`：以提示词为 system、章节文本为 user，调用 **DeepSeek Flash**（OpenAI 兼容接口，`TEXT_NER_API_KEY / TEXT_NER_BASE_URL / TEXT_NER_MODEL` 来自项目根 `.env`；`temperature=0.0`、`response_format=json_object`、`thinking disabled`），`_parse_mentions` 只收 `entity_type == "physical_exam_finding"` 的 surface text，产出 `sign_features.parquet`（`hadm_id, features`）；默认 **dry-run**（只打印规模不发请求）；逐条写进度 `sign_ner`；
3. 提示词（`sign_physical_exam.md`）要求：surface_text 逐字复制、只标检查者客观发现（心音/杂音、呼吸音/啰音/哮鸣、JVP、水肿、压痛、腹部/神经/皮肤/关节发现）、**不标**患者主诉症状、**不标**生命体征数值（那是 P2 的事）、**不标**一般状态描述（alert / NAD / well-appearing 等，除非是偏离正常的神志/神经发现）、否定与可能发现用 assertion 保留（present/absent/possible/unknown）、temporality（current/historical/unclear）、laterality；
4. `filter_sign_features`（`sign_ner.py`）：装载时按 `SIGN_STOPLIST`（约 25 个大小写无关的正常发现速记：rrr、ctab、wwp、warm、well perfused、nt、nd、eomi、nabs、perrla、mmm、ncat、op clear 等）过滤——挖掘的 lift/支持度门槛本会淘汰它们，提前删可以缩小条件空间；
5. 接入方式：`run_phenotype.py --sign-features <sign_features.parquet>`。

### 3.6 P5 显式否定（`absent_features.py`）

**目的**：「否认胸痛 / denies fever」这类**显式否定**本身是强鉴别信号，单独成 `absent` 特征类型。

**输入**：门禁后的 `symptom_reported` 事件。

**判定规则**（`extract_absent_features`）：`assertion == "absent"` 且 `source_label` 非空 → 该短语成为 absent 特征。注意三点与在场症状不同：**不做** `normalize_condition` 归一化、**不做** Vital 词过滤、显示名统一加 `no ` 前缀（在 P6 `build_feature_frame` 里做）。否定组合的 ≥8 支持度约束由挖掘侧门槛执行，本模块不剪。

### 3.7 P6 组装（`phenotype.py`）与 feature_id 编码

**`feature_id(feature_type, display_name)`**（`phenotype.py: feature_id`）：

| 类别 | 编码 | 例 |
|---|---|---|
| 枚举型：`age_band / sex / physiologic_flag / medication` | `{type}:{value}`（原值直用） | `age_band:65-79`、`sex:M`、`physiologic_flag:tachycardia`、`medication:antidiabetic` |
| 自由文本型：`symptom / sign / past_condition / absent` | `{type}:{hash16}` | `symptom:1bce3b700f26488e`（= "chest pain" 的 hash16） |

**hash16 算法**：`hashlib.sha256(display_name.casefold().encode("utf-8")).hexdigest()[:16]`——对显示名先 casefold 再取 SHA-256 的前 16 个十六进制字符，保证大小写变体坍缩、ID 稳定可复现。

**注意 display_name 与编码值的差异**：`age_band` 的 feature_id 用裸分段值（`age_band:65-79`）而 display_name 是 `age 65-79`；`absent` 的 hash 输入是**带 `no ` 前缀**的完整短语。

**`build_feature_frame` 组装顺序**：人口学（age_band + sex，`gender` 仅收 `M/F`）→ 在场症状 → physiologic_flag → medication → absent → past_condition → sign，全部坍缩为长表四列（`hadm_id / feature_id / feature_type / display_name`），末尾 `drop_duplicates`。

**在场症状**（`extract_present_symptoms`）：`assertion == "present"` 的 `symptom_reported`，先经 `benchmark_common.conditions.normalize_condition`（小写化、去括号限定词、按 `,;` 分短语、短语/单 token 同义词替换、多主诉排序去重），再 `_split_phrases` 按 `", "` 拆分，最后过滤 `_VITAL_SIGN_WORDS`——**9 个体征词**（fever、hypertension、hypotension、tachycardia、bradycardia、tachypnea、bradypnea、hypoxia、hypothermia）只保留在 `physiologic_flag` 侧，避免同一概念以两种特征类型出现造成「fever; fever」式重复条件。

### 3.8 条件空间枚举与剪枝（`condition_space.py`）

**目的**：把长表特征事务转成挖掘输入——每个 `(hadm_id, 特征组合)` 一行。

**约束**（`_valid_combination`，对应设计文档 §7.1）：

- 组合规模 ∈ `[min_conditions, max_conditions]`（CLI 默认 1-4；正式口径 2-4）；
- **≥1 个临床类**特征（`CLINICAL_TYPES = {symptom, sign, physiologic_flag, absent}`）——纯人口学/用药/既往史组合不构成「临床表现」；
- **≤1 个 age_band 且 ≤1 个 sex**（`SINGLETON_TYPES`）——同一组合里「65-79 岁 + 40-64 岁」无意义；
- 特征按 `feature_id` 排序成**规范序**，`condition = "|".join(ids)` 作为组合 key。

**枚举**（`enumerate_conditions`）：按 `hadm_id` 分组，entries 按 feature_id 排序后用 `itertools.combinations` 逐 k 生成（k 从小到大、组内字典序），逐个校验约束后追加；`max_combinations_per_visit=500` 截断病态扇出（截断优先吃掉大 k 的组合）。

**Apriori L1 剪枝**（`min_feature_support`，`>1` 时启用）：先按 `feature_id` 统计 `nunique(hadm_id)` 支持度，低于阈值的特征**在组合之前整列删除**——支持度不足的单体不可能组成满足 `min_x_support` 的组合。组合级的深层支持度剪枝刻意留给挖掘侧（`mcq/mining.py` 的 cheap 拒绝），本层只做单体剪枝。

**规模数据**（此前全量 development 实测）：23,626 住院 → 3,183 个特征 → 2,443,998 个不同条件（约 70% 支持度 = 1，即靠挖掘侧短路消化）。

### 3.9 规则去重与收敛（`dedup_rules.py`，挖掘下游、维护在本目录）

- **B1 子sumption 去重**（`dedup_rules`）：规则按 score 降序贪心；当已保留的某规则与当前规则**同 `comparison_class` + 同 `target_investigation_id`**，且已保留者的条件特征是当前规则的**子集**时，当前规则被丢弃——保留的是「最小充分条件」的更一般规则，被丢的只是在其上叠加人口学/修饰词的变体。
- **B2 上下文变体收敛**（`converge_rules`，`--converge`）：把 accepted 规则按 `(target, 核心表现特征)` 分组——核心 = 条件里属于 `CORE_FEATURE_TYPES = {symptom, sign, physiologic_flag, absent}` 的部分（无核心则整组条件兜底）——每组保留**特征最少、score 最高、n_x 最大**的代表。
- 产物：去重/收敛后 JSONL + 可读 Markdown 表（比较类 | 条件特征 | 答案 | score | n_x | lift）。注意默认输入输出路径是硬编码的（`data/phenotype/conditional_rules_development.jsonl` 等）。

### 3.10 题目生成与人工审阅（`run_generation.py`、`make_review_html.py`、`make_review_md.py`）

- `run_generation.py`：取 accepted 规则按 score 降序前 N（`--n`，默认 20）→ `lock_options` 锁 A-D 选项 → LLM 写 stem+rationale（`generate_stem.md`）→ 独立自动评审（`review_question.md`）→ `export_human_queue` 人工队列（UTF-8-SIG CSV）→ `apply_human_decisions`（question_id → approved/rejected/revise）→ `export_gold`（**fail-closed**：exploratory profile 下 gold 为空）。默认 `FakeStructuredClient` 干跑，`--execute` 才用真实 DeepSeek Flash（`.env` 的 `TEXT_NER_*` 键）。全程写 `generation` 进度。
- `make_review_html.py` / `make_review_md.py`：从 `questions_reviewed.jsonl` 生成人工审阅材料——交互 HTML（每题 approved/rejected/revise 单选、「全选 approved」、导出决策 JSON 供 `--human-decisions` 回填）与 Markdown 清单（总表 + 逐题详情）。两者共用 `_score`：`wilson_lower × log2(lift) × log1p(n_xy) × bootstrap_stability`。

### 3.11 进度服务（`progress.py` + `serve_progress.py`）

`write_progress(task, data)` 以 temp+replace 原子写 `data/phenotype/progress/<task>.json`（任务名：`mining` / `generation` / `sign_ner`）；`serve_progress.py [--port 8766]` 在 127.0.0.1 起一个 `Cache-Control: no-store` 的静态服务，根目录 `data/phenotype/`，供浏览器监视页（`docs/reports/progress_monitor.html`）`fetch` 轮询——因为 `file://` 下 fetch 被浏览器拦截。

---

## 4. 数据契约

### 4.1 输入

| 输入 | 路径（默认） | 关键字段 | 校验 |
|---|---|---|---|
| 归一化事件 | `G:\Projects\llm_benchmark\data\derived\coronary_all_three_modules_full\event_pipeline\normalization\normalized_events.parquet`（默认） | `EVENT_COLS`：event_id、subject_id、hadm_id、event_kind、entity_type、source_label、preferred_name、source_concept_id、concept_id、assertion、event_time、evidence_phase、value_numeric、value_text、value_structured_json、unit | **fail-closed**：`benchmark_common.io._verify_normalized_events` 对照 `event_pipeline/workflow_manifest.json` 的 `stages.normalization.output_sha256["normalized_events.parquet"]`，哈希漂移即 `ValueError` |
| 切分表 | `versions/v1-template-stem/artifacts/investigation_selection/output/split/subject_split.parquet` | subject_id、role | 按 `--role`（默认 development）做 **subject 级**过滤（防同一患者跨 train/dev 泄露） |
| 原始归档 | `G:\Projects\llm_benchmark\data\validation\mimic-admission-raw-coronary-all-three-modules.jsonl`（默认） | `mimic_iv_hosp.patients[0]`（gender/anchor_age/anchor_year/anchor_year_group）、`admissions[0].admittime`、subject_id、hadm_id | 缺模块/字段即跳过该行（`parse_admission` 返回 None） |
| NER sidecar（可选） | `data/ner_v2_v2/sidecars/entity_mentions.parquet` | entity_type、temporality、hadm_id、surface_text | 不存在则 NER 轨静默为空 |
| 出院总结文档（sign 轨） | `data/ner_v2_v2/documents.parquet` | source_text_kind、hadm_id、chunk_index、chunk_text | 只取 discharge_summary |
| sign 特征（可选） | `data/phenotype/sign_features.parquet` | hadm_id、features | `--sign-features` 注入，装载时过停用词 |

本模块消费的 `event_kind`：`vital_measured`、`medication_reconciled`、`symptom_reported`、`condition_recorded_post_hoc`；`evidence_phase`：`source_event` vs `post_hoc`。

### 4.2 输出

**`visit_features_{role}.parquet`（长表，一行 = hadm_id × feature）**

| 字段 | 含义 |
|---|---|
| `hadm_id` | 住院 ID（字符串） |
| `feature_id` | 稳定特征 ID（见 §3.7 编码规则） |
| `feature_type` | 8 类之一：age_band / sex / symptom / sign / physiologic_flag / past_condition / medication / absent |
| `display_name` | 人类可读名（age_band 带 `age ` 前缀、absent 带 `no ` 前缀） |

**`visit_conditions_{role}.parquet`（一行 = hadm_id × 条件组合）**

| 字段 | 含义 |
|---|---|
| `hadm_id` | 住院 ID |
| `condition` | 组合 key：`\|`.join(按 feature_id 排序的 ids) |
| `condition_feature_ids` | list[str]，排序后的 feature_id（挖掘用） |
| `condition_features` | list[str]，与 ids 同序的 display_name（规则 schema 要求） |
| `n_features` | 组合规模 k |

**`hadm_demographics.parquet`**：subject_id、hadm_id、gender、anchor_age、anchor_year、anchor_year_group、`age_at_encounter`、`age_band`。

### 4.3 Manifest

- **`hadm_demographics.manifest.json`**（P1，写在 Parquet 同目录）：schema_version `phenotype-demographics-manifest/1.0.0`、输入/输出文件 **SHA-256**、counts（records_read / parsed / subjects / admissions）、age_bands 清单。
- **`phenotype_manifest_{role}.json`**（P6）：schema_version `phenotype-visit-transactions/1.0.0`、input（events_sha256、split_sha256、split_role、n_subjects）、`demographics_sha256`、min/max_conditions、min_feature_support、counts（n_admissions、n_admissions_with_index、n_features、n_feature_rows、n_conditions）、outputs 路径。
- 挖掘下游另有 `conditional_rules_development.jsonl`（accepted 规则，含 comparison_class、condition_feature_ids、condition_display_names、target_investigation_id/name、score、n_x、lift 等字段）。

---

## 5. 正确性与可复现性保障

1. **输入 fail-closed**：`normalized_events.parquet` 与上游 workflow manifest 的 SHA-256 不一致直接抛错（`_verify_normalized_events`）；门禁中无 index 的住院整段丢弃，不猜测时间。
2. **全链确定性**：年龄公式纯算术；`feature_id` 只依赖 casefold 后的显示名（hash16）或枚举值；条件枚举先排序后组合（规范序）；P1 输出按 hadm_id 排序落盘；同一输入必然产出逐字节可比的 Parquet + manifest 哈希。
3. **无中生有防护**：sign 轨在 sidecar 无 `physical_exam_finding` 时是显式 no-op；性别只收 M/F；年龄缺失则该行无 age_band 特征而非补默认。
4. **概念去重**：`_VITAL_SIGN_WORDS` 防止同一体征概念同时以 symptom 与 physiologic_flag 出现；长表末尾 `drop_duplicates`。
5. **前瞻性**：P0 时间门禁 + `evidence_phase` 双保险（post_hoc 永不可用），从机制上排除答案泄露。
6. **单元测试**：`tests/test_phenotype.py`（307 行）覆盖 age_band 边界、年龄推算、°F 换算、BP systolic 解析、慢病用药保留/排除、absent 断言、index 与可用性、feature_id 稳定性、vital 词过滤、ICD 轨（Z-code/慢病词/急性排除）、`_normalize_icd_name`（含 C1 扩展）、NER 轨（historical 过滤 + 前缀/缩写归一化）、体格检查章节切分、条件空间约束。
7. **LLM 环节可控**：`run_sign_ner` / `run_generation` 默认 dry-run / FakeClient；真实调用需显式 `--execute` + `.env` 凭据。

---

## 6. 使用方法

所有命令在仓库根 `D:\Projects\llm_benchmark` 下执行（PowerShell 反引号续行）。

**P1 人口学（全量，写 hadm_demographics.parquet + manifest）**

```powershell
.\.venv\Scripts\python.exe .\data_pipeline\phenotype\run_demographics.py `
  --raw-archive G:\Projects\llm_benchmark\data\validation\mimic-admission-raw-coronary-all-three-modules.jsonl `
  --out D:\Projects\llm_benchmark\data\phenotype\hadm_demographics.parquet
```

（`--max-lines` 缺省为全量；传整数可截断冒烟。）

**P6 端到端特征 + 条件空间（全量 development）**

```powershell
.\.venv\Scripts\python.exe .\data_pipeline\phenotype\run_phenotype.py `
  --role development `
  --min-conditions 2 `
  --max-conditions 4 `
  --min-feature-support 10 `
  --sign-features D:\Projects\llm_benchmark\data\phenotype\sign_features.parquet `
  --past-condition-ner D:\Projects\llm_benchmark\data\ner_v2_v2\sidecars\entity_mentions.parquet
```

（`--events/--split/--demographics/--out-dir` 均有默认值；`--max-admissions` 可做小样本冒烟；`--sign-features` / `--past-condition-ner` 省略则两轨为空。）

**sign 轨 NER（默认 dry-run；`--execute` 真实调用 DeepSeek Flash）**

```powershell
.\.venv\Scripts\python.exe .\data_pipeline\phenotype\run_sign_ner.py `
  --documents D:\Projects\llm_benchmark\data\ner_v2_v2\documents.parquet `
  --max-docs 50 --execute
```

**端到端挖掘验证（development 条件 → accepted 规则）**

```powershell
.\.venv\Scripts\python.exe .\data_pipeline\phenotype\run_mining_verification.py `
  --profile exploratory
```

**P4 双轨比较探针**

```powershell
.\.venv\Scripts\python.exe .\data_pipeline\phenotype\compare_past_condition.py `
  --role development --max-admissions 1500
```

**规则去重 / 收敛**

```powershell
.\.venv\Scripts\python.exe .\data_pipeline\phenotype\dedup_rules.py --converge
```

**题目生成（默认 FakeClient；`--execute` 真实出题）**

```powershell
.\.venv\Scripts\python.exe .\data_pipeline\phenotype\run_generation.py `
  --n 20 --profile exploratory `
  --human-decisions <decisions.json> --execute
```

**审阅材料与进度服务**

```powershell
.\.venv\Scripts\python.exe .\data_pipeline\phenotype\make_review_html.py
.\.venv\Scripts\python.exe .\data_pipeline\phenotype\make_review_md.py
.\.venv\Scripts\python.exe .\data_pipeline\phenotype\serve_progress.py --port 8766
```

**测试**

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD="1"
E:\Anaconda3\python.exe -m pytest tests/test_phenotype.py versions/v2-llm-stem/tests -q -p no:cacheprovider
```

---

## 7. 已知限制与设计取舍

1. **sign 轨默认阻塞**：全文档 NER pilot 产出为 0 的 `physical_exam_finding`，`extract_signs_ner` 是显式 no-op；解锁需 `run_sign_ner.py --execute` 全量跑章节级 NER（新增 API 成本）并经 `--sign-features` 注入。默认构建里 sign 特征类型实际为空。
2. **NER 既往史轨是 pilot 规模**：仅一个 text_ner_v2 sidecar（此前记录约 300 文档 / 121 hadm_id），与 ICD 轨全量（约 1493/1500 住院）不可同日而语；两轨概念粒度不一致（ICD 正式名 vs NER 原文缩写，仅做了轻量归一化），做严格一致性评估前需要专门的概念归一化层——当前合并采取保守并集。
3. **ICD 既往史是启发式**：Z-code + 23 个慢病关键词 + 正则剥限定词 + 约 60 条人工映射，均为探索性规则，待临床审核冻结；MIMIC-IV `diagnoses_icd` 的 POA（present-on-admission）语义弱，「出院诊断→既往史」的推断有假阳性/假阴性风险。
4. **组合爆炸**：全量 2-4 特征条件约 244 万个（约 70% 支持度 = 1）。本层只做 Apriori L1 单体剪枝 + 每 visit 500 组合截断，深层剪枝依赖挖掘侧 `min_x_support` cheap 拒绝（跳过 bootstrap）——全量挖掘仍需数十分钟。
5. **路径硬编码**：`dedup_rules.py`、`make_review_html.py` / `make_review_md.py` 及各 run_* 的默认输入输出是绝对路径常量，跨机器需显式传参；`run_mining_verification.py` 定义了 rejected 规则输出路径但默认 `materialize_rejections=False`，rejected 只进内存计数不落盘。
6. **年龄推算的精度**：`anchor_age + (admit_year − anchor_year)` 只有年级精度，且 MIMIC 对 89 岁以上做了锚定偏移；`<18` 段是兜底而非设计主场景（MIMIC-IV 为成人库）。
7. **阈值与词表的维护成本**：9 个体征阈值、32 个用药类别、23 个慢病关键词、停用词表均以「已采纳、待临床复审」状态硬编码/半硬编码（yaml 仅覆盖体征）；改阈值需重跑 P2 及下游全部产物。
