# Patient-Journey Clinical Decision Benchmark

## 项目要做什么

本项目构建一个面向患者单次就诊全流程的临床决策评测集（patient-journey benchmark），评估模型能否在不同临床决策节点，仅依据“当时已经发生且已经可用”的信息作出合理决策。

当前以 MIMIC-IV v3.1、MIMIC-IV-ED 2.2 和 MIMIC-IV-Note 2.2 开发、验证并冻结方法学；后续在香港真实世界资料上进行本地适配和外部验证。MIMIC 中得到的字段映射、统计阈值、行为 gold 和医疗流程不会直接移植到香港数据。

最终产物是五类英文 A–D 单选临床决策题，用于评估 LLM 在一次诊疗流程中的五项能力：

1. 检查检验选择；
2. 临床诊断；
3. 治疗与处置；
4. 转诊与科室选择；
5. 离院指导与随访。

项目以真实世界数据中的结构化事实和时间关系为依据，先冻结可用证据、答案定义与数据划分，再生成题目和开展模型评测。行为一致性任务回答“真实临床中最可能发生什么”，规范性任务回答“依据临床证据最应该做什么”；两类 gold 不混用。所有前瞻性题目只允许使用在决策时点已经发生且已经可用的信息，后验资料和行政终点信息不能进入题干。

## 两条并行数据轨道

当前仓库里有两条**互不互为输入**的数据轨道。五类题型底座走第三版直抽，不再经过住院全表归档或事件管线。

| | **V3 五类题型 Visit 直抽（当前出题底座）** | 冠心病检查选择（v3.1 方法学） |
|---|---|---|
| 输入 | `data/RawData/` 下 MIMIC-IV / ED / Note 的 **CSV.GZ 原表** | 同一套 CSV.GZ，但先做成住院归档再事件化 |
| 抽样 | 漏斗（成年、主诊断、有效出院小结）后，开发池内确定性随机 10,000 个 `(subject_id, hadm_id)` | 现有冠心病方法学队列 |
| 代码 | `data_pipeline/mcq_visit_{extract,standardize,timeline,mining}` | `mimic_raw_archive` → `event_pipeline` → `investigation_selection` |
| 交付 | 一行一次住院的 `visits.json` / `.csv`，再标准化、时间线、分家族规则 | 事件 Parquet、1,000 例 first-wave corpus |
| 不是 | 不是 gold；不替代 v3.1 W0–W10 | 不是五类题型的 visit 行文件 |

V3 直抽链路（只读 CSV.GZ，不读事件 Parquet、不读冠心病归档）：

```text
data/RawData/*.csv.gz
        │  mcq_visit_extract（漏斗 + 随机 10k + 字段投影）
        ▼
visits.json / visits.csv          schema mcq_visit_extract/3.1.x
        │  时间点补齐（另目录，不覆盖抽取）
        │  mcq_visit_standardize（术语 / 单位 / 主诉概念）
        ▼
visits_standardized.json
        │  mcq_visit_timeline（时钟 + 标准名）
        ▼
visit_events.parquet
        │  mcq_visit_mining（六个家族分别挖 X→y，隔离后验）
        ▼
conditional_rules.jsonl           exploratory_unreviewed；不出题；gold = 0
```

运行：抽取见 [`data_pipeline/mcq_visit_extract/README.md`](data_pipeline/mcq_visit_extract/README.md)；时间线与挖掘见 [`docs/guides/mcq-visit-timeline-mining.md`](docs/guides/mcq-visit-timeline-mining.md)。执行计划：[`docs/design/20260820_出题数据抽取第三版-1万例随机Visit直接抽取执行计划.md`](docs/design/20260820_出题数据抽取第三版-1万例随机Visit直接抽取执行计划.md)。

## 整体计划

项目按“数据层 → 评测层 → 外部验证层”推进。数据支路可以并行准备，但进入 patient journey、决策快照或题目构建前，各自必须通过明确的产物合同和验收门禁。

```text
MIMIC 原始表
    ↓
单次住院原始归档
    ↓
字典解码与 POE 解析
    ↓
临床事件清洗
    ↓
确定性标准化
    ↓
文书索引、章节与选择性事实抽取
    ↓
Patient journey 事件流
    ↓
决策时点快照与 gold 构建
    ↓
五类 MCQ 生成与临床审核
    ↓
LLM 评测、统计分析与报告
    ↓
香港 RWD 本地适配与外部验证
```

