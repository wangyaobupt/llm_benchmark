# MCQ 生成模块

本目录存放五类英文 A–D 临床决策题的**设计文档**，不是现行检查选择实现。正式生成须等 1,000 例 integration audit 通过；当前 `gold = 0`。

检查选择重建代码在 `data_pipeline/investigation_selection/`。旧 V1 / V2 出题分别在 `versions/v1-template-stem/` 与 `versions/v2-llm-stem/`，不得当新 gold。

## 当前状态：设计阶段

| 文件 | 作用 |
|---|---|
| `真实世界数据临床基准题型规范.md` | 五类题型规范 |
| `RWD Clinical Benchmark 检查检验选择题生成设计.md` | 题型 1（检查检验选择）生成设计 |
| `MCQ 出题逻辑.md` | 统计定答案 → 程序锁选项 → LLM 只写题干 |
| `MCQ 生成模块：设计逻辑综合.md` | 跨文档设计综合 |
| `出题数据抽取规范.md` / `出题数据抽取字段规范.md` / `出题全流程字段需求映射.md` | 2026-08-07 visit 级 JSONL 抽取旧规范；已被 event pipeline 取代，只作历史对照 |

## 五类题型

1. Clinical investigation selection（检查检验选择）
2. Clinical diagnosis（临床诊断）
3. Treatment and management（治疗处置）
4. Referral and specialty selection（转诊科室）
5. Discharge advice and follow-up（离院指导）

生成代码待实现。不要按本目录旧 visit JSONL 规范去抽现行 MIMIC 事件。
