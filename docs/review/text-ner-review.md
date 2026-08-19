# Text NER 人工校准操作说明

## 1. 这一步在做什么

这一步不是再次做结构化事件归一化，也不是直接生成检查选择题。它是在校准“如何把 MIMIC 文本中的临床表达转换为可追溯文本事实”。

当前输入包括：

- ED `triage.chiefcomplaint`：结构化表中的自由文本主诉字段；
- radiology report：放射报告的分节文本。

当前输出只包含原文 mention、属性和文本显式关系。术语标准化固定保持：

```json
{
  "normalization_status": "unattempted",
  "concept_id": null,
  "preferred_name": null,
  "terminology": null
}
```

因此，人工校准回答的是“原文明确表达了什么”，不是“它应该映射到哪个标准医学编码”，更不是“临床上最佳检查是什么”。

## 2. 当前状态

- calibration：50份文档、24名患者；
- 其中ED主诉25份、放射报告25份；
- A/B各有171个相同文本单元，顺序不同；
- evaluation：150份文档、657个文本单元，保持`blocked_pending_calibration`；
- A、B和裁决日志当前均为0；
- 模型调用为0。

重要限制：当前ED主诉的`available_time=null`。它们可以用于校准实体、属性和span规则，但在确定可审计的可用时间策略之前，不得进入前瞻性检查选择快照。

## 3. 角色与入口

每名标注者只能使用自己的角色界面，不得查看另一人的决定：

- Annotator A：`http://127.0.0.1:8765/`
- Annotator B：建议使用`http://127.0.0.1:8776/`
- Adjudicator：建议使用`http://127.0.0.1:8767/`

当前先从Annotator A开始。若只有一名实际标注者，只完成A；不要由同一个人再充当B，否则不能计算独立标注一致性。

标注者ID必须稳定且能区分角色，例如`reviewer-01-a`。不要使用`1`、`test`等无法长期追溯的值。

## 4. 首批10个ED主诉任务

界面按钮显示`section_name`和`annotation_unit_id`后8位。Annotator A先完成以下10个`chief_complaint`单元；这只是calibration内的规则试运行，不改变原任务包和顺序。

| 顺序 | A界面列表位置 | annotation unit | 界面后8位 |
|---:|---:|---|---|
| 1 | 4 | `aunit:fb417b2810b6d82d1c6aa5b4` | `1c6aa5b4` |
| 2 | 17 | `aunit:e74130d17834677ece0c2b4e` | `ce0c2b4e` |
| 3 | 21 | `aunit:ebee06bc4f0060176e82d4df` | `6e82d4df` |
| 4 | 26 | `aunit:3c84ed56a259e72d58202396` | `58202396` |
| 5 | 27 | `aunit:3b3ed72afd2fcedfbabe566c` | `babe566c` |
| 6 | 33 | `aunit:0cf73bcd1f9b1dfdcb5afa21` | `cb5afa21` |
| 7 | 47 | `aunit:85f62dd328053e0bb6da7abe` | `b6da7abe` |
| 8 | 49 | `aunit:7d0113a06e206dfc8da9e394` | `8da9e394` |
| 9 | 50 | `aunit:20c5b04d0b29f7f6468abf90` | `468abf90` |
| 10 | 64 | `aunit:dc7da138b5bc21a3de99e65e` | `de99e65e` |

A和B必须独立完成同一批单元，双方提交前不得讨论具体标注。

## 5. 单条ED主诉怎么标

### 步骤1：完整阅读原文

先判断原文是否包含：

- 症状或体征；
- 已明确的疾病或临床问题；
- 检查或操作；
- 药物或物质；
- 时间表达。

不要根据医学常识补充原文没有表达的诊断、部位或因果关系。

### 步骤2：选择exact span

用鼠标只选择最小但临床意义完整的连续原文。选择后点击“用当前选择新增 mention”。

