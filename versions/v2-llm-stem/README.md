# v2-llm-stem — 历史 v2 题型1（检查检验选择）MCQ 生成管线

> 本目录的旧 phenotype/V2 产物已由 W0 整体失效。它只保留作审计和测试材料；不得送审、发布或作为新统计基线。新管线必须遵循 [`docs/plans/20260819_Benchmark-问题复核与实施计划.md`](../../docs/plans/20260819_Benchmark-问题复核与实施计划.md) 的 `decision_document` 合同。表型代码在 `data_pipeline/archived/phenotype/`。

> 从 v1（`versions/v1-template-stem`）派生的 v2 实现，严格遵循
> `mcq_generation/MCQ 出题逻辑.md` 的出题决策链：

> **统计定答案 → 程序锁选项 → LLM 只写题干 → 三道门禁才进 gold。**

## 1. v2 相对 v1 新增了什么

| 环节 | v1（模板题干） | v2（本实现） |
|---|---|---|
| 统计定答案 | selectivity/PSR，单类候选 | 8 道硬门槛 + 规则 Schema（lift/Wilson/Fisher/FDR/bootstrap/score_ratio） |
| 选项 | 取「前 3 个非 gold」、gold 恒在 A | 3 干扰项（同家族优先 + 就诊数接近）+ `sha256(rule_id)` 循环 A-D 锁定 |
| 题干 | f-string 模板、零 LLM | LLM 只返回 `stem`+`rationale`（JSON response mode、temperature=0、5 次重试） |
| 程序校验 | 无 | 12 条确定性检查（答案泄漏/语义漂移/隐私/CJK/源文本重合…） |
| 自动审题 | 无 | 独立请求 + 独立 prompt，10 项布尔裁定 + accept/reject/revise |
| 人工审核 | 全部 `exploratory_unreviewed` | 只有 `candidate_passed` 进入 `human_review_queue.csv` |
| Gold 导出 | 无 | fail-closed：源规则 accepted + 校验通过 + 审题通过 + 人工 approved + 非 exploratory |

## 2. 目录结构

```text
versions/v2-llm-stem/
├── README.md               # 本文件
├── smoke_test.py           # 离线端到端冒烟（合成数据 + FakeClient，0.05s）
├── mcq/                    # v2 包（自包含；运行时 sys.path 定位仓库根复用 benchmark_common/text_ner）
│   ├── constants.py        # 版本 + 稳定错误码/拒绝码/状态枚举
│   ├── hashing.py          # content-addressed ID（rule_id/question_id/candidate_id/feature_id）
│   ├── validators.py       # 严格 JSON Schema 加载 + validate_strict（禁止额外字段）
│   ├── conditions.py       # 条件特征抽取（复用 benchmark_common 主诉归一化）
│   ├── lab_panels.py       # 化验 panel 映射（沿用 v1 占位，待临床冻结）
│   ├── catalog.py          # 检查目录 InvestigationConcept（家族/粒度/可开立/就诊数）
│   ├── mining.py           # 8 门槛规则挖掘（bootstrap/Fisher/BH-FDR/score）
│   ├── distractors.py      # 3 干扰项选择 + A-D 位置锁定
│   ├── privacy.py          # 禁止字段递归校验 + 文本隐私检查 + 5-gram Jaccard
│   ├── client.py           # 结构化 LLM 客户端（复用 text_ner 传输/门禁）+ FakeStructuredClient
│   ├── generation.py       # LLM 生成 stem+rationale + 组装题目（Stage 6-7）
│   ├── validation.py       # 12 条程序校验（Stage 7）
│   ├── review.py           # 10 项独立自动审题（Stage 8）
│   ├── pipeline.py         # 编排 + 人工队列 + gold 导出 + 产物写入（Stage 9-10）
│   ├── audit.py            # 原子写 + cache key
│   ├── config_loader.py    # thresholds/prompt 加载
│   ├── cli.py              # run-all 命令
│   ├── config/
│   │   ├── thresholds.yaml # formal + exploratory 两档预登记阈值
│   │   ├── api.json        # OpenAI-compatible 配置（MCQ_* 环境变量）
│   │   └── prompts/{generate_stem,review_question}.md
│   └── schemas/            # 6 份严格版本化 JSON Schema
└── tests/                  # 24 个离线测试（FakeClient，不触网）
```

