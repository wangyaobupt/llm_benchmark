# 真实世界 EHR 评测集构建方法普查（EHR Evaluation Benchmark Construction Survey）

- **调研日期**：2026-08-16
- **定位说明**：本笔记与本项目 2026-08-10 的五维综述（`benchmark-five-dimension-evidence-review.md`，已覆盖 EHRNoteQA、MIMIC-CDM、DiSCQ、CliBench、EHRBench、npj DM 2025 triage/referral 工作、label leakage 框架、Harutyunyan 2019 MIMIC-III 四任务、MCQ 题项分析、LLM 选项位置偏好、BetterBench、npj DM 2024 出院指导安全）互补，**不重复**其已详述来源，聚焦"用真实世界 EHR 数据（结构化/文本）构建评测集"的既有工作，重点在 **gold 标签构建方法、标注一致性与泄漏控制**，而非排行榜数字。
- **方法**：WebSearch 检索 + 论文原文/官方页面核读。所有具体数字均来自论文原文或官方页面；未核实的项明确标注"未找到/未核实"。

---

## 2. 总览矩阵

下表汇总 A1–C3 全部已在正文详述的数据集，所有内容均转录自本文各节已写明的信息（含"未核实"标注），未新增任何数字。

| # | 数据集 | 来源 EHR | 规模 | 任务 | gold 构建方式 | 一致性 | 访问方式 |
|---|---|---|---|---|---|---|---|
| A1 | EHRXQA | MIMIC-IV + MIMIC-CXR + Chest ImaGenome（交集 19,264 患者） | 46,152 条 QA / 417 模板 | 多模态 QA / text-to-NeuralSQL（非 MCQ） | 4 名研究生约 2 个月手写模板 SQL，槽位填充生成问题，gold = 执行 SQL 返回值；GPT-4 改写后人工复核；临床效用经 1 名神经外科医生确认 | 未报告 IAA | PhysioNet credentialed（CITI + License 1.5.0） |
| A2 | EHRSQL / EHRSQL-2024 | 原版 MIMIC-III + eICU；2024 版 MIMIC-IV Demo v2.2 | 原版 230 模板（174 answerable + 56 unanswerable）；2024 版 5,124/1,163/1,167（train/val/test） | text-to-SQL + 可靠性（unanswerable 须弃答） | 模板派生 + 医院真实工作人员需求收集改写；2024 版 unanswerable 构造流程未核实 | 未核实 | 2024 版数据/代码全开源（Demo 库 ODbL 无 DUA 门槛）；Codabench 赛页 |
| A3 | DrugEHRQA | MIMIC-III v1.4 结构化表 + 505 份出院小结（复用 n2c2 2018 T2 人工标注） | 7 万+ QA 对（41,417 个结构化三元组） | 药物相关多模态 QA（问题 + SQL + 答案） | 9 个药物属性模板槽位填充；答案 = SQL 执行与 n2c2 2018 人工标注取回后规则合并；人工验证仅抽样 500 条 | 无 IAA 统计 | PhysioNet credentialed + n2c2 门户跨库许可拼接 |
| A4 | MedBench（中文，对照系） | 中文评测，题目来源构成未核实（非真实 EHR 派生路线） | 300,901 题 / 43 个专科 | 多维度中文医疗 LLM 评测 | 未核实（摘要仅称评测结果与医学专业人士视角一致） | 未核实 | 官网平台提交输出；题目与 gold 物理隔离，test gold 不公开 |
| B1 | i2b2 2006 去标识化 | Partners 出院小结 | 889 份（train 669 / test 220） | 8 类 PHI 去标识化 | 自动系统预标 + 3 名标注者串行三遍人工校验 + 分歧讨论定稿；真实 PHI 替换为合成 surrogate | 未报告 κ | n2c2 门户注册 DUA |
| B2 | i2b2 2008 肥胖/合并症 | Partners 出院小结（超重/糖尿病队列） | 1,237 份（train ~730 / test ~507） | 肥胖 + 15 项合并症，textual/intuitive 双轨分类 | 2 名专科专家独立标注 + 1 名住院医师第三人裁决；textual 分歧三人多数票，intuitive 只取双标一致为 gold | textual κ 0.71–0.94（12 项 ≥0.8）；intuitive 最低 0.44 | n2c2 门户 DUA |
| B3 | i2b2 2009 用药抽取 | Partners 出院小结 | 1,249 份（train 696 / test 533） | 药名 + 剂量/途径/频次等字段抽取 | 145 份最长文档专家串行精标（医生先标、研究者修订）；评测 gold 另用社区标注（每文档 2 队各 1 人 + 第三队裁决） | 无 κ；社区 gold 对专家 gold F > 0.90 | n2c2 门户 DUA |
| B4 | i2b2/VA 2010 概念/断言/关系 | Partners、BIDMC、UPMC 出院小结 + 病程记录 | train 394 / test 477（另 877 份未标注） | 概念抽取 / 断言 / 关系 | 人工精标参考语料；标注人数/裁决流程在在线补充材料 | κ 未核实 | n2c2 门户 DUA |
| B5 | i2b2/VA 2011 共指消解 | i2b2/VA（出院小结+病程记录）+ ODIE（Mayo/UPMC） | 978 份（train 590 / test 388）；5,227 条 gold 链 | 共指消解 | 每份文档 2 名独立标注者 + 1 名裁决者，两轮裁决（分歧解决 + 全局一致性复查） | κ 在在线附录（未核实） | n2c2 门户 DUA |
| B6 | i2b2 2012 时间关系 | Partners/BIDMC 出院小结 | 310 份（约 17.8 万 token） | EVENT / TIMEX3 / TLINK 时间标注 | 8 名标注者（4 名医学背景）双标 + 第三人裁决；TLINK 7 类因一致性过低合并为 3 类，两版标注均发布 | EVENT span 0.83/0.87、type 0.93/0.90；TIMEX3 span 0.73/0.89；TLINK span 仅 0.39 | n2c2 门户 DUA |
| B7 | i2b2/UTHealth 2014 危险因素 | Partners 296 名糖尿病患者纵向记录 | 1,304 份（train 790 / test 514，患者级切分 + 三队列均衡） | CAD 危险因素文档级标注 + 相对文档时间 | 7 名医学背景标注者（1 MD、5 RN、1 医助），每份文档 3 人独立标注多数票定 gold | overview 未报 κ | n2c2 门户 DUA（surrogate 后发放） |
| B8 | n2c2 2018 Track 1 队列筛选 | 复用 2014 纵向语料（288 名糖尿病患者） | 288 患者 × 2–5 份记录（约 78 万 token） | 13 条真实试验入选/排除标准 met/not met 判定 | 2 名医学背景标注者独立标注每患者每条标准并标证据，裁决人（含 MD 咨询）解决分歧，"possibly"并入二值 | Cohen κ 平均 0.54；偏态类目低至 −0.1 | n2c2 门户 DUA；test 仅开放 3 天、每队限 3 次提交 |
| B9 | n2c2 2018 Track 2 ADE/用药 | MIMIC-III 出院小结 | 505 份（train 303 / test 202） | 9 类药物实体 + 关系抽取（概念/关系/端到端三档） | 领域专家标注（多标注者 + 临床裁决） | 标注人数与 κ 未核实 | n2c2 门户 DUA（底库 MIMIC-III，亦受 PhysioNet 体系约束——推断） |
| B10 | n2c2 2019 与 SemEval-2015 Task 6（Clinical TempEval） | TempEval：Mayo Clinic THYME 结肠癌记录与病理报告；n2c2 2019：任务更正见 B10 节 | TempEval 440 份（train 293 / test 147） | n2c2 2019：语义相似度/家族史/概念规范化（无 ADE 任务）；TempEval：THYME-TimeML（DocTimeRel + CONTAINS 型 tLink，样本过少的关系弃用） | TempEval 采用 THYME-TimeML 标注方案 | 未核实 | n2c2 部分经 n2c2 门户 DUA；TempEval 数据授权流程漫长（当年仅 2 队参赛） |
| C1 | MIMIC-CXR / MIMIC-CXR-JPG | BIDMC 急诊胸片 + 报告（2011–2016） | 377,110 张 DICOM / 227,835 study / 约 65,000 患者 | 图文多模态、报告理解、14 类病理标签 | CheXpert labeler 规则三段式派生（提及抽取 → 三值判定 → 优先级聚合）；1 名放射科医师标注 test set 评估 labeler（单人——页面明示局限） | 未报告 IAA（labeler 评估为单人标注） | PhysioNet credentialed（CITI + DUA 1.5.0），禁再分发，发表须公开代码 |
| C2 | CheXpert | 斯坦福医院胸片（2002–2017） | 65,240 患者 / 224,316 张 | 14 类病理三值（阳/不确定/阴）分类 | 规则 labeler 从报告自动打标；500 份报告与 1 名放射科医师比对验证（平均准确率约 93.6%、uncertain 约 86.8%——转述自 Table 2，未逐字核读）；竞赛验证集 3 名医师标注 200 张并裁决 | labeler vs 医师约 93.6%（转述）；竞赛集为 3 医师共识 | 图像经斯坦福方协议申请（非 PhysioNet）；labeler 开源 |
| C3 | RadGraph | MIMIC-CXR 报告 | 人工 dev 500 份（14,579 实体 + 10,889 关系）+ test 100 份双套标注 + 机器标注 220,763 份 | 报告实体 + 属性（否定/不确定/变化）+ 关系抽取 | board-certified 放射科医师标注（schema 基于 Dykstra 方案）；test 每份两套独立标注作人类基线 | 人类一致性以双标注 F1 表示（数值未逐字核读） | GitHub 指引分发；底库 MIMIC-CXR 需 PhysioNet credentialed（推断） |

