# Admission 原始归档

## 当前定位

这是当前推荐清洗主流程的第一步。它从本地 MIMIC 原始 CSV.GZ 表抽取并聚合 admission 记录，输出一行一次住院的原始 JSONL。它保留源表字段和值，不做编码释义替换，也不解析 POE 语义。

```text
MIMIC 原始表 → mimic_raw_archive → Admission 原始 JSONL
```

## 输入与输出

输入根目录通过 `--data-root` 指定，代码按锁定目录和表头读取：

- MIMIC-IV 3.1 HOSP；
- MIMIC-IV 3.1 ICU；
- MIMIC-IV-ED 2.2；
- MIMIC-IV-NOTE 2.2。

每条输出记录的 schema 为：

```json
{"name": "mimic_admission_raw", "version": "1.0.0"}
```

顶层固定包含 `subject_id`、`hadm_id`、`mimic_iv_hosp`、`mimic_iv_icu`、`mimic_iv_ed` 和 `mimic_iv_note`。当前归档包含 32 张住院内可可靠连接的源表；`chartevents` 因体积和连续监测属性明确排除，`omr` 因没有可验证的住院原生连接键明确排除。

输出采用分片和 manifest，可中断后继续；最终合并为一个 JSONL。

## 基本用法

在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.mimic_raw_archive `
  --data-root data\RawData `
  --output-dir data\raw_archive\shards `
  --merged-output data\mimic-admission-raw.jsonl `
  --sample-size 100 `
  --shard-size 100 `
  --workers 2 `
  --duckdb-threads 4 `
  --duckdb-memory-limit 12GB
```

主要参数：

- `--sample-size`：随机抽取的 admission 数；不传时默认 10,000。
- `--selection-input`：按已有选择清单抽取；传入后可不写 `--sample-size`。
- `--shard-size`：每个输出分片的记录数。
- `--workers`：并行分片工作进程数。
- `--duckdb-threads`：单个 DuckDB 工作进程线程数。
- `--duckdb-memory-limit`：例如 `4GB`、`12GB`，格式不合法会立即失败。

输出路径不得与原始数据目录重叠。已有完整输出不会被静默覆盖。

## 冠心病选择清单

如需先生成冠心病谱系 admission 清单：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.mimic_raw_archive.cohort `
  --data-root data\RawData `
  --output data\coronary-admission-selection.jsonl `
  --development-percent 20
```

再将其传给主入口的 `--selection-input`。

## 运行监控

只读监控页面不会修改归档：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.mimic_raw_archive.monitor `
  --output-dir data\raw_archive\shards `
  --merged-output data\mimic-admission-raw.jsonl `
  --host 127.0.0.1 `
  --port 8765
```

## 下游

生成的 JSONL 直接交给 `data_pipeline.clean_clinical_archive`。不要先经过 `mimic_episode` 或 `parquet_to_jsonl`。

## 代码文件

- `extractor.py`：分片抽取、恢复、合并和运行报告。
- `catalog.py`：纳入表、模块和原生连接规则。
- `schema.py`：冻结的 admission 原始 JSONL schema 与逐条校验。
- `config.py`：路径、并发、分片及 DuckDB 资源配置。
- `selection.py`：样本和选择清单处理。
- `cohort.py`：冠心病谱系 admission 清单。
- `manifest.py`：分片状态、哈希和续跑依据。
- `monitor.py`：本地只读运行监控。
- `module_subset.py`：从既有 JSONL 筛选满足模块条件的记录。
- `field_dictionary.py`：从锁定表头生成字段说明材料。

## 依赖与限制

- 运行依赖 Python 3.12、DuckDB 和项目中锁定的 MIMIC 表头定义。
- `catalog.py`、`cohort.py`、`extractor.py` 和 `field_dictionary.py` 统一读取 `data_pipeline.mimic_source_catalog`。
- 共享源表契约位于活动 `data_pipeline` 根目录，主流程不依赖 `archived/` 中的 Episode 代码。

## 验证

```powershell
.\.venv\Scripts\python.exe -m unittest -v `
  tests.test_raw_admission_archive `
  tests.test_raw_archive_monitor `
  tests.test_module_subset
```
