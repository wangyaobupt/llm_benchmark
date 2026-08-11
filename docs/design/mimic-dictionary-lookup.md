# MIMIC-IV 编码解析字典

## 目标

将本机授权的 MIMIC-IV 3.1 独立语义字典转换成适合后续 Python、DuckDB 和批处理流程读取的格式，同时完整保留官方字段、编码和原始拼写。

输出固定在 `data/解析/`。该目录受 `.gitignore` 保护，不进入 Git，也不得公开分发。

## 范围

纳入：

- `hosp/d_labitems`：实验室项目；
- `icu/d_items`：ICU项目；
- `hosp/d_icd_diagnoses`：ICD诊断；
- `hosp/d_icd_procedures`：ICD操作；
- `hosp/d_hcpcs`：HCPCS项目。

明确排除 MIMIC-III 1.4。`provider` 和 `caregiver` 只是去标识化人员ID登记表，不具有“编码到临床含义”的解析功能，也不纳入。

## 构建

```powershell
.\.venv\Scripts\python.exe -m mimic_dictionary
```

构建器要求目标目录不存在，避免静默覆盖已有解析结果。需要重建时，应先明确删除旧目录，再重新运行。

## 输出

```text
data/解析/
├── csv/
│   ├── code_lookup.csv
│   ├── d_hcpcs.csv
│   ├── d_icd_diagnoses.csv
│   ├── d_icd_procedures.csv
│   ├── d_items.csv
│   └── d_labitems.csv
├── json/
│   ├── code_lookup/
│   │   ├── d_hcpcs.json
│   │   ├── d_icd_diagnoses.json
│   │   ├── d_icd_procedures.json
│   │   ├── d_items.json
│   │   └── d_labitems.json
│   ├── d_hcpcs.json
│   ├── d_icd_diagnoses.json
│   ├── d_icd_procedures.json
│   ├── d_items.json
│   └── d_labitems.json
├── tables/
│   ├── d_hcpcs.parquet
│   ├── d_icd_diagnoses.parquet
│   ├── d_icd_procedures.parquet
│   ├── d_items.parquet
│   └── d_labitems.parquet
├── mimic_code_lookup.parquet
├── mimic_dictionaries.duckdb
├── manifest.json
└── README.md
```

五张独立 Parquet 保留官方原表结构。统一 `code_lookup` 提供以下固定字段：

```text
source_database, source_version, source_module, dictionary_name,
code_system, code, code_version, label, description, category,
source_path, attributes_json
```

ICD编码必须同时使用 `code` 与 `code_version`，不能只按编码字符串连接。

CSV 使用 UTF-8 BOM，并对字段进行标准 CSV 引号转义，可直接由 Excel、WPS、文本编辑器和数据程序读取。CSV 本身没有强制列类型的元数据；若 Excel 自动转换带前导零的 ICD 编码，应使用“从文本/CSV导入”并把编码列指定为文本。JSON 中编码始终保存为字符串，是保留编码原值的权威文本格式。

统一 CSV 为单文件 `csv/code_lookup.csv`。统一 JSON 若写成一个标准数组会超过50 MiB，因此按字典拆分到 `json/code_lookup/`；五个分片使用完全相同的字段，可以直接逐个读取或合并。`json/*.json` 则保留各官方字典的全部原始字段。

## 查询

```sql
SELECT code, label, category, attributes_json
FROM code_lookup
WHERE dictionary_name = 'd_labitems'
  AND code = '50878';
```

原始字段没有塞入统一列的部分保存在 `attributes_json`。例如 `d_labitems.fluid`、`d_items.unitname` 和正常范围仍可完整读取。

## 下游解码与 POE 清洗

字典构建完成后，统一从 `data_cleaning.clean_clinical_archive` 一次完成编码解码和 POE 医嘱解析。完整命令、字段映射、组合键规则、失败条件及输出契约集中维护在 [临床可读归档清洗器](../../data_cleaning/clean_clinical_archive/README.md) 和其 [字典解码规则](../../data_cleaning/clean_clinical_archive/docs/decoding-rules.md)，本构建文档不再复制运行规则。

旧入口 `mimic_dictionary.decode_archive` 仍可用于只增加字典释义的兼容场景，但它与统一入口调用同一个共享解码内核，不维护第二套规则。

## 验收约束

- 每张字典的源行数必须与独立 Parquet 行数一致；
- 字典主键不得为空或重复；
- 五张字典的行数总和必须等于统一查询表行数；
- 任一输出文件默认不得超过 50 MiB；
- `manifest.json` 必须记录来源、版本、字段、行数、大小和 SHA-256。
