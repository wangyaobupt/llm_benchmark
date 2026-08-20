# Visit 时间线合并与分家族规则挖掘：运行指南

仓库根目录执行。Python 3.12。`gold = 0`，产物都是 `exploratory_unreviewed`。本轮不跑 NER、不生成题目。

设计合同：[`docs/design/20260820_出题Visit时间线合并与规则挖掘计划-1万例全量.md`](../design/20260820_出题Visit时间线合并与规则挖掘计划-1万例全量.md)

---

## 0. 先跑单测

```powershell
.\.venv\Scripts\python.exe -m unittest -v tests.test_mcq_visit_timeline tests.test_mcq_visit_mining
```

---

## 1. 时间线合并（先做这一步）

输入只读：

- 时钟：`data/derived/mcq_visit_extract/random10k_dev20_times/visits.json`
- 名称：`data/derived/mcq_visit_standardize/random10k_dev20_v1.0.9/visits_standardized.json`
- 身份（可选但推荐）：`data/derived/mcq_visit_extract/random10k_dev20/manifest.json`

不要把 `--output-dir` 指到上述任一上游目录。

### 1.1 建议先 100 例烟测

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.mcq_visit_timeline `
  --times data\derived\mcq_visit_extract\random10k_dev20_times\visits.json `
  --standardized data\derived\mcq_visit_standardize\random10k_dev20_v1.0.9\visits_standardized.json `
  --extract-manifest data\derived\mcq_visit_extract\random10k_dev20\manifest.json `
  --output-dir data\derived\mcq_visit_timeline\pilot100_dev20_v1.0.0 `
  --expected-count 100 `
  --limit 100 `
  --skip-fingerprint
```

看 `summary.json`：`visits=100`，有 `lab_resulted` / `medication_prescribed`。

### 1.2 正式 10,000 例

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.mcq_visit_timeline `
  --times data\derived\mcq_visit_extract\random10k_dev20_times\visits.json `
  --standardized data\derived\mcq_visit_standardize\random10k_dev20_v1.0.9\visits_standardized.json `
  --extract-manifest data\derived\mcq_visit_extract\random10k_dev20\manifest.json `
  --output-dir data\derived\mcq_visit_timeline\random10k_dev20_v1.0.0 `
  --expected-count 10000
```

约 2.3M 条事件，会扫两份约 1GB 的 JSON，按机器大约十几分钟到一小时。每 200 例打印一行进度。

10k 默认核对冻结 SHA-256。文件换过才加 `--skip-fingerprint`。

同一 `--output-dir` 已 `status=complete` 且身份一致 → 直接结束，不重算。换输入必须换目录。

产物：

| 文件 | 用途 |
|---|---|
| `visit_events.parquet` | 一行一事件，给挖掘用 |
| `visit_timelines.jsonl` | 一行一次住院（无 DS 原文） |
| `presentation_facts.jsonl` | 主诉概念、生命体征、诊断名（挖掘按家族选用） |
| `summary.json` | 计数，无原文 |

---

## 2. 规则挖掘（六个家族分别跑）

每个家族单独命令、单独输出目录。题型① 看不到诊断和化验结果；题型② 的诊断只当 y、不当 X；题型③ 默认不用出院诊断当条件。

配置在 `config/mcq_visit_mining/`（窗口、门槛、生命体征旗标、高信号化验 itemid）。改门槛必须换 output-dir。

### 2.1 烟测（时间线 100 例之后）

把 `--expected-count` 和 `--limit` 都设成 100，换一个 `pilot100` 目录。strict 门槛在 100 例上 accepted 经常是 0，这是正常的，只验证能跑通。

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.mcq_visit_mining `
  --timeline-dir data\derived\mcq_visit_timeline\pilot100_dev20_v1.0.0 `
  --output-dir data\derived\mcq_visit_mining\pilot100_strict_v1.0.0\type1_investigation `
  --config-dir config\mcq_visit_mining `
  --family type1_investigation `
  --profile strict `
  --expected-count 100 `
  --limit 100
```

