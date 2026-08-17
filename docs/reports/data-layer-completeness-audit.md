# 数据层全流程完整性审计

> 审计对象：当前 visit JSONL 与上游 episode Parquet  
> 审计范围：MIMIC-IV 3.1、MIMIC-IV-ED 2.2、MIMIC-IV-Note 2.2  
> 审计原则：只输出聚合结果，不输出患者标识、病历原文或精确事件时间

## 结论

当前 JSONL **没有涵盖全部数据，也不能表示一名患者从出现症状、就诊、诊疗到真实出院后随访的完整流程**。

它更准确的定位是：

> 以一次住院 visit 为单位、由出院后资料回顾性组装的出题数据汇总。

当前 JSONL 对实验室、放射学、诊断、处方、转科和出院文书覆盖较高，但存在六个决定性缺口：

1. 上游 99.73% visit 有 POE 医嘱，JSONL 完全没有医嘱时间线；
2. 症状和病史主要来自出院小结，属于事后文书，不能直接代表决策时点可见信息；
3. ICU 连续监测、输入、输出、操作等事件被 JSONL 抽取层主动排除；
4. 多个已声明字段实际恒空或丢失关键属性，包括 baseline、cardiology、respiratory、ed_disposition 和 ICU care unit；
5. 诊断主要是无时间戳的出院后 ICD 编码，不能作为实时诊断过程；
6. MIMIC-IV-Note 不提供完整门诊随访、依从性和长期结局，出院指导不等于真实出院后发生的事件。

因此，当前 JSONL 可以支持回顾性数据画像和部分标签构造，但**不能直接作为五维时序决策 benchmark 的唯一数据底座**。

正确的数据层应保留两种不同产品：

```text
完整 episode 事件层
    保存来源、发生时间、可见时间、记录时间和原始证据

决策快照层
    按五个决策时点，只暴露当时可见的信息并连接后续隐藏标签
```

不应把“全流程档案”和“题目可见字段”继续混成一个 JSON 对象。

## 审计方法

本次审计执行了以下检查：

- 流式扫描 29,391,481,925 bytes JSONL；
- 解析全部 320,267 条 visit；
- 检查顶层、嵌套字段、类型和 schema 变体；
- 统计症状、检查、诊断、治疗、路径和出院阶段组合覆盖率；
- 将 320,267 条 visit 与 episode Parquet 聚合层连接；
- 汇总事件类型、来源表、时间字段和后续 episode 可观察性；
- 构建一条不含患者信息的相对时间结构示例；
- 对照 41 张 MIMIC 源表检查当前 JSONL 的字段血缘。

全量扫描结果：

| 指标 | 结果 |
|---|---:|
| JSONL visit | 320,267 |
| 唯一患者 | 143,047 |
| 非法 JSON 行 | 0 |
| 重复 `subject_id + hadm_id` | 0 |
| 多次进入当前 JSONL 的患者 | 58,443（40.86%） |
| 属于多 visit 患者的记录 | 235,663 |
| 上游仍可观察到后续 episode 的当前 visit | 216,451（67.58%） |

## “完整”需要分成三个层次

### Visit 档案完整性

问题是：一次住院期间发生过的资料是否被保留。

当前 JSONL 在检验、影像、处方、诊断和出院文书方面较强，但 POE、ICU细节、ED去向和多类时间字段缺失，尚不完整。

### 决策时点完整性

问题是：能否知道医生在某一时点已经看到了什么，以及之后采取了什么动作。

当前 JSONL 不满足。它没有统一的：

- episode 起止时间；
- `event_time`；
- `available_time`；
- `recorded_time`；
- POE新建、修改和停止时间线；
- 信息截止点与后续标签边界。

### 患者纵向完整性

问题是：能否追踪患者出院后的复诊、依从性、治疗调整和临床结局。

当前 JSONL 不满足。`subject_id` 可以连接同一患者后续进入 MIMIC 的住院或急诊记录，但不能恢复未进入该医院系统的门诊随访、依从性或真实生活结局。

## 全流程阶段覆盖

### 当前 JSONL 覆盖率

