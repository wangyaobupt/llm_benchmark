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

产物：`visit_events.parquet`、`visit_timelines.jsonl`、`presentation_facts.jsonl`、`summary.json`。不含出院小结原文。
