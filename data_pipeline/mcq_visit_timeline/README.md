# mcq_visit_timeline

把时间点补齐时钟和标准化名称合成一次住院事件时间线。不覆盖抽取 / 补齐 / 标准化目录。非正式 gold。

计划：[`docs/design/20260820_出题Visit时间线合并与规则挖掘计划-1万例全量.md`](../../docs/design/20260820_出题Visit时间线合并与规则挖掘计划-1万例全量.md)

运行手册：[`docs/guides/mcq-visit-timeline-mining.md`](../../docs/guides/mcq-visit-timeline-mining.md)

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.mcq_visit_timeline `
  --times data\derived\mcq_visit_extract\random10k_dev20_times\visits.json `
  --standardized data\derived\mcq_visit_standardize\random10k_dev20_v1.0.9\visits_standardized.json `
  --extract-manifest data\derived\mcq_visit_extract\random10k_dev20\manifest.json `
  --output-dir data\derived\mcq_visit_timeline\random10k_dev20_v1.0.0 `
  --expected-count 10000
```

100 例烟测加 `--limit 100 --expected-count 100 --skip-fingerprint`，并换 output-dir。

产物（三种读法，不要混）：

| 文件 | 读法 |
|---|---|
| `visit_timelines.jsonl` | 时间线总览：一行一次住院 + `events[]`。给人抽查。挖掘不读。 |
| `visit_events.parquet` | 事件表：一行一事件。挖掘读。 |
| `presentation_facts.jsonl` | 就诊表现（主诉概念、生命体征、诊断名等）。挖掘读。 |
| `summary.json` | 计数，无原文 |

不含出院小结原文。`manifest.status=complete` 后即可进入 `python -m data_pipeline.mcq_visit_mining`。
