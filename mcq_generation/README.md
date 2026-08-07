# MCQ 生成模块

本模块负责从 RWD 数据底座生成五类英文 A-D 单选临床 MCQ，用于评测 LLM 的临床判断能力。

## 当前状态：设计阶段

- `architecture_overview.md` — 跨文档架构总览
- `mcq_generation_design.md` — 题型 1（检查检验选择）Stage 0-10 完整生成设计
- `question_types.md` — 五类题型规范 + EHR 字段表

## 五类题型

1. Clinical investigation selection（检查检验选择）— 完整设计
2. Clinical diagnosis（临床诊断）— 题型规范
3. Treatment and management（治疗处置）— 题型规范
4. Referral and specialty selection（转诊科室）— 题型规范
5. Discharge advice and follow-up（离院指导）— 题型规范

生成代码待实现。