| 阶段或资料 | Visit 数 | 覆盖率 | 判断 |
|---|---:|---:|---|
| 可用主诉 | 319,083 | 99.63% | 主要来自出院小结，不是实时主诉 |
| 初始生命体征 | 145,607 | 45.46% | 仅有ED关联时较可靠 |
| 现病史 | 316,605 | 98.86% | 出院后回顾性文书 |
| 既往史 | 304,787 | 95.17% | 出院后回顾性文书 |
| 社会史 | 9,242 | 2.89% | 约95%字符串实际是去标识化占位符 |
| 入院用药文本 | 302,027 | 94.30% | 出院小结章节 |
| 结构化用药核对 | 124,035 | 38.73% | ED medrecon |
| 体格检查 | 301,750 | 94.22% | 出院后回顾性文书 |
| 任一检查 | 312,698 | 97.64% | 主要是结果或报告，不是完整医嘱链 |
| 实验室 | 308,184 | 96.23% | 有采样时间，丢失store/available时间 |
| 微生物 | 195,119 | 60.92% | 部分结构保留 |
| 放射学 | 264,265 | 82.51% | 检查名称由文本猜测，详情为空 |
| POE医嘱 | 0 | 0% | 上游覆盖99.73%，JSONL完全丢失 |
| 主诊断 | 320,267 | 100% | 主要是无实时可见时间的出院后编码 |
| ED诊断 | 149,575 | 46.70% | 有事件时间，但上游没有可见时间 |
| 任一治疗资料 | 320,156 | 99.97% | 处方、药房医嘱或给药至少一种 |
| 处方 | 319,712 | 99.83% | 计划治疗，不等于实际执行 |
| 药房医嘱 | 319,712 | 99.83% | 多个细节字段被压缩 |
| 实际给药 | 153,284 | 47.86% | eMAR详情被丢失 |
| ICD操作 | 187,305 | 58.48% | 缺少实时可见时间 |
| 转科路径 | 320,267 | 100% | 有物理路径，但存在行政时间边界问题 |
| ICU住院 | 62,886 | 19.64% | 只保留起止时间，care unit和LOS为空 |
| 出院用药文本 | 313,883 | 98.01% | 出院小结章节 |
| 出院状态 | 319,846 | 99.87% | 出院小结章节 |
| 出院指导 | 314,462 | 98.19% | 计划，不是真实随访结果 |
| 真实出院后随访 | 0 | 0% | 当前数据包不提供完整随访链 |

当前 JSONL 中有 97.24% 的记录同时具备“主诉＋任一检查＋诊断＋任一治疗＋任一出院资料”。这个数字**不能解释为完整诊疗流程覆盖率**，因为它没有要求医嘱、决策时间、信息可见时间、治疗执行细节或真实随访。

当增加“初始生命体征”要求后，组合覆盖率降至45.19%。这更接近能够构造早期决策快照的上限，但仍未解决出院小结后验信息和POE缺失。

## 上游 episode 层与 JSONL 的差异

| 数据类型 | 上游episode覆盖 | JSONL覆盖 | 结论 |
|---|---:|---:|---|
| POE医嘱 | 319,402（99.73%） | 0 | 抽取层完全丢失 |
| 实验室 | 308,184（96.23%） | 308,184 | 保留结果，时间和字典属性被压缩 |
| 微生物 | 195,119（60.92%） | 195,119 | 部分保留 |
| 放射报告 | 264,267（82.51%） | 264,265 | 两条visit发生差异，且报告被按猜测名称去重 |
| 实际给药 | 153,284（47.86%） | 153,284 | eMAR主事件保留，eMAR detail丢失 |
| 操作 | 230,109（71.85%） | 187,305 ICD操作＋46,314 HCPCS | ICU操作被排除，口径不等价 |
| ED分诊 | 150,052（46.85%） | 生命体征145,607 | 部分分诊字段未进入JSONL |
| ICU连续事件 | 约62,000 visit | 0 | 抽取层主动排除 |
| ED发药Pyxis | 126,188（39.40%） | 0 | 完全丢失 |

上游 episode 层已经保存了35,312,988条目标visit内POE事件，并且全部具有事件时间和可见时间。重新抽取可以恢复严格的医嘱大类时间线。

## 当前实际 Schema 问题

### 字段数量命名已经不是实际契约

全部320,267条记录都有8个顶层组：

```text
identifiers
demographics
vitals
narrative
investigations
diagnoses
treatments
disposition
```

但实际代码已经增加 baseline、home medications、microbiology、ED diagnoses、药房医嘱、给药、HCPCS、转科、ICU和DRG等嵌套字段。因此应停止用字段数量作为精确 schema 名称。

