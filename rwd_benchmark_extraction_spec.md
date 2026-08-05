# MIMIC RWD Clinical Benchmark 数据抽取规范

## 1. 文档定位与抽取范围

本文档统一规定 MIMIC RWD Clinical Benchmark 的 Visit 边界、纳入条件、正式输出 Schema、字段来源、转换、去重、排序和缺失处理，是数据抽取实现与验收的权威规范。

本规范使用 MIMIC-IV v3.1。全文中的 `dataset` 表示数据根目录 `/data/ehr/MIMIC/physionet.org/files/mimiciv/3.1`；例如，`dataset/hosp/admissions.csv` 解析为 `/data/ehr/MIMIC/physionet.org/files/mimiciv/3.1/hosp/admissions.csv`。迁移运行环境时，只需相应调整该数据根目录。

抽取范围如下：

- `dataset/hosp/admissions.csv` 中的全部住院记录定义候选 Visit 集合；
- admissions 中每个非空且唯一的 `hadm_id` 对应一个候选 Visit，并按源文件顺序处理；
- `dataset/hosp` 提供住院、人口学、诊断、医嘱、实验室结果、药物处方和操作数据；
- `dataset/note` 提供 DS 出院小结、放射学报告及其结构化明细；
- 正式输出只包含通过资格筛选的 Visit，且每个 Visit 只包含当前住院的数据，不包含同一患者其他住院的信息。

## 2. Visit 边界与纳入条件

### 2.1 Visit 边界

- 一个 Visit 固定等于一个 `hadm_id`，`hadm_id` 是 Visit 的权威标识。
- 正式 `subject_id` 和 `hadm_id` 来自 `dataset/hosp/admissions.csv`。
- `admissions.csv` 中每一行住院记录都是一个候选 Visit。
- `subject_id` 和 `hadm_id` 必须非空，`hadm_id` 必须在 admissions 中唯一；违反任一条件均属于全局数据完整性错误，抽取必须终止。
- 候选 Visit 按 admissions 源文件顺序进入资格评估。
- 每个 `hadm_id` 完全独立处理。
- 所有结构化记录和文本必须明确属于当前 `hadm_id`，其中的 `subject_id` 必须与 `admissions.subject_id` 一致。
- 不查询、不继承、不汇总同一 `subject_id` 的其他住院记录。
- 不允许仅根据 `subject_id` 将 `hadm_id` 为空或属于其他住院的记录归入当前 Visit。
- 发现 subject/hadm 关系冲突时不得自动修复、覆盖或跨 Visit 合并。

### 2.2 Visit 纳入条件

每个 Visit 必须同时满足：

1. 能连接到唯一、有效的 `patients.csv` 人口学记录；
2. `age_at_encounter` 可计算且大于或等于 18；
3. `patients.gender` 为有效的 `M` 或 `F`；
4. 当前 `hadm_id` 至少有一个代码非空、ICD 版本有效且能连接诊断字典的诊断；
5. 当前 `hadm_id` 存在唯一、有效且可映射的 `seq_num=1` 主诊断；
6. 当前 `hadm_id` 至少存在一份 `note_type=DS`、`subject_id` 一致且 `text` 非空的出院小结；
7. 至少一份符合条件的 DS 包含明确、非空的 `Chief Complaint` 章节，并能按第 4.2 节的规则唯一选定来源文档。

任一必需条件不满足时排除整个 Visit。非必需字段缺失不影响 Visit 纳入，并按第 3.4 节的规则表示缺失。

## 3. 正式输出 Schema

### 3.1 输出文件与粒度

- 唯一正式输出文件为 `rwd_benchmark_visits.csv`。
- 每个 eligible `hadm_id` 恰好一行，`hadm_id` 在文件内唯一。
- 输出只包含本节规定的 17 个字段，不增加审计、来源追踪或运行状态列。

### 3.2 固定列顺序

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

CSV 表头固定为：

```csv
subject_id,hadm_id,age_at_encounter,sex,chief_complaint,history_of_present_illness,past_medical_history,medications_on_admission,investigation_orders,investigation_reports,primary_icd_code,primary_diagnosis_name,primary_icd_version,other_diagnoses,medication_prescriptions,procedures,discharge_record
```

### 3.3 字段总表

