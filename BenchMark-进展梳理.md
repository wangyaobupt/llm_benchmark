# Benchmark 当前状态摘要

> 本文件只保留当前状态，不复制另一套数字。  
> 带关键代码的数据层解读：[`docs/guides/项目进展与数据层代码解读.md`](docs/guides/项目进展与数据层代码解读.md)  
> 执行合同与 W0–W10 闸门：[`docs/plans/20260819_Benchmark-问题复核与实施计划-v3.1-明确执行版.md`](docs/plans/20260819_Benchmark-问题复核与实施计划-v3.1-明确执行版.md)  
> 仓库入口：[`README.md`](README.md)  
> 文件保存：[`文件保存规范.md`](文件保存规范.md)

## 一句话

冠心病 MIMIC 事件底座可用；W1 合同、eligibility catalog 和 1,000 例 first-wave corpus 已落地，但非正式金标准。旧 V2 / phenotype 已失效。`gold = 0`。

## W0 失效结论

- 本轮只使用 MIMIC-IV，香港 RWD 不纳入。
- 旧 phenotype、8 类特征设计和旧 V2 规则/题目不作为新管线输入。
- 旧 V2 历史链路：`1,584` formal accepted → `738` 去重 → `165` 收敛 → `134` 候选 → `0` 人工批准 gold。整链因时间、split、分母和后验信息合同未冻结而失效。
- 旧 final-test 只保留为 `engineering_audit_only`。
- 已落地：[`docs/legacy-invalidation-manifest.json`](docs/legacy-invalidation-manifest.json)、`evaluation_pipeline/governance/legacy.py`、`data_pipeline.phenotype` 旧路径不可导入。

## 分层现状

| 层 | 可用 | 不可用 |
|---|---|---|
| 数据 | 冠心病谱归档 108,833 住院；三模块事件 39,036 住院 / 27,336,811 条 `clinical_event/1.2.0`；1,000 例无损聚合 | 全队列未聚合；15,316 条归一化复核未关 |
| 历史出题 | V1 冻结在 `versions/v1-template-stem/`（221 题）；V2 在 `versions/v2-llm-stem/` + `data_pipeline/archived/phenotype/` | V1 探针非正式评测；V2 134 候选不得送审或发布；根目录 `tasks/` 已删除 |
| 评测重建 | `protocol.yaml` 为 `frozen`（`conditional_order_choice`）；`protocol-lock.json` / `catalog-lock.json` 存在；eligibility 协议冻结（Telemetry = `monitoring_only`）；1,000 例 first-wave corpus（1,011 documents，`methodology_unreviewed`）；POE 按 `chain_root_poe_id` 分组，后来 cancel 不删 create | 无 run-lock；临床 panel 成员表未审；W1 exposure 审计 `previous_exposure=none` 为 0，不能新建 formal val/test；snapshot 仍可能放行 `event_time == index_time`；mining 11 条 FDR 通过，全部不是 gold |

## 仓库整理（文档 / 目录）

- 规范源：根目录 [`文件保存规范.md`](文件保存规范.md)。
- 执行合同现文件名：`docs/plans/20260819_Benchmark-问题复核与实施计划-v3.1-明确执行版.md`。
- 设计文档已改为中文名，见 [`docs/README.md`](docs/README.md)。
- 五类题型设计在 `mcq_generation/`（非正式实现）；visit 级旧抽取规范也收在该目录，不能当现行 event pipeline 合同。

## 下一步

1. 对齐 snapshot 与 query 的时钟（`event_time < index_time` + `evidence_window_basis`）。
2. 完成 1,000 例 integration audit；未 freeze 不得把 W6/W7 或 mining 当作成绩。
3. 不要把 11 条 FDR 规则或 134 道旧候选审成 gold。
4. 新 formal validation/final-test 不能从旧 60/20/20 holdout 升级（`previous_exposure=none` 为 0）。
