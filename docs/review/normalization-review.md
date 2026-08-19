# 跨批归一化人工审阅操作指南

## 1. 文档目的

本指南用于完成两批 MIMIC 真实数据归一化结果的 100 条人工试审，并优先判断哪些标准化结果可以支持首个“检查检验选择”评测任务。

人工审阅解决两个不同问题：

1. **跨批归一化质量**：同一冻结键在不同批次中是否保持相同、正确且可复现的语义；
2. **首任务候选目录质量**：检查、检验、影像和监测项目是否具有适合作为题目答案或条件的粒度。

完成 100 条全局试审，不自动等于检查候选目录已经可冻结。候选目录还必须独立通过目标事件、comparison class、时间语义和唯一答案门禁。

## 2. 审阅边界

### 2.1 人工审阅可以做什么

- 核对源代码、源名称、当前标准概念和单位；
- 对照两个批次的事件数量和证据样本；
- 通过 `raw_row_ref` 回查原始 JSONL 源行；
- 记录接受、保持未解决、确定性纠正、待外部证据或源缺陷决定；
- 识别影响检查候选目录、条件 X 或 comparison class 的问题。

### 2.2 人工审阅不能替代什么

- 不能用人工决定直接编辑 normalization Parquet；
- 不能用人工判断替代确定性映射规则；
- 不能把“概念映射正确”直接等同于“可以成为 MCQ 答案”；
- 不能由审核者临时决定 patient split、时间窗、统计阈值或 gold 构念；
- 不能把 MIMIC 实际行为解释为临床最佳决策；
- 不能把患者级内容发送到未经批准的外部模型或服务。

## 3. 审阅输入与输出

审阅包目录：

```text
data/derived/normalization_review_master/
```

主要输入：

| 文件 | 用途 |
|---|---|
| `review_summary.json` | 批次、计数、decision taxonomy 和验收状态 |
| `consolidated_review_decisions.parquet` | 16,860 个唯一 mapping key 及 100 条试审标记 |
| `cross_batch_evidence_samples.parquet` | 两批事件证据样本及 `raw_row_ref` |
| `adjudication_protocol.md` | 冻结键、试审构成、decision code 和完成门槛 |
| `review_app.py` | 本地只读浏览与追加式决定记录界面 |

两批原始证据：

```text
data/test_1000_0812/mimic-admission-clinical-readable-coronary-random-1000.jsonl
data/test_1000_0812_2/mimic-admission-clinical-readable-coronary-random-1000.jsonl
```

唯一人工写入文件：

```text
data/derived/normalization_review_master/normalization_review_annotations.jsonl
```

该文件是追加式 sidecar。保存新决定不会覆盖旧记录；同一 `review_id` 的最新记录用于当前统计，完整历史继续保留。

## 4. 审阅前检查

在项目根目录 `D:\Projects\llm_benchmark` 执行：

```powershell
.\.venv\Scripts\python.exe data\derived\normalization_review_master\review_app.py --check
```

正常结果应至少包含：

- `app_version = normalization-review-ui/1.1.0`；
- `review_run_id = master-7811a482da1871aea4903ce2`；
- `decisions = 16860`；
- `samples = 5205`；
- 两个 `source_batches` 均能定位到对应 JSONL；
- `annotations` 等于当前已保存的人工决定记录数。

如果任何输入文件缺失、批次源 JSONL 不可访问或审阅日志不是合法 JSONL，应停止审核并解决文件或日志问题。

## 5. 启动和停止界面

### 5.1 启动

```powershell
.\.venv\Scripts\python.exe data\derived\normalization_review_master\review_app.py
```

默认地址：

```text
http://127.0.0.1:8766/
```

服务只监听本机回环地址，不允许通过局域网访问。

如果不希望自动打开浏览器：

```powershell
.\.venv\Scripts\python.exe data\derived\normalization_review_master\review_app.py --no-browser
```

如果 8766 端口已被本项目的另一个审阅进程占用，应先确认并关闭旧进程；确需保留旧进程时才指定另一个本机端口：

```powershell
.\.venv\Scripts\python.exe data\derived\normalization_review_master\review_app.py --port 8767
```

### 5.2 停止

回到启动服务的终端，按：

```text
Ctrl+C
```

### 5.3 多批审阅限制

本审阅包已从 `review_summary.json` 自动加载两个批次。不要传入单个 `--source-jsonl`，因为单一路径会破坏跨批证据回查，程序也会拒绝这种配置。

## 6. 界面说明

顶部卡片显示：

- 归一化事件数；
- 唯一术语数；
- unresolved 事件数；
- 选中待审数；
- 已完成数；
- 剩余数。

左侧支持以下筛选：

- 搜索术语、代码、概念或 event ID；
- 优先级；
- 当前状态；
- 审阅范围；
- 试审类别；
- 审阅原因；
- 实体类型；
- 按优先级、影响事件数、术语或状态排序。

