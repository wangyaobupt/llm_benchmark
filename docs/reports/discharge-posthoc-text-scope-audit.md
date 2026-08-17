# 出院小结 post-hoc 文本抽取范围审计

## 结论

出院小结应当进入文本抽取与patient journey回顾支路，但不能直接进入前瞻性检查选择快照。

当前100例文本输入中，88份出院小结共有1,145,655个字符，占全部ED主诉、放射报告和出院小结字符的70.0%。因此，将其永久排除会丢失文本主体；但将其作为检查决策时点的可见输入，又会直接泄漏检查、结果、最终诊断、治疗和结局。

正确边界是：

```text
出院小结
  ├─ retrospective_journey_view：纳入，标记post_hoc
  ├─ corpus/schema discovery：纳入
  ├─ gold候选与错误分析：可使用，但必须声明来源阶段
  └─ prospective_snapshot_view：禁止直接纳入
```

本审计只覆盖`data/mimic-admission-raw-coronary-all-three-modules-random-100.jsonl`中的100次住院样本，不能外推为完整冠状动脉疾病谱队列统计。

## 1. 当前manifest为什么排除出院小结

现有`text_ner_input_manifest.parquet`包含2,812行：

| 来源 | 文档数 | manifest状态 | 原因 |
|---|---:|---|---|
| ED chief complaint | 100 | included | `NER_ELIGIBLE_ED_CHIEF_COMPLAINT` |
| Radiology | 443 | included | `NER_ELIGIBLE_RADIOLOGY` |
| Discharge summary | 88 | excluded | `POST_HOC_DISCHARGE` |

出院小结并未从来源合同中消失。当前代码读取`mimic_iv_note.discharge`，保存文档身份、原始哈希、`charttime`、`storetime`和来源位置，但故意不生成可供当前NER pilot使用的section。

所有88份出院小结均满足：

- `note_type=DS`；
- `time_policy_id=discharge_post_hoc_v2`；
- `evidence_phase=post_hoc`；
- `available_time=storetime`；
- `reason_code=POST_HOC_DISCHARGE`。

当前样本没有`AD`类型的出院补充记录。

## 2. 文本规模

按唯一文档统计：

| 来源 | 文档数 | 总字符数 | 平均字符数 | 中位字符数 | 全部字符占比 |
|---|---:|---:|---:|---:|---:|
| Discharge summary | 88 | 1,145,655 | 13,018.8 | 11,978 | 70.0% |
| Radiology | 443 | 490,664 | 1,107.6 | 733 | 30.0% |
| ED chief complaint | 100 | 1,490 | 14.9 | 14 | 0.1% |

单份出院小结长度范围为3,491–27,406字符。每份文档可检测到13–42个章节标题，中位数为24。

这说明ED主诉适合校准短文本症状span，放射报告适合校准发现、测量和显式关系；二者不能替代出院小结中的完整住院过程表达。

## 3. 时间语义

### 3.1 `charttime`不能作为前瞻性可用时间

相对于正式`dischtime`：

- `charttime-dischtime`中位数为-16.75小时；
- 最早为-22.25小时；
- 最晚为0小时；
- 只有1/88份的`charttime`位于或晚于正式出院时间。

这反映`charttime`更接近出院日期的文档标签时间，不证明全文在该时点已被临床使用者看到。

### 3.2 `storetime`仍然表明文书属于末期或出院后材料

相对于正式`dischtime`：

- `storetime-dischtime`中位数为+10.07小时；
- 最早为-4.15小时；
- 最晚为+366.98小时；
- 71/88份在正式出院时或之后存储。

即使17份在正式出院前存储，文书内容仍总结整次住院，不能据此拆回早期决策时点。所有出院小结继续统一标记`post_hoc`，避免按单份文档偶然时间差放宽规则。

## 4. 章节覆盖

严格按独立英文标题行进行聚合，不保存或输出任何患者原文。核心章节覆盖如下：

| 章节 | 覆盖文档数 / 88 |
|---|---:|
| Allergies | 88 |
| Pertinent Results | 88 |
| Discharge Condition | 88 |
| Discharge Instructions | 88 |
| Followup Instructions | 88 |
| Major Surgical or Invasive Procedure | 87 |
| History of Present Illness | 86 |
| Past Medical History | 86 |
| Family History | 86 |
| Discharge Medications | 86 |
| Physical Exam | 85 |
| Social History | 85 |
| Discharge Disposition | 85 |
| Chief Complaint | 84 |
| Medications on Admission | 82 |
| Discharge Diagnosis | 82 |
| Brief Hospital Course | 73 |
| Transitional Issues | 36 |
| Admission Labs | 28 |
| Discharge Labs | 23 |
| Imaging | 20 |
| Studies | 6 |

`discharge_detail`在本样本中只有44行，`field_name`全部为`author`，不提供可替代出院正文的临床内容。

## 5. 当前NER Schema覆盖情况

### 5.1 可以复用的基础mention层

当前`section-annotation/1.0.0`的9类mention可以继续覆盖：

- 症状和体征：`symptom_or_sign`；
- 疾病和诊断：`clinical_problem`；
- 影像表现：`imaging_finding`；
- 解剖部位：`anatomical_site`；
- 检查和操作：`procedure_or_test`；
- 器械：`device`；
- 药物和物质：`medication_or_substance`；
- 数值测量：`measurement`；
- 时间表达：`temporal_expression`。

