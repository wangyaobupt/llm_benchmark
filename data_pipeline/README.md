# MIMIC 数据处理管道

本目录集中维护 MIMIC 数据从原始表到可分析 JSONL 的处理代码。这里存在一条当前推荐的主清洗路线和一条可选的 Episode/visit 路线，两条路线不能混为同一条顺序流程。

## 当前推荐主流程

```text
MIMIC 原始 CSV.GZ 表
    ↓ mimic_raw_archive
Admission 级原始 JSONL
    ↓ clean_clinical_archive
字典解码 + POE 解析后的临床可读 JSONL
    ↓ event_pipeline clean
结构化临床事件 Parquet + 术语清单
    ↓ event_pipeline normalize
确定性归一化事件 Parquet + 审核队列
```

`tools/mimic_dictionary` 是字典生成工具，为清洗器提供五份官方字典；正常清洗时不需要重复执行。

## 可选 Episode/visit 路线

```text
MIMIC 原始 CSV.GZ 表
    ↓ archived/mimic_episode
Episode Parquet 数据集
    ↓ archived/parquet_to_jsonl
Visit 级 JSONL + 决策快照
```

这条路线用于 Episode 事件模型和评测快照，不是当前 admission 临床可读归档的必经步骤。

## 模块定位

| 目录 | 当前定位 | 主要输入 | 主要输出 |
|---|---|---|---|
| `mimic_raw_archive/` | 主流程第一步 | MIMIC CSV.GZ 原始表 | `mimic_admission_raw/1.0.0` JSONL |
| `clean_clinical_archive/` | 主流程第二步 | Admission 原始 JSONL | `mimic_admission_clinical_readable/1.0.0` JSONL |
| `event_pipeline/` | 主流程第三、四步 | 字典解码与 POE 解析后的 Admission JSONL | 结构化及确定性归一化事件 Parquet |
| `mimic_source_catalog.py` | 活动共享契约 | MIMIC 文件目录与锁定表头 | 供原始归档和归档 Episode 复用的源表定义 |
| `tools/mimic_dictionary/` | 辅助工具 | 五张官方字典表 | JSON、CSV、Parquet、DuckDB 字典 |
| `archived/mimic_episode/` | 已归档路线 | 41 张 MIMIC 源表 | Episode/事件 Parquet |
| `archived/parquet_to_jsonl/` | 已归档路线 | Episode Parquet | `mimic_visit_archive/1.0.0` JSONL |

`mimic_raw_archive` 与归档 Episode 路线共同读取根目录的 `mimic_source_catalog.py`。活动主流程不再依赖 `archived/` 内的任何文件。

## 主流程命令

在项目根目录执行：

```powershell
# 1. 原始表聚合为 admission JSONL
.\.venv\Scripts\python.exe -m data_pipeline.mimic_raw_archive `
  --data-root data\RawData `
  --output-dir data\raw_archive\shards `
  --merged-output data\mimic-admission-raw.jsonl `
  --sample-size 100

# 2. 解码并解析 POE
.\.venv\Scripts\python.exe -m data_pipeline.clean_clinical_archive `
  data\mimic-admission-raw.jsonl `
  --output data\clean_clinical_archive\clinical-readable.jsonl `
  --report data\clean_clinical_archive\clinical-readable.report.json
```

各模块的完整参数、数据约束和文件职责见对应目录的 `README.md`。

## 共同约束

- 当前主流程从项目根目录以 `python -m data_pipeline.<module>` 形式执行；辅助工具使用 `data_pipeline.tools.<module>`，归档代码使用 `data_pipeline.archived.<module>`。
- 原始 MIMIC 数据、生成数据和五份授权字典不得提交到 Git。
- 输出已存在时，相关主流程默认拒绝覆盖；应明确处理旧输出，不能依赖隐式覆盖。
- admission 主流程以 schema 标识连接：清洗器只接受 `mimic_admission_raw/1.0.0`。
- `clean_clinical_archive/` 可单独复制运行，其他模块默认依赖项目目录结构或项目环境。
