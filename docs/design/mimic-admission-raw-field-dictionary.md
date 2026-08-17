# MIMIC 单次住院原始归档逐字段数据字典

> 本文档由实际归档契约与本地 MIMIC 表结构自动生成。归档表头是覆盖范围的唯一事实源；参考文档负责原始类型和中文释义。任一字段缺少说明时生成过程直接失败。

## 统计与使用边界

- 顶层字段：7 个。
- JSONL 内32张源表字段：380 个。
- 外置7张公共字典字段：25 个。
- JSONL 内模块字段数：HOSP 209、ICU 92、ED 53、NOTE 26。
- 原始CSV单元格在JSONL中保存为字符串；空单元格写为`null`。`source_type`表示MIMIC源表的逻辑类型，不代表JSON中已经转成数值或日期对象。
- `post_hoc`和`administrative_end`字段不得进入前瞻性决策题干；其他事件仍须同时通过决策时点和可用时点检查。

## 时间与信息阶段定义

| 标记 | 定义 |
|---|---|
| `event time` | 事件发生、开始、结束或临床标记时间。 |
| `recorded/available time` | 系统存储、录入或核验时间，用于判断该信息何时真正可见。 |
| `post_hoc` | 出院文书、住院ICD、DRG等住院后验资料。 |
| `administrative_end` | 出院、死亡、出院去向等住院结局。 |
| `identifier` | 只用于连接、去重和审计，不作为临床证据。 |

## 顶层字段

| JSON路径 | JSON存储类型 | 源类型 | 源约束 | 中文说明 | 键角色 | 时间语义 | 信息阶段 | Benchmark使用限制 |
|---|---|---|---|---|---|---|---|---|
| schema | object | object | NOT NULL | 归档格式标识，固定为 mimic_admission_raw 1.0.0。 | 非键字段 | 非时间字段 | archive_structure | 归档结构字段，不作为临床证据。 |
| subject_id | string | string | NOT NULL | 原始患者标识，来自 admissions.subject_id。 | 患者连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| hadm_id | string | string | NOT NULL | 原始住院标识；一行 JSON 对应一个 hadm_id。 | 住院连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp | object | object | NOT NULL | HOSP 模块容器，内部固定包含16张源表数组。 | 非键字段 | 非时间字段 | archive_structure | 归档结构字段，不作为临床证据。 |
| mimic_iv_icu | object | object | NOT NULL | ICU 模块容器，内部固定包含6张源表数组，不含 chartevents。 | 非键字段 | 非时间字段 | archive_structure | 归档结构字段，不作为临床证据。 |
| mimic_iv_ed | object | object | NOT NULL | ED 模块容器，内部固定包含6张经 edstays 原生关联的源表数组。 | 非键字段 | 非时间字段 | archive_structure | 归档结构字段，不作为临床证据。 |
| mimic_iv_note | object | object | NOT NULL | NOTE 模块容器，内部固定包含4张文书源表数组。 | 非键字段 | 非时间字段 | archive_structure | 归档结构字段，不作为临床证据。 |

## JSONL内32张源表字段