页面默认将审阅范围设为 `pilot`。开始审核时继续保持该范围，避免误审 16,860 条完整队列。

右侧详情包括：

- 原始术语和源概念代码；
- 当前概念、标准名称和映射规则；
- 术语及单位状态；
- 两批事件数；
- 事件证据样本；
- 原始源行回查按钮；
- decision、reviewer、纠正字段和comment。

## 7. 推荐审核顺序

不要机械地从第 1 条审到第 100 条。先审核与首个检查检验任务直接相关的 16 条，再完成其余全局质量试审。

### 7.1 第一组：目标候选与目标事件范围

按以下顺序搜索并审核：

1. `General Xray`
2. `Blood tests`
3. `Telemetry`
4. `Potassium`
5. `Sodium`
6. `Chloride`
7. `Creatinine`
8. `Urea Nitrogen`
9. `Bicarbonate`
10. `Anion Gap`
11. `Glucose`
12. `Hematocrit`

重点：

- `General Xray` 是明确的 `imaging_ordered` 事件，但必须确认是否过度合并不同解剖部位、投照方式或检查协议；
- `Blood tests` 是通用医嘱类别，不能未经拆分就作为某一具体检查答案；
- `Telemetry` 是否属于检查、监测或治疗管理，必须在任务本体中明确；
- 9 项实验室映射证明概念和单位存在，但实验室结果事件不自动等于具有可靠下单时点的目标动作。

### 7.2 第二组：条件 X 可见证据

继续审核：

1. `Chest pain`
2. `Blood pressure`
3. `Heart rate`
4. `Respiratory rate`

重点：

- 症状是否表达患者本人当前阳性事实；
- 生命体征概念和单位是否正确；
- 原始值、标准值和时间字段是否可回查；
- 该证据是否能在目标决策时点之前合法进入条件 X。

### 7.3 第三组：完成剩余 84 条

首批 16 条完成后，再按以下顺序完成全局质量试审：

1. 其余一般医嘱；
2. 有效代码映射中的非首任务项目；
3. 未解决单位；
4. 高频无代码药物；
5. 无效 NDC；
6. 类别型未解决药物医嘱。

该阶段解决的是跨批标准化整体质量，不代表首任务候选目录已经自动通过。

## 8. 单条记录审核流程

### 步骤 1：核对映射概览

检查：

- `source_label_example`；
- `source_concept_id`；
- `entity_type`；
- `concept_id`；
- `preferred_name`；
- `mapping_rule`；
- `normalization_status`；
- `source_unit`；
- `normalized_unit`；
- `unit_normalization_status`；
- `event_count`；
- 两批事件数量。

### 步骤 2：核对两个批次的证据

每条至少查看两批各一条证据样本：

- 两批是否表达同一临床概念；
- source table 和 event kind 是否一致或差异可解释；
- 是否因为名称相同而错误合并不同临床含义；
- 高事件数是否来自合理复用，而不是过度泛化。

### 步骤 3：回查原始源行

点击“回查原始行”，核对：

- 原始 code、label 和 unit；
- 原始状态和内容；
- source table；
- event、recorded和available时间字段；
- 是否存在更细粒度的原始字段；
- 事件代表医嘱、结果、执行、状态还是一般类别。

如果原始行无法回查，不能只依据标准化摘要形成最终决定。

### 步骤 4：判断标准化语义

回答：

1. 当前概念是否与源语义一致？
2. 当前单位是否正确？
3. 是否遗漏了可以确定性利用的源代码？
4. unresolved 是否确实无法通过确定性规则解决？
5. 两批中的同一冻结键是否语义一致？

### 步骤 5：判断首任务影响

对首批 16 条额外回答：

1. 它是答案候选、条件证据还是仅用于审计？
2. 它是否可以独立开立或选择？
3. 粒度是否足以进入 comparison class？
4. 是否混合不同解剖部位、标本、协议或临床目的？
5. 目标动作的下单时间、执行时间和结果时间能否区分？

首任务影响判断属于候选目录审核，不写入一个并不存在的临床最佳 gold。

### 步骤 6：选择决定并保存

填写稳定的 `reviewer` 标识、选择decision，并按要求填写comment或纠正字段。点击“保存决定”后，确认：

- 页面显示“已保存到追加式审阅日志”；
- 已完成数量增加；
- 剩余数量减少；
- 当前记录显示最新决定；
- 历史记录数增加。

## 9. Decision code

| Decision | 使用条件 | 是否终态 | 必填内容 |
|---|---|---:|---|
| `accepted_mapped` | 当前概念和单位映射均正确 | 是 | reviewer；建议写简短依据 |
| `accepted_unresolved` | 证据不足，保持 unresolved 才是正确决定 | 是 | reviewer；建议说明为什么不能确定性映射 |
| `deterministic_correction` | 存在明确、可复现的修正规则 | 是，但必须修规则并重跑 | reviewer、comment，以及概念ID+名称或标准单位 |
| `needs_external_evidence` | 需要官方字典、术语库或专家证据 | 否 | reviewer、comment、待查证据来源 |
| `source_defect` | 源代码、源名称、单位或源行本身有缺陷 | 是 | reviewer、comment和源缺陷证据 |

