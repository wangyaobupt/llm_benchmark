# 临床诊断（Clinical Diagnosis）评测集构建

本目录集中管理「临床诊断」这一评测任务（给定主诉，最可能的诊断是什么）的全部代码与产物。结构与 `investigation_selection/` 一致，**复用**其患者级划分、主诉归一化、统计与评测基础设施。

> 状态：**探索性草案**。P1-2 已做「诊断归一化家族合并 + 阈值放宽」，题量 38→94、验证通过 12→23；final_test 已盲测一次（重构前 76.9%，13/38 checked，n 偏小）。诊断词表/共病黑名单/「两可」多 gold 仍待临床审核。

## 目录结构

```text
clinical_diagnosis/
├── README.md
├── src/
│   ├── diagnosis.py       # 核心：候选提取、PSR gold、出题、run_diagnosis
│   ├── run_development.py # development 出题
│   ├── run_validation.py  # validation 稳定性验证（--role validation|final_test）
│   ├── build_validated.py # 筛稳定题集
│   └── sweep.py           # 阈值扫参
└── output/
    ├── development/       # 94 题 + gold
    ├── validation/        # 稳定性结果
    └── validated/         # 23（rank-1）/ 26（top-3）题
```

## 与检查检验选择的关键差异

| | 检查检验选择 | 临床诊断 |
|---|---|---|
| 答案空间 | 检查（CXR/CT/化验 panel） | **诊断（疾病）** |
| gold 语义 | selectivity（lift） | **PSR**（概率×特异性×可靠性） |
| 候选来源 | POE 下单 / 化验结果 | `hosp.diagnoses_icd` 主诊断（seq_num==1） |
| 候选先验 | 高（检查普适） | 低（单病种罕见）→ PSR 适用 |

## 诊断候选清洗

- **主诊断**：`hosp.diagnoses_icd` 中 `source_array_index==0`（已验证原始归档按 seq_num 排序，即 seq_num==1 主诊断），一人一条。
- **疾病章过滤**：ICD10 只留 A–N；ICD9 只留 001–779（排除症状 780–799、损伤 800–999、E/V 外因/历史）。
- **共病黑名单**：排除高血压/糖尿病/高脂/冠心病/旧心梗/房颤/慢性肾病/COPD/哮喘/抑郁/甲减/反流/肥胖/痛风/骨质疏松/UTI 等慢病。
- **归一化**（P1-2 新增）：小写 + 去括号限定 + 去 `unspecified/nos/initial episode of care` 等后缀 + 同义词映射 + **家族合并**：
  - 所有 `heart failure` 亚型 → `heart failure`
  - 所有 `st elevation myocardial infarction*` → `stemi`
  - 所有 `sepsis`/`septicemia` → `sepsis`
  - 所有 `cerebral infarction/embolism/occlusion` → `cerebral infarction`
- **症状黑名单**（P3 默认）：`orthostatic hypotension`、`melena` 从候选（答案）空间剔除。

## 结果快照

| 阶段 | 数值 |
|---|---|
| development 出题 | 94 题 |
| validation rank-1 / top-3 | **70.6% / 79.4%**（34 checked） |
| 验证通过题集 | 24（rank-1）/ 27（top-3） |
| DeepSeek（24 题 rank-1） | **95.8%** |
| final_test 盲测（重构前） | 76.9%（13/38 checked，n 偏小） |

**rank-1 验证通过的 23 条**含：`chest pain→nstemi`、`chest pain, dyspnea→heart failure`、`dyspnea→heart failure`、`dyspnea on exertion→heart failure`、`dyspnea, leg swelling→heart failure`、`fever→sepsis`、`abnormal ekg, chest pain→nstemi`、`slurred speech→cerebral infarction`、`stemi→stemi`、`hypotension→sepsis`、`unresponsive→sepsis` 等，全部临床正确。

## gold 语义对比（主诊断候选空间）

| gold 语义 | 公式 | rank-1 | top-3 |
|---|---|---|---|
| **PSR** | 概率×特异性×可靠性 | 最高 | 最高 |
| likelihood（最可能） | 概率 | 45.8% | 60.4% |
| selectivity（最判别） | 特异性 | 13.3% | 13.3% |

主诊断 + PSR 是关键组合；selectivity 因主诊断先验极低、lift 把极稀有疾病顶到最前而剧烈波动。

## 剩余已知问题（待临床审核，P3）

1. **两可主诉**（HF vs 肺炎/脓毒症/COPD、nstemi vs stemi 前壁/下壁）：gold 只选一个，多个正确诊断时需「允许多 gold」或非对称计分。
2. **症状当答案**：`orthostatic hypotension`、`melena` 作为诊断候选仍会出现（ICD 疾病章但实为症状/体征），需症状黑名单。
3. **阈值**：`psr_nco_min=5`（P1-2 放宽）为占位值，待冻结。
4. validation 集 34/94 可验证，长尾主诊断仍验证不足。

## 运行

```powershell
.\.venv\Scripts\python.exe .\tasks\clinical_diagnosis\src\run_development.py
.\.venv\Scripts\python.exe .\tasks\clinical_diagnosis\src\run_validation.py
.\.venv\Scripts\python.exe .\tasks\clinical_diagnosis\src\build_validated.py
# 扫参：.\.venv\Scripts\python.exe .\tasks\clinical_diagnosis\src\sweep.py
```

可复现性同 `investigation_selection/`：输入哈希 fail-closed 校验、划分哈希绑定、run manifest 落盘。
