# 文本 NER 实体与显式关系标注协议

协议版本：`text-ner-annotation-protocol/1.0.0`

## 1. 目标与边界

本协议只覆盖首批 ED chief complaint 与 radiology report。目标是生成可回到原文字符 span 的实体 mention 和文中显式关系候选，为后续人工裁决、术语标准化、临床事件编译和知识图谱构建提供证据层。

本层不负责：

- 从医学常识推断原文未表达的诊断或关系；
- 将 mention 自动合并为住院级唯一事实；
- 把检查建议当成已经执行的检查；
- 将标准化代码、结构化事件或出院后事实混入 NER；
- 产生 benchmark gold 或调用任何模型。

原始文本保持不变。标注单位是 `text_ner_input_manifest.parquet` 中一条纳入的 section；所有位置均为 Python 字符串的 0-based、左闭右开字符位置。

## 2. 产物层次

| 层 | 合同 | 职责 |
|---|---|---|
| section 标注响应 | `section-annotation/1.0.0` | 一条 section 内的 mention 和文本显式关系 |
| mention sidecar | `entity-mention/1.0.0` | 一行一个通过 Python 校验的 mention 候选 |
| relation sidecar | `text-relation/1.0.0` | 一行一个有原文证据的直接关系候选 |
| 人工裁决 | 后续单独冻结 | 保存接受、纠正、拒绝和裁决历史，不覆盖模型原始候选 |

机器可读响应 Schema 位于 `data_pipeline/text_ner/schemas/section-annotation.schema.json`；Parquet Schema 位于 `data_pipeline/text_ner/annotation_contracts.py`。

## 3. 实体类型

| `entity_type` | 标注对象 | 不标注为该类 |
|---|---|---|
| `symptom_or_sign` | 患者感受到的症状或临床体征，如疼痛、呼吸困难、发热 | 影像学表现 |
| `clinical_problem` | 疾病、综合征、诊断或需要排除的临床问题 | 单纯影像表现、检查名称 |
| `imaging_finding` | 影像可见的异常或有临床意义的正常观察 | 临床症状、解剖名称本身 |
| `anatomical_site` | 原文明确出现的器官、区域、结构 | 根据医学知识推测但原文没有的部位 |
| `procedure_or_test` | 检查、影像操作或其他医疗操作 | 检查结果、器械 |
| `device` | 导管、管路、支架、起搏器、假体等器械 | 药物和造影剂 |
| `medication_or_substance` | 药物、造影剂或临床相关物质 | 器械、一般食物 |
| `measurement` | 数值及其单位构成的测量表达 | 没有临床量纲的普通数字 |
| `temporal_expression` | 与临床事实相关的时间点、时长或相对时间 | 文档元数据中的 chart/store time |

禁止建立 `other` 或 `miscellaneous` 实体类型。无法归类时不猜测，记录为人工讨论项；若协议确实缺类，必须升协议版本后重新校准。

## 4. Span 规则

1. `surface_text` 必须严格等于 `section_text[start:end]`；大小写、缩写、拼写和标点不纠正。
2. 选择最小但临床意义完整的连续名词短语。连续附着且影响概念的类型、部位、侧别或严重度修饰词可以纳入 span。
3. 否定词、可能性词和时间提示词通常不纳入临床实体 span，由属性表达；若它们本身构成 `temporal_expression`，另建 mention。
4. v1 不允许 discontinuous span。无法用连续 span 表达时保留最接近的完整短语并标记 `SPAN_AMBIGUOUS`，交人工裁决。
5. 嵌套 mention 只有在两个 span 分别承担不同临床角色时允许，例如影像发现与其中明确出现的解剖部位。
6. 同一词在文中重复出现时分别标注，不能因标准名称相同而去重。
7. 章节标题只有在自身表达临床实体时才标注；不能仅因标题是 `FINDINGS` 或 `IMPRESSION` 而创建实体。

## 5. Mention 属性

### 5.1 Assertion

| 值 | 规则 |
|---|---|
| `present` | 原文明示该事实存在；无否定/不确定提示的 ED 主诉默认属于此类 |
| `absent` | 原文明示否定、缺如或已排除；否定 mention 仍必须保留 |
| `possible` | 原文使用可能、疑似、不能排除、待排除等不确定表达 |
| `unknown` | 语法或上下文不足以可靠判断，禁止用它替代应当解决的普通情况 |

### 5.2 Temporality

| 值 | 规则 |
|---|---|
| `current` | 当前主诉、当前报告发现或当前状态 |
| `historical` | 既往史、历史检查或 comparison 中明确属于过去的事实 |
| `future_planned` | 建议、计划或待完成的检查/操作；不能编译为已完成事件 |
| `unclear` | 原文没有足够线索，且不能由文档类型可靠确定 |

### 5.3 Experiencer

`patient`、`family_member`、`other`、`unknown`。ED chief complaint 在没有反向证据时可依据来源语境标为 `patient`；明确家族史必须标为 `family_member`，不得误当患者事实。

### 5.4 Laterality、Severity、Trend

- `laterality`：`left/right/bilateral/midline/not_stated/not_applicable`。
- `severity`：`mild/moderate/severe/not_stated/not_applicable`。
- `trend`：`new/increased/decreased/stable/resolved/not_stated/not_applicable`。

这些值只能来自当前 section 的直接表达。没有明示时用 `not_stated`；对类型本身无意义时用 `not_applicable`。不允许依据解剖常识、上下文猜测或跨文档推断。

