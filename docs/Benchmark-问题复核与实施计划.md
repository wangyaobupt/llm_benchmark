# Benchmark 高频医嘱偏倚、诊断扩展与 phenotype 重构实施计划

> 状态：待用户确认后实施
>
> 审阅日期：2026-08-18
>
> 范围：项目实际进度复核、`BenchMark-进展梳理.md` 核验、`data_pipeline`/`phenotype` 当前状态审阅、高频医嘱偏倚解决方案、多诊断扩展方案。本文不把任何现有候选题称为正式 gold。

## 1. 结论先行

当前最先要解决的不是 TF-IDF，也不是立刻增加诊断数据，而是让 V2 的时间、划分和目标语义重新可信。现有 134 道 formal 候选题不应继续进入人工审核；它们需要标记为失效并在修复后重新生成。

原因有五个：

1. `phenotype` 没有使用项目已经实现的正式 snapshot 可见性合同；它只比较 `event_time`，没有读取 `available_time`。
2. 出院 ICD 诊断和出院小结体格检查被直接加入预测点前条件，构成后验信息泄漏。
3. sidecar 没有按 split 过滤。当前名为 development 的特征表实际混入 184 个 validation、176 个 final_test 住院；其中 346 个非 development 住院进入条件组合表，并改变规则挖掘分母。
4. V2 没有冻结 target window；化验答案使用全住院 `laboratory_resulted`，不是项目级开单事件，任务语义从“下一步开什么”漂移为“住院期间最终得到过什么结果”。
5. 条件组合默认每次住院最多 500 个，但 23,127 个有条件组合的住院中有 11,747 个（50.79%）触顶；截断顺序由 feature ID 排序决定，没有截断报告，条件空间不是所声明的完整 Apriori 空间。

TF-IDF 的方向有价值，但“TF-IDF 可以单独解决当前问题”不成立。V2 已按

\[
\operatorname{lift}(X,Y)=\frac{P(Y\mid X)}{P(Y)}
\]

排序。对二元就诊文档而言，IDF 近似 `-log P(Y)`；`log P(Y|X) + IDF(Y)` 与 `log lift` 只差平滑和常数。因此在现有 lift 上再乘一次 IDF 会重复惩罚高频项，并放大罕见噪声。TF-IDF 应用于：

- 预测点前患者/就诊表示；
- 相似病例检索；
- 候选召回及消融对照。

最终规则排名应以时间安全的目标事件为基础，使用带支持度收缩的条件 log-RR/lift、独立 validation 稳定性和临床审核，而不是让 IDF 直接成为 gold。

## 2. 审阅范围与证据

### 2.1 文档扫描

全库共识别 206 份 Markdown 文档：

| 分组 | 数量 | 审阅方式 |
|---|---:|---|
| `docs/` 当前文档 | 55 | 结构/状态全量扫描，任务相关文档全文交叉核验 |
| `data_pipeline/` | 22 | README、契约和 phenotype 文档全文核验 |
| `docs/reference/` | 48 | 作为 MIMIC 字段语义索引，按涉及来源定向核验 |
| `docs/_archive/` | 5 | 仅用于识别历史口径，不作为当前事实源 |
| `rwd_pipeline/` | 4 | 按仓库约束视为历史交接材料 |
| `tasks/` | 5 | V1 现状、结果和 gold 语义全文核验 |
| `versions/` | 4 | V1 冻结说明与 V2 当前主线全文核验 |
| `docs/P-2026-LLMBenchwork/` | 8 | 全目录扫描，研究方案和进度文档重点核验 |
| 根目录及其他 | 55 | 项目入口、规范、配置提示和方法文档扫描 |

### 2.2 代码与产物证据

重点核验了：

- `data_pipeline/phenotype/*.py`；
- `versions/v2-llm-stem/mcq/{mining,catalog,conditions,pipeline,generation,review}.py`；
- `evaluation_pipeline/snapshot/`；
- `config/investigation-selection/protocol.yaml`；
- phenotype manifest、特征/条件 Parquet、规则 JSONL、134 题生成摘要；
- 冠心病全量 EDA、检查瓶颈指标和 V1 split/validation/final-test 摘要。

现有测试结果：

- phenotype + V2 wiring：22 passed；
- snapshot visibility + boundary adapter：19 passed。

