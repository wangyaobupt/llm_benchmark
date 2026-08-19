# v2 临床审核冻结清单（待裁决）

> 本清单把 v2 phenotype 层 + mining 层的**全部占位阈值/词表**列出，供临床 reviewer 逐项裁决。
> 裁决方式：在「裁决」栏写 `确认` 或「改为 <新值> + 理由」；完成后我据此冻结进 config 并重跑。
> 状态：`exploratory_unreviewed`，以下所有值均为占位，尚未冻结。

## A. 规则挖掘 8 道统计门槛（`mcq/config/thresholds.yaml`）

| 参数 | 当前 exploratory 值 | 当前 formal 值 | 含义 | 裁决 |
|---|---|---|---|---|
| min_x_support | 10 | 5 | 条件组合最少支持住院数 | |
| min_xy_support | 4 | 4 | 条件与目标检查最少共现数 | |
| min_smoothed_probability | 0.05 | 0.60 | 最低平滑条件概率 | |
| min_lift | 1.0 | 1.20 | 相对基线最低提升 | |
| min_wilson_lower | 0.02 | 0.35 | 95% Wilson 区间下界 | |
| max_fdr_q | 0.10 | 0.05 | 最大 FDR q 值 | |
| min_bootstrap_stability | 0.50 | 0.80 | bootstrap 第一名稳定性 | |
| min_probability_gap | 0.10 | 0.15 | 与第二名最低概率差 | |
| min_score_ratio | 1.25 | 1.25 | 与第二名最低 score 比 | |
| min_conditions / max_conditions | 1 / 4 | 2 / 4 | 条件特征数范围 | |

> 关键背景：exploratory 档全量跑出 20,904 条 accepted（imaging 20,895 / laboratory 9 / clinical_order 0）；
> formal 档（更严）正在后台重跑。clinical_order 几乎不出题，疑似其候选（Telemetry/ECG/Echo/Blood tests 等）基线占比过高 → lift 上不去，需临床裁决候选空间。

## B. 生命体征阈值（`data_pipeline/archived/phenotype/config/vital_flag_rules.yaml`）

| 标志 | 来源 | 当前阈值 | 裁决 |
|---|---|---|---|
| tachycardia | Heart rate | > 100 /min | |
| bradycardia | Heart rate | < 60 /min | |
| fever | Temperature | ≥ 38.0 °C | ≥ 37.0 °C |
| hypothermia | Temperature | < 35.0 °C | |
| hypoxia | O2 saturation | < 92 % | |
| tachypnea | Respiratory rate | > 20 /min | |
| bradypnea | Respiratory rate | < 12 /min | |
| hypotension | SBP | < 90 mmHg | |
| hypertension | SBP | ≥ 140 mmHg | |

## C. 既往史 ICD 词表（`data_pipeline/archived/phenotype/past_condition.py`）

| 项 | 当前值 | 裁决 |
|---|---|---|
| 历史前缀（ICD-10 Z-code） | `z8`、`z9`（Z80-Z99 个人/家族史） | |
| 慢性病关键词 | diabetes, hypertension, copd, asthma, heart failure, chronic kidney/renal failure, atrial fibrillation, coronary artery, hyperlipidemia, hypothyroid, gout, osteoporosis, epilepsy, cirrhosis, depression, anxiety, obesity, stroke/cerebrovascular, peripheral vascular | |

## D. 候选/比较类白名单（`mcq/catalog.py`，沿用 v1）

| 类 | 答案空间 | 裁决 |
|---|---|---|
| imaging | General Xray / CT Scan / Ultrasound（一线） | |
| clinical_order | Telemetry / ECG / Echo / Vitals/Monitoring / Blood tests | |
| laboratory | 16 个 panel（LAB_PANEL_MAP） | |
| 化验 panel 映射 | `lab_panels.py` 的 LAB_PANEL_MAP | |

## E. 既往史/体征 NER 归一化词表（`past_condition.py`）

| 项 | 当前值 | 裁决 |
|---|---|---|
| 缩写归一化 | CAD/CHF/HTN/DM/PNA/COPD/CKD/AF/MI/OSA/GERD/PE/DVT/TIA/CVA/ESRD/PAD/BPH 等 | |
| 历史前缀剥离 | "PMHx of "/"PMH of "/"h/o "/"history of "/"hx of " | |