| 序号 | 字段名 | 数据形式 | 权威来源 | 必需性 | CSV 缺失表示 |
|---:|---|---|---|---|---|
| 1 | `subject_id` | ID 字符串 | `admissions.subject_id` | 必需 | 缺失时排除 Visit |
| 2 | `hadm_id` | ID 字符串 | `admissions.hadm_id` | 必需 | 缺失时排除 Visit |
| 3 | `age_at_encounter` | 整数 | `patients` + `admissions.admittime` | 必需 | 无法计算时排除 Visit |
| 4 | `sex` | `M` 或 `F` | `patients.gender` | 必需 | 无效时排除 Visit |
| 5 | `chief_complaint` | `str` | DS 的 Chief Complaint 章节 | 必需 | 缺失时排除 Visit |
| 6 | `history_of_present_illness` | `str` | 选定 DS 的 History of Present Illness 章节 | 非必需 | 空单元格 |
| 7 | `past_medical_history` | `str` | 选定 DS 的 Past Medical History 章节 | 非必需 | 空单元格 |
| 8 | `medications_on_admission` | `str` | 选定 DS 的 Medications on Admission 章节 | 非必需 | 空单元格 |
| 9 | `investigation_orders` | JSON 对象数组 | `poe` + `poe_detail` | 非必需 | `[]` |
| 10 | `investigation_reports` | JSON 对象 | `labevents` + `d_labitems`；`radiology` + `radiology_detail` | 非必需 | `{"laboratory":[],"radiology":[]}` |
| 11 | `primary_icd_code` | ICD 代码字符串 | `diagnoses_icd.seq_num=1` | 必需 | 缺失时排除 Visit |
| 12 | `primary_diagnosis_name` | 疾病名称 | `d_icd_diagnoses.long_title` | 必需 | 缺失时排除 Visit |
| 13 | `primary_icd_version` | ICD 版本字符串 | `diagnoses_icd.icd_version` | 必需 | 缺失时排除 Visit |
| 14 | `other_diagnoses` | JSON 字符串数组 | `seq_num>1` 的有效诊断 | 非必需 | `[]` |
| 15 | `medication_prescriptions` | JSON 对象数组 | `prescriptions.drug_type=MAIN` | 非必需 | `[]` |
| 16 | `procedures` | JSON 对象数组 | `procedures_icd` + `d_icd_procedures` | 非必需 | `[]` |
| 17 | `discharge_record` | 文本 | DS 的 Follow-up Instructions 章节 | 非必需 | 空单元格 |

### 3.4 通用存储规则

- CSV 使用 UTF-8 编码。
- `subject_id`、`hadm_id`、`primary_icd_code` 和 `procedures.icd_code` 按字符串处理，保留前导零。
- 标量非必需字段缺失时写空单元格。
- 集合字段没有元素时写合法 JSON 数组 `[]`。
- 不使用字符串 `nan`、`None` 或 `null` 表示 CSV 缺失。
- 含逗号、双引号或换行的文本按照标准 CSV 规则引用和转义。
- 文本字段保留内部换行。
- `other_diagnoses` 保存 JSON 字符串数组。
- `investigation_orders`、`medication_prescriptions` 和 `procedures` 保存 JSON 对象数组。
- `investigation_reports` 保存为包含 `laboratory` 和 `radiology` 两个数组的 JSON 对象。
- JSON 对象的固定属性必须完整，不因源值缺失而省略属性。源字段缺失、CSV 为空或字符串去除首尾空白后为空时保存 JSON `null`；有效字符串保存为 JSON 字符串，有效数值保存为 JSON 数值。不得使用空字符串或字符串 `"nan"`、`"None"`、`"null"` 表示属性缺失。
- 名称标准化只用于比较、去重和排序；正式输出保留所选源记录中的名称。

### 3.5 字段保存格式示例

以下标量示例表示字段的逻辑类型；写入 CSV 时按第 3.4 节的规则序列化。

#### 标量字段

| 字段 | 保存类型 | 示例 |
|---|---|---|
| `subject_id` | `str` | `"10152414"` |
| `hadm_id` | `str` | `"27578173"` |
| `age_at_encounter` | `int` | `60` |
| `sex` | `str` | `"M"` |
| `chief_complaint` | `str` | `"nausea, fatigue"` |
| `history_of_present_illness` | `str` | `"Two days of fever.\nSymptoms worsened overnight."` |
| `past_medical_history` | `str` | `"Hypertension\nType 2 diabetes"` |
| `medications_on_admission` | `str` | `"1. Aspirin 81 mg daily\n2. Metoprolol 50 mg twice daily"` |
| `primary_diagnosis_name` | `str` | `"Acute kidney failure, unspecified"` |
| `primary_icd_version` | `str` | `"ICD-10-CM"` |

非必需标量字段缺失时保存为空单元格，不写成 JSON 值。

#### 集合字段

`investigation_orders`：

```json
[
  {
    "order_type": "Imaging",
    "order_subtype": "CT Scan",
    "poe_detail": [
      {
        "field_name": "Body Part",
        "field_value": "Head"
      },
      {
        "field_name": "Contrast",
        "field_value": "Without Contrast"
      }
    ]
  }
]
```

`investigation_reports`：

```json
{
  "laboratory": [
    {
      "d_labitems": {
        "itemid": 50912,
        "label": "Creatinine",
        "fluid": "Blood",
        "category": "Chemistry"
      },
      "labevents": {
        "value": "1.5",
        "valuenum": 1.5,
        "valueuom": "mg/dL",
        "ref_range_lower": 0.4,
        "ref_range_upper": 1.1,
        "flag": "abnormal",
        "comments": null
      }
    },
    {
      "d_labitems": {
        "itemid": 50971,
        "label": "Potassium",
        "fluid": "Blood",
        "category": "Chemistry"
      },
      "labevents": {
        "value": "4.2",
        "valuenum": 4.2,
        "valueuom": "mEq/L",
        "ref_range_lower": 3.3,
        "ref_range_upper": 5.1,
        "flag": null,
        "comments": null
      }
    }
  ],
  "radiology": [
    {
      "radiology": {
        "text": "CT head report..."
      },
      "radiology_detail": [
        {
          "field_name": "exam_name",
          "field_value": "CT HEAD W/O CONTRAST",
          "field_ordinal": 1
        }
      ]
    },
    {
      "radiology": {
        "text": "Chest X-ray report..."
      },
      "radiology_detail": [
        {
          "field_name": "exam_name",
          "field_value": "CHEST X-RAY",
          "field_ordinal": 1
        }
      ]
    }
  ]
}
```