程序会强制执行：

- reviewer不能为空；
- correction、external evidence和source defect必须填写comment；
- `accepted_mapped`不能用于术语或单位仍未解决的记录；
- `accepted_unresolved`不能用于术语和单位均已成功映射的记录；
- 确定性纠正必须填写概念ID和名称，或者填写标准单位。

## 10. Comment写法

### 10.1 接受映射

```text
Source code lab:50971 matches Potassium; source and normalized units are both mEq/L; evidence is consistent across both batches.
```

### 10.2 接受未解决

```text
The source row contains only the generic category "Blood tests" and no specific test code; a deterministic mapping to one laboratory investigation is not supported.
```

### 10.3 确定性纠正

```text
For source_table=<table>, entity_type=<type>, source_concept_id=<code> and mapping_version=event-terminology/1.1.0, map to <concept_id>/<preferred_name>. The same rule applies to both batches and affects <N> events.
```

### 10.4 待外部证据

```text
The local source fields do not distinguish <A> from <B>. Verify against <official dictionary or clinical terminology source> before a terminal decision.
```

不要只写“看起来正确”“应该可以”“疑似错误”等不可审计说明。

## 11. 确定性纠正后的处理

发现 `deterministic_correction` 后：

1. 按相同错误机制检索所有受影响mapping key；
2. 明确触发条件和排除条件；
3. 修改正式映射或单位规则；
4. 只重跑受影响批次及对应审计；
5. 重新生成 normalization manifest；
6. 检查 `mapping_conflicts=0`；
7. 比较修正前后的mapping、事件数和候选目录；
8. 不直接修改任何最终Parquet。

## 12. 验收标准

### 12.1 首批16条

- 16条均查看两个批次的证据；
- 所有直接候选相关记录均有终态决定；
- `needs_external_evidence`均记录待查来源和负责人；
- 所有correction均写明规则和影响范围；
- 明确记录：
  - `General Xray`是否过粗；
  - `Blood tests`能否拆成具体检查；
  - `Telemetry`是否属于首任务候选；
  - 实验室结果能否提供合法的目标动作时间语义。

### 12.2 全100条

- `pending_human_decisions=0`；
- 100条均有reviewer和终态decision；
- correction、external evidence和source defect均有充分comment；
- 所有确定性修正均已通过规则重跑；
- `mapping_conflicts=0`；
- 新旧manifest和影响计数完整；
- `needs_external_evidence`不得计为完成。

### 12.3 检查候选目录

- 所有进入候选目录的mapping key已经审核或具有可信的确定性来源；
- 不存在高影响的未解决候选；
- 同义、包含和不同粒度候选已分开处理；
- comparison class内候选粒度一致；
- 每个候选可以独立成为答案；
- 候选目录可重复生成且哈希稳定；
- 映射正确不被误写成规范性临床最佳决定。

## 13. 停止条件

出现以下任一情况，应停止候选目录或下游问题生成，先解决根因：

- 高频系统性映射错误；
- `General Xray`等概念合并不同部位或协议；
- 实验室结果无法可靠关联到检查选择时点；
- POE只有`Blood tests`等通用类别，无法形成具体唯一答案；
- 同一候选混合医嘱、结果和执行事实；
- 两批对同一冻结键呈现不同语义；
- 多个comparison class粒度无法统一；
- 确定性修正导致候选目录大范围变化；
- 原始源行无法回查；
- 审阅日志损坏或包含不合法记录。

停止表示门禁生效，不应通过降低阈值、忽略冲突或手工改最终产物继续推进。

## 14. 常见问题

### 页面打不开

确认启动终端仍在运行，并访问：

```text
http://127.0.0.1:8766/
```

### 端口被占用

先确认是否已有同一审阅服务运行。不要同时启动两个进程写同一个annotation sidecar。仅在明确保留旧的只读进程时使用其他端口。

### 无法回查原始行

执行`--check`确认两个source batch路径。多批审核不要传入单个`--source-jsonl`。在原始证据恢复前，不形成终态决定。

### 保存被拒绝

根据页面错误检查：

- reviewer是否为空；
- decision是否与当前mapped/unresolved状态矛盾；
- 是否缺少comment；
- correction是否缺少概念或单位字段。

### 决定填错

重新打开同一记录并保存正确决定。程序追加新历史，不删除旧记录；最新决定用于当前统计。不要手工删除或改写历史JSONL。

## 15. 相关文件

- [人工试审协议](../../data/derived/normalization_review_master/adjudication_protocol.md)
- [审阅摘要](../../data/derived/normalization_review_master/review_summary.json)
- [本地审阅程序](../../data/derived/normalization_review_master/review_app.py)
- [检查检验选择协议](../methods/investigation-selection-protocol.md)
- [项目当前进度](../../README.md)

