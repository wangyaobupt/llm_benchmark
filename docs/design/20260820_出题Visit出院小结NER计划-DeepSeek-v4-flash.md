# 出题 Visit 出院小结 NER 计划（DeepSeek-v4-flash）

> **版本**: v1.0  
> **日期**: 2026-08-20  
> **状态**: 模块已落地，默认空跑；尚未对 10k 调用外部 API  
> **评测状态**: `exploratory_unreviewed`；`gold = 0`  
> **上游抽取**: `data/derived/mcq_visit_extract/random10k_dev20/visits.json`  
> **上游标准化**: `data/derived/mcq_visit_standardize/random10k_dev20_v1.0.9/`（术语层；本 NER 不读它当原文）  
> **实现**: `data_pipeline/mcq_visit_ner/`

---

## 0. 这一步做什么

结构化字段（主诉切开、检验名、药物名）已经在标准化层处理。出院小结叙事里的症状、问题、检查、药物仍是自由文本。

本层只做 span NER：

> 从冻结 `visits.json` 的出院小结原文抽出 mention，`surface_text` 必须是源文字符串，偏移在 Python 里接地。然后才允许用已审核同义词表做实体标准化。不出题。

```text
visits.json（只读，不改写 DS）
        │  prepare：按字段切块，写 documents.jsonl
        ▼
mention_results.jsonl（API + 接地，可续跑）
        │  compile
        ▼
visit_mentions.jsonl（一行一次住院，非正式 gold）
        │  后续：用 reviewed_synonyms 映射标准名（本模块不做）
        ▼
不出题，直到 NER 覆盖与映射过门禁
```

不消费 `text_ner_v2` 的聚合事件；不覆盖抽取目录；不把标准化后的概念列表当成 NER 原文。

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
