# MIMIC 数据处理管道总览

本目录有两条并行轨道，**不要串成一条流水线**：

1. **V3 五类题型 Visit 直抽**（当前出题底座）：只读 `data/RawData` 的 CSV.GZ → `mcq_visit_extract` → standardize → timeline → mining。不读住院归档，不读事件 Parquet。
2. **冠心病检查选择**：raw → clean → event → aggregation → `investigation_selection`。文本 NER 只读这条的聚合产物。

`archived/phenotype/` 是已失效的 visit 特征线，旧导入路径不可用，formal 入口拒绝。另有一条已归档的 Episode/visit 路线，不能与上述任一条混为同一顺序流程。

各模块的深度解析见对应目录的 `README.md`，本文件只做全局串联。

## V3 五类题型：从 CSV.GZ 直抽

```text
data/RawData/*.csv.gz（HOSP 3.1 / ED 2.2 / Note 2.2）
        │  mcq_visit_extract     漏斗 + 开发池随机 10k + 规范字段
        ▼
visits.json / visits.csv
        │  backfill_times        用药起止、storetime、chartdate（另目录）
        │  mcq_visit_standardize 术语 / 单位 / 主诉概念
        ▼
visits_standardized.json
        │  mcq_visit_timeline    时钟 + 标准名
        ▼
visit_events.parquet + presentation_facts.jsonl
        │  mcq_visit_mining      --family 一次一个；隔离后验
        ▼
conditional_rules.jsonl     exploratory_unreviewed；不出题
```

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.mcq_visit_extract `
  --data-root data\RawData `
  --output-dir data\derived\mcq_visit_extract\random10k_dev20 `
  --sample-size 10000 `
  --shard-size 1000 `
  --development-percent 20

.\.venv\Scripts\python.exe -m data_pipeline.mcq_visit_extract.backfill_times `
  --extract-dir data\derived\mcq_visit_extract\random10k_dev20 `
  --output-dir data\derived\mcq_visit_extract\random10k_dev20_times `
  --expected-count 10000

.\.venv\Scripts\python.exe -m data_pipeline.mcq_visit_standardize `
  --input data\derived\mcq_visit_extract\random10k_dev20\visits.json `
  --output-dir data\derived\mcq_visit_standardize\random10k_dev20_v1.0.9 `
  --expected-count 10000
```

时间线与六个家族挖掘命令见 [`docs/guides/mcq-visit-timeline-mining.md`](../docs/guides/mcq-visit-timeline-mining.md)。

## 冠心病检查选择主流程

```text
MIMIC-IV 原始 CSV.GZ（39 个锁定文件：HOSP 3.1 / ICU 3.1 / ED 2.2 / Note 2.2）
        │
        │ ① mimic_raw_archive      抽取 + 聚合（原生键连接、DuckDB 分片、可断点续跑）
        ▼
admission 原始 JSONL                          schema: mimic_admission_raw/1.0.0
（一次住院一行；32 张表分模块内嵌、全字符串原值、无派生字段）
        │
        │ ② clean_clinical_archive 字典解码 + POE 时间线（纯标准库、可整体拷走）
        ▼
临床可读 JSONL                                schema: mimic_admission_clinical_readable/1.0.0
（源行追加 *_decoded 释义；新增派生表 hosp.poe_timeline；可逆性自检保证原始内容零改动）
        │
        │ ③ event_pipeline run     事件化 + 确定性归一化 + 双层独立审计 + 复跑门禁 + 原子发布
        ▼
event_pipeline_output/
  ├── cleaning/      cleaned_events.parquet（47 列事件表，一行一事件）等 6 个产物
  ├── normalization/ normalized_events.parquet（8 个归一化字段，其余 39 列逐值不变）等 4 个产物
  ├── quality/       两级验收审计 + 复现报告
  └── workflow_manifest.json（仅全部门禁通过后存在）
        │
        │ ④ event_aggregation      无损聚合：把事件与临床可读/原始 JSONL 重连
        ▼
event_pipeline_output/aggregation/
  ├── processed_events.parquet     事件 + 五类逐字符 source_text（NER/检索分析层）
  ├── raw_source_records.parquet   每个源行恰好一行（source_record_id 存储层）
  └── traceable_events.parquet     事件内嵌完整源行（审计层）
        │
        │ ⑤ investigation_selection  检查选择重建（clock / grouping / snapshot / episodes）
        ▼
decision-document 与 1,000 例 first-wave corpus（`methodology_unreviewed`，不是 gold）；catalog-lock 已生成

旧 `archived/phenotype` + `versions/v2-llm-stem` 已失效，不在本图主链上。

文本支路：text_ner / text_ner_v2 只读取 ④ 的 aggregation 产物
（raw_source_records 提供去重自由文本与血缘，processed_events 提供事件关联），不再回读源 JSONL。出院 NER 一律 post_hoc，不能进 formal 条件。

五类题型不在本图上：见上文 V3 直抽。NER 全量本轮不做。
```

