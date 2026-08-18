# Benchmark 检查选择金标准重建实施计划

> 文档状态：已确认，待按工作包实施
>
> 最近修订：2026-08-19
>
> 本轮适用范围：MIMIC-IV 冠心病现有数据及 MIMIC-IV 多诊断扩展
>
> 当前 gold：`0`；现有候选均为 `exploratory_unreviewed`
>
> 硬约束：旧 `data_pipeline/phenotype` 代码与“8 类 phenotype 特征”设计全部弃用，不从中复制逻辑。

## 0. 执行结论

先重建“在什么时点、当时能看到什么、预测什么检查”的数据合同，再处理高频常规检查遮蔽和诊断单一化。执行顺序固定为：

1. 失效旧 V2 候选并冻结任务语义；
2. 补齐到诊、入院、医嘱、采样、结果可见和文档签署的统一时间轴；
3. 从正式 snapshot 构建 `decision_document`；
4. 建立检查/检验的 order、specimen、result 三类 episode；
5. 在 development 内比较 frequency、lift、TF-IDF/BM25 和收缩 log-RR；
6. 按来源、检查类别、时间窗、频率层分别验证；
7. 扩展多诊断数据后重新生成规则与题目；
8. 临床审核通过前，gold 始终保持为 0。

两条不可绕过的源数据事实：

- MIMIC 普通检验没有独立 `specimen_received_time`。`labevents.charttime` 只能叫“标本采集时间代理”，`labevents.storetime` 是结果在实验室系统可见的时间，二者都不能冒充“实验室收到样本时间”。
- MIMIC 的 POE Lab 绝大多数只有泛化 `Lab` 类别，不能从 `labevents.itemid` 或时间邻近关系伪造项目级医嘱。本轮只构建 `generic_lab_order` 和明确命名的 `result_availability_proxy`，不接入香港 RWD，也不声称获得项目级检验 order gold。

### 0.1 已确认并冻结的执行决策

| 决策 | 冻结结果 | 对代码和产物的直接影响 |
|---|---|---|
| 旧 134 道候选 | 整体失效 | W0 建失效 manifest；审核、发布和新统计入口必须拒绝旧 candidate/rule IDs |
| 旧 final-test | 不再作为新 V2 正式盲测集 | subjects 固定为 `engineering_audit_only`；新 final-test 只能来自 exposure registry 中从未使用的 subjects |
| 香港 RWD | 本轮不纳入 | 不读取其数据/字典，不实现 connector，不把 RWD 覆盖或字段作为 W0–W10 验收条件 |
| 本轮数据源 | 仅 MIMIC-IV | Lab 只分 `generic_lab_order` 与 `lab_result_proxy`；项目级 Lab order gold 保持 unavailable |

这些决策已由用户确认，不在 W1 再次讨论，也不能因候选数量不足而回退。未来若单独启动香港 RWD 工作，必须另建协议、source contract 和计划，不修改本轮冻结语义。

## 1. 当前项目实际进度复核

### 1.1 已完成、部分完成与不可使用产物

| 层级 | 实际状态 | 可继续复用 | 不可继续声称或使用 |
|---|---|---|---|
| 冠心病原始归档 | 已完成 | 108,833 次住院、46,062 名患者的疾病谱归档与源表抽取方式 | 不能代表多诊断 MIMIC 队列 |
| 三模块事件批 | 工程运行完成 | 39,036 次住院、20,136 名患者、27,336,811 条规范事件；lineage、manifest、事件 schema 和 transformer | 归一化人工复核未完成，不能称临床语义全部冻结 |
| event aggregation | 1,000 例验收 | lossless aggregation 合同与样本测试 | 尚未完成 39,036 住院全量聚合 |
| protocol/split/journey/snapshot | 合同和合成测试已存在 | `evaluation_pipeline/journey`、`evaluation_pipeline/snapshot` 的 fail-closed 代码 | 正式 protocol lock、真实 split、真实 boundary/snapshot 产物尚不存在 |
| 文本 NER | 工程接口与未审核输出存在 | 可作为开发输入和错误分析材料 | 人工双标与裁决为 0，不可作为 formal 特征或 gold |
| V1 | 冻结历史基线 | 用于说明模板题和高先验偏倚 | 不作为新管线输入；随访没有 MCQ gold |
| 旧 phenotype | 已运行但科学合同不合格 | 无 | 全部代码、8 类设计、特征表、条件表均不采用 |
| 旧 V2 | 134 道未审核候选 | 仅保留审计记录 | 全部失效，不送审、不发布、不作为新统计基线 |

### 1.2 现有 event 层的准确边界

现有 `clinical_event/1.2.0` 已经提供：

- `event_time`、`source_available_time`、`available_time`、`recorded_time`；
- `source_concept_id`、`concept_id`、`preferred_name`、`normalization_status`；
- 数值、单位及异常标记归一化；
- `source_table`、`raw_row_ref`、supporting refs；
- `time_policy_id`、`time_resolution_reasons`、`evidence_phase`、`quality_flags`；
- unresolved 项进入 review queue 的 fail-closed 机制。

因此本计划不重做 event schema 或 transformer。只补两个已验证的缺口：

1. `labevents.specimen_id`/`micro_specimen_id` 尚未在规范事件中提供可稳定聚合的分组键；
2. `edstays.intime`、`admissions.edregtime/admittime` 属于 encounter context，现有 `encounter_manifest.parquet` 只有处理计数，没有临床时钟。

三个使用边界：

- `labevents.charttime` 的官方限定是“通常为标本采集时间”，故工程语义是 `specimen_collection_time_proxy`，不能无条件写成精确抽血时刻；
- ED 主诉可完成概念归一化并保留原始行定位，但如果 occurrence/availability 时间均未知，就不能直接进入小时级前瞻 snapshot；
- 药物 `normalization_status=unresolved` 继续进入复核队列，不用 `source_label` 猜 concept，也不进入需要冻结 concept 的 formal 条件空间。

### 1.3 旧 V2 实际链路必须补入进展文档

```text
1,584 条 formal accepted 规则
  → 738 条去重规则
  → 165 条收敛规则
  → 134 道候选题
  → 0 道人工批准 gold
```

1,584 条规则全部属于 imaging，其中 1,102 条含出院 ICD 派生的 post-hoc `past_condition`。该链还混入 validation/final-test sidecar，并使用未冻结的全住院目标窗口，因此 134 道题必须整体失效，不能只删除明显泄漏题。

### 1.4 `BenchMark-进展梳理.md` 修订清单

| 现有表述 | 复核结论 | 必须改成 |
|---|---|---|
| clean 层已字典解码具体检查、检验项目 | 部分错误 | 检验结果 `labevents.itemid → d_labitems` 可到 analyte 级；POE Lab 没有项目键，不能解码具体开单 |
| normalized events 已“归一化完成” | 过强 | 工程转换完成；12,236,240 条 unresolved、15,316 个 review keys 仍需冻结 |
| phenotype 已形成预测点快照 | 错误 | 旧 phenotype 未使用正式 snapshot，忽略 `available_time` 并摄入 post-hoc 内容 |
| phenotype 为 8 类特征 | 不再采用 | 删除此设计；新输入按“可见临床事实合同”组织，不预设 8 类 |
| 当前是 ICU 单病种 | 错误 | 当前是冠心病谱 HOSP+ED+Note 队列，ICU 不是入选必要条件 |
| BMP/CBC 几乎人人做 | 只在特定口径成立 | 必须按数据源、candidate class、index、目标窗和分母分别报告 |
| V2 题目进展 | 缺失 | 补入 1,584→738→165→134、gold=0 和整体失效原因 |

W0 中，根目录进展文档只保留当前状态摘要并链接本计划；不得继续复制另一套数字形成双事实源。

### 1.5 全库扫描与代码复核证据

本次扫描快照共识别 206 份 Markdown，覆盖 `docs/`、`data_pipeline/`、`tests/`、`versions/`、`mcq_generation/`、调研目录和历史交接目录；`rwd_pipeline/` 仅作为历史材料，不作为当前实现依据。代码重点逐项核对 event contracts/transformers、journey/snapshot、旧 phenotype、V2 catalog/mining/generation/review 和 investigation protocol。

旧 phenotype/V2 的可复现问题包括：

