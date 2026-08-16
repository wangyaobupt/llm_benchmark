# 转诊与科室选择（Referral）—— 框架 + 唯一性过滤

行为 gold = **R1 services 团队变更**（`service_changed`，住院场景），gold 语义 selectivity。
依据 `docs/reports/five-dimension-execution-refinement.md` §2.4；**绝不用 LLM 映射诊断→专科**（直接用真实 services 事件）。R2（poe consult，ED）与 R3（transfers，床位噪声）未纳入。

> 状态：**探索性草案**。科室码映射为占位值。final_test 已盲测一次（重构前 gap 0.05：rank-1 66.2% / top-3 84.6%，65/147 checked）。P2 已把唯一性过滤 `min_share_gap` 0.05→0.10。

## 结果（gap 0.10，dev → validation）

| 阶段 | 数值 |
|---|---|
| development 出题 | 115 题 |
| validation rank-1 / top-3 | **68.75% / 87.5%**（48 checked） |
| 验证题集 | 33（rank-1）/ 42（top-3） |

final_test 盲测（重构前 gap 0.05）：66.2% / 84.6%（泛化缺口为正，test 略高于 val）。

## P2 唯一性过滤

`min_share_gap` 扫参（dev→val）：

| gap | n_gold | rank-1 | top-3 |
|---|---:|---:|---:|
| 0.05 | 118 | 66.0% | 88.0% |
| 0.08 | 116 | 67.4% | 87.8% |
| **0.10** | 115 | **68.8%** | 87.5% |
| 0.15 | 115 | 68.8% | 87.5% |

0.10 已捕获增益（survey「多专科合理性 ~10pp」），题量几乎不降，选 0.10。

## 说明

- 科室码 → 全称映射是**占位**（`MED→medicine`、`CMED→cardiac medicine`、`SURG→surgery` 等），待审核冻结。
- 剩余 discordant 多为相邻科室翻转（`cardiac medicine ↔ cardiac surgery`、`trauma ↔ neurosurgery`、`medicine ↔ oncology medicine`）——即调研指出的「多专科合理性 ~10pp」，唯一性过滤已缓解但仍存在。

## 下一步

1. 科室码映射审核冻结；
2. 对相邻科室合理性高的主诉做多专科判定（允许多 gold / 非对称计分）；
3. 规范轨（本地转诊路径）缓行到香港阶段。

## 结构

`src/run.py`（development，含 `--min-share-gap`）、`src/validate.py`（`--role validation|final_test`）、`src/build_validated.py`（筛验证集）、`src/sweep.py`（share-gap 扫参）。复用 `benchmark_common/task.py`。

## 运行

```powershell
.\.venv\Scripts\python.exe tasks/referral/src/run.py
.\.venv\Scripts\python.exe tasks/referral/src/validate.py
.\.venv\Scripts\python.exe tasks/referral/src/build_validated.py
```
