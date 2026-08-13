# Text NER 方法学设计

方法版本：`two-stage-explicit-clinical-ner/1.0.0`

## 1. 研究问题

本阶段研究的不是“某个模型是否已经达到可发布准确率”，而是：在保持来源可追溯、字符span精确、临床语境属性显式和评估集隔离的条件下，哪种候选生成方法能够稳定产出可验证的临床实体与文本显式关系。

当前只覆盖ED chief complaint和radiology report。结果不能外推到全部临床文书，也不能把术语标准化、事件编译或医学常识推理算作NER能力。

## 2. 核心方法

采用两个顺序阶段：

1. mention阶段读取单个section，输出实体span、类型及assertion、temporality、experiencer等属性，不输出关系。
2. Python验证Schema、输入哈希、`surface_text == section_text[start:end]`、ID唯一性和取值域。
3. relation阶段只接收原section和已验证mention，输出两个mention之间由当前原文明示的关系。
4. Python再次验证关系端点、方向、证据span及证据对端点的覆盖。
5. 通过验证的结果写入不可变candidate sidecar；人工gold始终来自独立双标和第三人裁决。

两阶段设计使mention错误和relation错误可以分别计数，也避免模型在建立关系时偷偷增加、删除或改变实体。

## 3. 方法比较空间

后续方法可以替换候选生成器，但不能改变输入、Schema、验证器或正式评估集：

| 方法 | 允许产生的内容 | 主要研究问题 |
|---|---|---|
| 保守规则基线 | 测量值、显式时间表达 | 验证链路并建立最低基线 |
| 传统序列标注NER | mention span和类型 | 局部模型在短主诉与长放射报告上的差异 |
| 单阶段结构化生成 | mention、属性、关系一次生成 | 简化调用是否导致关系和span相互污染 |
| 两阶段结构化生成 | 先mention，验证后关系 | 约束分解是否改善合规性和可归因性 |
| 规则与模型混合 | 确定性类型由规则产生，其余由模型产生 | 是否在保持召回率时减少测量和时间错误 |

方法比较必须记录方法ID、提示词哈希、模型及revision、参数、随机种子、输入包哈希、实现哈希、原始响应哈希和验证拒绝原因。模型通过Schema的比例本身是方法指标，不能只评价被后处理保留下来的结果。

## 4. 数据与污染控制

- 50份calibration是方法开发区；模型候选目录与A/B人工目录物理分离，标注者不得查看模型输出。
- 150份evaluation保持`blocked_pending_calibration`，方法开发、提示词修改和错误分析都不能读取它。
- 当前dry-run只读取`calibration/annotator_a/tasks.jsonl`作为规范化输入顺序，并核对A/B任务集合一致；不读取evaluation任务文件。
- 原文和模型原始响应只保存在Git忽略的本地运行目录；Git中的报告只包含计数、状态、reason code和哈希。

## 5. 评价设计

没有人工gold时，指标状态必须为`not_evaluable/HUMAN_GOLD_UNAVAILABLE`，不得把空gold转换为0分，也不得用模型共识替代gold。

gold可用后报告：

- exact span＋type micro precision、recall、F1；
- 相同类型且字符span有重叠的relaxed指标，使用最大一对一匹配；
- assertion、temporality、experiencer的端到端macro-F1；
- 以mention span＋type标识端点的显式关系exact F1；
- ED与radiology分层结果，以及九种实体类型分层结果；
- 否定事实当阳性、家族史当患者事实、建议当已执行事件三类严重错误计数。

属性指标将span、实体类型和属性值作为一个端到端预测单元，因此漏抽实体和伪实体都会被惩罚，不会因只在“恰好匹配的实体”上计算属性而虚高。

## 6. 当前运行门禁

当前方法配置中的provider、model、revision、seed均为`null`，外部API固定为不允许。CLI默认dry-run；显式`--execute`也会失败，因为本版本尚未实现或授权任何模型适配器。

进入真实模型执行前必须另外完成：

1. 确定本地模型或经过合规审查的执行环境；
2. 冻结模型revision、推理参数和随机性策略；
3. 实现原始响应不可变保存及逐次调用日志；
4. 保持模型结果对A/B标注者不可见；
5. 由用户显式授权一次真实模型执行。

即使真实模型开始运行，calibration完成前的输出仍只能用于方法探索，不能称为经过验证的实验结果。

## 7. DeepSeek外部API边界

DeepSeek的成本优势不改变受限数据边界。PhysioNet要求第三方API具备可验证的零数据保留、不训练和无人审；无法完整验证时不得使用。DeepSeek现行公开隐私政策说明会收集用户输入，并可能为服务、研发和安全目的保留数据，未提供本项目可核验的零保留承诺。

因此当前实现包含DeepSeek JSON API请求合同、环境变量读取、响应哈希和usage记录能力，但只允许`synthetic`与`public_nonclinical`数据。`restricted_mimic`在读取API key和构造网络客户端之前即失败，且没有环境变量覆盖入口。若未来获得满足PhysioNet要求的企业零保留协议，必须保存协议证据、升级`deepseek-api-policy`版本、重新验收后才能改变此门禁。
