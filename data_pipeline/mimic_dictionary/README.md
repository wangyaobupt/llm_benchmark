# MIMIC 官方字典构建器

## 当前定位

这是辅助工具，不是每次 JSONL 清洗都必须执行的步骤。它从授权 MIMIC-IV 3.1 源文件生成可审计、可查询的五类编码字典：

- `d_labitems`；
- `d_items`；
- `d_icd_diagnoses`；
- `d_icd_procedures`；
- `d_hcpcs`。

清洗器已经在 `clean_clinical_archive/dictionaries/` 读取这五份字典。只有首次生成、MIMIC 版本变化或字典文件需要重建时才运行本模块。

## 输入

`--data-root` 应指向授权 MIMIC 原始数据根目录。构建器读取：

```text
mimic-iv-3.1/hosp/d_labitems.csv.gz
mimic-iv-3.1/icu/d_items.csv.gz
mimic-iv-3.1/hosp/d_icd_diagnoses.csv.gz
mimic-iv-3.1/hosp/d_icd_procedures.csv.gz
mimic-iv-3.1/hosp/d_hcpcs.csv.gz
```

## 构建字典

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.mimic_dictionary `
  --data-root data\RawData `
  --output-dir data\解析 `
  --max-file-bytes 52428800
```

为防止混合新旧结果，`--output-dir` 已存在时会失败，不会覆盖。输出目录包括：

- `mimic_dictionaries.duckdb`：五张字典表和统一 `code_lookup` 表；
- `mimic_code_lookup.parquet`：统一查询表；
- `csv/`：字典 CSV 和统一 lookup CSV；
- `json/*.json`：清洗器使用的五张原始字典 JSON 数组；
- `json/code_lookup/`：按字典拆分的统一查询结构；
- `manifest.json`：来源、版本、行数、体积和 SHA-256；
- `README.md`：构建器随输出自动生成的使用说明。

## 与主清洗器的关系

主清洗器默认读取：

```text
data_pipeline/clean_clinical_archive/dictionaries/
```

其中必须恰好提供五个标准 JSON 数组。授权字典受 `.gitignore` 保护，不进入 Git。更新便携包字典时，还必须同步更新 `bundle-manifest.json` 的行数、文件大小和 SHA-256，并执行便携包校验；不能只替换 JSON 后跳过完整性检查。

## 仅做字典解码

如果只需要给已有 admission JSON/JSONL 增加编码释义，而不解析 POE，可使用：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.mimic_dictionary.decode_archive `
  --input data\mimic-admission-raw.jsonl `
  --output data\mimic-admission-decoded.jsonl `
  --dictionary-db data\解析\mimic_dictionaries.duckdb
```

当前推荐的完整主流程仍是 `data_pipeline.clean_clinical_archive`，因为它在同一次遍历中完成字典解码和 POE 解析。两个入口调用同一个 `clean_clinical_archive.decoder` 解码内核，不维护第二套解码规则。

## 代码文件

- `builder.py`：验证源表、构建五张字典、统一 lookup、manifest 和多种导出格式。
- `decode_archive.py`：只做字典解码的兼容入口。
- `__main__.py`：字典构建命令行入口。

## 依赖与验证

构建和 DuckDB 解码入口依赖 Python 3.12 与 DuckDB。

```powershell
.\.venv\Scripts\python.exe -m unittest -v `
  tests.test_mimic_dictionary `
  tests.test_decode_archive
```
