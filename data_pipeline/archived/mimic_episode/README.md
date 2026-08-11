# MIMIC Episode 事件管道

## 当前定位

这是可选的 Episode/visit 路线，不属于当前 admission 临床可读 JSONL 主流程。它直接从 MIMIC CSV.GZ 源表构建跨急诊、住院、ICU 和文本系统的 Episode、接触和事件 Parquet 数据集。

```text
MIMIC 原始表 → mimic_episode → Episode Parquet
```

只有需要 Episode 时间线、事件关系或后续 `parquet_to_jsonl` visit 归档时才执行本模块。若目标只是“原始 admission JSONL → 字典解码和 POE 解析”，不需要运行它。

## 当前不能直接删除的原因

`mimic_raw_archive` 目前复用了本目录 `source_catalog.py` 中的 MIMIC 源文件路径、锁定表头和字段类型。因此本模块虽然不在主清洗执行链中，目录仍包含共享代码依赖。删除前必须先把 `source_catalog.py` 迁入独立公共模块并更新调用方。

## 命令

查看所有子命令：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.archived.mimic_episode --help
```

### 1. 验证第一阶段源文件

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.archived.mimic_episode validate `
  --data-root data\RawData
```

### 2. 抽取文本和病例索引

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.archived.mimic_episode extract `
  --data-root data\RawData `
  --output-dir data\episodes\stage1 `
  --memory-limit 8GB `
  --threads 4
```

输出包括 `case_index.parquet`、`text_documents.parquet`、`note_details.parquet` 和 `quality_report.json`。

### 3. 验证 Episode 全量源表

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.archived.mimic_episode validate-episodes `
  --data-root data\RawData
```

该命令检查全过程聚合要求的 41 张源表及锁定表头。

### 4. 聚合 Episode

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.archived.mimic_episode aggregate-episodes `
  --data-root data\RawData `
  --output-dir data\episodes\full `
  --memory-limit 8GB `
  --threads 4
```

主要输出：

- `episode_index.parquet`；
- `care_contacts.parquet`；
- `timeline_events.parquet`；
- `event_items.parquet`；
- `documents.parquet`；
- `evidence_links.parquet`；
- `patient_history_refs.parquet`；
- `episode_coverage.parquet`；
- `unresolved_events.parquet`；
- `quality_report.json`。

已有输出默认拒绝覆盖；只有明确传入 `--overwrite` 才覆盖受管输出。

### 5. 导出单个 Episode JSON

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.archived.mimic_episode export-episode `
  --output-dir data\episodes\full `
  --episode-id EPISODE_ID `
  --destination data\episodes\one-episode.json
```

导出结构明确区分 `prior_context` 和 `current_episode`。

## 与 `parquet_to_jsonl` 的关系

`parquet_to_jsonl.adapter` 默认读取本模块生成的 Episode Parquet，再组装为 visit 级 JSONL 和决策快照。它不是 admission 主清洗路线的上游。

## 代码文件

- `cli.py`：五个子命令的统一入口。
- `source_catalog.py`：41 张源表路径、表头和字段类型；当前也被 `mimic_raw_archive` 复用。
- `paths.py`：第一阶段源文件定位与验证。
- `pipeline.py`：文本和病例索引第一阶段。
- `episode_pipeline.py`：Episode 全过程聚合。
- `episode_events.py`：事件和 event item 生成规则。
- `episode_export.py`：单个 Episode JSON 导出。
- `sql/`：DuckDB 建表、连接、聚合和质量检查 SQL。
- `scripts/`：历史运行、恢复和画像脚本。

## 限制

- `scripts/` 中部分辅助脚本仍包含旧项目的 `G:` 盘绝对路径，不属于通用 CLI；迁移环境时不要直接运行这些脚本。
- 归档入口是 `python -m data_pipeline.archived.mimic_episode ...`，所有关键路径都应通过命令行显式传入。
- 模块依赖 Python 3.12、DuckDB 和本地授权 MIMIC 数据。

## 验证

```powershell
.\.venv\Scripts\python.exe -m unittest -v tests.test_episode_pipeline
```
