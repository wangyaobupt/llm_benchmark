# 基于 MIMIC/EHR 构建五维临床 MCQ Benchmark：证据综述与出题蓝图

> 调研日期：2026-08-10  
> 研究对象：检查检验选择、临床诊断、治疗处置、转诊科室、离院指导五类单项最佳答案题  
> 证据范围：MIMIC 官方数据说明、原始 benchmark/dataset 论文、EHR 泄漏方法学论文、医学 MCQ 实证研究；检索以英文公开来源为主。本文是 benchmark 设计报告，不是临床指南。

## 1. 结论

五类题可以建立在同一条数据流水线上，但**不能把真实 EHR 中“发生了什么”和医学上“应该做什么”混成同一种标准答案**。

最稳妥的设计是预先选择并明确发布以下一个或两个轨道：

| 轨道 | 题目实际测量的构念 | Gold 的含义 | 可作出的结论 |
|---|---|---|---|
| RWD-concordance（行为一致性） | 模型能否复现该机构的群体实践模式，或预测某次 encounter 随后发生的事件 | 预先声明为开发集群体规则的 argmax，或病例级实际事件 | “模型复现了历史临床实践模式”；两种子任务不可混名、混分 |
| Clinical-best-decision（规范性决策） | 模型能否在给定时点选择当前证据支持的最佳决策 | 冻结版本指南、当地服务路径和临床专家裁定 | “模型在受控病例上作出规范性临床判断” |

两条轨道都可以有五类题，但不能共用一个未经区分的总准确率。真实检查、用药、转科和出院建议受到资源、床位、医生习惯、患者偏好、禁忌证和文书完整度影响；“最常发生”不等于“最佳”。反过来，用指南答案评价“下一步真实行为预测”也改变了任务定义。

对当前项目的直接建议是：

1. 保留已经明确的检查题 `most likely to be selected` 作为 **RWD pattern/rule-concordance pilot**：合成特征条件 `X`，gold 是仅由 development 患者估计、并在独立样本验证的 `argmax_y P(y|X)`。不要把它改写成病例级实际下一事件，也不要把其准确率解释为指南依从性。
2. 若项目核心主张是“评估临床推理/决策能力”，五维正式主榜应采用 **Clinical-best-decision**：EHR 只提供候选病例和可见事实，gold 必须独立于实际行为，由指南证据与专家裁定形成。
3. 病例级题必须有显式 decision snapshot（决策快照），先冻结可见信息，再隐藏未来结果；群体规则题则必须有 rule manifest，记录 (X)、候选 (y)、开发集统计量、独立验证结果和版本。两种证据单元不能混用。
4. 不应把多个患者的特征重新拼接后仍沿用其中一人的真实行为作为 gold。合成/重组特征可以服务于 pattern/rule-concordance，但 gold 必须来自开发集群体规则；病例级 next-event 必须保持单一 encounter；规范性合成题则需重新裁定 gold。
5. 先做每维 100 道候选题的 pilot。只有泄漏、唯一答案、专家一致性和干扰项功能均达标，才扩大题库。

## 2. 为什么首先要分清行为预测与规范性决策

