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

## 目录结构

五类临床决策 MCQ 任务已整合到 `tasks/` 下统一管理；共享基础设施保留在仓库根。

```text
D:\Projects\llm_benchmark\
├── tasks/                          # 五类临床决策 MCQ 任务（探索性原型，exploratory_unreviewed）
│   ├── investigation_selection/    # 1. 检查检验选择（selectivity gold）
│   ├── clinical_diagnosis/         # 2. 临床诊断（PSR gold）
│   ├── treatment/                  # 3. 治疗处置（T1 开立 / T2 执行 / T3 手术）
│   ├── referral/                   # 4. 转诊与科室选择（R1 services）
│   └── discharge_followup/         # 5. 离院指导与随访（F1 文书轨，骨架）
├── benchmark_common/               # 五维共享：条件归一化、统计门禁、通用任务框架
├── data_pipeline/                  # 数据支路（清洗/标准化/文本 NER/聚合）
├── evaluation_pipeline/            # 评测层工程链（split/snapshot/journey）
├── config/                         # 协议与配置
├── schemas/                        # JSON schema
├── docs/                           # 设计文档与报告
├── tests/                          # 测试
└── scripts/                        # 工具脚本
```

每个任务目录自带 `README.md`（含 gold 语义、阈值、结果快照与运行命令）。任务间共享：`benchmark_common/`（条件归一化、统计门禁、通用任务框架）与 `tasks/investigation_selection/output/split/`（患者级 60/20/20 划分，其余四维复用）。所有产物当前均标记 `exploratory_unreviewed`，尚未冻结；见各任务 README 与 `docs/reports/execution-progress-p1-p5.md`。

## 当前进展

截至 2026-08-15，MIMIC 数据层已从 100 例验收样本推进到 1,000 次住院的正式全队列：清洗与确定性标准化通过完整验收并发布 workflow manifest，无损事件聚合把标准化事件重新连接回完整原文与源行血缘，文本事实支路扩展到 1000 例全来源并完成通用 API 接入与多模型小批试点。但正式评测产物仍未形成：检查检验选择协议仍不可冻结，跨批归一化与文本 NER 的人工门禁尚未关闭，真实正式的 split、journey、snapshot、gold、MCQ 和模型评测结果均不存在。已进行的模型调用（DeepSeek/Qwen/Bailian 等）均为 `unreviewed_model_output`，不能替代人工 gold，也不能作为经过验证的实验结果。

> **探索性原型（与正式链路并行）**：五类临床决策 MCQ 的探索性原型已整合在 `tasks/` 下（检查/诊断/治疗/转诊/离院），直接消费 normalized events 出题并做患者级 60/20/20 划分验证与 DeepSeek 模型评测，全部产物标记 `exploratory_unreviewed`，用于预研 gold 语义与阈值，不计入正式评测结果。详见 `docs/reports/execution-progress-p1-p5.md` 与各任务 README。