### Schema发生漂移

`vitals.pain` 只在150,052条记录中存在，另外170,215条记录完全没有这个键。固定schema应保证所有记录都存在该键，缺失时使用 `null`。

### 声明存在但恒空

| 字段 | 实际状态 | 原因或判断 |
|---|---|---|
| `demographics.baseline` | 320,267条全部为空对象 | adapter查询了不存在于timeline的OMR事件类型 |
| `investigations.cardiology` | 全部空数组 | assembler硬编码为空 |
| `investigations.respiratory` | 全部空数组 | assembler硬编码为空 |
| `disposition.ed_disposition` | 全部为null | assembler硬编码为空 |
| `icu_stays[].first_careunit` | 全部为null | 只读取care contact起止时间 |
| `icu_stays[].last_careunit` | 全部为null | 只读取care contact起止时间 |
| `icu_stays[].los` | 全部为null | 未从原始icustays保留 |
| `radiology[].details` | 全部为空 | radiology_detail未进入聚合结果 |
| `medication_administrations[].detail` | 全部为空 | emar_detail未进入JSONL |

### 文档和实际数据不一致

现有EDA报告把住院经过和出院指导写为0%，但实际全量JSONL分别为87.54%和98.19%。另一方面，EDA把主诉和社会史等字符串只按非null统计，没有识别 `___` 去标识化占位符，导致可用性被高估。

## 41张源表到JSONL的数据血缘

### MIMIC-IV hosp（22张）

| 源表 | 当前JSONL | 完整性判断 |
|---|---|---|
| patients | 年龄、性别 | `dod`、anchor年代等未保留 |
| admissions | 入院类型、入院位置、出院位置 | 入院/出院/死亡时间、院内死亡、保险、语言等未保留 |
| transfers | `transfer_path` | 路径保留；部分结束时间缺失，行政边界需解释 |
| services | 最终 `primary_service` | 完整服务转移历史被压缩为最终科室 |
| labevents | laboratory results | storetime、priority、comments等缺失 |
| d_labitems | label | fluid、category在JSONL中恒为空 |
| microbiologyevents | microbiology | 数量、comments、部分代码和store时间缺失 |
| omr | baseline | 当前JSONL实际完全没有数据 |
| poe | 无 | 35,312,988条目标visit医嘱被丢失 |
| poe_detail | 无 | 8,503,948条全episode属性记录未进入JSONL |
| pharmacy | pharmacy_orders | 多个时间、状态和配药属性被压缩 |
| prescriptions | treatments.medications | stoptime、药物编码和部分剂量属性缺失 |
| emar | medication_administrations | 主事件部分保留 |
| emar_detail | 无 | 实际给药剂量、途径、未给原因等丢失 |
| diagnoses_icd | diagnoses | 主诊断较完整；其他诊断只保留名称，编码、版本和顺序丢失 |
| d_icd_diagnoses | diagnosis_name | 用作字典 |
| procedures_icd | procedures | chartdate和顺序丢失 |
| d_icd_procedures | procedure_name | 用作字典 |
| hcpcsevents | hcpcs | 部分保留 |
| d_hcpcs | 短描述 | 完整描述和类别未保留 |
| drgcodes | 仅第一条DRG | 其余DRG被丢弃；无决策时点 |
| provider | 无 | 不应进入题目；只需在受控审计层保留来源关系 |

### MIMIC-IV ICU（9张）

| 源表 | 当前JSONL | 完整性判断 |
|---|---|---|
| icustays | 起止时间 | care unit和LOS丢失 |
| chartevents | 无 | 主动排除，床旁观察缺失 |
| datetimeevents | 无 | 主动排除 |
| ingredientevents | 无 | 主动排除，输注成分缺失 |
| inputevents | 无 | 主动排除，ICU输入和治疗缺失 |
| outputevents | 无 | 主动排除，出量信息缺失 |
| procedureevents | 无 | 主动排除，ICU操作缺失 |
| d_items | 无 | ICU事件字典随事件一起缺失 |
| caregiver | 无 | 不应进入题目；审计层可保留关系 |

### MIMIC-IV-ED（6张）

