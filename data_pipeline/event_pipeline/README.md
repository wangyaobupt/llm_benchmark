# 临床事件流水线

本目录是所有 event 任务的唯一代码边界和命令入口。输入为可回溯到原始 admission JSONL 的临床可读 JSONL；输出为 cleaning、确定性归一化、独立验收和可重复性报告。

## 目录职责

```text
event_pipeline/
├── __main__.py               # 唯一命令入口
├── workflow.py               # 固定顺序、门禁、复跑和原子发布
├── event_contracts/          # 各阶段共享的 Arrow/JSON 合同与状态
├── event_cleaning/           # 来源登记、原生键、时间语义和事件化
├── event_normalization/      # 确定性概念及单位归一化
├── event_quality/            # 独立审计、回归基线和复现比较
└── event_viewer/             # 本地只读查看器
```

依赖方向固定为：

```text
event_contracts
      ↑
event_cleaning → event_normalization
      ↑                 ↑
      └──── event_quality
                 ↑
             workflow
```

`event_cleaning` 不依赖 normalization；质量审计不调用 transformer 或归一化规则来证明实现自身正确。

## 一条命令完成全部 event 任务

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.event_pipeline run `
  data\validation\NEW-BATCH-clinical-readable.jsonl `
  --raw-source-jsonl data\validation\NEW-BATCH-raw.jsonl `
  --output-dir data\derived\event_pipeline_NEW_BATCH
```

固定执行顺序：

1. 校验输入文件和输出边界；
2. cleaning/事件化；
3. cleaning 独立验收；
4. 只有 cleaning 通过才执行确定性归一化；
5. normalization 独立验收；
6. 使用另一批大小重新运行 cleaning 和 normalization；
7. 比较所有数据文件 SHA-256、run ID 和计数；
8. 所有门禁通过后原子发布正式目录。

任一步失败，命令返回非零状态且不会留下正式输出目录。默认正式 batch size 为 5000，复跑 batch size 为 777；可通过 `--batch-size` 和 `--replay-batch-size` 修改，但二者不能相同。

## 输出

```text
event_pipeline_NEW_BATCH/
├── cleaning/
│   ├── cleaned_events.parquet
│   ├── cleaning_rejected.parquet
│   ├── term_inventory.parquet
│   ├── encounter_manifest.parquet
│   ├── source_reconciliation.json
│   └── run_manifest.json
├── normalization/
│   ├── normalized_events.parquet
│   ├── normalization_mappings.parquet
│   ├── normalization_review_queue.parquet
│   └── normalization_manifest.json
├── quality/
│   ├── cleaned-events-acceptance-audit.json
│   ├── normalized-events-acceptance-audit.json
│   └── reproducibility-report.json
├── review/                         # 显式执行 review 后生成
│   ├── review_app.py
│   ├── normalization_review_summary.json
│   ├── normalization_review_samples.parquet
│   ├── normalization_review_decisions.parquet
│   ├── normalization_review_decisions.csv
│   └── normalization_review_checklist.md
└── workflow_manifest.json
```

`workflow_manifest.json` 只有在两层审计及复跑全部通过后才会出现。

## 阶段边界

### Cleaning

封闭式 `SOURCE_CATALOG` 登记输入全部 33 张表：21 张事实拥有者生成事件，6 张 support 表只提供原生键证据，6 张 context 表不重复生成事实。`source_reconciliation.json` 对每张表记录角色、raw/derived 来源及分类结果；support 行还必须通过原生键关联到其事实拥有者。任一目录行未分类、support 未关联、derived 计数漂移、未登记表、缺少必需表、身份冲突或不可解释的时间关系都会阻断 normalization。

临床 transformer 按 ED、检验、医嘱、药物、诊断操作、ICU 和 Note 拆分，唯一 registry 负责将合同中的 transformer 名称映射到实现。

### Normalization

