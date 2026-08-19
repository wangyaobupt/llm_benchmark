# 诊断：为什么「检查检验选择」当前只能出非常简单的题？

> 依据：`normalized_events_EDA报告.html`（全量 27.3M 事件 EDA）+ `investigation_bottleneck_metrics.json`（本目录补充扫描，复用任务自身的 LAB_PANEL_MAP / 阈值模拟）。
> 结论先行：**不是出题代码的问题，而是「检验医嘱侧类别化 → gold 被迫用全住院结果代理 → 普适 panel 双胞胎占据 rank-1/2 → 唯一性过滤 (min_share_gap=0.10) 大规模杀伤」的级联约束**。能存活下来的只剩「小众主诉 × 经典判别检查」配对——天然简单、题量稀少。

## 一句话机制

题目要「rank-1 与 rank-2 拉开 ≥10pp 且 selectivity≥1.5」；但数据里**所有大主诉的 rank-1/rank-2 都是 BMP/CBC 这对基线 91% 的普适孪生 panel，gap 只有 0.00–0.01**；真正判别的 panel（如 Abd pain→pancreatic, lift 2.88）share 只有 0.3–0.7，永远排不进 rank-1 → 被过滤机制整体抹掉。

## 证据链（按数据流顺序）

### 1. 数据源层：检验「开立」侧无项目内容 —— gold 语义被迫漂移

| 证据 | 数值 | 出处 |
|---|---|---|
| `laboratory_ordered`（POE 检验医嘱）标签 | **99.99% 为空**（969,560/969,587 无项目名） | EDA ② |
| 医嘱内容特异性质量标记 `CATEGORY_ONLY_NO_SPECIFIC_ORDER_CONTENT` | 1,553,458 行 | EDA ⑦ |
| POE→labevents 链接键 | MIMIC-IV 不提供 | 上游限制 |
| 实际 gold 来源 | `laboratory_resulted`（结果侧，全住院化验存在性） | pipeline.py `_lab_panel_orders` |

后果：
- **语义漂移**：「ED 医生开什么检查」变成「整个住院期间做过什么化验」。入院常规、每日重复抽血、ICU 面板全部计入 gold，普适性被系统性放大。
- **时间污染**：无决策时点快照。结果跨全住院（甚至含出院前复查），与「来诊时该查什么」的前瞻语义不符。
- 对比：用药侧没有这个问题（prescriptions 提供项目级 T1 开立轨迹，1.98M 行 87.8% 映射）——检验侧是 MIMIC 结构性短板。

### 2. 分布层：普适 panel 双胞胎锁死 rank-1/2

**项目级覆盖（756 个项目）**：

- 覆盖率 ≥85%：**20 项**；≥50%：25 项 —— 全部是 BMP/CBC 成分（Potassium/Creatinine/Na/Cl/Glucose… 91%+），构成「普适块」。
- 判别带 2–50%：162 项（Troponin、血气、Lipase 等）——真正有信息量的候选。
- <2%：569 项 —— 碎片化长尾，撑不起候选池。

**Panel 级基线（16 panel，任务实际候选粒度）**：

| panel | 住院覆盖 | 结局 |
|---|---|---|
| chemistry_bmp | **91.6%** | 撞 max_baseline_share=0.85 上限，**被排除出候选** |
| cbc_hematology | **91.3%** | 同上 |
| coagulation 72.0% → cardiac_markers 53.5% → liver 49.4% → … → iron_studies 11.4% | 11 个在带内 | 候选池实际只有 11 个 |

### 3. 机制层：唯一性过滤的杀伤力实测（top-25 主诉模拟）

对支撑度最高的 25 个主诉，按任务同款阈值模拟（gap≥0.10、lift≥1.5、share≥0.15）：

**通过率 0/25。** 全部主诉 top1=chemistry_bmp 或 cbc_hematology（share 0.75–1.00，lift 0.82–1.09 ≈ 1），top1−top2 gap 全部 ≤0.01。

判别信号其实存在，但都被压在 rank-3 以下：

