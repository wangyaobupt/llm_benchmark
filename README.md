# MIMIC 临床 LLM Benchmark

基于 MIMIC-IV v3.1 / ED 2.2 / Note 2.2 构建临床 LLM 评测基准：先用真实世界数据产出五类英文 A-D 单选临床 MCQ，再用这五类题目从五个维度评估 LLM 的临床判断能力。

题目围绕统一临床流程 `患者信息 → 检查检验 → 临床诊断 → 治疗处置 → 转诊科室 → 离院指导` 展开，覆盖五个决策点。

## 两层架构

项目从下到上分为**数据层**和**评测层**，数据层的产物直接喂给评测层出题。

```
MIMIC-IV v3.1 / ED 2.2 / Note 2.2
        │
        ▼
  数据层 ──────────────────────────────────────────
  │  原始住院归档  data_pipeline/mimic_raw_archive/  10K与冠状动脉疾病谱全量运行完成
  │  32张住院内源表 → 一行一个 hadm_id
  │  7张公共字典单独保存；排除 ICU chartevents 与 OMR
  │  [2] 清洗      类型/时间/质量/文书结构化   已指定流程
  │  [3] 标准化    代码/药物/检验/文本术语映射 已指定流程
  └────────────────────────────────────────────────
        │
        ▼
  评测层 ──────────────────────────────────────────
  │  [4] MCQ 出题  mcq_generation/          仅设计
  │  [5] LLM 评估                              待办
  └────────────────────────────────────────────────
```

| 阶段 | 层 | 完成度 | 说明 |
|---|---|---|---|
| Episode 聚合 | 数据层 | 🟤 历史中间层 | 41 表 episode Parquet 仍保留供审计，新的 raw archive 直接按原始主键关联 |
| 数据抽取 | 数据层 | ✅ 已完成验证 | `mimic_admission_raw` 1.0.0；10K与108,833次冠状动脉疾病谱全量提取完成，分片、续跑和原始字段验证通过 |
| 清洗 | 数据层 | 📋 流程已指定 | raw row 展开、类型与时间解释、质量标记、文书结构化；不覆盖原始归档 |
| 标准化 | 数据层 | 📋 流程已指定 | 代码字典、药物、检验单位和文本实体映射；结果以 sidecar 保存 |
| MCQ 出题 | 评测层 | 🔷 设计中 | 题型 1 有完整 Stage 0-10 设计；题型 2-5 仅题型规范；零实现代码 |
| LLM 评估 | 评测层 | ⏳ 待办 | 评估框架、指标、LLM 接入未启动，依赖题库产出 |

## 五类题型

| # | 题型 | 评测层向 LLM 提出的问题 | 设计状态 |
|---:|---|---|---|
| 1 | Clinical investigation selection | "该患者下一步最可能开什么检查？" | 完整 10 阶段生成设计 |
| 2 | Clinical diagnosis | "该患者的诊断是什么？" | 题型规范 |
| 3 | Treatment and management | "该患者的首选治疗方案？" | 题型规范 |
| 4 | Referral and specialty selection | "该患者应转哪个科室？" | 题型规范 |
| 5 | Discharge advice and follow-up | "该患者离院后如何随访？" | 题型规范 |

题型 1 的核心原则：统计答案先于语言生成——先从 RWD 挖掘「患者特征 → 检查项」条件概率规则取 rank-1，模型只负责写合成题干和理由，不决定答案、不改选项、不添加规则外的患者事实。

## 项目结构

| 目录 | 层 | 作用 |
|---|---|---|
| `data_pipeline/` | 数据层 | 格式转换、原始归档、字典构建、临床可读清洗和 Episode 聚合 |
| `rwd_pipeline/` | 数据层 | 旧版提取/清洗/标准化（17 列 CSV 路线，已被替代） |
| `mcq_generation/` | 评测层 | MCQ 出题模块（当前仅设计文档，代码待实现） |
| `eda/` | — | 探索性数据分析（`exploratory/` 早期探索 + `analysis/` 当前分析） |
| `docs/` | — | 项目文档（`design/` 方法学、`reports/` 分析报告、`reference/` 参考资料） |
| `tests/` | — | 测试套件 |
| `data/` | — | 本地数据与工具（`.gitignore` 排除，不推送） |

目录编排规范详见 [docs/文件保存规范.md](docs/文件保存规范.md)。

## 数据层

### Episode 聚合

跨系统聚合 MIMIC-IV 3.1、IV-ED 2.2、IV-Note 2.2 的 41 张源表为 episode-level Parquet（768K episode / 48.9 GB）。住院使用 `H:<hadm_id>`；无有效住院关联的急诊使用 `E:<stay_id>`。

```powershell
data_pipeline\mimic_episode\scripts\pipeline\run_mimic_pipeline.ps1 -Task sync
data_pipeline\mimic_episode\scripts\pipeline\run_mimic_pipeline.ps1 -Task validate
data_pipeline\mimic_episode\scripts\pipeline\run_mimic_pipeline.ps1 -Task extract
data_pipeline\mimic_episode\scripts\pipeline\run_mimic_pipeline.ps1 -Task aggregate-episodes
```