只读取 `cleaned_events.parquet` 和 `term_inventory.parquet`。它使用有效源编码、冻结同义词和冻结单位表，不调用 LLM。无效 NDC、多值 GSN 和无法确定含义的单位进入 review queue。

### Quality

Cleaning audit 全量复算 33 张表的角色、raw/derived 计数、supporting lineage、encounter manifest、身份、时间和逐表对账；normalization audit 验证除 8 个归一化字段外所有事件事实不变。复现比较独立计算两次运行所有数据文件的 SHA-256。

## 只运行单个阶段

排查问题时可以仍从同一个总入口调用单个阶段：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.event_pipeline clean INPUT.jsonl `
  --output-dir OUTPUT\cleaning

.\.venv\Scripts\python.exe -m data_pipeline.event_pipeline normalize `
  OUTPUT\cleaning\cleaned_events.parquet `
  OUTPUT\cleaning\term_inventory.parquet `
  --output-dir OUTPUT\normalization
```

这两个子命令不代表完整验收；正式批次应使用 `run`。

## 查看结果

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.event_pipeline view `
  data\derived\event_pipeline_NEW_BATCH
```

查看器只监听 `127.0.0.1`，可浏览 cleaning 和 normalization Parquet，并通过 `raw_row_ref` 回查源 JSONL。只验证目录而不启动服务器：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.event_pipeline view `
  data\derived\event_pipeline_NEW_BATCH --check
```

## 回归基线

验证三批人工确认的 cleaning 基线：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.event_pipeline regression verify
.\.venv\Scripts\python.exe -m data_pipeline.event_pipeline regression verify --rerun
```

新批次不会自动写入人工回归 fixture。只有人工确认后才允许显式执行 `regression capture`。

## 生成归一化审阅包

完整 event workflow 通过后，显式生成只读输入、独立输出的审阅包：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.event_pipeline review `
  data\derived\event_pipeline_NEW_BATCH
```

该命令重新计算当前 cleaning/normalization Parquet 的 SHA-256，要求 workflow 和 normalization audit 均通过，再生成：全部待复核术语、每类高频映射、按 `source_table × event_kind × normalization_status` 确定性分层的事件样本。`normalization_review_decisions.csv` 供人工填写，源 Parquet 不被修改。自动门禁通过只表示可以开始人工审阅，不表示人工审阅已经完成。

启动审阅窗口有两种等价方式：

```powershell
# 从总入口启动
.\.venv\Scripts\python.exe -m data_pipeline.event_pipeline review-ui `
  data\derived\event_pipeline_NEW_BATCH

# 直接运行审阅包内的单文件
.\.venv\Scripts\python.exe `
  data\derived\event_pipeline_NEW_BATCH\review\review_app.py
```

窗口只监听 `127.0.0.1`。人工决定以追加式日志写入 `review/normalization_review_annotations.jsonl`，不会修改 Parquet、CSV、cleaning 或 normalization 产物。需要连接非自动发现位置的源 JSONL 时，使用 `--source-jsonl PATH`。

## 合并多批归一化审阅

至少两批审阅包生成后，可以按冻结键跨批去重，并建立固定 100 条试审：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.event_pipeline review-master `
  data\test_1000_0812\event_pipeline_output `
  data\test_1000_0812_2\event_pipeline_output `
  --output-dir data\derived\normalization_review_master
```

冻结键为 `entity_type + source_concept_id + normalized_source_label + source_unit + mapping_version`。概念、状态、单位或规则不一致会直接失败；同一术语的各批事件数和原始证据分别保留。试审按七类依次、互斥、按总事件影响降序选择，共 100 条。

启动主审阅窗口：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.event_pipeline review-ui `
  data\derived\normalization_review_master
```

主审阅决定只追加到 `normalization_review_annotations.jsonl`。`needs_external_evidence` 仍算待处理；任何确定性纠正应回到规则层修改并重跑，而不是直接编辑归一化 Parquet。
