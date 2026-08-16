# 临床审核冻结清单（P3 材料）

> 用途：供临床审核一次性裁决并**冻结**所有占位值。冻结后重跑 development → validation → 发布前一次性 final_test 复检（只读、不改参）。
> 每项给出：当前值 / 影响面 / 建议 / 待裁问题。所有产物当前均标记 `exploratory_unreviewed`。

## A. 全局

| 项 | 当前值 | 影响面 | 待裁问题 |
|---|---|---|---|
| 患者级划分比例 | 60/20/20（development/validation/final_test） | 五维全部 | 60/20/20 是否够（validation 偏小时长尾主诉验证不足）；是否需更大 val |
| 主诉归一化 + 垃圾黑名单 | `benchmark_common/conditions.py` | 五维全部 | 缩写词表（c/p→chest pain 等）、垃圾主诉（unknown-cc/单字符）是否完备 |

## B. 检查检验选择（investigation，selectivity）

| 项 | 当前值 | 待裁问题 |
|---|---|---|
| 一线影像白名单 | `{General Xray, CT Scan, Ultrasound}` | MRI/Nuclear Med/介入是否该入一线？ |
| 临床监护白名单 | `{Telemetry, ECG, Echo, Blood tests}` | 是否完整 |
| 化验 panel 映射 | 507 项 → 16 panel | panel 划分是否临床合理（laboratory 类 rank-1 58.5% 是主拖累） |
| 统计阈值 | `min_condition_support=10, max_baseline_share=0.85, min_baseline_share=0.02, min_candidate_support=10, fdr_q=0.10, score_ratio=1.5` | 各阈值是否冻结 |
| 唯一性过滤 | **无**（pipeline.py 未加 min_share_gap） | 是否补 `min_share_gap≈0.10`（与其他维一致）以提升 laboratory 类 |

## C. 临床诊断（diagnosis，PSR）

| 项 | 当前值 | 待裁问题 |
|---|---|---|
| 主诊断定义 | `hosp.diagnoses_icd` seq_num==1（`source_array_index==0`） | 已验证排序，是否接受 |
| 疾病章过滤 | ICD10 A–N；ICD9 001–779 | 是否排除 O/P/Q 孕产（当前已排除） |
| 同义词 + 家族合并 | heart failure/STEMI/sepsis/cerebral infarction 家族合并 | 是否再补（nstemi vs stemi 是否合并为 MI） |
| 共病黑名单 | 慢病 20+ 项（含 UTI） | 是否完备 |
| 症状当答案 | `orthostatic hypotension`、`melena` 仍会作候选 | 是否加症状黑名单 |
| PSR 阈值 | `psr_nco_min=5, psr_p_min=0.005, max_baseline_share=0.15, min_candidate_support=20` | 是否冻结 |
| 两可主诉 | HF vs 肺炎/脓毒症/COPD（4+ 条 discordant） | 是否「允许多 gold」/ 非对称计分 |

## D. 治疗处置（treatment，selectivity）

| 项 | 当前值 | 待裁问题 |
|---|---|---|
| 品类映射 | ~30 类 substring（~78% 覆盖）；RxNorm 精确映射未做 | 是否接受 substring；是否升级 RxNorm/ATC |
| 急性治疗 vs 慢病续方 | **未划分**（T1 仍有 `abnormal mri→vaccine`、`abnormal labs→antigout` 语义错误 gold） | 慢病续方品类（vaccine/antigout/thyroid/sleep_aid/antidepressant）是否从候选剔除 |
| condition 空间 | 含 `abnormal mri/labs/clotted fistula/elevated troponin` 等检验结果 | 是否从主诉空间过滤 |
| 事件分层 | T1/T2/T3 分开 | 是否保持（survey 建议保持，分歧作题目素材） |
| 唯一性过滤 | `min_share_gap=0.10` | 是否冻结 |

## E. 转诊与科室选择（referral，selectivity）

| 项 | 当前值 | 待裁问题 |
|---|---|---|
| SERVICE_MAP | `MED→medicine` 等 18 码（占位） | 码→全称映射是否准确 |
| 唯一性过滤 | `min_share_gap=0.10` | 是否冻结 |
| 相邻科室翻转 | `cardiac medicine ↔ cardiac surgery` 等 | 是否多专科判定 |

## F. 离院指导与随访（discharge，F1 文书轨）

| 项 | 当前值 | 待裁问题 |
|---|---|---|
| 四子轴 | 随访科室 / 随访时间窗（≤1周,1–4周,1–3月,3–12月,3–5年）/ 带药变更 / 红旗症状 | 时间窗离散边界是否合理 |
| 抽取方式 | 出院小结全文（`note.discharge.text`）正则/规则首抽 | 是否需 NER 支路（后续） |
| 规范轨 | 缓行香港阶段 | 确认 |

## 冻结后动作（P4 前置）

1. 临床逐项裁决 → 我改代码阈值/词表（只 dev+val）。
2. 重跑 development → validation → build_validated（四维）。
3. 统一跑 DeepSeek 模型评测（validated rank-1 题集）。
4. 发布前一次性 final_test 复检（只读）。