`other_diagnoses`：

```json
["Cardiogenic shock", "Septic shock", "Acute kidney failure, unspecified"]
```

`medication_prescriptions`：

```json
[
  {
    "drug": "Vancomycin",
    "prod_strength": "500 mg",
    "form_rx": "VIAL",
    "dose_val_rx": "1000",
    "dose_unit_rx": "mg",
    "route": "IV",
    "doses_per_24_hrs": 2
  },
  {
    "drug": "Furosemide",
    "prod_strength": "10 mg/mL",
    "form_rx": "VIAL",
    "dose_val_rx": "40",
    "dose_unit_rx": "mg",
    "route": "IV",
    "doses_per_24_hrs": 1
  },
  {
    "drug": "Aspirin",
    "prod_strength": null,
    "form_rx": "TABLET",
    "dose_val_rx": "81",
    "dose_unit_rx": "mg",
    "route": "PO",
    "doses_per_24_hrs": null
  }
]
```

`procedures`：

```json
[
  {
    "procedure_name": "Insertion of endotracheal tube",
    "icd_code": "9604",
    "icd_version": "ICD-9-PCS"
  },
  {
    "procedure_name": "Respiratory Ventilation, Greater than 96 Consecutive Hours",
    "icd_code": "5A1955Z",
    "icd_version": "ICD-10-PCS"
  }
]
```

## 4. 共用来源与解析规则

### 4.1 住院和人口学关联

- `admissions.csv` 中通过基础 ID 完整性校验的全部住院记录进入候选 Visit 集合。
- 候选 Visit 保留 admissions 源文件顺序。
- `admissions.subject_id` 是正式患者 ID，并用于连接 `patients.csv` 及校验所有临床来源。
- admission 和 patient 关联必须唯一；缺失、重复或冲突均不能通过资格校验。

### 4.2 DS 出院小结选择与章节解析

以下字段使用同一份选定的 DS 出院小结：

- `chief_complaint`；
- `history_of_present_illness`；
- `past_medical_history`；
- `medications_on_admission`；
- `discharge_record`。

首先建立当前 Visit 的 DS 候选集。每条候选记录必须满足：

- `note_type=DS`；
- `hadm_id` 等于当前 Visit；
- `subject_id` 与 `admissions.subject_id` 一致；
- `text` 非空。

`note_type=AD` 的补充记录不进入候选集。对每条候选 DS 独立解析 Chief Complaint，只保留包含明确、非空主诉的候选记录。若多条候选记录均包含有效主诉，依次按 `note_seq`、`charttime`、`storetime`、`note_id` 降序选择最新记录；可空的 `storetime` 排在非空值之后。选中的 DS 同时作为上述五个文本字段的共同来源。不同 DS 的章节内容不得合并。

如果没有符合基础条件的 DS，或所有候选 DS 均不包含明确、非空的 Chief Complaint，则排除整个 Visit。

章节解析采用大小写不敏感的顶层标题匹配，允许标题末尾带英文冒号。章节内容从目标标题之后开始，到下一个已知顶层标题之前结束。除字段专门规则规定的清理外，去除章节首尾空白，保留内部原文、顺序和换行。

## 5. 逐字段最终抽取规则

### 5.1 `subject_id`

- 来源：`dataset/hosp/admissions.csv` 的 `subject_id`。
- 关联：与同一行的 `hadm_id` 共同定义候选 Visit，并用于连接 `patients.csv` 和当前 Visit 的临床来源。
- 校验：必须非空，并与 `patients` 及当前 Visit 所有临床来源中的 `subject_id` 一致。
- 输出：字符串。
- admissions 中值为空或临床来源发生 subject/hadm 冲突时，视为数据完整性错误并终止抽取。

### 5.2 `hadm_id`

- 语义：MIMIC 单次住院标识，是 Visit 的唯一权威标识。
- 权威来源：`dataset/hosp/admissions.csv` 的 `hadm_id`；不得从其他数据表推导或改写。
- 候选范围：admissions 中每个非空且唯一的 `hadm_id` 直接定义一个候选 Visit。同一 `subject_id` 可以对应多个不同的 `hadm_id`。
- 关联：`hadm_id` 与同一行的 `admissions.subject_id` 共同确定该 Visit 的住院归属。各住院级源数据表中，只有 `hadm_id` 存在于 admissions 且 `subject_id` 与该 admission 一致的记录才能归入当前 Visit。
- 孤立记录：住院级源数据表中 `hadm_id` 为空或不在 admissions 中的记录直接忽略，不参与任何 Visit 的字段抽取。
- 冲突记录：住院级源数据表中的 `hadm_id` 存在于 admissions，但其 `subject_id` 与 `admissions.subject_id` 不一致时，视为全局数据完整性错误并终止抽取。
- 基础校验：admissions 中 `hadm_id` 为空或重复时，视为全局数据完整性错误并终止抽取，不自动补全、选择或合并。
- 输出：去除首尾空白后按字符串保留源值，不转换为整数、不哈希、不重新编码。
- 唯一性：正式输出中的 `hadm_id` 必须唯一，每个通过资格筛选的 Visit 恰好一行。
- 排序：候选 Visit 及通过资格筛选后的输出 Visit 均保留 admissions 源文件顺序。
- Visit 隔离：禁止仅根据 `subject_id` 将无明确 `hadm_id` 的记录归入某次住院，也禁止将其他 `hadm_id` 的记录补入当前 Visit。