| 源表 | 当前JSONL | 完整性判断 |
|---|---|---|
| edstays | 间接关联 | intime/outtime、到达方式、ED disposition未保留 |
| triage | 首次生命体征 | triage主诉未单独保留；仅约46.85%目标visit有关联 |
| vitalsign | 只取首个非空rhythm | 完整串行生命体征被丢弃 |
| diagnosis | ed_diagnoses | 有事件时间，但缺可见时间 |
| medrecon | home_medications | 部分字段保留 |
| pyxis | 无 | ED发药记录完全丢失 |

### MIMIC-IV-Note（4张）

| 源表 | 当前JSONL | 完整性判断 |
|---|---|---|
| discharge | 完整正文＋11个章节 | Family History、Pertinent Results、Studies、Discharge Diagnosis等未结构化；正文为事后信息 |
| discharge_detail | 无 | 文档结构属性未保留 |
| radiology | 报告正文 | 同一猜测名称只保留最早报告，可能丢失重复检查和病程变化 |
| radiology_detail | 无 | exam code、检查名称和补充报告关系未保留 |

完整性不等于把41张表全部复制进benchmark JSON。字典表、provider和caregiver等不应直接进入题目，但必须在权威事件层保留清晰血缘，并说明为何不进入决策快照。

## 时间与信息可见性

### 上游具有时间，JSONL通常只保留一个时间

episode层区分：

```text
event_time
available_time
recorded_time
start_time
end_time
```

当前JSONL通常只保留 `charttime`、`starttime` 或单一事件时间，导致无法判断结果何时真正对医生可见。

### 无法作为实时标签的资料

| 资料 | 时间问题 |
|---|---|
| 出院ICD诊断 | 4,046,904条目标事件全部没有event/available/recorded time |
| DRG | 526,248条目标事件全部没有时间，属于后验结算信息 |
| ICD操作 | 只有日期级chartdate，34.54%显示早于精确episode开始，不能直接解释为真正提前发生 |
| HCPCS | 日期级记录，73.26%显示早于精确episode开始，主要是时间精度不一致 |
| discharge summary | 出院阶段形成，不能用于早期检查或诊断题题干 |

### 时间异常不应直接删除

部分转科、处方、药房和POE事件落在clinical end之后，可能反映行政结束时间、跨日记录或真实数据问题。应保留并按 `clinical_end_time` 与 `administrative_end_time` 分别审计，不能用简单越界规则删除。

## 脱敏单次流程结构示例

本次从完整度较高的一条visit中只保留相对时间和事件计数：

| 相对流程 | 观察到的结构 |
|---|---|
| 到达时 | 1条ED分诊；3组ED生命体征 |
| 最初约1小时 | 实验室、微生物、放射、POE、ED诊断、转科和给药开始出现 |
| 全episode | 167条POE、37组实验室、7份放射报告、127条给药、54条药房医嘱、68条处方 |
| ICU阶段 | 183组床旁观察、143组输入、156组输注成分、20组输出、8组ICU操作 |
| 诊断与结算 | 31条ICD诊断和2条DRG没有可用时间 |
| 出院文书 | 出院小结在episode后段形成 |

在这条结构完整的visit中，当前JSONL仍然丢失167条POE、全部ICU床旁事件、全部ICU输入/输出/操作细节，并把无实时信息的出院诊断放入统一对象。这证明高字段覆盖率不等于完整决策时间线。

## 对五维 Benchmark 的影响

| 题型 | 当前可用内容 | 当前阻塞 |
|---|---|---|
| 1 检查检验选择 | 初始资料、实验室和放射结果 | POE缺失；无法严格定义下一医嘱；DS题干有后验泄漏 |
| 2 临床诊断 | 症状、检查结果、主诊断 | 主诊断是出院后编码；缺少诊断形成时间；DS包含答案后信息 |
| 3 治疗处置 | 处方、药房医嘱、部分实际给药 | POE和eMAR detail缺失；计划与执行边界不完整；ICU治疗缺失 |
| 4 转诊科室 | 最终服务、转科路径 | 完整services历史被压缩；ED去向为空；ICU care unit为空 |
| 5 离院指导 | 出院用药、状态和指导 | 可以预测文书中的指导，但没有真实随访、依从性或长期结局 |

在修复数据层之前，不应开始批量生成500道benchmark题。否则每个题型都会用不同方式把后验记录、执行结果或缺失时间误当成决策时点信息。

## 根因

当前问题不是MIMIC数据不足这一种原因，而是三类原因叠加。

### 上游有，JSONL抽取丢失

