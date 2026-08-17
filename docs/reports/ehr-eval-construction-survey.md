# 真实世界 EHR 构建评测集：调研主报告

> 调研日期：2026-08-16
> 输入材料：本次新完成的两份证据笔记——[基准/数据集普查](ehr-eval-construction-survey-benchmarks.md)（17 个数据集/benchmark，A 结构化 QA、B i2b2/n2c2 共享任务、C 报告理解、D 衍生标签套件）、[方法学深挖](ehr-eval-construction-survey-methodology.md)（五个专题：病历复核、标注科学、LLM 参与边界、合规发布、文档化/污染/统计）——以及项目已有的 [五维 MCQ 综述（2026-08-10）](benchmark-five-dimension-evidence-review.md)。本报告只做决策层综合，事实细节与引用一律见两份笔记。

## 1. 核心结论

1. **真实 EHR 评测集的 gold 构建只有三种成熟模式**：程序/模板派生（EHRXQA/EHRSQL）、规则 labeler 从文本或结构化字段派生（CheXpert/MIMIC-CXR/MIMIC-IV-Data-Pipeline）、人工双标+第三人裁决（i2b2/n2c2 全系、RadGraph）。没有第四种。项目当前的**两条 gold 生产线恰好各对应一种**：结构化事件流水线（归一化映射、事件派生）= 规则派生 + PPV 式人工验证（eMERGE/PheCAP 范式）；NER 与临床决策 MCQ = 人工双标 + 裁决 + IAA 门禁。两条线的质量保障手段必须分开设计，不能用同一把尺子验收。
2. **"行为 gold vs 规范性 gold"的构念区分有直接的实证先例**：i2b2 2008 肥胖挑战的 textual（文中明说，κ 0.71–0.94）与 intuitive（专家推断，最低 κ 0.44）双轨，与我们两条轨道同构——**推断/规范性判断的标注一致性天然显著更低**，这是已发表 18 年的规律，应在规范性 gold 的专家裁定流程设计中被正面接受（双专家独立 + 第三人裁决 + 分歧改题/删题），而不是期待高 κ。
3. **两个人工标注门禁的阈值都有可引的实测锚点**：实体 span 双标 F1 ≈ 0.80（THYME 0.8038、Stubbs 0.895、RadGraph 人类双标口径）；关系/链接类 0.45–0.56 是已发表常态（THYME TLINK、i2b2 2012 span 0.39 靠合并类目解决）；含时间窗的判定平均 κ 仅 0.54（n2c2 2018 队列筛选）。因此建议：**实体 F1 ≥ 0.80 解锁、关系 F1 ≥ 0.55 解锁、属性 κ/α ≥ 0.667 底线**，按类型分报；归一化试审按 **PPV + Wilson 95% CI** 报告，下界 ≥90% 放行。
4. **LLM 可以起草，不能单独产 gold，且专家修改率必须逐题留痕**：GPT-4 做 i2b2 概念抽取 exact F1 仅 0.593（低于微调 BERT 0.785，span 边界不可靠）；EHRNoteQA 1,000 题经 3 名医生 2 个月审校，约 24% 题干被改或删。这为项目"LLM 输出一律 `unreviewed_model_output`、不能反向替代人工 gold"的现行纪律提供了正面文献支持——该纪律应继续执行，并从现在开始逐题记录修改类型（这是事后无法补采的字段）。
5. **发布走"代码公开 + 数据 credentialed"默认模式**：PhysioNet License 1.5.0 并不禁止派生数据集发布，而是要求派生物本身经 credentialed 通道发布（EHRNoteQA 即先例：代码 MIT 开源 + 962 题 PhysioNet credentialed）。香港站点必须自行完成 credentialing，项目只能传代码与 ID 列表。
6. **污染与统计是同类基准的公认短板，也是最容易超车的地方**：预训练语料 Dolma 含 99.21% 的 MedQA 测试题；26 个医学 LLM 基准的系统综述显示统计严谨性 rarely reported。项目发布应配齐"五件套"：数据本体 + datasheet + canary/私有镜像 + bootstrap CI 与多重比较校正 + TRIPOD+AI 式外部验证报告。

## 2. gold 构建三种模式与项目映射

