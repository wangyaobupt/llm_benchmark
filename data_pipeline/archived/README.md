# 已归档数据路线

本目录保存已完成历史数据生产、但不属于当前 admission 清洗主流程的代码：

- `mimic_episode/`：MIMIC 原始表到 Episode/事件 Parquet；
- `parquet_to_jsonl/`：Episode Parquet 到 visit JSONL 和决策快照。

当前活动流程是根目录的 `mimic_raw_archive/` 和 `clean_clinical_archive/`。归档 Episode 为保证历史产物可复现，仍读取活动共享契约 `data_pipeline.mimic_source_catalog`，但活动代码不依赖本目录。

归档入口统一使用：

```powershell
python -m data_pipeline.archived.mimic_episode --help
python -m data_pipeline.archived.parquet_to_jsonl.adapter --help
```
