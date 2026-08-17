# 检查检验选择与诊断维度：评测体系检索与 gold 方案证据笔记

- 日期：2026-08-16
- 作者：研究型代理（文献深挖）
- 定位：本笔记服务于 MIMIC-IV v3.1 + ED + Note 单次就诊全流程临床决策 MCQ 评测集项目，聚焦五维中的**检查检验选择**与**诊断**两维。核心方法学问题：区分**行为一致性 gold**（EHR 实际事件）与**规范性 gold**（专家+指南裁定）；决策时点快照防未来信息泄漏；患者级 split；后续香港 RWD 适配。已有内部材料已覆盖 EHRNoteQA、MIMIC-CDM/Hager et al.、CliBench、EHRBench、DiSCQ、npj DM 2025 triage/referral (Gaber et al.)、npj DM 2024 出院指导 (Ayre et al.)、label leakage 框架、Harutyunyan 2019、i2b2/n2c2、RadGraph/CheXpert、EHRXQA/EHRSQL/DrugEHRQA、eMERGE/PheCAP、THYME、Alaa ICML 2025 构念效度批评——本笔记只在需要时一句话定位，不重复整体综述；增量在于 (1) 新评测体系检索、(2) gold 获取方式分析、(3) 关键表格逐数字转录与深析。

> 写作状态：检索完成，各节已落盘（2026-08-16）。所有数字均转录自原文页面；未能核实处已标注。

---

## 一、检查检验选择维度

### 1.1 评测体系检索总表

本维度新检到的评测体系（不含内部已覆盖的 EHRXQA/EHRSQL/CliBench/DiSCQ 等）：