| 问题 | 实际证据 | 对统计的影响 |
|---|---|---|
| split sidecar 未过滤 | 特征表比 manifest 多 360 个住院：validation 184、final-test 176；346 个进入条件组合 | 改变 development 分母、lift 和 FDR |
| post-hoc ICD | 1,584 条旧 accepted 规则中 1,102 条使用出院 ICD 派生条件 | 目标后诊断进入题干 |
| discharge sign | 出院小结 Physical/Admission/Discharge Exam 未保留实体时间与审核状态 | 住院后状态可能成为早期特征 |
| available time 未使用 | 私有门禁只比较 `event_time`，未知时间还可默认可用 | 晚入库结果和未知主诉可能泄漏 |
| 组合静默截断 | 23,127 个有组合住院中 11,747 个触及每住院 500 cap | 条件空间受 feature ID 顺序控制 |
| 分母 inner join | 没有同类 target 的条件文档不进入 `n_x` | 条件概率、Lift、Wilson 指标向上偏 |
| bootstrap 单位错误 | 协议要求 subject，代码按 `hadm_id` 重采样 | 多次住院被当作独立个体 |
| 目标窗未冻结 | laboratory 用全住院 result，其他类用全住院 order | “下一步选择”漂移为“最终做过” |
| Lab order 不具项目名 | 969,587 条 laboratory order 中 969,558 条只有 category，另 27 条仅 subtype、2 条 attribute-enriched | MIMIC 无法建立项目级 lab order gold |
| normalization pending | 12,236,240 条事件 unresolved，15,316 个 review keys 待审核 | 工程转换完成不等于临床概念冻结 |

已有测试“全绿”只证明旧代码按自己的预期运行，不能抵消错误科学合同。新测试必须让上述注入场景 fail-closed。

### 1.6 文献证据的使用边界

