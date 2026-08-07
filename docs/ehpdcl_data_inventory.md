# EHPDCL 数据清单（香港医管局数据协作平台）

> 数据源：[醫弘數科 EH Plus Digital](https://ehpdigital.com/data-service/data-catalogue/)
> 运营主体：EH Plus Digital Technology Limited（背后为香港医院管理局 Hospital Authority，`ha.org.hk`）
> 数据性质：匿名化全港人群纵向医疗数据，跨度 30+ 年
> 整理日期：2026-08-06
> 关键约束：所有日期字段已脱敏至「月」或「年」级；原始患者数据不可外带，仅限安全分析环境内使用

---

## 访问层级与数据覆盖

三层服务递进，能拿到的数据范围逐层扩大。**非结构化文本与影像仅 EXPERT 层提供。**

| 层级 | 数据范围 | 用途 | 可带出内容 |
|---|---|---|---|
| CRADLE | ~20 万患者代表性样本（2007/2017 人群，按年龄性别分层），仅结构化 | 熟悉 schema、评估数据价值 | 仅环境内分析结果 |
| DARE | 全量结构化数据，30+ 年，季度刷新 | 正式研究分析 | 仅环境内分析结果 |
| EXPERT | 全量结构化 + 非结构化文本 + 影像 + 病种队列产品 | 模型训练与验证 | 合规审核后：聚合结果、图表、代码、AI 模型 |

物理环境：Data Collaboration Lab, 11/F, Harbourside HQ, 8 Lam Chak Street, Kowloon Bay, Hong Kong（工作日 09:00-18:00）。

---

## 一、结构化数据集（CRADLE / DARE / EXPERT 均有）

日期均已脱敏，标注「月」表示到月级，「年」表示到年级。

| # | 数据集 | 记录规模 | 起始时间 | 字段要点 | 时间精度 |
|---|---|---|---|---|---|
| 1 | Demographic 人口学 | 12M | 全程 | 性别、出生年 | 年 |
| 2 | Accident & Emergency 急诊就诊 | 84M | 1997 | 就诊月、就诊年龄、triage 分流级别、出院信息 | 月 |
| 3 | Inpatient 住院/转院/出院 | 523M | 1997 | 入出院月、入院年龄、入院来源、入院专科、出院信息 | 月 |
| 4 | Outpatient 门诊预约 | 102M | 2000 | 预约月、年龄、就诊专科、初/复诊 | 月 |
| 5 | Diagnosis 诊断 | 102M | 全程 | 诊断、诊断状态、诊断月 | 月 |
| 6 | Procedure 操作 | 39M | 全程 | 操作、操作月 | 月 |
| 7 | Medication 处方配药 | 1,170M | 2000 | BNF 编码药品、处方周期、剂量 | 月 |
| 8 | Immunization 疫苗接种 | 6M | 2009-10 | 注射月、疫苗 | 月 |
| 9 | Family Medicine 家庭医学 | 438M | 全程 | ICPC2 编码、疾病结果月 | 月 |
| 10 | Obstetrics 产科 | 743K | 2002 | 分娩年、出生体重、产次、孕周 | 年 |
| 11 | Laboratory 检验结果 | 2,538M | 2000 | 生化/血液免疫/微生物病毒、参考月 | 月 |
| 12 | Radiology 放射检查 | 131M | 1999-04 | 登记月、检查详情、年龄 | 月 |

---

## 二、非结构化文本与影像（仅 EXPERT）

这是做医疗 LLM benchmark 最关键、最稀缺的部分。

| # | 数据集 | 规模 | 起始时间 | 内容 |
|---|---|---|---|---|
| 1 | Clinical Note/Summary 临床记录/摘要 | 130M 条 | 1994-02 | 临床与出院记录的文本内容 |
| 2 | Laboratory Result 检验结果文本 | 65M 条 | 2000 | 检验结果的文本 |
| 3 | Radiology Report 放射报告文本 | 23M 条 | 1999 | 检查报告的文本 |
| 4 | Radiology Image 放射影像 | 项目制 | — | DICOM 格式，分期交付，提取量决定周期 |

---

## 三、病种队列 Data Products（EXPERT 标准产品）

### 14 种慢性病队列

| # | 病种 | 患者规模 | 临床定义要点 |
|---|---|---|---|
| 1 | Hypertension 高血压 | 2,100K+ | 原发性占 95%，持续血压升高，风险因子含年龄/肥胖/盐敏感 |
| 2 | Hyperlipidemia 高血脂 | 1,290K+ | LDL 和/或甘油三酯升高，动脉粥样硬化主因 |
| 3 | Diabetes Mellitus 糖尿病 | 850K+ | 1 型（自身免疫）/2 型（胰岛素抵抗），慢性高血糖 |
| 4 | Chronic Kidney Disease 慢性肾病 3A-5 期 | 730K+ | GFR<60 持续≥3 月；3A:45-59, 3B:30-44, 4:15-29, 5:<15 |
| 5 | Coronary Heart Disease 冠心病 | 560K+ | 冠脉粥样硬化狭窄/阻塞，含心绞痛、心梗 |
| 6 | Chronic Heart Failure 慢性心衰 | 320K+ | 泵血功能进行性下降，65 岁以上高发 |
| 7 | Hepatitis B Carriers 乙肝携带 | 310K+ | HBsAg/DNA 阳性>6 月，肝硬化/HCC 风险升高 |
| 8 | Glaucoma 青光眼 | 250K+ | 眼压升高致视神经损伤、视力丧失 |
| 9 | Dementia 痴呆 | 270K+ | 进行性认知衰退（阿尔茨海默/血管性/神经退行性） |
| 10 | Stroke 卒中 | 220K+ | 脑缺血/出血，症状含偏瘫/失语/意识改变 |
| 11 | Depression 抑郁症 | 200K+ | 持续悲伤/快感缺失/疲劳，癌症患者中 15-25% |
| 12 | COPD 慢阻肺 | 180K+ | 持续气流受限，暴露有害颗粒/气体（如吸烟） |
| 13 | Hip Fracture 髋部骨折（骨质疏松近似） | 160K+ | 股骨近端骨折，老年高发、活动力下降 |
| 14 | Parkinsonism 帕金森综合征 | 70K+ | 运动迟缓 + 震颤/强直/姿势不稳 |

### 11 种癌症队列（患病率源自香港癌症登记处 Hong Kong Cancer Registry）

| # | 癌种 | 患者规模 | 说明 |
|---|---|---|---|
| 1 | Colorectal 结直肠癌 | 80K+ | 结肠/直肠恶性肿瘤，多源于腺瘤性息肉 |
| 2 | Lung 肺癌 | 80K+ | 小细胞（侵袭性、吸烟相关）/非小细胞（腺癌、鳞癌） |
| 3 | Breast (Female) 乳腺癌 | 60K+ | 导管/小叶癌，浸润型可转移 |
| 4 | Prostate 前列腺癌 | 30K+ | 老年男性腺癌 |
| 5 | Liver 肝癌 | 30K+ | 原发（HCC）/继发（转移） |
| 6 | Stomach 胃癌 | 20K+ | 胃黏膜腺癌 |
| 7 | Nasopharynx 鼻咽癌 | 10K+ | 鼻咽上皮恶性肿瘤，EB 病毒相关 |
| 8 | Corpus 子宫体癌 | 10K+ | 子宫内膜癌、平滑肌肉瘤 |
| 9 | Non-Hodgkin Lymphoma 非霍奇金淋巴瘤 | 10K+ | B 细胞/T 细胞淋巴瘤 |
| 10 | Ovary 卵巢癌 | 9K+ | 上皮癌（多见）/生殖细胞瘤，常晚期诊断 |
| 11 | Cervix 宫颈癌 | 8K+ | HPV 相关 |

---

## 四、编码体系与术语标准

提取数据时会遇到的标准化编码，benchmark 设计需对齐：

- **ICD**（诊断编码）：诊断数据集
- **BNF**（British National Formulary）：处方配药药品编码
- **ICPC2**（International Classification of Primary Care）：家庭医学疾病编码
- **DICOM**：放射影像格式

---

## 五、计算环境与输出约束

- **环境内计算**：Technical Platform 提供常用开源软件、R 包、Python 模块（详见 R Package List / Python Module List 页）。
- **可带出（仅 EXPERT 合规审核后）**：聚合结果、图表、源代码、训练好的 AI 模型。
- **严禁外带**：任何层级均不可带出原始患者级数据。
- **EXPERT 收费**：按研究需求报价，提交申请审核后出具。

---

## 六、对 LLM Benchmark 项目的影响

1. **非结构化文本是核心语料**：1.3 亿条临床记录 + 2300 万条放射报告，真实香港临床中英夹杂写法，需 EXPERT 层访问。
2. **时间精度上限到月/年**：benchmark 中无法做精确日期时序推理，只能到月/年级时间推理。
3. **多模态可能**：EXPERT 可提供 DICOM 影像，支持图文多模态 benchmark，但影像按项目分期交付。
4. **病种队列现成**：14 慢性病 + 11 癌症队列可直接用作特定病种评测的入组筛选。
5. **输出即模型**：训练完成的模型经审核可带出，适合「在飞地训练、带模型回本地评测」的工作流。

---

*来源：ehpdigital.com Data Catalogue / CRADLE / DARE / EXPERT / Accessing DCL / Technical Platform 页面，2026-08-06 抓取。*
