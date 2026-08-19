# v2 临床决策题出题方法学

> 本基准采用「统计定答案、程序锁选项、LLM 只写题干、三道门禁才进 gold」的确定性出题方法学，
> 把真实世界数据中的统计关联转成可追溯、可复现的英文 A-D 单选临床决策题。全链路分四段十阶段。

## 数据层（阶段 1–3）——构建类型化条件特征空间

1. **人口学**：从单次住院原始归档 `mimic-admission-raw-coronary-all-three-modules.jsonl` 流式抽取
   内嵌的 `mimic_iv_hosp.patients[0]`（gender/anchor_age/anchor_year），按
   `age_at_encounter = anchor_age + (admit_year − anchor_year)` 算就诊时年龄，生成
   39,036 住院 / 20,136 受试者的人口学 sidecar。
2. **八类特征**：从事件级标准化数据 `normalized_events.parquet`（23,626 住院）抽取
   `age_band`、`sex`、`symptom`（仅 assertion=present）、`sign`（体格检查章节 NER）、
   `physiologic_flag`（生命体征数值阈值化，如发热 ≥37.0°C）、`past_condition`（ICD Z80-Z99
   历史码 + 慢性病词表）、`medication`（入院用药类别）、`absent`（否定症状）。

   八类特征的来源与抽取方式（分工表）：

   | 特征类型 | 数据来源 | 抽取方式 | 实现模块 |
   |---|---|---|---|
   | age_band | 人口学 sidecar（就诊时年龄） | 结构化 · 确定性 | `demographics.py` |
   | sex | 人口学 sidecar | 结构化 · 确定性 | `demographics.py` |
   | symptom | `symptom_reported` 事件（assertion=present） | 结构化 · 确定性 | 事件直接读取 |
   | sign | 出院小结「体格检查」章节 | NER · LLM（DeepSeek Flash） | `sign_ner.py` + `run_sign_ner.py` |
   | physiologic_flag | `vital_measured` 结构化事件 | 结构化 · 确定性（数值阈值化） | `vital_flags.py` + `vital_flag_rules.yaml` |
   | past_condition | ICD Z80-Z99 + 慢性病词表（ICD 轨）；出院小结（NER 轨） | 确定性 + NER·LLM 双轨 | `past_condition.py` |
   | medication | 入院用药事件 | 结构化 · 确定性（类别归并） | `medication_features.py` |
   | absent | 否定症状事件 | 结构化 · 确定性 | `absent_features.py` |

   **生命体征只体现在 `physiologic_flag`，不进 `sign`**：`vital_measured` 的结构化数值经
   `vital_flags.py` 阈值化产出 9 个定性 flag——tachycardia（HR>100）、bradycardia（HR<60）、
   fever（体温 ≥37.0°C）、hypothermia（<35.0°C）、hypoxia（SpO2<92%）、tachypnea（RR>20）、
   bradypnea（RR<12）、hypotension（SBP<90）、hypertension（SBP≥140）——sign NER 明确排除生命
   体征，避免同一信息被 `sign` 与 `physiologic_flag` 两类特征重复计数。

3. **条件组合枚举**：对每个就诊的特征集做组合枚举生成条件 X（2–4 个特征，约束：≥1 个临床类、
   ≤1 个年龄、≤1 个性别），共 8,033,269 个条件组合（C1 归一化后）。

## 统计层（阶段 4–5）——统计定答案、程序锁选项

4. **规则挖掘**：对每个条件 X 与候选检查 y 计算共现计数（n_x/n_y/n_xy）与统计量：
   平滑条件概率 `smoothed=(n_xy+1)/(n_x+2)`、`lift=smoothed/baseline`、Wilson 区间下界、
   单侧 Fisher/Binomial p 值、BH-FDR q 值、bootstrap 第一名稳定性、综合 `score`。
   每个 X 下按 lift→score 排序（lift 排序修复影像类失衡，v1 实证 selectivity/lift 最优），
   第一名即 rank-1 正确答案。规则须同时过八道预登记硬门槛
   （support 5/4、smoothed 0.60、lift 1.20、wilson 0.35、fdr 0.05、bootstrap 0.80、
   gap 0.15 / ratio 1.25）才 `accepted`，否则 `rejected` 并记稳定拒绝码。
5. **选项锁定**：对每条 accepted 规则，从同家族、同粒度、可开立候选中选 3 个干扰项（同家族优先、
   就诊数接近），正确位置由 `sha256(rule_id)` 循环分配 A-D，程序确定性锁定、模型不得改动。

## 生成层（阶段 6–7）——LLM 只写题干、程序严格校验

6. **LLM 生成题干**：生成模型（DeepSeek Flash）仅返回 `stem` 与 `rationale` 两字段，用
   「most likely to be selected」的 RWD 预测语义（禁用 most appropriate / best next step 等
   规范性措辞），不得增删选项、决定答案、补规则外事实、在题干出现答案或同义词。
7. **12 条程序校验**：长度 / 预测语义 / 无答案或同义词泄漏 / 无日期与脱敏占位符 / 无 CJK /
   无后验事实 / 与源文本 5-gram Jaccard ≤0.55 / 选项恰为 A-D 且唯一 /
   options[correct_option]==answer / 答案==rank-1 / 条件特征一致；任一失败即丢弃并记稳定错误码。

## 审核层（阶段 8–10）——三道门禁才进 gold

8. **自动审题**：独立请求 + 独立 prompt，返回 10 项布尔裁定 + accept/reject/revise，
   全 true 且 accept 才 `candidate_passed`。
9. **人工审核**：仅 `candidate_passed` 进 `human_review_queue.csv`，临床 reviewer 逐条
   `approved/rejected/revise`。
10. **gold 门禁（fail-closed）**：同时满足「来源规则 accepted + 生成校验通过 + 自动审题
    candidate_passed + 人工 approved + schema/prompt 版本放行 + 非 exploratory 档」才导出 gold；
    任一环缺失即不发布，保证每道 gold 题可回溯到来源规则→统计量→生成模型/prompt→审核记录→人工决定。
