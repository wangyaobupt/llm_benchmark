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

## 查询

```sql
SELECT code, label, category, attributes_json
FROM code_lookup
WHERE dictionary_name = 'd_labitems'
  AND code = '50878';
```

原始字段没有塞入统一列的部分保存在 `attributes_json`。例如 `d_labitems.fluid`、`d_items.unitname` 和正常范围仍可完整读取。

## 验收约束

- 每张字典的源行数必须与独立 Parquet 行数一致；
- 字典主键不得为空或重复；
- 五张字典的行数总和必须等于统一查询表行数；
- 输出总大小默认不得超过 50 MiB；
- `manifest.json` 必须记录来源、版本、字段、行数、大小和 SHA-256。