| JSON路径 | JSON存储类型 | 源类型 | 源约束 | 中文说明 | 键角色 | 时间语义 | 信息阶段 | Benchmark使用限制 |
|---|---|---|---|---|---|---|---|---|
| mimic_iv_hosp.patients[].subject_id | string | INTEGER | NOT NULL, 主键 | 患者唯一标识符 | 患者连接键 | 非时间字段 | baseline（患者背景） | 可作为患者背景；年龄须在清洗sidecar中按住院时点解释。 |
| mimic_iv_hosp.patients[].gender | string | VARCHAR(1) | NOT NULL | 患者性别 | 非键字段 | 非时间字段 | baseline（患者背景） | 可作为患者背景；年龄须在清洗sidecar中按住院时点解释。 |
| mimic_iv_hosp.patients[].anchor_age | string | INTEGER | NOT NULL | 锚定年龄 | 非键字段 | 非时间字段 | baseline（患者背景） | 可作为患者背景；年龄须在清洗sidecar中按住院时点解释。 |
| mimic_iv_hosp.patients[].anchor_year | string | INTEGER | NOT NULL | 锚定年份（去标识化后的年份） | 非键字段 | 非时间字段 | baseline（患者背景） | 可作为患者背景；年龄须在清洗sidecar中按住院时点解释。 |
| mimic_iv_hosp.patients[].anchor_year_group | string | VARCHAR(255) | NOT NULL | 真实年份范围 | 非键字段 | 非时间字段 | baseline（患者背景） | 可作为患者背景；年龄须在清洗sidecar中按住院时点解释。 |
| mimic_iv_hosp.patients[].dod | string \| null | TIMESTAMP(0) | 可空 | 死亡日期（去标识化） | 非键字段 | event time：事件发生、开始、结束或临床标记时间 | administrative_end（住院结局） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_hosp.admissions[].subject_id | string | INTEGER | NOT NULL | 患者唯一标识 | 患者连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.admissions[].hadm_id | string | INTEGER | NOT NULL, 主键 | 住院唯一标识 | 住院主键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.admissions[].admittime | string | TIMESTAMP | NOT NULL | 入院时间 | 非键字段 | event time：事件发生、开始、结束或临床标记时间 | source_event（按源事件时间判断） | 事件时间与可用时间均不晚于决策时点时，才可进入题型快照。 |
| mimic_iv_hosp.admissions[].dischtime | string \| null | TIMESTAMP | 可空 | 出院时间 | 非键字段 | event time：事件发生、开始、结束或临床标记时间 | administrative_end（住院结局） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_hosp.admissions[].deathtime | string \| null | TIMESTAMP | 可空 | 院内死亡时间 | 非键字段 | event time：事件发生、开始、结束或临床标记时间 | administrative_end（住院结局） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_hosp.admissions[].admission_type | string | VARCHAR(40) | NOT NULL | 入院类型 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.admissions[].admit_provider_id | string \| null | VARCHAR(10) | 可空 | 接诊医生标识 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.admissions[].admission_location | string \| null | VARCHAR(60) | 可空 | 入院前位置 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.admissions[].discharge_location | string \| null | VARCHAR(60) | 可空 | 出院去向 | 非键字段 | 非时间字段 | administrative_end（住院结局） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_hosp.admissions[].insurance | string \| null | VARCHAR(255) | 可空 | 保险类型 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.admissions[].language | string \| null | VARCHAR(10) | 可空 | 患者语言 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.admissions[].marital_status | string \| null | VARCHAR(30) | 可空 | 婚姻状态 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.admissions[].race | string \| null | VARCHAR(80) | 可空 | 种族/民族 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.admissions[].edregtime | string \| null | TIMESTAMP | 可空 | 急诊登记时间 | 非键字段 | event time：事件发生、开始、结束或临床标记时间 | source_event（按源事件时间判断） | 事件时间与可用时间均不晚于决策时点时，才可进入题型快照。 |
| mimic_iv_hosp.admissions[].edouttime | string \| null | TIMESTAMP | 可空 | 急诊离开时间 | 非键字段 | event time：事件发生、开始、结束或临床标记时间 | source_event（按源事件时间判断） | 事件时间与可用时间均不晚于决策时点时，才可进入题型快照。 |
| mimic_iv_hosp.admissions[].hospital_expire_flag | string \| null | SMALLINT | 可空 | 院内死亡标志 | 非键字段 | 非时间字段 | administrative_end（住院结局） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_hosp.transfers[].subject_id | string | INTEGER | NOT NULL | 患者唯一标识 | 患者连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.transfers[].hadm_id | string \| null | INTEGER | 可空 | 住院唯一标识 | 住院连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.transfers[].transfer_id | string | INTEGER | NOT NULL, 主键 | 转移记录唯一标识 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.transfers[].eventtype | string \| null | VARCHAR(10) | 可空 | 事件类型 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.transfers[].careunit | string \| null | VARCHAR(255) | 可空 | 护理单元/病房类型 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.transfers[].intime | string \| null | TIMESTAMP(0) | 可空 | 进入该单元的时间 | 非键字段 | event time：事件发生、开始、结束或临床标记时间 | source_event（按源事件时间判断） | 事件时间与可用时间均不晚于决策时点时，才可进入题型快照。 |
| mimic_iv_hosp.transfers[].outtime | string \| null | TIMESTAMP(0) | 可空 | 离开该单元的时间 | 非键字段 | event time：事件发生、开始、结束或临床标记时间 | source_event（按源事件时间判断） | 事件时间与可用时间均不晚于决策时点时，才可进入题型快照。 |
| mimic_iv_hosp.services[].subject_id | string | INTEGER | NOT NULL | 患者唯一标识 | 患者连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.services[].hadm_id | string | INTEGER | NOT NULL | 住院唯一标识 | 住院连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.services[].transfertime | string | TIMESTAMP(0) | NOT NULL | 转科时间 | 非键字段 | event time：事件发生、开始、结束或临床标记时间 | source_event（按源事件时间判断） | 事件时间与可用时间均不晚于决策时点时，才可进入题型快照。 |
| mimic_iv_hosp.services[].prev_service | string \| null | VARCHAR(20) | 可空 | 前一个服务科室 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.services[].curr_service | string | VARCHAR(20) | NOT NULL | 当前服务科室 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.labevents[].labevent_id | string | INTEGER | NOT NULL, 主键 | 检验事件唯一标识 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.labevents[].subject_id | string | INTEGER | NOT NULL | 患者唯一标识 | 患者连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.labevents[].hadm_id | string \| null | INTEGER | 可空 | 住院唯一标识 | 住院连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.labevents[].specimen_id | string | INTEGER | NOT NULL | 标本唯一标识 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.labevents[].itemid | string | INTEGER | NOT NULL | 检验项目标识 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.labevents[].order_provider_id | string \| null | VARCHAR(10) | 可空 | 开单医生标识 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.labevents[].charttime | string \| null | TIMESTAMP(0) | 可空 | 标本采集时间 | 非键字段 | event time：事件发生、开始、结束或临床标记时间 | source_event（按源事件时间判断） | 事件时间与可用时间均不晚于决策时点时，才可进入题型快照。 |
| mimic_iv_hosp.labevents[].storetime | string \| null | TIMESTAMP(0) | 可空 | 结果入库时间 | 非键字段 | recorded/available time：系统记录、存储、录入或核验时间 | source_event（按源事件时间判断） | 用于判断信息何时可见；不得把记录时间晚于决策时点的事件纳入快照。 |
| mimic_iv_hosp.labevents[].value | string \| null | VARCHAR(200) | 可空 | 检验结果（文本） | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.labevents[].valuenum | string \| null | DOUBLE PRECISION | 可空 | 检验结果（数值） | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.labevents[].valueuom | string \| null | VARCHAR(20) | 可空 | 计量单位 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.labevents[].ref_range_lower | string \| null | DOUBLE PRECISION | 可空 | 参考范围下限 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.labevents[].ref_range_upper | string \| null | DOUBLE PRECISION | 可空 | 参考范围上限 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.labevents[].flag | string \| null | VARCHAR(10) | 可空 | 异常标志 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.labevents[].priority | string \| null | VARCHAR(7) | 可空 | 检验优先级 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.labevents[].comments | string \| null | TEXT | 可空 | 备注信息 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 按决策时点截取；患者原文不得发送到未经批准的外部API。 |
| mimic_iv_hosp.microbiologyevents[].microevent_id | string | INTEGER | NOT NULL, 主键 | 微生物事件唯一标识 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.microbiologyevents[].subject_id | string | INTEGER | NOT NULL | 患者唯一标识 | 患者连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.microbiologyevents[].hadm_id | string \| null | INTEGER | 可空 | 住院唯一标识 | 住院连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.microbiologyevents[].micro_specimen_id | string | INTEGER | NOT NULL | 微生物标本标识 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.microbiologyevents[].order_provider_id | string \| null | VARCHAR(10) | 可空 | 开单医生标识 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.microbiologyevents[].chartdate | string | TIMESTAMP(0) | NOT NULL | 记录日期 | 非键字段 | event time：事件发生、开始、结束或临床标记时间 | source_event（按源事件时间判断） | 事件时间与可用时间均不晚于决策时点时，才可进入题型快照。 |
| mimic_iv_hosp.microbiologyevents[].charttime | string \| null | TIMESTAMP(0) | 可空 | 记录时间 | 非键字段 | event time：事件发生、开始、结束或临床标记时间 | source_event（按源事件时间判断） | 事件时间与可用时间均不晚于决策时点时，才可进入题型快照。 |
| mimic_iv_hosp.microbiologyevents[].spec_itemid | string | INTEGER | NOT NULL | 标本类型标识 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.microbiologyevents[].spec_type_desc | string | VARCHAR(100) | NOT NULL | 标本类型描述 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.microbiologyevents[].test_seq | string | INTEGER | NOT NULL | 测试序号 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.microbiologyevents[].storedate | string \| null | TIMESTAMP(0) | 可空 | 结果存储日期 | 非键字段 | recorded/available time：系统记录、存储、录入或核验时间 | source_event（按源事件时间判断） | 用于判断信息何时可见；不得把记录时间晚于决策时点的事件纳入快照。 |
| mimic_iv_hosp.microbiologyevents[].storetime | string \| null | TIMESTAMP(0) | 可空 | 结果存储时间 | 非键字段 | recorded/available time：系统记录、存储、录入或核验时间 | source_event（按源事件时间判断） | 用于判断信息何时可见；不得把记录时间晚于决策时点的事件纳入快照。 |
| mimic_iv_hosp.microbiologyevents[].test_itemid | string \| null | INTEGER | 可空 | 测试项目标识 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.microbiologyevents[].test_name | string \| null | VARCHAR(100) | 可空 | 测试名称 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.microbiologyevents[].org_itemid | string \| null | INTEGER | 可空 | 微生物标识 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.microbiologyevents[].org_name | string \| null | VARCHAR(100) | 可空 | 微生物名称 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.microbiologyevents[].isolate_num | string \| null | SMALLINT | 可空 | 分离株编号 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.microbiologyevents[].quantity | string \| null | VARCHAR(50) | 可空 | 菌落数量 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.microbiologyevents[].ab_itemid | string \| null | INTEGER | 可空 | 抗生素标识 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.microbiologyevents[].ab_name | string \| null | VARCHAR(30) | 可空 | 抗生素名称 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.microbiologyevents[].dilution_text | string \| null | VARCHAR(10) | 可空 | 稀释度文本 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.microbiologyevents[].dilution_comparison | string \| null | VARCHAR(20) | 可空 | 稀释度比较符 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.microbiologyevents[].dilution_value | string \| null | DOUBLE PRECISION | 可空 | 稀释度数值 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.microbiologyevents[].interpretation | string \| null | VARCHAR(5) | 可空 | 敏感性解读 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.microbiologyevents[].comments | string \| null | TEXT | 可空 | 备注 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 按决策时点截取；患者原文不得发送到未经批准的外部API。 |
| mimic_iv_hosp.poe[].poe_id | string | VARCHAR(25) | NOT NULL, 主键 | 医嘱唯一标识 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.poe[].poe_seq | string | INTEGER | NOT NULL | 医嘱序号 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.poe[].subject_id | string | INTEGER | NOT NULL | 患者唯一标识 | 患者连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.poe[].hadm_id | string \| null | INTEGER | 可空 | 住院唯一标识 | 住院连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.poe[].ordertime | string | TIMESTAMP(0) | NOT NULL | 医嘱下达时间 | 非键字段 | event time：事件发生、开始、结束或临床标记时间 | source_event（按源事件时间判断） | 事件时间与可用时间均不晚于决策时点时，才可进入题型快照。 |
| mimic_iv_hosp.poe[].order_type | string | VARCHAR(25) | NOT NULL | 医嘱类型 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.poe[].order_subtype | string \| null | VARCHAR(50) | 可空 | 医嘱子类型 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.poe[].transaction_type | string \| null | VARCHAR(15) | 可空 | 操作类型 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.poe[].discontinue_of_poe_id | string \| null | VARCHAR(25) | 可空 | 被停止的医嘱ID | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.poe[].discontinued_by_poe_id | string \| null | VARCHAR(25) | 可空 | 停止此医嘱的医嘱ID | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.poe[].order_provider_id | string \| null | VARCHAR(10) | 可空 | 下达医嘱的医生标识 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.poe[].order_status | string \| null | VARCHAR(15) | 可空 | 医嘱状态 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.poe_detail[].poe_id | string | VARCHAR(25) | NOT NULL | 医嘱唯一标识 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.poe_detail[].poe_seq | string | INTEGER | NOT NULL | 医嘱序号 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.poe_detail[].subject_id | string | INTEGER | NOT NULL | 患者唯一标识 | 患者连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.poe_detail[].field_name | string | VARCHAR(255) | NOT NULL | 属性名称 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.poe_detail[].field_value | string \| null | TEXT | 可空 | 属性值 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.pharmacy[].subject_id | string | INTEGER | NOT NULL | 患者唯一标识 | 患者连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.pharmacy[].hadm_id | string | INTEGER | NOT NULL | 住院唯一标识 | 住院连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.pharmacy[].pharmacy_id | string | INTEGER | NOT NULL, 主键 | 药房记录唯一标识 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.pharmacy[].poe_id | string \| null | VARCHAR(25) | 可空 | 医嘱标识 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.pharmacy[].starttime | string \| null | TIMESTAMP(3) | 可空 | 用药开始时间 | 非键字段 | event time：事件发生、开始、结束或临床标记时间 | source_event（按源事件时间判断） | 事件时间与可用时间均不晚于决策时点时，才可进入题型快照。 |
| mimic_iv_hosp.pharmacy[].stoptime | string \| null | TIMESTAMP(3) | 可空 | 用药结束时间 | 非键字段 | event time：事件发生、开始、结束或临床标记时间 | source_event（按源事件时间判断） | 事件时间与可用时间均不晚于决策时点时，才可进入题型快照。 |
| mimic_iv_hosp.pharmacy[].medication | string \| null | TEXT | 可空 | 药物名称 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.pharmacy[].proc_type | string | VARCHAR(50) | NOT NULL | 处方类型 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.pharmacy[].status | string \| null | VARCHAR(50) | 可空 | 处方状态 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.pharmacy[].entertime | string | TIMESTAMP(3) | NOT NULL | 录入时间 | 非键字段 | recorded/available time：系统记录、存储、录入或核验时间 | source_event（按源事件时间判断） | 用于判断信息何时可见；不得把记录时间晚于决策时点的事件纳入快照。 |
| mimic_iv_hosp.pharmacy[].verifiedtime | string \| null | TIMESTAMP(3) | 可空 | 审核时间 | 非键字段 | recorded/available time：系统记录、存储、录入或核验时间 | source_event（按源事件时间判断） | 用于判断信息何时可见；不得把记录时间晚于决策时点的事件纳入快照。 |
| mimic_iv_hosp.pharmacy[].route | string \| null | VARCHAR(50) | 可空 | 给药途径 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.pharmacy[].frequency | string \| null | VARCHAR(50) | 可空 | 给药频次 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.pharmacy[].disp_sched | string \| null | VARCHAR(255) | 可空 | 配药时间表 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.pharmacy[].infusion_type | string \| null | VARCHAR(15) | 可空 | 输液类型 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.pharmacy[].sliding_scale | string \| null | VARCHAR(1) | 可空 | 滑动比例标志 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.pharmacy[].lockout_interval | string \| null | VARCHAR(50) | 可空 | PCA锁定间隔 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.pharmacy[].basal_rate | string \| null | REAL | 可空 | 基础速率 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.pharmacy[].one_hr_max | string \| null | VARCHAR(10) | 可空 | 每小时最大剂量 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.pharmacy[].doses_per_24_hrs | string \| null | REAL | 可空 | 每日给药次数 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.pharmacy[].duration | string \| null | REAL | 可空 | 持续时间数值 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.pharmacy[].duration_interval | string \| null | VARCHAR(50) | 可空 | 持续时间单位 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.pharmacy[].expiration_value | string \| null | INTEGER | 可空 | 有效期数值 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.pharmacy[].expiration_unit | string \| null | VARCHAR(50) | 可空 | 有效期单位 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.pharmacy[].expirationdate | string \| null | TIMESTAMP(3) | 可空 | 过期日期 | 非键字段 | event time：事件发生、开始、结束或临床标记时间 | source_event（按源事件时间判断） | 事件时间与可用时间均不晚于决策时点时，才可进入题型快照。 |
| mimic_iv_hosp.pharmacy[].dispensation | string \| null | VARCHAR(50) | 可空 | 配发来源 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.pharmacy[].fill_quantity | string \| null | VARCHAR(50) | 可空 | 配发数量 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.prescriptions[].subject_id | string | INTEGER | NOT NULL | 患者唯一标识 | 患者连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.prescriptions[].hadm_id | string | INTEGER | NOT NULL | 住院唯一标识 | 住院连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.prescriptions[].pharmacy_id | string | INTEGER | NOT NULL | 药房记录标识 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.prescriptions[].poe_id | string \| null | VARCHAR(25) | 可空 | 医嘱标识 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.prescriptions[].poe_seq | string \| null | INTEGER | 可空 | 医嘱序号 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.prescriptions[].order_provider_id | string \| null | VARCHAR(10) | 可空 | 开单医生标识 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.prescriptions[].starttime | string \| null | TIMESTAMP(3) | 可空 | 处方开始时间 | 非键字段 | event time：事件发生、开始、结束或临床标记时间 | source_event（按源事件时间判断） | 事件时间与可用时间均不晚于决策时点时，才可进入题型快照。 |
| mimic_iv_hosp.prescriptions[].stoptime | string \| null | TIMESTAMP(3) | 可空 | 处方结束时间 | 非键字段 | event time：事件发生、开始、结束或临床标记时间 | source_event（按源事件时间判断） | 事件时间与可用时间均不晚于决策时点时，才可进入题型快照。 |
| mimic_iv_hosp.prescriptions[].drug_type | string | VARCHAR(20) | NOT NULL | 药物成分类型 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.prescriptions[].drug | string | VARCHAR(255) | NOT NULL | 药物名称 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.prescriptions[].formulary_drug_cd | string \| null | VARCHAR(50) | 可空 | 医院药物目录代码 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.prescriptions[].gsn | string \| null | VARCHAR(255) | 可空 | 通用序列号 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.prescriptions[].ndc | string \| null | VARCHAR(25) | 可空 | 国家药品编码 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.prescriptions[].prod_strength | string \| null | VARCHAR(255) | 可空 | 药品规格 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.prescriptions[].form_rx | string \| null | VARCHAR(25) | 可空 | 药品剂型 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.prescriptions[].dose_val_rx | string \| null | VARCHAR(100) | 可空 | 处方剂量值 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.prescriptions[].dose_unit_rx | string \| null | VARCHAR(50) | 可空 | 处方剂量单位 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.prescriptions[].form_val_disp | string \| null | VARCHAR(50) | 可空 | 单次给药量 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.prescriptions[].form_unit_disp | string \| null | VARCHAR(50) | 可空 | 单次给药单位 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.prescriptions[].doses_per_24_hrs | string \| null | REAL | 可空 | 每24小时给药次数 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.prescriptions[].route | string \| null | VARCHAR(50) | 可空 | 给药途径 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.emar[].subject_id | string | INTEGER | NOT NULL | 患者唯一标识 | 患者连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.emar[].hadm_id | string \| null | INTEGER | 可空 | 住院唯一标识 | 住院连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.emar[].emar_id | string | VARCHAR(25) | NOT NULL, 主键 | 给药记录唯一标识 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.emar[].emar_seq | string | INTEGER | NOT NULL | 给药序号 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.emar[].poe_id | string | VARCHAR(25) | NOT NULL | 医嘱标识 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.emar[].pharmacy_id | string \| null | INTEGER | 可空 | 药房记录标识 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.emar[].enter_provider_id | string \| null | VARCHAR(10) | 可空 | 录入人员标识 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.emar[].charttime | string | TIMESTAMP | NOT NULL | 给药时间 | 非键字段 | event time：事件发生、开始、结束或临床标记时间 | source_event（按源事件时间判断） | 事件时间与可用时间均不晚于决策时点时，才可进入题型快照。 |
| mimic_iv_hosp.emar[].medication | string \| null | TEXT | 可空 | 药物名称 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.emar[].event_txt | string \| null | VARCHAR(100) | 可空 | 给药事件状态 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.emar[].scheduletime | string \| null | TIMESTAMP | 可空 | 计划给药时间 | 非键字段 | event time：事件发生、开始、结束或临床标记时间 | source_event（按源事件时间判断） | 事件时间与可用时间均不晚于决策时点时，才可进入题型快照。 |
| mimic_iv_hosp.emar[].storetime | string | TIMESTAMP | NOT NULL | 记录存储时间 | 非键字段 | recorded/available time：系统记录、存储、录入或核验时间 | source_event（按源事件时间判断） | 用于判断信息何时可见；不得把记录时间晚于决策时点的事件纳入快照。 |
| mimic_iv_hosp.emar_detail[].subject_id | string | INTEGER | NOT NULL | 患者唯一标识 | 患者连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.emar_detail[].emar_id | string | VARCHAR(25) | NOT NULL | 给药记录标识 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.emar_detail[].emar_seq | string | INTEGER | NOT NULL | 给药序号 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.emar_detail[].parent_field_ordinal | string \| null | VARCHAR(10) | 可空 | 父字段序号 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.emar_detail[].administration_type | string \| null | VARCHAR(50) | 可空 | 给药类型 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.emar_detail[].pharmacy_id | string \| null | INTEGER | 可空 | 药房记录标识 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_hosp.emar_detail[].barcode_type | string \| null | VARCHAR(4) | 可空 | 条形码类型 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.emar_detail[].reason_for_no_barcode | string \| null | TEXT | 可空 | 未扫码原因 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.emar_detail[].complete_dose_not_given | string \| null | VARCHAR(5) | 可空 | 完整剂量是否未给 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.emar_detail[].dose_due | string \| null | VARCHAR(100) | 可空 | 应给剂量 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.emar_detail[].dose_due_unit | string \| null | VARCHAR(50) | 可空 | 应给剂量单位 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.emar_detail[].dose_given | string \| null | VARCHAR(255) | 可空 | 实际给予剂量 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.emar_detail[].dose_given_unit | string \| null | VARCHAR(50) | 可空 | 实际给予剂量单位 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.emar_detail[].will_remainder_of_dose_be_given | string \| null | VARCHAR(5) | 可空 | 剩余剂量是否会给 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.emar_detail[].product_amount_given | string \| null | VARCHAR(30) | 可空 | 产品给予量 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.emar_detail[].product_unit | string \| null | VARCHAR(30) | 可空 | 产品单位 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.emar_detail[].product_code | string \| null | VARCHAR(30) | 可空 | 产品代码 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.emar_detail[].product_description | string \| null | VARCHAR(255) | 可空 | 产品描述 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.emar_detail[].product_description_other | string \| null | VARCHAR(255) | 可空 | 其他产品描述 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.emar_detail[].prior_infusion_rate | string \| null | VARCHAR(40) | 可空 | 之前输液速率 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.emar_detail[].infusion_rate | string \| null | VARCHAR(40) | 可空 | 当前输液速率 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.emar_detail[].infusion_rate_adjustment | string \| null | VARCHAR(50) | 可空 | 速率调整 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.emar_detail[].infusion_rate_adjustment_amount | string \| null | VARCHAR(30) | 可空 | 速率调整量 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.emar_detail[].infusion_rate_unit | string \| null | VARCHAR(30) | 可空 | 输液速率单位 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.emar_detail[].route | string \| null | VARCHAR(10) | 可空 | 给药途径 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.emar_detail[].infusion_complete | string \| null | VARCHAR(1) | 可空 | 输液是否完成 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.emar_detail[].completion_interval | string \| null | VARCHAR(50) | 可空 | 完成时间间隔 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.emar_detail[].new_iv_bag_hung | string \| null | VARCHAR(1) | 可空 | 是否挂新袋 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.emar_detail[].continued_infusion_in_other_location | string \| null | VARCHAR(1) | 可空 | 是否在其他位置继续输液 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.emar_detail[].restart_interval | string \| null | TEXT | 可空 | 重启间隔 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.emar_detail[].side | string \| null | VARCHAR(10) | 可空 | 身体侧（左/右） | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.emar_detail[].site | string \| null | VARCHAR(255) | 可空 | 给药部位 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.emar_detail[].non_formulary_visual_verification | string \| null | VARCHAR(1) | 可空 | 非处方目录药物视觉确认 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_hosp.diagnoses_icd[].subject_id | string | INTEGER | NOT NULL | 患者唯一标识 | 患者连接键 | 非时间字段 | post_hoc（后验资料） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_hosp.diagnoses_icd[].hadm_id | string | INTEGER | NOT NULL | 住院唯一标识 | 住院连接键 | 非时间字段 | post_hoc（后验资料） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_hosp.diagnoses_icd[].seq_num | string | INTEGER | NOT NULL | 诊断序号 | 源记录标识或连接键 | 非时间字段 | post_hoc（后验资料） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_hosp.diagnoses_icd[].icd_code | string | VARCHAR(7) | NOT NULL | ICD诊断编码 | 非键字段 | 非时间字段 | post_hoc（后验资料） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_hosp.diagnoses_icd[].icd_version | string | INTEGER | NOT NULL | ICD版本（9或10） | 非键字段 | 非时间字段 | post_hoc（后验资料） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_hosp.procedures_icd[].subject_id | string | INTEGER | NOT NULL | 患者唯一标识 | 患者连接键 | 非时间字段 | post_hoc（后验资料） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_hosp.procedures_icd[].hadm_id | string | INTEGER | NOT NULL | 住院唯一标识 | 住院连接键 | 非时间字段 | post_hoc（后验资料） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_hosp.procedures_icd[].seq_num | string | INTEGER | NOT NULL | 操作序号 | 源记录标识或连接键 | 非时间字段 | post_hoc（后验资料） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_hosp.procedures_icd[].chartdate | string | DATE | NOT NULL | 操作日期 | 非键字段 | event time：事件发生、开始、结束或临床标记时间 | post_hoc（后验资料） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_hosp.procedures_icd[].icd_code | string | VARCHAR(7) | NOT NULL | ICD操作编码 | 非键字段 | 非时间字段 | post_hoc（后验资料） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_hosp.procedures_icd[].icd_version | string | INTEGER | NOT NULL | ICD版本（9或10） | 非键字段 | 非时间字段 | post_hoc（后验资料） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_hosp.hcpcsevents[].subject_id | string | INTEGER | NOT NULL | 患者唯一标识 | 患者连接键 | 非时间字段 | post_hoc（后验资料） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_hosp.hcpcsevents[].hadm_id | string | INTEGER | NOT NULL | 住院唯一标识 | 住院连接键 | 非时间字段 | post_hoc（后验资料） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_hosp.hcpcsevents[].chartdate | string \| null | DATE | 可空 | 编码对应的日期 | 非键字段 | event time：事件发生、开始、结束或临床标记时间 | post_hoc（后验资料） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_hosp.hcpcsevents[].hcpcs_cd | string | CHAR(5) | NOT NULL | HCPCS/CPT编码 | 非键字段 | 非时间字段 | post_hoc（后验资料） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_hosp.hcpcsevents[].seq_num | string | INTEGER | NOT NULL | 序号 | 源记录标识或连接键 | 非时间字段 | post_hoc（后验资料） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_hosp.hcpcsevents[].short_description | string \| null | VARCHAR(180) | 可空 | 编码简短描述 | 非键字段 | 非时间字段 | post_hoc（后验资料） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_hosp.drgcodes[].subject_id | string | INTEGER | NOT NULL | 患者唯一标识 | 患者连接键 | 非时间字段 | post_hoc（后验资料） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_hosp.drgcodes[].hadm_id | string | INTEGER | NOT NULL | 住院唯一标识 | 住院连接键 | 非时间字段 | post_hoc（后验资料） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_hosp.drgcodes[].drg_type | string | VARCHAR(4) | NOT NULL | DRG编码体系类型 | 非键字段 | 非时间字段 | post_hoc（后验资料） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_hosp.drgcodes[].drg_code | string | VARCHAR(10) | NOT NULL | DRG编码 | 非键字段 | 非时间字段 | post_hoc（后验资料） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_hosp.drgcodes[].description | string \| null | VARCHAR(195) | 可空 | DRG描述 | 非键字段 | 非时间字段 | post_hoc（后验资料） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_hosp.drgcodes[].drg_severity | string \| null | SMALLINT | 可空 | 疾病严重度 | 非键字段 | 非时间字段 | post_hoc（后验资料） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_hosp.drgcodes[].drg_mortality | string \| null | SMALLINT | 可空 | 死亡风险等级 | 非键字段 | 非时间字段 | post_hoc（后验资料） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_icu.icustays[].subject_id | string | INTEGER | NOT NULL | 患者唯一标识 | 患者连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_icu.icustays[].hadm_id | string | INTEGER | NOT NULL | 住院唯一标识 | 住院连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_icu.icustays[].stay_id | string | INTEGER | NOT NULL, 主键 | ICU入住唯一标识 | ED/ICU stay连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_icu.icustays[].first_careunit | string \| null | VARCHAR(20) | 可空 | 首个ICU类型 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_icu.icustays[].last_careunit | string \| null | VARCHAR(20) | 可空 | 最后ICU类型 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_icu.icustays[].intime | string | TIMESTAMP(0) | NOT NULL | ICU入住时间 | 非键字段 | event time：事件发生、开始、结束或临床标记时间 | source_event（按源事件时间判断） | 事件时间与可用时间均不晚于决策时点时，才可进入题型快照。 |
| mimic_iv_icu.icustays[].outtime | string | TIMESTAMP(0) | NOT NULL | ICU离开时间 | 非键字段 | event time：事件发生、开始、结束或临床标记时间 | source_event（按源事件时间判断） | 事件时间与可用时间均不晚于决策时点时，才可进入题型快照。 |
| mimic_iv_icu.icustays[].los | string \| null | DOUBLE PRECISION | 可空 | ICU住院时长（天） | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_icu.datetimeevents[].subject_id | string | INTEGER | NOT NULL | 患者唯一标识 | 患者连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_icu.datetimeevents[].hadm_id | string | INTEGER | NOT NULL | 住院唯一标识 | 住院连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_icu.datetimeevents[].stay_id | string | INTEGER | NOT NULL | ICU入住标识 | ED/ICU stay连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_icu.datetimeevents[].caregiver_id | string \| null | INTEGER | 可空 | 记录护士标识 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_icu.datetimeevents[].charttime | string | TIMESTAMP(0) | NOT NULL | 记录时间 | 非键字段 | event time：事件发生、开始、结束或临床标记时间 | source_event（按源事件时间判断） | 事件时间与可用时间均不晚于决策时点时，才可进入题型快照。 |
| mimic_iv_icu.datetimeevents[].storetime | string \| null | TIMESTAMP(0) | 可空 | 存储时间 | 非键字段 | recorded/available time：系统记录、存储、录入或核验时间 | source_event（按源事件时间判断） | 用于判断信息何时可见；不得把记录时间晚于决策时点的事件纳入快照。 |
| mimic_iv_icu.datetimeevents[].itemid | string | INTEGER | NOT NULL | 项目标识 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_icu.datetimeevents[].value | string | TIMESTAMP(0) | NOT NULL | 记录的日期时间值 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_icu.datetimeevents[].valueuom | string \| null | VARCHAR(50) | 可空 | 值的单位 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_icu.datetimeevents[].warning | string \| null | SMALLINT | 可空 | 警告标志 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_icu.ingredientevents[].subject_id | string | INTEGER | NOT NULL | 患者唯一标识 | 患者连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_icu.ingredientevents[].hadm_id | string | INTEGER | NOT NULL | 住院唯一标识 | 住院连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_icu.ingredientevents[].stay_id | string | INTEGER | NOT NULL | ICU入住标识 | ED/ICU stay连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_icu.ingredientevents[].caregiver_id | string \| null | INTEGER | 可空 | 记录护士标识 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_icu.ingredientevents[].starttime | string | TIMESTAMP(0) | NOT NULL | 开始时间 | 非键字段 | event time：事件发生、开始、结束或临床标记时间 | source_event（按源事件时间判断） | 事件时间与可用时间均不晚于决策时点时，才可进入题型快照。 |
| mimic_iv_icu.ingredientevents[].endtime | string | TIMESTAMP(0) | NOT NULL | 结束时间 | 非键字段 | event time：事件发生、开始、结束或临床标记时间 | source_event（按源事件时间判断） | 事件时间与可用时间均不晚于决策时点时，才可进入题型快照。 |
| mimic_iv_icu.ingredientevents[].storetime | string \| null | TIMESTAMP(0) | 可空 | 存储时间 | 非键字段 | recorded/available time：系统记录、存储、录入或核验时间 | source_event（按源事件时间判断） | 用于判断信息何时可见；不得把记录时间晚于决策时点的事件纳入快照。 |
| mimic_iv_icu.ingredientevents[].itemid | string | INTEGER | NOT NULL | 成分标识 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_icu.ingredientevents[].amount | string \| null | DOUBLE PRECISION | 可空 | 给予量 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_icu.ingredientevents[].amountuom | string \| null | VARCHAR(20) | 可空 | 给予量单位 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_icu.ingredientevents[].rate | string \| null | DOUBLE PRECISION | 可空 | 输注速率 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_icu.ingredientevents[].rateuom | string \| null | VARCHAR(20) | 可空 | 速率单位 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_icu.ingredientevents[].orderid | string \| null | INTEGER | 可空 | 医嘱ID | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_icu.ingredientevents[].linkorderid | string \| null | INTEGER | 可空 | 关联医嘱ID | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_icu.ingredientevents[].statusdescription | string \| null | VARCHAR(20) | 可空 | 状态描述 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_icu.ingredientevents[].originalamount | string \| null | DOUBLE PRECISION | 可空 | 原始量 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_icu.ingredientevents[].originalrate | string \| null | DOUBLE PRECISION | 可空 | 原始速率 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_icu.inputevents[].subject_id | string | INTEGER | NOT NULL | 患者唯一标识 | 患者连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_icu.inputevents[].hadm_id | string | INTEGER | NOT NULL | 住院唯一标识 | 住院连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_icu.inputevents[].stay_id | string | INTEGER | NOT NULL | ICU入住标识 | ED/ICU stay连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_icu.inputevents[].caregiver_id | string \| null | INTEGER | 可空 | 记录护士标识 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_icu.inputevents[].starttime | string | TIMESTAMP(0) | NOT NULL | 开始时间 | 非键字段 | event time：事件发生、开始、结束或临床标记时间 | source_event（按源事件时间判断） | 事件时间与可用时间均不晚于决策时点时，才可进入题型快照。 |
| mimic_iv_icu.inputevents[].endtime | string | TIMESTAMP(0) | NOT NULL | 结束时间 | 非键字段 | event time：事件发生、开始、结束或临床标记时间 | source_event（按源事件时间判断） | 事件时间与可用时间均不晚于决策时点时，才可进入题型快照。 |
| mimic_iv_icu.inputevents[].storetime | string \| null | TIMESTAMP(0) | 可空 | 存储时间 | 非键字段 | recorded/available time：系统记录、存储、录入或核验时间 | source_event（按源事件时间判断） | 用于判断信息何时可见；不得把记录时间晚于决策时点的事件纳入快照。 |
| mimic_iv_icu.inputevents[].itemid | string | INTEGER | NOT NULL | 药物/液体标识 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_icu.inputevents[].amount | string \| null | DOUBLE PRECISION | 可空 | 给药量 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_icu.inputevents[].amountuom | string \| null | VARCHAR(30) | 可空 | 给药量单位 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_icu.inputevents[].rate | string \| null | DOUBLE PRECISION | 可空 | 输注速率 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_icu.inputevents[].rateuom | string \| null | VARCHAR(30) | 可空 | 速率单位 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_icu.inputevents[].orderid | string \| null | BIGINT | 可空 | 医嘱ID | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_icu.inputevents[].linkorderid | string \| null | BIGINT | 可空 | 关联医嘱ID | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_icu.inputevents[].ordercategoryname | string \| null | VARCHAR(100) | 可空 | 医嘱类别名称 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_icu.inputevents[].secondaryordercategoryname | string \| null | VARCHAR(100) | 可空 | 次级类别名称 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_icu.inputevents[].ordercomponenttypedescription | string \| null | VARCHAR(200) | 可空 | 成分类型描述 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_icu.inputevents[].ordercategorydescription | string \| null | VARCHAR(50) | 可空 | 医嘱类别描述 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_icu.inputevents[].patientweight | string \| null | DOUBLE PRECISION | 可空 | 患者体重(kg) | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_icu.inputevents[].totalamount | string \| null | DOUBLE PRECISION | 可空 | 总量 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_icu.inputevents[].totalamountuom | string \| null | VARCHAR(50) | 可空 | 总量单位 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_icu.inputevents[].isopenbag | string \| null | SMALLINT | 可空 | 是否开放袋 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_icu.inputevents[].continueinnextdept | string \| null | SMALLINT | 可空 | 是否在转入下一科室后继续该输入事件 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_icu.inputevents[].statusdescription | string \| null | VARCHAR(30) | 可空 | 状态描述 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_icu.inputevents[].originalamount | string \| null | DOUBLE PRECISION | 可空 | 原始药量 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_icu.inputevents[].originalrate | string \| null | DOUBLE PRECISION | 可空 | 原始速率 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_icu.outputevents[].subject_id | string | INTEGER | NOT NULL | 患者唯一标识 | 患者连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_icu.outputevents[].hadm_id | string | INTEGER | NOT NULL | 住院唯一标识 | 住院连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_icu.outputevents[].stay_id | string | INTEGER | NOT NULL | ICU入住标识 | ED/ICU stay连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_icu.outputevents[].caregiver_id | string \| null | INTEGER | 可空 | 记录护士标识 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_icu.outputevents[].charttime | string | TIMESTAMP(3) | NOT NULL | 记录时间 | 非键字段 | event time：事件发生、开始、结束或临床标记时间 | source_event（按源事件时间判断） | 事件时间与可用时间均不晚于决策时点时，才可进入题型快照。 |
| mimic_iv_icu.outputevents[].storetime | string \| null | TIMESTAMP(3) | 可空 | 存储时间 | 非键字段 | recorded/available time：系统记录、存储、录入或核验时间 | source_event（按源事件时间判断） | 用于判断信息何时可见；不得把记录时间晚于决策时点的事件纳入快照。 |
| mimic_iv_icu.outputevents[].itemid | string | INTEGER | NOT NULL | 排出项目标识 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_icu.outputevents[].value | string \| null | DOUBLE PRECISION | 可空 | 排出量 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_icu.outputevents[].valueuom | string \| null | VARCHAR(20) | 可空 | 计量单位 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_icu.procedureevents[].subject_id | string | INTEGER | NOT NULL | 患者唯一标识 | 患者连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_icu.procedureevents[].hadm_id | string | INTEGER | NOT NULL | 住院唯一标识 | 住院连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_icu.procedureevents[].stay_id | string | INTEGER | NOT NULL | ICU入住标识 | ED/ICU stay连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_icu.procedureevents[].caregiver_id | string \| null | INTEGER | 可空 | 记录护士标识 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_icu.procedureevents[].starttime | string | TIMESTAMP | NOT NULL | 操作开始时间 | 非键字段 | event time：事件发生、开始、结束或临床标记时间 | source_event（按源事件时间判断） | 事件时间与可用时间均不晚于决策时点时，才可进入题型快照。 |
| mimic_iv_icu.procedureevents[].endtime | string | TIMESTAMP | NOT NULL | 操作结束时间 | 非键字段 | event time：事件发生、开始、结束或临床标记时间 | source_event（按源事件时间判断） | 事件时间与可用时间均不晚于决策时点时，才可进入题型快照。 |
| mimic_iv_icu.procedureevents[].storetime | string \| null | TIMESTAMP | 可空 | 记录存储时间 | 非键字段 | recorded/available time：系统记录、存储、录入或核验时间 | source_event（按源事件时间判断） | 用于判断信息何时可见；不得把记录时间晚于决策时点的事件纳入快照。 |
| mimic_iv_icu.procedureevents[].itemid | string | INTEGER | NOT NULL | 操作项目标识 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_icu.procedureevents[].value | string \| null | DOUBLE PRECISION | 可空 | 持续时间（数值） | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_icu.procedureevents[].valueuom | string \| null | VARCHAR(20) | 可空 | 时间单位 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_icu.procedureevents[].location | string \| null | VARCHAR(100) | 可空 | 操作部位 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_icu.procedureevents[].locationcategory | string \| null | VARCHAR(50) | 可空 | 部位类别 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_icu.procedureevents[].orderid | string \| null | INTEGER | 可空 | 医嘱ID | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_icu.procedureevents[].linkorderid | string \| null | INTEGER | 可空 | 关联医嘱ID | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_icu.procedureevents[].ordercategoryname | string \| null | VARCHAR(50) | 可空 | 医嘱类别 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_icu.procedureevents[].ordercategorydescription | string \| null | VARCHAR(30) | 可空 | 类别描述 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_icu.procedureevents[].patientweight | string \| null | DOUBLE PRECISION | 可空 | 患者体重 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_icu.procedureevents[].isopenbag | string \| null | SMALLINT | 可空 | 是否开放袋 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_icu.procedureevents[].continueinnextdept | string \| null | SMALLINT | 可空 | 是否在下一科室继续 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_icu.procedureevents[].statusdescription | string \| null | VARCHAR(20) | 可空 | 状态描述 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_icu.procedureevents[].originalamount | string \| null | DOUBLE PRECISION | 可空 | 原始量 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_icu.procedureevents[].originalrate | string \| null | DOUBLE PRECISION | 可空 | 原始速率 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_ed.edstays[].subject_id | string | INTEGER | NOT NULL | 患者唯一标识 | 患者连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_ed.edstays[].hadm_id | string \| null | INTEGER | 可空 | 住院唯一标识 | 住院连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_ed.edstays[].stay_id | string | INTEGER | NOT NULL | 急诊就诊唯一标识 | ED/ICU stay连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_ed.edstays[].intime | string | TIMESTAMP(0) | NOT NULL | 急诊入科时间 | 非键字段 | event time：事件发生、开始、结束或临床标记时间 | source_event（按源事件时间判断） | 事件时间与可用时间均不晚于决策时点时，才可进入题型快照。 |
| mimic_iv_ed.edstays[].outtime | string | TIMESTAMP(0) | NOT NULL | 急诊出科时间 | 非键字段 | event time：事件发生、开始、结束或临床标记时间 | clinical_end（急诊结局） | 仅在决策时点已到相应临床阶段时可见；更早快照必须屏蔽。 |
| mimic_iv_ed.edstays[].gender | string | VARCHAR(1) | NOT NULL | 性别 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_ed.edstays[].race | string \| null | VARCHAR(60) | 可空 | 种族 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_ed.edstays[].arrival_transport | string | VARCHAR(50) | NOT NULL | 到达方式 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_ed.edstays[].disposition | string \| null | VARCHAR(255) | 可空 | 离开去向 | 非键字段 | 非时间字段 | clinical_end（急诊结局） | 仅在决策时点已到相应临床阶段时可见；更早快照必须屏蔽。 |
| mimic_iv_ed.triage[].subject_id | string | INTEGER | NOT NULL | 患者唯一标识 | 患者连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_ed.triage[].stay_id | string | INTEGER | NOT NULL | 急诊就诊唯一标识 | ED/ICU stay连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_ed.triage[].temperature | string \| null | NUMERIC(10,4) | 可空 | 体温（华氏度） | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_ed.triage[].heartrate | string \| null | NUMERIC(10,4) | 可空 | 心率（次/分） | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_ed.triage[].resprate | string \| null | NUMERIC(10,4) | 可空 | 呼吸频率（次/分） | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_ed.triage[].o2sat | string \| null | NUMERIC(10,4) | 可空 | 血氧饱和度（%） | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_ed.triage[].sbp | string \| null | NUMERIC(10,4) | 可空 | 收缩压（mmHg） | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_ed.triage[].dbp | string \| null | NUMERIC(10,4) | 可空 | 舒张压（mmHg） | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_ed.triage[].pain | string \| null | TEXT | 可空 | 疼痛评分（0-10） | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_ed.triage[].acuity | string \| null | NUMERIC(10,4) | 可空 | ESI分级（1-5） | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_ed.triage[].chiefcomplaint | string \| null | VARCHAR(255) | 可空 | 主诉 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_ed.vitalsign[].subject_id | string | INTEGER | NOT NULL | 患者唯一标识 | 患者连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_ed.vitalsign[].stay_id | string | INTEGER | NOT NULL | 急诊就诊唯一标识 | ED/ICU stay连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_ed.vitalsign[].charttime | string \| null | TIMESTAMP(0) | 可空 | 记录时间 | 非键字段 | event time：事件发生、开始、结束或临床标记时间 | source_event（按源事件时间判断） | 事件时间与可用时间均不晚于决策时点时，才可进入题型快照。 |
| mimic_iv_ed.vitalsign[].temperature | string \| null | NUMERIC(10,4) | 可空 | 体温（华氏度） | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_ed.vitalsign[].heartrate | string \| null | NUMERIC(10,4) | 可空 | 心率（次/分） | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_ed.vitalsign[].resprate | string \| null | NUMERIC(10,4) | 可空 | 呼吸频率（次/分） | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_ed.vitalsign[].o2sat | string \| null | NUMERIC(10,4) | 可空 | 血氧饱和度（%） | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_ed.vitalsign[].sbp | string \| null | INTEGER | 可空 | 收缩压（mmHg） | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_ed.vitalsign[].dbp | string \| null | INTEGER | 可空 | 舒张压（mmHg） | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_ed.vitalsign[].rhythm | string \| null | TEXT | 可空 | 心律 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_ed.vitalsign[].pain | string \| null | TEXT | 可空 | 疼痛评分（0-10） | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_ed.diagnosis[].subject_id | string | INTEGER | NOT NULL | 患者唯一标识 | 患者连接键 | 非时间字段 | post_hoc（后验资料） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_ed.diagnosis[].stay_id | string | INTEGER | NOT NULL | 急诊就诊唯一标识 | ED/ICU stay连接键 | 非时间字段 | post_hoc（后验资料） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_ed.diagnosis[].seq_num | string | INTEGER | NOT NULL | 诊断序号 | 源记录标识或连接键 | 非时间字段 | post_hoc（后验资料） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_ed.diagnosis[].icd_code | string | VARCHAR(10) | NOT NULL | ICD诊断编码 | 非键字段 | 非时间字段 | post_hoc（后验资料） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_ed.diagnosis[].icd_version | string | INTEGER | NOT NULL | ICD版本（9或10） | 非键字段 | 非时间字段 | post_hoc（后验资料） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_ed.diagnosis[].icd_title | string | TEXT | NOT NULL | 诊断描述 | 非键字段 | 非时间字段 | post_hoc（后验资料） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_ed.medrecon[].subject_id | string | INTEGER | NOT NULL | 患者唯一标识 | 患者连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_ed.medrecon[].stay_id | string | INTEGER | NOT NULL | 急诊就诊唯一标识 | ED/ICU stay连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_ed.medrecon[].charttime | string \| null | TIMESTAMP(0) | 可空 | 记录时间 | 非键字段 | event time：事件发生、开始、结束或临床标记时间 | source_event（按源事件时间判断） | 事件时间与可用时间均不晚于决策时点时，才可进入题型快照。 |
| mimic_iv_ed.medrecon[].name | string \| null | VARCHAR(255) | 可空 | 药物名称 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_ed.medrecon[].gsn | string \| null | VARCHAR(10) | 可空 | GSN编码 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_ed.medrecon[].ndc | string \| null | VARCHAR(12) | 可空 | NDC编码 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_ed.medrecon[].etc_rn | string | SMALLINT | NOT NULL | 药物分类序号 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_ed.medrecon[].etccode | string \| null | VARCHAR(8) | 可空 | ETC分类编码 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_ed.medrecon[].etcdescription | string \| null | VARCHAR(255) | 可空 | ETC分类描述 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_ed.pyxis[].subject_id | string | INTEGER | NOT NULL | 患者唯一标识 | 患者连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_ed.pyxis[].stay_id | string | INTEGER | NOT NULL | 急诊就诊唯一标识 | ED/ICU stay连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_ed.pyxis[].charttime | string \| null | TIMESTAMP(0) | 可空 | 发药记录时间 | 非键字段 | event time：事件发生、开始、结束或临床标记时间 | source_event（按源事件时间判断） | 事件时间与可用时间均不晚于决策时点时，才可进入题型快照。 |
| mimic_iv_ed.pyxis[].med_rn | string | SMALLINT | NOT NULL | 单次发药的行号 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_ed.pyxis[].name | string \| null | VARCHAR(255) | 可空 | 药物名称 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_ed.pyxis[].gsn_rn | string | SMALLINT | NOT NULL | GSN分组行号 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_ed.pyxis[].gsn | string \| null | VARCHAR(10) | 可空 | GSN编码 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_note.discharge[].note_id | string | VARCHAR(25) | NOT NULL, 主键 | 文档唯一标识 | 源记录标识或连接键 | 非时间字段 | post_hoc（后验资料） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_note.discharge[].subject_id | string | INTEGER | NOT NULL | 患者唯一标识 | 患者连接键 | 非时间字段 | post_hoc（后验资料） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_note.discharge[].hadm_id | string | INTEGER | NOT NULL | 住院唯一标识 | 住院连接键 | 非时间字段 | post_hoc（后验资料） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_note.discharge[].note_type | string | CHAR(2) | NOT NULL | 文档类型 | 非键字段 | 非时间字段 | post_hoc（后验资料） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_note.discharge[].note_seq | string | INTEGER | NOT NULL | 文档序号 | 源记录标识或连接键 | 非时间字段 | post_hoc（后验资料） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_note.discharge[].charttime | string | TIMESTAMP | NOT NULL | 文档记录时间 | 非键字段 | event time：事件发生、开始、结束或临床标记时间 | post_hoc（后验资料） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_note.discharge[].storetime | string \| null | TIMESTAMP | 可空 | 文档存储时间 | 非键字段 | recorded/available time：系统记录、存储、录入或核验时间 | post_hoc（后验资料） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_note.discharge[].text | string | TEXT | NOT NULL | 出院小结全文 | 非键字段 | 非时间字段 | post_hoc（后验资料） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_note.discharge_detail[].note_id | string | VARCHAR(25) | NOT NULL | 文档唯一标识 | 源记录标识或连接键 | 非时间字段 | post_hoc（后验资料） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_note.discharge_detail[].subject_id | string | INTEGER | NOT NULL | 患者唯一标识 | 患者连接键 | 非时间字段 | post_hoc（后验资料） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_note.discharge_detail[].field_name | string | VARCHAR(255) | NOT NULL | 属性名称 | 非键字段 | 非时间字段 | post_hoc（后验资料） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_note.discharge_detail[].field_value | string | TEXT | NOT NULL | 属性值 | 非键字段 | 非时间字段 | post_hoc（后验资料） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_note.discharge_detail[].field_ordinal | string | INTEGER | NOT NULL | 属性序号 | 源记录标识或连接键 | 非时间字段 | post_hoc（后验资料） | 禁止进入前瞻性决策题干；仅可用于队列、标签或事后审核。 |
| mimic_iv_note.radiology[].note_id | string | VARCHAR(25) | NOT NULL, 主键 | 报告唯一标识 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_note.radiology[].subject_id | string | INTEGER | NOT NULL | 患者唯一标识 | 患者连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_note.radiology[].hadm_id | string | INTEGER | NOT NULL | 住院唯一标识 | 住院连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_note.radiology[].note_type | string | CHAR(2) | NOT NULL | 报告类型 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_note.radiology[].note_seq | string | INTEGER | NOT NULL | 报告序号 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_note.radiology[].charttime | string | TIMESTAMP | NOT NULL | 检查时间 | 非键字段 | event time：事件发生、开始、结束或临床标记时间 | source_event（按源事件时间判断） | 事件时间与可用时间均不晚于决策时点时，才可进入题型快照。 |
| mimic_iv_note.radiology[].storetime | string \| null | TIMESTAMP | 可空 | 报告完成时间 | 非键字段 | recorded/available time：系统记录、存储、录入或核验时间 | source_event（按源事件时间判断） | 用于判断信息何时可见；不得把记录时间晚于决策时点的事件纳入快照。 |
| mimic_iv_note.radiology[].text | string | TEXT | NOT NULL | 报告全文 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 按决策时点截取；患者原文不得发送到未经批准的外部API。 |
| mimic_iv_note.radiology_detail[].note_id | string | VARCHAR(25) | NOT NULL | 报告唯一标识 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_note.radiology_detail[].subject_id | string | INTEGER | NOT NULL | 患者唯一标识 | 患者连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| mimic_iv_note.radiology_detail[].field_name | string | VARCHAR(255) | NOT NULL | 属性名称 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_note.radiology_detail[].field_value | string | TEXT | NOT NULL | 属性值 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| mimic_iv_note.radiology_detail[].field_ordinal | string | INTEGER | NOT NULL | 属性序号 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |

