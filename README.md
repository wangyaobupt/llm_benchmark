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
  │  Episode 聚合  mimic_episode/           OK
  │  41 表 → parquet（768K episode）
  │                                                ▼
  │  G 盘 episode parquet
  │  [1] 抽取      parquet_to_jsonl/        OK
  │      37 字段 JSONL  320K visits
  │  [2] 清洗      7 个 DS 文本 → LLM 实体抽取  待办
  │  [3] 标准化    值级术语标准化             待办
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
| Episode 聚合 | 数据层 | ✅ 完成 | 41 表 → 11 张 parquet，768K episode，48.9 GB（`mimic_episode/`） |
| 数据抽取 | 数据层 | ✅ 完成 | 37 字段 visit 级 JSONL，320,267 visits，27.4 GB（`parquet_to_jsonl/`） |
| 清洗 | 数据层 | ⏳ 待办 | 7 个 DS 章节文本字段 → LLM 实体抽取，新增 `_entities` 数组 |
| 标准化 | 数据层 | ⏳ 待办 | 诊断/药物/症状值级术语标准化，双阶段 LLM 映射 + manifest |
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
| `parquet_to_jsonl/` | 数据层 | G 盘 episode parquet → visit 级 37 字段 JSONL |
| `mimic_episode/` | 数据层 | Episode 聚合（覆盖 41 张源表） |
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
mimic_episode\scripts\pipeline\run_mimic_pipeline.ps1 -Task sync
mimic_episode\scripts\pipeline\run_mimic_pipeline.ps1 -Task validate
mimic_episode\scripts\pipeline\run_mimic_pipeline.ps1 -Task extract
mimic_episode\scripts\pipeline\run_mimic_pipeline.ps1 -Task aggregate-episodes
```

本机聚合目录为 `G:\Projects\医疗数据集评测-MIMIC\outputs\episodes`。详见 [docs/design/clinical_episode_aggregation_plan.md](docs/design/clinical_episode_aggregation_plan.md)。

### 数据抽取

从 G 盘 episode parquet 提取 visit 级全量 JSONL，作为评测层五类 MCQ 题型的统一数据底座。每行是一个住院（`hadm_id`）的完整 JSON 对象，37 个字段按 8 个顶层分组嵌套：

`identifiers` / `demographics` / `vitals` / `narrative` / `investigations` / `diagnoses` / `treatments` / `disposition`

抽取层忠实记录全量资料，不做信息隔离；信息隔离由下游出题引擎按题型选择性读取字段实现。

**关键修复**：旧 17 列路线的 `discharge_record` 字段 100% 为空（使用 Follow-up Instructions 章节，100% 被去标识化为 `___`）。新路线改用 **Discharge Instructions** 章节（99.2% 覆盖率），根治了离院指导（题型 5）的数据缺口。同理，转诊科室（题型 4）通过新增 `disposition.primary_service` + `disposition.discharge_location` 字段填补。

| 指标 | 值 |
|---|---|
| 候选 episodes | 331,537 |
| 写出 visits | 320,267 |
| 跳过 | 11,270 |
| 数据体积 | 27.4 GB |
| 平均每 visit | 89.6 KB |
| 提取耗时 | 68 min（DuckDB 流式批处理） |

```powershell
.venv\Scripts\python.exe -m parquet_to_jsonl.run_eda
```

字段规范详见 `data/出题数据抽取字段规范.md`（本地文件，`.gitignore` 排除）。

### 清洗与标准化（待实现）

**清洗**：对 7 个 DS 章节文本字段（chief_complaint, HPI, PMH, medications_on_admission, social_history, allergies, physical_exam）调用 DeepSeek 做 LLM 实体抽取。输出在 JSONL 中新增对应 `_entities` 数组，原文保留不动。技术路线：多线程 + checkpoint 断点续跑 + fail-closed。

**标准化**：值级术语标准化，不改字段结构。诊断名 → 标准疾病名 + ICD 章节归组；药物名 → 标准通用名/类别；症状实体同义归并；radiology exam_name 归一化；年龄 → age_band。双阶段 LLM 映射（build-mappings → transform），统计证据不足即终止。

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
| `handoffs/项目接手文档.md`（本地） | 项目总览、数据契约、字段映射（不推送） |
| [docs/项目流程梳理与推进计划.md](docs/项目流程梳理与推进计划.md) | 流程梳理与推进计划 |
| [docs/文件保存规范.md](docs/文件保存规范.md) | 目录职责、命名约定、新增文件决策流程 |

### 方法学与设计

| 文档 | 内容 |
|---|---|
| [docs/design/MIMIC评测数据集构建方法学.md](docs/design/MIMIC评测数据集构建方法学.md) | 方法学全文 |
| [docs/design/clinical_episode_aggregation_plan.md](docs/design/clinical_episode_aggregation_plan.md) | Episode 聚合实施方案 |
| [docs/design/episode_field_mapping.md](docs/design/episode_field_mapping.md) | 字段级映射 |
| [docs/design/mimic-multimodal-benchmark-guide.md](docs/design/mimic-multimodal-benchmark-guide.md) | 多模态 benchmark 指南 |

### 分析报告

| 文档 | 内容 |
|---|---|
| [docs/reports/dashboard.html](docs/reports/dashboard.html) | 动态进度仪表盘（浏览器直接打开） |
| [docs/reports/data-profiling-report.md](docs/reports/data-profiling-report.md) | 数据质量 profiling 报告 |
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
