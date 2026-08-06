# 香港 RWD 临床基准

基于 MIMIC-IV v3.1 真实世界数据，构建面向 LLM 临床判断能力评测的英文 A-D 单选 MCQ 基准。

题目围绕统一临床流程 `患者信息 → 检查检验 → 临床诊断 → 治疗处置 → 转诊科室 → 离院指导` 展开，覆盖五类题型。

## 整体流水线

```
MIMIC-IV v3.1 / IV-ED 2.2 / IV-Note 2.2 原始表
        |
        |---- 子系统 A：visit-level RWD pipeline --------|
        |                                                |
        |  [1] 抽取     rwd_pipeline/extraction/    OK   |
        |  [2] 清洗     rwd_pipeline/cleaning/      OK   |
        |  [3] 标准化   rwd_pipeline/standardization/ X  |
        |                                                |
        |---- 子系统 B：全过程 episode 聚合 ---------------|
        |                                                |
        |  mimic_episode/                         OK     |
        |                                                |
        |---- MCQ 题目生成 -------------------------------|
                                                       |
  [4] MCQ 生成   mcq_generation/            X  仅设计
```

| 阶段 | 完成度 | 说明 |
|---|---|---|
| 抽取 | OK | 17 列 visit-level CSV（266 MB），`data/rwd_benchmark_visits.csv` |
| 清洗 | OK | LLM 实体抽取，4 个自由文本字段转 JSON 数组（247 MB） |
| 标准化 | 代码缺口 | spec + 测试契约已就绪，`rwd_pipeline/standardization/` 无实现 |
| MCQ 生成 | 仅设计 | 题型 1 有完整 Stage 0-10 设计；题型 2-5 仅有题型规范 |

## 五类题型

| # | 题型 | 设计状态 |
|---:|---|---|
| 1 | Clinical investigation selection（检查检验选择） | 完整生成设计 |
| 2 | Clinical diagnosis（临床诊断） | 题型规范 |
| 3 | Treatment and management（治疗处置） | 题型规范 |
| 4 | Referral and specialty selection（转诊科室） | 题型规范 |
| 5 | Discharge advice and follow-up（离院指导） | 题型规范 |

题型 1 的核心原则：统计答案先于语言生成——先从 RWD 挖掘"患者特征 -> 检查项"条件概率规则取第一名，模型只负责写合成题干和理由，不决定答案、不改选项。

## 项目结构

| 目录 | 作用 |
|---|---|
| `rwd_pipeline/` | 子系统 A：visit-level 提取、清洗、标准化 |
| `mimic_episode/` | 子系统 B：全过程 episode 聚合（覆盖 41 张源表） |
| `mcq_generation/` | MCQ 出题设计文档 |
| `mimic_reference/` | MIMIC 全部源表的 schema 速查 |
| `tests/` | 测试套件 |
| `docs/` | 方法学、聚合方案、字段映射、流程图 |
| `research/` | 文献综述、领域全景分析 |
| `eda/` | 探索性数据分析 |
| `scripts/` | 数据审计与工具脚本 |
| `data/` | MIMIC 原始表与派生 CSV（`.gitignore` 排除） |

## 子系统 A：RWD Pipeline

从 MIMIC 原始表提取 visit-level 数据，经 LLM 清洗后生成标准化的 RWD benchmark 输入。

### 抽取

从 `admissions`、`poe`、`labevents`、`discharge` 等表提取 17 列 visit-level CSV。

```powershell
python -m rwd_pipeline.extract_rwd_benchmark `
    --data-root <MIMIC路径> `
    --output data/rwd_benchmark_visits.csv
```

### 清洗

对 4 个自由文本字段（主诉、现病史、既往史、入院用药）调用 DeepSeek 做实体抽取，保持 17 列、行数、行序不变。64 线程并发，按行 x 字段哈希 checkpoint 断点续跑。

```powershell
$env:DEEPSEEK_API_KEY = "<set-locally>"
rwd_pipeline\run_clean_rwd_benchmark.sh `
    --input data/rwd_benchmark_visits.csv `
    --output data/rwd_benchmark_visits_cleaned.csv
```

### 标准化（待实现）

将 17 列合并标准化为 15 列（ICD 三列合并为 `primary_diagnosis` 一列）。双阶段 LLM 映射：先 `build-mappings`（候选生成 + 独立等价复核），再 `transform`（纯查表）。

```powershell
# 需先实现 rwd_pipeline/standardization/ 模块
python -m rwd_pipeline.standardize_rwd_benchmark --use-llm --mode run
```

详见 [rwd_pipeline/rwd_benchmark_standardization_spec.md](rwd_pipeline/rwd_benchmark_standardization_spec.md)。

## 子系统 B：Episode 聚合

跨系统聚合 MIMIC-IV 3.1、IV-ED 2.2、IV-Note 2.2 的 41 张源表为 episode-level Parquet。住院使用 `H:<hadm_id>`；无有效住院关联的急诊使用 `E:<stay_id>`。

统一入口：