| 阶段 | 要解决的问题 | 核心产物与完成条件 |
|---|---|---|
| 单次住院原始归档 | 在不改写源记录的前提下，按住院聚合 HOSP、ED、ICU 和 Note | 原始 JSONL、字段与来源清单、manifest、完整性验证 |
| 字典解码与 POE 解析 | 将代码映射为可读含义，并保留医嘱生命周期和原生连接 | 解码 sidecar、POE timeline、可逆性与连接验证 |
| 临床事件清洗 | 将嵌套源行转换为一行一个可追溯临床事件 | cleaned events、拒绝记录、来源对账、时间与身份门禁 |
| 确定性标准化 | 统一代码、药物、检验、单位和术语，不由 LLM 猜测映射 | normalized events、映射表、审核队列、版本化 manifest |
| 文书事实支路 | 将同一次就诊中的多份文书拆为可追溯的文档、章节和事实证据 | note index、section/span 定位、实体与关系及人工审核报告 |
| Patient journey | 将结构化事件与文本事实组织为允许循环、并行和条件分支的就诊过程 | journey、state、decision node 和 evidence edge |
| 决策快照与 gold | 冻结每个决策时点可见证据，并区分行为 gold 与规范性 gold | 无未来信息泄漏的病例快照、标签与患者级数据划分 |
| MCQ 生成与审核 | 基于已冻结证据和答案生成题干、选项与解释 | 五类候选题、自动门禁、临床人工审核和发布集 |
| LLM 评测 | 比较不同模型的临床决策能力、稳定性和错误类型 | 评测协议、指标、置信区间、错误分析与最终报告 |
| 香港外部验证 | 在不同医疗系统中检验方法学的可迁移性，而不是复用 MIMIC 答案 | 本地 crosswalk、本地 gold、外部效度与 domain-shift 报告 |

原始归档始终保持不变；清洗、标准化、快照和题目均作为带版本与来源信息的派生产物保存。患者级数据按患者划分训练、开发和测试集合，避免同一患者跨集合泄漏。

上表是**冠心病检查选择**那条轨道的产物合同（raw archive → 事件 → decision document）。五类题型 Visit 底座不走这张表，见上文 V3 直抽。旧 V1 / V2 产物只作审计。检查选择闸门见 [v3.1 明确执行版](docs/plans/20260819_Benchmark-问题复核与实施计划-v3.1-明确执行版.md)。文件保存见 [`文件保存规范.md`](文件保存规范.md)。

## 目录结构

出题层有两条已关闭的历史线，一条未冻结的检查选择重建，以及一条 V3 Visit 直抽。V1 冻结在 `versions/v1-template-stem`（原根目录 `tasks/` 已并入并去重）。V2 在 `data_pipeline/archived/phenotype` 与 `versions/v2-llm-stem`，科学合同已失效，formal 入口拒绝。检查选择在 `data_pipeline/investigation_selection/` 与 `evaluation_pipeline/`。五类题型当前底座在 `data_pipeline/mcq_visit_*`（从 CSV.GZ 直抽，不经事件管线）。

```text
D:\Projects\llm_benchmark\
├── 文件保存规范.md / FILE_LAYOUT.md
├── BenchMark-进展梳理.md           # 唯一当前状态摘要
├── versions/                       # v1-template-stem（冻结基线）；v2-llm-stem（失效审计）
├── mcq_generation/                 # 五类题型设计文档（非正式实现）
├── data_pipeline/                  # 冠心病清洗：raw → clean → event → aggregation
│                                   # investigation_selection/ 检查选择重建
│                                   # mcq_visit_*  五类题型 V3：CSV.GZ 直抽 → 标准化 → 时间线 → 挖掘
│                                   # archived/phenotype/ 旧 visit 特征（失效）
│                                   # text_ner / text_ner_v2 文本支路（读事件聚合，不读 visit 行）
├── evaluation_pipeline/            # split / snapshot / journey / legacy 门禁
├── benchmark_common/               # V1 共享统计原语（冻结）
├── eda/                            # EDA 脚本
├── rwd_pipeline/                   # 香港 RWD 历史材料；本轮不纳入
├── config/                         # 协议与 lock（investigation-selection 已 frozen）
├── schemas/                        # JSON schema
├── docs/                           # design / plans / reports / guides / literature / review
├── tests/
└── scripts/                        # 一次性审计 / 冻结工具
```

