# Benchmark 当前状态摘要

> 本文件只保留当前状态，不复制另一套数字。  
> 带关键代码的数据层解读：[`docs/guides/项目进展与数据层代码解读.md`](docs/guides/项目进展与数据层代码解读.md)  
> 执行合同与 W0–W10 闸门：[`docs/plans/20260819_Benchmark-问题复核与实施计划-v3.1-明确执行版.md`](docs/plans/20260819_Benchmark-问题复核与实施计划-v3.1-明确执行版.md)  
> 仓库入口：[`README.md`](README.md)  
> 文件保存：[`文件保存规范.md`](文件保存规范.md)

## 一句话

五类题型底座第三版已从 MIMIC **CSV.GZ 原表**直抽 10,000 例 Visit 并完成标准化；时间线与分家族挖掘代码已落地、10k 待跑。并行的冠心病事件底座 / 检查选择 W1 仍非正式金标准。旧 V2 / phenotype 已失效。`gold = 0`。

## W0 失效结论

- 本轮只使用 MIMIC-IV，香港 RWD 不纳入。
- 旧 phenotype、8 类特征设计和旧 V2 规则/题目不作为新管线输入。
- 旧 V2 历史链路：`1,584` formal accepted → `738` 去重 → `165` 收敛 → `134` 候选 → `0` 人工批准 gold。整链因时间、split、分母和后验信息合同未冻结而失效。
- 旧 final-test 只保留为 `engineering_audit_only`。
- 已落地：[`docs/legacy-invalidation-manifest.json`](docs/legacy-invalidation-manifest.json)、`evaluation_pipeline/governance/legacy.py`、`data_pipeline.phenotype` 旧路径不可导入。

## 分层现状

| 层 | 可用 | 不可用 |
|---|---|---|
| **V3 五类题型直抽** | 只读 `data/RawData` CSV.GZ；10,000 例 `visits.json`（`random10k_dev20`）；时间点补齐 `random10k_dev20_times`；标准化 `v1.0.9`（主诉 mapped ≈96%）；timeline / mining 代码已落地 | 时间线 10k 与六个家族挖掘尚未跑完；NER 全量不做；不出题 |
| 冠心病事件数据 | 谱归档 108,833 住院；三模块事件 39,036 住院 / 27,336,811 条 `clinical_event/1.2.0`；1,000 例无损聚合 | 全队列未聚合；15,316 条归一化复核未关 |
| 历史出题 | V1 冻结在 `versions/v1-template-stem/`（221 题）；V2 在 `versions/v2-llm-stem/` + `data_pipeline/archived/phenotype/` | V1 探针非正式评测；V2 134 候选不得送审或发布；根目录 `tasks/` 已删除 |
| 检查选择重建 | `protocol.yaml` 为 `frozen`（`conditional_order_choice`）；`protocol-lock.json` / `catalog-lock.json` 存在；1,000 例 first-wave corpus（`methodology_unreviewed`） | 无 run-lock；不能新建 formal val/test；mining 11 条 FDR 通过不是 gold |

## V3 直抽（当前五类题型底座）

第三版**不**以住院归档、事件 Parquet、冠心病队列或旧 17 列 CSV 为输入。唯一合法输入是 MIMIC CSV.GZ。抽样键是原生 `(subject_id, hadm_id)`。

| 站 | 代码 | 产物（本地 `data/derived/`，不入库） |
|---|---|---|
| 抽取 | `data_pipeline/mcq_visit_extract/` | `mcq_visit_extract/random10k_dev20/`（10,000 行） |
| 时间点补齐 | `...backfill_times` | `random10k_dev20_times/`（不覆盖抽取） |
| 标准化 | `data_pipeline/mcq_visit_standardize/` | `random10k_dev20_v1.0.9/` |
| 时间线 | `data_pipeline/mcq_visit_timeline/` | 待跑 `mcq_visit_timeline/random10k_dev20_v1.0.0/` |
| 挖掘 | `data_pipeline/mcq_visit_mining/` | 待跑；六个 `--family` 分目录 |

计划：[`docs/design/20260820_出题数据抽取第三版-1万例随机Visit直接抽取执行计划.md`](docs/design/20260820_出题数据抽取第三版-1万例随机Visit直接抽取执行计划.md)。运行：[`docs/guides/mcq-visit-timeline-mining.md`](docs/guides/mcq-visit-timeline-mining.md)。标准化仪表盘：[`docs/reports/mcq-visit-standardize-random10k-dashboard.html`](docs/reports/mcq-visit-standardize-random10k-dashboard.html)。

## 仓库整理（文档 / 目录）

- 规范源：根目录 [`文件保存规范.md`](文件保存规范.md)。
- 执行合同现文件名：`docs/plans/20260819_Benchmark-问题复核与实施计划-v3.1-明确执行版.md`。
- 设计文档已改为中文名，见 [`docs/README.md`](docs/README.md)。
- 五类题型设计在 `mcq_generation/`；V3 直抽实现在 `data_pipeline/mcq_visit_*`。该目录里 2026-08-07 的 visit JSONL 规范是字段合同，不是让人去抽事件 Parquet。

## 下一步

1. **V3**：跑时间线 10,000 例，再按六个家族分别挖掘（隔离后验）。指南 [`docs/guides/mcq-visit-timeline-mining.md`](docs/guides/mcq-visit-timeline-mining.md)。NER 全量不做；accepted 规则不是 gold。
2. 检查选择：对齐 snapshot 与 query 的时钟（`event_time < index_time` + `evidence_window_basis`）。
3. 完成 1,000 例 integration audit；未 freeze 不得把 W6/W7 或检查选择 mining 当作成绩。
4. 不要把 11 条 FDR 规则或 134 道旧候选审成 gold。
5. 新 formal validation/final-test 不能从旧 60/20/20 holdout 升级（`previous_exposure=none` 为 0）。
