# MIMIC 多模态生态：官方来源研究笔记

> 研究截止日期：2026-08-04（Asia/Shanghai）
> 来源范围：PhysioNet、MIMIC 官方文档、MIT-LCP 官方代码仓库及数据集原始论文。
> 数据边界：本文只记录公开元数据、数据说明和研究设计判断，不包含、摘录或复制任何患者级数据。

## 1. 结论先行

1. 以文本 benchmark 为主时，最先补齐的不是另一个“大而全”数据库，而是 **MIMIC-IV-Note v2.2**；它公开的自然语言正文只有出院小结与放射学报告。MIMIC-IV 3.1 本体中的 `hosp`/`icu` 主要是结构化事件，虽然若干字段是字符串或自由文本，但不能等同于连续病程记录。
2. 多模态最实用的第一阶段组合是 **MIMIC-IV 3.1 + MIMIC-IV-Note 2.2 + MIMIC-IV-ED 2.2 + MIMIC-CXR-JPG 2.1.0**。它可以支持住院长文本、急诊主诉、结构化时间线和胸片—报告任务；若要保留临床原始图像信息，再补 MIMIC-CXR DICOM。
3. **MIMIC-IV-ECG 1.0** 值得下载：约 80 万份 10 秒、12 导联、500 Hz 诊断心电，且带机器测量和机器生成的文本报告行；但当前公开的 MIMIC-IV-Note 2.2 并不包含 ECG 报告表，因此不能把 `waveform_note_links.csv` 误当成已经获得心电医师自由文本。
4. **MIMIC-IV Waveform 0.1.0** 仍是技术预览，仅 198 名患者、200 条记录。它适合验证 WFDB、时间对齐和信号处理管线，不适合作为需要稳定统计结论的大规模主 benchmark。
5. 截至本次核查，新增的重要官方扩展是 **MIMIC-IV-ECHO 1.0（2026-03）**：包含 206,488 个超声研究的结构化测量，以及 7,243 个 TTE 研究、约 52.5 万个 DICOM；但心超医师报告仍注明“以后在 Note 模块发布”，当前不能作为已公开文本使用。
6. 最大风险是**版本与时间覆盖不一致**。MIMIC-IV 3.1 覆盖 2008–2022，而 Note/ED 2.2 及若干扩展主要停留在 2019 或更早；“`subject_id` 可关联”不表示“3.1 的每次就诊都有对应文本、图像或信号”。任何 benchmark 都必须先计算实际交集，不能按官网总体规模推断样本数。

## 2. 官方版本与下载优先级

| 数据集 | 截止 2026-08-04 的最新公开版本 | 模态 | 官方规模摘要 | 主要时间覆盖 | 访问 | 建议 |
|---|---:|---|---|---|---|---|
| MIMIC-IV | 3.1 | 住院/ICU 结构化 EHR、少量文本字段 | v3.0/3.1 系列约 364,627 人、546,028 次住院、94,458 次 ICU stay | 2008–2022 | 凭据 + CITI + DUA | P0，已有则保留 |
| MIMIC-IV-Note | 2.2 | 出院小结、放射学报告 | 331,794 份出院小结；2,321,355 份放射报告 | 与旧版 MIMIC-IV 人群/就诊窗口关联；仅纳入就诊前后一年内的 note | 凭据 + CITI + DUA | **P0，文本任务必需** |
| MIMIC-IV-ED | 2.2 | 急诊主诉、分诊、生命体征、用药核对/发药、诊断 | 约 425,000 次 ED stay；官方表文档为 425,087 行 | 2011–2019 | 凭据 + CITI + DUA | **P0/P1** |
| MIMIC-CXR | 2.1.0 | 胸片 DICOM + 报告 | 377,110 张图像、227,835 个研究 | 2011–2016 | 凭据 + CITI + DUA | P1；需要原始 DICOM 时下载 |
| MIMIC-CXR-JPG | 2.1.0 | JPG + CheXpert/NegBio 标签 + 划分/元数据 | 377,110 张 JPG；报告派生标签覆盖约 227,827 个报告 | 与 MIMIC-CXR 相同 | 凭据 + CITI + DUA | **P0/P1，多模态起步首选** |
| MIMIC-IV-ECG | 1.0 | 12 导联 ECG、机器测量、机器文本行、note 链接表 | 约 800,000 ECG，近 160,000 人；约 600,000 个医师报告链接 | 2008–2019 | **开放访问**（ODbL） | P1；约 33.8 GB 下载包/90.4 GB 解压 |
| MIMIC-IV Waveform | 0.1.0 | 床旁高频波形 + 数值趋势 | 200 条记录、198 人 | 官方页未给出总体年份；父项目为 MIMIC-IV 2.0 | **开放访问**（ODbL） | P2，仅管线预研；12.8 GB 解压 |
| MIMIC-IV-ECHO | 1.0 | 心超结构化测量 + DICOM 序列 | 206,488 个测量研究/91,372 人；7,243 个 TTE 研究/4,579 人/约 525,000 DICOM | 测量 2008–2022；DICOM 2017–2019 | 凭据 + CITI + DUA | P1/P2，心血管多模态强烈推荐 |
| MIMIC-IV on FHIR | 2.1 | MIMIC-IV/ED 的 FHIR NDJSON 重编码 | 24 个 MIMIC-IV profile + 6 个 ED profile | 来源为 MIMIC-IV 2.2、ED 2.2 | 凭据 + CITI + DUA | P3；做互操作/FHIR benchmark 才下载 |