所有产物当前均标记 `exploratory_unreviewed`，`gold = 0`。文档导航见 `docs/README.md`。当前状态摘要只看 [`BenchMark-进展梳理.md`](BenchMark-进展梳理.md)。V1 / V2 历史数字见 `docs/reports/execution-progress-p1-p5.md` 与 `docs/reports/v2-pipeline-methodology.md`。

## 当前进展

截至 2026-08-20：**五类题型底座第三版已从 MIMIC 原始 CSV.GZ 直抽 10,000 例 Visit**（不经住院全表归档、不经事件管线）。标准化 `v1.0.9` 主诉概念 mapped ≈96%。时间线合并与六个家族隔离挖掘的代码已落地，10k 跑数待执行。出院小结 NER 全量本轮不做。与此并行，冠心病事件底座仍可用，检查选择正式金标准尚未开始。`gold = 0`。

冠心病事件侧：39,036 次住院 / 27,336,811 条 `clinical_event/1.2.0`；无损聚合只验收了 1,000 例。V1 已冻为探索基线（221 题探针，非正式评测）。V2 因出院 ICD、未用 `available_time`、全住院目标窗、Lab 仅 category、split 泄漏而**整链失效**，不能送审或发布。`protocol.yaml` 已 `frozen`；1,000 例 first-wave corpus 为 `methodology_unreviewed`。

> **五类题型当前走 V3 直抽，不要再按旧 17 列 CSV 或事件 Parquet 去抽 visit 行。** 检查选择那条线不要把 11 条 FDR 或 134 道旧候选当成绩。状态摘要见 [`BenchMark-进展梳理.md`](BenchMark-进展梳理.md)。

