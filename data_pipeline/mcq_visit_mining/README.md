# mcq_visit_mining

在 Visit 时间线上按六个家族**分别**挖 X→y。每次只读该家族允许的特征，禁止后验泄漏。不出题。非正式 gold。

必须先有一份完成的时间线目录（`manifest.status=complete`）。本模块**只读**：

- `presentation_facts.jsonl`（X：表现特征）
- `visit_events.parquet`（题型①②③ 的窗口内事件）

**不读** `visit_timelines.jsonl`（那是给人看的嵌套时间线），也不读抽取/标准化里的病历正文。

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.mcq_visit_mining `
  --timeline-dir data\derived\mcq_visit_timeline\random10k_dev20_v1.0.0 `
  --output-dir data\derived\mcq_visit_mining\random10k_dev20_strict_v1.0.0\type1_investigation `
  --family type1_investigation `
  --profile strict `
  --expected-count 10000
```

六个家族请各跑一次、各写一个目录（见运行手册）。不要把诊断、化验结果、处方写进题型①。

`--family all` 会在 `--output-dir` 下建六个子目录顺序跑，仍彼此隔离。

对照策略（不覆盖 `strict` 目录）。门槛在 `compare_*` 档案里已放宽。可复用已有事务：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.mcq_visit_mining `
  --transactions-from data\derived\mcq_visit_mining\random10k_dev20_strict_v1.0.0 `
  --output-dir data\derived\mcq_visit_mining\random10k_dev20_compare_psr_v1.0.0 `
  --family all `
  --profile compare_psr `
  --expected-count 10000
```

`--profile`：`strict`（原 8 门 + 条件概率排序）、`compare_likelihood`、`compare_psr`、`compare_tfidf`、`compare_idf`。调研见 [`docs/literature/mcq-visit-mining-strategies.md`](../../docs/literature/mcq-visit-mining-strategies.md)。
