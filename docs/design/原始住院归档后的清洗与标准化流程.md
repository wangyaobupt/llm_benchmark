# 原始住院归档后的清洗与标准化流程

## 1. 分层原则

```text
原始 MIMIC CSV
  → 单次住院原始归档 raw archive（只保留原始字段）
  → 清洗层 cleaned events（可用性、质量与文本结构）
  → 标准化层 normalized events（术语、单位与代码映射）
  → 评测层 dynamic view（题型字段白名单＋时间截断）
```

各层产物独立保存，禁止覆盖上一层。所有清洗和标准化记录必须保留 `subject_id`、`hadm_id`、`source_table` 和稳定 `source_row_id`，能够追溯到原始 JSONL 中的一行源记录。

本流程不复用旧 17 列 CSV 的字段设计或完成状态。旧代码中可复用的只有 checkpoint、原子写入、失败即停止等工程机制。

### 1.1 固定产物接口

| 产物 | 建议格式 | 一行代表什么 | 固定核心字段 |
|---|---|---|---|
| `raw_manifest.json` | JSON | 一次 raw 抽取运行 | schema/source 版本、输入指纹、selection hash、分片状态、行数、字节数、SHA-256 |
| `cleaned_events.parquet` | Parquet | 一条可追溯的原始 source row；文书章节和实体以嵌套列表保存 | `subject_id`, `hadm_id`, `source_module`, `source_table`, `source_row_id`, `raw_row_ref`, `event_kind`, `event_time`, `available_time`, `recorded_time`, `evidence_phase`, `parsed_value`, `quality_flags`, `exact_duplicate_group`, `cleaning_rule_version` |
| `cleaning_rejected.parquet` | Parquet | 一条未通过清洗门禁的源事件 | 上述定位字段、`rejection_code`, `rejection_detail`, `rule_version` |
| `term_inventory.parquet` | Parquet | 一个待映射原始术语/单位/代码 | `domain`, `source_system`, `raw_code`, `raw_term`, `raw_unit`, `context_key`, `frequency`, `input_sha256` |
| `normalization_mappings.parquet` | Parquet | 一条冻结映射规则 | `mapping_id`, `domain`, `source_key`, `normalized_code`, `normalized_term`, `normalized_unit`, `method`, `mapping_version`, `review_status` |
| `normalized_events.parquet` | Parquet | 一条已应用冻结映射的 cleaned event | cleaned 定位字段、`normalized_code`, `normalized_term`, `normalized_value`, `normalized_unit`, `mapping_id`, `mapping_version`, `normalization_status` |
| `normalization_review_queue.parquet` | Parquet | 一条未解决或冲突映射 | 原始术语上下文、候选映射、冲突原因、频次、`review_status` |

`raw_row_ref` 使用 `part file + JSONL line number + source_table + source_array_index`，避免在 sidecar 中再次复制整行原始 payload。`source_row_id` 使用原始主键或完整复合键；没有可保证唯一的原始键时，使用 `canonical raw row hash + duplicate occurrence ordinal`。`parsed_value` 只保存类型化解析结果；原始字符串永远从 raw archive 回查。

## 2. 清洗阶段

清洗解决“这条原始数据能否可靠使用、如何结构化读取”，不解决“它对应哪个标准医学概念”。

### C0 输入冻结与治理

- 校验 `mimic_admission_raw` schema version、源版本、分片 SHA-256 和 manifest。
- 患者原文保持本地；未经单独合规确认，不发送 MIMIC 文书到普通在线 LLM/API。
- 生成外部 patient split manifest；同一 `subject_id` 只能属于 development 或 final_test 之一，不回写原始 JSONL。

### C1 原始行展开

- 将每次住院中各表数组展开为统一索引：`subject_id`, `hadm_id`, `source_table`, `source_row_id`, `raw_row`。
- `source_row_id` 优先使用原始主键或完整复合键；仍不唯一时使用行内容哈希加重复出现序号。
- 不删除原始重复行，只额外标记 `exact_duplicate_group`。

### C2 类型与时间解释

- 在 cleaned sidecar 中解析数字、日期和时间；原始字符串继续保留在 raw archive。
- 为每张表显式映射 `event_time`、`available_time`、`recorded_time`，不得用其他时间静默填补缺失值。
- ICD、DRG、出院文书等后验资料在 cleaned sidecar 标记 `evidence_phase=post_hoc`。
- 时间无法解释时标记 `time_status=unknown`，不伪造时间。

### C3 质量清洗

- 标记 subject/hadm/stay/parent ID 冲突、非法数值、倒置时间、未知单位和关键字段缺失。
- 去标识占位符 `___`、`[**...**]` 只在派生文本字段中标记或移除；原始 `text` 不修改。
- 不通过降低门槛、填默认值或吞异常让记录“通过”。

### C4 文书结构化

- ED 主诉只来自 `ed.triage.chiefcomplaint`。
- 出院小结可解析为 HPI、PMH、hospital course、discharge instructions 等章节，但全部保留 `post_hoc` 属性。
- 放射 detail 按 `note_id + field_ordinal` 组织，报告正文不改写。
- 文本实体抽取保存 source span、否定、不确定性和章节来源；不在本阶段合并同义词。

### C5 清洗验收

- 输入/输出住院数和 source row 数可对账。
- 每条 cleaned event 能回溯唯一 raw row。
- 原始 JSONL 与源 CSV 不被修改。
- 质量失败进入明确 rejected report，不进入正式 cleaned 数据。