exact span、assertion、experiencer、laterality、severity、trend和来源哈希合同也可以复用。

### 5.2 不能由现有mention和7类关系完整表达的内容

| 缺口 | 当前后果 | 所需表达能力 |
|---|---|---|
| 药物剂量、途径、频率、开始/停止和出院携带状态 | 只能识别药名，无法重建治疗过程 | medication event frame与属性 |
| 检查与结果的对应关系 | 检查名、测量值和发现彼此分离 | `result_of`或等价受约束关系 |
| 问题—干预—反应链 | 无法表示为何治疗及治疗后的变化 | `treatment_for`、`response_to`等文本显式关系 |
| 过敏原与反应 | `Allergies`章节只能被粗略拆成药物和问题 | allergy event frame |
| 出院去向与照护场所 | 现有9类没有care setting/disposition | care transition结构 |
| 随访、复查和出院指导 | 只能把部分检查标成`future_planned` | plan/instruction frame及责任对象 |
| 住院阶段 | `current/historical/future_planned`不足以区分入院时、住院中、出院时 | section role＋episode phase |
| 跨章节与跨文档共指 | 当前关系限定在单section | 独立的document/admission consolidation层 |

因此，直接把出院全文塞进当前标注工具会产生大量`ENTITY_TYPE_AMBIGUOUS`和`RELATION_AMBIGUOUS`，并不能形成完整patient journey。

## 6. 推荐架构

不修改当前ED/radiology calibration包，也不把出院小结并入其50/150分组。新增独立的`discharge_posthoc`支路。

```text
原始discharge text（只读）
  → span保持型章节解析
  → 基础mention层（复用9类实体）
  → discharge event-frame层
  → Python schema/span/hash验证
  → 人工A/B校准与裁决
  → retrospective_journey_view
  → prospective snapshot显式拒绝
```

### 6.1 第一层：章节与mention

- 为discharge建立独立章节标题词表和归并表；
- 输出必须覆盖全文且section span无重叠、无缺口；
- 保留原始标题和规范化section role；
- 复用现有9类mention，不在此层做术语标准化；
- 不从章节标题自动生成患者事实。

### 6.2 第二层：event frame

建议建立与mention分离的出院事件合同，至少覆盖：

- `problem_state`；
- `investigation_result`；
- `medication_course`；
- `procedure_course`；
- `allergy`；
- `discharge_state`；
- `care_transition`；
- `followup_plan`。

每个frame必须引用一个或多个已验证mention和连续原文证据。文本明确表达的关系与跨文档工程推断必须使用不同字段，不能混写。

### 6.3 时间与下游路由

所有出院事实固定携带：

```json
{
  "available_time": "<storetime>",
  "evidence_phase": "post_hoc",
  "prospective_snapshot_eligible": false
}
```

若出院小结回顾“入院时胸痛”，该mention可以进入回顾性journey；只有在ED主诉或其他早期来源中找到独立证据，才能生成一条可进入早期snapshot的事实。不能把出院文本自己的时间描述当成当时可用证据。

## 7. 探索性标注包路线

### 阶段A：全88份只读section rehearsal

- 解析章节，不做NER；
- 输出聚合章节覆盖、长度分层和异常标题；
- 验证全文字符守恒、span无重叠无缺口；
- 原文只保存在Git忽略的本地派生目录。

### 阶段B：10份schema shakedown

从87名患者中按患者整体抽取10份文档，覆盖短/中/长文本、常见章节和复杂hospital course。10份只用于发现schema缺口，不计算或宣称正式一致性。

### 阶段C：正式A/B calibration

在shakedown后冻结discharge协议版本，再决定正式calibration规模。A/B必须患者隔离、任务相同顺序不同、彼此不可见；裁决保留双方原始决定。正式规模不能沿用探索性10份，也不能未经依据照搬ED/radiology的50份。

### 阶段D：模型方法试验

只有人工协议门禁通过后才能生成模型请求。默认dry-run，受限原文不得发送普通第三方API。

## 8. 验收标准

### 工程门禁

- 88份源文档全部对账；
- note、subject、admission和raw row lineage缺失为0；
- 原始文本SHA-256一致率100%；
- section全文字符守恒率100%；
- section重叠、缺口和越界为0；
- 所有事实均为`evidence_phase=post_hoc`；
- `prospective_snapshot_eligible=true`数量为0；
- evaluation、当前50/150包和原始JSONL均不被改写；
- 模型调用为0。

### 方法学门禁

- 基础mention与event frame职责分离；
- 否定、历史、住院中、出院时和未来计划不互相替代；
- 检查建议不编译为已完成检查；
- 出院药物不反推为整个住院期间持续使用；
- 出院诊断不反推为入院时已知诊断；
- 出院小结中的早期事实未经独立早期来源确认，不进入前瞻性snapshot；
- schema不能覆盖的现象形成显式讨论清单，不创建`other`兜底类型。

## 9. 当前停止点

本次已完成只读范围审计和独立支路设计，尚未：

- 修改现有manifest逻辑；
- 创建discharge任务包；
- 决定正式calibration样本量；
- 解锁evaluation；
- 调用任何模型。

下一项可执行工作是实现“全88份span保持型section rehearsal＋独立聚合审计”，随后再生成10份`schema shakedown`任务包。
