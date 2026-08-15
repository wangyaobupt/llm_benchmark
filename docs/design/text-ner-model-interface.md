# Text NER 全量抽取模型接口

## 目标与边界

本接口以已验收的 `data/test_1000_0812/event_pipeline_output` 为队列和标准化血缘主入口，将配置目录中的全部自由文本转换为两阶段结构化请求。当前范围包括 hosp laboratory/microbiology comments、ED chief complaint、radiology 和 discharge；`source_table` 不再限定具体表。接口可配置任意 OpenAI-compatible API，但默认不调用模型。

因此，`prepared_no_model_calls` 只证明数据与接口已经就绪，不代表已完成实体识别实验。没有模型响应时，实体和关系 sidecar 必须是零行并保持 `pending_model_execution`。

## 数据流

1. `prepare-event-output-manifest` 验证 workflow 与 normalized events，再按 `all-free-text-sources.json` 从同批 source JSONL 回取自由文本；discharge 纳入并保留 `post_hoc`。
2. `prepare-full-extraction` 处理 manifest 中所有 `inclusion_status=included` 的合法来源表，不再使用 ED/radiology 白名单。
3. 每个文本单元生成一个 mention 请求；对应 relation 请求先保持 `blocked_pending_validated_mentions`。
4. 模型适配器实现 `TextNerModelAdapter.generate(request)`，返回 `text-ner-model-response/1.0.0` envelope。接口不限定提供商、部署方式或传输协议。
5. `compile-model-responses` 先校验 mention 响应的来源、输入哈希、精确字符 span 和枚举值，再生成带 `validated_mentions` 的 relation 请求。
6. relation 响应只能引用已验证 mention，且 evidence span 必须覆盖关系两端实体。通过校验后编译 `entity_mentions.parquet` 与 `text_relations.parquet`。

## 输入

- `event_pipeline_output/workflow_manifest.json` 与 `normalized_events.parquet`：锁定1000例总体、标准化状态和来源事件。
- workflow 声明的 clinical-readable JSONL：仅用于按 manifest 回取文本并复核 source/section SHA-256。
- `text_ner_input_manifest.parquet`：决定纳入范围、切片位置、时间语义和来源追踪字段。
- mention/relation prompt：内容被固化进本地请求包，并记录 SHA-256。
- 可选模型响应 JSONL：每行包含请求 ID、阶段、模型 provenance 与一个 `section-annotation/1.0.0` 对象。

## 输出

准备阶段输出：

- `requests/mention_requests.jsonl`
- `requests/relation_requests.pending.jsonl`
- `response_templates/mention_responses.jsonl` 与 `relation_responses.jsonl`（空文件，只定义导入位置，不含模型结果）
- `extraction_summary.json`
- `run_manifest.json`

编译阶段输出：

- `requests/relation_requests.ready.jsonl`
- `sidecars/entity_mentions.parquet`
- `sidecars/text_relations.parquet`
- `candidates/section_annotations.jsonl`
- `compile_summary.json` 与 `compile_manifest.json`

请求包含受限临床原文，只能保存在本地 `data/` 路径，不允许提交到 Git。聚合验收报告不得包含原文、surface text 或患者标识符。

机器可读协议位于 `data_pipeline/text_ner/schemas/model-request.schema.json`、`model-response.schema.json` 和 `section-annotation.schema.json`。未来适配器只负责完成一次 request/response 映射；患者范围、哈希校验、span 校验、关系依赖和 sidecar 编译仍由本模块统一控制。

## 为什么拆成两阶段

关系的节点必须是已经通过 span 校验的实体。先锁定实体，再允许关系请求，能够从结构上阻止模型在关系阶段改写实体、引用不存在的实体，或产生无法回溯到原文的关系。对使用者的影响是多一次接口往返，但换来可审计、可拒绝和可重放的结果链路。

## 命令

```powershell
python -m data_pipeline.text_ner prepare-event-output-manifest `
  data/test_1000_0812/event_pipeline_output `
  config/text_ner/all-free-text-sources.json `
  --output-dir data/test_1000_0812/event_pipeline_output/NER/input

python -m data_pipeline.text_ner prepare-full-extraction `
  data/test_1000_0812/mimic-admission-clinical-readable-coronary-random-1000.jsonl `
  data/test_1000_0812/event_pipeline_output/NER/input/text_ner_input_manifest.parquet `
  --mention-prompt config/text_ner/prompts/two-stage-mentions.md `
  --relation-prompt config/text_ner/prompts/two-stage-relations.md `
  --output-dir data/test_1000_0812/event_pipeline_output/NER/extraction_interface
```

```powershell
python -m data_pipeline.text_ner compile-model-responses `
  data/test_1000_0812/event_pipeline_output/NER/extraction_interface `
  data/test_1000_0812/event_pipeline_output/NER/input/text_ner_input_manifest.parquet `
  mention_responses.jsonl relation_responses.jsonl `
  --output-dir data/test_1000_0812/event_pipeline_output/NER/final
```

第二条命令只导入给定响应，不会自行调用模型。

## 通用 API

环境变量为 `TEXT_NER_API_KEY`、`TEXT_NER_BASE_URL`、`TEXT_NER_MODEL`、`TEXT_NER_MODEL_VERSION` 和 `TEXT_NER_PROVIDER`。批处理命令为 `run-openai-compatible-api`，支持按 request ID 断点续跑和 `--maximum-requests` 分批执行。没有 `--execute` 时在读取凭据或创建网络连接前失败；外部端点还要求 `--confirm-data-transfer-authorized`，本地端点必须是 loopback 地址。完整参数见 `python -m data_pipeline.text_ner run-openai-compatible-api --help`。