清洗门禁必须同时满足：住院数对账一致、逐表 `input_rows = cleaned_rows + rejected_rows`、孤立 parent/child 关联数为 0、未知字段数为 0、所有输出均可反向定位 raw row。任一项失败即停止，不进入标准化。

## 3. 标准化阶段

标准化解决“不同原始表达是否代表同一医学概念或单位”，不改变原始事实。

### S0 冻结映射输入

- 仅消费通过清洗门禁的事件。
- 建立去重 source term inventory 和出现频次。
- 映射表、规则、字典版本和输入 SHA-256 写入 manifest。

### S1 确定性代码映射

- `labevents.itemid` 连接独立 `d_labitems`；保留 itemid、label、fluid、category。
- ICD diagnosis/procedure 连接对应字典；不静默跨 ICD-9/10 转换。
- HCPCS、NDC、GSN、ETC、ICU itemid 使用各自原始字典或经过版本锁定的外部术语表。
- 原始 code 和原始名称始终保留在标准化对象中。

### S2 药物标准化

- 分别处理处方、药房、eMAR 和 ED 用药核对，不先合并事件。
- 映射通用名、成分、剂型、规格、剂量、途径和频次。
- `dose_given` 与 `product_amount_given` 分开保存，不能把“1 mg”和“1 tablet”合并为同一数值。
- 映射不确定时保留原始表达并标记 unresolved。

### S3 检验与单位标准化

- 检验名称映射键至少包含 `itemid + fluid + category`。
- 数值、文本结果、参考范围、flag 和 comments 分开保存。
- 只有确定性等价单位可直接统一；需要比例换算时保存换算规则和原值，禁止静默改值。

### S4 临床文本实体标准化

- 对清洗层已经定位的实体做同义词、缩写和标准概念映射。
- 否定、历史、假设和当前状态不能在标准化时丢失。
- LLM 只能生成映射候选，必须经过独立规则/模型复核；正式 transform 不允许运行时创建新映射。

### S5 标准化验收

- 每个 normalized event 同时保存 raw reference、cleaned value、normalized value、method、mapping version 和 confidence/review status。
- 映射表缺项、版本不符或 hash 不一致时终止。
- 未解决项保留并进入 review queue，不用上位概念或猜测值兜底。

标准化门禁必须同时满足：映射表版本/hash 与运行 manifest 一致、每个非空待映射项均明确落入 mapping 或 review queue、所有数值换算可逆回算、`normalization_status` 仅取 `mapped/exact`, `mapped/converted`, `unresolved`, `not_applicable`、每条非 `not_applicable` 事件存在映射或 review queue 记录。`unresolved` 不算错误，但不得进入要求标准答案唯一的题目。

## 4. 动态读取规则

动态读取属于评测层，不写入大型 raw JSONL。每一道候选题保存一个小型 view manifest：

```json
{
  "hadm_id": "22595853",
  "question_type": "investigation_selection",
  "cutoff_time": "2151-05-25 08:20:00",
  "visible_sources": ["ed.triage", "ed.vitalsign", "hosp.patients"],
  "time_rule": "available_time <= cutoff_time",
  "forbidden_evidence_phases": ["post_hoc"],
  "hidden_outcome_source_row_id": "..."
}
```

renderer 依次执行：source/字段白名单、时间截断、后验排除、答案隐藏和泄漏测试。模型不得直接读取完整 raw、cleaned 或 normalized 住院记录。

## 5. 推荐执行顺序

1. 生成并验证 10,000 例 raw archive。
2. 对每张源表做行数、空值、时间和体积 profiling。
3. 冻结 cleaned event schema 与 source-specific 时间映射。
4. 先在 development 患者的 100 例上运行清洗。
5. 扩至 1,000 例并人工审核文本结构和质量标记。
6. 冻结术语映射表，再运行标准化。
7. 为五类题型分别生成 dynamic view，并执行未来信息泄漏测试。
8. 通过门禁后才生成每类100道候选题。

### 5.1 每一步的停止条件与交付物

| 顺序 | 执行任务 | 交付物 | 进入下一步的条件 |
|---:|---|---|---|
| 1 | 10,000 例 raw 抽取与续跑演练 | raw JSONL、32 表 staging、7 字典、manifest | schema 验证通过，分片 hash 可复现，源表行数可对账 |
| 2 | 逐表 profiling | 表级行数/空值/时间/单位/体积报告 | 32 张表全部有报告，父子孤立率和异常时间可解释 |
| 3 | 冻结 cleaning schema 与逐表规则 | cleaned schema、时间语义矩阵、质量规则表 | 规则覆盖全部 32 表，不存在默认时间或默认值 |
| 4 | development 100 例清洗 | cleaned/rejected sidecar、人工审核表 | 人工审核确认 source span、时间语义和拒绝原因正确 |
| 5 | development 1,000 例清洗 | 规模化质量报告 | 全部清洗门禁通过，规则不再因单例临时改动 |
| 6 | 构建并冻结 mappings | inventory、mappings、review queue | 映射经过人工审核并锁定版本/hash |
| 7 | 1,000 例标准化 | normalized sidecar、覆盖率与可逆性报告 | 全部标准化门禁通过 |
| 8 | 五个维度逐个构建 dynamic view | 每题 view manifest、泄漏测试报告 | 当前维度泄漏测试通过后，才开始该维度候选题生成 |

五个维度按“一个维度完成字段白名单、时间规则、100 道候选题与抽样人工审核，再进入下一个维度”推进；单病种病例只用于前期熟悉和调试，不在通用 schema 中增加疾病专属字段。
