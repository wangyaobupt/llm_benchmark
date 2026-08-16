# 离院指导与随访（Discharge Follow-up）—— 框架（暂不可自动化出题）

> 依据 `docs/reports/five-dimension-execution-refinement.md` §2.5：本维**降级为 F1 文书轨**，且**规范主榜缓行到香港阶段**。

## 为什么暂不建行为 gold 出题

1. **MIMIC 内真实随访事件（F2）基本不可得**：MIMIC-IV 无出院后门诊/随访数据，行为轨只剩出院文书内容（F1）。
2. **F1 文书轨的四子轴都依赖出院小结全文**（`note.discharge.text`）：
   - 随访科室 / 随访时间窗（≤1周、1–4周、1–3月、3–12月、3–5年）
   - 带药变更（新开/停用/调整，prescriptions × 文书双源）
   - 红旗症状覆盖
3. 这些需要**全量聚合**（`raw_source_records` 回连出院全文），而全量聚合尚未运行（见 `investigation_selection/` 的说明）。

## 规范 gold（人工，缓行）

- 病种 surveillance 间隔表（可半自动、间隔离散天然适合 MCQ；但行为依从仅 48.8%）。
- MedRec 式带药比对（入院前用药 × 出院带药，专家双人）。
- **专家一致性全项目最低**（随访动作 κ 0.52–0.57）→ 双人+仲裁不可省。

## 何时启动

- **香港阶段**：HA 有 SOPC 门诊预约与再入院数据，可补 F2 真实随访事件——随访维在香港反而可能成为数据最全的一维。
- 若要在 MIMIC 阶段先行：需先跑全量聚合拿到出院全文，再实现 F1 四子轴的离散化抽取（这属于文本 NER/RE 支路的下游消费）。

## 当前状态（P0-1 已建骨架）

已有 `src/` 两段：出院全文抽取 + 随访时间窗首抽（正则，非 NER）。

| 产物 | 结果 |
|---|---|
| 出院全文抽取 | dev 23,626 住院 → 21,757（92%）有出院小结全文 `output/development/discharge_text.parquet` |
| 随访时间窗首抽 | 1,330 匹配 / 1,089 住院（~5%），分布 1-4w(509) > ≤1w(373) > 1-3m(318) > 3-12m(130) |

**结论**：出院全文可得（92%），但显式「随访时间窗」表述稀疏（~5%），且多写为「follow up with <科室> in N weeks」。这与 survey §2.5 一致（随访动作专家一致性全项目最低 κ 0.52–0.57）。F1 完整四子轴需文本 NER/RE 支路 + 以「出院诊断」而非「主诉」为键，非本阶段正则可完成。

行为/规范双轨的 MCQ gold 尚未建，故无 final_test 盲测项。

## 运行

```powershell
.\.venv\Scripts\python.exe tasks/discharge_followup/src/extract_discharge.py --role development
.\.venv\Scripts\python.exe tasks/discharge_followup/src/extract_followup_window.py
```