- POE和POE detail；
- ICU连续事件和治疗事件；
- Pyxis；
- eMAR detail；
- radiology detail；
- ED disposition；
- 完整service路径；
- admission、discharge和clinical end时间。

### JSONL有，但语义被压缩

- 实验室只有charttime，没有store/available time；
- 放射报告按猜测名称去重；
- 诊断缺少形成时间；
- 处方和实际给药的关联不完整；
- 出院小结章节被当作早期临床事实；
- ICU只剩起止时间。

### MIMIC本身没有

- 完整门诊随访记录；
- 患者是否执行出院建议；
- 院外用药依从性；
- 未回到MIMIC医院的结局；
- 完整护理、会诊和纵向生活质量文本。

## 推荐的数据层结构

### 1. 权威 episode 事件层

继续以episode Parquet作为事实来源，必须保留：

```text
source_table
source_version
event_id
episode_id
subject_id
event_type
event_subtype
event_time
available_time
recorded_time
start_time
end_time
status
raw_payload或证据引用
```

该层追求血缘和时间完整，不直接作为模型输入。

### 2. Visit 临床档案层

重新生成JSONL，但定位为便于审阅的完整visit视图，至少补充：

- episode起止时间；
- ED到达/离开和ED disposition；
- triage主诉与DS回顾性主诉分离；
- POE完整时间线；
- 结果发生时间和可见时间；
- 完整services和care unit路径；
- 药物计划、实际给药和未给原因；
- ICU事件摘要或受控引用；
- 诊断来源类型与时间证据；
- 出院与院内死亡状态；
- 后续episode引用，但不伪装成完整随访。

### 3. 五类决策快照层

从权威事件层生成五种不同快照：

```text
snapshot_time
visible_evidence
forbidden_future_evidence
hidden_outcome
source_event_ids
exclusion_reasons
```

每个题型的输入截止点不同，不能共用一个“全字段患者对象”直接出题。

## 修复优先级

### P0：没有这些不能开始评测层

1. 冻结新的嵌套 schema，并使用稳定的 schema name/version；
2. 加入episode、ED、clinical end和administrative end时间；
3. 恢复POE和POE detail；
4. 分开triage主诉和出院小结回顾性章节；
5. 为实验室、放射、药物和转科保留event/available/recorded时间；
6. 修复baseline、ED disposition、ICU metadata、cardiology和respiratory恒空字段；
7. 修复`vitals.pain` schema漂移；
8. 明确ICD诊断、DRG和出院文书属于后验资料；
9. 建立患者级开发集与最终测试集隔离；
10. 为每种题型生成决策快照并执行未来信息泄漏测试。

### P1：影响治疗、转诊和复杂病例

1. 恢复eMAR detail与处方/药房/给药关联；
2. 恢复ICU care unit和关键事件；
3. 恢复Pyxis、radiology detail和完整services路径；
4. 保留其他诊断的编码、版本和顺序；
5. 设计后续episode和院内死亡结局视图。

### P2：MIMIC之外才能解决

如果研究问题要求真实出院后随访、依从性和长期结局，需要引入其他纵向数据源或改变题型定义。仅靠当前MIMIC数据包无法通过重新抽取解决。

## 数据层验收标准

进入500道pilot benchmark生成前，数据层至少应满足：

1. 所有visit使用同一固定schema，允许值为空但不允许键漂移；
2. 41张源表均有“保留、派生、只作字典、主动排除”的明确血缘决定；
3. 所有用于决策顺序的事件都有时间精度和可见时间说明；
4. POE、结果、处方、给药、转科和出院形成可连接时间线；
5. 出院后编码和出院文书不能进入早期题型输入；
6. 题型1至题型5分别通过未来信息泄漏测试；
7. 开发患者与最终测试患者按subject_id完全隔离；
8. 100条分层样本能够恢复来源事件和排除原因；
9. 覆盖率报告区分“字段非空”和“临床可用”；
10. 任何不完整记录被显式排除并记录原因，不使用默认值伪装完整。

## 本次产物

- 审计脚本：`eda/analysis/audit_data_layer_completeness.py`
- 聚合指标：`docs/reports/data-layer-completeness-audit-metrics.json`
- 审计结论：`docs/reports/data-layer-completeness-audit.md`

本次只完成审计和根因定位，没有修改现有JSONL，也没有重新抽取数据。
