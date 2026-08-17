# 检查检验选择任务 — 探索性首版原型（未审阅）

> 状态：`exploratory_unreviewed`。本报告记录一次端到端可运行性探针，不是正式评测产物。
> 未冻结候选目录、未冻结协议、未做人工审阅、未做 FDR/validation。所有 gold 均为"开发数据中实际最可能下单"的行为近似，不冒充规范 gold。

## 1. 目的

跳过人工标注，用已验收的 1000 例结构化事件（`test_1000_0812`），跑通「条件 X → 行为 gold → MCQ 题干」的确定性链路，快速看清：这份数据能否支撑首个"检查检验选择"任务，哪里会卡。

## 2. 实现

- 模块：`evaluation_pipeline/investigation_selection/`（`pipeline.py` + `__main__.py`）
- 输入：`data/test_1000_0812/event_pipeline_output/aggregation/processed_events.parquet`
  （`cleaning/normalization/review` 目录在本环境被 ACL 拒绝访问，但 `processed_events` 已含全部标准化字段）
- 占位参数：`min_condition_support=5`、`max_baseline_share=0.85`（剔除基线占比 >85% 的普适候选）
- 产物：`artifacts/investigation_selection_exploratory/{summary.json, questions.jsonl, gold_patterns.jsonl}`

## 3. 三个比较类与候选目录

| 类 | 来源 event_kind | 候选示例 | 备注 |
|---|---|---|---|
| imaging | `imaging_ordered` | General Xray(773)、CT Scan(439)、Ultrasound(196)、MRI(131)、Nuclear Med(80) | 名字干净，信号最好 |
| clinical_order | `clinical_ordered`（`clinical_order` 白名单） | Telemetry(714)、Blood tests(481)、ECG(373)、Echo(358) | 已剔除 Vitals/Monitoring(996/1000 普适) |
| laboratory | `laboratory_resulted`（结果代理下单） | 面板化验（Potassium 929 等）+ 差异化验（Troponin T 509、PT 733 等） | 见第 5 节问题 |

## 4. 结果：行为 gold 信号质量

### 4.1 影像类 — 信号真实、临床合理

| 条件 | 最可能影像 | share | selectivity |
|---|---|---|---|
| chest pain (n=103) | General Xray | 0.87 | 1.12 |
| dyspnea (n=51) | General Xray | 0.98 | 1.26 |
| fall (n=24) | CT Scan | 0.92 | 2.07 |
| sdh (n=6) | CT Scan | 1.00 | 2.26 |
| bright red blood per rectum (n=6) | CT Scan | 0.83 | 1.89 |
| abdominal pain (n=27) | CT Scan | 0.70 | 1.59 |

胸痛/气促→胸片、跌倒/硬膜下血肿→CT、消化道出血→CT，均符合临床常识。

### 4.2 临床监护类 — 可用但偏"胸痛→Telemetry"主导

剔除 Vitals/Monitoring 后，chest pain→Telemetry(0.93)、gi bleed/sdh→Blood tests(1.00) 合理；但 Telemetry 在冠心病谱队列中过于普遍，导致多个条件都落到 Telemetry，区分度有限。

### 4.3 化验类 — 改为 panel + 选择性，出真信号但也暴露假阳性

首版按"最可能"在化验类退化（普适面板污染），故改为：507 个化验归入 ~16 个临床 panel，候选=panel，gold=**选择性最高**（lift）的 panel（`behavioral_most_selective_panel`）。

| 条件 | 最相关 panel | share | selectivity | 临床合理性 |
|---|---|---|---|---|
| chest pain (n=106) | cardiac_markers | 0.84 | 1.58 | ✓ 心肌标志物 |
| nstemi (n=7) | cardiac_markers | 1.00 | 1.88 | ✓ |
| abdominal pain (n=30) | pancreatic | 0.30 | 2.66 | ✓ 胰酶 |
| nausea/vomiting (n=7) | pancreatic | 0.57 | 5.07 | ✓ |
| bright red blood per rectum (n=13) | coagulation | 0.92 | 1.25 | ✓ |
| hemoptysis (n=5) | coagulation | 1.00 | 1.35 | ✓ |

