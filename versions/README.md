# versions/ — 历史出题线（冻结 / 失效）

本目录只保存已经关掉的出题实现，**不是**当前检查选择主线。不要在这里添加新 formal 语义、新 gold 或新统计。

当前重建在 `data_pipeline/investigation_selection/` 与 `evaluation_pipeline/`。题型 2–5 设计仍在 `mcq_generation/`。仓库规范见根目录 [`文件保存规范.md`](../文件保存规范.md)。

根目录曾经有一份可运行的 `tasks/`（V1 五维原型）。那份工作树已移入本目录，并与冻结快照逐文件对过：代码 38 个 `.py`、产物 json/jsonl 与 `v1-template-stem` **哈希一致**。重复的 `versions/tasks/` 已删除，只保留下面两个版本目录。

```text
versions/
├── README.md                 # 本文件
├── v1-template-stem/         # 冻结：模板题干 + 确定性统计 gold（探索基线）
└── v2-llm-stem/              # 失效：phenotype 条件 + LLM 写题干（不得送审）
```

| 目录 | 状态 | 是什么 | 能否当新 gold |
|---|---|---|---|
| `v1-template-stem/` | 冻结，`exploratory_unreviewed` | 五维模板题，validated rank-1 共 221 题；DeepSeek 探针非正式 | 否 |
| `v2-llm-stem/` | 科学失效，仅审计 | 134 候选自动审题通过；时间/split/ICD/Lab 合同未冻结 | 否 |

`benchmark_common/` 仍在仓库根，是 V1 的共享原语；冻结快照里另有一份只读拷贝（`v1-template-stem/src/benchmark_common/`）。

## `v1-template-stem/` — 冻结探索基线

冻结时间 2026-08-16。题干是 `A patient presents … with {主诉}`，不含病例级特征；gold 是 development 上的 selectivity / PSR，零 LLM 出题。离院维无 MCQ。

| 子路径 | 作用 |
|---|---|
| `README.md` / `FREEZE_MANIFEST.json` | 版本说明与核心数字 |
| `src/` | 当时出题代码快照（`benchmark_common` + 五任务 `src/`），只读溯源 |
| `src_sha256.json` | 43 个代码文件的 SHA-256 |
| `artifacts/` | 当时聚类产物（115 个 json/jsonl 等），与冻结清单对应 |
| `artifacts_sha256.json` | 上述产物的 SHA-256 |
| `presentation.html` | 该版汇报页 |
| `unclustered/discharge_followup/` | 冻结时未写入 115 件清单的离院抽取（无 MCQ）；从原 `tasks/` 工作树原样并入 |

V1 的旧患者划分（仅审计，不得当新 formal split）现在在：

`versions/v1-template-stem/artifacts/investigation_selection/output/split/`

`protocol.yaml` 的 `audit_metadata` 仍用历史键名 `tasks/investigation_selection/output/split/split_manifest.json` 记录当时哈希；文件字节在上述 artifacts 路径，不要改 lock 键名。

不要改写本目录去「继续出题」。若要演进，另开新版本目录，不要改冻结快照。

## `v2-llm-stem/` — 失效审计材料

从 V1 派生：规则挖掘 + LLM 只写题干。配套表型代码在 `data_pipeline/archived/phenotype/`。formal 入口拒绝。绿的 `smoke_test.py` 只证明离线夹具能跑，不是正式进展。

| 子路径 | 作用 |
|---|---|
| `README.md` | 失效说明与管线步骤 |
| `mcq/` | 当时生成/校验/审题代码 |
| `tests/` | 该包的离线测试 |
| `smoke_test.py` | FakeClient 冒烟 |

不要把 134 道旧候选审成 gold，也不要往这个包加新 formal 语义。

## 不要放进这里的东西

- 新检查选择实现 → `data_pipeline/investigation_selection/`
- 正式 snapshot / split / journey → `evaluation_pipeline/`
- 可重复主清洗 → `python -m data_pipeline.<module>`
- pytest 临时目录（`mcq-test-*`）→ 删除，不入库