### 5.3 `age_at_encounter`

来源字段：

- `patients.anchor_age`；
- `patients.anchor_year`；
- `admissions.admittime`。

计算公式：

```text
age_at_encounter = anchor_age + year(admittime) - anchor_year
```

- 结果必须为有效整数且大于或等于 18。
- `anchor_age`、`anchor_year` 或 `admittime` 无效时排除 Visit。
- 输出整数，不输出年龄段字段。

### 5.4 `sex`

- 来源：`dataset/hosp/patients.csv` 的 `gender`。
- 关联：使用当前 admission 的 `subject_id`，patient 记录必须唯一。
- 有效值：只允许 `M` 或 `F`。
- 输出：保留源值，不转换为 `male` 或 `female`。
- 缺失或无效：排除 Visit。

### 5.5 `chief_complaint`

- 语义：患者本次住院的主诉，是 DS 出院小结中记录的主要症状或就诊原因。
- 权威来源：`dataset/note/discharge.csv` 中当前 Visit 选定 DS 的 `text`，不使用 `discharge_detail.csv`。
- DS 候选条件：`note_type=DS`、`hadm_id` 等于当前 Visit、`subject_id` 与 `admissions.subject_id` 一致且 `text` 非空；`note_type=AD` 不纳入。
- 章节识别：`Chief Complaint` 必须是独立的顶层标题行；匹配时忽略大小写和首尾空白，允许标题末尾带英文冒号。
- 单份 DS 重复标题：按原文顺序选择第一个内容非空的 Chief Complaint 章节，不拼接同一 DS 中的多个同名章节。
- 多份 DS 选择：对每份候选 DS 独立提取主诉，只在包含明确、非空主诉的 DS 中，依次按 `note_seq`、`charttime`、`storetime`、`note_id` 降序选择最新记录；可空的 `storetime` 排在非空值之后。
- 内容处理：去除章节首尾空白后保留原文、内部顺序和换行，不做症状拆分、标准化或改写。
- 保存格式：`str`。每个 Visit 保存一个字符串，不使用 JSON、数组、列表或对象。多行主诉仍是一个字符串，内部换行以字符串内容保留。
- 缺失表示：该字段为必需字段，不允许写空单元格，也不使用 `nan`、`None`、`null` 或 `[]` 表示缺失。
- 禁止合并不同 DS 的主诉，也禁止从 HPI、诊断、治疗或其他章节推断或补全。
- 缺失：所有候选 DS 均无明确、非空的 Chief Complaint 时，排除整个 Visit。

### 5.6 `history_of_present_illness`

- 语义：患者本次住院相关症状、发病经过及入院前后早期临床过程。
- 权威来源：`dataset/note/discharge.csv` 中当前 Visit 按第 4.2 节选定 DS 的 `text`，不使用 `discharge_detail.csv`。
- 文档一致性：使用与 `chief_complaint` 相同的选定 DS，不重新从其他 DS、`note_type=AD` 的补充记录或同一患者其他住院记录中搜索和补写 HPI。
- 章节识别：`History of Present Illness` 必须是独立的顶层标题行；匹配时忽略大小写和首尾空白，允许标题末尾带英文冒号。不将 `HPI`、`Present Illness` 或标题与正文位于同一行的形式自动视为标准章节标题。
- 重复标题：同一份选定 DS 中出现多个 History of Present Illness 标题时，按原文顺序选择第一个内容非空的章节，不拼接多个同名章节。
- 章节边界：内容从标题后的下一行开始，到下一个已知顶层标题之前结束。
- 内容处理：去除章节首尾空白，保留内部原文、段落顺序、换行和 `___` 去标识化标记；不摘要、不改写，也不做实体标准化。
- 保存格式：`str`。每个 Visit 保存一个字符串，不使用 JSON、数组、列表或对象；多段或多行 HPI 仍然是一个字符串。
- 缺失表示：选定 DS 中缺少标准标题或章节内容为空时写空单元格，不使用 `nan`、`None`、`null` 或 `[]` 表示缺失，且不影响 Visit 纳入。
- 禁止补全：不从 Chief Complaint、Past Medical History、诊断编码、Brief Hospital Course 或其他章节推断、复制或补写 HPI。

### 5.7 `past_medical_history`

