 # 医疗 LLM 评测基准：领域全景分析

 > 数据来源：Zotero Collection「模型评测」([zotero://select/library/collections/I7YDA259](zotero://select/library/collections/I7YDA259))
 > 分析日期：2026-08-06 | 文献池规模：1000 篇

 ---

 ## 1. 文献池画像

 ### 总数与类型分布

 | 类型 | 数量 | 占比 |
 |------|------|------|
 | journalArticle | 1000 | 100% |
 | conferencePaper | 0 | 0% |
 | preprint | 0 | 0% |

 数据来源高度集中——全部为期刊论文,无会议论文或预印本。这是因为检索以 WoS 核心合集 + Article/Review 文献类型筛选导入,会议论文(如 CHIL、MLHC)被系统性排除。

 ### 年份分布

 | 年份 | 文献数 | 占比 |
 |------|--------|------|
 | 2025 | 1 | 0.1% |
 | 2026 | 993 | 99.3% |
 | 2027 | 6 | 0.6% |

 文献池几乎全部标注为 2026 年(含部分 2027 在线发表),反映了两个事实:一是 LLM 医疗评测是 2023 年 ChatGPT 发布后才爆发的领域,文献集中在近两年;二是 WoS 检索按相关性排序取前 1000 条,可能优先返回最新文献。重要限制:文献池缺乏 2022-2024 年的早期奠基文献(MedQA/MedMCQA/PubMedQA 原始构造论文),后续分析中的"趋势"判断基于截面数据,无法展现真实的时间演变曲线。

 ### 期刊分布

 | 排名 | 期刊 | 文献数 | 类型定位 |
 |------|------|--------|---------|
 | 1 | Scientific Reports | 32 | 综合性 OA |
 | 2 | NPJ Digital Medicine | 21 | 数字医学(高 IF) |
 | 3 | Frontiers in Medicine | 20 | 临床综合 |
 | 4 | IEEE Access | 19 | 工程/计算 |
 | 5 | J Med Internet Research (JMIR) | 17 | 医学信息学 |
 | 6 | JAMIA | 14 | 医学信息学(旗舰) |
 | 7 | JAMIA Open | 13 | 医学信息学 |
 | 8 | Applied Sciences-Basel | 13 | 工程综合 |
 | 9 | PLoS Digital Health | 13 | 数字医学 |
 | 10 | JMIR Formative Research | 13 | 临床信息 |

 期刊多样性:455 种独立期刊收录,Top 5 仅占 10.9%,Top 10 占 17.5%。高度分散——这是新兴交叉领域的典型特征,尚未形成少数核心期刊垄断。JMIR 系列(JMIR + JAMIA + JAMIA Open + JMIR Med Inform + JMIR Med Educ + JMIR Form Res)合计约 78 篇,是最大的期刊集群。

 ### 摘要覆盖率

 994/1000 = 99.4%。数据质量优秀,可支持可靠的摘要级主题聚类。

 ### 影响因子分布

 | 区间 | 文献数 | 占比 |
 |------|--------|------|
 | 高 IF (>=10) | 125 | 12.5% |
 | 中 IF (3-9.9) | 620 | 62.0% |
 | 低 IF (<3) | 252 | 25.2% |
 | 无 IF 数据 | 3 | 0.3% |

 平均 IF = 6.4 | 中位 IF = 4.6 | 最高 IF = 56.1 (Nature Medicine 级别)

 12.5% 高 IF 文献占比在综述文献池中属于较高水平,说明该领域不仅有量,也有发表在顶级期刊(Nature Medicine IF=52.5、Nature Methods IF=26-56、Lancet Digital Health IF=18)的重磅工作。

 ### 模型提及频次

 | 模型 | 提及 | | 模型 | 提及 |
 |------|------|---|------|-------|
 | GPT-4 | 250 | | DeepSeek | 153 |
 | ChatGPT | 204 | | Claude | 124 |
 | Gemini | 198 | | Llama/LLaMA | 94+94 |
 | GPT-4o | 152 | | GPT-3.5 | 26 |

 GPT-4 系列是评测中被研究最多的模型;DeepSeek(153)和 Claude(124)的提及量已与 Gemini(198)接近,说明评测对象已从"OpenAI 一家独大"转向多模型对比。o1/o3 系列推理模型已开始被评测(26+31 篇)。

 ### 关键信号

 该文献池呈现三个显著特征:(1) 规模与质量并重——1000 篇文献、99.4% 摘要覆盖、12.5% 高 IF,足以支撑领域全景分析和深度选题挖掘;(2) 高度集中在新近——几乎所有文献标注 2026 年,反映这是一个正在急速膨胀的研究前沿,但也意味着缺乏历史纵深;(3) 期刊高度分散——455 种期刊、无单一主导阵地,典型的新兴交叉领域信号。已有 104 篇 survey/review,综述产出密集,新综述必须找到差异化切口。

 ---

 ## 2. 研究主题地图

 基于标题 + 摘要聚类,识别出 10 个主要研究方向(多标签,一篇可属于多个主题)。

 | 编号 | 主题名称 | English label | 代表性关键词 | 文献数(约) | 典型文献 | 判断依据 |
 |------|---------|---------------|------------|-----------|---------|---------|
 | T1 | 医学问答与考试评测 | Medical QA & Examination | MCQ, USMLE, MedQA, question answering, board exam | ~156 | MedHELM (IF=52.5); BRIDGE (IF=26.3); "Beyond multiple-choice questions" (IF=7.8) | 摘要聚类;标题含 benchmark/examination |
 | T2 | 多模态/视觉-语言评测 | Multimodal & Vision-Language | multimodal, VQA, foundation model, medical image, radiology | ~140 | "Advancing conversational diagnostic AI with multimodal reasoning" (IF=52.5); "Medical multimodal LLMs: A survey" (IF=17.4) | 标题关键词 + 摘要 |
 | T3 | 临床推理与决策支持 | Clinical Reasoning & Decision Support | clinical reasoning, differential diagnosis, decision making | ~63 | "Clinical decision support in hematological malignancies using case-grounded AI agent" (IF=52.5); PsychiatryBench (IF=18) | 标题 + 摘要 |
 | T4 | Agent 与临床工作流 | Agentic & Clinical Workflow | agent, agentic, multi-agent, tool use, autonomous | ~58 | EvoMDT (IF=18); "Benchmarking LLM-based agent systems for clinical decision tasks" (IF=18); AgentClinic (IF=18) | 标题 + 摘要 |
 | T5 | RAG 与知识增强 | RAG & Knowledge Enhancement | retrieval-augmented, knowledge graph, GraphRAG | ~51 | DUAL-Know GraphRAG (IF=11.6); "Zero-shot Thoracic Oncologic History Generation Using RAG" (IF=17.6) | 摘要聚类 |
 | T6 | 安全性/幻觉/偏见 | Safety, Hallucination & Bias | hallucination, misinformation, safety, bias, jailbreak | ~38 | "Mapping the susceptibility of LLMs to medical misinformation" (IF=25.5); "Security, Privacy, and Ethical Challenges in LLMs" (IF=12.9) | 摘要聚类 |
 | T7 | 医学教育应用与评估 | Medical Education & Assessment | medical education, student, curriculum, board prep | ~89 | "Psychometric properties of GPT-4o-generated MCQs" (IF=18); "Performance of DeepSeek in question generation for radiology education" (IF=18) | 标题 + 摘要 |
 | T8 | EHR/临床文本/RWD 评测 | EHR & Clinical NLP & RWD | electronic health record, clinical note, discharge summary, MIMIC, real-world | ~39 | "General-purpose chatbots outperform clinical AI tools on physicians' real-world questions" (IF=52.5); BRIDGE (IF=26.3) | 摘要聚类 |
 | T9 | 专科专项基准 | Specialty-Specific Benchmarks | oncology benchmark, ophthalmology benchmark, psychiatry benchmark | ~22 | BELO (IF=5); ATCMD-Bench for TCM (IF=9.1); CARDBiomedBench (IF=25.5) | 标题含 [specialty] + benchmark |
 | T10 | 提示工程/微调方法学 | Prompt & Fine-tuning Methodology | fine-tuning, prompt engineering, CoT, few-shot, RLHF, domain adaptation | ~71 | "Enhancing domain adaptation via model composition in solving medical exam questions" (IF=23.4); "The recipe for open and specialized healthcare LLMs" (IF=18) | 标题 + 摘要 |

 ### 主题间逻辑关系

 主线方向:T1(医学问答与考试评测)是文献池中文献量最大的核心主题,直接回答"LLM 在标准化考试中表现如何"。T3(临床推理与决策)是 T1 的能力升级——从知识测验到临床推理。T4(agentic)是 T3 的进一步延伸——从单轮推理到多轮自主决策。三者构成"知识 - 推理 - 自主行动"的能力递进链。

 方法论支撑:T10(提示工程/微调)为 T1-T4 提供方法工具箱;T5(RAG/知识增强)是 T10 的一个重要分支,侧重通过外部知识库增强 LLM 医疗能力。两者偏向技术实现而非评测本身。

 维度交叉:T2(多模态)横切 T1-T4,为评测增加视觉/影像维度;T6(安全性)横切所有能力主题,关注 LLM 出错时的风险;T8(EHR/RWD)横切 T1-T3,为评测提供不同于标准化考试的数据来源。

 应用层:T7(医学教育)和 T9(专科基准)是 T1-T3 在特定场景中的落地——教育评估和专科评测。

 边缘/辅助性:T5 和 T10 文献量不少但偏向"怎么让 LLM 更好"而非"怎么评测 LLM",与泛主题(评测)为间接相关。作为综述素材时,它们更适合作为"评测结果的技术归因分析"而非主体。

 ---

 ## 3. 研究成熟度评估

 | 编号 | 主题名称 | 成熟度 | 文献密度 | 年份趋势 | 方法趋同度 | 成熟度说明 |
 |------|---------|--------|---------|---------|-----------|-----------|
 | T1 | 医学问答与考试评测 | 成熟 | 高(~156) | 持续高位 | 高(以 MCQ accuracy 为主) | 文献量最大,方法趋同(选模型 - 跑题库 - 报 accuracy),已有大量综述;新论文增量价值递减,除非有范式创新 |
 | T2 | 多模态/视觉-语言 | 成长中 | 高(~140) | 快速增长 | 中(VQA vs report generation vs diagnosis) | 文献量大且增长快,但方法路线在分化,仍有系统梳理空间 |
 | T7 | 医学教育应用 | 成长中 | 中(~89) | 快速增长 | 中 | 文献集中在"LLM 跑医学考试题"和"LLM 自动生成考题",方向正在分化,有综述空间 |
 | T10 | 提示/微调方法学 | 成长中 | 中(~71) | 快速增长 | 低(方法高度分散) | 各种提示策略和微调方案层出不穷,但缺乏系统比较框架,方法分散是综述机会 |
 | T3 | 临床推理与决策 | 成长中 | 中(~63) | 快速增长 | 中 | 从知识测验到临床推理的升级正在进行,出现推理链评测和 case-grounded 评测 |
 | T4 | Agent/工作流 | 新兴 | 中(~58) | 爆发式增长 | 低(概念定义尚未统一) | 2026 年集中爆发,AgentClinic/EvoMDT/ATCMD 等框架定义各异,先发综述优势明显 |
 | T5 | RAG/知识增强 | 成长中 | 中(~51) | 快速增长 | 中(GraphRAG vs vanilla RAG) | 文献偏技术实现而非评测,作为综述主题需与评测视角结合 |
 | T8 | EHR/RWD 评测 | 新兴 | 低(~39) | 快速增长 | 低(数据源和方法各异) | 从标准化考试转向 RWD-based 评测是重要趋势,但方法尚未标准化,高 IF 文献集中 |
 | T6 | 安全性/幻觉/偏见 | 成长中 | 低(~38) | 快速增长 | 低 | 有综述存在(IF=12.9),但幻觉检测方法和偏见评估框架仍高度分散 |
 | T9 | 专科专项基准 | 新兴 | 低(~22) | 快速增长 | 低(各专科独立构建) | 各专科独立建基准,缺乏跨专科比较框架;24 篇涉及中文/TCM,是差异化方向 |

 ### 成熟度核心洞察

 T4(Agent)、T8(RWD 评测)、T9(专科基准)位于"文献量低 + 方法趋同度低"象限,是先发综述价值最高的方向——领域正在形成但无人系统梳理。T1(医学问答)位于"文献量高 + 趋同度高"象限,已过度饱和,新综述必须有范式创新才能差异化。

 ---

 ## 4. 研究空白与机会方向

 | 编号 | 方向描述 | English label | 空白类型 | 支撑文献 | 机会窗口 |
 |------|---------|---------------|---------|---------|---------|
 | G1 | 基准构建方法学的系统框架——现有文献各自建基准,缺乏统一的质量标准、验证流程和报告规范 | Benchmark Construction Methodology | 评测空白 | "Structured taxonomy and framework for developing medical benchmark" (IF=18) 已开始但仅 scoping review; BELO/BRIDGE/EHRSHOT 各自实践; 缺乏类似 TRIPOD+AI 的基准报告规范 | 文献池中 44+ 篇涉及基准构造但无系统方法学综述;用户 MIMIC-IV 项目直接需要此框架 |
 | G2 | 数据泄露/基准污染问题——LLM 训练集可能包含已知基准(MedQA 等),导致评测分数虚高 | Benchmark Contamination & Data Leakage | 被忽视的问题 | 全池仅 3 篇涉及 contamination/leakage; "AgentLeak" (IF=4.2) 聚焦多 agent 隐私泄露但非评测污染; 无人系统讨论训练集-基准重叠对医疗评测的影响 | 在通用 NLP 已是热点(Memorization、test set contamination),但医疗领域几乎空白;高影响力方向 |
 | G3 | 评测范式的能力层级模型——从"知识-推理-决策-行动"建立评测维度分类学 | Evaluation Paradigm Taxonomy | 评测空白 | "Beyond multiple-choice questions" (IF=7.8) 提出问题但未建框架; "A Survey on Medical Competence Evaluation Benchmarks" (IF=6) 尝试但偏列举; 缺少基于认知/临床能力理论的层级模型 | 可引入 Miller's Pyramid(临床能力评估经典模型)构建 LLM 评测的理论框架 |
 | G4 | RWD-based 基准的信度问题——EHR 本身有噪声和不完整性,如何用它来评测 LLM | RWD Benchmark Validity | 争议未解 | BRIDGE (IF=26.3) 从临床文本构建基准; "General-purpose LLMs outperform specialized tools" (IF=52.5) 用真实问题评测但引发争议; 缺乏对 RWD-based 评测信效度的系统讨论 | 与 G1 高度互补;用户 MIMIC-IV 项目直接面对此问题 |
 | G5 | Agentic 评测的定义与标准化——各 agent 基准(AgentClinic vs ATCMD vs clinical environment simulator)评估的维度差异极大 | Agentic Evaluation Standardization | 评测空白 | AgentClinic (IF=18) 多模态工具使用; ATCMD-Bench (IF=9.1) 多 agent 模拟; "clinical environment simulator" (IF=52.5) 动态环境; 三者维度不可比 | 先发定义权;方法趋同度极低 = 综述机会 |
 | G6 | 多语言/中文医疗 LLM 评测——现有基准高度英语中心 | Multilingual & Chinese Medical Evaluation | 跨学科空白 | 池中 24 篇涉及中文/TCM; "A large-scale benchmark for medical QA in Romanian" (IF=18); "A Dataset for Chinese National Medical Licensing Exams" (IF=7.2) | 差异化方向;与用户中文背景和研究目标对齐 |
 | G7 | LLM 自动生成考题的质量评估——用 LLM 出题评测 LLM 的循环依赖问题 | LLM-Generated Question Quality | 争议未解 | "Psychometric properties of GPT-4o-generated MCQs" (IF=18); "Can LLMs generate exam questions comparable to humans?" meta-analysis; 多篇尝试但质量标准不一致 | 已有多篇实践但缺乏方法学共识;连接教育测量学 |
 | G8 | 评测中的人类基线设定——"LLM vs human"对比中人类基线的定义差异极大 | Human Baseline Standardization | 被忽视的问题 | "General-purpose LLMs outperform specialized clinical AI tools" (IF=52.5) 引发争议; 多篇声称"LLM 超过人类"但人类基线各异 | 影响所有性能对比的效度;高概念价值 |

 ### 空白优先级判断

 最高机会(文献支撑充分 + 空白明确 + 与用户项目对齐):G1(基准构建方法学)、G2(数据泄露)、G4(RWD 基准信度)三者紧密关联,可整合为一篇综述的不同章节。

 高机会(先发优势):G3(范式分类学)、G5(agentic 标准化)——定义权尚无人占据。

 中等机会(文献量偏少):G6(多语言)、G7(自动出题质量)、G8(人类基线)——需要补充文献。

 ---

 ## 5. 高影响力文献速览

 按推荐阅读顺序排列(综合 IF、期刊地位、摘要显示的内容贡献):

 | 序号 | 标题 | 年份 | 期刊 | IF | 推荐理由 | 优先级 |
 |------|------|------|------|-----|---------|--------|
 | 1 | General-purpose large language models outperform specialized clinical AI tools on medical benchmarks | 2026 | Nature Medicine | 52.5 | 颠覆性发现——通用 LLM 在真实医师问题上超过专用临床 AI;引发"评测到底测了什么"的根本性质疑 | P0_必读 |
 | 2 | Holistic evaluation of large language models for medical tasks with MedHELM | 2026 | Nature Medicine | 52.5 | 医疗 LLM 的整体性评测框架;定义了多维度评测基准,是范式设计的参考 | P0_必读 |
 | 3 | A clinical environment simulator for dynamic AI evaluation | 2026 | Nature Medicine | 52.5 | 动态临床环境模拟器,代表 agentic 评测的前沿;超越静态题库的范式创新 | P0_必读 |
 | 4 | BRIDGE: benchmarking large language models for understanding real-world clinical practice texts | 2026 | Nature Methods | 26.3 | 从真实临床文本构建评测基准,与 RWD 方向直接相关;方法论参考 | P0_必读 |
 | 5 | Structured taxonomy and framework for developing medical benchmark in large language models derived from scoping review | 2026 | — | 18.0 | 唯一一篇系统讨论"基准怎么造"的框架性论文;scoping review 方法;选题核心参考 | P0_必读 |
 | 6 | A Survey on Medical Competence Evaluation Benchmarks for Large Language Models | 2026 | — | 6.0 | 专门综述医疗 LLM 评测基准;了解现有基准分类的起点 | P1_重点 |
 | 7 | Beyond multiple-choice questions: Rethinking evaluation frameworks for large language models for clinical medicine | 2026 | — | 7.8 | 对 MCQ 评测范式的批判性反思;提出替代方案的起点文献 | P1_重点 |
 | 8 | AgentClinic: a multimodal benchmark for tool-using clinical AI agents | 2026 | — | 18.0 | 多模态临床 agent 评测基准的代表作;agentic 评测方向必读 | P1_重点 |
 | 9 | Benchmarking large language model-based agent systems for clinical decision tasks | 2026 | — | 18.0 | 临床决策 agent 系统的基准评测;与 T4 主题直接相关 | P1_重点 |
 | 10 | Medical multimodal large language models: A survey | 2026 | — | 17.4 | 多模态医疗 LLM 综述;建立 T2 主题的知识框架 | P1_重点 |
 | 11 | Large language models are powerful electronic health record encoders | 2026 | NPJ Digital Medicine | 18.0 | EHR 基础模型;使用 EHRSHOT 基准;与 T8(RWD)方向相关 | P1_重点 |
 | 12 | Reasoning-driven large language models in medicine: opportunities, challenges, and the road ahead | 2026 | — | 25.5 | 推理型 LLM 在医疗中的展望;涵盖 o1/o3 等推理模型;前瞻性视角 | P1_重点 |
 | 13 | Fine-grained evaluation of large language models in medicine using non-parametric cognitive diagnostic modeling | 2026 | — | 4.9 | 引入认知诊断模型(CDM)做细粒度评测;方法论创新,连接教育测量学 | P2_拓展 |
 | 14 | Can large language models generate exam questions comparable to humans? A systematic review and meta-analysis | 2026 | — | 4.0 | LLM 自动生成考题的系统综述 + meta-analysis;G7 方向的核心参考 | P2_拓展 |
 | 15 | Agentic AI in Healthcare and Medicine: A Seven-Dimensional Taxonomy for Empirical Evaluation of LLM-Based Agents | 2026 | — | 4.2 | 提出七维分类法评估医疗 agent;G5 方向的概念起点 | P2_拓展 |

 ### 推荐阅读路径

 1. 先读综述建立框架:论文 6(基准综述) - 论文 5(基准构建框架) - 论文 7(范式批判)
 2. 再读高 IF 里程碑:论文 1(通用 vs 专用) - 论文 2(MedHELM) - 论文 4(BRIDGE)
 3. 最后读方法创新:论文 13(认知诊断模型) - 论文 8/9(agent 评测) - 论文 3(临床模拟器)

 ---

 ## 6. 后续行动建议

 ### 当前文献池适配性判断

 结论:适合直接进入选题挖掘。文献池规模(1000 篇)、摘要覆盖率(99.4%)、主题清晰度(10 个可辨识方向)均达到选题挖掘的门槛。已在 `$sci-review-topic-mining` 中完成 7 个候选选题的评分排序,首选方向为"基准构建方法学"(综合评分 4.8/5)。

 ### 推荐深挖方向(按优先级)

 | 优先级 | 方向 | 关联主题 | 关联空白 | 理由 |
 |--------|------|---------|---------|------|
 | 1 | 基准构建方法学 | T1, T8, T9 | G1, G4 | 文献池最大空白;与 MIMIC-IV 项目完美对齐;方法学综述半衰期最长 |
 | 2 | 评测范式演变与分类学 | T1, T3, T4 | G3, G5 | 可建立"知识-推理-决策-行动"能力层级;与 G1 互补 |
 | 3 | Agentic 评测标准化 | T4 | G5 | 先发综述价值最高;但文献量(58 篇)中等,需补充 |

 ### 需要补充的文献

 | 类型 | 原因 | 建议 |
 |------|------|------|
 | 2022-2024 早期文献 | 文献池几乎全是 2026 年,缺 MedQA/MedMCQA/PubMedQA 原始构造论文和 ChatGPT 早期评测浪潮 | 用 wos-review-search-strategy 针对性补检 2020-2024 |
 | 经典教育测量学 | 讨论基准质量(IRT、Cronbach alpha、效度理论)需要引入,池中完全缺失 | 手动补充经典教材和综述 |
 | TRIPOD+AI / CONSORT-AI | AI 医疗报告规范,可作为基准报告规范的参照系 | 手动补充 |
 | 通用 LLM 评测方法学 | HELM、BIG-bench、Chatbot Arena 等通用框架的设计经验 | 补检(可与现有 WoS 检索式组合) |

 ### 风险提示

 1. 年份偏差:文献池集中于 2026 年,对"趋势"的判断本质上是截面观察,不是真实的时间序列。任何"快速增长"的判断需要警惕——可能是真实增长,也可能是检索排序偏差。
 2. 综述饱和:池中已有 104 篇 survey/review(10.4%),新综述必须找到明确差异化切口。最安全的方向是方法学(怎么做基准)而非应用(模型表现如何)。
 3. 专科覆盖不均:肿瘤(88)、影像(107)文献多,但皮肤科(4)、急诊(9 标题级)文献少,若选题涉及特定专科需补检。

 ---

 本报告由 sci-review-landscape skill 基于文献池数据自动分析生成。所有判断基于 JSON 中的 title、abstract、year、publicationTitle、影响因子等字段,未调用外部文献。标注"约"的文献数为基于关键词的多标签估算,非精确分类。