- [OrderRex（JAMIA 2016）](https://pubmed.ncbi.nlm.nih.gov/26198303/) 支持把就诊早期信息与后续医嘱分窗，并用相对风险降低纯高频预测偏倚；它不直接证明本项目的窗口或 gold。
- [医疗知识图谱 PSR（Artificial Intelligence in Medicine 2020）](https://pubmed.ncbi.nlm.nih.gov/32143785/) 说明特异性与可靠性结合可优于单纯 TF-IDF；它不是检查选择的临床验证。
- [Order frequency–inverse patient frequency（PLOS Digital Health 2024）](https://doi.org/10.1371/journal.pdig.0000606) 支持 EHR 表示中的逆患者频率；其任务是风险建模，不是检查 order gold。
- [罕见病患者 TF-IDF 检索（Journal of Biomedical Informatics 2017）](https://doi.org/10.1016/j.jbi.2017.07.016) 支持将 TF-IDF 用于患者相似检索。

因此 TF-IDF 在本项目中是待配对验证的召回方法，不是由文献直接确立的最终排名或 gold 生成规则。

## 2. 术语和研究对象

### 2.1 `decision_document` 不是“整次住院”

一个 `decision_document` 表示一次明确决策时点的统计样本：在某患者、某次就诊、某个 `index_time`，只取当时真实可见的信息作为 query，并把冻结目标窗内同类检查 episode 作为 target。

```text
ED 到诊 00:00
  ├─ 02:10 影像决策文档：输入为 02:10 前可见事实，目标为该时点影像 order set
  ├─ 03:40 临床检查文档：输入为 03:40 前可见事实，目标为该时点临床 order set
  └─ 固定窗检验代理文档：输入 [00:00,04:00)，目标为 [04:00,28:00) 首次可见结果 bundle
```

整次住院前后状态会变化；把它作为一个文档会把目标后的信息和重复监测混到同一袋中。新设计使每条规则都能回答“当时已知什么、随后发生什么”。

### 2.2 “二元就诊文档”的准确含义

“二元”不是把内容压缩成两个字段，而是候选在一个 `decision_document` 中的词频只取 `0/1`：出现一次或多次均为 1，未出现为 0。这样 RBC 重复测 8 次不会得到 8 倍权重。重复次数可作为 `1+log(count)` 消融，但不进入主分析。panel 与 component 分开统计，不能把 CBC、RBC、Hemoglobin、Hematocrit 同时当成四个独立开单。

### 2.3 “放大罕见噪声”不只指一次性检查

罕见噪声指 `df`、患者数或共同支持很低，却因偶然共现获得很高 IDF/lift 的候选。只出现一次是极端情形，出现 2–20 次也可能是噪声。门禁同时使用 development `document_frequency`、独立患者数、共同患者数、收缩 log-RR、subject-level bootstrap、validation 稳定性和临床审核。单次项目一定拒绝；但“不是一次”不等于可靠。

### 2.4 “归一化”要完成什么

归一化不是把项目粗暴合并，而是保留原始事实并建立稳定概念层：

```text
source_label / source_concept_id（原始事实）
  → component concept（RBC、Hemoglobin、Creatinine）
  → panel membership（CBC、BMP；版本化临床目录）
  → comparison class（血液学、代谢、影像模态等）
```

四类任务是：字典解码、同义词统一、component/panel 层级建模、单位和值统一。`RBC → CBC` 只能表达 membership，不能把 RBC 改名为 CBC，也不能仅看到 RBC 就断言完整 CBC。禁止从泛化 POE Lab 猜项目、从时间邻近猜 order-result 链接、把不完整 component 集合标为完整 panel、用未审核 LLM 输出冻结概念。

## 3. 统一临床时间轴

### 3.1 时间轴对象

```text
ED 实际进入/登记 → 医院入院 → 临床事实发生 → 医嘱创建
→ 标本采集 → 标本接收（仅源系统真实提供时） → 检查/检验执行
→ 部分/完整结果可见 → 文档完成/签署 → 医院出院
```

规范事件继续保留现有四类时间及其 policy/reasons；新增的是 encounter clock 和 specimen grouping，不另建重复事件体系。

### 3.2 到诊、登记和入院

| 中文语义 | MIMIC 来源 | 原始 JSON | 当前 Parquet | 新合同用途 |
|---|---|---|---|---|
| 进入急诊 | `edstays.intime` | `mimic_iv_ed.edstays[].intime` | 不在 normalized events；encounter manifest 也不保存 | `ed_arrival_time`，ED-linked 任务首选 origin |
| 离开急诊 | `edstays.outtime` | `mimic_iv_ed.edstays[].outtime` | 同上 | `ed_departure_time` |
| 急诊登记 | `admissions.edregtime` | `mimic_iv_hosp.admissions[].edregtime` | 同上 | `ed_registration_time`，独立交叉审计 |
| 急诊离科 | `admissions.edouttime` | `mimic_iv_hosp.admissions[].edouttime` | 同上 | ADT 来源离科时间 |
| 医院入院 | `admissions.admittime` | `mimic_iv_hosp.admissions[].admittime` | boundary 单独消费 | `hospital_admit_time`；非 ED 住院 origin |
| 医院出院 | `admissions.dischtime` | `mimic_iv_hosp.admissions[].dischtime` | boundary 单独消费 | encounter end，不进入前瞻输入 |

官方依据：[ED `edstays`](https://mimic.mit.edu/docs/iv/modules/ed/edstays.html)、[HOSP `admissions`](https://mimic.mit.edu/docs/iv/modules/hosp/admissions.html)。

锚点规则：ED-linked 任务优先 `edstays.intime`；`edregtime` 独立保留，不与其无条件 `coalesce`；只有登记时间时 origin 类型写 `ed_registration`；非 ED 住院任务使用 `admittime`；多 ED stay、时序倒置或冲突超过冻结阈值时正式样本 fail-closed 排除。

W2 新建 `encounter_clock.parquet`。现有 `encounter_manifest.parquet` 继续只做行数/事件数审计，不承担临床边界语义。

### 3.3 医嘱、检验和文档时间

| 对象 | 源字段 | 官方语义 | 新用途 | 禁止解释 |
|---|---|---|---|---|
| POE 医嘱 | `poe.ordertime` | provider order was made | `order_created_time` | 执行、采样、接收或结果时间 |
| 普通检验标本 | `labevents.specimen_id` | 同一标本分组键 | specimen/result bundle | 不能从 ID 推断时间 |
| 普通检验 | `labevents.charttime` | charted；通常为采集时间 | `specimen_collection_time_proxy` | 接收时间或精确 order time |
| 普通检验 | `labevents.storetime` | 结果在实验室系统可见 | component `result_available_time` | 接收、采集或开单时间 |
| 微生物 | `microbiologyevents.charttime` | 官方示例支持采样时间 | `specimen_collection_time` | 接收或结果可见 |
| 微生物 | `microbiologyevents.storetime` | 最后已知更新时间 | `microbiology_last_update_time` | 首次 interim result |
| 放射报告 | `radiology.charttime/storetime` | charted / 通常完成签署 | 内容时间 / 保守可见代理 | 影像开单或执行时间 |
| 出院小结 | `discharge.storetime` | 通常完成签署入库 | 回顾性 NER；post_hoc | 早期 snapshot 输入 |

官方依据：[POE](https://mimic.mit.edu/docs/iv/modules/hosp/poe.html)、[`labevents`](https://mimic.mit.edu/docs/iv/modules/hosp/labevents.html)、[`microbiologyevents`](https://mimic.mit.edu/docs/iv/modules/hosp/microbiologyevents.html)、[radiology](https://mimic.mit.edu/docs/iv/modules/note/radiology.html)、[discharge](https://mimic.mit.edu/docs/iv/modules/note/discharge.html)。

### 3.4 “采用化验单收到样本时间”的本轮落地规则

- 本轮仅处理 MIMIC-IV：`specimen_received_time=null`、`specimen_received_time_status=source_insufficient`；普通检验保留采集代理 `charttime` 和结果可见 `storetime`。
- 不读取香港 RWD，也不为其预留会参与当前运行的空 connector、配置项或验收分支。
- 不得用二者中点、同一 specimen 最早时间、最近 POE 或模型推断补造接收时间。
- “收到样本时间”需求记录为未来独立数据源项目的前置 source-contract 要求，不改变本轮 MIMIC 语义。

### 3.5 可见性规则

进入 query 的每条事件必须同时满足：

```text
event_time < index_time
AND available_time <= index_time
AND evidence_phase not in {post_hoc, administrative_end}
AND split_role permitted
AND source/time semantics allowed by frozen policy
```

目标 order 本身不进入同一时点的 query；已有事实允许 `available_time == index_time`。未知 occurrence/availability 在没有明确结构性先后证据时拒绝。date-only 时间不能假装为当天 00:00。

## 4. 检查与检验 episode 合同

### 4.1 三类对象不能混用

| track | 目标对象 | MIMIC 可支持的声明 | 主时间 |
|---|---|---|---|
| `imaging_order` | 可识别影像 order episode | 观察到的下一组影像医嘱 | `poe.ordertime` |
| `clinical_order` | 可识别临床检查/监护 order episode | 观察到的下一组同类医嘱 | `poe.ordertime` |
| `generic_lab_order` | 类别级 Lab POE | 随后创建泛化 Lab 医嘱 | `poe.ordertime` |
| `lab_result_proxy` | specimen 下 component/panel bundle | 目标窗内结果首次/完整可见 | `storetime`；发生代理另存 `charttime` |

不同 track 单独建目录、分母、频率层和排行榜，不生成跨 track 选择题。

### 4.2 component、panel 与 CBC/BMP

正式目录同时保留 `candidate_level=component|panel`、`panel_completeness=complete|partial|extra_components|unknown`、`panel_definition_version` 和实际 component 集合。同一 `specimen_id` 内聚合；panel 主分析计一次，components 另行报告，二者不进入同一竞争集合。

当前手写 RBC→CBC 占位映射作废。W4 经官方项目字典、共现审计和临床冻结后生成目录。普通检验 bundle 输出：

- `first_component_available_time=min(component.storetime)`；
- `all_required_components_available_time=max(required component.storetime)`，仅 complete panel 有值。

主 panel 结果代理使用完整 panel 可见时间；partial panel 只进入 component 分析。

### 4.3 对现有 event 合同的最小增量

不改变已有四类时间和归一化字段。只在不丢失原始 lineage 的前提下增加：

| 字段 | 约束 | 用途 |
|---|---|---|
| `source_group_type` | nullable：`lab_specimen`、`microbiology_specimen`、`poe_order`、`report` | 分组语义 |
| `source_group_id` | 稳定去标识 hash | 跨 component 构建 episode |
| `source_group_id_status` | `observed|derived|unavailable` | 区分真实源键与派生键 |
| `time_semantics` | 版本化枚举；与现有 `time_policy_id` 一一对应 | 明确 `event_time` 的源语义 |

这四个字段作为现有 `clinical_event` 的顶层最小增量，统一更新 JSON/Arrow schema、transformer、audit 和 schema version。原因是 episode 构建必须按 specimen/order 高效分组并做非空、唯一性和来源一致性校验；藏入自由 JSON 会削弱合同。禁止建立与现有 event 平行的第二套事件文件，也不改动已有时间、概念和值字段的含义。

## 5. `decision_document` 数据合同

### 5.1 四个正式产物

1. `decision_documents.parquet`：一行一个决策；
2. `decision_evidence.parquet`：`decision_id ↔ event_id`；
3. `decision_targets.parquet`：`decision_id ↔ episode_id ↔ candidate_id`；
4. `decision_manifest.json`：schema、协议、输入输出 hash、计数和 Git commit。

### 5.2 决策主表

| 字段 | 中文语义 | 来源 | 缺失门禁 |
|---|---|---|---|
| `schema_version` | 合同版本 | 常量 | 拒绝 |
| `decision_id` | 稳定决策 ID | protocol+journey+node+class hash | 重复拒绝 |
| `subject_ref` | 去标识患者引用 | split manifest | 不输出原 ID |
| `admission_ref` | 去标识住院引用 | boundary manifest | 未匹配拒绝 |
| `journey_id` | 旅程 ID | boundary manifest | 未认证拒绝 |
| `split_role` | 数据角色 | split manifest | 跨 split 拒绝 |
| `encounter_origin_type/time` | ED 到诊/登记或入院起点 | encounter clock | 未声明/冲突拒绝 |
| `hospital_admit_time` | 医院入院 | admissions | 可空但要有状态 |
| `index_policy_id` | 节点策略 | protocol | 拒绝 |
| `index_event_id/index_time` | 触发事件与截断时间 | order episode 或固定窗 | 与策略不符拒绝 |
| `query_window_start/end` | 输入窗口 | protocol | 非法区间拒绝 |
| `target_window_start/end` | 目标窗口 | protocol | 非法区间拒绝 |
| `candidate_class` | 同类比较空间 | versioned catalog | 未知拒绝 |
| `target_semantics` | order/result proxy | track | 混轨拒绝 |
| `zero_candidate_observed` | 目标为零 | targets 计数 | 必须保留作分母 |
| `eligibility_status` | eligible/excluded | validator | formal 只读 eligible |
| `exclusion_reason_codes` | 机械原因码 | validator | excluded 必须非空 |
| `snapshot_sha256` | 可见证据 hash | evidence canonical hash | 拒绝 |
| `protocol_lock_sha256` | 协议 hash | protocol lock | 不匹配拒绝 |
| `subject_split_manifest_sha256` | split hash | split manifest | 不匹配拒绝 |
| `boundary_manifest_sha256` | boundary hash | boundary manifest | 不匹配拒绝 |
| `source_input_sha256` | 事件输入 hash | workflow manifest | 不匹配拒绝 |

### 5.3 证据表与目标表

`decision_evidence.parquet` 至少包含 `decision_id,event_id,feature_concept_id,event_time,available_time,visibility_policy_id,evidence_role`。

`decision_targets.parquet` 至少包含 `decision_id,episode_id,candidate_id,candidate_level,target_occurrence_time,target_available_time,target_semantics,is_primary_target`。

### 5.4 原始 JSON → 现有 Parquet → 新合同

| 内容 | 原始 JSON | 当前规范 Parquet | 新合同 |
|---|---|---|---|
| ED 到诊 | `mimic_iv_ed.edstays[].intime` | 未进入 normalized events | encounter clock → origin |
| 医院入院 | `mimic_iv_hosp.admissions[].admittime` | boundary 单独消费 | encounter clock |
| 项目医嘱 | `poe[].ordertime/order_type/order_subtype/poe_id` 或 `poe_timeline` | `*_ordered` 有 event/available time | order episode → index/target |
| 泛化 Lab | 同上，仅 `order_type=Lab` | `laboratory_ordered` + category-only flag | 仅 generic lab order |
| 普通检验 | `labevents[].specimen_id/itemid/charttime/storetime` | 有时间与 analyte，缺 specimen 分组 | specimen/component/panel episode |
| 微生物 | `microbiologyevents[].micro_specimen_id/charttime/storetime` | 有规范事件 | microbiology episode |
| 放射报告 | `radiology[].charttime/storetime` | note/report event | 报告证据，不代替 order |
| 出院小结 | `discharge[].charttime/storetime/text` | post-hoc note/NER | 回顾性 NER，不进 query |

当前仓库没有上述 decision 产物，W5 才会正式生成。

### 5.5 合成端到端示例

```text
edstays.intime                    2100-01-01 08:00  → encounter_origin_time
poe imaging ordertime             2100-01-01 09:10  → target order episode / index_time
labevents specimen 77 charttime   2100-01-01 08:35  → specimen_collection_time_proxy
labevents specimen 77 storetime   2100-01-01 09:25  → result_available_time
```

09:10 的影像 order 文档不能看到 09:25 才可见的检验结果，即使其采集代理时间是 08:35。若为 CBC result-proxy 文档，先根据冻结 panel 目录判断 complete/partial，再使用相应可见时间；`specimen_received_time` 为空。

## 6. 两个核心问题的统计解决方案

### 6.1 Lift 为什么没有解决 CBC/BMP 支配

旧流程存在四个结构问题：分母删除零目标文档；全住院结果冒充开单；panel/components/重复测量放大频率；所有 class 和时间窗混合解释。此外，若 CBC 基线覆盖为 0.9133，其 lift 上限约为 `1/0.9133=1.095`，固定 `min_lift=1.2` 会在数学上排除它，却不真正解决候选空间。

主方案是先修复研究单位和候选层级，再将 TF-IDF 用于召回、收缩 log-RR 用于规则排名。

### 6.2 TF-IDF 的职责边界

\[
idf(y)=\log\frac{N+1}{df(y)+1}+1
\]

`N` 是全部 eligible decision documents，包括零目标文档；`df(y)` 是含候选 y 的文档数，不是事件行数。词表与 IDF 只从 development 拟合。

配对比较 `frequency`、修正分母后的 `lift`、`tfidf_retrieval`、`bm25_retrieval` 和主路径 `shrunk_log_rr`。TF-IDF 不与 Lift 直接相乘。

### 6.3 收缩与验证

\[
\widehat{\log RR}_{shrunk}
=\frac{n_{xy}}{n_{xy}+\lambda}
\log\left(
\frac{(n_{xy}+\alpha)/(n_x+2\alpha)}{(n_y+\alpha)/(N+2\alpha)}
\right)
\]

`n_x` 必须包含条件出现但目标为零的 eligible 文档；bootstrap 单位是 `subject_ref`；FDR family 在看结果前由 `condition × candidate_class` 机械枚举；validation 只验证冻结规则；final_test 完全隔离。

### 6.4 CBC/BMP 约 91% 如何处理

现有约 91% 是“冠心病、全住院、result proxy”口径，不是跨机构事实。正式报告按下列组合分别计算：

```text
data_source × diagnosis_stratum × candidate_track × candidate_class
× candidate_level × observation_window × target_window × split_role
```

每个单元报告 `N、df、subject_count、prevalence、first/complete availability、head/mid/tail`。CBC/BMP 不删除，而是 panel 主分析计一次、components 分析另报、同类比较、同时报告 micro 与 macro/head-mid-tail recall，并用低频召回增益和 validation 稳定性评估 TF-IDF。

旧 index 下 4h/24h/48h 结果覆盖（BMP 4.13/76.37/90.15，CBC 3.96/75.03/89.59）只作审计；新 decision 文档后全部重算。

### 6.5 诊断单一化

不随机补诊断，也不预设等量。执行规则：

1. 全源统计诊断 family 的患者/住院数、ED/Note 覆盖、项目级 order 覆盖；
2. 计算各 family 相对冠心病的 candidate 分布 Jensen–Shannon divergence 与 top-k 重叠；
3. 预注册感染/脓毒症、呼吸、心衰、神经、肾脏/电解质、消化/肝胆、血液/肿瘤七个候选域；
4. 仅 `subjects≥2,000` 且关键源与时间合同通过门禁的域进入；
5. 选分布差异最大且质量合格的至少四个域；
6. 按 subject 抽样，单域最多为最小域 2 倍；同一患者不得跨 split；
7. 先报告分域指标，再决定 pooled benchmark。

若某域不合格，明确排除并记录原因，不静默换成另一个诊断。

## 7. 新实现边界与目录

新代码建立在合格 upstream event、boundary 和 snapshot 之后，不放进旧 phenotype：

```text
data_pipeline/investigation_selection/
  __init__.py
  __main__.py
  contracts.py                 # Arrow/JSON schema 与 reason codes
  exposure_registry.py         # 历史使用登记与新 formal role 门禁
  time_semantics.py            # 来源时间白名单与语义解析
  encounter_clock.py           # ED/住院 origin 与冲突审计
  snapshot_adapter.py          # 唯一的正式 snapshot 接口
  episodes.py                  # order/specimen/result episode
  candidate_catalog.py         # component/panel/class 目录
  decision_documents.py        # 三张 decision Parquet
  text_entities.py             # 审核后、时间安全的 NER 适配
  retrieval.py                 # binary TF-IDF/BM25
  ranking.py                   # frequency/lift/shrunk log-RR/FDR
  cohort.py                    # 多诊断审计与抽样
  validation.py                # split/time/statistics/clinical gates
  io.py                        # 原子发布与 manifest/hash
  schemas/
    encounter-clock.schema.json
    investigation-episode.schema.json
    decision-document.schema.json

config/investigation-selection/
  protocol.yaml
  time-semantics.yaml
  candidate-catalog.yaml
  panel-definitions.yaml
  diagnosis-strata.yaml
  feature-whitelist.yaml

tests/investigation_selection/
  test_exposure_registry.py
  test_time_semantics.py
  test_encounter_clock.py
  test_snapshot_adapter.py
  test_episodes.py
  test_candidate_catalog.py
  test_decision_documents.py
  test_retrieval.py
  test_ranking.py
  test_cohort.py
  test_validation.py
```

可复用依赖仅限：

- `data_pipeline/event_pipeline` 已验证的 event 转换、时间字段、归一化和 lineage；
- `evaluation_pipeline/journey` 的 split-bound boundary 认证；
- `evaluation_pipeline/snapshot` 的 occurrence + availability + phase + split 可见性；
- 现有原始归档 manifest 与 source catalog。

明确不导入 `data_pipeline.phenotype`，不读取旧 phenotype/condition/rule/question 产物。

### 7.1 模块公开接口

每个模块只暴露一个主操作和明确的数据类；下游不得绕过接口直接拼 Parquet：

```python
# contracts.py
@dataclass(frozen=True)
class InvestigationProtocol: ...

def load_and_validate_protocol(path: Path) -> InvestigationProtocol: ...

# encounter_clock.py
def build_encounter_clock(
    admissions: pa.Table,
    ed_stays: pa.Table,
    boundary_manifest: Mapping[str, object],
    protocol: InvestigationProtocol,
) -> ClockBuildResult: ...

# exposure_registry.py
def build_exposure_registry(
    legacy_manifests: Sequence[Mapping[str, object]],
    candidate_subjects: pa.Table,
    split_policy: SplitPolicy,
) -> ExposureRegistryResult: ...

# episodes.py
def build_investigation_episodes(
    events: pa.Table,
    catalog: CandidateCatalog,
    panel_definitions: PanelDefinitions,
    protocol: InvestigationProtocol,
) -> EpisodeBuildResult: ...

# decision_documents.py
def build_decision_documents(
    events: pa.Table,
    clocks: pa.Table,
    episodes: pa.Table,
    snapshot_policy: SnapshotPolicy,
    protocol: InvestigationProtocol,
) -> DecisionBuildResult: ...

# retrieval.py
def fit_retriever(
    documents: DecisionCorpus,
    config: RetrievalConfig,
) -> FittedRetriever: ...

# ranking.py
def mine_and_validate_rules(
    development: DecisionCorpus,
    validation: DecisionCorpus,
    config: RankingConfig,
) -> RuleMiningResult: ...
```

所有 `*BuildResult` 至少包含 `table(s)`、`exclusions`、`metrics`、`manifest_payload`；遇到合同错误抛出领域异常并终止，不返回空表伪装成功。公开函数只接受已验证对象，不接受任意字典参数。

### 7.2 配置装载和 fail-closed 顺序

`contracts.py` 按固定顺序验证：

1. YAML 只允许 schema 中声明的键，未知键报错；
2. 所有 scientific fields 非空，枚举值与版本匹配；
3. 主窗口、敏感性窗口和 burst 均为正且时序合法；
4. 四个 MIMIC track 的 target semantics 与允许 source/event kind 一一对应；
5. split 比例为 70/15/15 且总和精确为 1；
6. threshold、bootstrap、FDR 参数满足类型和范围；
7. candidate/panel/feature/time 配置 hash 与 protocol lock 一致；
8. 输入 manifest 的 schema version、Git commit、文件 hash 全部匹配后才读取数据行。

配置使用 frozen dataclass；canonical JSON 采用 UTF-8、key 排序、无 NaN，SHA-256 由 canonical bytes 计算。运行期不允许用 CLI 参数覆盖 scientific fields；CLI 只传输入、输出和已冻结配置路径。

### 7.3 encounter clock 算法

`build_encounter_clock` 按下列确定性步骤执行：

```text
validate boundary manifest and split lineage
→ normalize ID type without changing value
→ one-to-one join admission_ref/hadm_id
→ enumerate linked ED stays
→ validate each [intime, outtime] and [admittime, dischtime]
→ choose origin by frozen task rule
→ retain ed_arrival, ed_registration and hospital_admit separately
→ emit eligible row or exclusion reason
→ canonical sort by journey_id
```

关键实现约束：

- 不使用 `fill_null`/`coalesce` 混合 `intime`、`edregtime`、`admittime`；
- 多个 ED stay 不能按“最早一个”自动解决，必须通过正式 linkage 唯一化，否则 `ENCOUNTER_ORIGIN_AMBIGUOUS`；
- 比较时间前统一解析为 naive MIMIC datetime，输出统一 ISO 秒精度，同时保留 source precision；
- ID 和时间不从自由文本解析；
- clock 输出与 boundary manifest 的 `journey_id` 集合做双向 anti-join，任何未解释差异阻断发布。

### 7.4 episode 算法

#### Order episode

```text
filter allowed ordered event kinds
→ group by stable source_group_id/poe_id
→ order lifecycle by ordertime + deterministic source row key
→ fold New/Change/Cancel/Discontinue state machine
→ reject terminal cancelled/inactive episodes
→ map specific content to candidate_id
→ category-only Lab maps only to generic_lab_order
→ deduplicate same candidate within 15-minute burst
→ group same class/burst into order_set_id
```

状态机必须有显式 transition table。未知 transaction、循环 predecessor/successor、同一 group 跨患者/住院或时间倒置均拒绝；不得取“最后一行看起来有效”作为结果。

#### Result episode

```text
filter laboratory_resulted
→ require observed lab_specimen source_group_id
→ group components by journey + specimen group
→ preserve every component charttime/storetime/value
→ map components through frozen catalog
→ compare observed component set with each panel definition
→ classify complete/partial/extra/unknown
→ calculate first and complete availability
→ emit component episodes and eligible complete panel episodes separately
```

同一 specimen 内一个 analyte 多行时按 `itemid + charttime + storetime + source_row_id` 保留测量事实；是否属于重复结果由明确规则处理，不能简单 `drop_duplicates(candidate_id)`。panel 匹配使用集合包含关系和版本化 required/optional components，不用名称字符串包含判断。

### 7.5 decision document 算法

```text
enumerate eligible decision nodes from episode table
→ bind journey clock and split role
→ derive query/target bounds from protocol
→ call formal snapshot once per unique (journey, index_time, policy)
→ project only whitelisted evidence fields
→ attach same-class target episodes in frozen window
→ retain zero-target eligible documents
→ validate no target/evidence overlap
→ generate stable decision_id and three normalized tables
→ hash canonical evidence/target membership
```

性能上先按唯一 `(journey_id,index_time,snapshot_policy_id)` 缓存 snapshot，再展开 candidate class，避免同一时点重复扫描 2,700 万事件。缓存键必须包含 input manifest hash；缓存内容仅是确定性中间结果，不能绕过验证。

三表写出前执行：

- 主表 `decision_id` 唯一；
- evidence/targets 的 `decision_id` 全部存在于主表；
- eligible 文档的 snapshot hash 非空；
- excluded 文档不得出现在 formal evidence/targets；
- `max(evidence.available_time) <= index_time`；
- order target 的 `target_occurrence_time >= index_time`；
- result proxy target 的完整可见时间位于冻结窗口；
- 每个 split 的 subject 集合两两不交。

### 7.6 检索与统计实现重点

#### Binary TF-IDF/BM25

用稀疏 CSR 矩阵表示 `decision_id × feature_concept_id`。主 TF 为 binary：同一文档重复实体只置 1。训练对象提供 `fit(development)`、`transform(validation)`，禁止 `fit_transform` 跨 split。

```text
development evidence → vocabulary/df/idf → frozen index
validation evidence → transform with frozen vocabulary
→ remove same subject neighbours
→ cosine/BM25 top-k
→ aggregate neighbour targets with similarity weights
→ emit candidate contribution trace
```

OOV 特征忽略但计入审计；没有任何可用特征或邻居时返回明确 refusal reason，不回退为全局高频榜。检索 index manifest 记录 vocabulary hash、document order hash、IDF 数组 hash 和库版本。

#### 规则计数与收缩

计数以 `decision_id` 二元集合完成，不在事件行上 group count：

```text
eligible development documents N
condition document set X
candidate document set Y within same class/track/window
n_x=|X|, n_y=|Y|, n_xy=|X∩Y|
→ preregistered marginal filters
→ full family hypothesis tests
→ BH-FDR
→ shrunk log-RR ranking
→ subject bootstrap stability
→ frozen validation evaluation
```

使用整数 2×2 表作为事实源，所有浮点指标由它现场计算。FDR 前只允许 W1 列出的结构和边际支持过滤；不得用 joint support、lift 或 p-value 预筛后再声称对完整 family 做 BH。bootstrap 先抽 subject，再带入该 subject 的全部 documents。

### 7.7 CLI 与原子发布

统一入口：

```powershell
uv run python -m data_pipeline.investigation_selection validate-config --protocol config/investigation-selection/protocol.yaml
uv run python -m data_pipeline.investigation_selection build-exposure-registry --run-config <path>
uv run python -m data_pipeline.investigation_selection build-clock --run-config <path>
uv run python -m data_pipeline.investigation_selection build-episodes --run-config <path>
uv run python -m data_pipeline.investigation_selection build-decisions --run-config <path>
uv run python -m data_pipeline.investigation_selection fit-retrieval --run-config <path>
uv run python -m data_pipeline.investigation_selection mine-rules --run-config <path>
uv run python -m data_pipeline.investigation_selection audit-cohort --run-config <path>
uv run python -m data_pipeline.investigation_selection validate-run --run-dir <path>
```

每个命令先验证配置和输入 hash，在目标父目录创建同卷临时目录，完成写入、重新读取、schema/row-count/hash 审计后原子 rename 为由 `protocol_sha + input_sha` 决定的 run 目录。目标已存在且 hash 相同则明确报告 already-published；不同则报冲突并停止，不覆盖、不自动改名。

manifest 最少记录：command、schema versions、protocol/split/boundary/input/output hashes、Git commit、`uv.lock` hash、参数、开始/结束时间、输入输出计数、排除原因计数和验证状态。时间戳只作运行审计，不用作文件版本号。

### 7.8 全量数据性能与确定性

27,336,811 条事件不能默认整体载入 pandas。实现约束：

- 用 `pyarrow.dataset.Scanner` 做列裁剪和 predicate pushdown，只读当前阶段所需列；
- encounter/episode/decision 中间计算按稳定 `journey_id` bucket 分区，bucket 数写入 runtime config，不改变科学结果；
- 聚合状态只保存当前分区所需 group，不构建全量 Python `list[dict]`；
- Parquet schema 和 row-group size 由 `contracts.py` 固定，禁止由推断类型写出；
- 多线程结果在写出前按稳定键排序；线程数变化不得改变行、ID、hash 或浮点统计；
- 计数先用整数、浮点使用固定公式和排序，FDR 对同 p-value 使用 candidate ID 次级排序；
- 每阶段记录 peak RSS、扫描行数、过滤行数、分区耗时和异常分区；性能指标不参与临床筛选；
- 开发测试使用最小合成 fixture，另设 1,000 例 integration 和全量 release 三层；样本通过不能替代全量验收。

建议内存上限通过 runtime config 明确设置。超限时命令失败并指出阶段/bucket，不自动采样、不减少候选、不改变窗口。

### 7.9 代码级回归用例

实现每个模块前先增加最小失败 fixture，随后编码至通过。至少覆盖：

| fixture | 输入构造 | 必须断言 |
|---|---|---|
| exposure 污染 | 旧 validation/final subject 注入候选池 | role 固定 audit，不能进入新 val/final |
| ED 双时钟 | `intime != edregtime` | 两字段均保留，origin 来源明确，无 coalesce |
| ED 一对多 | 一个 hadm 对多个无法唯一链接 stay | encounter 被排除并给 ambiguous reason |
| 晚可见 Lab | charttime<index<storetime | 结果不进入 evidence |
| 无 specimen receipt | MIMIC lab 行 | received time 为 null 且状态为 source insufficient |
| order lifecycle | New→Change→Cancel | 不生成有效 target episode |
| 泛化 Lab POE | 只有 order_type=Lab | 只生成 generic candidate，不出现 analyte |
| complete CBC | 同 specimen 包含冻结 required components | 生成一个 complete panel 和各 component episode |
| partial CBC | 缺一个 required component | 不生成 complete CBC target |
| component 延迟 | 同 specimen storetime 不同 | first/complete availability 分别等于 min/max required |
| target 泄漏 | target event 同时被送入 snapshot | 构建失败而非静默删除 |
| 零目标文档 | 合格 query 无同类 target | 主表保留、targets 为 0、进入 N/n_x |
| 跨 split IDF | validation-only feature | vocabulary/IDF 中不存在 |
| 同患者近邻 | query 与 development 含同 subject | 自患者邻居全部排除 |
| 罕见偶然项 | joint=1 且 lift 极高 | support/收缩门禁拒绝 |
| 多住院 bootstrap | 同 subject 有多个 documents | 一次抽中/排除时整组同行 |
| 线程确定性 | threads=1 与 4 | 排序后表内容和 hash 完全相同 |

集成 fixture 使用真实 schema 的合成数据，不复制受限临床数据进 Git。全量运行失败时先增加能复现根因的最小 fixture，再修代码；不得只对坏分区加跳过名单。

## 8. 环境、版本和运行规则

所有命令从仓库根目录执行，使用项目 `uv` 环境：

```powershell
uv sync
uv run python -m pytest tests/investigation_selection -q -p no:cacheprovider
```

若执行中出现真实缺失的模块：

```powershell
uv add --dev <test-only-package>
uv add <runtime-package>
```

安装后必须更新 `pyproject.toml`/`uv.lock`，运行 import smoke test 和相关 pytest；不得改用系统 Python、Anaconda 或未锁定的 `pip install`。大于 50 MB 的生成数据不进 Git。每个完整工作包验证通过后形成一个本地 commit，不 push；commit 同时记录“改了什么”和“为什么”。

## 9. W0—W10 可直接执行工作包

### W0：失效旧 V2 与统一事实源

**目标**：阻止不合格候选继续流转，并让项目状态只有一个口径。

**前置输入**：本计划、旧 phenotype manifest、V2 rule/dedup/converged/question summaries、根目录和调研目录进展文档。

**执行步骤**：

1. 建立旧产物审计清单，记录路径、hash、行数和失效原因；不删除历史证据；
2. 给旧 134 候选的发布/审核入口加 fail-closed 状态 `invalidated_upstream_contract`；
3. 将旧 final-test manifest 标记为 `legacy_holdout_not_formal_final_test`，任何新 split loader 读到其 ID 均拒绝；
4. 禁止旧 phenotype entrypoint 生成 formal 产物；调用时显式报错并指向新模块；
5. `BenchMark-进展梳理.md` 补入 1,584→738→165→134、gold=0；
6. README 只保留状态摘要并链接本计划，删除重复数字；
7. 搜索全库 `formal accepted`、`134`、`8 类`、`phenotype`、`legacy final_test`，逐项增加历史限定或入口门禁；
8. 生成 `legacy-invalidation-manifest.json`，包含旧 candidate/rule/split IDs、输入 hash、原因码和 Git commit。

**产物**：失效 manifest、唯一进展事实源、旧入口拒绝门禁与测试。

**测试**：

```powershell
uv run python -m pytest tests -q -p no:cacheprovider -k "legacy or phenotype or v2"
```

**验收**：任何旧候选不能进入审核/发布；旧 final-test subject 不能被注册为新 formal final-test；gold 计数为 0；审计清单可复现旧数字；无历史文件被当作新输入。

**依赖**：无。后续 W1–W10 均依赖 W0。

### W1：冻结研究构念、时间窗和协议

**目标**：填完 `config/investigation-selection/protocol.yaml` 的所有影响科学结论的 `null`。

**执行步骤**：

1. 本轮冻结四个 MIMIC track：`imaging_order`、`clinical_order`、`generic_lab_order`、`lab_result_proxy`；协议 schema 对其他来源 fail-closed，不保留未实现的 RWD track；
2. 冻结两个主任务：
   - order decision：只纳入 origin 后 24 小时内的 order node；`index_time=order_set.ordertime`，query 为 `[max(origin,index-4h),index)`，target 为从 index 开始 15 分钟 burst 内的同 class order set；
   - MIMIC 固定窗 result proxy：query 为 origin 后前 4 小时，target 为随后 24 小时首次完整可见 result episode；
3. 冻结敏感性窗：query 2/4/8 小时、target 12/24/48 小时，order burst 5/15/30 分钟；只有 query 4 小时、target 24 小时、burst 15 分钟为主结果；
4. 冻结 tie：同一 class 同一 burst 可多标签；MCQ 只在统计规则产生唯一优势候选时生成；
5. 冻结 missing/zero/refusal：缺时间拒绝、零候选保留作分母、无稳定唯一答案则拒绝生成题；
6. 先构建 `subject_exposure_registry.parquet`：旧 development 保持 development；被 sidecar 污染的旧 validation 与已查看的旧 final-test 固定为 `engineering_audit_only`；从未进入特征、规则、调参、审核或结果查看的 subjects 才能补入 validation/final-test；
7. 对可用 formal subjects 以 70/15/15 为目标比例、带项目 secret 的 subject hash 确定新增分桶；已有 development 不改角色，新 final-test 只能来自 `previous_exposure=none`，若人数不足则协议冻结失败，不挪用旧 holdout；
8. 初始 formal 阈值固定为 condition≥50 subjects、candidate≥30 subjects、joint≥10 subjects、BH-FDR `q≤0.05`、1,000 次 subject bootstrap、方向稳定率≥0.80；validation 中 support<20 subjects 的规则标为 inconclusive，不降阈值救题；
9. 生成 `protocol-lock.json`，绑定 dependency lock 和所有输入 manifest hash；
10. 增加所有 unresolved decision 非空、exposure role 不可升级、hash 可复核、改后 lock 失效的测试。

**产物**：完成的 protocol、time semantics、feature whitelist、`subject_exposure_registry.parquet`、新 split manifest、protocol lock。

**测试**：

```powershell
uv run python -m pytest tests -q -p no:cacheprovider -k "protocol or governance or split"
```

**验收**：科学配置不存在 `null`；修改任一科学参数会使 lock 验证失败；旧 validation/final-test 均不能升级为新 formal role；新 final-test subjects 的 exposure 必须全部为 none；final-test 信息不能被 development 进程读取。

**依赖**：W0。

### W2：补齐 encounter clock 与 specimen 分组

**目标**：在复用现有 event 的前提下补齐建立 episode/decision 所必需的两个字段域。

**执行步骤**：

1. 对 `admissions`、`edstays` 建覆盖率、一对多、倒置和差值分布审计；
2. 实现 `encounter_clock.parquet`：`journey_id/admission_ref/ed_stay_ref/origin_type/origin_time/ed_arrival/ed_registration/ed_departure/hospital_admit/hospital_discharge/source refs/status/reasons`；
3. 对 `intime` 与 `edregtime` 不做静默合并，按 W1 阈值标记 `consistent|conflict|ambiguous|source_missing`；
4. 将 `specimen_id`、`micro_specimen_id`、`poe_id` 转成稳定 `source_group_id`；hash salt/key 只记引用位置，不进数据；
5. 优先在现有 `value_structured_json` 中无损加入 grouping；基准证明查询/一致性不足时才升级 event schema；
6. 若升级 schema，同步修改 JSON Schema、Arrow Schema、laboratory/microbiology/order transformers、quality audit 和 manifest version；
7. 全量重跑规范事件，禁止原地覆盖旧成功输出；用 run manifest 选择新有效版本；
8. 比较重跑前后除新增字段外的事件数、event_id、时间、概念和值，必须零非预期差异。

**产物**：`encounter_clock.parquet`、clock manifest、带稳定 group 的规范事件、差异报告。

**测试**：

```powershell
uv run python -m pytest tests/test_encounter_boundaries.py tests/test_event_pipeline.py tests/investigation_selection/test_encounter_clock.py tests/investigation_selection/test_time_semantics.py -q -p no:cacheprovider
```

**验收**：每个 formal journey 有唯一可解释 origin 或明确排除；普通检验 group 可回聚到同一 specimen；不得出现伪造接收时间；非新增字段差异为 0。

**依赖**：W1。

### W3：正式 snapshot 与 discharge NER

**目标**：仅由可见事实构建 query，同时完成出院文本实体抽取但阻断后验泄漏。

**执行步骤**：

1. `snapshot_adapter.py` 只调用 `evaluation_pipeline.snapshot`，不复制时间比较；
2. 给每个 track 建 event-kind/field whitelist；未经映射、未知时间、post-hoc、administrative-end 和错误 split 均拒绝；
3. 对 ED 主诉时间未知建立覆盖报告；不得用 ED arrival 自动回填 triage occurrence/availability；
4. discharge NER 输出 mention、canonical concept、assertion、section、experiencer、temporal relation、document chart/store time、model/prompt version、review status；
5. 出院实体 phase 固定 `post_hoc`，只用于回顾性标签、错误分析和临床审阅辅助；
6. 若同一实体有独立预测点前来源，只把该独立事件放入 snapshot，不因 discharge 提及提升其可见性；
7. 建人工 A/B 双标与裁决样本，按实体类型/否定/时间/section 分层；
8. 未达到冻结 precision/recall 和一致性门槛前，NER 输出不得进入 formal 条件空间。

**产物**：snapshot adapter、可见性审计、discharge NER Parquet、annotation guideline、review manifest。

**测试**：

```powershell
uv run python -m pytest tests/test_snapshot_visibility.py tests/test_boundary_snapshot.py tests/investigation_selection/test_snapshot_adapter.py -q -p no:cacheprovider
```

**验收**：晚可用结果、出院 ICD/小结、未知时间主诉、错误 split 注入均为 0 泄漏；NER 每个实体可追到文本 span 和文档时间。

**依赖**：W2。

### W4：构建 order/specimen/result episode 与候选目录

**目标**：从规范事件生成不重复、语义单一的 target 单元。

**执行步骤**：

1. POE 以 `poe_id` 生命周期合并 New/Change/Cancel/Discontinue；
2. 排除取消、纯物流、饮食、转运和非 investigation 动作，保留 reason；
3. 同候选短时间重复创建按 W1 burst 窗合并，同一时点同 class 形成 order set；
4. category-only Lab 只生成 `generic_lab_order`；禁止与结果强连；
5. labevents 按 `source_group_id` 构建 component bundle；保留每个 component 的 chart/store time；
6. 从官方字典和共现数据产生 panel 候选定义，临床复核后冻结 `panel-definitions.yaml`；
7. complete/partial/extra/unknown 机械判定，输出 first/complete availability；
8. component/panel/category 分层建立 candidate ID，不跨层竞争；
9. 对每个 source×track×class×window 输出覆盖、重复折叠率和排除率；
10. 用 synthetic CBC、partial CBC、BMP、重复 POE、取消医嘱和 storetime 缺失建立回归 fixtures。

**产物**：`investigation_episodes.parquet`、candidate catalog、panel definitions、episode manifest/audit。

**测试**：

```powershell
uv run python -m pytest tests/investigation_selection/test_episodes.py tests/investigation_selection/test_candidate_catalog.py -q -p no:cacheprovider
```

**验收**：同一 episode 不重复计数；RBC 不被改名成 CBC；partial CBC 不进入 complete panel；POE Lab 无伪造项目；时间与 source refs 可回溯。

**依赖**：W2、W3。

### W5：生成 `decision_document`

**目标**：建立统计、检索和题目生成的唯一样本单位。

**执行步骤**：

1. 从 protocol、encounter clock 和 episodes 枚举所有潜在 decision node；
2. 对每个 node 调用正式 snapshot，得到 query evidence；
3. 按 track/class/target window 连接 targets；
4. 保留合格但无 target 的 `zero_candidate_observed=true` 文档；
5. 输出主表、evidence 表、targets 表；
6. 校验同一 decision 的 evidence 均在时间与 split 门禁内；
7. 校验 target 不反向进入 evidence；
8. canonical 排序后生成 snapshot、表文件、protocol/split/boundary/input hashes；
9. 输出 exclusion table，按 reason code 报告每个阶段损失；
10. 生成 20 个可人工阅读的端到端 trace（去标识引用、原始字段、事件、episode、snapshot、decision）。

**产物**：三张 decision Parquet、manifest、exclusions、trace report。

**测试**：

```powershell
uv run python -m pytest tests/investigation_selection/test_decision_documents.py tests/test_boundary_snapshot.py -q -p no:cacheprovider
```

**验收**：document ID 唯一；零目标文档未丢失；无 target/evidence 重叠泄漏；三表 row-count/hash 可互相核对；重复运行逐字节稳定。

**依赖**：W1、W3、W4。

### W6：TF-IDF/BM25 候选召回实验

**目标**：验证逆文档频率是否提高低频但稳定项目的可检出性，而不是默认其有效。

**执行步骤**：

1. 只在 development decision evidence 构建 binary query features；
2. 过滤 unresolved、post-hoc、身份字段和未冻结 NER 实体；
3. 按 track/class/window 分别拟合 vocabulary、df、IDF；
4. 实现 frequency、binary TF-IDF、log-count TF-IDF、BM25 四个检索配置；
5. 对 validation query 只检索 development 文档，按相似度聚合 target 候选；
6. 同患者文档从其自身邻居集合排除，防止患者记忆；
7. 保存每次预测的邻居、相似度、候选贡献和拒绝原因；
8. 报告 Recall@k、MRR、NDCG、macro recall、head/mid/tail recall 和 rare-stable recall；
9. 罕见随机标签、打乱 target、重复行注入作为负对照；
10. 只在 validation 选择检索配置，final-test 不读。

**产物**：retrieval index manifest、逐预测 evidence、配对实验报告。

**测试**：

```powershell
uv run python -m pytest tests/investigation_selection/test_retrieval.py -q -p no:cacheprovider
```

**验收**：IDF 不含 validation/final-test；重复行不改变 binary TF-IDF；单次罕见项不能越过门禁；低频增益提供 paired bootstrap CI，而非只报均值。

**依赖**：W5。

### W7：规则统计、Lift 对照与收缩排名

**目标**：修复旧 Lift 分母和支持度问题，并建立可稳定验证的主规则路径。

**执行步骤**：

1. 从 eligible development documents 枚举 condition；不再使用每住院 500 个静默 cap；
2. 采用两阶段 Apriori：先按预注册 marginal support 剪枝，再机械枚举 FDR family；
3. `n_x` 从全部含条件文档计算，target 为零仍进入；
4. 同时计算 frequency、probability、lift、log-RR、shrunk log-RR、Wilson interval 与 p-value；
5. BH-FDR 的 family 定义、过滤顺序和候选全集写入 manifest；
6. 按 subject bootstrap，输出方向稳定率、top-rank 稳定率和置信区间；
7. 在 validation 上机械判断 validated/failed/inconclusive；
8. 比较旧 Lift、新 Lift、收缩 RR 与 retrieval 路径，禁止事后选最漂亮指标；
9. head/mid/tail、track、class、time window、diagnosis 分层报告；
10. 每条保留规则输出完整 2×2 计数和可复算统计量。

**产物**：rule table、FDR manifest、bootstrap/validation reports、method comparison。

**测试**：

```powershell
uv run python -m pytest tests/investigation_selection/test_ranking.py tests/investigation_selection/test_validation.py -q -p no:cacheprovider
```

**验收**：人工构造零目标文档能改变分母；subject 重复住院不被当独立 bootstrap 单位；罕见偶然共现经收缩后不能通过；每个统计量可从计数复算。

**依赖**：W5、W6。

### W8：多诊断审计与增量抽取

**目标**：扩展检查分布真正不同的临床域，降低冠心病单一谱系造成的答案单一化。

**执行步骤**：

1. 只读取全源诊断索引和源表覆盖元数据，不先读取 final-test 内容；
2. 将 ICD 映射到版本化 diagnosis family，保留原 code 和映射状态；
3. 对七个预注册域计算规模、ED/HOSP/Note/POE/lab 覆盖和时间可构建率；
4. 在 development 候选池计算 candidate 分布差异和 top-k 重叠；
5. 按 6.5 的机械规则选择至少四个域，输出入选/排除 reason；
6. subject-level 去重后抽取，单域不超过最小域 2 倍；
7. 复用现有 raw archive → event pipeline，不另写诊断专属清洗脚本；
8. 对新增数据运行 W2–W5 全部合同；
9. 比较新增前后 candidate entropy、class coverage、tail coverage 和规则多样性；
10. 若 pooled 与 domain-stratified 结论方向冲突，正式结果以分域为主并报告异质性。

**产物**：diagnosis coverage audit、选择 manifest、新增 raw/event/decision manifests、多样性报告。

**测试**：

```powershell
uv run python -m pytest tests/investigation_selection/test_cohort.py tests/test_event_pipeline.py -q -p no:cacheprovider
```

**验收**：至少四个域通过全部时间/来源门禁，否则本工作包明确失败；无患者跨 split；选择规则可由 manifest 重放；新增域产生可量化的候选分布差异。

**依赖**：W2–W5；可与 W6/W7 方法实现并行，但合并统计须等 W8 完成。

### W9：重建规则、题目与人工审核

**目标**：只从冻结的新规则生成候选，并区分行为 gold 与规范 gold。

**执行步骤**：

1. 只读取 W7 validated rule IDs 和对应 decision lineage；
2. 候选题按单一 track/class 构造，答案不能跨层级或跨语义；
3. 题干只使用 `decision_evidence` 白名单字段；不允许模型补充患者事实；
4. LLM 只负责语言表达，不选择统计答案；
5. 程序校验时间、split、唯一答案、选项同类、lineage 和 hash；
6. 独立 reviewer 使用不同审查过程，自动 reviewer 不称“独立临床审核”；
7. 临床审核至少记录：事实正确性、时间可见性、比较类合理性、行为/规范边界、答案唯一性；
8. `pattern_rule_concordance` 只能称“MIMIC 观察数据中同类最可能选择”；
9. `clinical_best_decision` 必须由指南与专家裁决另建 normative gold；
10. 全部门禁通过后才从 gold=0 增加批准数。

**产物**：候选题、程序验证、独立复核、临床审核表、freeze manifest。

**测试**：

```powershell
uv run python -m pytest versions/v2-llm-stem/tests tests/investigation_selection -q -p no:cacheprovider
```

**验收**：旧规则 ID 为 0；每题可追到 decision/rule/protocol；任何来源/时间/语义不一致都拒绝；未签字题不进入 gold。

**依赖**：W7、W8。

### W10：独立验证、final test 与发布

**目标**：完成可复现的盲测和发布门禁。

**执行步骤**：

1. 冻结代码 commit、uv lock、protocol、catalog、panel、diagnosis、feature whitelist 和全部 hashes；
2. 独立验证脚本从原始 manifest 重算关键计数、时间门禁和统计量；
3. 在未参与开发的新 formal final-test subject 上单次运行；
4. final-test 只输出预注册总体/分层指标，不回流调参；
5. 报告 failure/inconclusive，不删除难例；
6. 生成 data card、model/method card、clinical review record 和 reproducibility commands；
7. 检查大文件 `.gitignore`，路径和生成方式写入项目记忆文档（若该文档存在）；
8. 全库扫描是否仍有把 proxy 称 order gold、把行为称临床最佳、把旧 134 称 formal 的文本；
9. 运行完整离线测试；
10. 本地 commit，不 push。

**测试**：

```powershell
uv sync --locked
uv run python -m pytest tests versions/v2-llm-stem/tests -q -p no:cacheprovider
```

**验收**：环境可由 `uv.lock` 重建；final-test 单次运行且无调参回写；全部 artifact hash 可复核；临床未批准内容不进入 gold；文档声明与产物一致。

**依赖**：W0–W9。

## 10. 固定 reason codes

原因码先于运行结果冻结；每个排除样本必须至少有一个码，且不得用自由文本替代：

| 范围 | reason code | 含义 |
|---|---|---|
| encounter | `ENCOUNTER_ORIGIN_MISSING` | 没有任务所需 origin |
| encounter | `ENCOUNTER_ORIGIN_AMBIGUOUS` | 一对多或冲突无法唯一判断 |
| encounter | `ENCOUNTER_TIME_INVERTED` | arrival/admit/discharge 时序倒置 |
| event | `EVENT_OCCURRENCE_TIME_UNKNOWN` | occurrence 不可判定 |
| event | `EVENT_AVAILABLE_TIME_UNKNOWN` | availability 不可判定 |
| event | `EVENT_POST_HOC_FORBIDDEN` | 后验来源禁止进入 query |
| event | `EVENT_NORMALIZATION_UNRESOLVED` | formal 条件需要 concept 但尚未冻结 |
| specimen | `SPECIMEN_RECEIVED_TIME_SOURCE_INSUFFICIENT` | 数据源不提供接收时间；不是一般缺失 |
| specimen | `SPECIMEN_GROUP_MISSING` | 需要 bundle 但没有分组键 |
| panel | `PANEL_DEFINITION_UNREVIEWED` | panel 目录未临床冻结 |
| panel | `PANEL_INCOMPLETE` | required components 不全 |
| order | `ORDER_CONTENT_CATEGORY_ONLY` | 只能识别泛化类别 |
| order | `ORDER_CANCELLED_OR_INACTIVE` | 生命周期不构成有效 target |
| decision | `DECISION_TARGET_WINDOW_INVALID` | 窗口缺失、倒置或越界 |
| decision | `DECISION_TARGET_EVIDENCE_OVERLAP` | target 泄漏进 query |
| decision | `DECISION_SPLIT_FORBIDDEN` | 来源不属于允许 split |
| statistics | `CANDIDATE_SUPPORT_INSUFFICIENT` | 预注册支持度未达标 |
| statistics | `VALIDATION_DIRECTION_REVERSED` | validation 方向反转 |
| statistics | `VALIDATION_INCONCLUSIVE` | 无法得出冻结判断 |
| release | `CLINICAL_REVIEW_REQUIRED` | 尚未完成人工临床审批 |

`source_insufficient` 与普通 null 分开：前者说明官方源表根本没有该语义字段，后者才是源字段存在但该行缺值。两者不得互换。

## 11. 总体验收矩阵

| 验收域 | 必须通过的测试 | 阻断发布的条件 | 证据产物 |
|---|---|---|---|
| 环境 | `uv sync --locked` 和 import smoke | 使用非项目 Python 或 lock 漂移 | `uv.lock`、测试日志 |
| 旧产物 | 审核/发布入口拒绝旧 ID | 任一旧 134 候选进入新链 | invalidation manifest |
| split | subject 唯一角色、sidecar 注入拒绝 | development 读到 val/test | split audit |
| encounter | origin 唯一、时序合法、来源可追溯 | 静默合并 arrival/registration/admit | encounter clock audit |
| 时间 | occurrence + availability + phase 均通过 | 晚可见、未知时间或 post-hoc 进入 query | visibility audit |
| lab 时间 | chart/store/received 三语义分离 | 伪造 `specimen_received_time` | time semantics registry |
| grouping | specimen/order group 稳定且可回聚 | component 无法回到真实 group | schema/audit report |
| episode | lifecycle、burst、panel 层级正确 | 取消 order、partial panel 误计 | episode manifest |
| decision | 三表一致、零目标保留、无 target 泄漏 | 文档粒度退回整次住院 | decision manifest |
| normalization | 原始标签保留、mapping 可追溯 | unresolved 被模型猜补 | mapping/review manifest |
| NER | span/assertion/section/time/review 可追溯 | discharge 实体进入前瞻 query | NER review report |
| retrieval | development-only IDF、患者自邻居排除 | val/test 参与词表或权重选择 | retrieval manifest |
| statistics | 正确分母、subject bootstrap、FDR 可复算 | 零目标被删或按 hadm bootstrap | rule/FDR manifest |
| 高频分层 | class/window/domain/head-tail 分报 | 只报全住院总体覆盖 | stratified metrics |
| 多诊断 | 至少四域通过数据与时间门禁 | 随机补数或患者跨 split | cohort manifest |
| 题目 | 同类选项、唯一统计答案、lineage 完整 | LLM 自选答案或补事实 | question validation |
| 临床 | 双重程序/独立/人工门禁 | 未签字题计为 gold | review freeze record |
| 复现 | 同输入重复运行 hash 相同 | 原地覆盖成功产物 | run manifest |

## 12. 工作包依赖与里程碑

```text
W0 旧产物失效
 └─ W1 协议冻结
     ├─ W2 时钟与分组
     │   ├─ W3 snapshot + NER
     │   └─ W4 episodes/catalog
     │       └─ W5 decision documents
     │           ├─ W6 TF-IDF/BM25
     │           └─ W7 规则统计
     └────────────── W8 多诊断抽取（复跑 W2–W5）
                         └─ W9 新规则与题目
                             └─ W10 盲测与发布
```

| 里程碑 | 完成条件 | 此时允许声称 |
|---|---|---|
| M1：合同可信 | W0–W2 | 源时间和 encounter origin 可审计；不能声称已有题 |
| M2：样本可信 | W3–W5 | 已建立时间安全 decision documents；不能声称方法有效 |
| M3：方法可信 | W6–W7 | 已完成 development/validation 配对实验；不能声称临床最佳 |
| M4：谱系扩展 | W8 | 至少四个合格诊断域进入相同合同 |
| M5：候选可审 | W9 | 通过程序门禁的行为一致性候选可送临床审核 |
| M6：正式冻结 | W10 | 仅人工批准项可计 gold，报告盲测结果 |

## 13. 对用户已提出问题的落实索引

| 问题/要求 | 本计划的确定处理 |
|---|---|
| 旧 134 道候选 | 0.1、W0；整体失效，审核/发布/统计入口按 ID 拒绝 |
| 旧 final-test | 0.1、W0–W1；仅作 engineering audit，相关 subjects 不进入新 formal roles |
| 香港 RWD | 0.1、3.4；本轮不读取、不实现 connector、不作为验收条件 |
| 环境统一用 uv，缺包就安装 | 第 8 节；只用 `uv sync/uv add/uv run` |
| event 中有哪些时间字段 | 1.2、3.3；已有四类时间、policy/reasons/phase，另补源语义 |
| Lift 效果仍被 CBC 类项目占据 | 6.1–6.4、W6–W7；修分母/层级/窗口，TF-IDF 召回 + 收缩 RR |
| 二元就诊文档是什么 | 2.1–2.2；一次决策一个文档，候选 TF 为 0/1 |
| 放大罕见噪声是否指只做一次 | 2.3；一次是极端，不是完整定义 |
| phenotype 代码都不采用 | 0、1.1、7、W0；代码和 8 类设计全部弃用 |
| 归一化怎么进行 | 2.4、W4；解码、同义词、component/panel、单位，全部可追溯 |
| discharge 文本 NER | W3；抽 mention/assertion/section/time，但 phase 固定 post_hoc |
| 字典没有项目级内容 | 0、1.4、4.1；结果可到 analyte，POE Lab 仍仅类别级；本轮不构建具体 Lab order gold |
| 8 类特征不采用 | 1.1、1.4、7；新输入用可见事实白名单，不预设特征类 |
| CBC/BMP 91% 如何解决 | 4.2、6.4；panel/component 分层及多维口径分别统计 |
| V2 规则组合缺失是什么 | 1.3、W0；进展文档漏了 1,584→738→165→134 和失效原因 |
| decision_document 是什么/能否映射 | 2.1、5、W5；三张 Parquet + manifest 的逐字段合同 |
| 检验时间采用收到样本时间 | 3.4；本轮 MIMIC 明确 source insufficient，不推断、不接入 RWD |
| 到诊/入院及实际可见时间 | 3.2–3.5；arrival、registration、admit 分开，query 用 occurrence+availability |

## 14. 完成定义

本计划不是在“代码能跑”时完成，而是在以下条件同时满足时完成：

1. 旧 phenotype/V2 产物无法进入新链；
2. 每个决策的 origin、index、query、target、可见 evidence 和 target episode 都可追溯；
3. MIMIC 未拥有的检验接收时间没有被创造；
4. MIMIC generic Lab order 与 result proxy 分轨，项目级 Lab order gold 明确 unavailable；
5. TF-IDF 相对频率/Lift 的增益经过配对、分层和 validation 检验；
6. CBC/BMP 没有被删除，也没有因 component/重复行被多重计数；
7. 至少四个检查分布不同的诊断域通过相同数据合同；
8. final-test 未参与任何词表、阈值、目录、prompt 或方法选择；
9. 所有 formal 题经过程序、独立复核和临床审批；
10. gold 数量只统计人工批准项，未批准时保持 0。
