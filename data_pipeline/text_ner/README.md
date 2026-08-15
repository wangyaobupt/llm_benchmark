# Text NER 与关系抽取接口

最新版只读取已验收的 `event_pipeline_output/aggregation`：`raw_source_records.parquet` 提供去重后的完整自由文本和源行血缘，`processed_events.parquet` 提供标准化事件关联。NER 不再回读 source JSONL。默认不执行模型；未来可通过通用 OpenAI-compatible API 接入任意兼容 LLM。

当前同时冻结了 section 标注响应、mention sidecar 和显式关系 sidecar 的首版合同：

- `schemas/section-annotation.schema.json`
- `annotation_contracts.py`
- `annotation_validation.py`

标注规则见 `docs/design/text-ner-entity-annotation-protocol.md`。

当前1000例入口：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.text_ner prepare-aggregation-manifest `
  data\test_1000_0812\event_pipeline_output\aggregation `
  config\text_ner\all-free-text-sources.json `
  --output-dir data\test_1000_0812\event_pipeline_output\NER\input
```

最新版纳入 `hosp.labevents.comments`、`hosp.microbiologyevents.comments`、`ed.triage.chiefcomplaint`、`note.radiology.text` 和 `note.discharge.text`。discharge 保持 `evidence_phase=post_hoc`，但不再从 NER 排除。结构化编码、受控词表、状态、单位、药名和文档元数据不重复送入 NER。

从 `.env`/进程环境变量配置、10例小批运行、断点续跑到全量两阶段编译的可复制命令见[运行手册](../../docs/guides/text-ner-runbook.md)；接口合同与方法边界见[模型接口设计](../../docs/design/text-ner-model-interface.md)。

## 历史100例接口

`prepare-legacy-ed-radiology`、`audit`、人工 A/B 包和 calibration-only method run 只用于重放旧100例研究记录，不约束最新版1000例接口。旧报告中 `POST_HOC_DISCHARGE`、2,724个文本单元和 ED/radiology-only 的结论均是历史版本事实。

历史接口独立验收：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.text_ner audit `
  data\mimic-admission-raw-coronary-all-three-modules-random-100.jsonl `
  data\derived\text_ner_sample_100 `
  --replay-directory data\derived\text_ner_sample_100_replay `
  --output-json docs\reports\text-ner-input-manifest-acceptance.json `
  --output-markdown docs\reports\text-ner-input-manifest-acceptance.md
```

## 本地 A/B 双标与裁决界面

标注界面只监听 `127.0.0.1`，每个进程固定一个角色。A 与 B 的服务只加载各自任务和决定日志；裁决服务只有在同一标注单元的 A/B 决定均已追加后才开放详情。界面不调用模型或外部服务，任务原文和人工结果仍只保存在被 Git 忽略的本地标注包中。

分别启动三个角色（端口可自行调整）：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.text_ner.annotation_app `
  data\derived\text_ner_annotation_pilot --role annotator_a --port 8765

.\.venv\Scripts\python.exe -m data_pipeline.text_ner.annotation_app `
  data\derived\text_ner_annotation_pilot --role annotator_b --port 8766

.\.venv\Scripts\python.exe -m data_pipeline.text_ner.annotation_app `
  data\derived\text_ner_annotation_pilot --role adjudicator --port 8767
```

浏览器中的 exact span 会显式转换 JavaScript UTF-16 offset 到 Python Unicode code-point offset，并处理 CRLF/LF 差异；后端在写入前再次核对 surface text、关系 evidence 覆盖、输入哈希和两个 JSON Schema。每次提交生成新的 payload 文件并向角色日志追加一行；修改必须通过 `supersedes_decision_id` 引用旧决定，旧文件不会被覆盖。`blocked_pending_calibration` 状态的 evaluation 任务会返回锁定错误，不能从界面打开。

对真实 pilot 做只输出聚合计数的标注范围演练：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.text_ner rehearse-scope `
  data\mimic-admission-raw-coronary-all-three-modules-random-100.jsonl `
  data\derived\text_ner_sample_100\text_ner_input_manifest.parquet `
  --expected-pilot-documents 200 `
  --output-json docs\reports\text-ner-annotation-scope-rehearsal.json `
  --output-markdown docs\reports\text-ner-annotation-scope-rehearsal.md
```

该命令读取真实 section 来统计否定、不确定、比较、建议、测量、侧别、器械和时间表达覆盖，但不会在报告中保存原文，也不会生成实体或调用模型。