### 2.2 正式 10,000 例：一次一个家族

时间线目录用 1.2 的产物。**请按这个顺序跑**（先检查选择，后诊断/治疗，避免看串目录）：

```powershell
$tl = "data\derived\mcq_visit_timeline\random10k_dev20_v1.0.0"
$root = "data\derived\mcq_visit_mining\random10k_dev20_strict_v1.0.0"

.\.venv\Scripts\python.exe -m data_pipeline.mcq_visit_mining --timeline-dir $tl --output-dir "$root\type1_investigation" --family type1_investigation --profile strict --expected-count 10000

.\.venv\Scripts\python.exe -m data_pipeline.mcq_visit_mining --timeline-dir $tl --output-dir "$root\type2_diagnosis" --family type2_diagnosis --profile strict --expected-count 10000

.\.venv\Scripts\python.exe -m data_pipeline.mcq_visit_mining --timeline-dir $tl --output-dir "$root\type3_medication" --family type3_medication --profile strict --expected-count 10000

.\.venv\Scripts\python.exe -m data_pipeline.mcq_visit_mining --timeline-dir $tl --output-dir "$root\type3_procedure" --family type3_procedure --profile strict --expected-count 10000

.\.venv\Scripts\python.exe -m data_pipeline.mcq_visit_mining --timeline-dir $tl --output-dir "$root\type4_service" --family type4_service --profile strict --expected-count 10000

.\.venv\Scripts\python.exe -m data_pipeline.mcq_visit_mining --timeline-dir $tl --output-dir "$root\type5_disposition" --family type5_disposition --profile strict --expected-count 10000
```

想一次排队跑完六个（仍然分目录、仍然隔离）：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.mcq_visit_mining `
  --timeline-dir data\derived\mcq_visit_timeline\random10k_dev20_v1.0.0 `
  --output-dir data\derived\mcq_visit_mining\random10k_dev20_strict_v1.0.0 `
  --family all `
  --profile strict `
  --expected-count 10000
```

每个家族的 10k 挖掘可能要数分钟到数十分钟（bootstrap 在候选项上 200 次）。

### 2.3 各家族隔离（合同）

| `--family` | X 允许 | X 禁止 | y | 窗口 |
|---|---|---|---|---|
| `type1_investigation` | 主诉、生命体征旗标、年龄段、性别、入院类型 | 诊断、化验结果、处方、操作、POE `Lab` 类别 | 4h 内影像 exam / ECG 等开单 / 高信号化验 | 就诊原点起 4h |
| `type2_diagnosis` | 表现 + 24h 内可见化验 flag | 诊断不当 X | 出院主诊断（后验标记） | 结果可见 24h |
| `type3_medication` | 表现 + 过敏 | 默认无出院诊断 | 24h 内处方成分 | 24h |
| `type3_procedure` | 同上 | 同上 | 日历日窗口内操作（date 精度） | 24h |
| `type4_service` | 表现 | 默认无诊断 | 主服务 | Visit 级 |
| `type5_disposition` | 表现 | 默认无诊断 | `discharge_location` | Visit 级 |

题型③④⑤ 若要加出院诊断进 X（exploratory），必须**单独**跑该家族并加 `--allow-posthoc-diagnosis`，规则会打 `uses_posthoc_diagnosis`。不要和 `--family all` 一起用。

每个家族产物：`visit_transactions.jsonl`、`conditional_rules.jsonl`、`conditional_rules_rejected.jsonl`、`summary.json`、`report.html`。accepted=0 是合法结果，不要改门槛覆盖同一目录。

---

## 3. 不要做的事

- 不要覆盖 `random10k_dev20`、`random10k_dev20_times`、标准化目录。
- 不要把本产物送进 gold 或出题。
- 不要在 strict 跑次中途改 `config/mcq_visit_mining/thresholds.yaml`。
- 不要 import `investigation_selection` 或旧 phenotype 来挖这 10k。
