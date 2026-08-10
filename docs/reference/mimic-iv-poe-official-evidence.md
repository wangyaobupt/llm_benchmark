# MIMIC-IV v3.x POE 官方语义与时间线解析边界

## 目的与证据范围

本文为 `hosp/poe` 与 `hosp/poe_detail` 的批量解析提供官方证据边界，重点服务于“把原始 POE 医嘱转成可读事件，并逐步还原临床决策时间线”。

仅使用以下第一方来源：

- MIMIC 官方在线文档；
- PhysioNet 的 MIMIC-IV v3.1 数据集页面与发布说明；
- MIT-LCP 官方 `mimic-code` 仓库中的建表和约束脚本。

文中“官方事实”均可由上述来源直接支持；“工程推断”是面向本项目的解析建议，不声称为 MIMIC 官方定义。

## 版本适用性

**官方事实：** PhysioNet 将 MIMIC-IV v3.1 标记为 2024 年 10 月发布的版本。v3.1 发布说明列出的、相对 v3.0 发生修改的表不包括 `poe` 或 `poe_detail`；v3.0 的相关变化是 `poe` 新增 `order_provider_id`。[PhysioNet: MIMIC-IV v3.1 与 Release Notes](https://physionet.org/content/mimiciv/3.1/)

**官方事实：** MIT-LCP 当前 PostgreSQL 建表脚本给出的 `poe` 和 `poe_detail` 字段，与当前 MIMIC 在线文档一致。[MIT-LCP create.sql：`poe_detail` 与 `poe`](https://github.com/MIT-LCP/mimic-code/blob/main/mimic-iv/buildmimic/postgres/create.sql#L256-L280)

**工程结论：** 本文可作为 v3.0/v3.1 的结构与核心字段语义依据；但 `poe_detail.field_name` 的频数和常见值不能直接视为 v3.1 的完整枚举，因为该页明确将统计表限定为“截至 v2.2”。

## 两张表分别表达什么

### `poe`

**官方事实：** Provider Order Entry（POE）是医院照护提供者录入医嘱的一般界面；官方使用的是“多数治疗和操作必须通过 POE 下达”，不是“全部临床行为都一定有 POE”。[MIMIC 官方：poe](https://mimic.mit.edu/docs/iv/modules/hosp/poe.html)

`poe` 每行是一条医嘱记录，当前官方 schema 为：

| 字段 | 官方类型/可空性 | 官方语义 |
|---|---|---|
| `poe_id` | `VARCHAR(25) NOT NULL` | 医嘱唯一标识；由 `subject_id` 与单调递增的 `poe_seq` 按 `subject_id-poe_seq` 形式组成。 |
| `poe_seq` | `INTEGER NOT NULL` | 单调递增整数，可按时间顺序排列患者的 POE 医嘱。 |
| `subject_id` | `INTEGER NOT NULL` | 患者标识。 |
| `hadm_id` | `INTEGER`，可空 | 住院标识；每次住院唯一。 |
| `ordertime` | `TIMESTAMP(0) NOT NULL` | 提供者下达医嘱的日期和时间。 |
| `order_type` | `VARCHAR(25) NOT NULL` | 医嘱主类型。 |
| `order_subtype` | `VARCHAR(50)`，可空 | 医嘱类型的进一步细分，应结合 `order_type` 解读。 |
| `transaction_type` | `VARCHAR(15)`，可空 | 提供者执行该医嘱记录时的动作代码。 |
| `discontinue_of_poe_id` | `VARCHAR(25)`，可空 | 当前医嘱若停止了既往医嘱，则指向被停止的既往医嘱。 |
| `discontinued_by_poe_id` | `VARCHAR(25)`，可空 | 当前医嘱若后来被另一条医嘱停止，则指向那条后续医嘱。 |
| `order_provider_id` | `VARCHAR(10)`，可空 | 下达医嘱者的匿名标识；标识无内在业务含义。 |
| `order_status` | `VARCHAR(15)`，可空 | 医嘱是否仍为 `Active`，或已被置为 `Inactive`。 |

字段语义来源：[MIMIC 官方：poe](https://mimic.mit.edu/docs/iv/modules/hosp/poe.html)；类型与可空性复核：[MIT-LCP create.sql](https://github.com/MIT-LCP/mimic-code/blob/main/mimic-iv/buildmimic/postgres/create.sql#L265-L280)。

官方列出的 `order_type` 值为：`ADT orders`、`Blood Bank`、`Cardiology`、`Consults`、`Critical Care`、`General Care`、`Hemodialysis`、`IV therapy`、`Lab`、`Medications`、`Neurology`、`Nutrition`、`OB`、`Radiology`、`Respiratory`、`TPN`。[MIMIC 官方：poe/order_type](https://mimic.mit.edu/docs/iv/modules/hosp/poe.html#order_type)

### `poe_detail`

**官方事实：** `poe_detail` 为 POE 医嘱提供进一步信息，采用实体—属性—值（EAV）模型：实体是 `poe_id`，属性是 `field_name`，值是 `field_value`。EAV 用于在属性异构时灵活描述实体。[MIMIC 官方：poe_detail](https://mimic.mit.edu/docs/iv/modules/hosp/poe_detail.html)

| 字段 | 官方类型/可空性 | 官方语义 |
|---|---|---|
| `poe_id` | `VARCHAR(25) NOT NULL` | 医嘱实体标识。 |
| `poe_seq` | `INTEGER NOT NULL` | 与 POE 相同的单调递增序号。 |
| `subject_id` | `INTEGER NOT NULL` | 患者标识。 |
| `field_name` | `VARCHAR(255) NOT NULL` | 某一医嘱方面/属性的名称。 |
| `field_value` | `TEXT`，可空 | 与 `poe_id + field_name` 对应的属性值。 |

字段语义来源：[MIMIC 官方：poe_detail](https://mimic.mit.edu/docs/iv/modules/hosp/poe_detail.html)；类型与可空性复核：[MIT-LCP create.sql](https://github.com/MIT-LCP/mimic-code/blob/main/mimic-iv/buildmimic/postgres/create.sql#L256-L264)。

**官方示例：** `field_name = Admit to` 时，`field_value` 表示收治单元类型，例如 Psychiatry、GYN。官方页面还展示 `Indication`、`Code status`、`Transfer to`、`Consult Status`、`Level of Urgency`、`Tubes & Drains type` 等属性，但明确说明该列表及频数是“截至 MIMIC-IV v2.2”。[MIMIC 官方：poe_detail/field_name](https://mimic.mit.edu/docs/iv/modules/hosp/poe_detail.html#field_name)

## 表关系与键

**官方事实：** 在线文档声明 `poe_detail` 通过 `poe_id` 链接到 `poe`。[MIMIC 官方：poe_detail Links to](https://mimic.mit.edu/docs/iv/modules/hosp/poe_detail.html#links-to)

**官方 schema 事实：** MIT-LCP 约束脚本定义：

- `poe` 主键为 `poe_id`；
- `poe_detail` 主键为 `(poe_id, field_name)`；
- `poe_detail.poe_id` 外键指向 `poe.poe_id`；
- `poe` 与 `poe_detail` 的 `subject_id` 分别外键指向 `patients.subject_id`；
- `poe.hadm_id` 外键指向 `admissions.hadm_id`。

来源：[MIT-LCP constraint.sql：主键](https://github.com/MIT-LCP/mimic-code/blob/main/mimic-iv/buildmimic/postgres/constraint.sql#L95-L106)；[MIT-LCP constraint.sql：POE 外键](https://github.com/MIT-LCP/mimic-code/blob/main/mimic-iv/buildmimic/postgres/constraint.sql#L296-L320)。

**工程结论：** 批处理时应以 `poe_id` 为正式连接键，并校验重复携带的 `poe_seq`、`subject_id` 是否一致；不能仅凭 `poe_seq` 跨患者连接。每个 `poe_id` 下可把多行 `field_name/field_value` 聚合为属性映射。

### 处方与药房补充信息的连接

**官方事实：** `prescriptions.poe_id/poe_seq` 可将处方连接到 `poe`；`prescriptions` 与 `pharmacy` 的链接键是 `pharmacy_id`。[MIMIC 官方：prescriptions](https://mimic.mit.edu/docs/iv/modules/hosp/prescriptions.html)

**官方事实：** `pharmacy.pharmacy_id` 是药房记录的唯一标识，`pharmacy.poe_id` 可空并用于连接 POE。药房表提供频次、途径、疗程和计划起止时间等处方补充信息，但不等同于实际床旁给药。[MIMIC 官方：pharmacy](https://mimic.mit.edu/docs/iv/modules/hosp/pharmacy.html)

**工程结论：** 处方必须严格按 `pharmacy_id` 获取药房补充字段；`pharmacy.poe_id` 用于直接归属和一致性检查，不能在 `pharmacy_id` 不匹配时充当替代连接键。即使某个 POE 下只有一条药房记录，也不能据此猜测它属于另一 `pharmacy_id` 的处方。

## 事务、状态与停止关系

### `transaction_type`

**官方事实：** 官方仅将其定义为“提供者执行该医嘱时所做的动作”，并列出六类代码：`Change`、`Co`、`D/C`、`H`、`New`、`T`。[MIMIC 官方：poe/transaction_type](https://mimic.mit.edu/docs/iv/modules/hosp/poe.html#transaction_type)

**重要边界：** 官方当前页面没有进一步展开 `Co`、`H`、`T` 的业务含义，也没有给出状态机或合法跳转规则。因此：

- 不应把 `Co`、`H`、`T` 擅自扩写成某个临床动作；
- 即使 `New`、`Change`、`D/C` 的字面含义较直观，代码也应同时保留原值，且不要只凭该字段推断完整医嘱生命周期；
- 未见官方依据支持把 `Renew` 当作当前 v3.x `transaction_type` 枚举值。

后两点为工程约束，目的是避免把未经官方定义的代码映射写成事实。

### `order_status`

**官方事实：** `order_status` 表示医嘱仍为 `Active`，还是已经 `Inactive`。[MIMIC 官方：poe/order_status](https://mimic.mit.edu/docs/iv/modules/hosp/poe.html#order_status)

**工程推断：** 该字段描述行上的状态，不提供“何时转为该状态”的独立时间戳。它适合用于事件结果/状态校验，不应单独用来生成一个具有推断时间的“停嘱事件”。

### `discontinue_of_poe_id` 与 `discontinued_by_poe_id`

**官方事实：** 若当前医嘱停止了既往医嘱，`discontinue_of_poe_id` 指向被停止的既往医嘱；反向地，若当前医嘱后来被另一条独立医嘱停止，`discontinued_by_poe_id` 指向该后续医嘱。[MIMIC 官方：poe/停止关系](https://mimic.mit.edu/docs/iv/modules/hosp/poe.html#discontinue_of_poe_id-discontinued_by_poe_id)

**官方 schema 事实：** 当前约束脚本没有为这两个字段声明自引用外键，只有上述文档给出的逻辑链接语义。[MIT-LCP constraint.sql：`poe` 约束](https://github.com/MIT-LCP/mimic-code/blob/main/mimic-iv/buildmimic/postgres/constraint.sql#L309-L320)

**工程结论：** 还原停止链时，显式链接是最高置信证据，但必须做完整性检查：目标是否存在、是否同一患者、方向是否互相一致、时间是否前后合理。链接缺失不能自动补成确定事实，冲突也不能静默修复。

## 时间排序：`ordertime` 与 `poe_seq`

**官方事实：** `ordertime` 是提供者下达医嘱的日期时间；`poe_seq` 是单调递增、可按时间顺序排列 POE 医嘱的整数。[MIMIC 官方：poe](https://mimic.mit.edu/docs/iv/modules/hosp/poe.html#ordertime)

**官方事实：** MIMIC 的日期均为保护隐私而平移；同一患者内部日期保持一致，但被随机分布到未来。因此患者内相对时序仍可使用，真实日历年份不能直接解释。[MIMIC 官方：Core concepts / Date shifting](https://mimic.mit.edu/docs/iv/about/concepts.html#date-shifting)

**工程结论：** 时间线建议按患者/住院分组后使用 `(ordertime, poe_seq, poe_id)` 稳定排序。`ordertime` 是临床可解释时间，`poe_seq` 用于确定性解并列与一致性检查；不要把 `poe_seq` 的数值差解释成真实经过时长。

## `field_name/field_value` 的可解释边界

**官方事实：** `field_name/field_value` 是异构 EAV 属性，并非一张固定列式临床字典。[MIMIC 官方：poe_detail](https://mimic.mit.edu/docs/iv/modules/hosp/poe_detail.html)

由此产生的工程要求：

1. 原样保留 `field_name`、`field_value`，再额外生成规范化键和可读文本；不能用规范化结果覆盖源值。
2. 只对有明确证据或经样本验证的属性做语义映射；未知属性进入 `unmapped_fields` 统计，而不是丢弃。
3. `field_value` 允许为空；空值表示该属性行没有可用值，不能自动解释为否定、正常或未执行。
4. 官方 v2.2 的属性示例不是 v3.1 的封闭枚举。批量代码应接受新 `field_name`，而不是用固定白名单拒绝。
5. `poe_detail` 没有自己的事件时间；将其挂到 `poe.ordertime` 是基于连接关系的工程归属，不代表官方声明该属性在那个时刻被单独记录或可见。

其中第 3 点的“允许为空”由官方 schema 支持，其余是从 EAV 结构和版本边界推导出的工程约束。

## 官方明确或结构上可见的数据限制

1. **不是完整临床行为日志。** 官方只说“多数”治疗和操作必须通过 POE，不能反推所有决策、执行、沟通和床旁行为都在 POE 中。[MIMIC 官方：poe](https://mimic.mit.edu/docs/iv/modules/hosp/poe.html)
2. **数据来自常规临床实践。** PhysioNet 明确提示数据会反映实践自身的特殊性，归档过程可能产生不合理值，应遵循分析最佳实践。[PhysioNet：MIMIC-IV v3.1 Usage Notes](https://physionet.org/content/mimiciv/3.1/#usage-notes)
3. **准备过程移除了审计轨迹。** v3.1 方法说明指出数据准备包含表反规范化、移除 audit trails、重组为更少的表。因此 POE 不应被宣称为原始 EHR 的完整逐次审计历史。[PhysioNet：MIMIC-IV v3.1 Methods](https://physionet.org/content/mimiciv/3.1/#methods)
4. **住院关联可缺失。** 官方 schema 中 `poe.hadm_id` 可空；批处理不能假设每条 POE 均可归入某次住院。[MIT-LCP create.sql](https://github.com/MIT-LCP/mimic-code/blob/main/mimic-iv/buildmimic/postgres/create.sql#L265-L280)
5. **明细是异构且非封闭的。** `poe_detail` 的 EAV 设计允许医嘱具有不同属性；官方展示的属性统计停留在 v2.2，不能当作 v3.1 完整字典。[MIMIC 官方：poe_detail](https://mimic.mit.edu/docs/iv/modules/hosp/poe_detail.html)
6. **时间是去标识化时间。** 同一患者内的先后与间隔可用于时间线，但绝对年份已平移。[MIMIC 官方：Date shifting](https://mimic.mit.edu/docs/iv/about/concepts.html#date-shifting)

## 对批量解析器的最低证据等级建议（工程推断）

| 证据等级 | 可输出内容 | 条件 |
|---|---|---|
| 高 | 下达时间、医嘱主/子类型、原始事务代码、状态、明细属性 | 直接来自当前 `poe`/`poe_detail` 行。 |
| 高 | “医嘱 B 停止医嘱 A” | 存在显式 `discontinue_of_poe_id` 或 `discontinued_by_poe_id`，且连接和一致性检查通过。 |
| 中 | `New/Change/D/C` 的可读动作标签 | 保留原始值，并明确这是基于字面和关系字段的工程映射。 |
| 低/待定 | `Co/H/T` 的业务动作、缺失链接的医嘱链、状态改变的精确时间 | 官方资料未给出足够定义；只能原样呈现或标记待映射。 |

最终时间线应把“医嘱记录”与“实际执行结果”分开。POE 证明提供者在系统中下达或操作了医嘱；除非再连接检验结果、影像报告、处方/药房、eMAR、操作记录等表，否则不能把医嘱本身表述为已经执行或已经产生临床结果。