## 模块定位

| 目录 | 站位 | 一句话职责 | 主要输入 | 主要输出 |
|---|---|---|---|---|
| `mimic_raw_archive/` | ① | 把 39 个锁定 CSV.GZ 聚合为「一次住院一行」的原始 JSONL；内容指纹绑定、可断点续跑 | MIMIC CSV.GZ | `mimic_admission_raw/1.0.0` JSONL |
| `clean_clinical_archive/` | ② | 五份官方字典追加式解码 + POE 医嘱时间线重建；纯 Python 3.12 标准库、可整体拷走 | ① 的 JSONL | `mimic_admission_clinical_readable/1.0.0` JSONL + 报告 |
| `event_pipeline/` | ③ | 33 张登记表事件化（21 fact owner + 6 support + 6 context）+ 冻结规则归一化；独立审计、复跑 SHA-256 对比、原子发布 | ② 的 JSONL（+① 的 raw JSONL 供审计） | cleaning/normalization/quality Parquet + workflow manifest |
| `event_aggregation/` | ④ | 把已验收事件与两份源 JSONL 无损重连：五类逐字符 source_text + 每源行唯一 `source_record_id` | ③ 的已验收产物 + 两份 JSONL | aggregation/ 三份 Parquet + 两份 JSON 报告 |
| `investigation_selection/` | ⑤ 重建 | 检查选择：clock、grouping、episodes、facts/actions、snapshot adapter、first-wave corpus | ④ 的聚合事件 + `evaluation_pipeline.snapshot` | 1,000 例 corpus（`methodology_unreviewed`）；catalog-lock 已生成；不是 gold |
| `mcq_visit_extract/` | 并行（五类题型） | 从 MIMIC CSV.GZ 按 `(subject_id, hadm_id)` 漏斗+确定性抽样，写出一行一次住院的 csv/json；可断点续跑 | MIMIC CSV.GZ | `visits.csv` + `visits.json`（`exploratory_unreviewed`，不是 gold） |
| `mcq_visit_standardize/` | 并行（五类题型） | 对 visit 行做术语/单位/主诉症状统一；不覆盖抽取、不改写病历正文 | `visits.json` | `visits_standardized.json` + inventory + review_queue |
| `mcq_visit_ner/` | 并行（五类题型） | 对冻结 `visits.json` 出院小结做 span NER（OpenAI 兼容；默认空跑；外传需显式授权） | `visits.json` | `visit_mentions.jsonl`（接地 mention；非正式 gold） |
| `mcq_visit_timeline/` | 并行（五类题型） | 把补齐时钟与标准化名称合成一次住院事件时间线；不覆盖上游 | times `visits.json` + standardized JSON | `visit_events.parquet` + timelines/facts（非正式 gold） |
| `mcq_visit_mining/` | 并行（五类题型） | 10k Visit 上按题型做 X→y；strict 8 门；不出题 | timeline 目录 | accepted/rejected 规则（`exploratory_unreviewed`） |
| `archived/phenotype/` | 已失效 | 旧 visit 特征与条件组合；旧路径不可导入，formal 入口拒绝 | — | 仅审计，不得进入新 gold |
| `text_ner/`、`text_ner_v2/` | 支路 | 文档/章节/span 清单与 NER 接口（默认不调模型） | ④ 的 aggregation 产物 | section 标注、mention sidecar、关系 sidecar |
| `mimic_source_catalog.py` | 共享契约 | 锁定 MIMIC 文件目录与表头，供各站复用同一份源表定义 | — | `SOURCE_BY_KEY` |
| `tools/mimic_dictionary/` | 辅助工具 | 生成五份官方字典的 JSON/CSV/Parquet/DuckDB 形态 | 五张官方字典表 | ② 所需的 `dictionaries/*.json` |
| `archived/mimic_episode/`、`archived/parquet_to_jsonl/` | 已归档路线 | Episode/visit 事件模型与评测快照（非主流程必经） | 41 张 MIMIC 源表 | Episode Parquet、`mimic_visit_archive/1.0.0` JSONL |

