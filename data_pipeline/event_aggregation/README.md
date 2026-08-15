# 事件无损聚合

本模块把已通过验收的 `normalized_events.parquet` 与 manifest 声明的临床可读、原始 JSONL 重新连接，解决事件化过程只保留文档元数据、遗漏 note 正文和 hosp comments 的问题。本步骤不执行 NER。

## 输出

默认输出到 `INPUT/event_pipeline_output/aggregation`：

- `processed_events.parquet`：保留全部标准化事件字段，并增加五类可用于后续文本处理的完整 `source_text`；不嵌入完整原始行。
- `raw_source_records.parquet`：按 JSONL 行、模块、表和数组下标保存每个源行一次，同时保留临床可读行及其原始行。
- `traceable_events.parquet`：在处理后事件上嵌入对应的临床可读源行和原始源行，供直接审计。
- `aggregation_manifest.json`：输入、输出、哈希、文本字段范围和大小。
- `quality_report.json`：事件数、住院数、源记录数、各来源文本覆盖及不可变性检查。

三份 Parquet 通过 `source_record_id` 连接。`supporting_source_record_ids` 保存支持行的去重引用，不把支持行重复嵌入每条事件。

`source_text` 保留源字符，不做空白折叠或改写，以免破坏后续 NER 的字符位置；清洗和标准化结果仍由原事件字段表达。当前明确的自由文本范围为：

- `hosp.labevents.comments`
- `hosp.microbiologyevents.comments`
- `ed.triage.chiefcomplaint`
- `note.radiology.text`
- `note.discharge.text`

完整源行中的其他字段不会丢失，统一保存在 `clinical_readable_record_json` 和 `raw_record_json`。

## 运行

在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.event_aggregation `
  data\test_1000_0812
```

显式指定目录和批大小：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.event_aggregation `
  data\test_1000_0812 `
  --output-dir data\test_1000_0812\event_pipeline_output\aggregation `
  --batch-size 5000
```

输出目录已经存在、源文件哈希不匹配、`raw_row_ref` 无法定位、源/原始 JSONL 不对齐或任何计数变化时，程序直接失败，不发布不完整目录。

## 验证

```powershell
.\.venv\Scripts\python.exe -m unittest -v tests.test_event_aggregation
```
