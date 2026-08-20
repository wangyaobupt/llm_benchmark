# Visit 规则挖掘策略调研（PSR / IDF / TF-IDF）

> 日期：2026-08-20  
> 范围：V3 10k Visit 事务上的**排名语义**，不是检查选择 v3.1 的 formal TF-IDF 实验。  
> 状态：`exploratory_unreviewed`；不取代已跑完的 `strict` lift 目录。

已完成的 `random10k_dev20_strict_v1.0.0` 用 **平滑条件概率排序 + lift≥1.2 等 8 道门**。结果是：高基线答案（胸片、肝素、Medicine、HOME）占 accepted 大头，碎 ICD 诊断/操作过不了门。下面策略用来对照「最可能 / 最特异 / 降权高频」。

## 文献与仓库里已有的定义

| 策略 | 来源 | 公式（落到本仓库计数） | 会推谁靠前 |
|---|---|---|---|
| Likelihood / frequency | V1 `gold_semantics=likelihood`；Li 2020 的 probability | \(P(y\|X)=n_{xy}/n_x\) | 该条件下最常发生的 y（胸片、肝素、内科、回家） |
| Lift / selectivity | 现行 strict；`docs/methods/统计方式.md` | \(\mathrm{lift}=P(y\|X)/P(y)\) | 相对全队列更富集的 y；基线 90% 的项目 lift 上限约 1.1，过不了 1.2 |
| PSR | Li et al. 2020 *Artif. Intell. Med.*；V1 `benchmark_common/task.py` | \(\mathrm{PSR}=P(y\|X)\times\mathrm{lift}\times R\)，\(R=\log_{10}\max(1,1+n_{xy}-n_{\min})+r\) | 既要常见、又要比基线高、又要共现够多。文献 NDCG@10：概率 0.66 / TF-IDF 0.80 / PSR 0.91（10 个病） |
| SR | 同上，去掉概率项 | \(\mathrm{SR}=\mathrm{lift}\times R\) | 更偏特异，不要求高条件概率 |
| IDF | v3.1 计划 §6.2；smooth IDF | \(\mathrm{idf}(y)=\log\frac{N+1}{n_y+1}+1\) | 单独用等于「越罕见越靠前」，噪声大 |
| Binary TF-IDF | 同上；词频取 0/1 | \(\mathrm{tfidf}=(n_{xy}/n_x)\cdot\mathrm{idf}(y)\) | 在条件内仍要出现，但压低人人都有的 y |
| PMI | \(\log\mathrm{lift}\) | 与 lift 单调，不是独立算法 | 与 lift 同序 |

主键：N = 该家族事务数（10,000），\(n_x\) 含条件、\(n_y\) 含答案、\(n_{xy}\) 共现。Visit 内同一 y 只计一次（binary）。

Li 2020：PMID 32143785。仓库 V1 默认 \(n_{\min}=10\)，\(r=1\)，筛选 \(n_{xy}\ge 10\) 且 \(P\ge 0.01\)。

## 和现行 8 道门怎么配合

Strict 的 `min_smoothed_probability=0.60`、`min_lift=1.20`、`min_bootstrap_stability=0.80` 是为「唯一高概率答案」设计的。换策略时这些门会把对照意义抹掉（likelihood 若不降 lift 门，几乎仍是同一批规则）。

本轮 **`compare` 档案**：保留 min 支持（\(n_x\ge 5\)、\(n_{xy}\ge 4\)，PSR 用 \(n_{xy}\ge 10\)）、至少两个可比较 y、排名第一与第二在**该策略分数**上要拉开。放宽：不强制 P≥0.60、lift≥1.20、bootstrap≥0.80、FDR≤0.05。原 `strict` 目录只读，不覆盖。

TF-IDF **不与 lift 相乘**（与 v3.1 计划一致）。IDF 不在 validation 上拟合（这 10k 已全是 development）。

## 本轮落地的对照

对已有 `visit_transactions.jsonl` 重排名（不再扫事件表）：

1. `likelihood` — 排 \(P(y\|X)\)
2. `psr` — Li 2020 PSR
3. `tfidf` — \((n_{xy}/n_x)\cdot\mathrm{idf}(y)\)
4. `idf` — 只按 idf（对照「纯降权高频」有多噪）

输出另开 `data/derived/mcq_visit_mining/random10k_dev20_compare_<strategy>_v1.0.0/`。
