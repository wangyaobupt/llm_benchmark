# 治疗处置（Treatment）—— 三层行为 gold + 唯一性过滤

行为 gold = 事件分层的「给定主诉，最可能开立/执行/做的治疗」，gold 语义 selectivity。
依据 `docs/reports/five-dimension-execution-refinement.md` §2.3；规范轨（N1 bundle / N2 Beers / N3 MAI）为独立人工轨，未自动化。

> 状态：**探索性草案**。品类映射与阈值仍为占位值。final_test 已盲测一次（rank-1：T1 50.0% / T2 54.1% / T3 47.1%），泛化缺口为五维最大；P1-1 已做「映射修正 + 唯一性过滤 0.10」，治疗类 gold 仍需临床审核重构。

## 事件分层（survey §2.3）

| 层 | 事件 | 语义 |
|---|---|---|
| T1 | `medication_ordered`（POE + prescriptions） | 开立/处方（决策意图） |
| T2 | `medication_administered`（eMAR） | 执行（可识别 held/refused） |
| T3 | `procedure_performed` / `procedure_recorded_post_hoc` | 手术/操作 |

T1/T2 **不合并**：意图 vs 执行语义不同，「开了没给」的分歧本身就是后续规范轨的题目素材。

## 结果（gap 0.10，dev → validation）

| 层 | development 出题 | validation rank-1 / top-3 | 验证题集（rank-1 / top-3） | DeepSeek |
|---|---:|---:|---:|---:|
| T1 开立 | 90 | 65.2% / 84.8% | 30 / 39 | 66.7% |
| T2 执行 | 77 | 66.7% / 91.7% | 24 / 33 | 87.5% |
| T3 手术 | 55 | 68.4% / 89.5% | 26 / 34 | 73.1% |

final_test 盲测（重构前，gap 0.05）：T1 50.0% / T2 54.1% / T3 47.1%。

## P1-1 重构（本次）

1. **修 `soln` 误排除 bug**：`soln` 是剂型词（`Albuterol 0.083% Neb Soln`），不是载体；从 `_NON_TREATMENT` 移除，恢复 albuterol/morphine/ciprofloxacin 等真药。
2. **补 D10W/D30W 载体排除** + 补 ibuprofen/ketorolac/diclofenac/celecoxib/doxepin/amitriptyline/duloxetine/venlafaxine/bupropion/dipyridamole 等常见药。
3. **唯一性过滤 `min_share_gap` 0.05 → 0.10**（survey「多专科合理性 ~10pp」）：T3 58.6%→68.4%、T2 62.2%→64.7%、T1 持平；代价是题量收缩（少而精）。
4. 新增 `min_gold_share` 参数，扫参显示**无效**（伪 gold 不是低份额稀有品类，而是相邻品类翻转），保留默认 0.0。
5. **慢病续方品类剔除**（P3 默认）：`vaccine/sleep_aid/antidepressant/antigout/thyroid/vitamin` 从候选空间剔除 → T1 55.6%→65.2%（+9.6pp），消除 `abnormal mri→vaccine`、`abnormal labs→antigout` 伪 gold。

## 剩余已知问题（待临床审核，P3）

1. **T1 仍有语义错误 gold**：`abnormal mri→vaccine`、`abnormal labs→antigout`、`abdominal pain, chest pain→antidiabetic`。根因是 selectivity 对低基线「慢病续方」品类（vaccine/antigout/thyroid/sleep_aid/antidepressant）过度奖励——这些不是急性治疗，需在品类层划分「急性治疗 vs 慢病续方」。
2. **condition 空间含检验结果**：`abnormal mri` / `abnormal labs` / `clotted fistula` / `elevated troponin` 是检验/事件而非主诉，与主诉题混在同一类，需在主诉黑名单里过滤。
3. **相邻品类翻转**（`renal_replacement↔nutritional_support`、`nitrate↔vasopressor`、`antiemetic↔antacid`）：品类粒度待 RxNorm/ATC 精确映射后审核。
4. 品类映射仍为 substring（~78% 覆盖），RxNorm 精确映射待做（`concept_id` 是 NDC 码，无现成 RxNorm 层级可用）。

## 结构

`src/run.py`（development，含 `--min-share-gap`/`--min-gold-share`）、`src/validate.py`（`--role validation|final_test`）、`src/build_validated.py`（筛验证集）、`src/sweep.py`（share-gap 扫参）。复用 `benchmark_common/task.py`。

## 运行

```powershell
.\.venv\Scripts\python.exe tasks/treatment/src/run.py --layer t1
.\.venv\Scripts\python.exe tasks/treatment/src/validate.py --layer t1
.\.venv\Scripts\python.exe tasks/treatment/src/build_validated.py --layer t1
# 扫参：.\.venv\Scripts\python.exe tasks/treatment/src/sweep.py
```