假阳性（稀有 panel + 小样本被 lift 放大）：`altered mental status→thyroid`、`syncope→thyroid`、`dizziness/dyspnea/weakness→iron_studies`、`fever→toxicology`。这些需要协议 `statistical_policy` 的 FDR + Wilson 下界 + 最小支持度来滤除。

## 5. 关键发现（首版暴露的问题）

1. **化验下单身份丢失**：POE 的 "Lab" 订单是泛化下单（`order_type="Lab"`、`order_subtype=null`、`content_specificity=category_only`），`poe_detail` 里也没有 "Lab Test" 字段；具体化验名只存在于 `laboratory_resulted`（labevents 结果表）。→ 化验类第一版只能用"结果"代理"下单"，且结果面板近乎人人都有，无法区分"哪个化验"。
2. **普适医嘱/面板污染 gold**：Vitals/Monitoring（99.6%）、BMP/CBC（92%+）、凝血（71%+）都是无区分度的 standing order/panel，直接取"最可能"会被它们占据。
3. **主诉归一化必要**：Chest pain / CHEST PAIN / CP / CHEST PAIN (CARDIAC FEATURES) 需归一化合并；"s/p Fall"→fall、", Transfer" 需剥离。
4. **小样本条件噪声**：`gi bleed`(n=5) 落点与其他消化道出血表达不一致，支持度不足时 gold 不稳。
5. **时间语义仍未解**：ED 分诊事件 `available_time=null`（`triage_no_time_v1`）。首个 `pattern_rule_concordance` 任务用"主诉→随后下单"的天然时序绕开了逐病例时间对齐，但正式冻结前仍需解决。

## 6. 结论与下一步

- **影像类**：信号强、临床合理，可直接出题（19 个 pattern）。
- **临床监护类**：可用，但冠心病谱队列中 Telemetry 过度普遍，区分度有限（21 个 pattern）。
- **化验类**：改用 panel + 选择性后，强信号（心肌标志物/胰酶/凝血）出来了，但低基线稀有 panel 产生假阳性，需 FDR + Wilson 下界 + 最小支持度控制（20 个 pattern）。
- **化验订单身份**：MIMIC-IV POE 的 "Lab" 是泛化下单，`poe_detail` 无 "Lab Test" 字段，具体项目只在 labevents 结果表 → 化验类只能"结果代理下单"，这是数据结构性限制，非代码问题。

**下一步（推荐顺序）**：
1. 实现协议 `statistical_policy`（FDR + Wilson 下界 + 最小条件/候选支持度），把探索性 gold 升级为可过滤假阳性的候选 gold；
2. 在影像 + 临床监护两类先跑模型评测闭环（最快看到模型表现）；
3. 化验类在 FDR 层补齐后纳入；
4. 解决 ED 分诊 `available_time` 与主诉冻结词表。

## 7. 可复现性

生成管线为纯 Python（无 LLM、无随机数），每次运行：
- fail-closed 校验输入 `processed_events.parquet` 的 SHA-256（与 `aggregation_manifest.json` 一致）；
- 输出 `run_manifest.json`，记录输入哈希、全部参数（主诉同义词表、临床白名单、lab panel 映射、阈值）与计数，使每批题可审计。

## 8. 首轮模型评测（DeepSeek，探索性）

- 题目：39 道（影像 17、临床监护 21、化验 1；FDR 后化验类几乎无候选可组 4 选项）。
- 模型：`deepseek-v4-flash`，temperature 0，选项确定性打乱（gold 不恒在 A 位）。
- 结果：**overall accuracy = 0.154**（影像 0.235、临床监护 0.095、化验 0/1），低于随机（25%）。

### 关键发现：行为 gold 在当前粒度是"退化"的，模型分歧恰好暴露了这一点

模型几乎系统性偏离行为 gold，原因是 **gold 捕获的是"冠心病谱队列的常规普适做法"，而不是"判别性决策"**：