| 模式 | 代表 | gold 怎么来 | 质量保障 | 项目对应 |
|---|---|---|---|---|
| 程序/模板派生 | EHRXQA、EHRSQL、DrugEHRQA | 人工写模板 SQL，gold = 库上执行返回值 | 模板人工迭代；不覆盖规范性判断 | 无直接对应（快照字段白名单查询可算半个） |
| 规则 labeler/结构化派生 | CheXpert、MIMIC-CXR 14 类、MIMIC-IV-Data-Pipeline、eMERGE 表型 | 规则全库打标 | **抽样人工复核验证标签质量**：CheXpert 500 份 vs 1 名放射科医师；eMERGE 50–200 例/算法报 PPV；PheCAP ~200 例三级标签 | **结构化事件流水线**：归一化映射、事件派生规则 → 100 条试审即此范式 |
| 人工双标 + 第三人裁决 | i2b2/n2c2 全系、RadGraph、CheXpert 竞赛验证集 | 2 人独立标注 + 第 3 人裁决（n2c2 2018 原文口径） | IAA 门禁 + 裁决 + 脚本查漏 + 人类天花板公开报告 | **NER 双标**、**MCQ 临床审核**、**规范性 gold 专家裁定** |

反面教训同样有用：MIMIC-IV-Data-Pipeline 论文**未声明患者级切分**（同一患者多次入院可能横跨 train/test 虚高指标）——项目"患者级 split 先于一切规则挖掘"的现行合同方向正确，必须坚持并写入 datasheet。

## 3. 标注质量的可量化基线（门禁阈值推导依据）

| 任务类型 | 实测一致性 | 来源（详见笔记） |
|---|---|---|
| 文本明说类判断（textual） | κ 0.71–0.94 | i2b2 2008 |
| 推断类判断（intuitive） | 最低 κ 0.44 | i2b2 2008 |
| 含时间窗的试验标准判定 | 平均 κ 0.54，偏态类目可至 −0.1 | n2c2 2018 T1 |
| 实体 span 双标 | F1 0.80–0.90 | THYME 0.8038、Stubbs 0.895 |
| 关系/链接 | F1 0.39–0.56（低一致类目靠合并解决） | i2b2 2012、THYME |
| 社区标注 vs 专家 gold | F > 0.90 | i2b2 2009 |
| 规则 labeler vs 1 名医师 | 平均准确率约 93.6% | CheXpert 500 份验证 |

推导出的操作阈值（标注【推断】者为项目建议值，非文献原文）：

- **NER 门禁**：实体 span F1 ≥ 0.80 解锁；关系 F1 ≥ 0.55 解锁（0.45–0.55 继续迭代指南，不要为凑数改标签定义）；属性 κ/α ≥ 0.667 底线、≥ 0.8 目标（Krippendorff 口径）；按实体类型分报，禁止只报 micro【推断】。
- **归一化试审门禁**：PPV 下界（Wilson 95% CI）≥ 90% 放行；85–90% 定向修复重审；< 85% 返工映射规则【推断】。100 例的 CI 宽度本身够用：95/100 → [88.8%, 97.9%]，能区分"≥90% 放行"与"<85% 返工"两档，但不足以分辨 90% vs 95% 的细差。
- **流程纪律**：先 charter/codebook 后开审（CEA 裁决委员会模式）；分层随机抽样（不能只抽低置信样本——Connolly 2024）；三级标签 match/possible/no 且归并规则预先写死（PheCAP）；分歧必须转化为规则变更并版本化；A 标注员从空白文档开始（pre-annotation 未被证明提高 IAA，反有锚定风险——South et al. 转引）；裁决界面并列显示双方 span diff，分歧登记原因分类；机器辅助脚本查漏（Stubbs 模式）。

## 4. LLM 参与的证据边界

| 用途 | 证据 | 结论 |
|---|---|---|
| NER 预标注 | GPT-4 exact F1 0.593 / relaxed 0.861（Hu 2024，人类 IAA 0.862） | 可起草，span 必须全量人工改；对 A 标注员不可见 |
| 出题起草 | EHRNoteQA 删 38/1000、改 206 题干；EHRNote-ChatQA 11 专家 3 周改 967 样本 | 起草合法，逐题专家过审是必要成本；修改率按 EHRNoteQA 口径披露 |
| gold 生成 | 项目现行纪律：模型输出一律 `unreviewed_model_output` | 文献支持——任何 gold 不得由模型单独产出 |
| LLM-as-judge | GPT-4 vs 3 名医生 κ 0.757–0.880（医生相互 0.808–0.903，EHRNoteQA） | 先在 ≥100 例专家双标上校准 κ ≥ 0.8 才可上岗；judge 不得来自被评模型家族 |
| 独立性 | Alaa 2025、Raji 2021（构念效度批评） | 论文/datasheet 披露出题模型与被评模型关系；出题模型自身成绩单列 |

## 5. 发布与合规