本机聚合目录为 `G:\Projects\医疗数据集评测-MIMIC\outputs\episodes`。详见 [docs/design/clinical_episode_aggregation_plan.md](docs/design/clinical_episode_aggregation_plan.md)。

### 单次住院原始归档

新的数据层从原始 MIMIC CSV 构建 `mimic_admission_raw` 1.0.0：每行对应一个 `hadm_id`，各模块内按原始表名保存原始字段和原始行，不解析出院章节、不聚合 lab panel、不生成专科标签、标准名称、患者分区或决策快照。

纳入32张住院内源表；7张公共字典单独保存。明确排除 ICU `chartevents` 高频监护数据；`omr` 没有原生 `hadm_id`，也不通过时间推断纳入住院。层级、连接键与排除边界见 [MIMIC 单次住院原始归档 JSONL schema](docs/design/mimic-admission-raw-jsonl-schema.md)；全部412个顶层/源表/公共字典字段的逐字段解释见[原始归档逐字段数据字典](docs/design/mimic-admission-raw-field-dictionary.md)。

| 指标 | 值 |
|---|---|
| 候选 episodes | 331,537 |
| 写出 visits | 320,267 |
| 跳过 | 11,270 |
| 数据体积 | 27.4 GB |
| 平均每 visit | 89.6 KB |
| 提取耗时 | 68 min（DuckDB 流式批处理） |

以上指标属于 legacy visit JSONL，仅作为历史基线，不代表新的 raw archive。

```powershell
.venv\Scripts\python.exe -m data_pipeline.mimic_raw_archive --sample-size 10000
```

默认使用2个 worker、每个4个 DuckDB线程；每1,000例形成一个原子分片。中断后根据 manifest 只运行未完成的源表 staging 或 JSONL 分片。

2026-08-10 的10,000次住院验证运行已完成：最终 JSONL 为3,399,458,012字节（3.166 GiB），工作目录与最终文件合计6.442 GiB，实际耗时5分57秒。只读本地监控页面使用：

```powershell
.venv\Scripts\python.exe -m data_pipeline.mimic_raw_archive.monitor --open-browser
```

页面每5秒读取 manifest、文件元数据、磁盘和系统内存，不读取患者记录内容。单张大表扫描期间只报告表级状态，不提供无法验证的表内百分比。

当前10,000例的流式EDA见 [EDA报告](docs/reports/mimic-raw-10000-eda.md)。全患者与冠状动脉疾病谱的规模、时间和磁盘估算见 [疾病谱提取估算](docs/reports/coronary-cohort-extraction-estimate.md)。疾病谱固定为ICD-9 410–414 / ICD-10 I20–I25，外部selection不会把队列标签写进raw JSON。

2026-08-10 的冠状动脉疾病谱全量提取与 EDA 已完成：108,833 次住院、46,062 名患者、50.392 GiB、218 个分片。交互式结果见 [冠状动脉疾病谱全量 EDA](docs/reports/mimic-raw-coronary-eda.html)，可搜索/排序32张源表、筛选52个时间字段，并查看疾病谱、患者级分区、五维来源准备度和 JSONL 字段说明；页面自包含，可离线打开。

### 清洗与标准化（待实现）

清洗和标准化不修改 raw archive，分别生成可追溯 sidecar。清洗处理 source row 展开、类型/时间语义、质量标记和文书结构；标准化处理字典代码、药物、检验单位和文本实体映射。动态读取规则属于评测层，只为入选候选题生成小型 view manifest。完整流程见 [原始住院归档后的清洗与标准化流程](docs/design/raw-archive-cleaning-standardization.md)。

## 评测层

### MCQ 出题

题型 1（检查检验选择）有完整的 Stage 0-10 生成设计，从条件规则挖掘到 gold 发布共 11 个阶段，含 8 道统计硬门槛、干扰项选择、答案位置锁定、独立自动审题、人工审核和 fail-closed 发布门禁。

详见 [mcq_generation/mcq_generation_design.md](mcq_generation/mcq_generation_design.md)（题型 1 详细设计）和 [mcq_generation/architecture_overview.md](mcq_generation/architecture_overview.md)（跨文档架构总览）。题型 2-5 规范见 [mcq_generation/question_types.md](mcq_generation/question_types.md)。

## 环境配置