- 影像 gold 绝大多数是 `General Xray`（基线 77%，人人拍胸片），而模型回答"chest pain→CT、AMS→CT head"等——这些在临床上更合理，但不符合"最常拍胸片"的行为 gold；
- 临床监护 gold 绝大多数是 `Telemetry`（基线 71%），而模型回答"chest pain→ECG"（临床上 ECG 才是首选）。

结论：低准确率**不是"模型临床能力差"**，而是 `pattern_rule_concordance` 的"最可能下单"语义在**当前 candidate 粒度下被普适医嘱（CXR/Telemetry/BMP）占据**，导致 gold 不具判别性，与模型的临床推理（规范性）系统性分歧。

### 由此得出的方法学修正方向

1. 行为 gold 必须在**判别性粒度**构建：把普适候选（CXR、Telemetry、BMP/CBC）从 comparison class 中显式排除，或改用"最判别（选择性）"作为 gold 语义；
2. 化验类 FDR 后每个条件只剩 1–2 个显著 panel，无法组 4 选项 → 需要更宽的可选 panel 池或合并 panel；
3. 首轮仅 39 题、单一 fast 模型，结论为方向性提示，非正式评测。

## 9. gold 语义对比（likelihood / selectivity / psr / specificity×reliability）

产物按语义命名：`artifacts/investigation_selection_exploratory_gold_{likelihood,selectivity,psr,specificity_reliability}/`。

| 指标 | likelihood | selectivity | psr | specificity×reliability |
|---|---|---|---|---|
| 公式 | share | lift（FDR） | share×lift×rel | lift×rel |
| 题目数 | 39 | 17 | 30 | 30 |
| 总体准确率 | 0.154 | **0.353** | 0.233 | 0.233 |
| 影像 | 0.235 | 0.167 | 0.300 | 0.300 |
| 临床监护 | 0.095 | 0.167 | 0.000 | 0.000 |
| 化验 | 0.0（1题） | **0.800** | 0.400 | 0.400 |

结论：

1. **selectivity（判别性，v2）仍最好**：35.3%、化验 80%。
2. **PSR 与 SR 都回退到 23.3%**，且几乎相同，说明：
   - 去掉 `probability` 项（PSR→SR）只改变极少数 gold（如 chest pain：CXR↔Nuclear Med），而模型两者都不选，故准确率不变；
   - 真正的回退来自 **reliability 项 + Nco_min=10 阈值**：它把 Nco<10 的判别性候选（如 abdominal pain→pancreatic，Nco=9）过滤掉，化验类从 80% 掉到 40%。
   - 论文的 Nco_min=10 是为 1621 万次就诊标定的，对我们 1000 例样本**过严**。
3. 教训：论文思想（特异性 + 可靠性）可参考，但 **阈值需随样本量缩放**；在 1000 例上 selectivity（v2）已足够，reliability 需用更低的 Nco 下限或与 FDR 结合。

## 10. PSR 更适合"诊断类"题目吗？——是，根因是答案空间的 baseline 分布

**是的，PSR 天然更适合诊断类（以及一切"答案空间低先验、高特异性"的题目）。** 判断标准不是题目类型本身，而是**答案空间的 baseline 分布**：

| | 检查检验选择（当前） | 诊断/疾病判别（论文语境） |
|---|---|---|
| 答案空间 | 检查（CXR/Telemetry/BMP） | 疾病（MI/肺栓塞/帕金森） |
| baseline 先验 | **高**（77%/71%/99% 普适） | **低**（单病种罕见） |
| probability 项 Pr(O\|S) | 高 → 污染排名 | 低 → 不起主导 |
| specificity 项 | 低（≈1.1） | 高（5–20）→ 主导 |
| PSR 效果 | 回退到"最可能" | 正常（论文 NDCG 0.906） |

论文 Table 1 的帕金森例子正是"低先验"：Tremor/Bradykinesia 概率仅 0.16–0.23 但 specificity 8.5，PSR 能正确把"翻身困难"排到"头晕"之上。而我们的"胸痛→CXR"概率 0.87、specificity 1.12，probability 项压过一切。

**推论**：到第 2 类"临床诊断"任务时（主诉/检查→最可能诊断），答案=疾病，baseline 天然低，PSR 将直接适用；检查检验选择则用 selectivity（lift）即可。
