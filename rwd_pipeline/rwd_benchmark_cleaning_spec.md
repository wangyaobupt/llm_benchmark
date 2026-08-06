# MIMIC RWD Clinical Benchmark 数据清洗规范

## 1. 文档目的

本文档规定 `rwd_benchmark_visits.csv` 中 17 个字段的清洗范围、清洗结果、输出文件和 LLM Prompt。

清洗只处理需要从自由文本中提取实体的字段。来自结构化数据的字段不重复清洗；当前没有可用清洗内容的字段暂不处理。

## 2. 清洗输出与标准化边界

### 2.1 输入与输出文件

- 原始输入文件为 `rwd_benchmark_visits.csv`，清洗过程不得修改或覆盖该文件。
- 清洗结果另存为项目根目录下的 `out/rwd_benchmark_visits_cleaned.csv`。
- 清洗结果文件与原始文件保持相同的 17 个字段、列顺序、Visit 行数和 Visit 顺序。
- `subject_id` 和 `hadm_id` 必须与原始文件逐行一致。
- `chief_complaint`、`history_of_present_illness`、`past_medical_history` 和 `medications_on_admission` 写入 LLM 返回的 `entities` 数组，CSV 单元格保存为合法 JSON 字符串数组，例如 `["chest pain","dyspnea"]`。
- LLM 响应外层对象 `{"entities":[...]}` 只用于约束模型输出；写入清洗结果文件时只保存其中的 `entities` 数组。
- 四个 LLM 字段没有可提取实体时，清洗结果单元格写入 `[]`。
- 其余 13 个字段从原始文件逐值复制，不进行修改。

### 2.2 清洗与标准化边界

- 清洗阶段从指定自由文本字段中提取原子化实体，不保留完整句式或叙述结构。
- 实体保留原文中的医学表达，不展开缩写、不纠正拼写、不翻译、不合并同义词，也不转换为标准术语。
- 同义词归并、标准名称映射、编码映射和单位换算属于后续标准化阶段。
- 每个字段只使用自身内容，不从其他字段或外部医学知识补充实体。
- 调用 LLM 前删除字段文本中的 `___` 和 `[**...**]` 去标识化占位符；不修改原始输入文件。
- LLM 返回的实体不得包含去标识化占位符，包含占位符的响应视为无效并重试。
- 明确否定的实体不输出；不确定但属于字段目标范围的实体保留原文中的不确定修饰词。
- 只进行严格表面重复去重：比较时去除首尾空白、合并连续空白并忽略英文字母大小写，输出保留第一次出现的表达。
- 表面表达不同的同义词不在清洗阶段合并。

## 3. 字段处理总表

| 序号 | 字段 | 处理方式 |
|---:|---|---|
| 1 | `subject_id` | 无需清洗 |
| 2 | `hadm_id` | 无需清洗 |
| 3 | `age_at_encounter` | 无需清洗 |
| 4 | `sex` | 无需清洗 |
| 5 | `chief_complaint` | 使用 LLM 抽取主诉实体 |
| 6 | `history_of_present_illness` | 使用 LLM 抽取当前病程实体 |
| 7 | `past_medical_history` | 使用 LLM 抽取既往临床实体 |
| 8 | `medications_on_admission` | 使用 LLM 抽取入院药物名称 |
| 9 | `investigation_orders` | 当前不进行清洗 |
| 10 | `investigation_reports` | 无需清洗 |
| 11 | `primary_icd_code` | 无需清洗 |
| 12 | `primary_diagnosis_name` | 无需清洗 |
| 13 | `primary_icd_version` | 无需清洗 |
| 14 | `other_diagnoses` | 无需清洗 |
| 15 | `medication_prescriptions` | 无需清洗 |
| 16 | `procedures` | 无需清洗 |
| 17 | `discharge_record` | 当前不进行清洗 |

## 4. 通用 LLM 输出规则

四个 LLM 清洗字段统一使用：

- API 服务：DeepSeek API
- Base URL：`https://api.deepseek.com`
- 模型：`deepseek-v4-flash`
- API Key: 通过 `DEEPSEEK_API_KEY` 环境变量提供，不写入代码或文档
四个字段分别使用第 5 节规定的字段专属 Prompt，不共用同一个实体抽取 Prompt。

四个 LLM 清洗字段统一返回：

```json
{"entities":["entity one","entity two"]}
```

通用规则：

- `entities` 必须是 JSON 字符串数组。
- 每个数组元素只保存一个原子化实体，不保存完整句子、证据、解释、分类或其他属性。
- 实体按原文出现顺序输出。
- 明确并列或列表形式的多个实体分别输出。
- 删除主语、谓语、连接词、列表编号、独立时间表达和其他不属于实体本身的内容。
- 保留与实体直接组成概念的部位、侧别和有临床意义的修饰词。
- 没有符合条件的实体时返回空数组。
- LLM 只能返回指定 JSON 对象，不得返回 Markdown 或解释文本。