```powershell
mimic_episode\scripts\run_mimic_pipeline.ps1 -Task sync
mimic_episode\scripts\run_mimic_pipeline.ps1 -Task validate
mimic_episode\scripts\run_mimic_pipeline.ps1 -Task extract
mimic_episode\scripts\run_mimic_pipeline.ps1 -Task validate-episodes
mimic_episode\scripts\run_mimic_pipeline.ps1 -Task aggregate-episodes
mimic_episode\scripts\run_mimic_pipeline.ps1 -Task export-episode `
    -EpisodeId 'H:12345678' -Destination 'outputs/cases/H-12345678.json'
```

聚合产物：`episode_index`、`care_contacts`、`timeline_events`、`event_items`、`documents`、`evidence_links`、`patient_history_refs`、`episode_coverage`、`unresolved_events`、`quality_report.json`。

本机默认聚合目录为 `G:\Projects\医疗数据集评测-MIMIC\outputs\episodes`；代码与运行入口位于 D 盘。详见 [docs/clinical_episode_aggregation_plan.md](docs/clinical_episode_aggregation_plan.md)。

## MCQ 出题

题型 1（检查检验选择）有完整的 Stage 0-10 生成设计，从条件规则挖掘到 gold 发布共 11 个阶段，含统计阈值、干扰项选择、答案位置锁定、独立自动审题、人工审核和 fail-closed 发布门禁。

详见 [mcq_generation/mcq_generation_design.md](mcq_generation/mcq_generation_design.md)。题型 2-5 规范见 [mcq_generation/question_types.md](mcq_generation/question_types.md)。

## 环境配置

- **Python 3.12**（固定，`pyproject.toml` + `.python-version` 锁定）
- **uv** 管理依赖，`uv.lock` 锁定版本
- **DeepSeek API**：设置 `DEEPSEEK_API_KEY` 环境变量（`.env` 已被 `.gitignore` 排除）
- **WDAC 约束**：本机应用控制策略禁止从 `G:\` 和 `C:\Users` 运行 Python，仅 D 盘可用；统一入口默认使用 `C:\Python312\envs\mimic-benchmark`

```powershell
uv sync --locked
uv run python -m unittest discover -s tests -v
```

## 数据安全

- 不提交原始 CSV、影像、波形、Parquet、DuckDB 或病例输出（`.gitignore` 已覆盖 `*.csv`、`*.parquet`、`data/`、`*.pdf`）
- 不把 MIMIC 患者级内容发送到普通在线 LLM/API
- 公开成果只包含代码、配置、字段定义、汇总结果和合规文档

## 关键文档索引

### 方法学与方案

| 文档 | 内容 |
|---|---|
| [项目接手文档.md](项目接手文档.md) | 项目总览、数据契约、字段映射、运行方式 |
| [docs/MIMIC评测数据集构建方法学.md](docs/MIMIC评测数据集构建方法学.md) | 方法学全文 |
| [docs/项目流程梳理与推进计划.md](docs/项目流程梳理与推进计划.md) | 流程梳理与推进计划 |
| [ehpdcl_data_inventory.md](ehpdcl_data_inventory.md) | 香港医管局数据资产清单 |

### 子系统 B

| 文档 | 内容 |
|---|---|
| [docs/clinical_episode_aggregation_plan.md](docs/clinical_episode_aggregation_plan.md) | Episode 聚合实施方案 |
| [docs/episode_field_mapping.md](docs/episode_field_mapping.md) | 字段级映射 |

### MCQ 出题

| 文档 | 内容 |
|---|---|
| [mcq_generation/mcq_generation_design.md](mcq_generation/mcq_generation_design.md) | 题型 1 Stage 0-10 生成设计 |
| [mcq_generation/question_types.md](mcq_generation/question_types.md) | 五类题型规范 |

### RWD Pipeline 规格

| 文档 | 内容 |
|---|---|
| [rwd_pipeline/rwd_benchmark_extraction_spec.md](rwd_pipeline/rwd_benchmark_extraction_spec.md) | 抽取规格 |
| [rwd_pipeline/rwd_benchmark_cleaning_spec.md](rwd_pipeline/rwd_benchmark_cleaning_spec.md) | 清洗规格 |
| [rwd_pipeline/rwd_benchmark_standardization_spec.md](rwd_pipeline/rwd_benchmark_standardization_spec.md) | 标准化规格 |

### 文献研究

| 文档 | 内容 |
|---|---|
| [research/medical_llm_benchmark_landscape.md](research/medical_llm_benchmark_landscape.md) | 医疗 LLM 评测基准领域全景 |
| [research/literature_analysis.md](research/literature_analysis.md) | 文献分析 |

## 本地数据状态

- MIMIC-IV 3.1：已下载，SHA-256 33/33 通过
- MIMIC-III 1.4：已下载，SHA-256 30/30 通过
- MIMIC-IV-Note 2.2：已下载，SHA-256 5/5 通过
- MIMIC-IV-ED 2.2：已下载，SHA-256 8/8 通过
- CXR、ECG、ECHO、Waveform、FHIR：尚未发现

数据完整性校验：`scripts/audit_mimic_download.ps1` 读取 CSV 表头并可选核验 SHA-256，不读取或输出患者数据行。