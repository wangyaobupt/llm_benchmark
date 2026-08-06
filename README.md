# 医疗数据集评测：MIMIC

本仓库用于管理 MIMIC 数据审计、文本处理和多模态 benchmark 的代码、配置与文档。原始和派生患者数据不进入 Git。

当前指南：

- [MIMIC 全诊疗过程多系统聚合实施方案](docs/clinical_episode_aggregation_plan.md)
- [MIMIC 多模态数据与 Benchmark 建设指南](docs/mimic-multimodal-benchmark-guide.md)
- [MIMIC-IV 3.1 文本字段清单](docs/mimic-iv-3.1-text-field-inventory.md)
- [MIMIC 多模态官方来源研究笔记](research/mimic-multimodal-official-source-notes.md)

工具：

- `scripts/audit_mimic_download.ps1`：读取 CSV 表头并可选核验 `SHA256SUMS.txt`；不会读取或输出患者数据行。
- `scripts/run_mimic_pipeline.ps1`：统一完成 uv 同步、合成测试、真实数据验证、第一阶段提取和全过程就诊聚合。

本地原始数据状态：

- MIMIC-IV 3.1：已下载，SHA-256 33/33 通过；
- MIMIC-III 1.4：已下载，SHA-256 30/30 通过；
- MIMIC-IV-Note 2.2：已下载，SHA-256 5/5 通过；
- MIMIC-IV-ED 2.2：已下载，SHA-256 8/8 通过；
- CXR、ECG、ECHO、Waveform、FHIR：尚未发现。

## 第一阶段提取

项目固定使用 Python 3.12 和 `uv.lock`。本机 Windows 应用程序控制策略禁止从项目盘运行虚拟环境，因此统一入口默认使用受信任环境 `C:\Python312\envs\mimic-benchmark`；其他机器可通过 `-EnvironmentPath` 指定不同位置。

```powershell
.\scripts\run_mimic_pipeline.ps1 -Task sync
.\scripts\run_mimic_pipeline.ps1 -Task test
.\scripts\run_mimic_pipeline.ps1 -Task validate
.\scripts\run_mimic_pipeline.ps1 -Task extract
```

`validate` 只检查第一阶段八个压缩 CSV 是否存在及表头是否与锁定 schema 完全一致，不读取或输出患者数据行。`extract` 默认生成：

- `outputs/stage1/case_index.parquet`
- `outputs/stage1/text_documents.parquet`
- `outputs/stage1/note_details.parquet`
- `outputs/stage1/quality_report.json`

已有输出不会被自动覆盖；只有明确增加 `-Overwrite` 才会重新生成。

Parquet 的物理行顺序不属于输出契约。下游任务如需稳定顺序，必须在查询中对业务键显式使用 `ORDER BY`，不能依赖文件中的自然行序。

## 全过程就诊聚合

全过程聚合覆盖 MIMIC-IV 3.1、MIMIC-IV-ED 2.2 和 MIMIC-IV-Note 2.2 的 41 张源表。住院使用 `H:<hadm_id>`；没有有效住院关联的急诊使用 `E:<stay_id>`。急诊后入院合并进同一个住院 episode，急诊、住院、ICU 与转科接触仍分别保留。

```powershell
.\scripts\run_mimic_pipeline.ps1 -Task validate-episodes
.\scripts\run_mimic_pipeline.ps1 -Task aggregate-episodes
.\scripts\run_mimic_pipeline.ps1 -Task export-episode `
    -EpisodeId 'H:12345678' `
    -Destination 'outputs/cases/H-12345678.json'
```

`validate-episodes` 只核对 41 张表是否存在及表头是否与锁定 schema 一致。本机统一脚本将 `aggregate-episodes` 和 `export-episode` 的默认聚合目录设为 `G:\Projects\医疗数据集评测-MIMIC\outputs\episodes`；代码与运行入口仍位于 D 盘。底层 Python CLI 的 `--output-dir` 可在其他机器上显式指定。聚合生成：

- `episode_index.parquet`：就诊主索引；
- `care_contacts.parquet`：急诊、住院、ICU、转科接触；
- `timeline_events.parquet`：跨系统临床事件；
- `event_items.parquet`：检查、化验、医嘱、用药等事件的原始明细；
- `documents.parquet`：放射报告、出院小结及可用时间；
- `evidence_links.parquet`：事件或文书到原始行/文本位置的证据锚点；
- `patient_history_refs.parquet`：不设固定期限的患者既往资料窗口；
- `episode_coverage.parquet`：资料覆盖情况，不据此删除病例；
- `unresolved_events.parquet`：无法唯一归入某次就诊的事件；
- `quality_report.json`：仅含汇总计数和硬性质量检查结果。

聚合采用“两阶段落盘”：逐张解压源表并转为临时 Parquet，关闭原始读取连接后再做跨系统关联。原因是压缩 CSV 的解压缓冲会随同时打开的表数叠加；分阶段可限制内存占用，也让全量运行不依赖一次性装入所有源表。

每张 CSV 在单线程顺序读取时附加物理源行号。它只用于构造稳定且唯一的 `item_event_id`，不会替换原始业务键；因此即使两条原始记录内容完全相同，也会作为两个独立明细保留。ICU `chartevents` 按“同一 ICU stay + 同一 `charttime`”形成一个事件组，组内全部原始行进入 `event_items`。

质量报告区分两类检查：episode/contact/患者一致性使用输出回读精确统计；事件与 item 唯一性、item 父事件和 evidence 父目标由构造规则保证，并在 `quality_validation_basis` 中记录依据。这样避免在数亿行正式输出上重复执行同等规模的全表哈希连接。

`export-episode` 才会按需生成病例 JSON。JSON 将 `available_time < episode_start_time` 的全部既往资料放在 `prior_context`，本次就诊内容放在 `current_episode`，两者不混合。

## 数据安全

- 不提交原始 CSV、影像、波形、Parquet、DuckDB 或病例输出；
- 不把 MIMIC 患者级内容发送到普通在线 LLM/API；
- 公开成果只包含代码、配置、字段定义、汇总结果和合规文档。