- **Python 3.12**（固定，`pyproject.toml` + `.python-version` 锁定）
- **uv** 管理依赖，`uv.lock` 锁定版本
- **DeepSeek API**：设置 `DEEPSEEK_API_KEY` 环境变量（`.env` 已被 `.gitignore` 排除）
- **WDAC 约束**：本机应用控制策略禁止从 `G:\` 和 `C:\Users` 运行 Python，仅 D 盘可用

```powershell
uv sync --locked
.venv\Scripts\python.exe -m pytest tests/ -v
```

## 数据安全

- 不提交原始 CSV、影像、波形、Parquet、DuckDB 或病例输出（`.gitignore` 已覆盖 `*.csv`、`*.parquet`、`data/`、`*.pdf`）
- 不把 MIMIC 患者级内容发送到普通在线 LLM/API
- 公开成果只包含代码、配置、字段定义、汇总结果和合规文档

## 关键文档索引

### 项目概览

| 文档 | 内容 |
|---|---|
| [docs/research-status.md](docs/research-status.md) | 当前研究进度、验证结果、文档差异与下一步入口 |
| `handoffs/handoff-20260806-1520.md`（本地） | 历史合并记录（不代表当前主线，不推送） |
| [docs/项目流程梳理与推进计划.md](docs/项目流程梳理与推进计划.md) | 流程梳理与推进计划 |
| [docs/文件保存规范.md](docs/文件保存规范.md) | 目录职责、命名约定、新增文件决策流程 |

### 方法学与设计

| 文档 | 内容 |
|---|---|
| [docs/design/MIMIC评测数据集构建方法学.md](docs/design/MIMIC评测数据集构建方法学.md) | 方法学全文 |
| [docs/design/clinical_episode_aggregation_plan.md](docs/design/clinical_episode_aggregation_plan.md) | Episode 聚合实施方案 |
| [docs/design/episode_field_mapping.md](docs/design/episode_field_mapping.md) | 字段级映射 |
| [docs/design/mimic-admission-raw-jsonl-schema.md](docs/design/mimic-admission-raw-jsonl-schema.md) | 当前 raw JSONL 字段、原始连接与排除边界 |
| [docs/design/mimic-admission-raw-field-dictionary.md](docs/design/mimic-admission-raw-field-dictionary.md) | 7个顶层字段、JSONL内380个字段和7张外置公共字典25个字段的逐字段说明 |
| [docs/design/raw-archive-cleaning-standardization.md](docs/design/raw-archive-cleaning-standardization.md) | 下一步清洗、标准化和动态读取流程 |
| [docs/design/mimic-multimodal-benchmark-guide.md](docs/design/mimic-multimodal-benchmark-guide.md) | 多模态 benchmark 指南 |

### 分析报告

| 文档 | 内容 |
|---|---|
| [docs/reports/dashboard.html](docs/reports/dashboard.html) | 动态进度仪表盘（浏览器直接打开） |
| [docs/reports/mimic-raw-coronary-eda.html](docs/reports/mimic-raw-coronary-eda.html) | 108,833次冠状动脉疾病谱住院的交互式全量EDA与JSONL字段说明 |
| [docs/reports/mimic-admission-raw-field-dictionary.json](docs/reports/mimic-admission-raw-field-dictionary.json) | 与逐字段Markdown一致的机器可读字段字典 |
| [docs/reports/mimic-raw-coronary-eda.md](docs/reports/mimic-raw-coronary-eda.md) | 同一全量EDA的静态Markdown报告 |
| [docs/reports/data-profiling-report.md](docs/reports/data-profiling-report.md) | 数据质量 profiling 报告 |
| [docs/reports/visit-archive-p0-validation.md](docs/reports/visit-archive-p0-validation.md) | 新 schema P0 修复与 100 episode 小样本验证 |
| [docs/reports/ehpdcl_data_inventory.md](docs/reports/ehpdcl_data_inventory.md) | 香港医管局数据资产清单 |

### MCQ 出题

| 文档 | 内容 |
|---|---|
| [mcq_generation/architecture_overview.md](mcq_generation/architecture_overview.md) | MCQ 生成跨文档架构总览 |
| [mcq_generation/mcq_generation_design.md](mcq_generation/mcq_generation_design.md) | 题型 1 Stage 0-10 生成设计 |
| [mcq_generation/question_types.md](mcq_generation/question_types.md) | 五类题型规范 + EHR 字段表 |

### 旧版规格（17 列 CSV 路线，跟模块走）

| 文档 | 内容 |
|---|---|
| [rwd_pipeline/rwd_benchmark_extraction_spec.md](rwd_pipeline/rwd_benchmark_extraction_spec.md) | 抽取规格 |
| [rwd_pipeline/rwd_benchmark_cleaning_spec.md](rwd_pipeline/rwd_benchmark_cleaning_spec.md) | 清洗规格（4 字段，可复用 prompt） |
| [rwd_pipeline/rwd_benchmark_standardization_spec.md](rwd_pipeline/rwd_benchmark_standardization_spec.md) | 标准化规格 |

## 本地数据状态

- MIMIC-IV 3.1：已下载，SHA-256 33/33 通过
- MIMIC-III 1.4：已下载，SHA-256 30/30 通过
- MIMIC-IV-Note 2.2：已下载，SHA-256 5/5 通过
- MIMIC-IV-ED 2.2：已下载，SHA-256 8/8 通过
- CXR、ECG、ECHO、Waveform、FHIR：尚未发现

数据完整性校验工具：`data/audit_mimic_download.ps1`（本地文件，`.gitignore` 排除），读取 CSV 表头并可选核验 SHA-256，不读取或输出患者数据行。