- 不改拼写、不扩写缩写；
- 否定词、可能性词通常不放入临床实体span，而由属性表达；
- 同一个词在不同位置重复出现时分别标注；
- 无法可靠展开的缩写保留原文，并选择`ABBREVIATION_UNRESOLVED`；
- 不允许把不连续的两段文字合成一个mention。

### 步骤3：选择实体类型

ED主诉最常用：

- `symptom_or_sign`：疼痛、呼吸困难、发热等患者症状或临床体征；
- `clinical_problem`：原文明示的疾病、综合征或诊断；
- `procedure_or_test`：原文明示的检查或操作；
- `medication_or_substance`：原文明示的药物或相关物质；
- `temporal_expression`：与临床事实相关的时间点或持续时间。

不要用`clinical_problem`代替尚未确诊的普通症状，也不要创建`other`实体。

### 步骤4：填写属性

对普通ED主诉，在没有反向证据时通常使用：

- `assertion=present`；
- `temporality=current`；
- `experiencer=patient`；
- 没有明确侧别、严重度或趋势时使用`not_stated`；
- 对该实体类型没有意义时使用`not_applicable`。

只有原文明示时才能填写：

- `absent`：明确否定；
- `possible`：疑似、可能、待排除；
- `historical`：既往事实；
- `future_planned`：计划或建议；
- `family_member`：明确属于家族成员；
- laterality、severity、trend的具体值。

不确定时使用对应`*_AMBIGUOUS`质量标记；不要用`unknown`掩盖本应依据规则解决的普通情况。

### 步骤5：只建立文本显式关系

ED短主诉通常不需要关系。只有原文明确表达两个mention之间的关系时才建立，并选择一段连续原文作为evidence span。

禁止：

- 根据常识推断疾病导致症状；
- 创建通用`related_to`；
- 建立跨文档关系；
- 把可能或计划中的检查标记为已经完成。

### 步骤6：提交决定

- `accept`：当前人工标注完整，能够按协议确定；
- `uncertain`：协议不足或存在真实歧义；选择`PROTOCOL_AMBIGUITY`并在备注中写清冲突；
- `reject`：文本损坏、来源不匹配或该单元无法标注；填写相应reason code和说明；
- `correct`：用于明确提交一份纠正后的annotation，不作为首轮空白任务的默认选择。

首轮正常完成的ED主诉使用`accept`。即使原文没有任何临床实体，也不能凭空创建mention；保留空annotation，并用`NO_CLINICAL_ENTITY`说明。

## 6. 首批10条验收

完成10条不代表calibration通过，只用于检查规则是否可操作。验收要求：

- 10个指定单元均有A角色追加式决定；
- 标注者ID稳定；
- Schema、surface/span和来源哈希验证全部通过；
- 所有歧义都有质量标记、reason code或备注；
- 没有把症状扩写成诊断；
- 没有把否定、既往或计划事实当成当前阳性事实；
- 不使用evaluation任务；
- 不调用模型；
- 不把受限原文复制到文档、聊天、Git或外部服务。

完成后先汇总歧义类型，不立即修改协议。等B独立完成相同10条后，再比较A/B分歧并决定是否需要协议升级。

## 7. 与检查选择任务的连接

文本NER通过后仍不能直接进入题干，还必须依次经过：

```text
人工/模型文本mention
→ Python span、schema和来源校验
→ assertion、temporality、experiencer筛选
→ 文本事实sidecar
→ available_time门禁
→ 决策时点快照
→ 检查选择题
```

当前ED主诉缺少可靠`available_time`，所以“抽取正确”与“可以进入检查选择题”必须分开验收。

## 8. 完整规则

- [实体与显式关系标注协议](../design/text-ner-entity-annotation-protocol.md)
- [Text NER模块说明](../../data_pipeline/text_ner/README.md)
- [人工标注包验收报告](../reports/text-ner-annotation-package-acceptance.md)
