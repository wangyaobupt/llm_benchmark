# Episode Parquet 到 Visit JSONL

## 当前定位

这是可选 Episode/visit 路线的第二步，不是 admission 原始归档生成器。虽然目录名是 `parquet_to_jsonl`，它不能接收任意 MIMIC Parquet；它读取 `mimic_episode` 生成的固定 Episode Parquet 数据集，并结合部分原始表组装 visit 级评测归档。

```text
mimic_episode 输出的 Episode Parquet
    ↓ parquet_to_jsonl
mimic_visit_archive/1.0.0 JSONL + 决策快照
```

当前 admission 临床可读主流程不运行本模块。

## 输入

默认配置位于 `config.py`：

- Episode Parquet 目录：`G:/Projects/医疗数据集评测-MIMIC/outputs/episodes`；
- `patients.csv.gz`：用于年龄和性别；
- MIMIC 原始数据根目录：用于 OMR、ED stay、ICU stay 和 radiology detail 等补充数据。

适配器依赖固定的 Episode 表结构，例如 `episode_index.parquet`、`timeline_events.parquet`、`event_items.parquet` 和 `documents.parquet`。

## 输出

每行输出一个经过校验的 visit archive，其 `metadata` 中的 schema 标识为：

```json
{"schema_name": "mimic_visit_archive", "schema_version": "1.0.0"}
```

记录包括 encounter 标识、人口学信息、主诉、生命体征、医嘱、检查检验、诊断、治疗、转科、出院信息、纵向引用、患者级数据分区，以及五个时间点的 `decision_snapshots`。

决策快照只允许使用 `available_time <= index_time` 的信息，并排除 `post_hoc` 和 `administrative_end` 证据。

## 运行

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.archived.parquet_to_jsonl.adapter `
  --limit 100 `
  --output data\visit_archive\sample-100.jsonl
```

- `--limit 0` 表示不限制符合条件的 Episode。
- `--output` 只覆盖输出 JSONL 及同名 `.stats.json` 路径。
- 当前 CLI 不能覆盖 Episode 输入目录和原始数据根目录；迁移到其他机器前需要先调整 `config.py`。这是当前实现限制，不应把默认 `G:` 路径视为可移植配置。

## 验证输出

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.archived.parquet_to_jsonl.validate_archive `
  data\visit_archive\sample-100.jsonl `
  --report data\visit_archive\sample-100.validation.json
```

## 代码文件

- `adapter.py`：批量读取 Episode Parquet、筛选 visit、聚合资料并写入 JSONL。
- `config.py`：输入、输出、批大小、ICU 排除规则和出院小节配置。
- `assembler.py`：组装一条冻结 schema 的 visit archive。
- `aggregators.py`：实验室、诊断、用药、检查和接触等事件聚合。
- `schema.py`：`mimic_visit_archive/1.0.0` 契约。
- `snapshots.py`：五个临床决策时点的可用证据冻结。
- `partitioning.py`：按患者固定分配数据集分区，防止患者泄漏。
- `eligibility.py`：年龄、性别和病例可用性筛选。
- `ds_parser.py`：出院记录章节解析。
- `validate_archive.py`：流式校验 JSONL 和生成报告。
- `run_eda.py`、`run_disease_eda.py`、`build_eda_html.py`：早期 EDA 脚本。

## 依赖与限制

- 依赖 Python 3.12、DuckDB、Pandas 等项目环境依赖。
- 适配器面向固定 Episode 输出契约，不是通用 Parquet 转换器。
- `run_eda.py`、`run_disease_eda.py` 和 `build_eda_html.py` 含固定磁盘路径，属于历史分析入口，不应作为通用生产命令。
- 如果最终确认只保留 admission 清洗路线，本模块及 Episode 路线可以单独评估是否移出活动代码。

## 验证

```powershell
.\.venv\Scripts\python.exe -m unittest -v tests.test_visit_archive
```