| 主诉 | 真实判别 panel | 其 share / lift | 但 rank-1 是 |
|---|---|---|---|
| Chest pain | cardiac_markers | 0.74 / **1.39**（<1.5 阈值） | BMP 0.82 |
| CHEST PAIN（大写串） | cardiac_markers | 0.82 / **1.54**（过阈值！） | BMP 0.84 |
| Abd pain | pancreatic | 0.34 / **2.88** | BMP 0.95 |
| Fever | liver_panel, inflammatory | 0.74 / 1.51；0.55 / 1.51 | CBC 0.98 |
| Altered mental status | blood_gas | 0.53 / 1.46 | BMP 0.95 |
| Dyspnea | blood_gas | 0.46 / 1.28 | BMP 0.96 |

注意两点：① 连「Chest pain→心肌标志物」这种教科书配对，lift 都只有 1.39–1.54（队列本身是 CAD 疾病谱，心肌标志物基线已达 53.5%，抬升空间被挤掉——**队列选择进一步压缩判别度**）；② 同一主诉的大小写/缩写变体（Chest pain / CHEST PAIN / CP）各自成独立 condition，进一步稀释支撑度。

### 4. 题干层：condition 单变量且未术语化

- `symptom_reported`：9,234 个原始 triage 串，**术语映射率仅 9%**；支撑度 ≥10 的仅 **473** 个，≥50 的仅 **97** 个。
- 题干信息只有「A patient presents with {主诉}」——而事件表里已经标准化的 **vitals（98.6% 覆盖，100% 映射）、triage acuity（97.4%）、ED 用药核对（88.1%）、年龄性别** 全部没用上。
- 影像侧只能三选一：一线白名单 {General Xray 76.6%, CT 43.0%, US 17.9%} 是**模态级**；`imaging_reported` 只有文书类型（RR/AR），无部位/项目级内容 → 出不了「哪种 CT/哪个部位 X 光」这类进阶题。
- 临床监护类 allowlist 里 Vitals/Monitoring 覆盖 99.1%（又一个普适项），Echo/ECG 37%——5 个候选里 1 个是噪声，该类 DeepSeek 准确率仅 19%（gold 语义最可疑的一类）。

## 问题定位总结（按可改空间排序）

| 层 | 问题 | 性质 | 可改空间 |
|---|---|---|---|
| 统计机制 | rank-1 唯一性要求撞上普适双胞胎；selectivity 阈值对高基线判别对过严 | 对数据分布的合理防御，但把题量逼到枯竭 | ★★★ 改 gold 语义（如「排除普适 panel 后再选 rank-1」「分层出题：模态题/panel 题/项目题」） |
| gold 语义 | 用全住院结果存在性代理「开立决策」，普适性放大 + 时间污染 | 管线被迫为之 | ★★☆ 用 ED 时间窗（edstays 期间/入院 24h）内的 labevents 重建 gold，可显著降低普适基线 |
| 题干信息 | condition 只有未映射的主诉串 | 管线选择（数据已具备） | ★★★ 接入 vitals/acuity/年龄/既往用药，主诉先术语归一（9%→目标 >80%） |
| 粒度 | panel 折叠（16）与模态级影像（3）天花板低 | 折叠是被迫的（项目级更碎） | ★★☆ 判别带 162 项里挑「有临床决策语义的项目级候选」（Troponin/D-dimer/lactate…），配合小众主诉出中阶题 |
| 数据源 | POE 检验医嘱无项目内容、无 order→result 链接、ED 无自有检验表 | MIMIC-IV 结构性限制 | ★☆☆ 不可改源，只能换 gold 语义绕开 |
| 队列 | CAD 疾病谱把 cardiac_markers 基线推到 53.5%，胸痛题判别度被吃掉 | 队列定义使然 | ★☆☆ 泛化队列或按基线分层调阈值 |

## 建议的最小验证实验（按 ROI）

1. **ED 时间窗 gold**：把 `laboratory_resulted` 限制在 edstays/intime → +24h 窗口内重算 panel 基线与 gap——预期 BMP/CBC 基线显著下降，更多主诉通过 gap 过滤（只改 gold 构造，不动阈值）。
2. **去普适 rank**：候选池剔除 coverage>85% 的 panel 后重跑 selectivity——pancreatic/liver/blood_gas 等中游 panel 升为 rank-1，Abd pain/Fever/AMS 类主诉立即解锁。
3. **主诉术语化 + 加条件变量**：主诉归并（大小写/缩写/组合串拆分）后支撑度 ≥50 的 condition 预计从 97 → 150+；再叠加 acuity/vitals 分层可出「不稳定患者」类进阶题。