- 语义：患者在本次住院前已经存在的疾病、健康状况及相关既往临床信息。
- 权威来源：`dataset/note/discharge.csv` 中当前 Visit 按第 4.2 节选定 DS 的 `text`，不使用 `discharge_detail.csv`。
- 文档一致性：使用与 `chief_complaint` 和 `history_of_present_illness` 相同的选定 DS，不重新从其他 DS、`note_type=AD` 的补充记录或同一患者其他住院记录中搜索既往史。
- 章节识别：`Past Medical History` 必须是独立的顶层标题行；匹配时忽略大小写和首尾空白，允许标题末尾带英文冒号。不将 `PMH`、`Medical History` 或标题与正文位于同一行的形式自动视为标准章节标题。
- 重复标题：同一份选定 DS 中出现多个 Past Medical History 标题时，按原文顺序选择第一个内容非空的章节，不拼接多个非空的同名章节。连续重复标题中，内容为空的标题不作为结果。
- 章节边界：内容从标题后的下一行开始，到下一个已知顶层标题之前结束。`Past Surgical History` 未在 `docs/note/discharge.md` 中定义为标准顶层章节，也没有独立输出字段，因此其标题和后续内容保留在 `past_medical_history` 字符串中，直到遇到下一个已知顶层标题。
- 内容处理：去除章节首尾空白，保留内部原文、顺序、换行和 `___` 去标识化标记；不拆分疾病、不标准化疾病名称、不摘要也不改写。
- 有效原始状态：目标章节中明确记录的 `None`、`No past medical history`、`Unknown` 或 `Unable to obtain` 是有效 `str`，不视为字段缺失。
- 保存格式：`str`。每个 Visit 保存一个字符串，不使用 JSON、数组、列表或对象；多项疾病、多段文字或多行列表仍然是一个字符串。
- 缺失表示：选定 DS 中缺少标准标题或章节内容为空时写空单元格，不使用 `nan`、`None`、`null` 或 `[]` 表示缺失，且不影响 Visit 纳入。
- 禁止补全：只保留选定 DS 中 Past Medical History 章节的原始内容。标题缺失或章节内容为空时保持空单元格，不从 ICD 诊断编码、HPI、Chief Complaint、Brief Hospital Course、Discharge Diagnosis、其他 DS、AD 补充记录、同一患者其他住院记录或 LLM 推断中复制、推断或补写。

### 5.8 `medications_on_admission`

- 语义：DS 中记录的患者入院时或入院前正在使用的药物信息。
- 权威来源：`dataset/note/discharge.csv` 中当前 Visit 按第 4.2 节选定 DS 的 `text`，不使用 `discharge_detail.csv`。
- 文档一致性：使用与 `chief_complaint`、`history_of_present_illness` 和 `past_medical_history` 相同的选定 DS，不重新从其他 DS、`note_type=AD` 的补充记录或同一患者其他住院记录中搜索入院用药。
- 章节识别：`Medications on Admission` 必须是独立的顶层标题行；匹配时忽略大小写和首尾空白，允许标题末尾带英文冒号。不将 `Admission Medications`、`Home Medications` 或标题与正文位于同一行的形式自动视为标准章节标题。
- 重复标题：同一份选定 DS 中出现多个 Medications on Admission 标题时，按原文顺序选择第一个内容非空的章节，不拼接多个非空的同名章节。
- 章节边界：内容从标题后的下一行开始，到下一个已知顶层标题之前结束。遇到 `Discharge Medications` 等已知顶层标题时停止，不得将出院药物混入。
- 内容处理：去除章节首尾空白，保留药物名称、剂量、单位、途径、频次、PRN 信息、列表编号、段落顺序、内部换行和 `___` 去标识化标记；不拆分药物、不标准化药名、不进行同义词合并或去重，也不摘要、不改写。
- 有效原始状态：目标章节中明确记录的 `None`、`No medications`、`Unknown` 或 `Unable to obtain` 是有效 `str`，不视为字段缺失。
- 保存格式：`str`。每个 Visit 保存一个字符串，不使用 JSON、数组、列表或对象；编号药物列表、多段文字或多行内容仍然是一个字符串。
- 缺失表示：选定 DS 中缺少标准标题或章节内容为空时写空单元格，不使用 `nan`、`None`、`null` 或 `[]` 表示缺失，且不影响 Visit 纳入。
- 禁止补全：只保留选定 DS 中 Medications on Admission 章节的原始内容。标题缺失或章节内容为空时保持空单元格，不从 `prescriptions`、`pharmacy`、`emar`、Discharge Medications、HPI、诊断、治疗记录、其他 DS、AD 补充记录、同一患者其他住院记录或 LLM 推断中复制、推断或补写。

### 5.9 `investigation_orders`

