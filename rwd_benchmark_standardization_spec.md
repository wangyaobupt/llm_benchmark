# RWD Benchmark 医疗名称规范化规范

## 1. 输入与输出

输入固定为清洗阶段的 17 列 CSV。正式标准化输出保持一行一个 Visit、输入行顺序和 `subject_id/hadm_id`，使用以下 15 列：

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
primary_diagnosis
other_diagnoses
medication_prescriptions
procedures
discharge_record
```

所有 JSON 使用紧凑 UTF-8 表示，不写入 `NaN`、`Infinity` 或字符串形式的空值。

## 2. 通用名称规则

- 去除首尾空白并合并连续空白。
- 确定性别名优先于 LLM 映射；无法可靠归并时保留规范化自身表达。
- 保留部位、侧别、严重程度、急慢性和不确定性，不补充源实体没有表达的信息。
- 字符串数组按标准名称忽略大小写去重，保留第一次出现顺序；不跨字段去重。
- `chief_complaint`、`history_of_present_illness`、`past_medical_history`、`medications_on_admission`、`other_diagnoses` 和 `procedures` 均保存 JSON 字符串数组，只有 `primary_diagnosis` 保存标量字符串。

## 3. 字段规则

### 3.1 人口学与正文

- `subject_id`、`hadm_id`、`age_at_encounter`、`sex` 逐值复制；年龄必须为整数，sex 必须为 `M/F`。
- `discharge_record` 逐值复制，不摘要、不改写。
- 放射学正文和检验 comments 逐值复制。

### 3.2 临床实体与入院药物

- 三个临床实体字段使用 field-specific 映射，不跨字段复用歧义缩写。
- 入院药物优先映射到活性成分；复方映射可返回多个成分并保持映射表顺序。
- 商品名没有可靠成分映射时保留规范化商品名。

### 3.3 诊断与操作

- 主诊断映射键包含源名称、ICD code 和 ICD version，正式结果只保存名称。
- 其他诊断缺少源 code/version 时只按名称和字段上下文映射。
- 操作映射键包含源名称、ICD code 和 ICD version，正式结果只保存名称。
- 不建立跨 ICD 版本 crosswalk，不生成上位概念，不改变粒度。

### 3.4 检查医嘱

`investigation_orders` 不进行医学名称或结构标准化，整字段从清洗文件原样复制到正式标准化文件。

- 不汇总检查医嘱中的唯一表达，不为其生成映射记录。
- 不调用 LLM 处理 `order_type`、`order_subtype`、`poe_detail.field_name` 或 `poe_detail.field_value`。
- 不修改检查医嘱的属性名称、属性值、JSON 层级、数组顺序或缺失表示。
- 不根据通用医嘱推断具体检查，也不从其他字段补充检查信息。
- 正式文件中的 `investigation_orders` 必须与对应清洗记录逐字节一致。

### 3.5 实验室结果

每条结果固定包含：

```json
{
  "test_name":"Creatinine, blood",
  "result":{"type":"numeric","value":1.2,"text":null,"unit":"mg/dL"},
  "reference_range":{"lower":0.4,"upper":1.1},
  "interpretation":"abnormal",
  "comments":null
}
```

- 检验映射键包含 itemid、label、fluid、category；标准名称优先采用 `label, fluid`。
- 有有限数值 `valuenum` 时使用 `numeric`；否则使用 `text` 并保存清理后的 `value`。
- 单位只统一确定性等价写法，不缩放 result 或参考范围，不合并 FEU/DDU。
- interpretation 使用小写稳定名称；缺失保持 JSON null。

### 3.6 放射学结果

每条报告固定包含：

```json
{"examinations":["Chest radiography"],"report_text":"..."}
```

按 `field_ordinal` 提取并标准化 exam_name，同一报告内按名称去重。exam_code 不进入正式数据。

### 3.7 处方

每条处方固定包含：

```json
{
  "ingredients":["Ceftriaxone"],
  "product_strength":"1 g",
  "dose_form":"Frozen bag",
  "dose":{"type":"single","value":1,"minimum":null,"maximum":null,"text":null,"unit":"g"},
  "route":"intravenous",
  "doses_per_24_hours":1
}
```

- 单值剂量使用 `single`；`a-b` 或 `a to b` 使用 `range`；其他非空文本使用 `text`；缺失使用 `missing`。
- 无法解析的文本必须写入 `dose.text`，不得丢弃。
- product strength 和 dose form 进行空白、大小写和明确单位格式规范后保留。
- 复方成分保持在同一处方对象内。
- 仅删除完整标准化对象逐值相同的重复处方。

## 4. 映射文件

映射候选生成和独立等价复核统一使用以下 LLM：

```text
Provider: DeepSeek
Model: deepseek-v4-flash
Base URL: https://api.deepseek.com
```

两个阶段使用同一模型但采用相互独立的请求和 Prompt。模型名称、Prompt 配置摘要和规则版本必须写入 manifest。更换模型或影响映射结果的模型配置时，必须重新构建映射表并升级相应版本，不得静默覆盖已发布映射。

每条 JSONL 映射固定包含：

```json
{
  "domain":"clinical_entity",
  "source_field":"chief_complaint",
  "source":"SOB",
  "structured_context":{},
  "normalized_source":"sob",
  "standard":["Shortness of breath"],
  "method":"deterministic_alias",
  "frequency":10,
  "version":"1.0"
}
```

映射表按稳定映射键排序。review 文件保存所有 `normalized_identity` 记录并增加 `reason`。正式转换遇到映射表缺项必须终止，不允许运行时调用 LLM 或静默创建新映射。

## 5. 验收

- 输入必须严格匹配清洗 17 列 Schema；输出必须严格匹配标准化 15 列 Schema。
- 输入和输出 Visit 数量、顺序、ID、年龄、sex 以及规定原样保留的正文必须一致。
- `investigation_orders` 必须与清洗输入逐值一致，不得产生该字段的映射记录或 LLM 请求。
- 每个正式 JSON 对象必须具有本规范规定的完整属性集合。
- 映射后的空标准名称、非法数字和非有限 JSON 数值均视为错误。
- 生成采用临时文件；全部校验通过后才原子替换目标文件。

## 6. 运行方式

正式映射构建必须显式启用双阶段 LLM：

```bash
./run_standardize_rwd_benchmark.sh --mode build-mappings
./run_standardize_rwd_benchmark.sh --mode transform
```

也可用单条命令完成两阶段：

```bash
./run_standardize_rwd_benchmark.sh
```

`run_standardize_rwd_benchmark.sh` 与清洗启动脚本采用相同结构：设置 `DEEPSEEK_API_KEY` 后直接执行 `standardize_rwd_benchmark.py --use-llm`。运行脚本的 Python 环境需已安装 `openai`。直接调用 `standardize_rwd_benchmark.py` 时仍需显式传入 `--use-llm` 或 `--offline`。

`--offline` 只用于验证结构、确定性和失败恢复，其输出不得作为正式 v1 发布。`transform` 要求映射构建阶段的 manifest 存在，并核对其中的输入和冻结映射表 SHA-256；manifest 缺失或摘要不一致时终止且不替换现有正式数据。
