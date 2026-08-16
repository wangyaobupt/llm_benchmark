# 检查检验选择（Investigation Selection）评测集构建

本目录集中管理「检查检验选择」这一评测任务的全部代码与产物：从 MIMIC 全量数据里**确定性**地算出"给定主诉，最该做哪个检查"的题目与 gold，并做独立患者验证和模型评测。

> 状态：**探索性草案**。gold 语义、划分比例、词表、阈值均为占位值，待临床审核后冻结。final_test 已盲测一次（rank-1 69.3% / top-3 88.6%，140/295 checked），此后仅保留为发布前一次性复检，不再用于开发调参。DeepSeek 评测（validated rank-1）48.4%。

## 目录结构

```text
investigation_selection/
├── README.md            # 本文件
├── src/                 # 全部代码
│   ├── pipeline.py      # 核心：gold 计算、出题、验证（build_gold/run_split/validate_rules）
│   ├── evaluate.py      # DeepSeek MCQ 评测
│   ├── split.py         # 患者级划分（development/validation/final_test）
│   ├── run_development.py   # 在 development 集上算 gold + 出题
│   ├── run_validation.py    # 在 validation 集上验证规则稳定性（--role validation|final_test）
│   ├── build_validated.py   # 按验证结果筛出稳定题集
│   ├── cli.py           # 1000例小样本的旧版 CLI（历史）
│   └── explore/         # 数据勘察脚本（历史）
└── output/
    ├── split/           # 患者级划分 manifest + parquet
    ├── development/     # 全量 development 集的 gold + 题目 + 评测
    ├── validation/      # validation 稳定性结果
    ├── validated/       # 验证通过的题集 + DeepSeek 评测
    └── gold_semantics_comparison/  # 1000例上 4 种 gold 语义的对比实验
```

## 管线流程（按序）

```text
数据（MIMIC 全量 normalized_events，39,036 住院 / 20,136 患者）
  │  src/split.py
  ▼
患者级划分（development 60% / validation 20% / final_test 20%）
  │  src/run_development.py
  ▼
development 集上算 selectivity gold + 出题（224 题）
  │  src/run_validation.py
  ▼
validation 集上验证规则稳定性（rank-1 77.1% / top-3 95.4%）
  │  src/build_validated.py
  ▼
筛出稳定题集（84 条 rank-1）
  │  src/evaluate.py
  ▼
DeepSeek 模型评测（84 条 rank-1 上 53.6%）
```

final_test（4,027 患者 / 7,727 住院）**已盲测一次**（rank-1 69.3%），此后不再碰。

## 核心方法

### gold 语义：selectivity（特异性 / lift）

```
selectivity = P(候选 | 主诉) / P(候选) = share / baseline_share
```

衡量"该主诉把这个检查的概率抬升了几倍"。经 4 版对比（见 `output/gold_semantics_comparison/`），`selectivity` 最优；PSR（概率×特异性×可靠性）因概率项偏向普适候选而回退，更适合"诊断类"题目（答案=疾病、低先验）。

### 一线白名单

- 影像 gold 只在 `{General Xray, CT Scan, Ultrasound}` 三个**一线**模态里取"最判别"，排除 MRI / Nuclear Med / 介入等次级检查（干扰项仍用全候选池）。这一步把影像类 validation 稳定率从 61.7% 提到 86.7%、模型准确率从 27.6% 提到 65.4%。
- 临床监护白名单：`{Telemetry, ECG, Echo, Blood tests}`。
- 化验：507 项归入 16 个临床 panel（`LAB_PANEL_MAP`），候选=panel。

### 噪声清理

垃圾主诉黑名单（`unknown-cc`/`___`/单字符）+ 缩写归一化（`c/p`→chest pain、`l/r`→left/right 等）。

### 参数（占位，待冻结）

`min_condition_support=10`、`max_baseline_share=0.85`、`min_baseline_share=0.02`、`min_candidate_support=10`、`fdr_q=0.10`、`score_ratio_minimum=1.5`、`min_share_gap=0.10`（唯一性过滤，P3 默认已加，laboratory 类 60%→67.4%）。

## gold 语义对比（1000 例 + DeepSeek）

| 版本 | 公式 | 题目数 | DeepSeek 准确率 |
|---|---|---|---|
| likelihood | 概率（最可能） | 39 | 15.4% |
| **selectivity** | 特异性 lift（FDR） | 17 | **35.3%** |
| psr | 概率×特异性×可靠性 | 30 | 23.3% |
| specificity×reliability | 特异性×可靠性 | 30 | 23.3% |

结论：检查是先验高的普适动作，`selectivity` 能区分"判别性检查"与"普适检查"，最优。

## 结果快照

| 阶段 | 数值 |
|---|---|
| 划分 | dev 12,082 / val 4,027 / test 4,027 患者（23,626 / 7,683 / 7,727 住院） |
| development 出题 | 224 题（影像 93 / 临床 58 / 化验 73） |
| validation rank-1 / top-3 | **77.1% / 95.4%**（影像 79.1% / 临床 91.3% / 化验 67.4%） |
| final_test 盲测 rank-1 / top-3 | 69.3% / 88.6%（重构前） |
| 稳定题集 | 84（rank-1） |
| DeepSeek（flash）84 题 rank-1 | **53.6%**（影像 79.4% / 临床 19.0% / 化验 48.3%） |

## 如何运行

```powershell
.\.venv\Scripts\python.exe .\tasks\investigation_selection\src\split.py              # 划分
.\.venv\Scripts\python.exe .\tasks\investigation_selection\src\run_development.py    # 出题
.\.venv\Scripts\python.exe .\tasks\investigation_selection\src\run_validation.py     # 验证
.\.venv\Scripts\python.exe .\tasks\investigation_selection\src\build_validated.py    # 筛稳定题
.\.venv\Scripts\python.exe .\tasks\investigation_selection\src\evaluate.py           # DeepSeek 评测
```

## 可复现性

- 输入 `normalized_events.parquet` 的 SHA-256 与 workflow_manifest **fail-closed 校验**（漂移即停跑）；
- 划分 `subject_split.parquet` 的 SHA-256 绑定进 run manifest；
- 每次运行输出 `run_manifest.json`（输入哈希 + 划分哈希 + 全部参数 + 计数）；
- 纯 pandas、无随机数、无 LLM 参与生成。

## 待冻结（见 `docs/reports/clinical-review-freeze-checklist.md`）

1. 一线影像白名单 `{CXR, CT, US}` 是否完整。
2. 化验 panel 映射 + 临床监护白名单。
3. 主诉缩写词表 + 垃圾黑名单。
4. 各统计阈值 + 是否补 `min_share_gap`（laboratory 类是主拖累）。
