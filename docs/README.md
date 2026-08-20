# docs 文档索引

本目录存放项目的设计文档、报告、参考资料与操作手册。**当前进展与整体计划以根目录 [`README.md`](../README.md) 为准**，本索引只负责导航 `docs/` 内的文档。当前状态摘要只有一份：[`BenchMark-进展梳理.md`](../BenchMark-进展梳理.md)。

目录归类规则见根目录 [`文件保存规范.md`](../文件保存规范.md)（英文跳转 [`FILE_LAYOUT.md`](../FILE_LAYOUT.md)）。

## 目录导航

| 子目录 | 内容 |
|---|---|
| [`design/`](#design-方法学与设计) | 方法学、构建方案、字段映射、标注协议 |
| [`plans/`](#plans-执行计划) | 执行合同与闸门 |
| [`reports/`](#reports-分析报告与数据清单) | 分析报告、仪表盘、数据清单、验收与评测结果 |
| [`reference/`](#reference-参考资料) | MIMIC 官方字段文档、表 schema 速查 |
| [`guides/`](#guides-运行手册) | 运行手册、操作 runbook |
| [`methods/`](#methods-方法协议) | 方法/任务协议 |
| [`literature/`](#literature-文献) | 文献检索与综述 |
| [`review/`](#review-人工审阅指南) | 人工审阅操作说明 |
| [`_archive/`](_archive/README.md) | 已废止、过时或重复的文件 |

---

## design/ — 方法学与设计

| 文件 | 内容 |
|---|---|
| `MIMIC评测数据集构建方法学.md` | 评测数据集构建方法学全文（数据来源、聚合、清洗、标准化、出题设计） |
| `技术路线图.md` | Patient-Journey benchmark 详细技术路线图 |
| `MIMIC 单次住院原始归档 JSONL schema.md` | 单次住院原始归档 JSONL schema（字段、连接规则、边界） |
| `MIMIC 单次住院原始归档逐字段数据字典.md` | 单次住院原始归档逐字段数据字典 |
| `原始住院归档后的清洗与标准化流程.md` | 原始归档后的清洗与标准化流程 |
| `MIMIC 多模态数据指南.md` | MIMIC 多模态数据与 benchmark 建设指南 |
| `text-ner-methodology.md` | Text NER 方法学设计 |
| `text-ner-entity-annotation-protocol.md` | 文本 NER 实体与显式关系标注协议 |
| `MIMIC-IV Episode 聚合输出字段映射文档.md` | Episode 聚合输出字段映射（归档路线参考） |
| `一次住院信息分层与时点检查读法.md` | 一次住院分层与时点检查怎么读 |
| `一次住院从原始表到挖掘表的处理流程.md` | 从原始表到挖掘表的逐步对照 |
| `20260820_出题数据抽取第三版-1万例随机Visit直接抽取执行计划.md` | 五类题型 visit 底座第三版：从 MIMIC 原始 CSV.GZ 按 `(subject_id, hadm_id)` 随机抽 10,000 例；过程可溯源；正式交付 `visits.csv`+`visits.json` 各 1 万行、只含抽取结果 |
| `20260820_出题Visit标准化计划-术语单位症状.md` | 抽取完成后的标准化：统一检验/药物/科室术语、单位（含体温 °F→°C）、主诉症状概念；不覆盖抽取文件、不改写病历正文。主诉覆盖靠审核 `review_queue` 扩同义词，界面：`python -m data_pipeline.mcq_visit_standardize.review_app` |
| `20260820_出题Visit出院小结NER计划-DeepSeek-v4-flash.md` | 另开 visit NER：冻结 `visits.json` 出院小结 span 抽取；OpenAI 兼容 `deepseek-v4-flash`（`https://www.dmxapi.cn/v1`）；默认空跑，外传需三重授权；非正式 gold，不出题 |
| `20260820_出题Visit时间线合并与规则挖掘计划-1万例全量.md` | NER 先停。用时间点补齐时钟 + 标准化名称合成 Visit 时间线，再在 10,000 例上挖五类 X→y（strict 门槛，不出题，非正式 gold） |

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
| `mcq-visit-standardize-random10k-acceptance.md` / `.json` | 出题 Visit 标准化 10,000 例验收（无原文） |
| `mcq-visit-ner-pilot100-acceptance.md` / `.json` | 出题 Visit NER 试点 100 例验收（接地通过，非正式 gold，无原文） |
| `mcq-visit-standardize-random10k-dashboard.html` / `.json` | 出题 Visit 标准化 10,000 例结果统计与可视化（无原文） |
| `mcq-visit-mining-random10k-acceptance.md` / `.json` | 出题 Visit 六个家族 strict 挖掘验收（10k；无原文；非正式 gold） |

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

## plans/ — 执行计划

| 文件 | 内容 |
|---|---|
| `20260819_Benchmark-问题复核与实施计划-v3.1-明确执行版.md` | 检查选择重建执行合同（W0–W10 闸门） |
| `20260819_Benchmark-问题复核与实施计划.md` | 母版计划 |
| `20260819_数据层时点检查提取与完整执行清单.md` | 数据层时点检查执行清单 |

## guides/ — 运行手册

| 文件 | 内容 |
|---|---|
| `text-ner-runbook.md` | Text NER v1 API 配置与运行手册 |
| `text-ner-v2-runbook.md` | Text NER v2 运行手册（干净重做版） |
| `项目进展与数据层代码解读.md` | 数据层代码与产物读法 |
| （模块 README）[`data_pipeline/mcq_visit_ner/README.md`](../data_pipeline/mcq_visit_ner/README.md) | Visit 出院小结 NER：默认空跑；外传需 `--execute` + 确认 + `MCQ_VISIT_NER_EXTERNAL_API_APPROVED=YES` |
| `mcq-visit-timeline-mining.md` | Visit 时间线合并 + 六个家族分别挖掘的运行命令（先 timeline，再按 family 各跑一次） |
| `mcq-visit-mining-random10k-output.md` | `random10k_dev20_strict_v1.0.0` 挖掘产物目录说明（文件清单与读法；本地另有 `生成说明.md`） |

## methods/ — 方法协议

| 文件 | 内容 |
|---|---|
| `investigation-selection-protocol.md` | 检查检验选择任务协议（单一规范源、锁定语义、停止条件） |
| `数据划分.md` | 患者级划分规则 |
| `统计方式.md` | 统计口径 |

## literature/ — 文献

| 文件 | 内容 |
|---|---|
| `high-baseline-orders-masking-literature-review.md` | 高基线常规医嘱掩盖高特异性检查 |
| `mcq-visit-mining-strategies.md` | V3 Visit 挖掘策略：likelihood / PSR / TF-IDF / IDF，与 strict lift 对照 |
| `研究问题1_*.md` | 研究问题 1 检索与方案笔记 |

## review/ — 人工审阅指南

| 文件 | 内容 |
|---|---|
| `review/normalization-review.md` | 跨批归一化人工审阅操作指南（100 条试审流程与验收） |
| `review/text-ner-review.md` | Text NER 人工校准操作说明（A/B 双标 + 裁决流程） |

---

## 归档说明

已废止、过时或重复的文件已移入 [`_archive/`](_archive/README.md)，不再出现在上述索引中。归档明细与理由见该目录的 `README.md`。