| 阶段 | 状态 | 已完成的证据 | 尚未完成 |
|---|---|---|---|
| 单次住院原始归档 | 已完成 | 冠状动脉疾病谱共 108,833 次住院、46,062 名患者、50.392 GiB、218 个分片；32张住院内源表的 schema、原生父子键、患者分区和 `chartevents` 排除均通过验证 | 将该归档继续作为只读上游输入，不再改写 |
| 原始归档 EDA | 已完成 | 已完成全量流式分析，覆盖32张表、原始时间字段、疾病谱、模块覆盖和五类题型数据源准备度 | 后续数据层变化需继续以正式 metrics 和 manifest 对账 |
| 字典解码与 POE 解析 | 已完成 | 已实现可携带的字典解码与 POE timeline；保留源字段、原生键和可逆追溯关系 | 新输入版本出现时重新执行合同验证 |
| 临床事件清洗代码 | 33表清洗规则已实现 | 已明确33张输入表的封闭式来源范围与处理规则：21张事实源、6张支持源、6张上下文源；已实现稳定身份、药物原生键连接和统一时间下界 | 保持输入范围、处理规则、回归基线和来源对账一致 |
| 事件管线全量验收（100 → 1,000 → 39,036 全队列） | 全队列已通过完整验收并发布 workflow manifest（8/15） | 39,036 次住院（ED→HOSP→ICU→Note 全模块）全量运行：26,219,272 条事件源行清洗为 27,336,811 条事件、8,893 条拒绝；53,840 个唯一术语/单位组合、15,316 条人工复核队列；batch size 5000 与 777 复跑的 run ID 与 Parquet 哈希一致；manifest 中 cleaning/normalization/reproducible/can_start_text_ner 全部 true | 15,316 条归一化复核 pending，临床语义尚未人工确认；全量复核门禁未关闭 |
| 无损事件聚合 | 已通过验收（1,000 例批） | 把标准化事件重新连接回完整原文与源行血缘：1,241,918 条源记录、757,036 条处理后事件、43,551 条自由文本源记录；`processed_events`/`raw_source_records`/`traceable_events` 三份 Parquet 与质量报告全部 fail-closed 校验通过 | 全队列（39,036 例）聚合尚未运行；文本 NER 与 patient journey 回顾支路目前仍以 1,000 例聚合为唯一正文入口 |
| normalized_events 全量 EDA 与检查瓶颈诊断 | 已完成（8/17） | 27.3M 事件全量 EDA（领域覆盖、时间解析、归一化状态、单位分布）；检查维瓶颈定诊：POE 检验医嘱 99.99% 无项目内容、BMP/CBC 约 91% 普适基线锁死 rank-1/2、top-25 主诉唯一性过滤 0/25 通过、主诉术语映射率仅 9% | 作为失效旧链、重建 decision_document 的依据；数据层变化后需复扫对账 |
| 跨批归一化人工质量门禁 | 工具与试审队列就绪，人工试审 18/100（占位 reviewer） | 两批 1,000 例输出已汇总为1,422,220条 normalized events 和16,860个唯一 mapping key；映射冲突为0，已固定抽取100条人工试审并实现本机只读＋追加式审阅界面 | 已写入的18条决定使用占位 reviewer，不能视为完成；100条试审与首任务候选目录判定（`General Xray` 粒度、`Blood tests` 拆分、`Telemetry` 归属等）尚未形成；全队列新增 15,316 条复核队列待纳入同一流程 |
| 文本事实支路（text_ner v1 接口 + v2 干净重做） | v2 全量运行中；人工双标为空 | v1 接口覆盖 lab/micro comments、ED 主诉、放射报告与出院小结共 64,509 个文本单元；v2 干净重做（`data_pipeline/text_ner_v2`）修复 surface 偏移与无界递归分块两类阻断，37,790 份文档、41,902 分块，截至 8/17 编译 sidecar：804 份文档产出 154,639 实体提及、108 份文档 919 关系；DeepSeek/Qwen/Bailian 多模型试点已产出 sidecar | mentions 仅 804/37,790（2.1%），389 次失败待重试；人工 A、B 与裁决日志均为 0；输出全部为 `unreviewed_model_output`；出院小结（933份）按 `post_hoc` 排除出前瞻性快照，需独立 event-frame 支路 |
| v1 五维 MCQ 原型（`versions/v1-template-stem/`） | 探索闭环完成，已冻结为历史基线 | P1–P5 调优完成；validated rank-1 共 221 题（检查 84 / 诊断 24 / 治疗 T1 30 / T2 24 / T3 26 / 转诊 33）；DeepSeek flash 探针准确率 53.6% / 95.8% / 66.7% / 87.5% / 73.1% / 60.6%；`versions/v1-template-stem` 冻结快照 | 非正式评测；离院维无 MCQ gold；不得进入新发布链 |
| 旧 V2 phenotype + v2-llm-stem | 已失效，仅保留审计 | 1,584 formal accepted → 738 去重 → 165 收敛 → 134 候选 → 自动审题全过 → 人工 0 → gold 0。失效原因：出院 ICD、未用 `available_time`、全住院目标窗、Lab 仅 category、split sidecar 泄漏。legacy manifest 与 formal 入口拒绝已落地 | 不得送审、发布或作为新统计基线；不要往该包继续加 formal 语义 |
| 检查选择协议（W1） | `frozen`（本轮沿用现有冠心病队列） | `decision_contract`：`conditional_order_choice`；化验目标=`storetime`；panel 计一次；eligibility + `catalog-lock.json`；`protocol-lock.json` 已生成 | 方法学仍未走通；尚无 run-lock。BMP/CBC 成员表未写入，panel 级 lab gold 不可用。W1 exposure 审计 `previous_exposure=none` 为 0 |
| 检查选择重建骨架 | 合成测试 + 1,000 例 first-wave corpus | `data_pipeline/investigation_selection/`：clock、`chain_root_poe_id` 分组、后来 cancel 不删 create、episodes、facts/actions、snapshot adapter、corpus；`evaluation_pipeline/`：legacy / snapshot / journey / split | snapshot 仍可能放行 `event_time == index_time`；1,000 例 integration audit 未 freeze；mining 11 条 FDR 通过不是 gold |
| 患者级正式划分 | 合同与认证实现完成，尚无正式产物 | 已实现患者原子划分、HMAC 公开引用、受保护绑定、工程审计集隔离；旧 60/20/20 划分及接触过旧 holdout 的 subject 只能 audit-only | 新 validation/final 只能来自 `previous_exposure=none`（当前为 0）；尚未生成可发布 split / exposure registry |
| Patient journey | Encounter boundary 代码已实现，完整 journey 尚未实现 | 一个 `hadm_id` 一个住院边界、原生 ED handoff、ICU 子阶段、事件唯一归属 | 只有合成测试；无真实 boundary manifest |
| 决策快照与 gold | 认证快照工程链已实现；1,000 例 corpus 为 `methodology_unreviewed` | 通用时间 / phase / split / 字段白名单门禁，以及 boundary HMAC adapter；first-wave corpus 1,011 documents | 无 recency clock 对齐；`event_time == index` 当前会放行；corpus 不是 gold |
| V3 五类题型 Visit 直抽 | 10,000 例已抽出并标准化 | 只读 `data/RawData` CSV.GZ；`mcq_visit_extract` → `random10k_dev20`；时间点补齐 `random10k_dev20_times`；标准化 `random10k_dev20_v1.0.9`（主诉 mapped ≈96%） | 时间线 10k 与分家族挖掘待跑；不出题；非正式 gold |
| MCQ 生成 | 正式生成未开始 | 题型规范在 `mcq_generation/`；V3 直抽已接上抽取/标准化/时间线/挖掘代码；旧 V2 134 候选仅审计 | 挖掘验收前不出题；不把 V3 规则当 gold |
| LLM 评测 | 正式评测尚未开始 | v1 221 题 DeepSeek 探针为 `unreviewed_model_output` | 正式榜单等待新 gold 与 one-shot final test |

