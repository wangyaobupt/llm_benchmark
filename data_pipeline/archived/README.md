# 已归档数据路线

本目录保存已完成历史数据生产、但不属于当前 admission 清洗主流程的代码：

- `mimic_episode/`：MIMIC 原始表到 Episode/事件 Parquet；
- `parquet_to_jsonl/`：Episode Parquet 到 visit JSONL 和决策快照；
- `phenotype/`：旧 visit 级 8 类特征与 V2 出题入口。科学合同已失效，仅审计；`data_pipeline.phenotype` 旧路径不可导入，`--profile formal` 仍 fail-closed。

当前活动流程是 `mimic_raw_archive/` → `clean_clinical_archive/` → `event_pipeline/` → `event_aggregation/` → `investigation_selection/`。归档 Episode 为保证历史产物可复现，仍读取活动共享契约 `data_pipeline.mimic_source_catalog`，但活动代码不依赖本目录。

归档入口统一使用：

```powershell
python -m data_pipeline.archived.mimic_episode --help
python -m data_pipeline.archived.parquet_to_jsonl.adapter --help
```