## 主流程命令

在项目根目录执行（PowerShell 反引号续行；正式参数见各模块 README）：

```powershell
# （可选）先生成冠心病谱系住院清单
.\.venv\Scripts\python.exe -m data_pipeline.mimic_raw_archive.cohort `
  --data-root data\RawData `
  --output data\coronary-admission-selection.jsonl `
  --development-percent 20

# ① 原始表聚合为 admission JSONL（--selection-input 传入清单，或用 --sample-size 随机抽取）
.\.venv\Scripts\python.exe -m data_pipeline.mimic_raw_archive `
  --data-root data\RawData `
  --output-dir data\raw_archive\shards `
  --merged-output data\mimic-admission-raw.jsonl `
  --selection-input data\coronary-admission-selection.jsonl

# ② 解码 + POE 时间线 → 临床可读 JSONL
.\.venv\Scripts\python.exe -m data_pipeline.clean_clinical_archive `
  data\mimic-admission-raw.jsonl `
  --output data\NEW-BATCH-clinical-readable.jsonl `
  --report data\NEW-BATCH-clinical-readable.report.json

# ③ 事件化 + 归一化 + 全部门禁（一条命令；单阶段排查用 clean/normalize 子命令）
.\.venv\Scripts\python.exe -m data_pipeline.event_pipeline run `
  data\NEW-BATCH-clinical-readable.jsonl `
  --raw-source-jsonl data\mimic-admission-raw.jsonl `
  --output-dir data\NEW-BATCH\event_pipeline_output

# ④ 无损聚合（输入为批次目录；输出默认写到 event_pipeline_output\aggregation）
.\.venv\Scripts\python.exe -m data_pipeline.event_aggregation `
  data\NEW-BATCH

# ⑤ 时点检查投影（读已有 event extract，不重跑 event_pipeline）
.\.venv\Scripts\python.exe -m data_pipeline.investigation_selection `
  docs\reports\hadm-28234402-event-aggregated.json `
  --output-dir data\derived\investigation_timepoint\hadm-28234402
```

## 贯穿全流水线的工程纪律

五站共享同一套正确性哲学，理解这几点即可理解所有模块的行为模式：

