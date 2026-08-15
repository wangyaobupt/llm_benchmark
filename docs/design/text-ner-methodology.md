# Text NER 方法学设计

方法版本：`two-stage-explicit-clinical-ner/1.1.0`

## 1. 研究问题

本阶段不比较 NER 方法。目标是：对已验收1000例事件数据关联的全部配置自由文本执行同一套实体识别和文中显式关系抽取，并让每个结果能够回到来源行、原文字符span和标准化事件。

当前范围由 `all-free-text-sources.json` 冻结，覆盖 hosp laboratory/microbiology comments、ED chief complaint、radiology 和 discharge。discharge 纳入抽取但保留 `evidence_phase=post_hoc`；纳入不表示它可用于更早决策时点。

## 2. 核心方法

采用两个顺序阶段：

1. mention阶段读取单个section，输出实体span、类型及assertion、temporality、experiencer等属性，不输出关系。
2. Python验证Schema、输入哈希、`surface_text == section_text[start:end]`、ID唯一性和取值域。
3. relation阶段只接收原section和已验证mention，输出两个mention之间由当前原文明示的关系。
4. Python再次验证关系端点、方向、证据span及证据对端点的覆盖。
5. 通过验证的结果写入不可变candidate sidecar；人工gold始终来自独立双标和第三人裁决。

两阶段设计使mention错误和relation错误可以分别计数，也避免模型在建立关系时偷偷增加、删除或改变实体。

## 3. 固定方法与模型可替换性

抽取方法固定为两阶段结构化生成。未来可以更换 LLM 提供商或部署方式，但不能改变输入 manifest、提示词版本、响应 Schema、span 验证、关系依赖或 sidecar 合同。每次执行记录提示词哈希、模型及不可变 revision、参数、输入包哈希、实现哈希、响应文件哈希和验证拒绝原因。

## 4. 数据与污染控制

- 总体由已验收的 `event_pipeline_output/aggregation` 锁定；aggregation manifest、quality report、文件行数、Schema 和 SHA-256 必须全部通过校验。
- `raw_source_records.parquet` 提供去重的完整正文与源行血缘，`processed_events.parquet` 提供标准化事件关联；NER 不再回读 source JSONL。
- 原文、请求和响应只保存在Git忽略的 `event_pipeline_output/NER`；Git报告只包含计数、状态、reason code和哈希。
- 模型输出标记为 `unreviewed_model_output`；人工抽样验收完成前不能称为 gold 或经过验证的实验结果。

## 5. 评价设计

没有人工gold时，指标状态必须为`not_evaluable/HUMAN_GOLD_UNAVAILABLE`，不得把空gold转换为0分，也不得用模型共识替代gold。

gold可用后报告：

- exact span＋type micro precision、recall、F1；
- 相同类型且字符span有重叠的relaxed指标，使用最大一对一匹配；
- assertion、temporality、experiencer的端到端macro-F1；
- 以mention span＋type标识端点的显式关系exact F1；
- 按 hosp、ED、radiology、discharge 来源和九种实体类型分层的结果；
- 否定事实当阳性、家族史当患者事实、建议当已执行事件三类严重错误计数。

属性指标将span、实体类型和属性值作为一个端到端预测单元，因此漏抽实体和伪实体都会被惩罚，不会因只在“恰好匹配的实体”上计算属性而虚高。

## 6. 当前运行门禁

provider、model 和 revision 通过通用 OpenAI-compatible 接口配置，当前生成产物仍保持未绑定。CLI 默认拒绝执行；必须显式传入 `--execute`。外部端点还必须传入 `--confirm-data-transfer-authorized`，本地端点必须解析为 loopback 地址。

进入真实模型执行前必须另外完成：

1. 确定本地模型或经过合规审查的API环境；
2. 在环境变量中配置 endpoint、model 和不可变 revision；
3. 明确数据传输权限并由用户显式授权真实执行；
4. 先用 `--maximum-requests` 完成小批人工检查，再扩大批次；
5. mention 全部通过验证后，才开始 relation 阶段。

即使真实模型开始运行，人工抽样验收完成前的输出也不能称为经过验证的实验结果。

## 7. 通用API边界

通用接口兼容 OpenAI-style `/chat/completions`，不代表任意外部服务都已获得临床文本传输授权。环境变量只注入凭据，不能绕过显式执行和传输确认。逐次审计保存 request ID、provider、model revision、请求哈希和 token usage，不保存 API key。DeepSeek 的旧专用适配器继续保留其历史严格阻断策略，但不再限定最新版通用接口的提供商选择。