## 外置7张公共字典字段

| JSON路径 | JSON存储类型 | 源类型 | 源约束 | 中文说明 | 键角色 | 时间语义 | 信息阶段 | Benchmark使用限制 |
|---|---|---|---|---|---|---|---|---|
| references.d_labitems[].itemid | string | INTEGER | NOT NULL, 主键 | 检验项目唯一标识 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| references.d_labitems[].label | string \| null | VARCHAR(50) | 可空 | 检验项目名称 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| references.d_labitems[].fluid | string \| null | VARCHAR(50) | 可空 | 标本类型 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| references.d_labitems[].category | string \| null | VARCHAR(50) | 可空 | 检验类别 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| references.d_icd_diagnoses[].icd_code | string | CHAR(7) | NOT NULL | ICD诊断编码 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| references.d_icd_diagnoses[].icd_version | string | INTEGER | NOT NULL | ICD版本号 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| references.d_icd_diagnoses[].long_title | string \| null | VARCHAR(255) | 可空 | 诊断的完整描述 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| references.d_icd_procedures[].icd_code | string | CHAR(7) | NOT NULL | ICD操作编码 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| references.d_icd_procedures[].icd_version | string | INTEGER | NOT NULL | ICD版本号 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| references.d_icd_procedures[].long_title | string \| null | VARCHAR(255) | 可空 | 操作的完整描述 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| references.d_hcpcs[].code | string | CHAR(5) | NOT NULL, 主键 | HCPCS/CPT编码 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| references.d_hcpcs[].category | string \| null | SMALLINT | 可空 | 编码分类 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| references.d_hcpcs[].long_description | string \| null | TEXT | 可空 | 完整描述 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| references.d_hcpcs[].short_description | string \| null | VARCHAR(180) | 可空 | 简短描述 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| references.provider[].provider_id | string | VARCHAR(10) | NOT NULL, 主键 | 医疗提供者唯一标识 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| references.d_items[].itemid | string | INTEGER | NOT NULL, 主键 | 项目唯一标识 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |
| references.d_items[].label | string \| null | VARCHAR(200) | 可空 | 项目名称 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| references.d_items[].abbreviation | string \| null | VARCHAR(100) | 可空 | 项目缩写 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| references.d_items[].linksto | string \| null | VARCHAR(50) | 可空 | 链接到的表名 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| references.d_items[].category | string \| null | VARCHAR(100) | 可空 | 项目类别 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| references.d_items[].unitname | string \| null | VARCHAR(100) | 可空 | 计量单位 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| references.d_items[].param_type | string \| null | VARCHAR(30) | 可空 | 参数类型 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| references.d_items[].lownormalvalue | string \| null | FLOAT | 可空 | 正常范围下限 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| references.d_items[].highnormalvalue | string \| null | FLOAT | 可空 | 正常范围上限 | 非键字段 | 非时间字段 | source_event（按源事件时间判断） | 随所属源行执行决策时点过滤和未来信息泄漏测试。 |
| references.caregiver[].caregiver_id | string | INTEGER | NOT NULL, 主键 | 护理人员唯一标识 | 源记录标识或连接键 | 非时间字段 | identifier（连接/审计） | 仅用于连接、去重和审计，不进入模型题干。 |

## 明确不进入JSONL的表

- `mimic_iv_icu.chartevents`：高频床旁监护、护理观察与设备参数，按当前数据边界整表排除。
- `mimic_iv_hosp.omr`：没有原生`hadm_id`，禁止依赖时间窗口推断归属住院。