- 语义：当前 Visit 中医生下达的检查和检验医嘱。
- 来源：医嘱主体来自 `dataset/hosp/poe.csv`，医嘱明细来自 `dataset/hosp/poe_detail.csv`。
- 关联：只使用 `hadm_id` 等于当前 Visit、`subject_id` 与 `admissions.subject_id` 一致的记录；`poe_detail` 通过 `poe_id + poe_seq` 连接 POE。
- 纳入条件：比较前去除首尾空白，只保留 `transaction_type=New`，且 `order_type` 精确等于 `Lab` 或 `Imaging` 的医嘱。
- 排除范围：不纳入 `Medications`、`Blood Bank`、`Respiratory`、`Procedures`、`Consults`、`Nutrition`、`ADT` 或其他非 `Lab`/`Imaging` 医嘱，也不根据 `order_subtype` 或 `poe_detail` 将其他类型推断为检查。
- 保存格式：JSON 对象数组。每个对象保存原始 `order_type`、`order_subtype`，以及由原始 `field_name` 和 `field_value` 组成的 `poe_detail` 数组。
- 明细排序：每条医嘱的 `poe_detail` 按 `field_name` 稳定排序；`field_name` 相同时保留源文件行序。没有明细记录时保存空数组 `[]`。
- 相同检查：使用 `order_type + order_subtype + 排序后的 poe_detail 内容` 识别相同医嘱。同一 Visit 中相同医嘱只保留 `ordertime` 最早的一条；时间相同时按 `poe_id`、`poe_seq` 和 POE 源文件行序稳定选择。
- 数组排序：最终医嘱数组按 `ordertime`、`poe_id`、`poe_seq` 和 POE 源文件行序稳定排序；时间和 ID 只用于选择与排序，不写入正式对象。
- 原始值：保留源字段内容，不在抽取阶段生成或标准化检查名称。
- 缺失表示：没有符合条件的检查医嘱时保存 `[]`，不影响 Visit 纳入。
- 禁止补全：不根据检查结果、报告、诊断或其他 Visit 反向生成医嘱。

### 5.10 `investigation_reports`

- 语义：当前 Visit 已获得的实验室和放射学检查结果。
- 来源：实验室结果来自 `dataset/hosp/labevents.csv` 和 `dataset/hosp/d_labitems.csv`；放射学报告来自 `dataset/note/radiology.csv` 和 `dataset/note/radiology_detail.csv`。
- 关联：只使用 `hadm_id` 等于当前 Visit、`subject_id` 与 `admissions.subject_id` 一致的记录。
- 保存格式：JSON 对象，固定包含 `laboratory` 和 `radiology` 两个数组。

#### 实验室结果

- 项目定义：通过 `labevents.itemid` 连接 `d_labitems`，保存 `itemid`、`label`、`fluid` 和 `category`。
- 结果内容：保存 `value`、`valuenum`、`valueuom`、`ref_range_lower`、`ref_range_upper`、`flag` 和 `comments`。
- 相同项目：同一 Visit 中相同 `itemid` 只保留时间最早的有效结果。
- 首次结果：优先按 `charttime` 判断，时间相同时使用 `storetime` 和 `labevent_id` 稳定选择。
- 有效结果：`value`、`valuenum` 或 `comments` 至少一个有内容。
- 参考范围：参考范围和异常标志必须来自被选中的同一条 `labevents` 记录。

#### 放射学报告

- 项目定义：通过 `radiology.note_id` 连接 `radiology_detail`，使用 `field_name=exam_name` 对应的 `field_value` 识别检查项目。
- 报告内容：保存 `radiology.text` 完整原文。
- 详细属性：`radiology_detail` 保留原始 `field_name`、`field_value` 和 `field_ordinal`，不将 `field_name` 的取值转换为新的 JSON 字段。
- 正式报告：只使用 `note_type=RR` 的放射学正式报告。
- 相同项目：同一 Visit 中相同 `exam_name` 只保留时间最早的正式报告。
- 首次报告：按 `charttime` 判断，时间相同时使用 `storetime`、`note_seq` 和 `note_id` 稳定选择。
- 补充报告：`note_type=AR` 不作为新的首次检查项目。

#### 通用规则

- 原始值：保留源字段内容，不在抽取阶段生成、标准化或改写检查名称和结果。
- 属性缺失：实验室和放射学对象的固定属性必须完整；源字段缺失、CSV 为空或字符串去除首尾空白后为空时保存 JSON `null`。有效字符串保存为 JSON 字符串，有效数值保存为 JSON 数值。
- 时间字段：用于首次结果选择，不写入正式输出对象。
- 缺失表示：没有任何结果时保存 `{"laboratory":[],"radiology":[]}`，不影响 Visit 纳入。
- 禁止补全：不根据医嘱、诊断、其他 Visit、外部参考范围或 LLM 推断、生成或补写检查结果。

### 5.11 `primary_icd_code`

- 语义：当前 Visit 的主要 ICD 诊断编码；本规范以 `diagnoses_icd.seq_num=1` 定义主要诊断。该顺序来自出院后的诊断编码，不表示诊断发生时间或临床严重程度。
- 来源：`dataset/hosp/diagnoses_icd.csv`。
- 关联：只使用 `hadm_id` 等于当前 Visit、`subject_id` 与 `admissions.subject_id` 一致的记录。
- 选择：当前 Visit 必须恰好存在一条有效的 `seq_num=1` 记录。
- 有效条件：`icd_code` 去除首尾空白后非空，`icd_version` 为 9 或 10，并能通过 `icd_code + icd_version` 精确连接 `dataset/hosp/d_icd_diagnoses.csv`。
- 保存格式：一个 `str`，保存去除首尾空白后的源 `icd_code`。保留 MIMIC 中不含小数点的格式，不添加小数点、不改变前导零，也不转换 ICD 版本。
- 排除条件：缺少有效的 `seq_num=1` 记录、存在多条 `seq_num=1` 记录、ICD 版本无效或无法连接诊断字典时，排除整个 Visit。
- 禁止补全：禁止根据 Chief Complaint、HPI、出院诊断文字、其他诊断或其他 Visit 推断、生成或修改主诊断代码。