五类题型当前关键路径是 V3 时间线合并与六个家族隔离挖掘（代码已落地，10k 待跑），不是继续审旧 V2 题。检查选择那条线仍要完成 1,000 例 integration audit，不能把 11 条 FDR 或 134 道旧候选当 gold。

优先执行顺序是：

1. **V3 时间线 + 分家族挖掘**：先 `mcq_visit_timeline` 全量 10k，再按六个 `--family` 分别挖；运行指南 [`docs/guides/mcq-visit-timeline-mining.md`](docs/guides/mcq-visit-timeline-mining.md)。
2. **检查选择对齐时钟**：snapshot / query 使用 `event_time < index_time` 与冻结的 `evidence_window_basis`；不要另起平行包。
3. **1,000 例 integration audit**：eligibility、6 张审计表、可读 trace。未 freeze 不得进入 W6/W7，也不得把检查选择 mining 当成绩。
4. 跨批归一化 100 条试审（当前 18/100、reviewer 为占位）和文本 NER 人工双标可并行；出院小结保持 `post_hoc`。V3 出院小结 NER 全量本轮不做。
5. 检查选择 corpus freeze 后，才允许 coronary-only 的 retrieval / 规则方法检查（W6a / W7a）。多诊断扩展（W8）之后必须重跑 W2–W5 和 W6b / W7b。
6. 新 gold 只统计 programmatic + independent + clinical review 都通过的题目；行为 gold 与规范 gold 分开。V3 accepted 规则同样不是 gold。
7. 新 formal val/test 不得从旧 60/20/20 holdout 升级（`previous_exposure=none` 为 0）。
8. MIMIC 方法学冻结后，再在香港 RWD 重新完成数据合同、时间语义和两类 gold 的本地化。本轮不把香港数据纳入验收。

详细路线与文档：

- [当前状态摘要](BenchMark-进展梳理.md)
- [V3 直抽执行计划](docs/design/20260820_出题数据抽取第三版-1万例随机Visit直接抽取执行计划.md)
- [V3 时间线与挖掘运行指南](docs/guides/mcq-visit-timeline-mining.md)
- [v3.1 明确执行版](docs/plans/20260819_Benchmark-问题复核与实施计划-v3.1-明确执行版.md)
- [文件保存规范](文件保存规范.md)
- [文档索引（docs/README.md）](docs/README.md)
- [技术路线图](docs/design/技术路线图.md)
- [v1 执行进度 P1–P5（已归档基线）](docs/reports/execution-progress-p1-p5.md)
- [旧 V2 方法学（失效审计）](docs/reports/v2-pipeline-methodology.md)
- [legacy invalidation manifest](docs/legacy-invalidation-manifest.json)
