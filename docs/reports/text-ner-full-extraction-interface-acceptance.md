# Text NER 全量抽取接口验收

## 结论

通用大模型接口和全量请求链路已通过验收，状态为 `passed_interface_ready_no_model_calls`。当前版本没有绑定 DeepSeek、本地模型或其他提供商，也没有发生模型调用。

这表示 `event_pipeline_output` 的1000例数据已经完成“可交给未来模型处理”的工程准备，但不表示已经获得实体识别或关系抽取结果。实体与关系 sidecar 目前均为零行，状态必须解释为 `pending_model_execution`，不能作为实验结果使用。

## 本次处理的数据

本次使用用户指定的 `data/test_1000_0812/event_pipeline_output`：

- admission：1,000
- 标准化事件：757,036
- 含自由文本的来源记录：43,551
- 文本单元：64,509
- hosp laboratory comments：34,311
- hosp microbiology comments：3,549
- ED chief complaint：1,003
- radiology：3,755份文档，切分后23,175个单元
- discharge：933份文档，切分后2,471个单元；纳入并保留 `post_hoc`
- 标准化事件链接：71,024；未链接文本单元：0

## 实现内容

- 通用 `TextNerModelAdapter` 协议：未来模型只需实现一次 request/response 映射。
- `text-ner-model-request/1.0.0` 与 `text-ner-model-response/1.0.0` JSON Schema。
- 全量 hosp/ED/radiology/discharge mention 请求生成。
- 通用 OpenAI-compatible API，通过环境变量选择未来模型并支持按 request ID 断点续跑。
- relation 依赖门禁：只有 mention 响应完成并通过校验后才生成可执行 relation 请求。
- 响应导入校验：请求血缘、输入哈希、精确字符 span、实体枚举、关系引用和 evidence span 全部 fail-closed。
- typed Parquet sidecar 编译：`entity_mentions.parquet` 和 `text_relations.parquet`。
- 模型 provenance：provider、model name、model version、prompt SHA-256 和 input SHA-256 随结果保存。

## 验收证据

| 检查项 | 结果 |
|---|---:|
| mention 请求 | 64,509 |
| 阻塞中的 relation 请求 | 64,509 |
| 模型调用 | 0 |
| 已验证 mention 响应 | 0 |
| 已验证 relation 响应 | 0 |
| 当前实体 sidecar 行数 | 0 |
| 当前关系 sidecar 行数 | 0 |
| 确定性重放 | run ID 与全部输出哈希一致 |
| Text NER 测试 | 34 passed, 0 failed |

manifest run ID 为 `etrun:35dafb6399563d827269c170`，请求包 run ID 为 `xrun:b324e2a1af020fdcddb99ff3`。标准化事件 SHA-256 为 `90a1dc05686ed4366392ed646d50f786700df5c5376408993eae2474d4d10bd2`，输入 manifest SHA-256 为 `dcbe306b065b4e7baf88702e625d7c9df167a2e0e699e0f67dfb24ca46352ce1`。

受限临床原文只存在于 Git 已忽略的 `data/test_1000_0812/event_pipeline_output/NER` 请求包中；报告与代码不包含患者原文或标识符。

## 后续接入模型时的执行顺序

1. 通过通用环境变量选择 OpenAI-compatible endpoint、模型和不可变 revision。
2. 使用 `run-openai-compatible-api --execute` 消费 `mention_requests.jsonl`；外部端点还需明确确认数据传输授权。
3. 运行编译器校验 mention，并取得 `relation_requests.ready.jsonl`。
4. 消费 relation ready 请求，写出 relation response JSONL。
5. 再次运行编译器生成完整 sidecar。
6. 对抽样结果进行人工验收；在人工验收完成前，结果始终标记为 `unreviewed_model_output`。