### 5.5 标准化状态

NER 输出固定为：

```json
{
  "normalization_status": "unattempted",
  "concept_id": null,
  "preferred_name": null,
  "terminology": null
}
```

术语标准化是后续独立阶段，不得由抽取模型顺带填写。

## 6. 来源特异规则

### 6.1 ED chief complaint

- 电报式短语仍按原文标注，不扩写缩写。
- 无否定或不确定提示的主诉默认 `assertion=present`、`temporality=current`、`experiencer=patient`。
- 症状与疾病并列时分别标注，例如症状属于 `symptom_or_sign`，已明确疾病属于 `clinical_problem`。
- 无法可靠展开的缩写保留原 span，并标记 `ABBREVIATION_UNRESOLVED`。

### 6.2 Radiology

- `FINDINGS` 和 `IMPRESSION` 中的事实按 assertion 分别保留，不能只抽取阳性发现。
- `INDICATION/HISTORY` 中待排除的疾病通常为 `clinical_problem + possible`；不能视为已确诊。
- `COMPARISON` 中历史发现为 `historical`。描述当前变化时，在当前 mention 上记录 `trend`。
- `RECOMMENDATION` 中建议的检查为 `procedure_or_test + future_planned`，不能视为已经完成。
- `TECHNIQUE/EXAMINATION` 中出现的检查名称可以标注，但后续事件层仍以结构化报告元数据为事实来源。
- AR 与 RR 的父子关系来自原生 detail 字段，不由 NER 猜测，也不作为文本 relation 重复抽取。

## 7. 文本显式关系

关系必须同时满足：两个端点均为当前 section 的有效 mention、原文明确表达、证据 span 连续覆盖两个 mention。`relation_basis` 固定为 `text_explicit`。

| `relation_type` | 方向 | 含义 |
|---|---|---|
| `located_at` | finding/problem → anatomy | 原文明示事实位于某解剖部位 |
| `has_measurement` | clinical entity → measurement | 原文明示实体具有该测量值 |
| `has_temporal_context` | clinical entity → temporal expression | 原文明示事实对应某时间 |
| `compared_with` | current entity → historical/reference entity | 原文明示当前事实与历史事实比较 |
| `suggestive_of` | finding → clinical problem | 原文明示发现提示某临床问题 |
| `device_positioned_at` | device → anatomy | 原文明示器械位置 |
| `recommendation_for` | recommended procedure/test → triggering entity | 原文明示建议针对某发现或问题 |

没有显式连接词或语法证据时不建关系。禁止使用通用 `related_to`，也禁止把医学常识关系伪装成患者事实。

## 8. 歧义与质量标记

允许的质量标记为：

- `SPAN_AMBIGUOUS`
- `ENTITY_TYPE_AMBIGUOUS`
- `ASSERTION_AMBIGUOUS`
- `TEMPORALITY_AMBIGUOUS`
- `EXPERIENCER_AMBIGUOUS`
- `RELATION_AMBIGUOUS`
- `ABBREVIATION_UNRESOLVED`
- `COREFERENCE_UNRESOLVED`

标记歧义的目的是进入人工裁决，不能用它绕过 span、来源或 Schema 校验。

## 9. 人工标注与裁决流程

1. 从200份 pilot 中按患者分组建立50份 calibration 和150份 blinded evaluation；同一患者不能跨组。
2. calibration 由两名标注者独立标注；任何讨论只能在双方提交后进行。
3. 逐项计算实体 exact/relaxed span＋type 一致性、属性一致性和显式关系一致性。
4. 分歧由第三人裁决，保留原始两份标注和裁决记录，不覆盖历史。
5. 若修改实体类型、属性语义、span 原则或关系方向，协议必须升版本，并在新的 calibration 子集重新开始；不能用旧结果继续计算。
6. 协议稳定后，150份 evaluation 继续双标并裁决，形成模型 pilot 的人工参考集。

## 10. 进入模型 pilot 的 Go/No-Go 门禁

### 硬性工程门禁

- JSON Schema 通过率100%。
- mention surface/span、relation evidence/span 和来源哈希通过率100%。
- lineage ID 缺失、重复 ID、悬空关系、`post_hoc` 混入均为0。
- 原始 MIMIC 文本不发送到普通第三方 API。
- 本地运行器必须默认 dry-run，只有显式 `--execute` 才能调用模型。

### 人工协议门禁

- calibration exact span＋type micro-F1 ≥ 0.85。
- relaxed span＋type micro-F1 ≥ 0.90。
- assertion macro-F1 ≥ 0.90。
- temporality、experiencer macro-F1 均 ≥ 0.90。
- 显式关系 exact F1 ≥ 0.80。
- 把否定事实当阳性、把家族史当患者事实、把建议当已执行事件等严重错误为0。

任何门禁失败时回到协议或标注训练解决根因；不得降低阈值、吞掉失败记录或用后处理删除困难样本。

## 11. 当前结论

真实 pilot 的聚合范围演练已通过，覆盖否定、不确定、比较/历史、建议、测量、侧别、器械和时间表达。患者隔离的人工包也已生成：50份calibration和150份锁定evaluation，患者交叉0；A/B拥有相同任务集合但不同顺序，决定日志和裁决日志初始为空。该结果证明Schema和人工工作输入已准备完成，但不证明人工一致性或模型质量。下一步是A/B独立完成calibration、第三人裁决并计算预设指标；在其通过前，不解锁evaluation，也不开始模型NER。