## 3. 出题决策链（对应设计文档 §2/§9）

```text
normalized_events.parquet（事件级）
  ├─ catalog.py       ① 检查目录标准化（3 比较类：imaging/clinical_order/laboratory）
  ├─ conditions.py    ② 条件特征（主诉 → 排序去重症状短语）
  ├─ mining.py        ③ 规则挖掘（8 门槛）→ accepted/rejected
  ├─ distractors.py   ④ 3 干扰项 + A-D 位置（程序确定性锁定）
  ├─ generation.py    ⑤ LLM 生成 stem+rationale（仅两字段）
  ├─ validation.py    ⑥ 12 条程序校验（不过即丢）
  ├─ review.py        ⑦ 10 项独立自动审题 → candidate_passed/rejected
  ├─ pipeline.py      ⑧ 人工队列（candidate_passed）
  └─ export_gold      ⑨ gold fail-closed（非 exploratory + 人工 approved 才发布）
```

## 4. 8 道统计硬门槛（`config/thresholds.yaml`）

| 门槛 | formal | exploratory | 淘汰 |
|---|---:|---:|---|
| min_x_support | 5 | 10 | 条件样本太少 |
| min_xy_support | 4 | 4 | 共现太少 |
| min_smoothed_probability | 0.60 | 0.05 | 条件概率不够高 |
| min_lift | 1.20 | 1.0 | 不比基线好 |
| min_wilson_lower | 0.35 | 0.02 | 小样本区间太宽 |
| max_fdr_q | 0.05 | 0.10 | 多重检验不显著 |
| min_bootstrap_stability | 0.80 | 0.50 | 第一名不稳定 |
| min_probability_gap / min_score_ratio | 0.15 / 1.25 | 0.10 / 1.25 | 与第二名区分度不足 |

统计量：`smoothed_probability=(n_xy+1)/(n_x+2)`、`baseline_probability=(n_y+1)/(n_total+2)`、
`lift=smoothed/baseline`、`wilson_lower`、`fisher_p`（单侧 Fisher exact）、`fdr_q`（BH 校正）、
`bootstrap_stability`（固定种子 bootstrap 下目标独占平滑概率第一名的占比）、
`score = wilson_lower × log2(lift) × log(1+n_xy) × bootstrap_stability`。

`formal` 是设计文档默认严格档（可出 gold）；`exploratory` 是开发宽松档（**只调试，gold 导出被 fail-closed 阻断**）。

## 5. LLM 边界与合规

- 生成模型只返回 `{stem, rationale}`；选项、正确答案、位置全部程序锁定，模型不得改动。
- **payload 只含合成标准化概念名 + 聚合统计量，绝不含 MIMIC 原文**——这是 `deepseek-api-policy.json`
  （`restricted_mimic_api_transfer: blocked`，仅放行 `synthetic`/`public_nonclinical`）的硬约束。
- 真实调用默认关闭：`--execute-api` + `MCQ_API_KEY` + `MCQ_EXTERNAL_API_APPROVED=YES`（或
  `MIMIC_EXTERNAL_API_APPROVED=YES`）缺一即失败；复用 `data_pipeline/text_ner` 的
  OpenAI-compatible 传输、执行门禁、重试与用量审计原语。
- 缓存键覆盖 task type/model/prompt 版本/schema 版本/system prompt/payload/response model/参数。

## 6. 三道门禁

1. **12 条程序校验**（`validation.py`）：长度、`most likely to be selected` 语义、无答案/同义词/选项名泄漏、
   无精确日期/脱敏占位符/关联标识、无 CJK、无后验临床事实、5-gram Jaccard ≤ 0.55、选项恰为 A-D 且唯一非空、
   `options[correct_option]==correct_answer`、答案==规则 rank-1、条件特征与来源规则一致。
2. **自动审题**（`review.py`）：独立请求+独立 prompt，10 项布尔（is_investigation_selection /
   uses_rwd_prediction_semantics / single_best_answer / clinically_plausible / safe_priority /
   no_answer_leakage / options_same_granularity / statistically_supported / synthetic_case /
   english_quality）+ recommendation，全 true 且 accept 才 `candidate_passed`，否则 `candidate_rejected`。