| 阶段 | 状态 | 已完成的证据 | 尚未完成 |
|---|---|---|---|
| 单次住院原始归档 | 已完成 | 冠状动脉疾病谱共 108,833 次住院、46,062 名患者、50.392 GiB、218 个分片；32张住院内源表的 schema、原生父子键、患者分区和 `chartevents` 排除均通过验证 | 将该归档继续作为只读上游输入，不再改写 |
| 原始归档 EDA | 已完成 | 已完成全量流式分析，覆盖32张表、原始时间字段、疾病谱、模块覆盖和五类题型数据源准备度 | 后续数据层变化需继续以正式 metrics 和 manifest 对账 |
| 字典解码与 POE 解析 | 已完成 | 已实现可携带的字典解码与 POE timeline；保留源字段、原生键和可逆追溯关系 | 新输入版本出现时重新执行合同验证 |
| 临床事件清洗代码 | 33表清洗规则已实现 | 已明确33张输入表的封闭式来源范围与处理规则：21张事实源、6张支持源、6张上下文源；已实现稳定身份、药物原生键连接和统一时间下界 | 在扩大样本前继续保持输入范围、处理规则、回归基线和来源对账一致 |
| 1000例正式全队列（清洗＋标准化） | 已通过完整验收并发布 workflow manifest | 从 39,036 条冠心病住院总体按固定种子无放回抽样 1,000 次住院（964 名患者）；728,199 条事件源行清洗为 757,036 条事件、218 条拒绝；12,786 个唯一术语/单位组合、2,491 条人工复核队列；batch size 5000 与 777 复跑的 run ID 与 Parquet 哈希一致；`can_start_text_ner = true` | 该结论只覆盖当前 1,000 次住院样本，不代表全队列完成；2,540 条归一化复核仍 pending，临床语义尚未人工确认 |
| 无损事件聚合 | 已通过验收 | 把标准化事件重新连接回完整原文与源行血缘：1,241,918 条源记录、757,036 条处理后事件、43,551 条自由文本源记录；`processed_events`/`raw_source_records`/`traceable_events` 三份 Parquet 与质量报告全部 fail-closed 校验通过 | 作为文本 NER 与 patient journey 回顾支路的唯一正文入口，不再回读 source JSONL |
| 跨批归一化人工质量门禁 | 工具与试审队列就绪，人工试审进行中（18/100） | 两批输出已汇总为1,422,220条 normalized events 和16,860个唯一 mapping key；映射冲突为0，已固定抽取100条人工试审并实现本机只读＋追加式审阅界面 | 已写入的18条决定使用占位 reviewer，不能视为完成；100条试审与首任务候选目录判定（`General Xray` 粒度、`Blood tests` 拆分、`Telemetry` 归属等）尚未形成，之后才能冻结候选目录 |
| 文本事实支路（1000例全来源接口） | 接口验收通过；人工双标为空 | 以已验收 aggregation 为唯一输入，覆盖 lab/micro comments、ED 主诉、放射报告与出院小结共 64,509 个文本单元；通用 OpenAI-compatible API、自包含 prompt、确定性 span grounding、分块与断点续跑均已实现；200份pilot 仍按50 calibration/150 evaluation 患者隔离，A/B各171个相同任务、顺序不同 | 人工 A、B 与裁决日志均为0；出院小结（933份，100例审计中占自由文本字符70%）按 `post_hoc` 排除出前瞻性快照，需独立 event-frame 支路；模型输出尚未人工抽样验收 |
| 文本 NER v2 与模型试点 | 干净重做版已实现，多模型 100–300 例试点完成 | v2 修复了 surface 偏移循环重试与无界递归分块两类阻断问题，改为 Python 确定性回填 span 与首次调用前确定性分块；37,790 份文档、41,902 分块；DeepSeek 100例 5,666 实体/309 关系、Qwen 100例 2,716 实体/76 关系、Bailian smoke 5例，以及干净 v2 累计 300 例 12,596 实体/919 关系均产出 sidecar | 试点仅覆盖 100–300 份文档，远未完成 37,790 全量；所有输出均为 `unreviewed_model_output`，向外部服务发送受限文本的合规确认与人工验收仍未完成 |
| 首个检查检验任务协议 | 机器可校验的 draft，尚不可冻结 | 协议、配置、schema、34个固定reason code及fail-closed验证器已实现；当前配置可通过结构校验，但`freeze_ready = false` | 明确患者划分比例、决策时间窗、候选/条件/比较目录版本、缺失与并列策略、统计阈值、bootstrap和稳定性阈值，并补齐输入与代码审计哈希后生成`protocol-lock.json` |
| 患者级正式划分 | 合同与认证实现完成，尚无正式产物 | 已实现患者原子划分、HMAC公开引用、受保护绑定、工程审计集隔离、输入漂移检测和split角色门禁 | 协议中的划分比例尚未决定；当前通过的是合成测试，尚未在正式患者集合生成可发布split manifest |
| Patient journey | Encounter boundary 已实现，完整 journey 尚未实现 | 已实现患者级 split 绑定、一个 `hadm_id` 一个住院边界、原生 ED handoff、ICU 子阶段、事件唯一归属、并列时间组和稳定 unresolved reason code；该层只是 journey 的前置边界 | 当前通过的是合成测试，尚无真实正式boundary manifest；仍需实现state、decision node、evidence edge及journey→node→evidence→raw的完整追溯DAG |
| 决策快照与 gold | 认证快照工程链已实现，科学门禁未冻结 | 已实现通用时间/phase/split/字段白名单快照门禁，以及按 boundary HMAC、protocol/split/source lineage 和 `event_id + source_event_sha256` 强制连接的单 journey adapter | 当前通过的是合成测试，尚无真实正式snapshot或gold；需在协议冻结后对少量development患者生成正式链路并完成未来信息泄漏审计 |
| MCQ 生成 | 设计阶段 | 已形成五类题型设计；检查检验选择已有分阶段方法学方案 | 尚未形成端到端候选题生成、自动门禁和人工审核闭环 |
| LLM 评测 | 尚未开始 | 已确定评测对象是五类临床决策能力 | 模型范围、提示策略、指标、统计检验、错误分析和报告协议均待实现 |

当前唯一的关键路径仍是：关闭首个检查检验选择任务的上游人工质量门禁（跨批归一化100条试审＋文本NER人工A/B校准）和科学协议门禁，再生成第一批真实评测产物。文本NER的模型试点可以与人工门禁并行，但它产出的 `unreviewed_model_output` 不能反向替代人工 gold，也不能跳过协议冻结。

优先执行顺序是：

1. **最高优先级：完成跨批归一化的100条人工试审。** 这是冻结检查检验候选目录前的最后一个上游质量门禁；记录错误类型、歧义和目录粒度问题，必要时修正规则并重跑受影响批次（当前仅18条、reviewer 为占位值，须以稳定 reviewer 身份重做）；
2. 使用人工试审结果确定候选目录版本，同时补齐患者划分比例、决策时间窗、统计与验证阈值等科学参数，验证`freeze_ready = true`后生成并固定`protocol-lock.json`；
3. 在少量development患者上正式生成patient split → encounter boundary → decision snapshot，输出manifest、来源哈希和未来信息泄漏审计；在这一步之后再实现完整的state/node/evidence-edge DAG和单一构念gold；
4. 文本NER calibration可与前两步并行执行，但不能因工具、任务包或模型试点已经生成就视为人工gold完成；必须完成A/B独立标注、第三人裁决和一致性门禁后，才能解锁evaluation；出院小结需按 post_hoc 支路单独建立 event-frame 协议，不得进入前瞻性快照；
5. 将首个检查检验任务闭环到MCQ生成、自动门禁和临床审核；首个闭环通过后，再逐项扩展诊断、治疗、去向和离院计划，不同时铺开五条未经验证的实现线；
6. MIMIC方法学冻结后，在香港RWD中重新完成数据合同、时间语义、本体、行为gold和规范gold的本地化，并开展外部验证。

详细路线：

- [技术路线图（Markdown）](docs/design/patient-journey-benchmark-technical-roadmap.md)
- [交互式技术路线图（离线 HTML）](docs/reports/patient-journey-benchmark-roadmap.html)