这两个结果合在一起说明：正式 snapshot 层已经能 fail-closed 处理 `available_time`、未知时间、post-hoc 和 split，但 phenotype 没有复用它；现有 phenotype 测试反而把“未知时间默认可用”和“post-hoc ICD 可作既往史”固化为预期行为，因此测试全绿不能证明科学合同成立。

## 3. 当前项目实际进度

| 层级 | 实际状态 | 可以声称什么 | 不能声称什么 |
|---|---|---|---|
| 冠心病原始归档 | 已完成 | 108,833 次住院、46,062 名患者的冠状动脉疾病谱原始归档已建立 | 不能说是全诊断 MIMIC 队列 |
| 三模块事件批 | 已完成工程验收 | 39,036 次住院、20,136 名患者；27,336,811 条 normalized events；workflow manifest 已发布 | 15,316 条归一化复核仍 pending，不能说临床语义已全部审核 |
| event aggregation | 仅 1,000 例验收 | 聚合合同和三份产物已通过样本验收 | 全部 39,036 例尚未聚合 |
| 文本 NER | 工程接口和未审核模型输出已存在 | 可做方法开发和错误分析 | 人工 A/B 双标和裁决为 0，不能作为正式特征或 gold |
| V1 五维原型 | 探索性闭环、已冻结为历史基线 | 221 道 validation rank-1 探索题；final_test 曾使用一次 | 不是临床冻结 gold；随访没有 MCQ gold |
| 正式协议/split/journey/snapshot | 工程合同部分完成 | governance、subject split、boundary、snapshot 有合成测试 | `protocol-lock.json`、正式 split、真实 boundary/snapshot 均不存在 |
| V2 phenotype | 已运行，但结果不合格 | 能证明代码路径可运行并生成 352,063 行特征和 7,974,494 条组合 | 不能说 development 隔离、时间安全或可用于正式审核 |
| V2 规则与题目 | 134 道候选、gold=0 | 生成/程序校验/队列导出链路可运行 | 候选受上游泄漏和语义漂移影响，不能继续审核或发布 |

### 3.1 phenotype 实际产物

`phenotype_manifest_development.json` 声称输入为 12,082 名 development 患者、23,626 次住院；实际特征表有 23,986 个不同 `hadm_id`。各类特征为：

| 类型 | 行数 | 覆盖住院 | 唯一特征 |
|---|---:|---:|---:|
| age_band | 23,626 | 23,626 | 4 |
| sex | 23,626 | 23,626 | 2 |
| symptom | 29,983 | 22,687 | 2,310 |
| physiologic_flag | 28,126 | 17,000 | 9 |
| medication | 61,822 | 7,623 | 32 |
| past_condition | 167,868 | 23,658 | 7,882 |
| sign | 17,012 | 894 | 7,565 |
| absent | 0 | 0 | 0 |

非 development 的 360 个住院只来自 `past_condition` 和 `sign` sidecar：validation 184、final_test 176。条件组合表中仍有 346 个非 development 住院、142,658 行组合。

当前 1,584 条 formal accepted 规则全部属于 imaging；其中 1,102 条含 post-hoc `past_condition`。去重后 738 条、收敛后 165 条，最终生成 134 道候选、31 次生成失败、人工批准 0、gold 0。

## 4. `BenchMark-进展梳理.md` 核验

根目录文件和 `docs/P-2026-LLMBenchwork/BenchMark_当前进度梳理.md` 不是同一份内容；后者只多了格式调整、`TF·IDF` Todo 和一个 troponin 示例，并没有补齐实际 V2 进展。两份并存会继续造成事实源分裂。