- **默认模式 (i)**：公开 = 构建管线代码（MIT/Apache）+ 题目/选项 + ID 指针；note 原文与快照细节作为 credentialed 资源经 PhysioNet 发布（EHRNoteQA 同构先例）。模式 (ii)（n2c2 式再脱敏+新 DUA 再分发）仅在确需向标注外包方交付时使用内部 DUA 替代；模式 (iii)（Synthea 合成）只做管线冒烟测试。
- **题目内容二次脱敏**：Safe Harbor 18 项做成 CI 扫描（正则 + NER 双通道）；题干避免逐字长引用 note；聚合统计小格子（<11）不发布【推断】。
- **香港适配的合规重估**：本地 PDPO/IRB 不认 HIPAA Safe Harbor；香港站点自行完成 PhysioNet credentialing，项目只传代码 + ID 列表，不传任何患者级数据。

## 6. 防污染、统计与外部验证

- **canary**：项目专属 canary GUID 嵌入每份公开题目文件/README/论文附录（BIG-bench 官方机制）；对外声明前做 canary 复现检测。
- **私有镜像**：按 GSM1k 模式保留一小批永不公开的同分布题目，重大排名结论公开/私有双口径复核。
- **扰动自检**：术语互换/paraphrase 扰动版复测（Gallifant 模式：品牌↔通用名互换后模型一致降 1–10%；Dolma 含 99.21% MedQA 测试题）。
- **统计口径**：主指标必附患者聚类 bootstrap 95% CI（写明重采样次数）；模型两两比较报检验名与 p 值；多模型×多子集结论做多重比较校正并写明方法（Dror 2018：同类论文 110 篇仅 3 篇校正——做了就是超越多数）。
- **外部验证**：香港适配按 TRIPOD+AI 外部验证条目报告（人群差异、校准图、分层性能），不只看 accuracy/AUROC；部署后按 Davis 2017 设事件率/case-mix 监控，**漂移触发式** recalibration（模型约 1 年内出现校准漂移属正常预期）。

## 7. 按当前关键路径的落地清单

对应 README 当前优先级顺序，每项标注本次调研新增/强化的依据：

1. **归一化 100 条试审（最高优先级）**：新增——试审前先成文 charter + codebook（判定标准、边界情形、分歧路径），复核以 PPV + Wilson CI 报告并按三档阈值处置；现有 18 条占位 reviewer 的记录按新 charter 重做。
2. **协议冻结（检查检验任务）**：新增——统计口径（bootstrap CI、多重比较校正方法）在 protocol-lock 里一次锁死；候选目录版本与试审产出的规则变更联动。
3. **snapshot/gold 链路**：新增——i2b2 2008 的 textual/intuitive κ 差距提示：规范性 gold 的双专家流程要预设"分歧率高是常态"，分歧改题/删题优先于多数票。
4. **NER calibration**：新增——实体/关系分设门禁阈值；exact 与 inexact 双口径报告；预标注对 A 标注员隔离；断言（assertion）与 DocTimeRel 式时间属性纳入抽取规范（它们是防语义泄漏的现成语义框架）。
5. **MCQ 闭环**：新增——"uncertain/需补充信息"作为合法选项设计（CheXpert 三值标签先例）；专家修改率从第一题开始留痕；人类天花板（标注者间一致）与 LLM 成绩并列报告（RadGraph 实践）。
6. **香港适配**：新增——TRIPOD+AI 外部验证报告框架 + 漂移触发更新；站点自行 credentialing，只传代码与 ID。

## 8. 三份文档的分工

| 文档 | 回答的问题 |
|---|---|
| 五维综述（2026-08-10） | 五类 MCQ 题怎么设计：构念分轨、snapshot、泄漏三层检查、干扰项、pilot 停止条件 |
| 基准普查笔记 | 别人怎么建的：17 个数据集的队列→任务→gold→标注→发布全流程拆解 |
| 方法学笔记 | 每个环节怎么做对：charter、IAA 计算、阈值、LLM 边界、许可原文、canary、统计、外部验证 |
| 本报告 | 三者拼起来后，项目当前应该改什么、坚持什么 |

## 9. 调研局限

- 检索以英文公开来源为主；MedBench 等中文资源的题目来源与标注细节未能从公开材料核实。
- 任务书点名的 EHRSeqQA、EHRQuest、MedAxon 三个名字未找到可核实实体（普查笔记 A5 记录了最接近的替代品）；"MIMIC-IV benchmark suite"的常见传闻指向 healthylaife/MIMIC-IV-Data-Pipeline，MIT-LCP 官方并无 benchmark 仓库。
- 部分来源的具体数字（如 CheXpert labeler 93.6%、RadGraph 人类双标 F1 数值）来自检索结果转述而非逐字核读 PDF 全文，笔记中已逐处标注。
- Wilson CI 与门禁阈值为方法学推导/项目建议值，已标注【推断】，非文献原文标准。