MIMIC-IV 是回顾性、常规诊疗过程中产生的数据。官方说明明确指出，数据反映日常实践的特异性，归档过程还可能产生不合理数值；其模块按来源区分 EHR、ICU、ED 和文书，而不是按“医学真值”组织（[MIMIC-IV v3.1](https://physionet.org/content/mimiciv/3.1/)，[MIMIC-IV 原始论文](https://doi.org/10.1038/s41597-022-01899-x)）。

因此，同一个 EHR 事件可以支持不同任务：

- “患者接下来最可能被开哪项检查？”可以用下一条有效医嘱作为行为 gold；
- “患者此时最应该做哪项检查？”不能仅因某项检查实际被开立就把它当成规范性 gold；
- “本次住院最后被编码为何种诊断？”可以用账单编码作标签；
- “在当前可见证据下最可能的临床诊断是什么？”不能把出院后编码不经审核地当成临床真值。

这一差异是构念效度问题，不是措辞问题。Alaa 等在 ICML 2025 的立场论文中主张，医疗 LLM benchmark 必须验证题目是否真正测量它声称的临床能力，而不能用考试分数替代真实构念（[Medical LLM Benchmarks Should Prioritize Construct Validity](https://proceedings.mlr.press/v267/alaa25a.html)）。

### 2.1 推荐的任务声明

每个 release、每类题、每道题都保存：

```text
construct: rwd_concordance | clinical_best_decision
decision_actor: ED clinician | inpatient team | discharge team | ...
care_setting: ED | ward | ICU | discharge
index_time: 决策发生前的冻结时点
visible_evidence_rule: available_time <= index_time + 字段白名单
hidden_target: 被预测事件或经裁定的最佳决策
gold_source: observed_event | guideline_expert_adjudication | hybrid_candidate_only
```

若一篇论文希望同时报告两种能力，应分别命名为 RWD-Concordance 与 Guideline/Expert-Adjudicated Decision，不计算一个混合主分数。

## 3. 一手证据矩阵

| 来源 | 直接证据 | 对本项目的设计含义 |
|---|---|---|
| [MIMIC-IV v3.1 官方页面](https://physionet.org/content/mimiciv/3.1/)；[Scientific Data 数据论文](https://doi.org/10.1038/s41597-022-01899-x) | MIMIC-IV 按数据来源分模块；日期经去标识化；常规诊疗数据存在归档特异性；派生数据仍应按敏感数据对待 | 必须保留 provenance、使用可用时间而非仅事件时间；公开派生 benchmark 要遵守 PhysioNet 数据协议 |
| [MIMIC-IV-Note v2.2](https://physionet.org/content/mimic-iv-note/2.2/) | 出院小结描述住院原因、病程和出院指导；放射报告含检查发现与结论；PHI 被替换为 `___` | 出院小结是强后验信息源。做早期检查/诊断/治疗题时必须整体禁用或按可验证章节严格切分；占位符和原文重合需检测 |
| [MIMIC-IV-ED diagnosis](https://mimic.mit.edu/docs/IV/modules/ed/diagnosis.html)；[MIMIC-IV diagnoses_icd](https://mimic.mit.edu/docs/IV/modules/hosp/diagnoses_icd.html) | ED 诊断在离院后确定；住院 ICD 是出院后由编码人员依据签署文书生成的计费诊断；低优先级排序未必有唯一正确顺序 | ICD 适合筛选候选病例或“最终编码预测”，不应不经专家复核直接充当早期临床诊断 gold |
| [MIMIC-IV POE](https://mimic.mit.edu/docs/iv/modules/hosp/poe.html)、[prescriptions](https://mimic.mit.edu/docs/iv/modules/hosp/prescriptions.html)、[eMAR](https://mimic.mit.edu/docs/IV/modules/hosp/emar.html) | POE 是医嘱；prescriptions 是处方；eMAR 记录床旁扫码给药，且包含 delayed/not given 等状态；三者可链接但不是同一事件 | 治疗题必须先规定 gold 是“开立”“计划开始”还是“实际给药”。规范性 gold 不能以任一表单独替代临床裁定 |
| [MIMIC-IV services](https://mimic.mit.edu/docs/IV/modules/hosp/services.html)、[transfers](https://mimic.mit.edu/docs/IV/modules/hosp/transfers.html) | `services` 表示负责患者的医疗服务团队；`transfers` 表示物理病区/床位位置，二者可能不同 | 转诊题不能把病区位置当作专科归属；应将“会诊”“负责服务”“物理转运”“院外转介”拆成明确子任务 |
| [MIMIC-IV-ED triage](https://mimic.mit.edu/docs/IV/modules/ed/triage.html) | triage 含主诉、生命体征和 ESI，但 triage 观测没有独立时间，最接近时间是 `edstays.intime`；部分缺失由去标识或原始缺失造成 | 检查题早期快照可从 triage 起步，但必须记录时间近似和 missingness 语义；不能假定空值等于“正常/未发生” |
| [Harutyunyan et al., Scientific Data 2019](https://doi.org/10.1038/s41597-019-0103-9) | MIMIC-III benchmark 为每个预测明确定义观察窗口和未来结局；小时级任务只使用预测时点之前事件 | 五类题也应将每题定义成“观察窗口—index time—目标窗口”，而不是整次住院静态切片 |
| [A framework for understanding label leakage in machine learning for health care](https://pmc.ncbi.nlm.nih.gov/articles/PMC10746313/) | 医疗数据存在记录延迟；仅遵守“不要使用未来时间戳”不足以避免标签泄漏；诊疗过程中产生的代理变量可能确定性暴露结局 | 每个字段需同时管理 event time、recorded time、available time；还要做语义泄漏检查，而非仅 SQL 时间过滤 |
| [DiSCQ / Learning to Ask Like a Physician](https://doi.org/10.18653/v1/2022.clinicalnlp-1.8) | 医疗专家从 100 余份 MIMIC-III 出院小结产生 2,000 余个真实信息需求问题；作者指出纯自动模板问题难以代表医生真实提问 | 题型蓝图和临床信息需求应由临床专家先定义；LLM 适合起草语言，不应自行决定研究构念 |
| [EHRNoteQA, NeurIPS 2024](https://proceedings.neurips.cc/paper_files/paper/2024/file/e15c4afff22f12c4986c1fcb4e941e03-Paper-Datasets_and_Benchmarks_Track.pdf) | 1,000 个 GPT-4 草稿经临床审核后删除 38 个；962 个保留样本中 206 个问题、338 个答案及大量干扰项需修改；论文要求干扰项来自病例且必须合理，并报告评测者与临床医生的 Cohen kappa | LLM 生成后必须逐题临床修改，不能只抽检；应记录删除率、修改率和标注一致性；干扰项需要病例相关性审核 |
| [MIMIC-CDM, Nature Medicine 2024](https://doi.org/10.1038/s41591-024-03097-1) | 2,400 个 MIMIC-IV 急腹症病例被组织成逐步索取查体、实验室和影像信息后诊断/治疗的交互任务；全信息 second-reader 诊断与自主信息收集表现明显不同；治疗期望同时参考指南与病例实际治疗 | 同一病例在“信息已给全”和“模型自己决定收集什么”下测到的能力不同，必须固定交互设定；该文的“指南 + 实际治疗”是可借鉴的 hybrid 实现，不证明所有真实治疗都是规范性 gold |
| [Triage/referral/diagnosis workflow, npj Digital Medicine 2025](https://doi.org/10.1038/s41746-025-01684-1) | 研究用 2,000 个 MIMIC 病例评估 ESI、转诊专科和诊断；作者明确指出 MIMIC-ED/Note 没有精确的基层转诊专科字段，因而由 Claude 3.5 生成专科“ground truth”；专科又由出院主诊断推导 | 该研究证明这些子任务可被形式化，也同时展示了 gold 风险：LLM 生成标签和出院后诊断不能作为本项目独立真值；转诊 gold 必须由本地路径与专家裁定 |
| [CliBench](https://arxiv.org/abs/2406.09923) | 从 MIMIC-IV 构造诊断、治疗操作、检验医嘱和药物处方任务，并以结构化 ontology 做多粒度评价 | 支持五维任务采用标准术语与分层粒度；它是相关 benchmark 实现，不足以证明 EHR 后验标签等同于最佳临床决策 |
| [EHRBench](https://arxiv.org/abs/2605.30637) | 采用 EHR–LLM–知识库交互，将 encounter 轨迹转成结构化模板，再确定性实例化 QA，以追求规模与可靠性 | 支持“LLM 结构化、模板确定性出题”的工程路线；截至本报告它是 2026 年 arXiv 预印本，仍需本项目独立验证 gold、泄漏与专家一致性 |
| [实证医学 MCQ 干扰项研究](https://pmc.ncbi.nlm.nih.gov/articles/PMC3004925/)；[MCQ item analysis](https://pmc.ncbi.nlm.nih.gov/articles/PMC7873707/) | 大量题目的第四个干扰项不具功能；难度、区分度、干扰项效率和内部一致性是常用题项质量指标 | 项目虽固定 A–D 四选项，但若找不到 3 个有效干扰项，应拒绝该题而不是填充明显错误项；上线后必须做题项分析 |
| [Large Language Models Are Not Robust Multiple Choice Selectors, ICLR 2024](https://proceedings.iclr.cc/paper_files/paper/2024/hash/54dd9e0cff6d9214e20d97eb2a3bae49-Abstract-Conference.html) | 20 个 LLM 在三个 benchmark 上表现出选项 ID/位置偏好，调换选项可改变预测 | A–D 均衡只是最低要求；正式评测还应做选项排列敏感性测试，避免把位置偏好当临床能力 |
| [BetterBench, NeurIPS 2024](https://doi.org/10.52202/079017-0685) | 作者从 benchmark 全生命周期提出质量实践并发现常用 benchmark 常缺统计显著性和可复现性报告 | 支持完整记录构念、数据、指标、统计不确定性、维护和复现；它是通用审计框架，不是医疗 gold 构建规范 |
| [AI discharge instruction safety, npj Digital Medicine 2024](https://doi.org/10.1038/s41746-024-01336-w) | 对 100 份 MIMIC-IV 出院小结生成患者指导，18% 存在可能有害的 AI 相关安全问题，包括幻觉和新增药物；遗漏/新增行动的一致性也有限 | 离院指导不能由生成模型自由补齐；药物、复诊行动和危险信号需逐项核对来源并由医生/药师审核 |

## 4. 统一的数据与出题流水线

### 4.1 病例快照与群体规则是两种不同的最小证据单元

**Encounter next-event 与规范性病例题**先建立不可变 snapshot，而不是先把整份病历交给生成模型：

```json
{
  "subject_id": "internal only",
  "encounter_id": "internal only",
  "question_type": "diagnosis",
  "construct": "clinical_best_decision",
  "index_time": "...",
  "observation_start": "...",
  "target_window": ["...", "..."],
  "visible_source_rows": ["..."],
  "hidden_source_rows": ["..."],
  "gold_source": "guideline_expert_adjudication",
  "provenance_hash": "..."
}
```

快照选择规则：

1. 先以 `subject_id` 分配数据集，再做任何规则挖掘、提示词开发或题目生成。
2. `index_time` 必须早于被预测事件；输入以 `available_time <= index_time` 判定，而不是只看采样/执行时间。
3. 题干只允许使用 snapshot 白名单中的事实；同一事实的后验总结、计费编码、最终 impression 和出院结论仍算泄漏。
4. 缺失值保留“未记录/未知”，不得转换为正常；记录延迟未知的字段不得进入需要严格时点的题。
5. 每道题保留源行 ID、转换规则和 gold 证据，发布文本与内部可追溯记录分离。

**Pattern/rule-concordance 题**不对应一个病例级 hidden event，其最小单元是冻结的 rule manifest：

```json
{
  "task": "pattern_rule_concordance",
  "condition_features": ["X1", "X2"],
  "candidate_outcomes": ["y1", "y2", "y3", "y4"],
  "gold": "argmax_y P_dev(y|X)",
  "development_patient_split_hash": "...",
  "validation_statistics": {"n_x": 0, "probability_gap": 0, "stability": 0},
  "rule_version": "..."
}
```

群体规则必须只在 development 患者上估计，阈值和排序先冻结，再在独立 validation 患者上验证稳定性。最终题的 gold 是冻结规则的 argmax，而不是某一病例实际做过的检查。若题干使用合成特征，它只能声称测量“数据中最可能的实践模式”。

### 4.2 推荐流水线

```text
定义构念与临床场景
  → 先按 subject_id 冻结 dev / validation / final-test
  → 建立逐表 event_time / recorded_time / available_time
  → 分支：生成单患者 decision snapshot，或仅用 development 患者挖掘 rule manifest
  → 从 EHR 抽取候选目标（只作候选，不自动成为规范性 gold）
  → 冻结 gold 与理由
  → 构造同层级干扰项
  → LLM 只负责受约束的题干表述
  → 自动 schema / 隐私 / 时间 / 语义泄漏检查
  → 双临床专家独立审核，分歧由第三人裁决
  → 小规模作答试验与题项分析
  → 冻结测试集和版本化 manifest
```

关键顺序是“先定 gold 和选项，再生成题干”。如果让生成模型同时决定病例、答案和干扰项，无法区分模型语言错误、医学裁定错误和源数据错误。

## 5. 五个维度的出题蓝图

### 5.1 检查检验选择

| 设计项 | Pattern/rule-concordance | Encounter next-event prediction | Clinical-best-decision |
|---|---|---|---|
| 题干 | “具有特征 X 的患者最可能被选择哪项检查？” | “该患者下一项最可能被开立的检查是什么？” | “当前最应优先进行哪项检查？” |
| 证据单元 | 合成/标准化特征 X + 冻结 rule manifest | 单一 encounter 的 decision snapshot | 单一或合成病例 snapshot + 证据包 |
| 时点 | X 的每项特征必须在目标行为前可得；统计窗口预先固定 | triage/首次评估后、首个目标检查医嘱前 | 形成初始鉴别诊断后、目标检查前 |
| Gold | 仅由 development 患者估计的 `argmax_y P(y\|X)`，且需独立 validation 稳定性门禁 | 目标窗口内该病例首个有效且未取消的 POE/实验室/影像医嘱 | 冻结指南或临床路径 + 两名相关专家独立裁定 |
| 必须隐藏 | 规则统计值和目标名称不进题干；test 患者不得参与规则估计 | 后续检查名称/结果、诊断、治疗、出院小结 | 同左，并隐藏实际开立行为，避免专家被历史行为锚定 |
| 排除 | 样本量不足、概率差/稳定性不足、validation 排序反转、X 含后验特征 | 同时开立多个不可排序检查；订单取消/重复；可用时间不明 | 多个检查同等合理；缺少过敏、妊娠、肾功能或病情稳定性等会改变答案的信息 |

当前项目的检查题已明确采用行为预测语义，且具体实现是 **pattern/rule-concordance**。其 gold 正是冻结规则中条件概率最高的检查，不要求该检查在某个被描述的合成“患者”身上实际发生。只有另行建立 encounter next-event 子任务时，gold 才改为病例级下一项有效行为。两种子任务都属于行为轨道，但标签单位、可复现证据和可作出的结论不同。

### 5.2 临床诊断

| 设计项 | 建议 |
|---|---|
| 构念 | 优先做“在当前证据下的最可能诊断”；若做行为轨道，应明确命名为“随后记录/编码的诊断” |
| index time | 主诉、查体和指定关键检查结果均已可用，但首次明确诊断记录之前 |
| 可见信息 | 症状、体征、相关既往史、否定信息、关键实验室/影像结果；每项必须在时点前可用 |
| Gold | ICD/ED diagnosis/出院诊断只用于候选筛选；专家需判断这些可见证据是否足以支持唯一诊断，并排除“仅住院后期才成立”的编码 |
| 干扰项 | 同一器官系统、相似表现、在当前证据下可鉴别但被某项关键信息削弱的诊断 |
| 排除 | 仅有症状码、规则外诊断、并存诊断无法确定主问题、影像/病理证据在 index time 后才出现、编码与临床文书冲突 |

诊断题应区分“诊断推理”和“编码预测”。后者可自动生成更多题，但不能据此声称评估临床诊断能力。每个规范性诊断 gold 至少要有一条正向关键证据和一条能区分最强干扰项的证据。

### 5.3 治疗与处置

| 设计项 | 建议 |
|---|---|
| 子任务 | 药物治疗、操作/手术、支持治疗、观察/住院、紧急处置应分别标记；不要在一个选项集合中混合不可比较层级 |
| index time | 诊断或工作诊断已经形成，目标治疗医嘱之前 |
| 可见信息 | 严重度、过敏、妊娠、肝肾功能、当前药物、既往失败治疗、治疗目标；缺一项可能改变答案即排除 |
| 行为 gold | 明确选择 POE（开立）、prescription（处方）或 eMAR `Administered`（实际给药）之一；不得混用 |
| 规范性 gold | 当前版本指南/路径 + 专家裁定；实际治疗仅作为候选和真实性核查，不作为决定性证据 |
| 干扰项 | 同一治疗阶段的合理替代；每个错误项应有明确不优理由（禁忌、时机、谱过宽/窄、剂量/途径不当等） |
| 排除 | 需要床旁判断但数据缺失；多个指南允许等价方案；舒适治疗/目标治疗受患者偏好影响但偏好未记录；医嘱与执行状态冲突 |

这类题的风险最高，因为历史治疗行为同时受适应证和患者严重度影响。仅凭“患者后来用了药 X”不能推断 X 是当时最佳方案，更不能由后续结局反向证明。

### 5.4 转诊与科室选择

先拆清题目到底问哪一种动作：

1. 紧急分流（立即急诊、普通门诊、急救团队）；
2. 专科会诊（consult）；
3. 住院负责服务（`services.curr_service`）；
4. 物理病区/床位转移（`transfers.careunit`）；
5. 院外转介或出院去向。

| 设计项 | 建议 |
|---|---|
| index time | 会诊/收治/转运订单前，且关键诊断与严重度证据已可用 |
| 行为 gold | 与题目子任务一致的 POE consult、`services.curr_service` 或转运事件；物理位置不得替代负责专科 |
| 规范性 gold | 专科能力需求、紧急程度和当地服务路径联合裁定；MIMIC 的美国单中心路径不能直接作为香港服务体系的规范性 gold |
| 干扰项 | 同一服务层级的相邻专科；如果正确答案是“急性卒中团队”，其他项也应是可比较的急性服务，而不是皮肤科等显然无关项 |
| 排除 | 因床位短缺发生的非理想去向、多个团队共同管理、仅从物理位置推断专科、当地转诊路径未定义 |

如果目标是香港临床 benchmark，必须增加香港本地服务目录和路径审核。MIMIC 可提供病例表型，但不能证明香港应该转到哪个科室或服务层级。

### 5.5 离院指导与随访

| 设计项 | 建议 |
|---|---|
| 子任务 | 用药延续、复查/复诊、自我监测、活动/饮食、伤口护理、危险信号应分别标记；单题只问一个决策 |
| index time | 治疗完成或病情稳定、已满足离院条件，但出院指导文本尚未可见 |
| 可见信息 | 最终诊断、关键治疗、治疗反应、离院状态、必要的社会/功能因素；只使用在当时已知的信息 |
| 行为 gold | 出院记录中的实际指导适合做“文书内容预测/检索”，不自动代表最佳随访 |
| 规范性 gold | 疾病/操作相关指南、药物安全要求、当地随访路径 + 专家裁定；实际说明用于发现真实表达和遗漏模式 |
| 干扰项 | 同一管理目标的近似建议，错误原因应是时间、频率、阈值、持续时间或安全性不当 |
| 排除 | 文书模板化且无患者特异性、离院稳定性不明、复诊资源依赖但当地路径未定义、多个建议被打包导致部分正确 |

出院小结本身包含住院病程和指导，是该维度的答案源，同时也是前四维最严重的未来信息泄漏源。它不能出现在前四类题的模型输入中。

## 6. Gold label 构建规则

### 6.1 行为轨道包含两个不可混用的子任务

#### A. Pattern/rule-concordance

1. 先按 `subject_id` 冻结 development / validation / final-test；
2. 只在 development 患者上估计 `P(y|X)`、baseline、lift、置信区间、稳定性和候选排序；
3. 预先冻结样本量、概率差、排名稳定性与可重复性门槛；
4. 在 validation 患者上确认 argmax 排名和效应方向稳定，失败的规则拒绝；
5. 题目 gold 固定为通过门禁的 development argmax，不用 validation/test 重新选答案；
6. 最终解释只声称“群体历史实践中最可能的选择”，不声称病例级下一事件或医学最佳。

#### B. Encounter next-event prediction

Gold 必须来自病例级事件。建议按以下顺序确定：

1. 在 `index_time` 后的预定义 target window 内检索与任务一致的事件；
2. 去除取消、重复、无效状态和纯行政事件；
3. 如果同一时点有多个并列动作且临床上无法排序，拒绝该题；
4. 保存事件 ID、事件类型、订单状态和时间证据；
5. 题干固定使用“最可能被记录/选择/开立/实施”，答案解释只陈述历史数据标签，不声称医学最佳。

两者不能混名、混题或混分：pattern/rule-concordance 的一题对应一条群体规则，next-event 的一题对应一个 encounter snapshot。

### 6.2 规范性轨道

采用“证据包 + 独立裁定”：

- 一名方法学人员先冻结可见病例和候选选项；
- 两名具备相应场景经验的临床专家独立选择最佳答案并写出决定性理由；
- 专家看到指南版本和当地路径，但初审时不看实际 EHR 行为，避免锚定；
- 一致则进入下一步；不一致由第三名资深专家裁决；
- 若分歧来自题干缺信息或确有两个合理答案，必须改题或删除，不能靠多数票掩盖歧义；
- 每题记录 `guideline_version`、证据页/条款、专家角色、独立答案、分歧原因和最终决定。

“Hybrid”只允许表示：EHR 事件生成候选 gold，专家和指南重新判断后形成规范性 gold。它不能表述为“真实行为已经被医学验证”，除非审核明确完成。

## 7. 选项与干扰项

### 7.1 构造顺序

1. 先冻结唯一 gold；
2. 从同一任务本体/术语层级召回 6–10 个候选干扰项；
3. 依据病例事实筛除同义词、包含关系、部分正确项和禁忌信息不足项；
4. 选 3 个代表不同错误机制的干扰项；
5. 统一长度、语法、粒度和具体程度；
6. 确定性均衡 A–D 位置；
7. 临床专家逐项说明“为什么合理但不最佳”。

### 7.2 干扰项来源

- 诊断：同器官/相似表型的鉴别诊断；
- 检查：同一诊断阶段可考虑、但不能最先解决当前问题的检查；
- 治疗：同一适应证附近但因时机、禁忌或强度不合适的方案；
- 转诊：同一服务层级的相邻专科/团队；
- 离院：同一管理目标但频率、时限或危险信号阈值错误的建议。

禁止使用“明显荒谬的跨系统选项”、绝对词提示、最长选项提示、语法不一致和重复题干关键词。若无法得到 3 个功能性干扰项，拒绝候选题；不要为了四选项格式填充无效项。EHRNoteQA 的临床修改流程和医学 MCQ 实证研究都说明，干扰项质量是主要人工成本，而不是生成答案本身。

此外，A–D 均衡不能消除模型自身的选项 ID 偏好。开发集应抽样运行所有 24 种选项排列；正式结果至少报告原排列准确率、随机重排准确率以及同一道题在多种排列下答案内容是否一致。若模型输出自由文本，应先稳定解析为答案内容，再映射到字母，避免解析器放大位置偏差。

## 8. Future leakage 与数据拆分

### 8.1 三层泄漏检查

| 层级 | 检查内容 | 例子 |
|---|---|---|
| 时间泄漏 | `available_time` 是否晚于 index time | 结果采样早但报告签署晚；出院编码晚于诊断题时点 |
| 语义泄漏 | 文本是否直接或间接暴露 gold | “已计划 PCI”“最终诊断为…”“转神经科后…” |
| 身份/划分泄漏 | 同患者、模板或近重复文本是否跨 split | 同一 `subject_id` 多次住院分别进入训练和测试；同一出院模板近重复 |

自动检查至少包括：目标及同义词匹配、否定/历史/计划状态、章节黑名单、日期与状态词、文本近重复、答案长度/位置偏差、源行时间审计。自动通过后仍需专家检查“临床上已经等价泄漏但字面未出现”的线索。

### 8.2 拆分顺序

- 第一原则：按 `subject_id` 分组拆分，患者不能跨集；
- 所有表型规则、术语频率、干扰项库、提示词调试和自动阈值只在 development 患者上完成；
- final test 在流程冻结后才生成/裁定，禁止反复查看后调规则；
- 相同文书模板或高度近重复病例要做 group-aware 去重；
- 若做时间外推，MIMIC 的跨患者去标识日期不能直接按显示年份排序；应使用官方 `anchor_year_group` 等可解释的真实年代映射做粗粒度时间划分，并保持患者互斥；
- 主结果用患者聚类 bootstrap 置信区间，避免同一患者多题被当作完全独立样本。

## 9. 临床审核与质量门禁

### 9.1 自动门禁

每题必须全部满足：

- schema 完整且恰好一个 gold；
- 病例题的 snapshot 可追溯且所有可见事实在 index time 可用；规则题的 rule manifest 可追溯且未使用 validation/test 重新选 gold；
- gold 与题干构念一致；
- 四个选项唯一、同层级、非同义；
- 题干和解释无答案泄漏、PHI、`___`、精确日期和高原文重合；
- 无两个选项同时部分正确；
- 行为题明确使用行为措辞，规范题明确使用“最佳/优先”措辞；
- 任何生成、审核或来源不完整均 fail closed，不进入 gold。

### 9.2 人工审核表

两名专家独立回答以下布尔项并给置信度：

1. 这是该临床场景中真实会问的问题；
2. 题干信息在 index time 可得；
3. 信息足以确定一个最佳答案；
4. gold 医学正确且与构念一致；
5. 三个干扰项合理但不优；
6. 没有遗漏会改变答案的安全信息；
7. 没有未来、后验或措辞泄漏；
8. 语言和当地临床路径自然；
9. 病例未通过罕见组合重建真实患者；
10. 建议 `accept / revise / reject`。

报告每维的原始一致率、Cohen's kappa（两评者）或多评者适用统计量，并同时列出分歧类别。Kappa 不能替代逐题消歧；高一致率也不能证明指南本身正确。

## 10. 试点方案：每维 100 道候选题

### 10.1 两阶段 pilot

**阶段 A：构建可行性**

- development 患者中每维抽取至少 150–200 个候选证据单元（病例题为 snapshot，群体检查题为 rule manifest）；
- 自动生成 100 道候选题；
- 全量双专家独立审核；
- 记录候选到 gold 的漏斗，而不是只报告最终数量。

**阶段 B：测量学试验**

- 由不同年资/专科的临床医生和若干非临床对照完成题目；
- 专家不得参与自己审核过题目的作答评估；
- 同时评估代表性通用 LLM、医疗 LLM和简单基线；
- 预注册主指标、排除规则和统计方法。

### 10.2 必报指标

| 类别 | 指标 |
|---|---|
| 构建效率 | snapshot/rule 合格率、候选生成成功率、自动拒绝率、专家修改率、最终接受率；按稳定错误码统计 |
| Gold 可靠性 | 专家原始一致率、kappa、第三人裁决率、无唯一答案率、低置信度率 |
| 泄漏与隐私 | 时间泄漏率、语义泄漏率、近重复率、PHI/占位符命中率；正式 gold 目标为 0 |
| 题项质量 | 难度（p-value）、点二列相关/区分度、每个干扰项选择率、非功能干扰项比例 |
| 模型表现 | 每维 accuracy 与患者聚类 bootstrap 95% CI；宏平均仅作辅指标；拒绝/不确定若允许需单列 |
| 人类参照 | 相关专科专家、普通临床医生、低年资医生分层表现；不能只用单一“医生平均分” |
| 覆盖与公平性 | 疾病系统、急缓程度、场景、年龄/性别等预定义亚组覆盖与表现；小样本只描述不作过度推断 |
| 稳健性 | 改写题干、打乱答案位置、移除非决定性信息后的分数变化；相同临床事实不应因表面形式大幅波动 |

### 10.3 Pilot 的建议停止条件

任一维满足以下条件时不扩容，先修复根因并重做该维：

- 专家认为无唯一最佳答案的比例 >10%；
- 自动或人工发现任何未解释的未来信息泄漏；
- 专家独立一致率 <80% 或 kappa <0.60；
- >20% 题目含至少一个无人选择的明显无效干扰项；
- 某个答案位置、题干长度或关键词可以显著预测 gold；
- 选项内容不变而仅调整 A–D 位置时，模型答案内容出现不可接受的系统性变化；
- 超过 10% 题目的 gold 依赖题干未提供的禁忌证、资源条件或当地路径；
- 临床专家表现不能稳定高于不具备相关训练的对照，提示题目可能在测语言线索或数据集特征而非目标构念。

这些阈值是项目 pilot 的预注册起点，不是来自单一文献的普适标准；完成首轮后应依据分布和错误审计冻结正式阈值，不能为提高产量而事后降低门槛。

## 11. 总分、可靠性与构念效度

五维代表临床流程中的不同决策，不应默认它们构成单一潜变量。正式发布前：

1. 每维独立报告准确率和可靠性；
2. 只有在相关结构、因子分析或概化研究支持时才发布一个总分；
3. 若发布宏平均，明确它是人为等权汇总而非经验证的“总体临床能力”；
4. 比较模型排名与临床专家分层表现，检验已知组效度；
5. 检验同一构念不同表述/病例间的一致性，以及行为轨道与规范轨道之间的相关程度；
6. 用错误类型（遗漏危急情况、错误治疗、错误转诊、危险出院建议）补充准确率，不能把所有错误视为等价。

构念效度证据应覆盖：内容蓝图是否代表目标临床活动、作答过程是否需要目标推理、内部题项结构是否合理、与外部临床参照是否符合预期、错误使用分数会产生什么后果。一个模型分数“有区分度”并不自动证明 benchmark 测到了临床能力。

## 12. 与当前项目文档的差距

对 `mcq_generation/question_types.md`、`mcq_generation/mcq_generation_design.md` 和 `docs/design/raw-archive-cleaning-standardization.md` 的对照结论：

### 已具备的正确基础

- 五类题型和字段白名单已初步定义；
- 检查题已明确 RWD 行为预测语义；
- 已提出 raw → cleaned → normalized → dynamic view 的分层；
- 已要求 `available_time`、后验排除、患者级 split、人工批准和 fail-closed gold；
- 已要求固定选项、确定性答案位置、审计和复现 manifest。

### 必须补齐的设计决策

1. **全局构念不一致**：检查题测真实行为，其他四维文本仍倾向“最佳决策”；必须拆轨或统一构念。
2. **行为子任务命名仍需锁定**：当前检查题是 pattern/rule-concordance，允许用标准化/合成 X 表述群体规则；若未来新增病例级 next-event，必须改用单 encounter snapshot 和实际事件 gold，不能沿用同一名称或分数。
3. **诊断标签需降级为候选**：出院/ED ICD 是后验计费信息，不能直接作为早期诊断真值。
4. **治疗事件需分层**：POE、处方、实际给药和手术/操作必须指定一个可审计目标事件。
5. **转诊概念需拆分**：负责团队、会诊和物理位置不能共用一个标签空间。
6. **离院题需拆单一目标**：药物、复诊、监测、生活方式和危险信号不能打包成一个“全都正确”的长选项。
7. **规范性证据链未定义**：需增加指南版本、当地路径、双专家独立裁定和第三人仲裁。
8. **测试集治理需前移**：患者 split 必须在规则挖掘、干扰项统计和提示词调试之前冻结。

## 13. 推荐实施顺序

1. **先完成检查题 pattern/rule-concordance pilot**：验证 development-only 规则估计、独立 validation 稳定性、rule manifest、泄漏和干扰项机制；不要把它改造成 encounter next-event。
2. **第二个做诊断规范题**：ICD 只筛病例，建立专家裁定流程；这一步能检验规范性 gold 的成本和一致性。
3. **第三个做治疗题**：先限定一个病种/治疗阶段，确保禁忌证字段齐全，再扩展。
4. **第四个做离院题**：按单一管理目标拆题，建立指南证据包。
5. **最后做转诊题**：必须先冻结目标地区的服务目录和本地路径；否则最容易把单中心组织结构误当医学知识。

扩容前的正式交付物应包括：任务规范、逐表时间语义、患者 split manifest、每题 snapshot、gold adjudication 记录、泄漏报告、题项分析报告和版本化 release manifest。

## 14. 局限

- MIMIC 主要来自美国单一学术医疗中心，ICU/住院人群与香港或普通门诊人群不同；行为模式和转诊结构不可直接外推。
- 回顾性 EHR 只记录被执行和被文书化的部分临床过程；“没有记录”不等于“没有考虑”。
- 出院小结是高信息密度但强后验的文书，容易把检索能力伪装成早期临床推理。
- 专家裁定也会受专科、资历、当地资源和指南差异影响；需要记录分歧而非只保存最终答案。
- MCQ 强制唯一答案，会舍弃真实临床中的并行处置、共享决策和不确定性。应在论文中把 benchmark 定位为受控决策切片，而非完整临床能力替代品。
- 五维各 100 道只足够验证可行性和发现系统性缺陷，不足以稳定覆盖大量疾病与亚组；扩大样本应由 pilot 的接受率和测量误差决定。

## 15. 主要参考文献

1. Johnson AEW, et al. [MIMIC-IV, a freely accessible electronic health record dataset](https://doi.org/10.1038/s41597-022-01899-x). *Scientific Data*. 2023.
2. Johnson A, et al. [MIMIC-IV v3.1](https://doi.org/10.13026/kpb9-mt58). PhysioNet.
3. Johnson A, et al. [MIMIC-IV-Note v2.2](https://doi.org/10.13026/1n74-ne17). PhysioNet. 2023.
4. Johnson A, et al. [MIMIC-IV-ED](https://doi.org/10.13026/77z6-9w59). PhysioNet.
5. Harutyunyan H, et al. [Multitask learning and benchmarking with clinical time series data](https://doi.org/10.1038/s41597-019-0103-9). *Scientific Data*. 2019.
6. Suresh H, et al. [A framework for understanding label leakage in machine learning for health care](https://pmc.ncbi.nlm.nih.gov/articles/PMC10746313/). *Journal of the American Medical Informatics Association*. 2024.
7. Lehman E, et al. [Learning to Ask Like a Physician](https://doi.org/10.18653/v1/2022.clinicalnlp-1.8). ClinicalNLP. 2022.
8. Kweon S, et al. [EHRNoteQA: An LLM Benchmark for Real-World Clinical Practice Using Discharge Summaries](https://proceedings.neurips.cc/paper_files/paper/2024/file/e15c4afff22f12c4986c1fcb4e941e03-Paper-Datasets_and_Benchmarks_Track.pdf). NeurIPS Datasets and Benchmarks. 2024.
9. Alaa A, et al. [Medical Large Language Model Benchmarks Should Prioritize Construct Validity](https://proceedings.mlr.press/v267/alaa25a.html). ICML. 2025.
10. Rodriguez MC. [Three options are optimal for multiple-choice items: a meta-analysis of 80 years of research](https://doi.org/10.1111/j.1745-3984.2005.00006.x). *Educational Measurement: Issues and Practice*. 2005.
11. Hager P, et al. [Evaluation and mitigation of the limitations of large language models in clinical decision-making](https://doi.org/10.1038/s41591-024-03097-1). *Nature Medicine*. 2024.
12. Gaber F, et al. [Evaluating large language model workflows in clinical decision support for triage and referral and diagnosis](https://doi.org/10.1038/s41746-025-01684-1). *npj Digital Medicine*. 2025.
13. Ma MD, et al. [CliBench: A Multifaceted and Multigranular Evaluation of Large Language Models for Clinical Decision Making](https://arxiv.org/abs/2406.09923). arXiv. 2024.
14. Xie Y, et al. [EHRBench: An Automated and Reliable EHR-based Benchmark for Clinical Decision Making with LLMs](https://arxiv.org/abs/2605.30637). arXiv preprint. 2026.
15. Zheng C, et al. [Large Language Models Are Not Robust Multiple Choice Selectors](https://proceedings.iclr.cc/paper_files/paper/2024/hash/54dd9e0cff6d9214e20d97eb2a3bae49-Abstract-Conference.html). ICLR. 2024.
16. Reuel A, et al. [BetterBench: Assessing AI Benchmarks, Uncovering Issues, and Establishing Best Practices](https://doi.org/10.52202/079017-0685). NeurIPS Datasets and Benchmarks. 2024.
17. Ayre J, et al. [The quality and safety of using generative AI to produce patient-centred discharge instructions](https://doi.org/10.1038/s41746-024-01336-w). *npj Digital Medicine*. 2024.