生成患者隔离的人工双标包：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.text_ner prepare-annotation-package `
  data\mimic-admission-raw-coronary-all-three-modules-random-100.jsonl `
  data\derived\text_ner_sample_100\text_ner_input_manifest.parquet `
  --output-dir data\derived\text_ner_annotation_pilot `
  --calibration-documents 50
```

生成结果：

- `allocation/annotation_allocation.parquet`：200份文档的患者级分配。
- `calibration/annotator_a/tasks.jsonl`、`annotator_b/tasks.jsonl`：相同任务集合、不同确定性顺序。
- `evaluation/tasks.locked.jsonl`：状态为 `blocked_pending_calibration`，不得在calibration门禁通过前使用。
- `annotations/annotator_a|annotator_b|adjudicated/`：标注响应文件目录。
- `decisions/annotator_a.jsonl`、`annotator_b.jsonl`、`adjudication.jsonl`：追加式决定日志，初始为空。

任务文件包含受限MIMIC原文，只能保留在被Git忽略的`data/derived/`。A/B提交时分别把每个任务中的空白`annotation`填写后另存到自己的`annotations/`目录，再按`annotation-review-decision.schema.json`向自己的决定日志追加记录。裁决者只能在A/B均提交后工作，并在裁决日志中引用双方`decision_id`；不得覆盖原始决定。

独立验收：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.text_ner audit-annotation-package `
  data\derived\text_ner_annotation_pilot `
  --replay-directory data\derived\text_ner_annotation_pilot_replay `
  --output-json docs\reports\text-ner-annotation-package-acceptance.json `
  --output-markdown docs\reports\text-ner-annotation-package-acceptance.md
```

## 探索性NER方法链路

当前首个方法是“两阶段、可验证抽取”：第一阶段只产生mention及属性，Python通过Schema、字符span和来源哈希验证后，第二阶段才能引用有效mention产生文本显式关系。方法输出固定标记为`exploratory_candidate`，不能冒充人工gold。

当前版本只准备 calibration 请求，不调用模型：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.text_ner prepare-method-run `
  data\derived\text_ner_annotation_pilot `
  config\text_ner\exploratory-two-stage.json `
  --output-dir data\derived\text_ner_method_exploratory
```

独立验收并验证双次运行哈希一致：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.text_ner audit-method-run `
  data\derived\text_ner_annotation_pilot `
  config\text_ner\exploratory-two-stage.json `
  data\derived\text_ner_method_exploratory `
  --replay-directory data\derived\text_ner_method_exploratory_replay `
  --output-json docs\reports\text-ner-method-run-acceptance.json `
  --output-markdown docs\reports\text-ner-method-run-acceptance.md
```

运行目录中的`mention_requests.jsonl`包含受限临床原文，只能位于被Git忽略的`data/derived/`。relation请求初始状态为`blocked_pending_validated_mentions`，候选文件为空，指标文件必须为`not_evaluable`。即使传入`--execute`，当前版本也会在写文件前以`MODEL_EXECUTION_NOT_AUTHORIZED`失败；后续必须单独确定模型、合规边界和执行授权。

`rule_baseline.py`提供只识别测量值和显式时间词的保守非模型基线，用于验证方法与评价代码，不能替代完整临床NER。正式方法设计与结果解释边界见`docs/design/text-ner-methodology.md`。

## DeepSeek API成本与合规门禁

DeepSeek API可以通过环境变量配置，但环境变量只负责凭据注入，不能改变受限数据政策。当前PhysioNet要求第三方LLM服务具备可验证的零数据保留、不训练和无人审；DeepSeek公开隐私政策没有提供满足该要求的零保留承诺。因此`restricted_mimic`被代码硬阻断，不能通过环境变量解除。

环境变量名称记录在仓库根目录`.env.example`；真实key只放进进程环境，不写入`.env.example`、运行清单、日志或Git。适配器目前只允许`synthetic`和`public_nonclinical`测试。

对171个calibration单元执行零调用费用估算：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.text_ner estimate-deepseek-cost `
  data\derived\text_ner_method_exploratory `
  config\text_ner\deepseek-api-policy.json `
  --output-json docs\reports\text-ner-deepseek-cost-compliance.json `
  --output-markdown docs\reports\text-ner-deepseek-cost-compliance.md
```

估算使用DeepSeek官方英文字符约0.3 token的近似值，并给出多种输出长度和缓存情景；它不是账单，也不授权API执行。真实账单只能在合规执行后根据响应`usage`计算。