> 注：A5 点名的 EHRSeqQA / EHRQuest / MedAxon 经检索未找到（详见 A5 节），不列入本表。**D 组（MIMIC-IV 官方 benchmark 套件、eMERGE 表型验证、PheCAP）见表下补充**——其标签来自结构化字段规则派生而非文本标注，构建模式与 A–C 组不同，故不并入本表，见下文 D 组详述。

## 3. 分组详述

### A. 结构化 EHR 问答/临床决策 benchmark

> 先说明检索结果：任务书点名的 **EHRSeqQA、EHRQuest、MedAxon** 三个名字，经 arXiv/PubMed/Google 多轮英文检索（2026-08-16）**均未找到可核实的对应论文或数据集页面**，下文以"未找到"记录，并给出最接近的已核实替代品（EHRSQL、emrQA、LongHealth、Kim et al. 2022 多轮 text-to-program EHR-QA）。此外，MIMIC-CDM（Nature Medicine 2024）与 EHRBench 已在 2026-08-10 内部综述详述，此处不重复。

#### A1. EHRXQA（NeurIPS 2023 D&B；Nature Communications 2024 扩展版）

- **来源**：Bae et al.，[NeurIPS 2023 论文](https://arxiv.org/abs/2310.18652) | [PhysioNet 数据页](https://physionet.org/content/ehrxqa/)。
- **数据来源与队列**：MIMIC-IV（结构化多表）+ MIMIC-CXR（胸片）+ Chest ImaGenome（胸片标注），三者交集 19,264 名患者；Beth Israel Deaconess ICU 人群（推断自 MIMIC 来源）。
- **任务与题型**：多模态 QA / text-to-(Neural)SQL：自然语言问题 + 对应 SQL/NeuralSQL 查询（含调用视觉问答 API 的 `func_vqa`），答案为自由文本字符串；**非 MCQ**。共 46,152 条样本、417 个模板（图像类 16,366、表格类 16,529、图像+表格 13,257）。
- **gold 构建**：完全**程序化派生**——417 个模板的 SQL 由 4 名研究生历时约 2 个月手工编写并迭代修订；问题实例由模板槽位填充生成，再用 GPT-4 改写后人工复核；gold 答案 = 在数据库上执行 SQL 得到的返回值。模板的临床效用由一名 board-certified 神经外科医生确认。**未报告任何标注者间一致性统计**。
- **split 与泄漏**：train 36,174 / valid 5,170 / test 4,808；train+valid 用 Chest ImaGenome silver 子库（800 患者），test 用 gold 子库（400 患者），silver/gold 按患者分离，等效患者级 split；时间泄漏未显式处理（问题多为检索式，非预测式——推断）。
- **指标**：text-to-SQL 准确率 / 执行结果匹配（论文侧）。
- **发布与访问**：[PhysioNet credentialed access](https://physionet.org/content/ehrxqa/)，需 CITI 培训 + PhysioNet Credentialed Health Data License 1.5.0。
- **局限（作者自述）**：仅基于 MIMIC，泛化性受限；受 Chest ImaGenome 标签粒度限制无法问细粒度视觉问题；不含 unanswerable 问题（不像 EHRSQL）。
- **可借鉴点**：(1) "模板 + SQL 执行派生 gold"是结构化表上最廉价的大规模 gold 生成法，但只覆盖"可查询事实"，无法覆盖规范性决策——正好说明我们项目为何需要人工标注门禁；(2) train 用 silver（机器标注）、test 用 gold（人工标注）的两级 gold 设计可直接借鉴到我们的试审/正式标注分期。

#### A2. EHRSQL（NeurIPS 2022 D&B）与 EHRSQL-2024 共享任务（NAACL 2024 Clinical NLP）

- **来源**：[NeurIPS 2022 论文](https://proceedings.neurips.cc/paper_files/paper/2022/file/643e347250cf9289e5a2a6c1ed5ee42e-Paper-Datasets_and_Benchmarks.pdf) | [GitHub](https://github.com/glee4810/EHRSQL) | [EHRSQL-2024 overview（ACL Anthology）](https://aclanthology.org/2024.clinicalnlp-1.62/) | [arXiv 2405.06673](https://arxiv.org/abs/2405.06673) | [官方仓库](https://github.com/glee4810/ehrsql-2024)。
- **数据来源与队列**：原版基于 MIMIC-III + eICU；2024 版基于 **MIMIC-IV Demo v2.2**（Open Database License，可公开访问——这是它适合做共享任务的原因）。
- **任务与题型**：text-to-SQL：自然语言问题 → SQL；2024 版核心创新是**可靠性**：问题分 answerable / unanswerable，unanswerable 需输出 `null`（弃答）。原版 230 个模板（174 answerable + 56 unanswerable）。2024 版规模：train 5,124 / validation 1,163 / test 1,167 问（[GitHub README](https://github.com/glee4810/ehrsql-2024)）。
- **gold 构建**：模板派生 + 问题来自医院真实工作人员需求的收集改写（原版论文；具体标注人数/κ 未核实——PDF 未读取）；2024 版 unanswerable 问题的构造与验证流程未在已读页面披露（未核实）。
- **split 与泄漏**：患者级 split 未在已读材料中说明（未核实）。
- **指标**：执行准确率 + 可靠性分数（reliability，奖励正确弃答）；细节见 [Codabench 赛页](https://www.codabench.org/competitions/1889/)。
- **发布与访问**：2024 版数据/代码全开源（MIMIC-IV Demo 底库无 DUA 门槛）；100+ 人报名、8 队完赛。
- **局限**：Demo 库仅约 100 名患者，规模与人群代表性受限（推断：Demo 子集）；unanswerable 占比等构造细节透明度不足。
- **可借鉴点**：(1) 把"不可回答/应弃答"作为一等公民纳入评测，对应我们"决策时点快照下信息不足"的场景；(2) 用开放许可的 Demo 子库先做共享任务、全库留 credentialed，是数据访问分层设计的成熟做法。

#### A3. DrugEHRQA（LREC 2022 + PhysioNet）

- **来源**：Pampari et al.，[ACL Anthology 论文页](https://aclanthology.org/2022.lrec-1.117/) | [PhysioNet 数据页](https://physionet.org/content/drugehrqa/)。
- **数据来源与队列**：MIMIC-III v1.4；结构化侧用 PRESCRIPTIONS、DIAGNOSES_ICD 等表，非结构化侧用 505 份出院小结（其药物属性标注复用 **n2c2 2018 ADE/Medication** 挑战的人工标注——见 B 组）。
- **任务与题型**：药物相关多模态 QA（问题 + SQL + 答案三元组），共 7 万+ QA 对，其中 41,417 个"自然语言问题 + SQL + 结构化答案"三元组；按难度分层（易 ~1.3%、中 ~32%、难 ~33%、极难 ~33%）。
- **gold 构建**：9 个药物属性问题模板（剂量/频次/途径/原因等）槽位填充自动生成，SQL 模板同法填充；答案分别从 MIMIC-III 表执行 SQL 与 n2c2 2018 人工标注取回，多模态答案按规则合并；**人工验证仅抽样 500 条**；无标注者间一致性统计。
- **split 与泄漏**：PhysioNet 页未提及官方 split（未核实）。
- **指标**：QA 准确率 / text-to-SQL 执行匹配（论文侧，未逐字核实）。
- **发布与访问**：PhysioNet credentialed access（结构化部分）；非结构化标注需另行从 n2c2（i2b2/n2c2 门户）获取并用 GitHub 脚本合并——**跨库许可拼接**的典型实例。
- **局限**：仅药物域、模板合成问题而非真实临床提问、人工验证仅 500 条（作者/页面自述）。
- **可借鉴点**：(1) "复用既往共享任务的人工标注做 gold、用结构化表交叉验证"是低成本双源验证思路；(2) 难度分层发布便于按能力分层分析题项。

#### A4. MedBench（上海 AI Lab 系，中文医疗 LLM 评测平台）

- **来源**：Liu et al.，[arXiv 2407.10990](https://arxiv.org/abs/2407.10990) | [Big Data Mining and Analytics 期刊版（开放获取）](https://www.sciopen.com/article/10.26599/BDMA.2024.9020044) | 官网 [medbench.opencompass.org.cn](https://medbench.opencompass.org.cn)。
- **数据来源与队列**：**中文**评测，300,901 题、43 个临床专科（论文摘要）；题目来源构成（是否含真实病历 vs 执业医师考试题）**未核实**——摘要与官网均未披露，全文 PDF 未能解析。注意：这与本项目"真实 EHR 派生评测"路线不同质，列为对照。
- **任务与题型**：多维度（理解/生成/知识问答/复杂推理/安全伦理），题格式细节未核实。
- **gold 构建**：摘要层面仅披露"评测结果与医学专业人士视角一致"；标注人数/资质/一致性统计均**未核实**。
- **评测基础设施**：云端全自动评测、**题目与 gold 答案物理隔离**、动态评测机制防 shortcut learning 与答案记忆（摘要原文）。
- **指标 / split / 泄漏**：未核实（全文未读）。
- **发布与访问**：官网开放，模型通过平台提交输出（test 集 gold 不公开）。
- **局限**：题目来源与构造透明度低（推断：公开材料不含数据构造细节）。
- **可借鉴点**：(1) "题目与 gold 物理隔离 + 动态评测防记忆"是 leaderboard 防污染的标准设计，值得纳入我们的评测发布方案；(2) 其"中文医疗场景"覆盖可作香港本地适配时的对照系（但需先核实其数据来源）。

#### A5. 未找到的三个点名数据集

- **EHRSeqQA**：arXiv/PubBox 多轮检索无结果。最接近的已核实工作：Kim et al., "Uncertainty-Aware Text-to-Program for EHR-QA"（[PMLR 2022](https://proceedings.mlr.press/v174/kim22a.html)，多轮/结构化 EHR-QA text-to-program 线）与 LongHealth（[PMC12290132](https://pmc.ncbi.nlm.nih.gov/articles/PMC12290132/)，长病历纵向 QA）。
- **EHRQuest**：PubMed 与 Google 检索均无命中；可能与其他团队的内部名混淆。队列检索（cohort retrieval）方向可参考 emrQA（[模板化 notes QA，2018](https://www.researchgate.net/publication/334115868)）与 Bardhan et al. 的 [JMIR 2024 EHR-QA 综述](https://www.jmir.org/2024/1/e53636/)。
- **MedAxon**：arXiv 域内检索无命中。多患者/诊断推理方向的已核实替代：DR.Bench（[arXiv 2209.14901](https://arxiv.org/abs/2209.14901)）、DiagnosisArena（[arXiv 2505.14107](https://arxiv.org/abs/2505.14107)）。



### B. 临床文本 NLP 共享任务评测集（i2b2/n2c2 传统）

> 这一系列是"真实病历 + 人工双标 + 裁决"的最成熟传统，各任务均有官方 overview 论文（多为 JAMIA/JBI/JMIR Med Inform），官方数据经 [n2c2 数据门户](https://n2c2.dbmi.hms.harvard.edu/data-sets) 注册 DUA 后发放。**两处与任务书表述的更正**：(1) "n2c2 2018 药物依从性"——2018 年两个 track 实为 Track 1 临床试验队列筛选、Track 2 ADE/用药抽取；(2) "n2c2 2019 ADE/用药"——2019 年 n2c2 的任务是临床语义文本相似度、家族史抽取与概念规范化，**无 ADE 任务**；(3) "SemEval-2015 Task 6（关系模板）"——实际 Task 6 是 **Clinical TempEval**（临床时间关系），下文按官方论文更正覆盖。

#### B1. i2b2 2006 去标识化（De-identification）挑战

- **来源**：Uzuner, Luo, Szolovits, "Evaluating the state-of-the-art in automatic de-identification"，[JAMIA 2007（PMC1975792）](https://pmc.ncbi.nlm.nih.gov/articles/PMC1975792/)。
- **数据**：Partners HealthCare 出院小结 889 份（train 669 / test 220，随机划分）；8 类 PHI（患者/医生/医院/ID/日期/地点/电话/90 岁以上年龄）。
- **gold 构建**：先由自动去标识系统预标，3 名标注者（本科/研究生学生 + 1 名教授）串行三遍人工校验，分歧讨论定稿；真实 PHI 替换为合成 surrogate（保留格式、共指一致与相对日期偏移）。**未报告 κ**。
- **split/泄漏**：随机按文档切分；作者自述随机切分导致 OOV PHI 与歧义分布在 train/test 不均（教训：切分要分层）。
- **指标**：token 级与 MUC 式 instance 级 P/R/F1；置换检验显著性别。
- **局限（作者自述）**：系统利用机构特定文档结构过拟合；地点/电话识别最差；语料小而同质。
- **可借鉴点**：(1) "自动预标 + 人工校验"降低标注成本的标准流水线；(2) 合成 surrogate 需保留共指与时间偏移一致性——对我们构造"决策时点快照"后仍要保留相对时间结构有直接参考。

#### B2. i2b2 2008 肥胖及合并症（Obesity Challenge）

- **来源**：Uzuner, "Recognizing Obesity and Comorbidities in Sparse Data"，[JAMIA 2009（PMC2705260）](https://pmc.ncbi.nlm.nih.gov/articles/PMC2705260/)。
- **数据**：Partners 研究患者数据仓库中超重/糖尿病患者 2004-12 后的出院小结 **1,237 份**（train ~730 / test ~507）；标注肥胖 + 15 项合并症。
- **gold 构建**：**2 名 MGH 减重中心肥胖专科专家**独立标注全部文档，1 名 MGH 住院医师做第三人裁决；文本判断（textual）与直觉判断（intuitive）双轨——后者要求专家从 BMI、用药、化验推断。κ：textual 最低 0.71（高甘油三酯血症）、12 项 ≥0.8、最高 0.94；intuitive 最低 0.44（静脉功能不全）、7 项 >0.8。textual 分歧三人多数票；intuitive 无第三专家，**只取两专家一致为 gold**。
- **指标**：micro/macro 平均 P/R/F1，macro 为主，Z 检验。
- **局限（作者自述）**：Absent/Questionable 类稀疏导致 Questionable F 几乎为 0；textual/intuitive 边界本身模糊。
- **可借鉴点**：(1) "textual（文中明说）vs intuitive（专家推断）"双轨 gold 与本项目"行为一致性 vs 规范性"gold 的区分**同构**，其 κ 差距（intuitive 显著更低）直接预告了规范性标注的一致性风险；(2) "只保留双标一致样本为 gold"是提升 gold 纯度的可行降级策略。

#### B3. i2b2 2009 用药信息抽取（Medication Challenge）

- **来源**：Patrick & Li, "[2009 i2b2 medication extraction challenge](https://pmc.ncbi.nlm.nih.gov/articles/PMC2995676/)" JAMIA 2010；gold 生成专题：Uzuner et al., "[Community annotation experiment for ground truth generation](https://academic.oup.com/jamia/article/17/5/519/831043)" JAMIA 2010。
- **数据**：Partners 出院小结 1,249 份（train 696 / test 533）；抽取药名 + 剂量/途径/频次/疗程/原因等字段。
- **gold 构建**：组织者对 145 份最长 train 文档人工精标——1 名研究者 + 1 名医生**串行标注**（医生先标、研究者修订）；无 κ。评测 gold 另以"**社区标注**"生成：每份文档由 2 个不同参赛队各标 1 人，第三队裁决；社区 gold 对专家 gold 的 F > 0.90。
- **指标**：strict/inexact 匹配下的 P/R/F1（micro 系统级 + macro 患者级）。
- **局限（作者自述）**：reason/duration 识别弱（~50% F）；距临床可信的 ~95% 仍差 5–10 个点。
- **可借鉴点**：(1) **社区标注 + 双人 + 第三人裁决可逼近专家 gold（F>0.90）**——对我们"文本 NER A/B 双标 + 第三人裁决"是直接的历史证据；(2) "提供预标 pool 供修订而非从零标"可显著提速。

#### B4. i2b2/VA 2010 概念、断言与关系

- **来源**：Uzuner, South, Shen, Du, "[2010 i2b2/VA challenge on concepts, assertions, and relations in clinical text](https://pmc.ncbi.nlm.nih.gov/articles/PMC3168320/)" JAMIA 2011。
- **数据**：出院小结与病程记录，train 394 / test 477，另有 877 份未标注文档；来自 Partners、BIDMC、UPMC（与 VA 合办但语料非 VA 病历）。
- **任务**：问题/治疗/检查三类概念抽取；断言（present/absent/possible/conditional/hypothetical/他人）；关系（治疗-问题 TrIP 等 8 种、检查-问题、问题-问题）。
- **gold 构建**：人工精标参考语料；具体标注人数/裁决流程在 JAMIA 在线补充材料，**本文页面未含，κ 未核实**。[概念标注指南公开（i2b2 官网 PDF）](https://www.i2b2.org/NLP/Relations/assets/Concept%20Annotation%20Guideline.pdf)。
- **指标**：exact/inexact P/R/F1 + Z 检验。最优 F：概念 0.852 / 断言 0.936 / 关系 0.737。
- **局限（作者自述）**：关系最难（约 1/4 误分）；低频断言/关系类训练样例稀少；标注本身偶缺上下文，提示 gold 中混有"领域知识推断"成分。
- **可借鉴点**：**断言（assertion）维度**（present/absent/possible/hypothetical/他人）应作为我们 NER 抽取的标配属性——它直接决定"决策时点该信息是否成立、是否属于患者本人"，是防未来信息/伪信息泄漏的语义层工具。

#### B5. i2b2/VA 2011 共指消解（Coreference）

- **来源**：Uzuner et al., "[Evaluating the state of the art in coreference resolution for electronic medical records](https://pmc.ncbi.nlm.nih.gov/articles/PMC3422835/)" JAMIA 2012；[官方标注指南 PDF](https://www.i2b2.org/NLP/Coreference/assets/CoreferenceGuidelines.pdf)。
- **数据**：两库共 978 份（i2b2/VA 814：出院小结+病程记录，5,227 条 gold 链，链均长 4.33；ODIE 164：Mayo/UPMC 多类型报告）；train 590 / test 388。
- **gold 构建**：每份文档 **2 名独立标注者**标共指对，1 名裁决者解决分歧并增删标注，随后二轮再裁决重点查重复与一致性；标注者资质与 κ 在在线附录（页面未含，未核实）。
- **指标**：MUC / B³ / CEAF 三指标均值为主，近似随机化检验。
- **局限（作者自述）**：需要领域知识的共指（缩写、同义、临床关联）系统表现最差；无任何系统全对任何一条链。
- **可借鉴点**：**两轮裁决（首轮解决分歧 + 二轮全局一致性复查）**流程可直接纳入我们的裁决人 SOP。

#### B6. i2b2 2012 时间关系（Temporal Relations）

- **来源**：Sun, Rumshisky, Uzuner, "[Evaluating temporal relations in clinical text: 2012 i2b2 Challenge](https://pmc.ncbi.nlm.nih.gov/articles/PMC3756273/)" JAMIA 2013；配套标注方案论文（[JBI 2013](https://www.sciencedirect.com/science/article/pii/S1532046413001032)）。
- **数据**：Partners/BIDMC 出院小结 310 份（约 17.8 万 token），聚焦病史与住院经过两个时间密集段落。
- **gold 构建**：**8 名标注者（4 名医学背景）双标 + 第三人裁决**；指南基于 TimeML 改造（融合 THYME 中间版），事件/时间表达/tLink 三层。IAA（exact/partial）：EVENT span 0.83/0.87、type 0.93/0.90；TIMEX3 span 0.73/0.89；**TLINK span 仅 0.39、type 0.79/0.30**——因一致性过低，7 类 tLink 合并为 3 类（BEFORE/AFTER/OVERLAP），两版标注都发布。
- **指标**：EVENT span F、TIMEX3 span F × 值准确率、TLINK F（含时间闭包传递）。
- **局限（作者自述）**：相对时间归一化（"次日晨""住院第 5 天"）与候选对选择未解决；低 IAA 类目被迫合并。
- **可借鉴点**：(1) **IAA 过低的类目应合并或重定义再发布**，不要硬留噪声 gold；(2) 相对时间表达是中文病历同样存在的问题，时间归一化必须进入我们的 NER 规范。

#### B7. i2b2/UTHealth 2014 危险因素（糖尿病/冠心病）

- **来源**：Stubbs, Kotfila, Xu, Uzuner, "[Identifying risk factors for heart disease over time: Overview of 2014 i2b2/UTHealth shared task Track 2](https://pmc.ncbi.nlm.nih.gov/articles/PMC4978189/)" JBI 2015（[PubMed 26210362](https://pubmed.ncbi.nlm.nih.gov/26210362/)）。注意：语料来自 **Partners HealthCare**（非 MIMIC-III 文本；任务书表述有误），PHI 替换为合成 surrogate 后经 n2c2 门户发放。
- **数据**：296 名糖尿病患者的 **1,304 份纵向记录**（每患者 2–5 份），三个队列均衡：首份记录时已有 CAD、随访中新发 CAD、始终无 CAD；**train 790 / test 514（60/40，按患者整体切分，三队列在两侧均衡）**。
- **任务**：文档级标注 CAD 危险因素（糖尿病、高脂血症、高血压、肥胖、吸烟、早发 CAD 家族史、CAD 本身 + 指标/用药）及其相对文档时间（before/during/after/continuing）。
- **gold 构建**：**7 名医学背景标注者（1 MD、5 RN、1 医疗助理）**，每份文档 3 人独立标注，**多数票定 gold**；采用"轻量标注范式"平衡时间与可靠性；overview 未报 κ（细节在配套标注论文 Stubbs & Uzuner）。
- **指标**：文档级 micro P/R/F1 + 近似随机化检验。
- **局限（作者自述）**：数值型指标（A1c、血压等）识别远差于文字提及（表格转文本破坏结构）；"ever smoker"多队 F=0；未做患者内记录链接，不能直接研究疾病进展。
- **可借鉴点**：(1) **患者级 split + 队列均衡分层**是本系列中最接近我们需求的设计；(2) "医生/护士/医助混编 + 三人多数票"说明非 MD 标注者在结构化任务上可用，但数值/时间细粒度项误差大——我们的 NER 双标人员配置可参照。

#### B8. n2c2 2018 Track 1：临床试验队列筛选（Cohort Selection）

- **来源**：Stubbs, Filannino, Soysal, Henry, Uzuner, "[Cohort selection for clinical trials: n2c2 2018 shared task track 1](https://pmc.ncbi.nlm.nih.gov/articles/PMC6798568/)" JAMIA 2019。
- **数据**：**复用 2014 i2b2/UTHealth 纵向语料**——288 名糖尿病患者（每人 2–5 份记录，约 78 万 token）；13 条入选/排除标准改自 ClinicalTrials.gov 真实试验（药物滥用、酗酒、6 个月内心梗、HbA1c 6.5–9.5%、肌酐等）。
- **gold 构建**：**2 名医学背景标注者**独立对每名患者每条标准给 met/not met/possibly met 并标证据文本，裁决由 A.S.（含 MD 咨询 E.S.）完成，"possibly"最终并入二值。**Cohen κ 平均 0.54**；偏态类目 κ 低至 −0.1（KETO-1YR），非偏态低分项 ADVANCED-CAD 0.37、MI-6MOS 0.63；主要误差=漏看证据。
- **split/泄漏**：**患者级 70/30**（202 train / 86 test），按标准频率近似分层；test 仅开放 3 天评测窗口、每队限 3 次提交。
- **指标**：患者级 micro P/R/F1。47 队参赛；冠军为**规则系统 F1=0.91**，前十无纯 ML 系统。
- **局限（作者自述）**：病历开放解释空间大，"severe disease"等欠定义标准迫使标注者动用直觉，gold 有噪声；标签偏态扭曲 κ 与指标。
- **可借鉴点**：(1) 这是**"以真实试验标准对患者做 met/not met 判定"**的最成熟先例——与我们"检查检验选择/转诊判断"的患者级 MCQ 构造最接近；(2) κ 平均仅 0.54 + 偏态类目 κ 为负，说明**含时间窗的标准（如"6 个月内"）必须配显式时间推理规则与培训**；(3) 3 天封闭测试窗 + 限次提交的防过拟合操作值得效仿。

#### B9. n2c2 2018 Track 2：ADE 与用药抽取

- **来源**：Henry, Buchan, Filannino, Stubbs, Uzuner, "[2018 n2c2 shared task on adverse drug events and medication extraction in electronic health records](https://pubmed.ncbi.nlm.nih.gov/31584655/)" JAMIA 2020;27(1):3-12（doi:10.1093/jamia/ocz166；开放获取版 [PMC7489085](https://pmc.ncbi.nlm.nih.gov/articles/PMC7489085/)）；[n2c2 官方数据页](https://n2c2.dbmi.hms.harvard.edu/data-sets)。
- **数据**：**505 份 MIMIC-III 出院小结**（train 303 / test 202——[参赛论文交叉证实](https://pmc.ncbi.nlm.nih.gov/articles/PMC7489056/)），含 9 类实体（drug、strength、dosage、duration、frequency、form、route、reason、ADE）与关系。
- **任务**：概念抽取 / 关系分类 / 端到端三档。
- **gold 构建**：**每份记录由 2 名标注者独立标注、第 3 名标注者裁决分歧**（Henry et al. 2020 原文 "Each record … annotated by 2 independent annotators while a third annotator resolved conflicts"；经开放获取版 [PMC7489085](https://pmc.ncbi.nlm.nih.gov/articles/PMC7489085/) 核实，详见方法学笔记专题 2）；overview 正文**未报告 IAA 数字**。
- **指标**：strict/lenient 匹配 P/R/F1；最优 F：概念 0.9418、关系 0.9630、端到端 0.8905；ADE 与 Reason 类显著更差。
- **访问**：n2c2 门户注册 + DUA（因底库为 MIMIC-III，访问亦受 PhysioNet 体系约束——推断）。
- **可借鉴点**：(1) **MIMIC 文本 + 独立人工 gold** 的先例，说明在 MIMIC-IV-Note 上叠加我们自己的 NER 标注完全可行且社区接受；(2) "reason"（用药理由）与 ADE 的低分提示：隐含因果/适应证语义是 LLM 时代仍值得专门建 gold 的难点。

#### B10. n2c2 2019（更正说明）与 SemEval-2015 Task 6（Clinical TempEval）

- **n2c2 2019**：任务为 [Clinical Semantic Textual Similarity](https://medinform.jmir.org/2020/11/e23375)、家族史抽取、[概念规范化（UMass Lowell）](https://pmc.ncbi.nlm.nih.gov/articles/PMC7647359/)；**并无 ADE/用药任务**（ADE 在 2018 Track 2）。
- **SemEval-2015 Task 6 = Clinical TempEval**（Bethard, Derczynski, Savova, Pustejovsky, Verhagen，[ACL Anthology S15-2136](https://aclanthology.org/S15-2136/)；非"关系模板"）。语料为 **Mayo Clinic THYME 结肠癌患者**的临床记录与病理报告 **440 份（train 293 / test 147）**，THYME-TimeML 标注（DocTimeRel + CONTAINS 型 tLink，其余关系因样本过少弃用；数据统计见 [ACM 时间关系综述](https://dl.acm.org/doi/fullHtml/10.1145/3462475)）。当年仅 2 队参赛（数据授权流程漫长）。
- **可借鉴点**：THYME 的 **DocTimeRel**（事件相对文档时间的 BEFORE/OVERLAP/AFTER）是"叙事时间 vs 记录时间"的最小完备标注集，可作为我们判断"文本内容发生在决策时点之前/之后"的现成语义框架。



### C. 放射/报告理解评测集

#### C1. MIMIC-CXR / MIMIC-CXR-JPG（Scientific Data 2019 + PhysioNet）

- **来源**：Johnson et al., [Sci Data 2019 论文](https://www.nature.com/articles/s41597-019-0322-0) | [MIMIC-CXR PhysioNet](https://physionet.org/content/mimic-cxr/2.0.0/) | [MIMIC-CXR-JPG v2.1.0](https://physionet.org/content/mimic-cxr-jpg/2.1.0/)。
- **数据与队列**：BIDMC 急诊 2011–2016 胸片；377,110 张 DICOM / 227,835 个 study / 约 65,000 名患者，每 study 一份自由文本报告；HIPAA Safe Harbor 去标识（图像烧录字样 OCR 检测后遮黑，文本 PHI 置为 "___"，日期伪随机平移但保留相对时序）。
- **任务与题型**：图文多模态；下游评测主要用**报告文本规则派生的 14 类病理标签**（ CheXpert labeler）与报告理解任务。
- **gold 构建（重点）**：[CheXpert labeler](https://github.com/stanfordmlgroup/chexpert-labeler)（基于 NegBio）三段式：提及抽取（含同义词/缩写）→ 每提及判 positive/uncertain/negative → 按正>不确定>负聚合成 study 级标签；"No Finding" 仅当其余标签皆阴/未提及时为正。**这是"从报告文本用规则抽取衍生 gold"的原型**。另有 1 名放射科医师人工标注的 test set（`mimic-cxr-2.1.0-test-set-labeled.csv`）用于评估 labeler 本身（单人标注——页面明示的局限）。
- **split 与泄漏**：官方 `mimic-cxr-2.0.0-split.csv.gz` 按 dicom_id 给 train/validate/test；PhysioNet 页面未显式声明患者级隔离（未核实）；时间维度仅保留相对时序（日期平移）。
- **指标**：下游 AUROC 等（社区约定），本体未定义单一指标。
- **发布与访问**：PhysioNet credentialed（CITI + DUA 1.5.0），禁止再分发/再识别，发表须公开代码。
- **局限（页面自述）**：标签为报告文本弱标签而非图像直标；uncertain(-1.0)/missing 语义含混；报告模板漂移与书写者差异影响标签；JPG 有损压缩 + 直方图均衡。
- **可借鉴点**：(1) "规则 labeler 派生全库标签 + 抽样专家标注评估 labeler 本身"两件套，是我们"结构化事件流水线 + 人工门禁抽验"的同构设计；(2) 日期平移但保留相对时序，是"可做时间推理但不可再识别"的平衡范式。

#### C2. CheXpert（AAAI 2019，斯坦福）

- **来源**：Irvin et al., [CheXpert: A Large Chest Radiograph Dataset with Uncertainty Labels and Expert Comparison](https://ojs.aaai.org/index.php/AAAI/article/view/3834)（[arXiv 1901.07031](https://arxiv.org/abs/1901.07031)）| [labeler 代码](https://github.com/stanfordmlgroup/chexpert-labeler) | [竞赛页](https://stanfordmlgroup.github.io/competitions/chexpert/)。
- **数据与队列**：斯坦福医院 65,240 名患者的 224,316 张胸片（2002–2017，推断自原文设置）。
- **任务**：14 类病理的胸片分类，标签三值（阳性/不确定/阴性）。
- **gold 构建（重点）**：规则 labeler 从报告自动打标（提及匹配 + 上下文否定/不确定词 + 聚合优先级）；**labeler 验证**：与 1 名 board-certified 放射科医师在 500 份报告样本上比对（分歧报告经裁决），按 14 观测给出敏感度/特异度列联表，平均准确率约 93.6%、uncertain 提及约 86.8%（数字来自 [arXiv 论文 Table 2 的检索转述](https://arxiv.org/pdf/1901.07031)，未逐字核读 PDF）。**竞赛验证集**另由 3 名 board-certified 放射科医师对 200 张胸片独立标注并裁决形成参考标准。
- **split 与泄漏**：train/validation（无标签，供自评）/test；患者级隔离策略未在已读页面明示（未核实）。
- **指标**：per-observation AUROC + 与 3 名放射科医师共识比对的专家一致性分析（论文核心卖点：模型与专家间一致性接近专家间一致性）。
- **发布与访问**：图像与报告经斯坦福方协议申请（非 PhysioNet）；labeler 开源。
- **局限**：规则 labeler 对 uncertain 类最弱；报告书写偏倚传导为标签噪声；标签为 study 级。
- **可借鉴点**：(1) "**不确定"作为一等标签值**（而非硬二值）直接适用于我们的 MCQ 选项设计（"尚不能确定/需补充检查"可以是合法选项）；(2) "模型 vs 专家、专家 vs 专家"双对照的一致性报告框架，可平移为"LLM vs 标注者、标注者 vs 裁决 gold"的报告设计。

#### C3. RadGraph（NeurIPS 2021 D&B，斯坦福 AIMI）

- **来源**：Jain et al., [arXiv 2106.14463](https://arxiv.org/abs/2106.14463) | [NeurIPS 2021 论文](https://datasets-benchmarks-proceedings.neurips.cc/paper/2021/file/c8ffe9a587b126f152ed3d89a146b445-Paper-round1.pdf) | [GitHub](https://github.com/Stanford-AIMI/radgraph)。
- **数据与队列**：MIMIC-CXR 报告；**dev 集 500 份报告由 board-certified 放射科医师标注（14,579 实体 + 10,889 关系）**；test 集 100 份（MIMIC-CXR 与 CheXpert 各半）**每份两套独立放射科医师标注**用于人类基线；另有 220,763 份 MIMIC-CXR 报告的机器标注推理集（~600 万实体/~400 万关系，RadGraph-large 的来源）。
- **任务**：报告实体（解剖部位/观察等）+ 属性（否定、不确定、时间变化）+ 关系（位于/修饰/提示等）的结构化抽取。
- **gold 构建**：schema 基于 Dykstra 放射信息抽取 schema 设计；标注者均为 board-certified 放射科医师；**人类一致性以双标注 F1 表示**（具体数值在全文表格，未逐字核读 PDF）；基准模型关系抽取 micro F1 0.82（MIMIC-CXR）/0.73（CheXpert）。
- **split 与泄漏**：dev/test 按报告划分；患者级隔离未明示（未核实）。
- **指标**：实体/关系 micro F1（对齐人类双标 F1 报告）。
- **发布与访问**：论文称数据集 freely available；实际分发经其 GitHub 指引（底库 MIMIC-CXR 需 PhysioNet credentialed——推断）。
- **局限**：500 份人工标注规模有限；schema 面向胸片报告，跨模态/跨科室需扩展。
- **可借鉴点**：(1) "**专家双标 F1 作为人类天花板并公开报告**"是最值得抄的评测诚实性实践；(2) "小而精人工 gold + 大规模机器标注扩展（silver）"的 RadGraph-large 路线，可对应我们"人工标注门禁 + LLM 辅助全量预标"的组合。



### D. 衍生标签临床预测套件与表型算法验证

#### D1. MIMIC-IV benchmark 套件（MIMIC-IV-Data-Pipeline，healthylaife）

- **检索与线索核对（2026-08-16）**：按任务书线索逐条核对——GitHub 用户 **"healthylauren" 不存在**（GitHub API 返回 404，`healthylauren/MIMIC-IV-Benchmark` 仓库亦 404）；**未找到**题为 "MIMIC-IV benchmark suite" 的 Scientific Reports 2023 论文（多轮检索无命中）。实际可核实的最接近实体是 **Gupta et al. 的 MIMIC-IV-Data-Pipeline**（仓库 [healthylaife/MIMIC-IV-Data-Pipeline](https://github.com/healthylaife/MIMIC-IV-Data-Pipeline)，疑为任务书 "healthylauren" 之误；"作者 Wang" 疑与 MIMIC-III 时代前作 MIMIC-Extract (Wang et al. 2020) 混淆——此两句为【推断】）。官方 MIMIC 团队（MIT-LCP GitHub 组织）名下**无** benchmark 仓库（已逐一核对其 repo 列表，未核实到官方套件）。
- **来源**：Gupta, Gallamoza, Cutrona, Dhakal, Poulain, Beheshti, "An Extensive Data Processing Pipeline for MIMIC-IV"，[ML4H 2022，PMLR v193: 311–325](https://proceedings.mlr.press/v193/gupta22a.html)（[PMC9854277](https://pmc.ncbi.nlm.nih.gov/articles/PMC9854277/)）| [GitHub 仓库](https://github.com/healthylaife/MIMIC-IV-Data-Pipeline)（MIT 许可）| 2026 年多模态扩展版：[arXiv 2601.11606](https://arxiv.org/abs/2601.11606)。
- **预测任务**（PMC 原文核实）：4 大类任务 × 4 种慢性病（心衰/CKD/COPD/CAD）= **16 个预测任务**——
  - **死亡率**：基于入院首 **24/48/72（可自定义）小时**数据的死亡预测；
  - **LOS**：住院时长超过用户定义阈值（1–10 天）的二分类，输入窗 12/24/自定义小时；
  - **再入院**：前次出院后用户定义窗口（10–150 天）内的再入院预测（论文原文为 "readmission"，**未区分"ICU 再入"与普通再入院**——任务书"ICU 再入"表述未核实到）；
  - **表型**：预测**下次就诊**的 4 种慢病标签（作者说明：因 MIMIC 仅在入院时记录诊断，故不采用回顾式打标）。
- **标签如何从结构化字段派生**：完全**规则派生、无人工标注**——队列按入院 ICD-10 诊断前缀选取（心衰 I50、CKD N18、COPD J44、CAD I25，ICD-9 先转换为 ICD-10）；再入院标签取自入院/出院时间字段；年龄由 `anchor_year` 与 `anchor_age` 相减派生。特征来自诊断/操作/用药/化验/生命体征 + 人口学字段。
- **数据切分**：论文原文为 **5 折交叉验证、80% 训练 / 20% 测试，训练集内再随机抽 10% 作验证集**；**论文未声明切分为患者级**（样本级 vs 患者级未说明——未核实，这一点对该套件的泄漏控制是实质性缺口）。
- **发布与访问**：GitHub 发布**代码 + 可复现的配置记录**（cleaning/imputation/分箱等步骤可记录重放），**数据不随仓库分发**——README 明示须先经 [PhysioNet credentialed access](https://physionet.org/about/citi-course/) 自行下载 MIMIC-IV（支持 v1.0/2.0/3.1、MIMIC-IV-Note 等）。
- **对本项目的可借鉴点**：(1) "任务配置化 + 配置留痕保证可复现"的工程模式值得纳入我们的流水线；(2) 其切分**未声明患者级**恰好从反面说明：衍生标签套件若不做患者级隔离，同一患者多次入院横跨 train/test 会直接虚高指标——我们的评测集必须显式做患者级切分并写入文档；(3) 表型任务"预测下次就诊标签"的设计，是把"诊断码作为 gold"这一弱标签的时序缺陷（入院才记码）显式处理掉的少见例子。

#### D2. eMERGE 表型算法验证（Newton et al. 2013 JAMIA）

- **来源**：[PMC3715338](https://pmc.ncbi.nlm.nih.gov/articles/PMC3715338/)（以下数字转述自本项目方法学笔记专题 1，**详见方法学笔记专题1**，此处未重新联网核实）。
- **来源数据**：eMERGE 网络多站点 EHR——各站点用本地 EHR 的结构化字段（诊断码/用药/化验等）运行表型算法（规则 + 逻辑回归组合）产生病例候选，再回到**源病历**做人工复核。
- **验证设计**：每个表型算法在每站点人工复核 **50–200 例**（样本量"somewhat arbitrary"，按算法复杂度定）；结果以 **PPV（PV+）** 报告，case 与 control 分别计算；全部 13 个算法的 PV+ 为 **67.7%–100%**，约四分之三 ≥ 90%，仅 3 个结果 < 80%。复核者配置：部分站点用医生按书面 eligibility guide 复核；Northwestern 用**两名临床研究员独立复核 + 医生裁决不一致项**；其他站点用受训 abstractor + 结构化摘录表 + codebook。该文**未报告 reviewer 间一致性（κ），也未报告 PPV 置信区间**。
- **对本项目的可借鉴点**（评测集构建角度）：衍生标签预测任务的 gold 质量**必须用人工病历复核来验证**，且验证对象是"派生标签"本身而非模型——(1) 以 PPV 为主指标、case/control 双侧分别抽样计算；(2) 50–200 例/算法/站点的量级证明百例级试审足以给出可解释的 PPV；(3) eMERGE 未报告的 κ 与 CI 正是我们要补上的报告项（项目应报告 reviewer 间一致性与 PPV 置信区间）。

#### D3. PheCAP（Nature Protocols，电子表型高吞吐流程）

- **来源**：[PMC7323894](https://pmc.ncbi.nlm.nih.gov/articles/PMC7323894/)（以下数字转述自本项目方法学笔记专题 1，**详见方法学笔记专题1**，未重新联网核实）。
- **来源数据**：通用电子表型框架——用 ICD/用药等结构化特征作"代理表型"（surrogate phenotype）+ 惩罚回归机器学习，从任意 EHR 数据库高通量识别病例。
- **验证设计**：领域专家人工复核**随机抽样约 200 例**（≥100 训练 + ≥100 独立验证）；标签为**三级**：definite / possible / no（possible 的归并方向会改变 PPV，须预先决定）；**至少 10 例双人复核评估一致性**，分歧通过讨论解决并**更新表型定义**（验证是迭代闭环而非一次性审计）；另建议抽 5 组随机候选集与全库比较年龄/性别/关键 ICD 分布，检查代表性。
- **对本项目的可借鉴点**：(1) "三级置信标签 + possible 归并规则预先写死"避免强迫复核者在边界案例上二选一，可直接平移到我们术语归一化试审（match / possible / no-match）；(2) "分歧 → 讨论 → 更新表型定义 → 版本化"的闭环，说明人工复核的产出应包括**规则变更**而不仅是一次性纠错；(3) 随机候选集 vs 全库的分布比对，是检查"机器预标样本是否代表全库"的现成方法。

> **D 组与 A–C 组的本质区别**：A–C 组的 gold 最终落在**文本/图像内容的人工判定或模板查询**上（即便是程序派生的 EHRXQA，其模板 SQL 也由人工编写并迭代修订；EHRSQL/DrugEHRQA 的问题还来自真实工作人员需求）；D 组的标签则**完全由结构化字段的规则派生**（ICD 前缀、出入院时间、`anchor_age` 算术、表型算法输出），人工复核的角色从"直接产生 gold"变为"**验证派生标签的质量**"（eMERGE/PheCAP 的 PPV 验证范式）。对本项目的含义：我们的结构化事件流水线（术语归一化映射、事件派生）属于 D 组模式——gold 是规则的产物，人工复核的任务是量化规则的 PPV 并驱动规则迭代；而 NER 与临床决策 MCQ 属于 A–C 组模式——人工标注直接产生 gold，一致性门禁本身就是质量。两条线的质量保障手段应分开设计。

## 4. 跨数据集可复用构建经验小结

以下各条均综合自上文 A–D 组已核实内容，每条注明来源数据集。

1. **gold 构建有三种成熟模式，各有适用边界**：(a) **程序/模板派生**（EHRXQA、EHRSQL、DrugEHRQA——人工写模板 SQL，gold = 在库上执行返回值）：最廉价、可大规模，但只覆盖"可查询事实"，无法覆盖规范性决策，且 EHRXQA 作者自认不含 unanswerable；(b) **规则 labeler 从文本派生**（CheXpert、MIMIC-CXR 14 类标签、D 组 MIMIC-IV-Data-Pipeline 的 ICD/时间规则）：可全库打标，但 uncertain 语义最弱、书写偏倚传导为标签噪声，必须配抽样人工验证；(c) **人工双标 + 第三人裁决**（B 组 i2b2/n2c2 全系、RadGraph、CheXpert 竞赛验证集）：gold 质量最高、成本最高。选择准则：检索式/可执行事实可用 (a)+(c) 抽验；语义、推断、规范性判断必须 (c)。
2. **IAA 实测区间决定任务可行性预期，低一致类目要处理而非硬留**：文本明说类 κ 可达 0.71–0.94（i2b2 2008 textual），推断类可低至 0.44（2008 intuitive 静脉功能不全）；含时间窗的真实试验标准平均 κ 仅 0.54、偏态类目可至 −0.1（n2c2 2018 T1）；关系/链接类 span 一致性可低至 0.39（i2b2 2012 TLINK）。成熟处理法：**合并类目**（2012 把 7 类 tLink 并为 3 类、两版标注都发布）或**只保留双标一致样本为 gold**（2008 intuitive 轨）。
3. **患者级切分 + 分层是 leakage 控制的基线配置**：i2b2/UTHealth 2014 按患者整体切分并令三队列在 train/test 两侧均衡；n2c2 2018 T1 患者 70/30 且按标准频率近似分层；EHRXQA 的 silver/gold 子库按患者分离。反面教训：i2b2 2006 随机按文档切分导致 OOV PHI 与歧义分布不均（作者自述）；D1 的 MIMIC-IV-Data-Pipeline 论文未声明患者级切分（未核实）——衍生标签套件同样存在同一患者多次入院横跨两侧的风险。
4. **"预标 + 人工校验"是控制标注成本的标准流水线**：i2b2 2006 用自动去标识系统预标、3 名标注者串行三遍校验；i2b2 2009 给参赛队提供预标 pool 供修订而非从零标；B3 的社区标注（每文档 2 队各 1 人 + 第三队裁决）对专家 gold 的 F > 0.90，证明"多人 + 裁决"可逼近专家质量。
5. **把 uncertain / unanswerable 作为一等公民**：CheXpert 三值标签（阳/不确定/阴）直接支持"尚不能确定"类选项；EHRSQL-2024 把 answerable/unanswerable 分开并奖励正确弃答；n2c2 2018 T1 的 "possibly met"（虽最终并入二值）与 RadGraph 的"不确定"属性同属此思路。对"决策时点信息不足"的场景，弃答/不确定必须是合法的 gold 类目而非噪声。
6. **"小人工 gold + 大机器 silver"的分层设计**：RadGraph 用 500 份人工精标 + 220,763 份机器标注扩展出 RadGraph-large；EHRXQA 的 train/valid 用 Chest ImaGenome silver 子库（800 患者）、test 用 gold 子库（400 患者）。人工 gold 用于校准与门禁、机器 silver 用于规模，两者按患者分离——可直接映射到我们"人工标注门禁 + LLM 辅助全量预标"的组合。
7. **共享任务要配套防过拟合机制**：n2c2 2018 T1 的 test 仅开放 3 天评测窗口、每队限 3 次提交；MedBench 做题目与 gold 物理隔离 + 动态评测防 shortcut 与答案记忆；EHRSQL-2024 走 Codabench 托管。评测集若公开托管，"限次提交 + gold 不出域"应成为默认配置。
8. **发布访问分层：公开代码 + credentialed 数据**：PhysioNet credentialed 系（EHRXQA、DrugEHRQA、MIMIC-CXR——CITI + DUA 1.5.0）；labeler/代码开源而图像另走协议（CheXpert）；用 ODbL 的 MIMIC-IV Demo 做零门槛共享任务、全库留 credentialed（EHRSQL-2024）；跨库许可拼接需用户自行合并（DrugEHRQA 的 n2c2 标注 + PhysioNet 结构化）；D1 pipeline 只发代码、数据由用户凭 PhysioNet 凭证自行下载。"代码可公开复现、患者级数据不出 credentialed 通道"是被反复验证的安全默认。
9. **surrogate/去标识必须保共指与相对时间**：i2b2 2006 的合成 surrogate 保留格式、共指一致与相对日期偏移；MIMIC-CXR 日期伪随机平移但保留相对时序。去标识破坏的不是"文本像不像真的"，而是评测所依赖的**时间推理结构**——对"决策时点快照"类评测，surrogate 化必须保留相对时间与共指链。
10. **专家双标 F1 作为人类天花板公开报告**：RadGraph 的 test 集每份两套独立放射科医师标注、以双标注 F1 报告人类一致性；CheXpert 用"模型 vs 3 医师共识、医师 vs 医师"双对照框架。评测报告应把 LLM 成绩与"标注者之间的一致上限"并列呈现，否则无法区分"接近人类"与"超过 gold 噪声底"。

**综合推论**（承接方法学笔记）：本项目的两条 gold 生产线恰好各取一种成熟模式——结构化事件流水线走 D 组"规则派生 + PPV 式人工验证"路线，NER 与 MCQ 走 B/C 组"双标 + 裁决 + IAA 门禁 + 人类天花板报告"路线；发布走第 8 条的分层访问模式，评测托管配第 7 条的防过拟合机制。