| 原内容 | 判断 | 证据与修订方向 |
|---|---|---|
| 项目目标是 patient-journey 五维 MCQ | 基本正确 | 需补充行为 gold 与规范 gold 的边界，以及随访维当前无 MCQ gold |
| 数据源为 MIMIC-IV/HOSP、ED、Note | 正确 | ICU 是可选内容，不是筛选必需条件 |
| 五站式数据路径 | 结构基本正确 | phenotype 站目前不能标为合格完成 |
| clean 层“字典解码具体检查、检验项目” | 部分错误 | 结果项目可解码，但 `laboratory_ordered` 99.99% 没有项目级内容；不能说 POE 已恢复具体检验开单 |
| normalized events 是“归一化完成” | 表述过强 | 工程运行完成，但 12,236,240 条 normalization unresolved、15,316 个 review keys 待人工复核 |
| phenotype 已形成决策时刻快照 | 错误 | 没有使用正式 snapshot；忽略 `available_time`，并摄入 post-hoc 特征 |
| phenotype 为 8 类特征 | 设计层正确、实际产物不完整 | 实际只有 7 类有数据，`absent` 为 0；sign 和 past_condition 来源不合格 |
| development 的 655 道题来自 23,626 住院 | 错误/过时 | V1 当前 development 为 224，validation rank-1 稳定题 84；V2 为 1,584 规则→165→134 候选，不能合并成 655 |
| “数据集以 ICU 单病种为主” | 错误 | 当前是冠心病谱队列，要求 HOSP+ED+Note，ICU 不参与筛选；问题是单疾病谱，不是 ICU-only |
| 高频 CXR/Telemetry/BMP 遮蔽判别检查 | 方向正确但需分层 | BMP/CBC 在结果代理中的覆盖约 91%；不同 class 和时间窗必须分别统计，不能把跨机构“几乎人人做”当固定事实 |
| V2 规则组合 | 缺失 | 应补充 formal 1,584→738→165→134、gold=0，以及本次发现的失效原因 |

建议后续只保留一个当前进展事实源：根目录 `README.md` 负责简要状态，本文件负责问题与实施计划；`BenchMark-进展梳理.md` 在实施阶段改为引用两者，不继续手工复制整套数字。

## 5. 文献调研结论复核

### 5.1 可以保留的结论

1. **高频常规项会让普通精度和频率排名偏向平庸建议。** OrderRex 使用初始就诊信息预测随后医嘱，relative-risk 方法把 inverse-frequency weighted recall 从 4% 提高到 16%，并明确区分“预测最常见事件”和“推荐更有信息量事件”。
2. **时间窗是方法的一部分，不是实现细节。** OrderRex 使用前 4 小时项目作为 query、后续 24 小时新医嘱作为 validation target；这比当前“首个检查前条件 + 全住院目标”更接近可审计任务。
3. **TF-IDF/IPF 适合患者表示和相似病例检索。** 罕见病患者检索和 EHR 表示工作支持降低常见概念权重。
4. **只做逆频率不足以控制罕见偶然共现。** PSR 工作在 1,621 万次就诊上将 TF-IDF 的 NDCG@10 0.799 提高到 0.906，支持加入特异性与可靠性；但它是知识图谱关系排序，不是临床最佳检查 gold。

### 5.2 需要降级的结论

| 调研中的说法 | 修订 |
|---|---|
| “TF-IDF 可以很好解决当前问题” | 改为“TF-IDF 可解决表示/召回中的高频支配，但不能修复时间污染、缺失开单项目、行为≠规范以及稀有噪声” |
| “PSR 已证明适合本项目” | PSR 只证明在另一种关系排序任务上优于 TF-IDF；本项目必须做配对消融和临床盲评 |
| PLOS 2024 的 order-frequency–inverse-patient-frequency 直接支持医嘱 gold | 该研究用于 ED 返院风险建模，是间接方法证据，不是检查选择排名证据 |
| “尚无统一框架，因此构成创新” | 当前检索不是正式系统综述；在完成数据库检索、去重、纳排和引用核验前不能作为论文 novelty 声明 |

### 5.3 最可靠的种子证据