3. **人工审核 + gold**（`pipeline.py`）：只有 `candidate_passed` 进队列；gold 需同时满足
   `source rule accepted`、校验通过、`candidate_passed`、人工 `approved`、schema/prompt 版本放行、
   `profile != exploratory`。

## 7. 与设计文档的已知差异（记录在案）

1. **数据源**：设计文档假设 17 列 `rwd_benchmark_visits.csv`；实际输入是事件级 `normalized_events.parquet`
   （v1 已适配）。v2 复用同一事件流，条件特征 = 归一化主诉，候选 = 3 个比较类（imaging/clinical_order/laboratory）。
2. **特征空间**：设计文档 Stage 1 的 age_band/sex/sign/physiologic_flag/past_condition/medication 特征
   依赖上游 standardization 模块（仍缺失）；当前只有 symptom 特征。因此 `formal.min_conditions=2` 在单症状
   条件下会 fail-closed 产出 0 规则，`exploratory.min_conditions=1` 用于开发。
3. **min_smoothed_probability 门槛**：拒绝码沿用设计文档 §7.4 的 `low_conditional_probability`（门槛作用于 smoothed_probability）。
4. **审题布尔数**：设计文档 §7.1 写「9 项」，但 §12.2 Schema 列 10 项布尔；本实现按 §12.2 的 10 项。
5. **bootstrap 单位**：按 admission（hadm_id）重采样；协议中的 subject_id 级 bootstrap 留待协议冻结后升级。
6. **fisher_p**：精确单侧 Fisher exact（对数 gamma 求和）；FDR 用同一 p 值做 BH 校正。

## 8. 如何运行

```powershell
# 离线冒烟（合成数据 + FakeClient，不触网、不读真实数据）
.\.venv\Scripts\python.exe .\versions\v2-llm-stem\smoke_test.py

# 单元/集成测试（24 个，FakeClient 离线）
#   说明：本仓库 .venv 无 pytest；用系统 Anaconda 的 pytest（需禁用插件自动加载绕过沙箱卡顿）：
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD="1"
E:\Anaconda3\python.exe -m pytest versions/v2-llm-stem/tests -q -p no:cacheprovider

# 真实数据 dry-run（不调模型，只用 FakeClient 跑完整链路；需真实 parquet/split 就位）
.\.venv\Scripts\python.exe -m mcq.cli run-all --profile exploratory --out-dir .\versions\v2-llm-stem\output
```

真实调用（会消耗 API 额度，payload 仅合成概念名+聚合统计量）：

```powershell
$env:MCQ_API_KEY="<本地设置>"
$env:MCQ_BASE_URL="https://api.deepseek.com"
$env:MCQ_MODEL="deepseek-v4-flash"
$env:MCQ_MODEL_VERSION="DeepSeek-V4-Flash"
$env:MCQ_PROVIDER="deepseek"
$env:MCQ_EXTERNAL_API_APPROVED="YES"
.\.venv\Scripts\python.exe -m mcq.cli run-all --execute-api --profile exploratory --out-dir .\versions\v2-llm-stem\output
```

## 9. 可复现性

- 输入 `normalized_events.parquet` 的 SHA-256 与 workflow_manifest fail-closed 校验；`subject_split.parquet`
  SHA-256 绑定进 manifest。
- `rule_id`/`question_id`/`candidate_id`/`feature_id` 均为 content-addressed 哈希，相同规则→相同 ID。
- A-D 位置与干扰项顺序由 `sha256` 确定性派生；bootstrap 固定种子（`random_seed` 逐条件派生）。
- 所有主要 JSON/JSONL 原子写入，CSV 用 UTF-8-SIG。

## 10. 状态

`exploratory_unreviewed`。统计阈值、面板映射、白名单、词表均为占位/沿用 v1，尚未经临床审核冻结；
正式 gold 需在 `formal` 档 + 全部门禁通过后产出，当前环境与数据尚不满足（见 `docs/reports/clinical-review-freeze-checklist.md`）。
