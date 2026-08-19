# 归档说明

本目录保存已废止、过时或重复的文件，仅作历史记录，**不再参与当前工作流**。归档文件仍受 Git 版本控制，需要时可从历史找回。

## 归档明细

| 原路径 | 归档理由 |
|---|---|
| `docs/项目流程梳理与推进计划.md` | 2026-08-10 旧版概览，已被根目录 [`README.md`](../../README.md)（2026-08-15）的“整体计划 + 当前进展 + 优先执行顺序”完整取代 |
| `docs/项目流程图.drawio` | 同上，流程图内容已由根 README 的分层流程与交互式路线图覆盖 |
| `docs/research-status.md` | 2026-08-10 旧版进度文档，与根 README“当前进展”重复，且其“文档与仓库事实的差异”所记录的分歧均已解决 |
| `docs/design/visit-archive-schema.md` | 文档开头自标“已废止”，派生 visit archive 已被单次住院原始归档 JSONL schema 取代 |
| `docs/reports/visit-archive-p0-validation.md` / `.json` | 派生 visit archive（`parquet_to_jsonl` 路线）验证报告，该路线已废止 |
| `docs/reports/visit-archive-expanded-validation.json` | 同上（1,000 episode 扩展验证指标） |
| `docs/reports/mimic-poe-timeline-sample-100-metrics.json` | 与 `mimic-poe-timeline-sample-metrics.json` 内容逐字节相同（已比对确认），且 `mimic-poe-timeline-sample-analysis.md` 引用的是非 sample-100 版本 |
| `docs/_archive/Case_Spider.md` | 与本仓库无关的旧笔记 |
| `docs/_archive/20260817_周工作回顾.md` | 周报快照 |
| `docs/_archive/chat-dumps/` | 对话草稿（文件名即首句） |
| `docs/_archive/early-visit-specs/` | 2026-08-07 visit 级 JSONL 抽取规范，已被 event pipeline 取代 |