- [OrderRex（JAMIA 2016）](https://pubmed.ncbi.nlm.nih.gov/26198303/)
- [PSR 医疗知识图谱关系排序（Artificial Intelligence in Medicine 2020）](https://pubmed.ncbi.nlm.nih.gov/32143785/)
- [Order frequency–inverse patient frequency 的 EHR 应用（PLOS Digital Health 2024）](https://doi.org/10.1371/journal.pdig.0000606)
- [罕见病患者 TF-IDF 相似检索（Journal of Biomedical Informatics 2017）](https://doi.org/10.1016/j.jbi.2017.07.016)

## 6. phenotype/data pipeline 代码审阅

### 6.1 P0：会污染规则、split 或未来信息边界

#### P0-1：没有使用 `available_time`

- `run_phenotype.EVENT_COLS` 未读取 `source_available_time`、`available_time`、时间质量状态和 reason flags。
- `temporal_gate.gate_events` 只做 `event_time < index_time`。
- 正式 `evaluation_pipeline.snapshot.visibility` 要求 event time 与 available time 都存在且均不晚于 index；未知时间会产生 `SNAPSHOT_TIME_UNKNOWN`。

影响：晚入库结果、未知可用时间的生命体征/用药核对和其他记录可能被当成预测点前证据。

#### P0-2：未知时间被默认当成可用

`is_available` 明确把无 `event_time` 的 source event 当作已知的 presenting state。现有 39,093 条 `symptom_reported` 的 event/available time 均为空，项目其他审计文档已经规定“ED chief complaint 可用时间未知，不使用 ED 入科时间替代”。两套政策互相冲突。

影响：规则可以运行，但无法证明题干信息在目标医嘱前真实可见。

#### P0-3：post-hoc ICD 作为既往史

`run_phenotype.build` 刻意向 `extract_past_condition_icd` 传入未门禁事件；后者读取 `condition_recorded_post_hoc` 并用关键词判断慢病。MIMIC `diagnoses_icd` 是出院编码，缺少可靠 POA 语义；“慢病名”不等于“预测点前已知既往史”。

影响：最终诊断可通过 `past_condition` 间接进入题干条件。1,584 条规则中 1,102 条使用该类特征。

#### P0-4：出院小结体格检查作为预测点前 sign

`sign_ner` 从 discharge summary 中抽取 Physical Exam、Admission Exam、Exam on Discharge；输出没有 assertion/time/source section/模型审核状态，只保留短语。随后 `run_phenotype` 不经时间门禁直接拼入特征。

影响：住院后或出院时体征、治疗后状态可能被当作初始表现；`unreviewed_model_output` 被用于 formal 规则。

#### P0-5：split sidecar 污染

`signs` 和 `past_condition_ner` 只按路径读取，不与 development `hadm_id/subject_id` 做 inner join，也不验证 sidecar 的 split/输入哈希。实际混入 184 个 validation、176 个 final_test 住院。

影响：346 个非 development 住院进入条件空间；`mine_rules` 用条件表的 distinct hadm 作为 `n_total`，因此直接改变 baseline probability、lift、FDR 和支持度剪枝。当前 legacy final_test 不能再作为 V2 的正式盲测集。

#### P0-6：目标事件和时间窗未冻结

- 协议中的 observation/target window 仍为 `null`。
- index 是每次住院“任意三类检查医嘱的最早时间”，不是按 decision node/target episode 构建。
- imaging/clinical 使用整次住院所有 eligible orders；laboratory 使用整次住院所有 `laboratory_resulted`。

影响：任务不是 next-order prediction，也不是冻结时间窗内的 order-set concordance；重复监测、住院后复查和 ICU 检验均进入答案。

### 6.2 P1：会显著改变候选空间、统计量或可复现性

#### P1-1：条件空间静默截断

`enumerate_conditions` 默认每个住院最多输出 500 个组合。50.79% 的住院触顶；程序既不报告被截断数量，也不保证按临床信息量选择组合。

影响：哈希/类型排序较早的组合获得系统性优势，后续组合不是“支持度不足”，而是从未参与检验。

#### P1-2：统计分母只统计已有候选的条件住院

`n_x` 从 `cond INNER JOIN order_frame` 后计算。一个条件存在但目标窗内没有该 comparison class 候选的住院不会进入 `n_x`。

影响：`P(Y|X)`、Wilson lower bound 和 bootstrap stability 被向上偏置。正确分母应是全部 eligible condition decision documents；没有候选是零事件，不是删除样本。

#### P1-3：bootstrap 单位错误

协议要求 `bootstrap_unit: subject_id`，当前 `_bootstrap_stability` 按 `hadm_id` 列表重采样；`conditions` 也没有 subject_id。

影响：同一患者多次住院被当作独立样本，稳定性和置信度可能偏高。

#### P1-4：化验结果代理开单

`laboratory_ordered` 99.99% 没有项目名，当前代码改用 `laboratory_resulted` panel。这个做法可支持“结果可见性/住院中做过什么”的行为研究，但不能支持“医生下一步开哪个具体检验”的 gold。

影响：TF-IDF 无法修复源数据缺少 order→result 链接的事实；必须拆分任务语义。

#### P1-5：产物合同不足

- phenotype manifest 不记录 feature/condition 输出哈希；
- 输出直接写入目标路径，不是原子发布；
- mining 的 formal/exploratory 共用同一输出文件，后跑可覆盖先跑；
- rule 输出缺少独立 run manifest、threshold hash、condition hash；
- dedup/converge 也没有输入输出哈希和算法版本。

影响：文档中的 20,904、1,584、738、165 无法仅靠现存 manifest 完整追溯。

### 6.3 P2：维护性和验证盲区

- 多个脚本硬编码 `D:`/`G:` 绝对路径，无法由统一配置驱动。
- 时间用字符串比较，不验证格式一致性。
- 生成和自动审题使用同一 client/model，只是 prompt 不同，“独立自动审题”表述应降级。
- phenotype 测试没有覆盖 available-time 晚于 index、sidecar split 混入、post-hoc sign/ICD 拒绝、500 组合截断、subject-level bootstrap、target-window 外事件。
- `Case_Spider.md` 与当前 MIMIC 管线无关，含内网地址和硬编码用户标识，不应留在当前研究证据目录。

## 7. 问题一解决方案：高频常规医嘱遮蔽

### 7.1 先冻结研究单位

建议把一个统计文档定义为一个 `decision_document`，而不是整次住院：

```text
subject_id
hadm_id
decision_node_id
index_time
observation_window
target_window
pre_index_feature_ids
target_order_episode_ids
comparison_class
split_role
cohort_strata
lineage
```

主实验起点可参考 OrderRex：前 4 小时 observation、随后 24 小时 target；但该值只能作为 development sensitivity grid 的候选，最终值必须写入冻结协议，不能因为题量变化而调整。

### 7.2 先做 order episode，再做频率

1. 合并同一 POE 生命周期链的 New/Change/Cancel/Discontinue。
2. 排除取消、未执行、纯物流、饮食、转运等不属于 investigation 的动作。
3. 同一候选在短时间内的重复开立折叠为一个 burst/order episode。
4. panel 与 component 双层保留，不让 BMP/CBC 各成分重复放大频率。
5. primary TF 使用二元 `0/1`；`1+log(count)` 只作为重复强度消融，不作为主方案。

### 7.3 三类答案必须拆开

| 轨道 | 可用来源 | 可声称语义 |
|---|---|---|
| imaging order | `imaging_ordered` 项目/模态 | 目标窗内观察到的新影像医嘱 |
| clinical order | 有明确 content specificity 的 `clinical_ordered` | 目标窗内观察到的新临床检查/监护医嘱 |
| laboratory result proxy | `laboratory_resulted` | 目标窗内首次变为可见的检验结果/检验 panel，不称“开单选择” |

具体 laboratory order gold 在 MIMIC 中缺少项目级开单和 order→result 链接。根本解决办法是：在具有项目级开单键的香港 RWD 上构建 order track；MIMIC 的 result proxy 单独报告，不混入同一个排行榜。

### 7.4 TF-IDF 的正确位置

对 development 决策文档拟合：

\[
idf(y)=\log\frac{N+1}{df(y)+1}+1
\]

其中 `df(y)` 是包含候选 y 的 decision document 数，不是原始事件行数。IDF 只能读取 development，validation/final_test 不参与词表、df、阈值或截断。

实现两条可比较路径：

1. **规则路径（主路径）**：直接用时间安全的 condition→candidate 计数计算收缩 log-RR/lift。
2. **检索路径（TF-IDF 路径）**：用预测点前 feature TF-IDF 向量检索相似 development decision documents，再聚合它们的 target orders。

TF-IDF 不与 lift 机械相乘。若做 hybrid，只允许把“检索得到的局部证据”和“全局收缩 RR”作为两个校准特征，由 validation 决定权重；不得把 final_test 用于权重选择。

### 7.5 可靠性收缩

主统计量建议为：

\[
\widehat{\log RR}_{shrunk}
=
\frac{n_{xy}}{n_{xy}+\lambda}
\log\left(
\frac{(n_{xy}+\alpha)/(n_x+2\alpha)}{(n_y+\alpha)/(N+2\alpha)}
\right)
\]

其中：

- `N`：全部 eligible development decision documents；
- `n_x`：出现条件 X 的全部文档，包括没有候选的文档；
- `n_y`：出现候选 Y 的文档；
- `n_xy`：X/Y 共现文档；
- `alpha/lambda`：只在 development+validation 确定并冻结。

当前统一 `min_smoothed_probability=0.60` 不适合长尾特异项，应改成按 comparison class 预注册的支持度、置信下界、收缩 RR 和稳定性组合。改变门槛的目标是对齐构念，不是增加题量。

### 7.6 评价矩阵

| 维度 | 指标 |
|---|---|
| 高频遮蔽 | rank-frequency Spearman、HighFreqOccupancy@K、head/mid/tail Recall@K |
| 长尾发现 | inverse-frequency weighted recall、macro Recall@K、frequency-stratified NDCG |
| 罕见噪声 | 最低支持度、经验贝叶斯后验下界、置换负对照的假阳性率 |
| 时间有效性 | target-window 外事件摄入数必须为 0；post-hoc/unknown-time 摄入数必须为 0 |
| 稳定性 | patient-level bootstrap、development→validation rank concordance、规则 Jaccard |
| 临床价值 | 高频/中频/低频分层盲评、诊断/筛查目的、唯一答案、可行动性 |

必须增加两个反事实测试：

- 把同一个常规医嘱复制 10 次，二元 episode 排名不得改变；
- 加入一个只出现 1 次的随机候选，不能因 IDF 极高进入 Top-K。

## 8. 问题二解决方案：诊断单一化与数据扩展

### 8.1 不直接“随机再抽一批”

目标不是让诊断名称更多，而是让检查决策分布更丰富。应先在源 `diagnoses_icd` 上做只读诊断覆盖审计，再根据“新增候选覆盖 + 与 CAD 检查分布差异”选择队列。

对每个诊断家族 g 计算：

- 患者数、住院数、主诊断/次诊断比例；
- HOSP/ED/Note/POE/可用时间覆盖；
- 时间安全 target order episode 的候选分布；
- 与 CAD 分布的 Jensen-Shannon divergence；
- 新增候选覆盖数；
- head/mid/tail 分布；
- 可构造 decision document 的比例。

选择 Pareto 前沿，而不是按疾病知名度手工挑选。

### 8.2 建议候选临床谱系

以下仅作为审计分层起点，最终 code set 应使用带来源和版本的 ICD-9/10→CCSR/临床家族映射，并经临床复核：

- 神经血管/神经急症：扩大 CT/MRI、血管成像、凝血和代谢检查；
- 呼吸/肺部：扩大 CXR、CT、血气、微生物检查；
- 感染/脓毒症：扩大培养、乳酸、炎症和器官功能检查；
- 腹部/消化：扩大超声、腹部 CT、肝胆胰检验；
- 肾脏/代谢：扩大电解质、尿液、酸碱和肾功能检查；
- 创伤/骨科：扩大部位影像和术前检查；
- CAD 保留为对照谱系。

### 8.3 分层选择算法

1. 建立 multi-label 诊断家族标签；诊断只用于 cohort sampling/stratified reporting，不进入预测快照。
2. 使用 `subject_id` 先划分角色，再在角色内抽取住院；同一患者跨多个诊断也只能属于一个 split。
3. 每个住院保留多标签用于分析，但抽样时分配一个 canonical stratum，避免重复计数。canonical stratum 的规则必须预注册，例如主诊断家族优先、无主诊断时按固定临床优先级。
4. 样本量不写死为“每病种一样多”。对每组使用：

\[
N_g \ge \left\lceil \frac{n_{tail,min}}{\widehat p_{tail,g}} \right\rceil
\]

确保目标长尾候选在 development 和 validation 都达到最低患者级支持度。
5. 保存两套统计视图：
   - natural-prevalence view：保持真实分布，用于全局 IDF、校准和总体结果；
   - stratified audit view：各谱系有足够样本，用于 macro 指标和临床审阅。
6. 任何平衡抽样都保存 sampling weight；不能用平衡样本的频率冒充真实患病率或真实开单概率。

### 8.4 抽取实现方向

当前 `mimic_raw_archive/cohort.py` 把 CAD 规则硬编码为 ICD-9 410–414 / ICD-10 I20–I25。实施时应改成配置驱动的 cohort registry：

```text
config/cohorts/diagnosis-strata.yaml
schemas/diagnosis-strata.schema.json
data_pipeline/mimic_raw_archive/cohort.py
```

每个 selection manifest 至少记录：

- code set 版本和哈希；
- source `diagnoses_icd` 哈希；
- subject/hadm；
- multi-label strata 和 canonical stratum；
- split role；
- inclusion/exclusion reason；
- sampling weight；
- HOSP/ED/Note/POE 覆盖；
- 生成代码 Git commit。

超过 50 MB 的抽取产物继续留在数据目录并写入 `.gitignore`；只提交配置、schema、代码、测试和小型 manifest 摘要。

## 9. 实施工作包与依赖顺序

### W0：停止错误链路继续扩散

操作：

- 将现有 134 题标记为 `invalidated_upstream_temporal_and_split_leakage`；
- 暂停人工审核和任何模型评测；
- legacy final_test 明确降级，不能再作为 V2 正式 blind final test；
- 增加运行前 guard：检测 sidecar split、post-hoc 特征或未知时间即失败。

完成条件：旧产物不能被 gold exporter 或审核入口读取。

### W1：冻结构念、decision document 和时间窗

操作：

- 决定 imaging/clinical order 与 laboratory result proxy 的独立语义；
- 冻结 observation/target windows、并列 order-burst、取消/变更策略；
- 补齐 `protocol.yaml` 的 null 和 unresolved decisions；
- 规定 ED triage 未知时间的政策：没有正式结构先后证据就排除，不能静默假定可见。

完成条件：protocol validate 显示 `freeze_ready=true`，生成 `protocol-lock.json`。

### W2：复用正式 snapshot，删除 phenotype 私有时间政策

操作：

- phenotype 不再自行实现 `is_available`；
- 从 encounter boundary + normalized events 生成真实 decision nodes/snapshot；
- 强制 event time、available time、phase、split、field whitelist 和 source hash；
- sidecar 必须带 subject/hadm/split/source time/review status，并在进入 feature frame 前 inner join。

完成条件：真实 development 小样本的 post-hoc、unknown-time、validation/final-test 事件摄入均为 0。

### W3：重建可信特征层

操作：

- demographics 保留；
- symptoms 只接收通过时间政策的来源；
- vitals 使用 available-time 合同；
- medication reconciliation 只有结构性/时间证据成立才进入；
- 移除出院 ICD 既往史代理；既往史只用预测点前已记录来源；
- 移除 discharge-summary sign；改用预测点前文书或不启用 sign；
- 取消静默 500 cap，改为支持度优先的两阶段 Apriori，并报告每级候选/剪枝数。

完成条件：feature manifest 中的 unique hadm 与 development eligible hadm 完全一致，输出含哈希并原子发布。

### W4：建立 investigation order episode

操作：

- POE lifecycle 合并、burst collapsing、panel/component 双层表示；
- target window 过滤；
- imaging/clinical/lab-result 三轨分开；
- 输出可追溯 decision-document/episode 表。

完成条件：复制重复医嘱不改变 episode 计数；target-window 外事件为 0。

### W5：实现频率偏倚配对实验

固定同一数据、同一候选集、同一 split，比较：

1. conditional probability；
2. TF-IDF retrieval；
3. raw lift/log-RR；
4. shrunken log-RR；
5. TF-IDF retrieval + shrunken log-RR rerank。

完成条件：预注册指标全部输出；不能只选择对题量最有利的方法。

### W6：诊断覆盖审计和多谱系抽取

操作：

- 在源诊断表上先做只读全量 profile；
- 用支持度、模块覆盖、JSD 和新增候选覆盖选择谱系；
- 生成配置驱动 selection manifest；
- patient-first split 后抽取、清洗、标准化和聚合新数据。

完成条件：每个谱系满足患者级支持门槛，且新增候选覆盖相对 CAD 有可测增益。

### W7：重跑、validation 和人工审核

操作：

- 只在 development 拟合 IDF、词表和统计参数；
- validation 做 patient-level 稳定性和阈值选择；
- 分 head/mid/tail、comparison class、诊断谱系抽取盲评样本；
- 人工审核通过后再生成新的 formal 候选队列。

完成条件：所有题目可追溯到 protocol lock、split、decision snapshot、target episode、规则统计和人工决定。

### W8：重建正式 final test 和文档事实源

操作：

- 从未参与前述开发的患者池生成新的受保护 formal final-test split；
- 更新 README、进展梳理、方法学、冻结清单；
- 删除重复/过时数字，历史口径移入 archive 并标注来源。

完成条件：final-test 的原始行、统计、缺失率和失败日志在开发阶段均不可见。

## 10. 文件级改动地图

| 文件/模块 | 计划改动 | 为什么 | 对用户的影响 |
|---|---|---|---|
| `config/investigation-selection/protocol.yaml` | 冻结窗口、语义、并列/缺失政策 | 当前 null 导致任务不可定义 | 每道题的“何时、预测什么”一致 |
| `evaluation_pipeline/snapshot/` | 提取可复用 visibility/decision-node 接口 | 避免 phenotype 另建弱门禁 | post-hoc 和晚可用信息被统一阻断 |
| `data_pipeline/phenotype/temporal_gate.py` | 删除私有宽松政策或变成正式 snapshot adapter | 当前忽略 available_time | 预测点证据可审计 |
| `data_pipeline/phenotype/run_phenotype.py` | sidecar role/hash 校验、原子发布、完整 manifest | 当前混入 val/test 且输出无哈希 | development 真正隔离 |
| `data_pipeline/phenotype/past_condition.py` | 移除出院 ICD 预测特征用途 | 后验编码不是既往史时点证据 | 减少诊断泄漏 |
| `data_pipeline/phenotype/sign_ner.py` | 限定预测点前来源并保留时间/审核状态 | 当前读 discharge summary | 体征不再含出院状态 |
| `data_pipeline/phenotype/condition_space.py` | 两阶段 Apriori、取消静默 cap、输出剪枝审计 | 50.79% 住院触顶 | 条件组合不再受哈希顺序支配 |
| `versions/v2-llm-stem/mcq/mining.py` | 正确分母、subject bootstrap、时间窗目标、收缩 RR/实验接口 | 当前统计偏置 | 低频特异项与高频常规项公平比较 |
| `versions/v2-llm-stem/mcq/catalog.py` | 三轨候选和 episode 粒度 | lab result 与 order 混轨 | 题目语义清晰 |
| `data_pipeline/mimic_raw_archive/cohort.py` | 配置驱动诊断谱系 | 当前只支持硬编码 CAD | 可重复扩展多诊断数据 |
| `tests/test_phenotype.py` | 改写时间和 post-hoc 预期 | 当前测试认可泄漏 | 测试能阻断错误而非固化错误 |
| 新增 regression fixtures | split 污染、available-time、target-window、cap、重复医嘱 | 覆盖当前盲区 | 后续 LLM 修改不能复发同类问题 |
| `README.md` / `BenchMark-进展梳理.md` | 更新实际状态和唯一事实源 | 当前版本漂移 | 项目进度不再互相矛盾 |

## 11. 验收门禁

实施完成必须同时满足：

### 数据与划分

- 任一 development 产物中的 subject/hadm 均属于 development；
- validation/final-test sidecar 注入测试必须 fail-closed；
- 同一患者不能跨 split；
- IDF、词表、候选目录、阈值不读取 validation/final-test。

### 时间

- 每个可见事件同时满足 occurrence/availability/phase 政策；
- post-hoc 和 administrative-end 进入前瞻特征数为 0；
- 未知时间没有显式结构先后规则时一律拒绝；
- 目标事件全部落在冻结 target window。

### 统计

- `n_x` 包含没有候选的 eligible documents；
- bootstrap unit 为 subject；
- FDR family 在看结果前机械枚举；
- head/mid/tail 指标和总体指标同时报告；
- 罕见单次噪声不能通过支持度/收缩门禁。

### 产物

- manifest 包含 schema/version、protocol/split/input/output hash、参数、计数和 Git commit；
- 原子发布，不覆盖已有成功产物；
- formal/exploratory 使用不同 run directory，由 manifest 标识，不靠文件名版本号管理；
- 超过 50 MB 的数据产物不进入 Git。

### 临床与发布

- 行为一致性不能表述为临床最佳决策；
- laboratory result proxy 不能表述为 order selection；
- 自动审题不能替代独立临床审核；
- gold 仍保持 0，直到程序、独立复核和人工审批全部通过。

## 12. 需要用户确认的实施决策

1. 是否同意暂停并失效现有 134 道 V2 候选，修复后重新生成。
2. 是否同意把 MIMIC laboratory 拆为 `result-availability proxy`，不再称具体检验开单 gold；具体 order gold 留给具有项目级开单键的香港 RWD。
3. 是否同意 TF-IDF 作为候选召回/相似病例路径，最终规则以收缩 log-RR/lift + validation + 临床审核决定。
4. 是否同意 legacy final_test 不再用于 V2 正式测试，协议冻结后从未参与开发的患者池建立新的 formal final test。
5. 是否同意多诊断扩展先做全源诊断覆盖与检查分布差异审计，再决定实际谱系和抽取规模，不直接随机平衡抽样。

确认后按 W0→W8 顺序实施；每个完整工作包单独验证，但一次完整任务形成一个本地 Git commit，未经明确指令不 push。