对于非必需字段 `history_of_present_illness`、`past_medical_history` 和 `medications_on_admission`：

- 空单元格不调用 LLM，直接使用空数组。
- 只有格式字符或去标识化占位符时返回空数组。
- 非空文本中没有符合字段范围的实体时返回空数组。

## 5. LLM 清洗字段

### 5.1 `chief_complaint`

从 `chief_complaint` 中提取明确表示本次就诊或住院原因的实体。实体可以是症状、体征、临床状态、疾病、损伤、异常发现、事件或计划性操作原因，不限定为症状。

保留部位、侧别和直接修饰实体的病程词；删除独立时间表达。明确否定的实体不输出；不确定但构成本次就诊原因的实体保留不确定修饰词。

#### LLM Prompt

```text
Extract atomic chief-complaint entities from one clinical chief complaint.

Return exactly {"entities":["entity one","entity two"]}.

Rules:
- Use only the chief_complaint text.
- Include each explicitly stated reason for the current visit or admission,
  including a symptom, sign, clinical state, disease, injury, abnormal finding,
  event, or planned procedure reason.
- An atomic entity is one self-contained clinical concept, not necessarily one
  word. Split lists only when each result is independently meaningful.
- Keep anatomical site, laterality, uncertainty, and clinically meaningful
  qualifiers attached to the entity they modify. Remove framing, conjunctions,
  numbering, and standalone time expressions.
- Exclude explicitly negated entities.
- Never output a standalone modifier.
- Preserve source wording. Do not infer, expand abbreviations, correct spelling,
  translate, merge synonyms, or standardize terms.
- Deduplicate after trimming and collapsing whitespace and comparing English
  letters case-insensitively; preserve the first expression.
- Return an empty array when no entity qualifies. Return JSON only, with no
  explanation, evidence, categories, markdown, or original sentence.

Example:
Input: {"chief_complaint":"Worsening right foot pain and swelling for three days; no fever"}
Output: {"entities":["Worsening right foot pain","right foot swelling"]}

Input: {"chief_complaint":"Possible seizure, cardiogenic ___"}
Output: {"entities":["Possible seizure"]}
```

### 5.2 `history_of_present_illness`

该字段为非必需字段。从非空 HPI 中提取本次病程中的当前症状、体征、临床状态、疾病、损伤、异常发现和相关事件。

排除背景性既往疾病、既往操作、家族史、药物、治疗措施、检查名称和未来计划。原文明示的当前疾病或异常发现可以保留，但不得由检查结果推断诊断。

#### LLM Prompt

```text
Extract atomic current clinical entities from one history of present illness.

Return exactly {"entities":["entity one","entity two"]}.

Rules:
- Use only the history_of_present_illness text.
- Include explicitly stated current symptoms, signs, clinical states, diseases,
  injuries, abnormal findings, and relevant events.
- An atomic entity is one self-contained clinical concept, not the shortest
  phrase. Split lists only when each result is independently meaningful.
- Never output a standalone site, severity, course, timing, trigger, relieving
  factor, radiation direction, or other modifier. Keep it attached to the
  clinical entity it describes.
- First identify the current presentation. A condition introduced as history of,
  known for, with a history of, or status post is background even when it occurs
  in the same sentence as the current illness.
- Exclude background conditions, family history, medications, and every past,
  performed, or planned treatment, operation, procedure, or postoperative action.
- Exclude diagnostic test names and every normal or negative finding. A current
  abnormal finding explicitly stated by a test may be kept without the test name
  and with its uncertainty wording; never infer a diagnosis or abnormality.
- Do not output an isolated test value unless the source explicitly describes it
  as an abnormal or clinically significant current finding.
- Exclude explicitly negated entities. Keep uncertainty only for a qualifying
  current entity.
- Preserve source wording. Do not infer, expand abbreviations, correct spelling,
  translate, merge synonyms, or standardize terms.
- Deduplicate after trimming and collapsing whitespace and comparing English
  letters case-insensitively; preserve the first expression.
- Return an empty array when no entity qualifies. Return JSON only, with no
  explanation, evidence, categories, markdown, or original sentences.

Example:
Input: {"history_of_present_illness":"History of COPD. She has worsening abdominal pain (constant, epigastric and radiates to back), nausea, and no fever. Treated with IV fluids."}
Output: {"entities":["worsening abdominal pain (constant, epigastric and radiates to back)","nausea"]}

Input: {"history_of_present_illness":"Patient with AF, CAD and COPD presents for elective hernia repair. CXR was negative for acute process. The hernia contains incarcerated sigmoid colon."}
Output: {"entities":["incarcerated sigmoid colon"]}
```

