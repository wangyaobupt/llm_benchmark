# docs 文档索引

本目录存放项目的设计文档、报告、参考资料与操作手册。**当前进展与整体计划以根目录 [`README.md`](../README.md) 为准**，本索引只负责导航 `docs/` 内的文档。

目录归类规则见 [`文件保存规范.md`](文件保存规范.md)。

## 目录导航

| 子目录 | 内容 |
|---|---|
| [`design/`](#design-方法学与设计) | 方法学、构建方案、字段映射、标注协议 |
| [`reports/`](#reports-分析报告与数据清单) | 分析报告、仪表盘、数据清单、验收与评测结果 |
| [`reference/`](#reference-参考资料) | MIMIC 官方字段文档、表 schema 速查 |
| [`guides/`](#guides-运行手册) | 运行手册、操作 runbook |
| [`methods/`](#methods-方法协议) | 方法/任务协议 |
| [`normalization-review/`](#review-人工审阅指南) | 跨批归一化人工审阅操作指南 |
| [`text-ner-review/`](#review-人工审阅指南) | Text NER 人工校准操作说明 |
| [`_archive/`](_archive/README.md) | 已废止、过时或重复的文件 |

---

## design/ — 方法学与设计

| 文件 | 内容 |
|---|---|
| `MIMIC评测数据集构建方法学.md` | 评测数据集构建方法学全文（数据来源、聚合、清洗、标准化、出题设计） |
| `patient-journey-benchmark-technical-roadmap.md` | Patient-Journey benchmark 详细技术路线图 |
| `mimic-admission-raw-jsonl-schema.md` | 单次住院原始归档 JSONL schema（字段、连接规则、边界） |
| `mimic-admission-raw-field-dictionary.md` | 单次住院原始归档逐字段数据字典（自动对账生成） |
| `raw-archive-cleaning-standardization.md` | 原始归档后的清洗与标准化流程 |
| `data-layer-processing-patterns.md` | 数据层处理模式（代码级说明） |
| `mimic-dictionary-lookup.md` | MIMIC-IV 编码解析字典 |
| `mimic-multimodal-benchmark-guide.md` | MIMIC 多模态数据与 benchmark 建设指南 |
| `investigation-selection-gold-method.md` | 检查检验选择任务 gold 构建方法（探索性草案） |
| `text-ner-methodology.md` | Text NER 方法学设计 |
| `text-ner-model-interface.md` | Text NER 全量抽取模型接口 |
| `text-ner-entity-annotation-protocol.md` | 文本 NER 实体与显式关系标注协议 |
| `clinical_episode_aggregation_plan.md` | Episode 多系统聚合实施方案（归档路线参考） |
| `episode_field_mapping.md` | Episode 聚合输出字段映射（归档路线参考） |

## reports/ — 分析报告与数据清单

### EDA 与数据清单

| 文件 | 内容 |
|---|---|
| `mimic-raw-coronary-eda.md` / `.html` / `-metrics.json` | 冠心病疾病谱全量 EDA（交互式 HTML + 指标 + 摘要） |
| `mimic-raw-10000-eda.md` / `-metrics.json` | 10,000 例原始归档 EDA |
| `mimic-poe-timeline-sample-analysis.md` / `-metrics.json` | POE 可观察医嘱时间线样本验证 |
| `data-layer-completeness-audit.md` / `-metrics.json` | 数据层完整性审计 |
| `data-profiling-report.md` | 数据画像报告 |
| `ehpdcl_data_inventory.md` | EHR 数据清单 |
| `mimic-admission-raw-field-dictionary.json` | 逐字段数据字典（机器格式，与 design 中 .md 同源） |
| `coronary-cohort-extraction-estimate.md` / `.json` | 冠心病队列抽取估算 |

### 验收与审计

| 文件 | 内容 |
|---|---|
| `cleaned-events-acceptance-audit.json` | 清洗事件验收审计（机器指标） |
| `cleaned-events-next-round-assessment.md` | 清洗事件下一轮评估 |
| `normalized-events-acceptance-audit.json` | 归一化事件验收审计（机器指标） |
| `event-pipeline-sample-100-validation.md` | 事件管线 100 例验证 |
| `event-pipeline-modularization-validation.md` | 事件管线模块化验证 |
| `discharge-posthoc-text-scope-audit.md` | 出院小结 post-hoc 文本范围审计 |
| `clinical-review-freeze-checklist.md` | 临床审核冻结清单（六组占位值待裁决） |

### Text NER 验收（成对 .md 摘要 + .json 指标）

| 文件 | 内容 |
|---|---|
| `text-ner-annotation-package-acceptance.*` | 标注包验收 |
| `text-ner-annotation-scope-rehearsal.*` | 标注范围试运行 |
| `text-ner-input-manifest-acceptance.*` | 输入 manifest 验收 |
| `text-ner-method-run-acceptance.*` | 方法运行验收 |
| `text-ner-full-extraction-interface-acceptance.*` | 全量抽取接口验收 |
| `text-ner-api-json-reliability-acceptance.md` | API JSON 可靠性验收 |
| `text-ner-api-monitor-acceptance.md` | API 监控验收 |
| `text-ner-deepseek-cost-compliance.*` | DeepSeek 成本合规验收 |

### 评测、调研与方案

| 文件 | 内容 |
|---|---|
| `execution-progress-p1-p5.md` | 执行进度 P1–P5（探索性原型量化结果） |
| `multi-model-evaluation-plan.md` | 多模型评测方案 + 人工审核负荷清单 |
| `final-test-blind-evaluation.md` | final_test 盲测评估 |
| `benchmark-five-dimension-evidence-review.md` | 五维 benchmark 证据综述 |
| `ehr-eval-construction-survey.md` / `-benchmarks.md` / `-methodology.md` | EHR 评测集构建调研（综述 + 基准 + 方法学） |
| `five-dim-gold-survey-tests-diagnosis.md` | 诊断维 gold 调研测试 |
| `five-dim-gold-survey-treatment-referral-followup.md` | 治疗/转诊/随访维 gold 调研测试 |
| `five-dimension-execution-refinement.md` | 五维执行细化 |
| `ner-re-execution-survey.md` | NER 重执行调研 |
| `investigation-selection-exploratory-prototype.md` | 检查检验选择探索性原型 |

### 仪表盘

| 文件 | 内容 |
|---|---|
| `dashboard.html` | 动态进度仪表盘 |
| `patient-journey-benchmark-roadmap.html` | 交互式技术路线图（离线 HTML） |
| `monday-progress-report.html` | 项目进展汇报（周报快照） |

## reference/ — 参考资料

| 文件 | 内容 |
|---|---|
| `mimic-iv-3.1-text-field-inventory.md` | MIMIC-IV 3.1 文本字段清单 |
| `mimic_reference/` | MIMIC 官方表文档（`cxr/`、`ecg/`、`ed/`、`hosp/`、`icu/`、`note/`，逐表 schema + 字段说明） |

## guides/ — 运行手册

| 文件 | 内容 |
|---|---|
| `text-ner-runbook.md` | Text NER v1 API 配置与运行手册 |
| `text-ner-v2-runbook.md` | Text NER v2 运行手册（干净重做版） |

## methods/ — 方法协议

| 文件 | 内容 |
|---|---|
| `investigation-selection-protocol.md` | 检查检验选择任务协议（单一规范源、锁定语义、停止条件） |

## review/ — 人工审阅指南

| 文件 | 内容 |
|---|---|
| `normalization-review/README.md` | 跨批归一化人工审阅操作指南（100 条试审流程与验收） |
| `text-ner-review/README.md` | Text NER 人工校准操作说明（A/B 双标 + 裁决流程） |

---

## 归档说明

已废止、过时或重复的文件已移入 [`_archive/`](_archive/README.md)，不再出现在上述索引中。归档明细与理由见该目录的 `README.md`。
