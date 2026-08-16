# 执行进度报告 P1–P5（exploratory_unreviewed）

> 全程只在 development + validation 上调参；final_test 仅在重构前的盲测用过一次，重构后**未再触碰**。
> 本文记录本轮 P1-1 → P5 的全部代码变更与量化结果。

## 变更总览

| 项 | 内容 | 影响 |
|---|---|---|
| P1-1 治疗重构 | 修 `soln` 误排除 bug；补 D10W/D30W 载体排除 + 常见药；`min_share_gap` 0.05→0.10 | T3 +8.8pp、T2 +2.5pp、T1 持平 |
| P1-2 诊断扩容 | 归一化家族合并（sepsis/STEMI/cerebral）+ 发作期次后缀清理 + `psr_nco_min` 10→5 | 题量 38→94，验证通过 12→23，rank-1 50%→67.65% |
| P0-1 离院 F1 骨架 | 出院全文抽取（92% 覆盖）+ 随访时间窗首抽 | 建 `src/`；时间窗信号 ~5%（稀疏，符合 survey） |
| P2 唯一性过滤扫参 | referral `min_share_gap` 0.05→0.10 | referral rank-1 66.0%→68.75% |
| P3 冻结材料 | `docs/reports/clinical-review-freeze-checklist.md` | 六组占位值待临床裁决 |
| P4 模型评测 | 全 6 个 validated rank-1 集跑 DeepSeek | 222 题，见下表 |
| P5 文档刷新 | 五维 README 数字对齐当前 | 见各 README |

## 最终 gold 稳定性（dev → validation，60/20/20）

| 任务 | dev 题 | val rank-1 / top-3 | final_test（重构前） | validated rank-1 |
|---|---:|---:|---:|---:|
| 检查 | 295 | 71.0% / 90.1% | 69.3% / 88.6% | 93 |
| 诊断 | 94 | 67.65% / 76.5% | 76.9%（n=13） | 23 |
| 治疗 T1 | 88 | 55.6% / 77.8% | 50.0% | 25 |
| 治疗 T2 | 79 | 64.7% / 88.2% | 54.1% | 22 |
| 治疗 T3 | 55 | 68.4% / 89.5% | 47.1% | 26 |
| 转诊 | 115 | 68.75% / 87.5% | 66.2% / 84.6% | 33 |

## DeepSeek 模型评测（validated rank-1，222 题）

| 任务 | n | 准确率 |
|---|---:|---:|
| 检查（imaging / clinical_order / laboratory） | 93 | 48.4%（72.2% / 23.8% / 38.9%） |
| 诊断 | 23 | **100.0%** |
| 治疗 T1 / T2 / T3 | 25 / 22 / 26 | 60.0% / 81.8% / 73.1% |
| 转诊 | 33 | 60.6% |

## 关键结论

1. **诊断「少而精」最成功**：主诊断 + PSR + 归一化后 23 条验证通过、DeepSeek 100%（高共识教科书题）。
2. **治疗 T3/T2 唯一性过滤见效**：T3 68.4% / T2 64.7%（val），且模型 T2 81.8% / T3 73.1% 相对高。
3. **检查 laboratory/clinical_order 与转诊是剩余短板**：模型准确率 23.8%/38.9%/60.6%，gold 稳定性 60%/84%/68.75%。laboratory 需补唯一性过滤 + panel 粒度审核。
4. **离院 F1 信号稀疏**：出院全文可得（92%），但显式随访时间窗仅 ~5%，完整 F1 需 NER 支路（按 survey 缓行）。

## P3 默认值落地（第二轮，dev+val 调参）

按 `clinical-review-freeze-checklist.md` 的默认建议落地三项，全部改善：

| 变更 | 任务 | gold 稳定性（val rank-1） | 模型准确率 |
|---|---|---|---|
| 检查补 `min_share_gap=0.10` | investigation | 71.0% → **77.1%**（lab 60%→67.4%） | 48.4% → **53.6%** |
| 慢病续方品类剔除（vaccine/sleep_aid/antidepressant/antigout/thyroid/vitamin） | treatment T1/T2 | T1 55.6%→**65.2%**、T2 64.7%→**66.7%** | T1 60%→**66.7%**、T2 81.8%→**87.5%** |
| 诊断症状黑名单（orthostatic hypotension/melena） | diagnosis | 67.65% → **70.6%** | 100%→95.8%（n 23→24） |

T1 的 `abnormal mri→vaccine`、`abnormal labs→antigout` 伪 gold 已消除。题量：检查 295→224、T1/T2 88/79→90/77、诊断 94 不变。

## 待办（超出本轮自主范围）

1. **P3 临床审核冻结**（人）：逐项裁决 `clinical-review-freeze-checklist.md` 剩余占位值（尤其「慢病续方品类是否含 antidiabetic」「condition 空间是否过滤检验结果」）→ 我改代码（只 dev+val）→ 重跑 → 发布前一次性 final_test 复检。
2. **离院 F1 完整四子轴**：接文本 NER/RE 支路。
3. **治疗 T1 残余语义错误**（`abdominal pain, chest pain→antidiabetic` 等）：antidiabetic 未归入慢病续方（胰岛素可急性用），需临床裁决。

## 变更文件

- 代码：`benchmark_common/task.py`（+`min_gold_share`、`run_task` 透传 `min_share_gap/min_gold_share`）、`tasks/treatment/src/run.py`、`tasks/clinical_diagnosis/src/diagnosis.py`、`tasks/referral/src/run.py`、四个 `validate.py`/`run_validation.py`（`--role final_test`）。
- 新增：`tasks/treatment/src/sweep.py`、`tasks/clinical_diagnosis/src/sweep.py`、`tasks/referral/src/sweep.py`、`tasks/discharge_followup/src/{extract_discharge,extract_followup_window}.py`。
- 文档：五维 README + `docs/reports/final-test-blind-evaluation.md` + `docs/reports/clinical-review-freeze-checklist.md` + 本报告。
