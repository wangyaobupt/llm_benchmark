# 出题 Visit 出院小结 NER 计划（DeepSeek-v4-flash）

> **版本**: v1.1
> **日期**: 2026-08-20  
> **状态**: 残余 NER 已落地并完成 10 例验证；尚未对 10k 调用外部 API
> **评测状态**: `exploratory_unreviewed`；`gold = 0`  
> **上游抽取**: `data/derived/mcq_visit_extract/random10k_dev20/visits.json`  
> **上游标准化**: `data/derived/mcq_visit_standardize/random10k_dev20_v1.0.9/`（术语层；本 NER 不读它当原文）  
> **实现**: `data_pipeline/mcq_visit_ner/`

---

## 0. 这一步做什么

结构化字段（主诉切开、检验名、药物名）已经在标准化层处理。出院小结叙事里的症状、问题、检查、药物仍是自由文本。

本层只做残余 span NER：

> 先在本地扣除同一 visit 已有结构化字段中的主诉、诊断、检查、检验、药物和操作等内容，只把残余叙事交给模型。`surface_text` 必须是源文字符串，偏移在 Python 里接地。然后才允许用已审核同义词表做实体标准化。不出题。

```text
visits.json（只读，不改写 DS）
        │  prepare：收集结构化 surface、本地掩码、按字段切块
        ▼
documents.jsonl（原文 + 残余 model_text；仅本地）
        │  结构化-only 切块直接跳过 API
        ▼
mention_results.jsonl（残余 API + 原文接地，可续跑）
        │  compile
        ▼
visit_mentions.jsonl（一行一次住院，非正式 gold）
        │  后续：用 reviewed_synonyms 映射标准名（本模块不做）
        ▼
不出题，直到 NER 覆盖与映射过门禁
```

不消费 `text_ner_v2` 的聚合事件；不覆盖抽取目录；不把标准化后的概念列表当成 NER 原文。已有结构化内容在 API 请求前替换为 `[S]`，模型不得重建标记后的实体，Python 再按原文 span 做硬过滤。

---

## 1. 模型与端点

| 项 | 值 |
|---|---|
| Provider | OpenAI Compatible |
| Base URL | `https://www.dmxapi.cn/v1` |
| Model ID | `deepseek-v4-flash` |
| 环境变量 | `MCQ_VISIT_NER_*`（不要用 `TEXT_NER_*`） |

凭据只放本地 `.env`。仓库与对话都不写 API Key。

`text_ner.deepseek_adapter` 对 `restricted_mimic` 硬阻断且不可环境变量覆盖。本模块走通用 OpenAI 兼容客户端，因此额外三重闸门：

1. CLI `--execute`
2. CLI `--confirm-data-transfer-authorized`
3. `MCQ_VISIT_NER_EXTERNAL_API_APPROVED=YES`

缺一不可。默认 `prepare` 不调模型。`prepare` 未指定 `--max-visits` 时，`run` 还要 `--all-visits`，防止误发 10,000 份出院小结。

---

## 2. 输入与字段

输入必须是抽取产物 `visits.json`，不是 `visits_standardized.json`。默认字段：`discharge_note_full`。该字段为空时回退到已切开的叙事列（主诉、HPI、PMH、体格、病程、出院诊断）。

切块：3000 字符、重叠 200，优先段落/换行/句点。Checkpoint 键为 `hadm_id:field:chunk_index`。

---

## 3. 接地规则

模型不得输出 Unicode 偏移。Python：

1. `surface_text` 在 chunk 内唯一精确命中 → 采用
2. 否则大小写 + 空白折叠后唯一命中 → 采用并把 `surface_text` 改回源切片
3. 缺失或歧义 → 丢弃

标准化实体名不在本层做。后续映射必须从接地后的源切片出发，沿用 `reviewed_synonyms.jsonl`。

---

## 4. 执行顺序

1. `prepare --max-visits 100`（试点）
2. 人工看 `status` / `progress.json`（无病历原文）
3. 显式授权后 `run`
4. `compile`
5. 抽查 grounding 与否定/历史属性
6. 通过后再换新 `output-dir` 跑 10,000 例
7. 仍不出题

产物：`data/derived/mcq_visit_ner/<run>/`。`gold = 0`。

---

## 5. 10 例成本验证

2026-08-20 使用 `random10k_dev20` 前 10 例、30 个相同切块对比旧版全量 NER：

| 指标 | 旧版 | 残余 NER | 降幅 |
|---|---:|---:|---:|
| Prompt tokens | 48,541 | 45,025 | 7.24% |
| Completion tokens | 51,526 | 23,449 | 54.49% |
| Total tokens | 100,067 | 68,474 | 31.57% |
| 模型返回 mentions | 1,358 | 549 | 59.57% |

`prepare` 在 79,085 个原始字符中定位 341 个已结构化 span，替换后字符数减少 3.27%。编译得到 540 个去重 mentions，与结构化字段精确 surface 重复为 0。结论是主要节省来自减少 completion，而不是删除全文上下文；若后续还要显著压低 prompt tokens，需要另行设计句级候选门控并验证召回率，不能直接删上下文。