1. **fail-closed**：任何输入缺失、哈希漂移、结构漂移、计数不一致、血缘矛盾都直接抛错终止，不降级、不跳过、不静默修复。典型例子：解码未命中字典即整趟失败（②）、未登记表直接拒绝（③）、事件血缘与指针互验失败即不发布（④）。
2. **内容指纹身份**：全链路以 SHA-256 绑定内容而非路径/mtime——39 个源文件哈希聚合成运行身份（①）、字典行数/字节/哈希进便携包清单（②）、run_id 与目录 SHA-256 写进各级 manifest（③）、输入哈希对账后才聚合（④）、上游 manifest 校验后才建特征（⑤）。任何一环字节级变化都会被下一环拒收。
3. **原子发布、拒绝覆盖**：所有正式产物一律「临时目录/`.partial` 文件 + `os.replace`」上线（③④ 的输出目录、② 的输出与报告、① 的分片与合并文件）；目标已存在即失败，绝不产生半成品目录或部分成功的输出。
4. **确定性优先**：抽样/排序/ID/枚举全部由哈希或固定顺序决定（无随机种子），同输入必得逐字节一致的输出；③ 甚至用不同 batch size 复跑并要求 8 个数据文件 SHA-256 全等来证明分块不变性。
5. **可回溯血缘**：① 行键序=源表头、② 追加式解码 + 可逆性自检、③ `raw_row_ref` 行级指针、④ `source_record_id` 连接三份 Parquet——任何派生值都能回查到唯一源行，任何一步"改没改原始内容"都有独立校验。
6. **审计与实现分离**：③ 的质量审计不 import 生产 transformer/术语规则，而是独立重算期望值再比对——用"平行实现"证明实现正确，而非复述实现。

## 共同约束

- 从项目根目录以 `python -m data_pipeline.<module>` 形式执行；辅助工具用 `data_pipeline.tools.<module>`；归档代码用 `data_pipeline.archived.<module>`；phenotype 的入口是目录内脚本（`run_*.py`）。
- `clean_clinical_archive/` 可单独复制到任何有 Python 3.12 的机器运行（先跑 `verify_bundle` 自检）；其余模块依赖项目目录结构与 `.venv`。
- 原始 MIMIC 数据、生成数据和五份授权字典不得提交到 Git。
- 输出已存在时主流程默认拒绝覆盖；应明确处理旧输出，不能依赖隐式覆盖。
- admission 主流程以 schema 标识连接：② 只接受 `mimic_admission_raw/1.0.0`；③ 接受临床可读（或 raw）schema；④ 只接受全部门禁通过的 ③ 产物。

## 可选 Episode/visit 路线（已归档）

```text
MIMIC 原始 CSV.GZ → archived/mimic_episode → Episode Parquet → archived/parquet_to_jsonl → Visit 级 JSONL + 决策快照
```

这条路线用于 Episode 事件模型和评测快照，不是当前 admission 临床可读归档的必经步骤。活动主流程不依赖 `archived/` 内的任何文件；`mimic_raw_archive` 与归档 Episode 路线只共同读取根目录的 `mimic_source_catalog.py`。

## 测试

```powershell
# V3 直抽 / 标准化 / 时间线 / 挖掘
.\.venv\Scripts\python.exe -m unittest -v `
  tests.test_mcq_visit_extract tests.test_mcq_visit_extract_monitor tests.test_mcq_visit_extract_medtimes `
  tests.test_mcq_visit_standardize tests.test_mcq_visit_timeline tests.test_mcq_visit_mining
# ①
.\.venv\Scripts\python.exe -m unittest -v tests.test_raw_admission_archive tests.test_raw_archive_monitor tests.test_module_subset tests.test_raw_field_dictionary
# ②
.\.venv\Scripts\python.exe -m unittest -v tests.test_clean_clinical_archive tests.test_poe_timeline
# ③（unittest.TestCase，也可用 pytest）
.\.venv\Scripts\python.exe -m unittest -v `
  tests.test_event_pipeline tests.test_event_source_catalog `
  tests.test_event_terminology tests.test_event_audit_storage `
  tests.test_event_cleaning_regression tests.test_event_normalization_review `
  tests.test_event_pipeline_viewer tests.test_event_review_app `
  tests.test_event_review_consolidation
# ④
.\.venv\Scripts\python.exe -m unittest -v tests.test_event_aggregation
# ⑤（.venv 无 pytest 时用 Anaconda 解释器）
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD="1"; E:\Anaconda3\python.exe -m pytest tests/test_phenotype.py -q -p no:cacheprovider
```
