# scripts/ — 一次性工具入口

本目录放仓库根下的一次性审计、冻结、抽取和路径修补脚本。它们不是库，也不是数据层主流程。

可重复的管线入口是 `python -m data_pipeline.<module>`。正式 snapshot / split / journey 走 `evaluation_pipeline/`。新脚本落这里之前先看根目录 [`文件保存规范.md`](../文件保存规范.md)。

约定：

- 一律在仓库根目录调用。
- Python 用仓库 venv：`.\.venv\Scripts\python.exe scripts\<name>.py`。
- 患者级 JSON / 模型原文不得提交；写出 `docs/reports/hadm-*.json` 的抽取脚本只供本机对照。
- `_*.py` 是临时调试，用完删除，不长期留。
- 若干脚本写死了 `data/test_1000_0812`、`data/phenotype` 或 `G:\...` 全队列路径。本轮不搬这些数据路径；改默认值需另开任务。

## 协议冻结与失效门禁

| 脚本 | 作用 | 产物 |
|---|---|---|
| `freeze_w1_protocol.py` | 校验 `protocol.yaml` 并写出 W1 protocol lock | `config/investigation-selection/protocol-lock.json` |
| `freeze_decision_contract.py` | 刷新审计哈希并写出 catalog lock | `config/investigation-selection/catalog-lock.json` |
| `build_legacy_invalidation_manifest.py` | 汇总旧 V2 / 旧 split 的 ID 与哈希，供 formal 入口拒绝 | `docs/legacy-invalidation-manifest.json` |
| `build_w1_exposure_registry.py` | 按已批准来源建 W1 exposure registry 与新患者划分 | `data/derived/investigation_selection/w1/`（本地） |
| `run_final_test_rehearsal.py` | W10 final-test **合成夹具**预演，不碰真实 holdout | 打印 rehearsal manifest |

```powershell
.\.venv\Scripts\python.exe scripts\freeze_w1_protocol.py
.\.venv\Scripts\python.exe scripts\freeze_decision_contract.py
.\.venv\Scripts\python.exe scripts\run_final_test_rehearsal.py
```

`build_w1_exposure_registry.py` 会读冻结快照里的旧 `versions/v1-template-stem/artifacts/.../subject_split.parquet` 和本机全队列 `normalized_events.parquet`，需要那些文件在场才跑。该旧 split 只作 exposure 审计，不是新 formal 划分。

## 探索性 gold 审计（非正式）

E1–E4 只记录覆盖、歧义和可行性，**不创建正式 split，也不产生临床 gold**。编排器明确 exploratory-only，不跑 official final-test，也不做 git 操作。

| 脚本 | 作用 |
|---|---|
| `run_exploratory_gold_workflow.py` | 串联 E1–E4，写 run manifest，更新进度仪表盘 |
| `exploratory_source_audit.py` | E1：归一化源覆盖与歧义 |
| `exploratory_gold_definition_audit.py` | E2：EHR 可观察 gold 定义成分 |
| `exploratory_gold_coverage_audit.py` | E3：覆盖、唯一性、时间泄漏 |
| `exploratory_method_feasibility_audit.py` | E4：frequency / lift / TF-IDF 等能否 freeze（读 E2+E3） |

```powershell
.\.venv\Scripts\python.exe scripts\run_exploratory_gold_workflow.py `
  --source-root <normalization_dir> `
  --output-dir <audit_out>
```

历史报告在 `docs/reports/e1-*-e5-*`。结论是旧链迁不了，不能把这些数字当新成绩。

## 检查选择诊断（1,000 例）

| 脚本 | 作用 |
|---|---|
| `audit_poe_subtypes_1000.py` | `order_type × subtype` 频数，供 eligibility 审核 |
| `diagnose_mining.py` | 打印 1,000 例 corpus 的 split / family / 规则门槛 |
| `summarize_mining.py` | 打印 `mined_rules.parquet` 的 lift 排序 |

默认读 `data/test_1000_0812/...` 或 `data/derived/investigation_timepoint/corpus_1000/`。打印结果不是 gold；现行合同要求 integration audit 通过前不得把 mining 当成绩。

## 数据层抽查

| 脚本 | 作用 |
|---|---|
| `audit_mimic_download.ps1` | 核对 PhysioNet 下载：文件数、体积、可选 SHA-256 |
| `audit_normalization_loss_sample.py` | 抽 50 例住院，报告归一化事件丢掉的源字段（只写清单，不写原文） |
| `extract_normalized_hadm.py` | 把一次住院的全部 normalized events 抽成 JSON |
| `extract_aggregated_hadm.py` | 从 aggregation 三份 Parquet 抽一次住院的完整可追溯样本 |

```powershell
.\scripts\audit_mimic_download.ps1 -DatasetPath data\RawData -VerifyHashes
.\.venv\Scripts\python.exe scripts\extract_aggregated_hadm.py `
  --aggregation-dir data\test_1000_0812\event_pipeline_output\aggregation `
  --hadm-id 28234402 `
  --output docs\reports\hadm-28234402-event-aggregated.json
```

`hadm-*.json` 已被 gitignore。不要把患者级样本提交进仓库。

## 文本 NER 运行包装

| 脚本 | 作用 |
|---|---|
| `Run-TextNerV2.ps1` | v2：prepare / mentions / relations / compile；默认读写 `data/test_1000_0812` 与 `data/ner_v2_v2` |
| `Run-TextNerMentionSmoke.ps1` | v1 mention 冒烟；未授权外传临床文本会直接失败 |

外传临床文本必须显式确认（`-ConfirmExternalDataTransfer` 或 `-ValidateOnly`）。步骤说明见 `docs/guides/text-ner-v2-runbook.md`。

## 进度仪表盘

`benchmark_progress.py` 读写 `docs/benchmark-progress.json` / `.html`，可 `update` 某一 W 阶段或 `serve` 本机页面（默认端口 8767）。这是执行进度看板，不是科学协议。

## 已完成的路径修补（不要再跑）

`fixup_tasks_paths.py`、`fixup_readme_paths.py`、`fixup_docs_paths.py` 是把五维任务搬进 `tasks/` 之后的一次性改写。使命已完成，留作审计，重新执行会重复改路径。

## 不要放进这里的东西

- 主清洗 / 检查选择实现 → `data_pipeline/` 对应模块
- 正式 snapshot / split / journey → `evaluation_pipeline/`
- 设计、计划、验收报告 → `docs/`
- 可重复模块入口 → `python -m ...`，不要为同一功能再写一份 `scripts/` 包装
