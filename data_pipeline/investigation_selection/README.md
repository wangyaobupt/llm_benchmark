# investigation_selection

检查选择重建。本阶段只做数据层：把「某时点开了什么检查」做成可查询表。

不重跑 `event_pipeline`。输入是已有的规范化 / 聚合事件 extract。

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.investigation_selection `
  docs\reports\hadm-28234402-event-aggregated.json `
  --output-dir data\derived\investigation_timepoint\hadm-28234402
```

指定时点：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.investigation_selection `
  docs\reports\hadm-28234402-event-aggregated.json `
  --output-dir data\derived\investigation_timepoint\hadm-28234402 `
  --index-time 2142-04-28T18:02:32
```

| 模块 | 作用 |
|---|---|
| `facts.py` | 检查检验领域表：一项检查一行（`exam_name` / 化验名），统一 `domain` / `fact_type` / 时钟 / 分组。不把 POE 和结果对齐成一行 |
| `actions.py` | 在 facts 上打冻结协议的 eligibility / candidate_id |
| `source_grouping.py` | Lab 用真实 `specimen_id`；影像用 `note_id+exam_name`；POE 用 `chain_root_poe_id` |
| `episodes.py` | 按 chain 折叠；后来 Inactive 不删 create |
| `query.py` | `list_investigations_at` / `list_visible_facts` |
| `eligibility.py` | 读 `config/investigation-selection/investigation-order-eligibility.yaml` |

1,000 例方法学 corpus（不跑 mining）：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.investigation_selection.corpus `
  --output-dir data\derived\investigation_timepoint\corpus_1000
```

第一部分（主诉 → 检查检验）读 `investigation_facts` 里 `fact_type in {resulted, reported}` 的行，**不读 POE 开单时刻**。规则在 `config/investigation-selection/first-wave.yaml`：index = 最早结果层 `occurrence_time`（化验/影像 `charttime`）；候选名是化验项目和 `exam_name`（带部位），不是 POE 的 `CT Scan` / `Lab`。该时刻之后的信息不可见。ED 主诉在 `ed.triage` 没有原生时间戳，只绑定到就诊起点（`presentation_origin_v1`）。冻结的 `protocol.yaml` 开单合同未改。POE 开单仍作为 `fact_type=order` 留在 facts 里，供正式 track 使用，不与结果行 join。

只在 `decision_documents.parquet` 里 `split_role=development` 上挖规则。不要用 phenotype 特征表。

科学合同见 `config/investigation-selection/protocol.yaml` 的 `decision_contract`（`conditional_order_choice`；化验目标时刻=`storetime`；panel 主分析计一次）。资格目录与 catalog-lock 已按 1,000 例 subtype 审计冻结。

`encounter_clock.py` 仍负责 ED / 住院时钟，不 coalesce。

本目录产物**不是**一次住院的全文。开单细不下去是 MIMIC POE 的限制（Lab 没有项目名）；具体化验在结果事件里。整次住院应读全事件 extract，再按需连到本目录。读法见 [`docs/design/一次住院信息分层与时点检查读法.md`](../../docs/design/一次住院信息分层与时点检查读法.md)。从原始表到挖掘表的逐步对照（`hadm=28234402`）见 [`docs/design/一次住院从原始表到挖掘表的处理流程.md`](../../docs/design/一次住院从原始表到挖掘表的处理流程.md)。