优先级含义：P0 = 当前文本 benchmark 的必要基础；P1 = 明显扩展核心任务；P2 = 特定信号或影像问题才需要；P3 = 当前主线不需要。

## 3. 共用标识符、时间与版本原则

### 3.1 标识符层级

- `subject_id`：患者级匿名标识，是跨模块的首要关联键。
- `hadm_id`：一次住院标识；ED 的 `hadm_id` 仅在 ED 后发生住院时存在，指向紧随其后的住院。
- `stay_id`：ICU 或 ED 的连续科室停留标识。ED 的所有数据表通过 ED `stay_id` 连接到 `edstays`；ICU 事件通过 ICU `stay_id` 连接到 `icustays`。不要仅凭字段同名把 ED `stay_id` 与 ICU `stay_id` 直接等同。
- `note_id`：文书级标识；由 `subject_id-note_type-note_seq` 构成。
- `study_id`：CXR、ECG、ECHO 各自的检查/研究标识；它不是跨影像模态通用键。跨模块先以 `subject_id`，再按同一患者的时间窗与各数据集提供的显式链接表对齐。
- `dicom_id` 或文件哈希/路径：单张图像或单个序列对象标识；CXR 中一个 `study_id` 可对应多张图像。

官方依据：[MIMIC 核心标识符说明](https://mimic.mit.edu/docs/IV/about/concepts.html)、[跨模块关联 FAQ](https://mimic.mit.edu/docs/faq/data.html)（访问日期均为 2026-08-04）。

### 3.2 时间脱敏

- MIMIC-IV 为每个 `subject_id` 分配一次固定日期偏移；同一患者内部的事件顺序与时间差保留，不同患者的伪日期不可用于判断真实同期关系。
- 3.1 的 `patients.anchor_year_group` 给出真实年代区间：`2008-2010`、`2011-2013`、`2014-2016`、`2017-2019`、`2020-2022`。年龄大于 89 岁者在 `anchor_age` 中归为 91。
- 官方说明扩展模块使用一致的患者日期偏移，因此同一患者跨模块的伪时间可以对齐；但 ECG 设备时钟未必与 EHR 同步，官方明确提示其时间戳可能显著偏移。

官方依据：[MIMIC-IV 3.1 数据说明](https://physionet.org/content/mimiciv/3.1/)、[MIMIC-IV-ECG 1.0](https://physionet.org/content/mimic-iv-ecg/1.0/)（访问日期均为 2026-08-04）。

### 3.3 “可关联”不等于“完整覆盖”

设核心库 3.1 的患者/住院集合为 $C$，某扩展集合为 $M$。最终 benchmark 样本只能来自实际交集 $C \cap M$。此外还要满足任务时间窗、所需模态和标签均存在：

$$
B = C \cap M_{note} \cap M_{task\ modality} \cap M_{label} \cap M_{time\ window}
$$

因此必须在本地逐项计算：患者交集、住院交集、就诊内时间重叠、文书/图像/信号完整率，以及被排除样本的原因。

## 4. MIMIC-IV v3.1：核心临床上下文

### 4.1 内容与规模

- 3.1 于 2024-10-11 发布，是截至核查日的最新版本。
- 主体为两个模块：`hosp` 来自院级 EHR，`icu` 来自 MetaVision ICU 系统。
- 3.0 新增 2020–2022 的就诊；3.1 是小型 bug-fix 版本。对本地 3.1 压缩表流式计数确认：`patients` 364,627 人，`admissions` 546,028 次住院（223,452 人），`icustays` 94,458 次 ICU stay（65,366 人）。
- `hosp` 主要表：`patients`、`admissions`、`transfers`、`labevents`、`microbiologyevents`、`poe`/`poe_detail`、`emar`/`emar_detail`、`prescriptions`、`pharmacy`、ICD/HCPCS/DRG 编码表、`omr`、`services`、`provider`。
- `icu` 主要表：`icustays`、`chartevents`、`inputevents`、`ingredientevents`、`outputevents`、`procedureevents`、`datetimeevents`、`d_items`、`caregiver`。

### 4.2 文本价值边界

3.1 本体中确有对 NLP/病例序列有用的文本或字符串字段，例如：

- `labevents.value` 与 `comments`；
- `microbiologyevents` 的标本、检测、菌名、药名和 `comments`；
- `poe.order_type/order_subtype` 与 `poe_detail.field_name/field_value`；
- 药品名称、剂型、给药途径、频率等 `prescriptions`/`pharmacy`/`emar` 字符串；
- ICU `chartevents.value` 以及 `d_items.label`；
- ICD/HCPCS/DRG 的描述文本。

这些字段适合构建“文本化事件时间线”、实体标准化、检索和结构化到文本的忠实生成任务，但大多是短文本、枚举、标签或半结构化值，不是连续的医师病程叙述。完整病例正文仍需 Note。

### 4.3 版本风险

- Note、ED、ECG、Waveform、FHIR、ECHO 的父版本或原始覆盖均早于 3.1；3.1 新增的 2020–2022 住院不能默认在旧扩展中出现。
- 3.1 修复了 v3.0 中部分 `d_labitems/labevents.itemid` 与 v2.2 不一致的问题；跨版本概念映射应以 3.1 为准，不能沿用基于 3.0 错误 `itemid` 生成的缓存标签。
- 官方提醒 MIMIC-IV 是其他模块的超集，做多模态交集会产生选择偏倚。

来源：[MIMIC-IV 3.1 PhysioNet 页面](https://physionet.org/content/mimiciv/3.1/)、[MIMIC-IV 官方 schema overview](https://mimic.mit.edu/docs/IV/about/schema-overview.html)、[MIT-LCP/mimic-code](https://github.com/MIT-LCP/mimic-code)（访问日期均为 2026-08-04）。

## 5. MIMIC-IV-Note v2.2：自然语言主语料

### 5.1 实际公开的文本

- `discharge.csv.gz`：出院小结，长叙述通常包含入院原因、住院经过、出院指导。
- `discharge_detail.csv.gz`：文书附加信息，EAV 结构；当前主要包含作者占位信息。
- `radiology.csv.gz`：X-ray、CT、MRI、超声等多种影像的放射学报告；通常为半结构化章节，如 indication、comparison、findings、impression。
- `radiology_detail.csv.gz`：CPT、exam code/name、父报告/附加报告关系。

规模：331,794 份出院小结、145,915 名患者；2,321,355 份放射学报告、237,427 名患者。所有 PHI 实体用三个下划线 `___` 替代。官方纳入原则是文书一般在一次 ED 或住院 encounter 前后一年内。

### 5.2 明确没有公开的内容

当前 2.2 只有上述四张表，不含护理记录、进展记录、会诊记录、手术记录、病例管理记录、ECG 医师报告或 ECHO 医师报告。因此：

- 不能用 MIMIC-IV-Note 2.2 复刻 MIMIC-III `NOTEEVENTS` 的全类别文本 benchmark；
- 不能把 MIMIC-III 的 note 类别和 MIMIC-IV-Note 混为同一数据分布；
- ECG/ECHO 页面中“以后发布到 Note”不等于当前可下载。

### 5.3 与 3.1 的兼容风险

- Note 2.2 发布于 2023-01，核心库 3.1 于 2024-10 才加入 2020–2022 就诊；因此 3.1 的新增阶段必然不能假设都有 Note 2.2 覆盖。
- 最安全的做法是从 `discharge`/`radiology` 出发，以 `subject_id`、`hadm_id` 反向关联 3.1；不要从全部 3.1 住院出发假定一对一存在文书。
- `note_id` 是文书级主键；同一住院可能有主报告和 addendum。需通过 `note_type`、`note_seq`、`charttime/storetime` 和 detail 表中的 parent/addendum 关系保留版本语义，不能简单取最长文本。

来源：[MIMIC-IV-Note 2.2](https://physionet.org/content/mimic-iv-note/2.2/)、[Discharge 表](https://mimic.mit.edu/docs/IV/modules/note/discharge.html)、[Radiology 表](https://mimic.mit.edu/docs/IV/modules/note/radiology.html)、[Radiology detail 表](https://mimic.mit.edu/docs/IV/modules/note/radiology_detail.html)（访问日期均为 2026-08-04）。

## 6. MIMIC-IV-ED v2.2：急诊语境与短文本

### 6.1 表与字段

- `edstays`：一次 ED stay 的进入/离开时间、到院方式、去向；`hadm_id` 仅在随后住院时存在。
- `triage`：分诊生命体征、疼痛、acuity，以及真正的自由文本 `chiefcomplaint`。主诉通常是逗号分隔的短语，PHI 以 `___` 替代。
- `vitalsign`：ED 内不定期生命体征，含 `rhythm`、`pain` 等字符串。
- `diagnosis`：ED 出院后的 ICD-9/10 计费诊断和文本标题；它是后验标签，不是到院时可用信息。
- `medrecon`：到院前用药核对，含药名和药物分类描述。
- `pyxis`：ED 自动发药柜的药物发放记录；并不覆盖所有实际治疗。

### 6.2 规模、时间与关联

- 2011–2019，约 425,000 次 ED stay；官方 `edstays` 文档给出 425,087 行。
- 所有 ED 表围绕 `stay_id` 连接；`subject_id` 可连接 MIMIC-IV、CXR，`hadm_id` 可连接 ED 后紧随的住院。
- MIMIC-IV 3.1 覆盖更宽；官方明确说明：MIMIC-IV-ED 中的 ED stay 都存在于 MIMIC-IV `transfers`，反之不成立。

### 6.3 Benchmark 价值与泄漏

- 适合：主诉标准化、分诊严重度、ED 去向预测、早期风险分层、急诊检索、ED→住院/ICU 的时序预测。
- 不适合把 `diagnosis`、`disposition`、ED 后的住院/出院文书作为到院时输入；这些都是目标发生后或编码后信息。
- `chiefcomplaint` 是短文本，不是完整急诊病历。若 benchmark 名称使用“急诊病历理解”，必须明确输入只包含主诉/分诊和结构化事件。

来源：[MIMIC-IV-ED 2.2](https://physionet.org/content/mimic-iv-ed/2.2/)、[ED 表文档](https://mimic.mit.edu/docs/IV/modules/ed/)（访问日期均为 2026-08-04）。

## 7. MIMIC-CXR 2.1.0 与 MIMIC-CXR-JPG 2.1.0

### 7.1 MIMIC-CXR：原始临床影像版本

- 377,110 张胸片，227,835 个 radiographic study，DICOM 格式并附自由文本报告。
- 队列来自 2011–2016 年在 ED 做过胸片的人群，并提取这些患者同期间的全部胸片。因此它不是全部 MIMIC-IV 患者的随机样本，而是受 ED 与胸片指征双重选择的子集。
- 标识关系：`subject_id` 对患者，`study_id` 对一次检查，单图像用唯一哈希/文件名；一个 `study_id` 可有多张图像，但通常只有一份报告。
- 关键文件：`cxr-record-list.csv.gz`、`cxr-study-list.csv.gz`、`cxr-provider-list.csv.gz`、DICOM 文件、独立文本报告及报告压缩包。
- 2.1.0 相比 2.0.0 的主要变更是新增去标识化 provider 映射；provider id 与 MIMIC-IV 2.2 以后版本表示相同人员。

### 7.2 MIMIC-CXR-JPG：训练友好派生版

- 与 CXR 图像集合相同，转换为 JPG；官方摘要为 377,110 张 JPG，并提供从约 227,827 份报告派生的结构化标签。
- 提供元数据、官方患者级 train/validate/test split、CheXpert 标签、NegBio 标签，以及 v2.1.0 新增的单一放射科医师标注测试集。
- JPG 是有损、8-bit/常见 CV 流程友好的派生表示；DICOM 保留更丰富的临床元数据与像素深度。若研究目标是通用图文模型，JPG 更实用；若研究目标涉及成像物理、窗宽窗位、DICOM 元数据或临床部署一致性，应使用 DICOM。
- CheXpert/NegBio 标签来自报告的规则系统，不是真正独立于报告的 gold label。若模型输入包含同一报告，再用这些标签评测，将产生标签来源泄漏。

### 7.3 与 MIMIC-IV-Note 的关系

MIMIC-IV-Note 的 `radiology` 覆盖多种影像，而 MIMIC-CXR 只包含胸片。CXR 自带 study-level 报告文件；Note 的 radiology 表以 `note_id` 为中心，官方 detail 字段未列出 CXR `study_id`。因此建立 CXR↔Note 的精确 study 对齐时，应优先使用 CXR 自带报告/清单或官方提供的明确链接字段，不应只凭模糊时间最近邻假定一一对应。

来源：[MIMIC-CXR 2.1.0](https://physionet.org/content/mimic-cxr/2.1.0/)、[MIMIC-CXR-JPG 2.1.0](https://physionet.org/content/mimic-cxr-jpg/2.1.0/)、[原始数据论文](https://doi.org/10.1038/s41597-019-0322-0)（访问日期均为 2026-08-04）。

## 8. MIMIC-IV-ECG 1.0

### 8.1 信号与文件

- 约 800,000 份诊断 ECG、近 160,000 名患者；12 导联、10 秒、500 Hz。
- ECG 覆盖 2008–2019，可来自 ED、住院（含 ICU）和门诊；约 55% 与住院重叠、约 25% 与 ED visit 重叠。
- WFDB 每条记录包含 `.hea` 和 `.dat`；`record_list.csv` 提供路径、`subject_id`、`study_id`。
- `machine_measurements.csv` 提供 RR/QRS 等全局测量及 `report_0...report_17` 机器生成的报告行；它们是可直接用于文本/结构化联合任务的机器文本，不等同于心电医师最终解释。
- `waveform_note_links.csv` 提供 waveform 到 `note_id` 的映射。约 60 万份心电有医师报告链接，但 v1.0 移除了敏感自由文本，只保留链接，因此该数据集转为开放访问。
- 官方下载页面报告总解压规模约 90.4 GB、ZIP 约 33.8 GB。

### 8.2 当前的文本可用性判断

ECG 官方页一方面给出了 `note_id` 链接，MIMIC FAQ 也写明可连接 MIMIC-IV-Note；另一方面 ECG 1.0 页面明确写道心电医师自由文本将在未来的 Note 模块发布，而当前 Note 2.2 只有 discharge/radiology 四表。故截至本次核查：

- 可用：ECG 波形、机器测量、机器生成报告行、医师报告的 `note_id` 链接元数据；
- 不应声明可用：公开的心电医师报告正文；
- 后续应以实际 Note 下载目录是否出现 `EK`/ECG 表为准，不能仅按链接表推断正文存在。

### 8.3 对齐风险

- ECG 1.0 的 PhysioNet 父项目为 MIMIC-IV 2.2；3.1 新增 2020–2022，但 ECG 自身只到 2019。
- 设备内部时钟可能未同步，官方明确提示 ECG 时间戳可与 EHR/其他波形显著错位。事件级 benchmark 应设定容差并报告对齐质量，而不是强制精确秒级匹配。
- 约 5% ECG 被保留为隐藏测试集；公开数据规模不是院内全部 ECG。

来源：[MIMIC-IV-ECG 1.0](https://physionet.org/content/mimic-iv-ecg/1.0/)、[MIMIC 跨模块关联 FAQ](https://mimic.mit.edu/docs/faq/data.html)（访问日期均为 2026-08-04）。

## 9. MIMIC-IV Waveform Database 0.1.0

### 9.1 内容

- 床旁监护的高频 ECG、PPG、呼吸、有创/无创血压等波形，以及由监护仪派生或不规则采样的数值趋势。
- 每条记录包括多段 WFDB header/信号文件和压缩 CSV numerics；波形文件使用 FLAC 压缩。
- 采用与 MIMIC-IV 一致的 `subject_id`、`hadm_id` 和日期偏移，可关联住院；一个 ICU stay 可对应多条 waveform record。
- 由于监护系统人工“入床/出床”和记录间断，一名患者的一次 ICU stay 可能被切为多个记录；超过一小时无波形/数值会触发自动切分。

### 9.2 规模与适用边界

- 当前公开版本仍为 0.1.0（2022-07-10），只有 198 名患者、200 条记录，解压总量约 12.8 GB。
- 页面当年写有“未来约 10,000 条记录”和“1.0 很快发布”，但截至 2026-08-04 官方版本列表仍只有 0.1.0；不能把规划规模写成现有规模。
- 适合：验证信号读取、信号质量、片段抽样、多分辨率时间轴、波形与结构化事件对齐；不适合作为通用临床波形模型的唯一外部结论来源。

来源：[MIMIC-IV Waveform 0.1.0](https://physionet.org/content/mimic4wdb/0.1.0/)、[官方 waveform 教程](https://mimic.mit.edu/docs/iv/tutorials/waveform/)（访问日期均为 2026-08-04）。

## 10. 关键新增扩展

### 10.1 MIMIC-IV-ECHO 1.0

- 2026-03-10 发布，父项目为 MIMIC-IV 2.2。
- `structured_measurement.csv`：206,488 个研究、91,372 名患者；其中 TTE 179,928、stress echo 16,389、TEE 10,171，时间为 2008–2022。测量经过临床人员核验，但不同心超系统时期存在变量名与可用性漂移。
- DICOM 子集：约 525,000 个 DICOM、7,243 个 TTE 研究、4,579 人，仅 2017–2019；只是一部分可发布研究。
- `echo-record-list.csv`：DICOM 路径、acquisition time、`study_id`、`subject_id`。
- `echo-study-list.csv`：可把 DICOM `study_id` 连接到两日内的 `measurement_id`，并提供可用时的 `note_id/note_seq/note_charttime`。
- 约 5% 按患者级隐藏；部分研究在 ED/ICU encounter 之外，不能强制分配 `hadm_id`。
- 心超医师自由文本报告仍未随 1.0 发布，官方说明以后进入 Note 模块。

Benchmark 价值：视频/序列级心超理解、结构化测量预测、EF/瓣膜/腔室测量一致性、多模态心血管时间线。不能把未来报告作为当前标签；若用结构化测量作标签，应注意同一测量可能含机器算法与临床修订的共同贡献。

来源：[MIMIC-IV-ECHO 1.0](https://physionet.org/content/mimic-iv-echo/1.0/)（访问日期 2026-08-04）。

### 10.2 MIMIC-IV on FHIR 2.1

- 将 MIMIC-IV 2.2 和 MIMIC-IV-ED 2.2 映射为 FHIR R4/US Core 相关 profile，以压缩 NDJSON 分发。
- 它是原数据的互操作重编码，不增加新的临床模态或患者覆盖；版本 2.1 仍不对应 MIMIC-IV 3.1。
- 适合 FHIR 查询、互操作、数据映射、EHR agent 工具调用 benchmark；若目标是文本处理或临床预测，直接使用 CSV/Parquet 更简单，也更容易追踪源表字段。

来源：[MIMIC-IV on FHIR 2.1](https://physionet.org/content/mimic-iv-fhir/2.1/)、[官方 MIMIC FHIR 网站](https://mimic.mit.edu/fhir/)（访问日期均为 2026-08-04）。

## 11. 下载决策：为什么与对用户的影响

### 第一批：必须/最优先

1. **MIMIC-IV-Note 2.2**
   为什么：没有它就没有大规模连续病例正文，只能做结构化字段文本化。
   影响：可构建出院摘要、章节识别、事实抽取、证据定位、报告理解等核心 NLP benchmark；同时必须管理结局泄漏。

2. **MIMIC-IV-ED 2.2**
   为什么：补齐 ED 到院阶段的主诉和分诊语境。
   影响：可以把任务时点前移到“刚到 ED”，避免所有任务都围绕出院后文书；但仍不是完整急诊病历。

3. **MIMIC-CXR-JPG 2.1.0**
   为什么：下载/训练门槛低于 DICOM，且已有标签、元数据和官方划分。
   影响：最快建立可复现的图文 benchmark；代价是像素深度和部分 DICOM 信息损失。

### 第二批：按研究方向扩展

4. **MIMIC-IV-ECG 1.0**
   为什么：规模大、开放访问、下载体量可控，且有机器文本。
   影响：能建立信号—结构化—机器解释联合任务；不能把医师 ECG 正文列为现有输入。

5. **MIMIC-CXR 2.1.0 DICOM**
   为什么：保留临床格式与更完整成像信息。
   影响：有利于严肃的成像研究，但存储、I/O、预处理与合规成本显著增加；若仅做 LLM/VLM 基线，可后置。

6. **MIMIC-IV-ECHO 1.0**
   为什么：这是 2026 年已经正式公开、可与 MIMIC 关联的关键心血管多模态扩展。
   影响：可将 benchmark 从静态胸片/ECG 扩展到心超序列和结构功能测量；DICOM 子集较小且报告正文尚未发布。

### 暂不作为主数据下载

7. **MIMIC-IV Waveform 0.1.0**：仅 200 条记录，先用于技术验证；主 benchmark 等待官方更大版本或明确以 preview 为研究对象。
8. **MIMIC-IV on FHIR 2.1**：只有做 FHIR/互操作任务时才下载，不为现有文本/多模态任务重复存一份 2.2 数据。

## 12. Benchmark 设计的直接约束

### 12.1 划分与去重

- 所有模态统一按 `subject_id` 划分，禁止同一患者跨 train/validation/test。
- CXR-JPG 自带推荐划分；若与 Note/ED/ECG 联合，必须把该患者级划分传播到所有模态，不能让文本侧重新随机划分。
- 主报告/addendum、重复放射模板、同次研究多视图、ECG 重复采集均需成组处理。

### 12.2 预测时点

- ED 到院任务：只允许 `intime` 后指定窗口内的主诉、分诊和已发生事件。
- 住院早期任务：出院小结、最终 ICD/DRG、出院去向、死亡结果性描述不可进入输入。
- 报告生成任务：若标签由报告派生（CheXpert/NegBio），不得同时把报告放入输入。
- 多模态对齐：除显式 ID 外，必须验证图像/信号时间是否位于 encounter 窗口；对 ECG 还要标记设备时钟不确定性。

### 12.3 评测标签层级

- 原始人工文本：出院小结、放射报告；注意其本身仍包含临床判断与复制粘贴噪声。
- 后验人工/计费标签：ICD、ED diagnosis、disposition；只适合相应时点后的监督目标。
- 弱标签：CheXpert/NegBio、ECG machine report、机器测量；必须明确它们不是独立 gold standard。
- 隐藏测试集：MIMIC 多个模块约保留 5% 患者；公开 benchmark 不能声称覆盖院内全量分布。

## 13. 访问与合规

### 13.1 凭据访问数据

MIMIC-IV、Note、ED、CXR、CXR-JPG、ECHO、FHIR 均要求：PhysioNet credentialed user、完成 `CITI Data or Specimens Only Research`、签署对应 DUA；文件使用 PhysioNet Credentialed Health Data License 1.5.0。

### 13.2 开放访问数据

MIMIC-IV-ECG 1.0 与 MIMIC-IV Waveform 0.1.0 页面标记为 Open Access，使用 Open Data Commons Open Database License v1.0；但与受限 MIMIC 数据合并得到的派生数据仍应按更严格的来源约束管理。

### 13.3 派生 benchmark

MIMIC-IV 官方明确：由 MIMIC 派生或扩展的数据集/模型仍应视为敏感；若分享，应通过 PhysioNet 并使用与源数据相同的协议。若项目名使用 MIMIC，应加入 `Ext`。因此仓库中只应提交代码、配置、schema、聚合统计和不含患者内容的报告；患者级输入、标签、模型逐例输出、embedding、缓存、索引及 checkpoint 必须留在 Git 之外。

来源：[PhysioNet 的 MIMIC 派生数据/模型指南](https://physionet.org/news/post/mimic-derived-datasets-models/)、各数据集 Access 区（访问日期均为 2026-08-04）。

## 14. 尚未确认、必须用本地数据回答的问题

1. Note 2.2 与 MIMIC-IV 3.1 的精确 `subject_id`、`hadm_id` 覆盖率，以及 2020–2022 是否为零/极低覆盖。
2. CXR 自带报告与 Note `radiology` 中胸片报告的精确重复和映射比例；Note detail 官方字段列表未提供 CXR `study_id`。
3. ECG `waveform_note_links.csv` 中的 `note_id` 是否在用户当前 PhysioNet 权限下有任何公开对应正文。根据公开 Note 2.2 schema，预期没有，但应以下载后的实际文件列表验证。
4. ECHO 1.0 的下载体量与可用压缩格式。未登录的 PhysioNet页面未公开完整文件清单/体量，本研究不猜测。
5. Waveform 200 条记录的真实采集年份和每条记录的时长分布；需要读取公开 header 元数据后统计。

## 15. 官方来源索引

以下页面均于 **2026-08-04** 访问：

- [MIMIC-IV 3.1 — PhysioNet](https://physionet.org/content/mimiciv/3.1/)
- [MIMIC-IV 官方文档](https://mimic.mit.edu/docs/IV/)
- [MIMIC-IV schema overview](https://mimic.mit.edu/docs/IV/about/schema-overview.html)
- [MIMIC core concepts](https://mimic.mit.edu/docs/IV/about/concepts.html)
- [MIMIC 跨模块关联 FAQ](https://mimic.mit.edu/docs/faq/data.html)
- [MIT-LCP/mimic-code](https://github.com/MIT-LCP/mimic-code)
- [MIMIC-IV 原始数据论文](https://doi.org/10.1038/s41597-022-01899-x)
- [MIMIC-IV-Note 2.2](https://physionet.org/content/mimic-iv-note/2.2/)
- [MIMIC-IV-Note discharge 表](https://mimic.mit.edu/docs/IV/modules/note/discharge.html)
- [MIMIC-IV-Note radiology 表](https://mimic.mit.edu/docs/IV/modules/note/radiology.html)
- [MIMIC-IV-Note radiology_detail 表](https://mimic.mit.edu/docs/IV/modules/note/radiology_detail.html)
- [MIMIC-IV-ED 2.2](https://physionet.org/content/mimic-iv-ed/2.2/)
- [MIMIC-IV-ED 官方表文档](https://mimic.mit.edu/docs/IV/modules/ed/)
- [MIMIC-CXR 2.1.0](https://physionet.org/content/mimic-cxr/2.1.0/)
- [MIMIC-CXR 原始数据论文](https://doi.org/10.1038/s41597-019-0322-0)
- [MIMIC-CXR-JPG 2.1.0](https://physionet.org/content/mimic-cxr-jpg/2.1.0/)
- [MIMIC-IV-ECG 1.0](https://physionet.org/content/mimic-iv-ecg/1.0/)
- [MIMIC-IV Waveform 0.1.0](https://physionet.org/content/mimic4wdb/0.1.0/)
- [MIMIC-IV Waveform 官方教程](https://mimic.mit.edu/docs/iv/tutorials/waveform/)
- [MIMIC-IV-ECHO 1.0](https://physionet.org/content/mimic-iv-echo/1.0/)
- [MIMIC-IV on FHIR 2.1](https://physionet.org/content/mimic-iv-fhir/2.1/)
- [MIMIC FHIR 官方网站](https://mimic.mit.edu/fhir/)
- [PhysioNet：MIMIC 派生数据/模型指南](https://physionet.org/news/post/mimic-derived-datasets-models/)