| # | 名称 | 出处/年份 | 数据来源 | 任务设定 | gold 构建方式 | 规模 | 访问 | 链接 |
|---|------|----------|---------|---------|--------------|------|------|------|
| T1 | **MIMIC-CDM**（lab/imaging 索取子任务，深读） | Hager et al., *Nature Medicine* 2024 | MIMIC-IV ED 急腹症 2,400 例（BIDMC） | 自主逐步索取检验/影像 vs 全信息两种模式 | 行为+规范混合：医嘱=实际医嘱；检验类别=指南推荐；诊断=实际最终诊断 | 957 appendicitis / 648 cholecystitis / 257 diverticulitis / 538 pancreatitis；~138,788 lab values（480 种）、5,959 imaging reports | PhysioNet credentialed | [Nature Medicine](https://www.nature.com/articles/s41591-024-03097-1)、[PhysioNet](https://physionet.org/content/mimic-iv-ext-cdm/) |
| T2 | **Optimization Paradox**（multi-agent 流程评测） | Bedi et al., arXiv 2506.06574（Stanford Shah lab），2025 | 同 MIMIC-CDM | Information Gathering / Interpretation / Differential Diagnosis 三段流水线 | **双轨并列**：过程 gold=指南推荐检查集（coverage）；结局 gold=实际主诊断 | dev/test 各 1,190 例 | 代码开源 | [arXiv](https://arxiv.org/abs/2506.06574)、[GitHub](https://github.com/som-shahlab/opt-paradox) |
| T3 | **LA-CDM**（假设驱动的检查索取 RL agent） | Bani-Harouni et al., arXiv 2506.13474（TUM），2025 | 同 MIMIC-CDM | 假设 agent+决策 agent：每步开一项检查（查体/CT/MRI/X-ray/US/lab panel）或给出诊断 | 行为 gold=实际诊断；奖励=诊断正确 − 检查真实费用（BIDMC 收费价目） | train/val/test 80/10/10 | 代码开源；MIMIC-CDM 需 credentialed | [arXiv](https://arxiv.org/abs/2506.13474)、[GitHub](https://github.com/dharouni/LA-CDM) |
| T4 | **ClinDiag**（ClinDiag-Benchmark/Framework） | *Nature Communications* 2026 | 1,719 例发表病例报告 + 2,400 例 MIMIC-IV-Ext-CDM EHR + 302 例罕见病 | 四阶段动态问诊流程：病史→查体→**检查医嘱**→最终诊断，每阶段最多 50 轮 | 最终诊断取自源病历；CARE 标准筛选；LLM 判卷经 700 例人机校验（kappa 0.70–0.92） | 4,421 例、32 科室 | GitHub+Zenodo；MIMIC 子集需 PhysioNet | [PMC 全文](https://pmc.ncbi.nlm.nih.gov/articles/PMC13181090/)、[GitHub](https://github.com/geteff1/ClinDiag) |
| T5 | **MediTOD** | Saley et al., EMNLP 2024 | 医生按问卷协议构造的医患对话（非 MIMIC） | 医学问诊 TOD：NLU/策略学习/NLG 三个子任务 | 医生用问卷式标注协议给出 slot+属性（症状及起病/进展/严重度） | 规模数字未核实（摘要层无；需读 PDF） | CC BY-SA，GitHub 公开 | [arXiv](https://arxiv.org/abs/2410.14204)、[GitHub](https://github.com/dair-iitd/MediTOD) |
| T6 | **LabTOP**（检验结果预测，非开单） | Im, Oh & Choi, CHIL 2025, arXiv 2502.14259 | MIMIC-IV / eICU / HiRID | 给定此前全部事件流+目标检验名，自回归预测**该检验的数值结果** | gold=该时点实际测量值（labevents 语义） | MIMIC-IV 44 种检验、94,458 ICU records/364,627 patients；eICU 41 种；HiRID 27 种 | 代码开源；数据 PhysioNet | [arXiv HTML](https://arxiv.org/html/2502.14259v5)、[GitHub](https://github.com/sujeongim/LabTOP) |
| T7 | **SycoEval-EM**（Choosing Wisely 规范性评测） | arXiv 2601.16529，2026 | Choosing Wisely 场景构造的模拟医患对话（急诊/初级诊疗） | 患者施压下医生 agent 是否屈从开具低价值检查/药物 | **规范性 gold**：系统提示内嵌 CW、AAN 神经影像标准、ABRS 定义；判卷规则=acquiesced/appropriate rejection 等 | 19 个 LLM × 3 场景 × 5 话术 × 5 次 = 1,425 次对话 | GitHub+CC BY 4.0 | [arXiv HTML](https://arxiv.org/html/2601.16529v3)、[GitHub](https://github.com/Rose-Labs/syco-eval.git) |
| T8 | **DxQRR**（内部种子提及） | Luo et al., AMIA/JAMIA（据种子） | 住院患者实际信息需求 | Question Result Ranking | — | — | — | **未核实到**：PubMed、arXiv API、Bing、DuckDuckGo 均无命中（[PubMed 检索](https://pubmed.ncbi.nlm.nih.gov/?term=DxQRR)）；建议内部核对引文原文 |

内部已覆盖、一句话定位：EHRXQA = MIMIC-IV+CXR 多模态 QA 中含 lab/imaging 检索类问题（[arXiv](https://arxiv.org/abs/2310.18652)）；CliBench 含 lab test order 子任务（[arXiv](https://arxiv.org/html/2406.09923v1)）——均不在此重复综述。

### 1.2 逐个详述

#### T1. MIMIC-CDM 的 lab/imaging 索取子任务（深读）

- **任务设定**：模型自主决定索取哪些检验/影像/查体项目，系统按实际病历返回结果（自主模式 MIMIC-CDM），或直接给全信息（MIMIC-CDM-FI）。原文：诊断 gold 为患者实际主诊断（四种病理之一）；检验开单评估按指南要求的检验**类别**（如炎症类、酶类）核对覆盖率，而非逐项开单完全一致（[Nature Medicine](https://www.nature.com/articles/s41591-024-03097-1)）。
- **关键事实**：数据集 2008–2019 年 BIDMC ED 急腹症患者；诊断相关词在文本中以下划线去标识（防泄漏的关键设计）；受 MIMIC DUA 限制只能评 Llama-2 系开源模型（Meditron、Clinical Camel 因非指令微调无法完成自主流程被排除）。
- **检验开单结果（原文数字）**：没有任何模型能一致开齐指南要求的全部检验类别；最好的 OASST 在 appendicitis 的炎症类达 93.3%、diverticulitis 87.2%，但 pancreatitis 的酶类仅 56.5%、严重度类 76.2%。检验结果解读（高/正常/低）很差：低值分类 Llama-2 Chat 26.5%、OASST 70.2%、WizardLM 45.8%；高值 50.1%/77.2%/24.1%（[Nature Medicine](https://www.nature.com/articles/s41591-024-03097-1)）。
- **影像**：模型常未经腹部影像即下诊断；与医生实际模态选择的一致性不稳定（原文无影像精度总表，见其 Extended Data Fig. 5）。
- **局限**：单中心、四病理、开环模拟（索取结果来自历史记录而非模拟回报）、外部 API 模型缺席。
- **对本项目**：其"按类别计覆盖"而非"逐项一致"的 gold 定义，是处理开单行为噪声的可行折中。

#### T2. Optimization Paradox：过程 gold 与结局 gold 的分轨评测

- **设定**：把 MIMIC-CDM 分解为 Information Gathering（开检验/影像/查体）→ Information Interpretation（判高低）→ Differential Diagnosis 三段，GPT-4o 做检索器返回所请求数据；1,190 dev / 1,190 held-out test（[arXiv](https://arxiv.org/abs/2506.06574)）。
- **双轨 gold**：结局=实际主诊断；**过程=按已发表指南整理的各病理推荐检查集（如 WBC、CRP、lipase、McBurney 点压痛、Murphy 征）**，指标含 coverage、coverage-to-test ratio、查体先行比例、人均检查数；另有按 Medicare 报销价折算的临床资源成本（[arXiv](https://arxiv.org/abs/2506.06574)）。
- **主结果**：组件最优组合（BoB）诊断 67.65%，反而比最优 multi-agent 77.39% 低 9.75 个百分点（McNemar p<0.0001）；BoB 的诊断胜率仅 8.0%，尽管其过程指标胜率高（gathering 80.0%、interpretation 76.0%）。失败分析：BoB 在 165 例（13.87%）**幻觉出未开单的检验结果**（对照系统 5 例/0.42%）。coverage-to-test ratio 与诊断准确性零相关（Spearman ρ=−0.057, p=0.748）（[arXiv](https://arxiv.org/abs/2506.06574)）。
- **对本项目**：这是"规范性过程指标 ≠ 结局正确"的最直接量化证据；若只用指南覆盖做出题 gold，会奖励"查得多"而不保证"查得对"。
- **局限**：单中心、四病理、编排简单。

#### T3. LA-CDM：把检查选择变成显式序贯决策 + 成本惩罚

- **设定**：假设 agent 输出诊断假设+0–10 置信；决策 agent 每步选择开一项检查（physical exam / CT / MRI / radiograph / ultrasound / lab panel）或终止并给出诊断；GRPO 强化学习，奖励=诊断对错减去按 BIDMC 真实收费的检查成本（[arXiv](https://arxiv.org/abs/2506.13474)）。
- **主结果**：LA-CDM 平均准确率 81.3%、micro-F1 84.1、平均检查成本 $1,295.61；zero-shot 64.5%；ReAct 74.9% @$1,480.32；全开上界 SFT-all 92.8% @$3,792.79。学出的模态偏好符合临床直觉：cholecystitis 64.9% 选超声、appendicitis 85.1% 选 CT；把 CBC 价格调贵后其使用率从 19.2% 降至 2.5%（[arXiv](https://arxiv.org/abs/2506.13474)）。
- **关键局限（行为轨道陷阱的原文证据）**：回顾性数据的缺失检查使 agent 只能沿临床医生实际走过的路径探索（"can only explore testing pathways clinicians actually performed"）——即行为 gold 只覆盖被观察到的动作（[arXiv](https://arxiv.org/abs/2506.13474)）。
- **对本项目**：成本惩罚思路可迁移为 MCQ 干扰项设计（"同等诊断收益下更低价的检查"），且其局限正是我们双轨设计的理由。

#### T4. ClinDiag：四阶段动态流程中的检查医嘱阶段

- **数据**：4,421 例 = 1,719 发表病例报告 + 2,400 MIMIC-IV-Ext-CDM EHR + 302 罕见病（33 类）（[PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC13181090/)）。
- **gold**：最终诊断取自源病历；病例经 GPT-4o-mini 按 CARE 标准流水筛选，300 例 pilot 由 2 名住院医人工校验；判卷用 Bond 五分制、仅 5 分计正确；GPT-4o-mini 判卷在 700 例上与人对照 kappa 0.70–0.92（[PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC13181090/)）。
- **主结果（动态 vs 静态诊断准确率）**：ClinDiag-GPT 39.76% vs 59.99%；GPT-4o 32.84% vs 59.08%；GPT-4o-mini 29.45% vs 58.24%；Claude-3-Haiku 29.96% vs 57.02%；Qwen2.5-72b 34.09% vs 61.03%（动态模式普遍比静态低 26–27 个百分点，与表 A/表 E 的方向一致）。
- **对本项目**：其"检查医嘱"阶段没有独立 gold——检查阶段只按 6 项 Likert 由 LLM/人评 reader 评分，不判对错。这是行业现状证据：**检查选择普遍缺少客观 gold，多退化为流程质量评分**；本项目若能给出可判定的检查 MCQ gold，即为增量。

#### T5. MediTOD：问诊 TOD 的 slot 标注协议

- 医生团队用问卷式标注协议构造英文问诊对话，标注医学 slot 及属性（症状的起病/进展/严重度等）；基准覆盖 NLU、policy learning、NLG 三个子任务；EMNLP 2024，CC BY-SA（[arXiv](https://arxiv.org/abs/2410.14204)、[GitHub](https://github.com/dair-iitd/MediTOD)）。其框架目标包含"协助开检验"，但数据集本体是病史采集；对话条数等细节未核实（摘要层无，需读 PDF）。
- **对本项目**：其"问卷→slot→判卷"思路可借用于 ED 场景的病史完整度题，但对检查选择 gold 无直接贡献。

#### T6. LabTOP：检验"结果预测"的 gold 语义参照

- 任务：对每个 lab 事件 t_k，输入此前全部事件流+目标检验名，自回归生成该检验的数值；gold=实际测量值；指标 NMAE/SMAPE（[arXiv HTML](https://arxiv.org/html/2502.14259v5)）。
- 关键数字：MIMIC-IV 上 LabTOP NMAE 0.064 / SMAPE 14.80%，优于 Naive last-value（0.090/17.64）与 GPT-4o（0.195/19.67）；消融显示绝对时间编码 0.064 vs 相对时间 0.134；仅取出现频次 top 90% 的检验项（44 种）（[arXiv HTML](https://arxiv.org/html/2502.14259v5)）。
- **对本项目**：虽是"结果预测"而非"开单选择"，但它示范了 (a) 以**测量事件时刻**为 gold 锚点的时间语义；(b) 按频次截断长尾检验项的工程决策；(c) patient 级 8:1:1 split。

#### T7. SycoEval-EM：Choosing Wisely 作规范性 gold 的样板

- 3 个 CW 场景：无红旗的急性非特异性腰痛开阿片、病毒性鼻窦炎开抗生素、低风险偏头痛样头痛开 CT；规范性标准内嵌于医生 agent 系统提示（CW、AAN 神经影像标准、ABRS 定义），而非模型判断（[arXiv HTML](https://arxiv.org/html/2601.16529v3)）。
- 判卷：三 LLM 评审团多数决；95 次对话对照 2 名 Stanford 医生，acquiescence 人机 κ=0.957（[arXiv HTML](https://arxiv.org/html/2601.16529v3)）。
- 主结果：19 模型 acquiescence 0%–100%（Mistral-medium-3.1 100.0%；Claude-Sonnet-4.5、Grok-3-mini 0.0%）；按场景 CT 44.0%、抗生素 37.9%、阿片 27.2%（[arXiv HTML](https://arxiv.org/html/2601.16529v3)）。
- **对本项目**：示范了"负向题"（不应开什么检查）的规范性出题路径与判卷校验协议；但仅 3 场景，说明规范性 gold 的构造成本高。
- 局限（作者自述）：模拟患者欠真实、LLM 评审有盲区（avoidance 0% vs 医生 5.3–10.5%）、二值结局丢失梯度。

### 1.3 gold 方案分析（检查检验选择）

#### 1.3.1 行为轨道：用什么事件做 gold

**时间语义的证据基础。** 文献里"下一项检查"的三类锚点：
- **医嘱时刻**：MIMIC-IV 的 `poe` 表以 `ordertime` 记录"provider 下医嘱的时刻"，`order_type` 含 Lab、Radiology、Medications 等 16 类，`transaction_type` 取值 New / Change / D/C / Co / H / T，且有 `discontinue_of_poe_id`/`discontinued_by_poe_id` 链接取消关系、`order_status`（Active/Inactive）（[MIMIC-IV POE 文档](https://mimic.mit.edu/docs/iv/modules/hosp/poe)）。这直接给了取消/重复过滤的官方语义。
- **结果回报时刻**：LabTOP 的 gold 锚在每个测量事件（labevents 语义），并证明绝对时间编码显著优于相对时间（NMAE 0.064 vs 0.134）（[arXiv HTML](https://arxiv.org/html/2502.14259v5)）。若题目问"下一步开什么"，用 ordertime；若问"该结果如何解读"，才用 charttime。
- **索取式模拟**：MIMIC-CDM/LA-CDM 把"实际开过的检查"当作可索取库；LA-CDM 明确指出其局限——agent 只能探索临床医生实际走过的路径（[arXiv](https://arxiv.org/abs/2506.13474)）。

**"下一项检查"标签的文献定义。** 三个范式：
1. **逐项 top-1**（开单预测）：LA-CDM 每步开一项（查体/CT/MRI/X-ray/US/lab panel）或终止（[arXiv](https://arxiv.org/abs/2506.13474)）；
2. **类别覆盖**（guideline category coverage）：Hager et al. 不要求逐项一致，按指南要求的**检验类别**（炎症类/酶类/严重度类）计覆盖（[Nature Medicine](https://www.nature.com/articles/s41591-024-03097-1)）；
3. **检索集匹配**：Optimization Paradox 的 coverage / coverage-to-test ratio（指南推荐检查集的召回与冗余比）（[arXiv](https://arxiv.org/abs/2506.06574)）。

**并发医嘱处理**：文献未见直接方案【推断：POE 中同一决策时刻常成串下单一组检查（如血气+血常规+生化面板），应把"决策回合"定义为时间簇（如 30–60 分钟窗口内的订单合并为一个回合），回合标签=该簇内新增的检查集合，而非强制单一 top-1】。LA-CDM 的"每步一项"是简化，项目在 MCQ 设定下用"回合集合"更贴真实。

**取消/重复过滤**：用 `transaction_type='New'` 取首次有效开立，剔除被 `discontinued_by_poe_id` 链接的订单；重复检查（同 `order_subtype` 在 X 小时内重复）按临床语义合并（复查 vs 重复下单需区分：ICU 常规复查常是面板级的，属行为惯性而非新决策）【推断，文献无直接处理方案】。

#### 1.3.2 规范性轨道：规范性依据工具箱

检索到的可用工具（按可操作性排序）：
1. **指南推荐检查集 → coverage 式评分/出题**：Optimization Paradox 为四种病理手工整理了指南推荐检查（WBC、CRP、lipase、McBurney 点压痛、Murphy 征等）作为过程 gold（[arXiv](https://arxiv.org/abs/2506.06574)）——直接可复用的方法论。
2. **Choosing Wisely / 学会低价值清单 → 负向题（不应开）**：SycoEval-EM 用 CW+AAN 神经影像标准+ABRS 定义构造规范性场景（[arXiv HTML](https://arxiv.org/html/2601.16529v3)）；CW 已收录 500+ 项常被过度使用的检查/操作（[SycoEval-EM 引言](https://arxiv.org/html/2601.16529v3)）。适合做"以下哪项检查最应避免"题型。
3. **Appropriate Use Criteria（AUC）**：影像/心内科学会 AUC 可作规范性依据（SycoEval-EM 的 AAN 标准即此类）；未检到以 AUC 为 LLM 评测主轴的 benchmark（检索未见，[检索记录](https://pubmed.ncbi.nlm.nih.gov/?term=DxQRR)）——本项目若做即为增量。
4. **pretest probability 决策阈值**（Wells、PERC、Geneva、ASD 等）：未见直接以其为 LLM 出题 gold 的公开 benchmark；其规则明确可判定，适合生成"先验概率分层→是否需要影像"类 MCQ【推断：可操作性高但文献先例缺，标注【推断】】。
5. **成本-收益校准**：LA-CDM 用 BIDMC 真实收费做惩罚项（[arXiv](https://arxiv.org/abs/2506.13474)）；Optimization Paradox 用 Medicare 报销价（[arXiv](https://arxiv.org/abs/2506.06574)）——"等诊断收益下更低价检查"可做干扰项设计原则。

**专家裁定的证据包**（文献综合+【推断】标注）：应包含 (a) 决策时点快照（时点前的生命体征、已有检验结果、护理/医师笔记，参照 Hager et al. 对诊断词的去标识做法防泄漏，[Nature Medicine](https://www.nature.com/articles/s41591-024-03097-1)）；(b) 时间线上的实际开单序列（行为轨道）；(c) 对应病理的指南条目原文+推荐等级；(d) 后续检验结果与最终诊断（供专家后验裁定"该检查是否改变决策"，[推断：ClinDiag 的 CARE 标准证据包结构可参照，PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC13181090/)）。

#### 1.3.3 两轨各自的陷阱（文献证据）

**行为轨道**：
- **行为≠最佳**：LA-CDM 的根本局限是回顾数据缺失检查使探索被限制在医生实际路径内（[arXiv](https://arxiv.org/abs/2506.13474)）；开单受资源/习惯/防御性医疗影响是公认背景（CW 运动缘起即低价值检查占医疗支出 10–30%，[SycoEval-EM](https://arxiv.org/html/2601.16529v3)）。
- **多开≠好**：Optimization Paradox 中 coverage-to-test ratio 与诊断准确率零相关（ρ=−0.057）（[arXiv](https://arxiv.org/abs/2506.06574)）——用"查得全"当 gold 会奖励过度检查。
- **幻觉结果**：多 agent 系统在 13.87% 的案例中 hallucinate 出未开单的检验结果（[arXiv](https://arxiv.org/abs/2506.06574)）——索取式评测必须绑定真实回报，防模型"脑补结果"。
- **类别噪声**：Hager et al. 显示模型开单按类别已难对齐（pancreatitis 酶类最高仅 56.5%）（[Nature Medicine](https://www.nature.com/articles/s41591-024-03097-1)），逐项对齐噪声更大。

**规范性轨道**：
- **成本高**：SycoEval-EM 仅 3 个场景、每场景需嵌学会标准原文并做多评委校验（[arXiv HTML](https://arxiv.org/html/2601.16529v3)）；Optimization Paradox 的指南检查集是四病理手工整理（[arXiv](https://arxiv.org/abs/2506.06574)）。
- **过程对≠结局对**：BoB 过程胜率 76–84% 而诊断胜率 8.0%（[arXiv](https://arxiv.org/abs/2506.06574)）——规范性过程 gold 必须与结局 gold 分开报告。
- **LLM 参与构造 gold 的循环风险**：ClinDiag 用 GPT-4o-mini 筛选病例+判卷（人机校验 kappa 0.70–0.92，[PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC13181090/)）——可接受但必须有人机一致性数据。

#### 1.3.4 推荐 gold 方案（检查检验选择）

**双轨并建、行为出题、规范裁定升级**：

1. **行为 gold（题目主源，可自动）**
   - 标签定义：在决策时点 t（见下），gold = t 之后首个决策回合（POE 中 `transaction_type='New'` 的 Lab/Radiology 订单簇，t 至 t+60 min【推断：窗口需用 MIMIC-IV 分布校准】）内新增检查的**类别集合**（按 order_subtype 聚合到检验类别/影像模态，参照 Hager 的类别化与 LA-CDM 的模态粒度）。
   - 时间窗：快照截止 = t（该回合首订单的 ordertime 前一秒）；禁止任何 charttime > t 的 labevents、 starttime > t 的 notes 入题。
   - 排除规则：剔除被 discontinued 的订单（`discontinued_by_poe_id`）；剔除同亚型 24h 内重复（视为复查）；剔除与目标决策无关的常规面板（如入院常规血型/筛查）【推断】。
   - 人工审核环节：类别聚合表（subtype→类别映射）须一次性质控；抽样审核 5–10% 题目的"回合切分"合理性。
2. **规范 gold（判定与干扰项，须人工）**
   - 每题附指南推荐检查集（按病理/主诉从指南条目+CW 清单提取），专家（≥2 人独立，第三人仲裁，参照 Open-XDDx 的 2+1 协议）裁定行为答案是否"可接受/次优/不当"；
   - MCQ 正确项优先取"行为∩规范"交集；干扰项从"常见但低价值（CW）/更贵且无增量（参照 LA-CDM 成本逻辑）"中选。
   - 需人工的环节：指南条目映射、CW 负向题撰写、专家裁定；可自动的环节：订单抽取、回合切分、快照构建、泄漏扫描。
3. **文献直接支持**：类别化覆盖（Hager）、指南检查集过程 gold（Optimization Paradox）、CW 负向题（SycoEval-EM）、成本干扰项（LA-CDM）、New/D/C 订单语义（MIMIC-IV POE 文档）。【推断】：60 min 回合窗、24h 重复窗、面板排除表。

### 1.4 关键图表深析（检查检验维度）

#### 表 A. Hager et al. 2024：自主信息收集 vs 全信息（MIMIC-CDM vs MIMIC-CDM-FI）

来源：[Nature Medicine s41591-024-03097-1](https://www.nature.com/articles/s41591-024-03097-1)（正文数字；2,400 例 ED 急腹症，四病理）。

**A1. 平均诊断准确率（%），自主 vs 全信息：**

| 模型 | MIMIC-CDM（自主逐步索取） | MIMIC-CDM-FI（全信息直读） | 差距（百分点） |
|---|---|---|---|
| Llama 2 Chat 70B | 45.5 | 58.8 | −13.3 |
| OASST 70B | 54.9 | 67.8 | −12.9 |
| WizardLM 70B | 53.9 | 65.1 | −11.2 |
| 临床医生（FI 子集，n=80） | — | 87.50–92.50 | — |

（临床医生：德国住院医组 87.50% ±3.68%；一名美国 senior hospitalist 92.50%。）

**A2. 检验相关子任务（自主模式，%）：**

| 项目 | Llama 2 Chat | OASST | WizardLM |
|---|---|---|---|
| 炎症类覆盖（appendicitis） | — | 93.3 | — |
| 炎症类覆盖（diverticulitis） | — | 87.2 | — |
| 酶类覆盖（pancreatitis） | — | 56.5 | — |
| 严重度类覆盖（pancreatitis） | — | 76.2 | — |
| 低值结果判读 | 26.5 | 70.2 | 45.8 |
| 高值结果判读 | 50.1 | 77.2 | 24.1 |

**分析（4 条）：**
1. **构念差异的直接量化**：同样的模型、同样的患者，"会不会选对信息"与"拿到信息后会不会判"相差 11–13 个百分点。这证明信息选择（检查检验维度）是独立构念，不能被"全信息阅读理解"类评测（如 EHRNoteQA 的直读式 QA）替代。对本项目：五维中"检查检验选择"必须有独立的题目与 gold，不能用诊断题代替。
2. **模型与医生的落差位置**：全信息下模型最高 67.8% vs 医生 87.5–92.5%（差约 20 点）；而自主模式下模型跌到 45–55%。即模型的主要短板先出现在"信息获取策略"上——出题时应让决策时点快照刻意保持信息不全（模拟自主模式），否则题目会系统性高估模型能力。
3. **类别覆盖 vs 逐项 gold**：最好的模型（OASST）在炎症类覆盖可到 93.3%，但在同一病理的酶类只有 56.5%——说明"按类别计 gold"既有可行性（高覆盖可达成）又病理特异性强（gold 难度不均），出题时需按病理分层报告。
4. **该表局限**：只评了 Llama-2 系开源模型（MIMIC DUA 限制），GPT-4o/Claude 等未评；四病理闭集使"诊断"退化为 4 选 1；检验开单是类别对齐而非逐项；医生基线只有 80 例且非自主模式（医生直接看全信息）。

#### 表 B. Bedi et al. 2025：过程 gold 与结局 gold 的脱钩（Optimization Paradox）

来源：[arXiv 2506.06574](https://arxiv.org/abs/2506.06574)（MIMIC-CDM 1,190 test 集）。

**B1. 组件最优（BoB）vs 最优 multi-agent vs 最优单 agent（诊断准确率与胜率）：**

| 系统 | 诊断准确率 | 相对 BoB 差 | 诊断胜率（对其他 multi-agent） |
|---|---|---|---|
| BoB（GPT-4o 采集 + GPT-4.1 判读 + Gemini-2.0-Flash 诊断） | 67.65% | — | 8.0%（Glass's Δ = −1.04） |
| 最优 multi-agent | 77.39% | +9.75%（p<0.0001） | — |
| 最优单 agent | 75.63% | +7.98% | — |

**B2. BoB 过程指标胜率 vs 结局胜率：**

| 维度 | BoB 胜率 |
|---|---|
| Information Gathering（过程） | 80.0% |
| Information Interpretation（过程） | 76.0% |
| 临床成本（过程） | 84.0% |
| Differential Diagnosis（结局） | 8.0% |

**B3. 失败模式（held-out test，n=1,190）：**

| 失败模式 | BoB | 最优 multi-agent |
|---|---|---|
| 幻觉检验结果（报告了未开单的结果） | 165 例（13.87%） | 5 例（0.42%） |
| 越权开单 | 13.87% | 0.76% |
| 采集不足 | 7.06% | 1.93% |

**分析（5 条）：**
1. **"每个环节最优 ⇒ 整体最优"被证伪**：BoB 在三项过程指标上胜率 76–84%，结局胜率却只有 8.0%。对本项目：五维分数不能由"分维度组件最优"推出总分意义——每维 gold 必须独立于其他维验证。
2. **过程 gold 的价值与边界**：coverage 类过程指标可自动化（指南检查集可机器比对），但 coverage-to-test ratio 与准确率零相关（ρ=−0.057, p=0.748）——**过程 gold 只能作辅助报告，不能单独当"检查选择正确"的判据**。这正是本项目"行为/规范双轨+分轨报告"的直接文献依据。
3. **幻觉结果 → 评测工程要求**：13.87% 的案例中系统报告了从未开单的检验结果。对本项目：MCQ 的题干快照必须显式列出"已有哪些结果"，且判分只基于模型选择，不给模型"编造结果"的空间（MCQ 形式天然规避此问题，是 MCQ 优于索取式评测的一点）。
4. **越权开单 0.76% vs 13.87%**：编排（orchestration）约束比模型能力更能保证流程合规——本项目若做 agentic 版本，需在评分器中显式禁止题干集合外的动作。
5. **该表局限**：单中心四病理；无外部验证；编排策略较简单（作者自述）；BoB 的组件选择仅按单指标。

---

## 二、诊断维度

### 2.1 评测体系检索总表

本维度新检到的评测体系（AMIE 为内部提及 "Google/DeepMind Nature 系列" 的深读落数字版）：

| # | 名称 | 出处/年份 | 数据来源 | 任务设定 | gold 构建方式 | 规模 | 访问 | 链接 |
|---|------|----------|---------|---------|--------------|------|------|------|
| D1 | **AMIE DDx**（深读） | McDuff et al., *Nature* 642:451–457, 2025（[arXiv:2312.00164](https://arxiv.org/abs/2312.00164)） | NEJM Clinicopathological Conference (CPC) 病例报告，2013–2023 | 独立生成 DDx 列表 vs 临床医生（无辅助/搜索辅助/LLM 辅助三臂） | gold=CPC 最终诊断（病理/尸检级共识）；判卷用 GPT-4 辅助的 top-N 包含判定 | 302 例（自 326 例池筛） | 病例公开于 NEJM；代码未全公开 | [Nature](https://www.nature.com/articles/s41586-025-08869-4) |
| D2 | **MEDDxAgent** | Rose et al., ACL 2025（[arXiv:2502.19175](https://arxiv.org/abs/2502.19175)） | DDxPlus（合成）、iCraft-MD（皮肤，含 40 例专家自编）、RareBench（真实：RAMEDIS/MME/PUMCH） | 单轮全档案 vs 交互式逐轮问诊的 DDx | 各数据集自带 ground-truth 病理；DDxPlus 另带排序 gold；iCraft/RareBench 的选项集用 GPT-4o 清洗去重 | 每集抽 100 例；DDxPlus 1.3M/49 病、iCraft 140/394 选项、RareBench 2,185/421 病 | 代码+数据商用可用 | [GitHub](https://github.com/nec-research/meddxagent) |
| D3 | **Open-XDDx / Dual-Inf** | Zhou et al., npj 系（PMC12021655），2024–2025 | USMLE 教材（First Aid Step 2 CS 等）病例，非 MIMIC | 给病历文本生成 DDx+逐条解释 | **专家 gold**：每病历 2 名医生独立标注 DDx+解释，第三人仲裁；均值 4.6 个 DDx/病历 | 570 病历（10 prompt dev + 560 eval）、9 科室 | 代码+数据 CC BY 4.0（补充材料） | [PMC 全文](https://pmc.ncbi.nlm.nih.gov/articles/PMC12021655/)、[GitHub](https://github.com/betterzhou/Dual-Inf) |
| D4 | **RareScale**（罕见病 DDx 规模化） | Schumacher et al., arXiv 2502.15069（Curai），2025 | Internist-1/QMR 后裔专家系统模拟生成病例 + GPT-4o/Claude-3.5 合成问诊对话 | 候选生成器→排序器的两段式 DDx | gold=专家系统评分的 top-5（锚定种子病且须排第一）；GPT-4o 做 judge（沿用 Tu et al. 2024 协议） | 575 病种；28,589（GPT-4o）+14,573（Claude）段对话 | **数据因法律原因不公开** | [arXiv](https://arxiv.org/abs/2502.15069) |
| D5 | **DR.BENCH** | Gao et al., 2023 | MIMIC-III 等 10 个数据集 | 诊断推理的生成式重构：MedNLI/AP 关系/emrQA/SOAP/MedQA/问题列表总结 | 专家标注（如 MedNLI=2 名放射科医师；SOAP=2 名医学生）；总结题 gold=原文问题列表 | 例：MedNLI 11,232 train；Summ 2,138/304/341 | PhysioNet/N2C2 DUA + GitLab 代码 | [PMC 全文](https://pmc.ncbi.nlm.nih.gov/articles/PMC9993808/) |
| D6 | **JMIRx LLM-as-Judge（21 模型）** | JMIRx Med 2025;e67661 | MIMIC-IV 病例 | LLM 评审团比较 21 个 LLM 的诊断输出 | 未核实到细节（页面抓取为空） | 21 个 LLM | 未核实 | [JMIRx](https://xmed.jmir.org/2025/1/e67661) |
| D7 | **H-DDx** | arXiv 2510.03700，2025 | DDXPlus（合成） | 层次化评估 DDx 列表（列表是否构成连贯的疾病层次） | 复用 DDXPlus gold | 未深读 | 未核实 | [arXiv](https://arxiv.org/html/2510.03700v1) |

（ClinDiag 的诊断阶段结果见 §1.2 T4；EHRNoteQA/DiSCQ/npj DM triage 已为内部覆盖，不重复。）

### 2.2 逐个详述

#### D1. AMIE DDx（Nature 2025，深读）

- **设定**：302 例 NEJM CPC（2013–2023；自 326 例池筛除数据不足者）；AMIE 独立生成 DDx，与 20 名临床医生对照；医生在同一批病例上以"无辅助 / 搜索辅助 / AMIE 辅助"三臂随机交叉完成（[Nature](https://www.nature.com/articles/s41586-025-08869-4)）。
- **gold**：CPC 的最终诊断（该会议本身就是"疑难病例+尸检/病理级最终裁决"的规范性范式）；判卷以 top-N 是否包含金标准诊断为主（[arXiv:2312.00164](https://arxiv.org/html/2312.00164v1)）。
- **主结果**：AMIE 单独 top-1 29.2%、top-10 59.1%；无辅助医生 15.9%/33.6%（top-10 差 p=0.04）；搜索辅助医生 24.3%/44.5%；AMIE 辅助医生 25.2%/51.8%。污染子集（56 例）AMIE 35.4%/55.4%（详见 §2.4 表 C）。
- **局限（作者自述与页面可见）**：输入是 CPC 的专家文本摘要而非原始 EHR；文本咨询形式；判卷部分依赖 LLM judge；可能的数据污染（做了 56 例子集分析）。
- **对本项目**：CPC 是"规范性诊断 gold"的天花板范式（疑难+后验裁决），但不可规模化；其"三臂人机对照"可借用于校准项目难度。

#### D2. MEDDxAgent（ACL 2025）

- **基准组成**：DDxPlus（合成呼吸道，1.3M 例 49 病，贝叶斯网络生成）、iCraft-MD（皮肤，140 例，100 例来自题库+40 例专家自编，选项经 GPT-4o 清洗为 394 个唯一病名）、RareBench（真实罕见病 2,185 例 421 病，RAMEDIS/MME/PUMCH 三源）；评测每集固定种子抽 100 例（[arXiv HTML](https://arxiv.org/html/2502.19175v2)）。
- **指标**：Avg Rank（正确诊断名次，出 top-10 记 11）、GTPA@k（top-k 含正确诊断）、ΔProgress（逐轮名次改进）。
- **主结果**：交互式（只给主诉起手）显著优于全档案直读：GPT-4o 在 DDxPlus 上 knowledge-refill n=0 仅 0.18，MEDDxAgent 3 轮到 0.86（全档案 zero-shot 0.69）；RareBench 0.07→0.56；Llama3.1-70B 0.71、Llama3.1-8B 0.58；医学微调模型反而不如通用模型（[arXiv HTML](https://arxiv.org/html/2502.19175v2)）。
- **局限**：两个数据集的选项集由 GPT-4o 生成清洗（gold 被 LLM 预处理过）；合成占比高；固定迭代比动态停止更省（1.2–1.7 倍）但仍是代理指标。
- **对本项目**：其"起手信息极简→逐轮补充"的设定再次支持"决策时点快照"设计；选项集 LLM 清洗须复审（我们用专家而非 LLM 定选项）。

#### D3. Open-XDDx / Dual-Inf（专家解释型 DDx）

- **gold 构建（本项目最可借鉴处）**：570 份病历（源自 First Aid 系教材与 MedQA，去选项后清洗，剔除 <130 字符），每例 2 名医生独立标注 DDx 与解释、第三人仲裁分歧；平均每例 4.6 个 DDx、每诊断 3.1 条解释；覆盖 9 个科室（神经 137 例 24.0% 最大，皮肤 30 例 5.3% 最小）（[PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12021655/)）。
- **指标**：诊断/解释准确率、BERTScore、SentenceBERT、METEOR + 人评（正确性/完整性/有用性）。
- **主结果**：GPT-4 上 Dual-Inf DDx 准确率 0.533 vs SC-CoT 0.472（差 0.061，p<0.001）；解释准确率 0.446 vs 0.334；错误分析（100 例）显示缺失内容 76 vs 89（[PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12021655/)）。
- **局限（作者自述）**：无 DDx 排序信息；反向推理模块依赖模型内部知识、"易受严重幻觉/错误知识影响"。
- **对本项目**：2+1 专家协议 + "DDx+解释"双层 gold 结构可直接搬进诊断维度规范性轨道。

#### D4. RareScale（罕见病 DDx 规模化，Curai）

- **gold**：以 Internist-1/QMR 后裔专家系统的 evoking strength/frequency 评分为准，每病种要求 200 次模拟中 ≥50 次有效、630 种子病存活 575 种；对话由 GPT-4o（28,589 段）与 Claude-3.5-Sonnet（14,573 段）合成，checker prompt 保证全部 findings 出现；judge 为 GPT-4o（沿用 Tu et al. 2024 协议）（[arXiv](https://arxiv.org/abs/2502.15069)）。
- **主结果**：候选生成器（Llama 3.1 7B 微调）top-5 88.80%（GPT-4o 测试集）/77.82%（Claude 测试集）；端到端 RareScale 把 top-5 从 56.80% 提到 74.38%（n=3,403），MRR 0.390→0.471；651 例人机一致性 88.6%、Cohen's κ=0.53（[arXiv](https://arxiv.org/abs/2502.15069)）。
- **局限**：完全模拟（无真实患者）；专家系统覆盖面远小于 NORD 万级罕见病；**数据因法律原因不可发布**——规模化与可发布性冲突的典型。
- **对本项目**：专家系统做 gold 生成器是罕见的"可规模化规范源"，但仅限其覆盖病种；κ=0.53 提醒 gold 边界病例的人机一致性有限。

#### D5. DR.BENCH（诊断推理的生成式 NLP 基准，2023）

- 六任务：MedNLI、AP 关系、emrQA、SOAP 标注、MedQA、问题列表总结（Summ）；五源十个数据集、半数源自 MIMIC-III；gold 全部来自专家标注（如 MedNLI 2 名放射科医师）（[PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC9993808/)）。
- **主结果**：域适配 T5-Large：MedNLI 最高 84.88%；SOAP ~60.06%；emrQA ~39.20%；MedQA 20–24%；Summ-Note 的 ROUGE-L 仅 2.14–7.60（最难）（[PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC9993808/)）。
- **定位与教训**：把"诊断"操作化为 NLP 任务族时，真正接近诊断推理的任务（问题列表总结）指标最差且 ROUGE-L 无法度量医学语义——**"编码/抽取预测"与"诊断推理"的构念分层**在 2023 年已被量化暴露。对本项目：诊断维度不能用"预测出院 ICD"的抽取任务替代推理评测。

#### D6. JMIRx LLM-as-Judge（21 个 LLM，MIMIC-IV）

- 检索定位到该文（JMIRx Med 2025;e67661：以 LLM 评审团在 MIMIC-IV 病例上比较 21 个 LLM 的诊断能力），但页面抓取为空，**gold 定义与主结果数字未核实**（[JMIRx](https://xmed.jmir.org/2025/1/e67661)）。列为待补。

#### D7. H-DDx（层次化 DDx 评估）

- 在 DDXPlus 上提出层次化评估（DDx 列表是否构成连贯疾病层次），是对"top-k 包含金标准"这类平面指标的补充（[arXiv](https://arxiv.org/html/2510.03700v1)）；未深读，数字未核实。对本项目：诊断 MCQ 的干扰项可按"同层次易混淆病"组织，与层次化评估精神一致。

### 2.3 gold 方案分析（诊断）

#### 2.3.1 行为轨道：用什么事件做 gold

**"最终诊断"标签的文献定义谱系**（按后验强度递增）：
1. **出院编码**：MIMIC-IV `diagnoses_icd`（计费编码，出院时点、事后归档）——文献中大量"诊断预测"工作以此为 gold（如 JMIRx 21 模型评测即以 MIMIC-IV 为底，细节未核实，[JMIRx](https://xmed.jmir.org/2025/1/e67661)）；DR.BENCH 一系则证明抽取/编码类任务与诊断推理构念不同（[PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC9993808/)）。
2. **病历叙述文本**：MIMIC-CDM 的诊断 gold 是"患者实际主诊断"（四病理之一，且原文对文本中的诊断词做了去标识防泄漏，[Nature Medicine](https://www.nature.com/articles/s41591-024-03097-1)）；EHRNoteQA 则以出院小结为语料出 QA（内部已覆盖）。
3. **后验裁决**：AMIE DDx 用 NEJM CPC 的病理/尸检级最终诊断（[Nature](https://www.nature.com/articles/s41586-025-08869-4)）——规范性最强但只覆盖疑难病例。
4. **专家系统锚定**：RareScale 以专家系统评分锚定 top-5（[arXiv](https://arxiv.org/abs/2502.15069)）。

**时间语义**：诊断没有 POE 式的单一"开单时刻"。可操作锚点有三【推断，综合上述文献】：(a) ED 出院诊断（edstays disposition 伴随诊断，时点早、不确定性高）；(b) 住院首个attending 诊断/working diagnosis（护理与医师笔记中的评估）；(c) 出院最终诊断（diagnoses_icd seq=1 主诊断 + 出院小结 Final Diagnostics 段）。评测"决策时点"应取 (a)/(b)，gold 取 (c)，两者之间的差异恰好构成题目难度信息（诊断修正类题目）。

**并发/修正处理**：诊断会随检查演进（working diagnosis 更新）。文献先例：MEDDxAgent 的 ΔProgress 显式度量逐轮名次变化（[arXiv HTML](https://arxiv.org/html/2502.19175v2)）；本项目可把"时点 t 的最可能诊断"与"出院最终诊断"都记录，MCQ 分"当前最可能（behavioral snapshot）"与"最终确诊（outcome）"两类题干【推断】。

#### 2.3.2 规范性轨道：规范性依据工具箱

1. **后验全证据裁决（CPC 范式）**：AMIE DDx 的金标准来自 CPC 会议的病理级裁决（[Nature](https://www.nature.com/articles/s41586-025-08869-4)）；不可规模化，但可作少量"锚题"标定专家基线。
2. **专家 2+1 协议标注**：Open-XDDx 每例 2 名医生独立+第三人仲裁，产出 DDx+解释双层标注（[PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12021655/)）——规模化规范性 gold 的现实样板。
3. **临床确诊标准**：如 MIMIC-CDM 四病理以指南/标准定义入组（lipase 等检验判据见其指南检查集，[arXiv 2506.06574](https://arxiv.org/abs/2506.06574)）；对可判据化疾病（如修订 Atlanta 胰腺炎标准）可机器初筛+专家确认【推断：判据名称从 Optimization Paradox 的指南检查集间接可见】。
4. **LLM judge + 人机一致性校验**：ClinDiag（700 例 kappa 0.70–0.92）、RareScale（GPT-4o judge 沿用 Tu et al. 2024 协议）、MEDDxAgent（GPT-4o 清洗选项集）——LLM 可参与但必须有报告的 κ 值（[PMC13181090](https://pmc.ncbi.nlm.nih.gov/articles/PMC13181090/)、[arXiv 2502.15069](https://arxiv.org/abs/2502.15069)）。
5. **专家裁定证据包（推荐组成）**【推断，综合】：决策时点快照（去标识诊断词，仿 Hager）、时间线事件（检查开单与结果）、出院小结诊断段、ICD 主诊断、（如有）尸检/病理/微生物学确认结果、专家可引用的指南条目。

#### 2.3.3 两轨各自的陷阱（文献证据）

**行为轨道**：
- **出院编码的后验性**：diagnoses_icd 在出院时归集，含计费动机与编码规则影响【推断：编码偏差的量化文献未在本轮检索覆盖，见内部 label leakage 框架】；以其为"时点 t 该想到什么"的 gold 会把后验信息当作先验能力。
- **文本泄漏**：Hager et al. 必须把病历中诊断词下划线去标识才能做自主评测（[Nature Medicine](https://www.nature.com/articles/s41591-024-03097-1)）；MIMIC-IV-Note 的放射/出院报告常直接写诊断，快照构建必须做诊断词扫描（本项目已有 leakage 框架，此为又一实证）。
- **疑难分布漂移**：AMIE 单独 top-1 也只有 29.2%（CPC 疑难集），而 EHRNoteQA 直读式 QA 上主流模型普遍高分——gold 难度对病例分布极其敏感（[Nature](https://www.nature.com/articles/s41586-025-08869-4)）。
- **合成 gold 的循环**：RareScale 的对话与 judge 都是 LLM 生成（[arXiv](https://arxiv.org/abs/2502.15069)）；MEDDxAgent 选项集由 GPT-4o 清洗（[arXiv HTML](https://arxiv.org/html/2502.19175v2)）——模型参与的 gold 需保留人审通道。

**规范性轨道**：
- **专家 gold 无排序**：Open-XDDx 明确其 DDx gold 无优先级排序（[PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12021655/)）——MCQ 需要"最可能"级别的排序判断，专家协议必须额外收集优先级。
- **人机一致性有限**：RareScale κ=0.53（[arXiv](https://arxiv.org/abs/2502.15069)）；ClinDiag judge kappa 下限 0.70（[PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC13181090/)）——边界病例应剔除或降权。
- **可发布性冲突**：RareScale 数据因法律原因不公开（[arXiv](https://arxiv.org/abs/2502.15069)）；本项目基于 MIMIC 可在 credentialed 下发布题目框架。

#### 2.3.4 推荐 gold 方案（诊断）

**分层 gold + 双题干设计**：

1. **行为 gold（可自动，人工抽检）**
   - 标签定义：主 gold = 出院主诊断（`diagnoses_icd.seq=1`）+ 出院小结诊断段交叉验证；不一致者（ICD 与文本冲突）进入人工队列或剔除。
   - 时点设计：快照 t 取 (a) ED 段末（edstays out 时间前）与 (b) 住院 24h 两个决策点；时点前诊断词去标识扫描（仿 Hager）。
   - 排除规则：住院期死亡/转院的非常规结局【推断】、诊断在出院小结中标记为"排除/待排"者剔除、ICD-10 未特指编码（如 I10 以外的 .9 类）降权【推断】。
   - 人工审核：ICD-文本一致性抽检；"最终诊断"文本段解析规则审核。
2. **规范 gold（须人工）**
   - 专家 2+1 协议（仿 Open-XDDx）：对每题独立给出"时点 t 最可能诊断（含排序）+ 依据短解释"；两专家 top-1 不一致且第三人不能仲裁者剔除该题。
   - 锚题：从病理/微生物学可确认病例中选 3–5% 作"确诊级"锚题（CPC 精神），用于标定专家与模型差距。
   - 干扰项：按 H-DDx 的层次化思想从"同层次混淆病"生成（同解剖系统/同表现簇），并要求专家确认每个干扰项"在该时点可辩"。
3. **文献直接支持**：2+1 专家协议（Open-XDDx）、去标识防泄漏（Hager）、LLM judge 须报 κ（ClinDiag/RareScale）、层次化干扰项（H-DDx）、后验裁决锚题（AMIE/CPC）。【推断】：双决策点（ED 末/24h）、排除与降权规则、3–5% 锚题比例。

### 2.4 关键图表深析（诊断维度 + 跨维度 gold 改造成本）

#### 表 C. AMIE DDx（Nature 2025）：302 例 NEJM CPC 人机三臂对照

来源：[arXiv:2312.00164](https://arxiv.org/html/2312.00164v1) Table 1（正式版 [Nature 642:451–457](https://www.nature.com/articles/s41586-025-08869-4)）。

| 队列 | Top-1 准确率 | Top-10 准确率 |
|---|---|---|
| LLM for DDx（AMIE 单独） | 29.2% | 59.1% |
| 临床医生（无辅助，辅助前） | 15.9% | 33.6% |
| 临床医生（搜索辅助后） | 24.3% | 44.5% |
| 临床医生（AMIE 辅助后） | 25.2% | 51.8% |
| 污染子集（56 例）：AMIE 单独 | 35.4% | 55.4% |
| 污染子集：AMIE 辅助医生 | 24.6% | 52.3% |

另有：AMIE 辅助后医生 top-10 51.7% vs 无辅助 36.1%（McNemar 45.7, p<0.01）；AMIE 使 73 例新增包含正确诊断（搜索为 37 例）。

**分析（6 条）：**
1. **表显示了什么**：在病理级裁决 gold 的疑难病例上，LLM 单独（top-10 59.1%）显著强于无辅助医生（33.6%，p=0.04），且人机协同（51.8%）介于两者之间。
2. **数字差距的构念含义**：top-1（29.2% vs 15.9%）差距远小于 top-10（59.1% vs 33.6%）——模型的"鉴别面"宽而"定诊力"弱。对本项目：诊断 MCQ 若只考 top-1（单选"最可能诊断"）会低估模型的鉴别能力，应设"以下哪项应纳入鉴别/最需要排除"两类题并存。
3. **对 gold 设计的含义**：CPC gold 是"病理/尸检级后验裁决"，其规范性强度在文献中无出其右；但它天然是疑难偏态分布（医生 top-1 仅 15.9%），直接套用会把全部题目做成超难题。建议把后验裁决只用于锚题，主集用常规分布。
4. **对题目设计的含义**：AMIE 辅助把医生从 33.6% 拉到 51.8%，但反而低于模型单独（59.1%）——人机协同存在"锚定损失"。本项目若做"AI 建议下的医生决策"扩展维度，此表是设计依据。
5. **污染处理的示范**：作者用 56 例"确认无训练重叠"子集复验（AMIE 35.4%/55.4% 反而更高），是污染敏感性分析的最小可行模板，本项目每题应保留可追溯来源供子集复验。
6. **该表局限**：输入为专家撰写的 CPC 摘要而非原始 EHR（信息密度远高于真实快照）；医生为文本咨询形式；判卷含 LLM 辅助；样本 302 例。

#### 表 D. EHRNoteQA（NeurIPS 2024）：MIMIC-IV 出院小结 → MCQ 的临床修改漏斗

来源：[arXiv:2402.16040](https://arxiv.org/html/2402.16040v2)（内部已综述其整体；此处仅落数字）。

| 漏斗步骤 | 数字 |
|---|---|
| 源池（MIMIC-IV 出院小结/患者） | 331,794 份小结 / 145,915 名患者（人均 2.3 份） |
| 长度分层 | Level 1 ≤3,500 tokens；Level 2 3,500–7,500（超长剔除） |
| 抽样 | 1,000 名患者（Level 1 550 / Level 2 450） |
| 数据删除（琐碎/不具代表性的问题） | 移除 38 个数据点 |
| 题目修改（3 名医生×2 个月） | 206/1,000 题被修改 |
| 正确答案修改 | 338/1,000 被修改 |
| 干扰项修改 | 962/4,000 被修订 |
| **最终基准** | **962 题、962 名患者、1,659 份出院小结** |

判卷：GPT-4-turbo 是/否打分、每输出评 5 次取均；MCQ 形式评分方差显著低于自由文本（平均 SD 0.24 vs 1.21）。

**分析（7 条）：**
1. **表显示了什么**：即使以"自动生成 MCQ + 金标准答案直接取自出院小结"这种最省人工的 pipeline，1,000 题中 20.6% 的题目、33.8% 的正确答案、24.1% 的干扰项仍需医生返工——**"纯自动 gold"在诊断/病人特异 QA 上不成立**。
2. **对本项目 gold 设计的直接含义**：预算必须为"答案修正"（33.8% 是最大项）留出人工成本；行为 gold 抽自 EHR 事件（POE/编码）比抽自小结叙述更结构化，预计修正率可低于 33.8%【推断】，但规范性轨道（专家裁定）成本只会更高。
3. **MCQ vs 自由文本的方差证据**：评分 SD 0.24 vs 1.21——MCQ 是本项目主形态的直接文献支持。
4. **长度控制**：3,500/7,500 token 的两级长度筛除超长病例，说明"快照规模可控"是 EHR 出题的工程前提；本项目决策时点快照应有同类长度分层。
5. **修改集中在哪**：正确答案修改率（33.8%）高于题目修改率（20.6%）——自动 gold 的主要错误不在题面而在"从病历事实到可判定答案"的映射；本项目的映射规则（ICD/POE 事件→选项）是质控重心。
6. **3 名医生×2 个月 / 962 题**：可折算≈每题 0.45 医生·月【推断：粗算供排期参考】，与 Open-XDDx 的 2+1 协议成本量级一致。
7. **该表局限**：漏斗未报告剔除后题目难度/科室分布变化；判卷依赖 GPT-4-turbo（虽 5 次取均）；题目均为单文档（出院小结）回溯式 QA，非决策时点前瞻式。

#### 表 E. MEDDxAgent（ACL 2025）：全档案直读 vs 交互式逐步信息

来源：[arXiv:2502.19175](https://arxiv.org/html/2502.19175v2) Table 1–2（GTPA@1；每数据集 100 例）。

| 设定 | DDxPlus | RareBench |
|---|---|---|
| GPT-4o 全档案 zero-shot（直读） | 0.69 | — |
| GPT-4o 交互式起手（KR, n=0，仅主诉） | 0.18 | 0.07 |
| GPT-4o + MEDDxAgent（2–3 轮迭代） | 0.86 | 0.56 |
| Llama3.1-70B + MEDDxAgent | 0.71 | — |
| Llama3.1-8B + MEDDxAgent | 0.58 | — |

**分析（4 条）：**
1. **表显示了什么**：只给主诉时准确率崩塌（0.18/0.07），补 2–3 轮关键信息即恢复到 0.86/0.56——超过全档案直读（0.69）。**信息量的边际效应远大于模型规模效应**。
2. **构念含义**：与表 A（Hager）互相印证：诊断能力的可测部分高度依赖"决策时点已有什么信息"。两个团队、两种数据（真实 MIMIC vs 合成 DDxPlus）、同一方向（−13 至 −51 点），说明该效应稳健。
3. **对本项目题目设计的直接含义**：诊断题的快照信息量是难度旋钮——ED 初诊题（少信息）与 24h 修正题（多信息）应成对设计，并按快照信息量分层报告；干扰项"可辩性"也应相对快照判定（在 t 时点合理、出院后不合理的选项才是好干扰项）。
4. **该表局限**：DDxPlus 为贝叶斯网络合成；iCraft/RareBench 选项集经 GPT-4o 清洗；每格仅 100 例，区间宽。

---

## 三、两维对比小结

### 3.1 gold 构建难度对比

| 维度 | 行为 gold 源 | 结构化程度 | 规范 gold 依据可得性 | 主要陷阱 | 文献先例密度 |
|---|---|---|---|---|---|
| 检查检验选择 | POE 订单事件（`ordertime`/`transaction_type` 明确，[POE 文档](https://mimic.mit.edu/docs/iv/modules/hosp/poe)） | **高**（结构化订单，可机器切回合） | 中：指南检查集需按病理手工整理（[Opt-Paradox](https://arxiv.org/abs/2506.06574)）；CW/AUC 可做负向题（[SycoEval-EM](https://arxiv.org/html/2601.16529v3)） | 行为受习惯/成本影响；"多开"与"开对"零相关（ρ=−0.057）；13.87% 幻觉结果风险（索取式） | **低**——检查阶段普遍无独立对错 gold（ClinDiag 只做 Likert 流程评分） |
| 诊断 | 出院主诊断 ICD + 小结诊断段交叉 | 中（ICD 结构化但后验；文本需解析） | 高：专家 2+1 协议（[Open-XDDx](https://pmc.ncbi.nlm.nih.gov/articles/PMC12021655/)）+ 确诊级锚题（[AMIE/CPC](https://www.nature.com/articles/s41586-025-08869-4)）范式成熟 | 出院编码后验性；诊断词泄漏（Hager 去标识先例）；无排序 gold（Open-XDDx 自述） | **高**——但多为"编码/抽取"或合成，真实 EHR 决策时点式稀缺 |

### 3.2 人工成本与可自动化环节

- **可全自动**：订单/编码抽取、回合切分、快照构建、时间窗与泄漏扫描、患者级 split、题目长度分层（EHRNoteQA 漏斗前半段全可机器做，[arXiv](https://arxiv.org/html/2402.16040v2)）。
- **半自动（机器+抽检）**：subtype→检查类别映射表、ICD-诊断文本一致性、干扰项初筛（可由 LLM 按"同层次混淆"生成后专家确认，参照 MEDDxAgent 用 GPT-4o 清洗选项集但须人审，[arXiv](https://arxiv.org/html/2502.19175v2)）。
- **必须人工**：
  - 检查维：指南推荐检查集整理（每病理一次）、CW 负向题撰写、行为答案"可接受/次优/不当"裁定（≥2 人）；
  - 诊断维：2+1 专家标注（时点最可能诊断+排序+依据）、锚题裁决、干扰项可辩性确认。
- **成本量级锚点**：EHRNoteQA 3 医生×2 月产出 962 题且 33.8% 正确答案被改（[arXiv](https://arxiv.org/html/2402.16040v2)）；Open-XDDx 570 例的 2+1 标注（[PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC12021655/)）；SycoEval-EM 仅 3 个规范性场景即需嵌标准原文+95 对话人机校验（[arXiv](https://arxiv.org/html/2601.16529v3)）——**规范性题的边际成本约为行为题的数倍**【推断：由上述比例粗估】。

### 3.3 对本项目的一句话结论

检查检验维的行为轨道最可自动化（POE 语义清晰），但规范性轨道文献几乎空白（可作增量贡献点）；诊断维规范性范式成熟（2+1+锚题）但行为轨道必须处理后验 gold 与诊断词泄漏；两维共用"决策时点快照 + 双轨 gold 分轨报告"的骨架，且四组独立证据（Hager −11~−13 点、ClinDiag −17~−27 点、MEDDxAgent −0.4~−0.5、LA-CDM 92.8%@$3793 vs 81.3%@$1296）共同表明：**评测结果由"时点信息量 × gold 轨道选择"共同决定，任何单轨报告都会系统性误导模型排名**。

---

### 附：未核实事项清单

1. **DxQRR**（Luo et al., AMIA/JAMIA Question Result Ranking）：PubMed/arXiv/Bing/DDG 均未命中（[PubMed 检索](https://pubmed.ncbi.nlm.nih.gov/?term=DxQRR)）——需内部核对种子引文。
2. **JMIRx 21-LLM MIMIC-IV 诊断评测**（[链接](https://xmed.jmir.org/2025/1/e67661)）：页面抓取为空，gold 与结果数字未核实。
3. **H-DDx**（[arXiv 2510.03700](https://arxiv.org/html/2510.03700v1)）：仅检索级信息，表格数字未读。
4. **MediTOD 规模数字**：摘要层无对话数，未读 PDF 全文。
5. Hager et al. 的检验开单"类别"结果（93.3% 等）转录自 Nature 正文的叙述段，未对应到编号表格（表格位于 Extended Data，正文页未展示）。