### 5.12 `primary_diagnosis_name`

- 语义：当前 Visit 的主要诊断名称，与 `primary_icd_code` 和 `primary_icd_version` 表示同一项主诊断。
- 来源：`dataset/hosp/d_icd_diagnoses.csv` 的 `long_title`。
- 关联：使用已选定的 `diagnoses_icd.seq_num=1` 记录中的 `icd_code + icd_version`，精确连接 `d_icd_diagnoses` 的同名复合键。
- 有效条件：必须恰好连接到一条字典记录，且 `long_title` 去除首尾空白后非空。
- 保存格式：一个 `str`，保存去除首尾空白后的源 `long_title`。
- 原始值：保留字典中的英文名称，不翻译、不缩写、不改写，也不替换为自定义诊断名称。
- 去重和排序：不适用；每个 Visit 只有一个主诊断名称。
- 排除条件：无法连接字典、连接结果不唯一或 `long_title` 为空时，排除整个 Visit。
- 禁止补全：禁止根据 Chief Complaint、HPI、出院诊断文字、其他诊断、代码含义或 LLM 推断、生成或补写主诊断名称。

### 5.13 `primary_icd_version`

- 语义：`primary_icd_code` 所属的 ICD 诊断编码体系和版本。
- 来源：与 `primary_icd_code` 相同的、已选定的 `diagnoses_icd.seq_num=1` 记录中的 `icd_version`。
- 一致性：`primary_icd_code`、`primary_diagnosis_name` 和 `primary_icd_version` 必须由同一条主诊断记录及其字典连接共同确定。
- 有效条件：源 `icd_version` 只能为整数 9 或 10。
- 保存格式：一个 `str`，按以下固定规则映射：

```text
源 icd_version = 9  -> ICD-9-CM
源 icd_version = 10 -> ICD-10-CM
```

- 去重和排序：不适用；每个 Visit 只有一个主诊断版本。
- 排除条件：源版本缺失、无法解析或不是 9/10 时，排除整个 Visit。
- 禁止转换：不将 ICD-9-CM 转换为 ICD-10-CM，也不使用 SNOMED CT、CCS 或其他分类体系覆盖源版本。
- 禁止补全：禁止根据 ICD 代码形式、住院日期、诊断名称或其他 Visit 推断版本；版本必须直接来自所选主诊断记录。

### 5.14 `other_diagnoses`

- 语义：当前 Visit 中主诊断之外的其他有效 ICD 诊断名称。诊断编码代表整个住院期间，`seq_num` 只表示出院后的编码顺序，不表示诊断发生时间。
- 来源：`dataset/hosp/diagnoses_icd.csv` 和 `dataset/hosp/d_icd_diagnoses.csv`。
- 关联：只使用 `hadm_id` 等于当前 Visit、`subject_id` 与 `admissions.subject_id` 一致的记录；通过 `icd_code + icd_version` 精确连接诊断字典。
- 过滤条件：`seq_num>1`，`icd_code` 去除首尾空白后非空，`icd_version` 为 9 或 10，并能连接到 `long_title` 非空的字典记录。
- 保存格式：JSON 字符串数组。每个元素保存去除首尾空白后的英文 `long_title`，不保存 `icd_code`、`icd_version` 或 `seq_num`。
- 排序：按 `seq_num` 从小到大排列；`seq_num` 相同时，再按 `icd_version` 和 `icd_code` 稳定排序。
- 名称比较：仅去除首尾空白、合并连续空白并忽略英文字母大小写；名称相同的诊断只保留排序最前的一项，输出该项的源 `long_title`。
- 排除主诊断重复项：按照相同的名称比较规则，移除与 `primary_diagnosis_name` 相同的项目。
- 禁止语义合并：不使用字符串相似度、同义词词典或 LLM 合并名称不同的诊断。
- 缺失表示：没有符合条件的其他诊断时保存 `[]`，不影响 Visit 纳入。
- 禁止补全：禁止根据 DS、Chief Complaint、HPI、药物、检查结果或其他 Visit 生成其他诊断。

### 5.15 `medication_prescriptions`