### 5.3 `past_medical_history`

该字段为非必需字段。从非空既往史中提取本次住院前已经存在的疾病、慢性临床状态、疾病并发症、既往损伤、既往手术和既往操作。

排除当前主诉、当前疾病、家族史、社会史、药物、检查、治疗和未来计划。`None`、`No past medical history`、`Unknown` 和 `Unable to obtain` 不生成实体。

#### LLM Prompt

```text
Extract atomic past clinical entities from one past medical history.

Return exactly {"entities":["entity one","entity two"]}.

Rules:
- Use only the past_medical_history text.
- Include diseases, chronic conditions, complications, prior injuries, prior
  surgeries, and prior invasive procedures that existed before admission.
- An atomic entity is one self-contained clinical concept. Split lists only when
  each result is independently meaningful.
- Exclude current complaints or diseases, family history, social behaviors and
  exposures, medications, tests, non-procedural treatments, and future plans.
  Include a substance-related condition only when explicitly stated as a
  clinical diagnosis, not as mere use or exposure.
- Prior surgery and invasive procedures qualify; chemotherapy, radiotherapy,
  rehabilitation, and medication courses do not.
- Remove history framing such as history of, h/o, status post, and s/p while
  keeping the clinical entity that follows it.
- Exclude explicitly negated entities. Keep uncertainty only for a qualifying
  past entity.
- Preserve source wording. Do not infer, expand abbreviations, correct spelling,
  translate, merge synonyms, or standardize terms.
- Deduplicate after trimming and collapsing whitespace and comparing English
  letters case-insensitively; preserve the first expression.
- Treat None, No past medical history, Unknown, and Unable to obtain as empty.
  Return JSON only, with no explanation, evidence, categories, or markdown.

Example:
Input: {"past_medical_history":"Hypertension; h/o breast ca; s/p right lumpectomy; tobacco use"}
Output: {"entities":["Hypertension","breast ca","right lumpectomy"]}

Input: {"past_medical_history":"Craniotomy, irradiation to 6,120 cGy, 3 cycles of Temodar, depression"}
Output: {"entities":["Craniotomy","depression"]}
```

### 5.4 `medications_on_admission`

该字段为非必需字段。从非空入院用药文本中只提取患者入院前或入院时仍在使用的药物名称。

纳入处方药、非处方药、维生素、补充剂和 PRN 药物。删除剂量、规格数值、单位、途径、频次、疗程日期、执行条件、PRN 适应证、列表编号和药物列表说明。

品牌名与通用名同时出现在同一药物表达中时作为一个实体保留；复方药及其括号中的成分表达作为一个实体保留。排除明确未使用、已停用、已完成疗程、仅计划未来使用的药物和药物过敏项。

#### LLM Prompt

```text
Extract medication-name entities from one medications-on-admission text.

Return exactly {"entities":["medication one","medication two"]}.

Rules:
- Use only the medications_on_admission text.
- Include prescription and over-the-counter medications, vitamins, supplements,
  and PRN medications taken before or at admission.
- Return medication names only. Remove doses, strengths, concentrations, units,
  routes, frequencies, dates, conditions, PRN indications, numbering, and list
  boilerplate before deduplication.
- Keep parenthetical text only when it is a brand, generic name, or ingredient
  expression. Remove parenthetical strengths, dose ratios, routes, and frequency
  descriptions.
- Preserve a number only when it is intrinsic to the medication name, such as
  HumuLIN 70/30, Vitamin D3, or CoQ10.
- A trailing number or numeric ratio is a strength even without a unit or space.
  Remove it unless it is an intrinsic medication name such as HumuLIN 70/30.
- Keep a combination product as one entity; do not split active ingredients.
- Include an explicit medication even when its dose is unknown or the source
  list may be inaccurate.
- Exclude medications described as not taken, stopped, discontinued, completed,
  or planned only for future use. Exclude allergies and non-medication content.
- Preserve source naming. Do not infer, expand abbreviations, correct spelling,
  translate, merge synonyms, or standardize names.
- Deduplicate cleaned names after trimming and collapsing whitespace and
  comparing English letters case-insensitively; preserve the first expression.
- Treat None, No medications, Unknown, and Unable to obtain as empty. Return JSON only,
  with no explanation, evidence, categories, markdown, or original text.

Example:
Input: {"medications_on_admission":"venlafaxine hcl er 30; Advair250/50; HumuLIN 70/30"}
Output: {"entities":["venlafaxine hcl er","Advair","HumuLIN 70/30"]}

Input: {"medications_on_admission":"PredniSONE 30 mg, then 20 mg, then 10 mg; BuPROPion XL (Once Daily)"}
Output: {"entities":["PredniSONE","BuPROPion XL"]}
```
