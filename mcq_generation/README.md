# MCQ 生成模块

本目录存放五类英文 A–D 临床决策题的**设计文档**。题目生成代码尚未实现；当前 `gold = 0`。

**现行抽取实现是第三版直抽**：`data_pipeline/mcq_visit_extract/` 只读 `data/RawData` 的 MIMIC CSV.GZ，不读事件 Parquet、不读冠心病归档。检查选择重建仍在 `data_pipeline/investigation_selection/`（另一条轨道）。旧 V1 / V2 出题分别在 `versions/v1-template-stem/` 与 `versions/v2-llm-stem/`，不得当新 gold。

## 当前状态

底座第三版已抽 10,000 例并完成标准化；时间线与分家族挖掘待跑。本目录仍是题型/字段规范，不是运行入口。

| 文件 | 作用 |
|---|---|
| `真实世界数据临床基准题型规范.md` | 五类题型规范 |
| `RWD Clinical Benchmark 检查检验选择题生成设计.md` | 题型 1（检查检验选择）生成设计 |
| `MCQ 出题逻辑.md` | 统计定答案 → 程序锁选项 → LLM 只写题干 |
| `MCQ 生成模块：设计逻辑综合.md` | 跨文档设计综合 |
| `出题数据抽取规范.md` / `出题数据抽取字段规范.md` / `出题全流程字段需求映射.md` | visit 字段与漏斗合同；**实现按第三版从 CSV.GZ 直抽**，不要拿去抽 event pipeline |
| 第三版执行计划 | [`docs/design/20260820_出题数据抽取第三版-1万例随机Visit直接抽取执行计划.md`](../docs/design/20260820_出题数据抽取第三版-1万例随机Visit直接抽取执行计划.md)：从 MIMIC 原始 CSV.GZ 按 `(subject_id, hadm_id)` 随机抽 10,000 例；交付 `visits.csv` + `visits.json`（一行一次住院，只含结果；溯源留在过程文件） |
| 标准化计划 | [`docs/design/20260820_出题Visit标准化计划-术语单位症状.md`](../docs/design/20260820_出题Visit标准化计划-术语单位症状.md)：术语 / 单位 / 主诉症状概念；不覆盖抽取、不改写 HPI 与出院小结正文 |
| 时间线 + 挖掘计划 | [`docs/design/20260820_出题Visit时间线合并与规则挖掘计划-1万例全量.md`](../docs/design/20260820_出题Visit时间线合并与规则挖掘计划-1万例全量.md)：NER 先停；时钟与标准名合成时间线后，对 10,000 例全量挖五类 X→y；不出题 |

## 五类题型

1. Clinical investigation selection（检查检验选择）
2. Clinical diagnosis（临床诊断）
3. Treatment and management（治疗处置）
4. Referral and specialty selection（转诊科室）
5. Discharge advice and follow-up（离院指导）

题目生成代码待实现。Visit 行文件由 `python -m data_pipeline.mcq_visit_extract` 从 CSV.GZ 写出，不要按本目录规范去抽事件管线产物。