- 语义：当前 Visit 中每种主要药物最早的一条结构化处方信息。该字段表示处方，不表示药物已经实际给药。
- 来源：`dataset/hosp/prescriptions.csv`。
- 关联：只使用 `hadm_id` 等于当前 Visit、`subject_id` 与 `admissions.subject_id` 一致的记录。
- 过滤条件：只纳入 `drug_type=MAIN` 且 `drug` 去除首尾空白后非空的记录；不纳入 `BASE` 和 `ADDITIVE`。
- 保存格式：JSON 对象数组。每个对象固定包含 `drug`、`prod_strength`、`form_rx`、`dose_val_rx`、`dose_unit_rx`、`route` 和 `doses_per_24_hrs`。
- 原始值：各属性保存所选 `prescriptions` 记录中的源值。字符串去除首尾空白，不转换剂量、不标准化单位、不改写给药途径。
- 药物识别：比较 `drug` 时仅去除首尾空白、合并连续空白并忽略英文字母大小写。
- 首次处方：同一种药物只保留 `starttime` 最早的记录。缺少 `starttime` 的记录排在有时间的记录之后；时间相同或均缺失时，使用 `pharmacy_id`、`poe_id`、`poe_seq` 和源文件行序稳定选择。
- 用量调整：后续同名药物的规格、剂型、剂量、剂量单位、给药途径或每日次数即使发生变化，也不再输出。
- 禁止补全：首次处方的某个属性缺失时保存 JSON `null`，禁止使用该药物的后续处方补全。
- 数组排序：按照各药物首次处方的 `starttime` 排列；缺少时间的药物排在有时间的药物之后，并使用上述稳定选择字段确定顺序。
- 禁止语义合并：不使用 GSN、NDC、字符串相似度、同义词词典或 LLM 合并名称不同的药物。
- 禁止替代：不使用 POE、`pharmacy`、`emar`、DS 中的入院或出院药物以及其他 Visit 替代或补写处方信息。
- 缺失表示：没有符合条件的主要药物处方时保存 `[]`，不影响 Visit 纳入。

### 5.16 `procedures`

- 语义：当前 Visit 中有效、可映射的 ICD 手术和医疗操作集合，包括外科手术、机械通气、导管置入、内镜、透析、引流及其他 ICD 编码操作。这些代码由编码人员在住院结束后分配，不表示实时操作医嘱或 ICU 操作事件。
- 来源：`dataset/hosp/procedures_icd.csv` 和 `dataset/hosp/d_icd_procedures.csv`。
- 关联：只使用 `hadm_id` 等于当前 Visit、`subject_id` 与 `admissions.subject_id` 一致的记录；通过 `icd_code + icd_version` 精确连接操作字典。
- 过滤条件：`icd_code` 去除首尾空白后非空，`icd_version` 为 9 或 10，能精确连接到一条字典记录，且 `d_icd_procedures.long_title` 去除首尾空白后非空。
- 保存格式：JSON 对象数组。每个对象固定包含 `procedure_name`、`icd_code` 和 `icd_version`；完整结构示例见第 3.5 节。
- `procedure_name`：保存去除首尾空白后的英文 `d_icd_procedures.long_title`，不翻译或改写。
- `icd_code`：保存去除首尾空白后的源代码字符串，保留 MIMIC 中不含小数点的格式，不添加小数点、不丢失前导零。
- `icd_version`：源值为 9 时保存 `ICD-9-PCS`，源值为 10 时保存 `ICD-10-PCS`；不进行版本转换。
- 同一种操作：使用 `icd_code + icd_version` 识别。相同代码和版本重复出现时，只保留 `chartdate` 最早的一条；日期相同时按 `seq_num` 稳定选择。
- 数组排序：按 `chartdate`、`seq_num`、`icd_version` 和 `icd_code` 稳定排序。
- 日期和序号：`chartdate` 和 `seq_num` 只用于选择和排序，不写入正式输出对象；`seq_num` 不表示执行时间、主要操作或临床重要性。
- 不同代码同名：代码或版本不同的操作分别保留，不按 `procedure_name` 去重。
- 缺失表示：没有符合条件的操作时保存 `[]`，不影响 Visit 纳入。
- 禁止补全：禁止从 DS、POE、HCPCS、ICU `procedureevents`、其他 Visit 或 LLM 推断、生成或补写 ICD 操作。

### 5.17 `discharge_record`

- 语义：当前 Visit 的出院后随访指导文本；不表示完整出院小结。
- 来源：第 4.2 节选定的唯一 DS 的 `text`，只解析其中的 `Follow-up Instructions` 章节。
- 文档关联：只使用当前 `hadm_id`、`subject_id` 一致且 `note_type=DS` 的出院小结；`AD` 补充记录不作为来源。该字段与其他 DS 文本字段使用同一份选定 DS，不切换或合并其他文档。
- 标题识别：大小写不敏感，允许标题末尾带英文冒号，并兼容 `Follow-up Instructions`、`Followup Instructions` 和 `Follow Up Instructions`。
- 章节边界：从目标标题之后开始，到下一个已知顶层章节标题之前结束。
- 保存格式：一个 `str`，保存章节正文，不保存 JSON、数组或对象。
- 文本处理：去除章节首尾空白，保留内部换行、原始顺序和去标识化痕迹，例如 `___`。
- 缺失表示：标题缺失、章节为空或清理后只剩 `___` 时写空 CSV 单元格，不影响 Visit 纳入。
- 禁止保存：不保存完整 `discharge.text`，也不使用 `discharge_detail` 中的作者信息。
- 禁止替代章节：不从 `Discharge Instructions`、`Discharge Medications`、`Brief Hospital Course`、`Discharge Diagnosis`、`Discharge Condition` 或其他章节替代或补写。
- 禁止补全：不根据诊断、药物、操作、其他 Visit、外部知识或 LLM 生成或补写随访指导。
