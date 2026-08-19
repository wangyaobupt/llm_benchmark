# MCQ 出题逻辑

> 本文档单独说明 MCQ 模块的出题逻辑：一道题从数据到 gold 的完整决策链、每一道关卡的具体规则，以及"为什么这样设计"。内容综合自 `mcq_generation_design.md`（题型 1 设计）与 `question_types.md`（通用出题原则）。

## 1. 出题逻辑一句话

> **统计定答案，程序锁选项，LLM 只写题干，三道门禁才进 gold。**

即：先由真实世界数据统计确定"哪个选项正确"，再由程序固定"有哪些选项、正确位置在哪"，LLM 只负责把条件特征写成合成题干，最后经过程序校验、自动审题、人工审核三重关卡，全部通过才发布。

## 2. 出题链路总览

```text
输入数据（visit 级 RWD）
   │
   ▼
┌─────────────────────────────────────────────────────────────┐
│ ① 特征标准化    主诉→症状、年龄→年龄段、检查名→标准概念      │
│ ② 事务构建      visit → {features, outcomes}                │
│ ③ 规则挖掘      X→y，8 道统计硬门槛 → accepted/rejected      │
│ ④ 选项锁定      3 干扰项 + A-D 位置（程序确定性分配）         │
│ ⑤ LLM 生成      stem + rationale（权限受限）                │
│ ⑥ 程序校验      12 条检查，不过即丢弃                       │
│ ⑦ 自动审题      独立请求，9 项布尔裁定                        │
│ ⑧ 人工审核      approved / rejected / revise                │
│ ⑨ Gold 导出     fail-closed 门禁                            │
└─────────────────────────────────────────────────────────────┘
```

## 3. 出题资格：什么样的规则能出题

只有**同时通过 8 道统计硬门槛**的 accepted 规则才能出题：

| 门槛 | 默认值 | 淘汰什么 |
|---|---|---|
| min_x_support | 5 | 条件样本太少 |
| min_xy_support | 4 | 共现太少 |
| min_smoothed_probability | 0.60 | 条件概率不够高 |
| min_lift | 1.20 | 不比基线好 |
| min_wilson_lower | 0.35 | 小样本区间太宽 |
| max_fdr_q | 0.05 | 多重检验后不显著 |
| min_bootstrap_stability | 0.80 | 第一名不稳定 |
| min_probability_gap / min_score_ratio | 0.15 / 1.25 | 与第二名区分度不足 |

附加规则：

- 条件 X 必须含至少一个症状/体征/生理标志/否定特征（absent），至多一个年龄段、一个性别；
- 正确答案永远是该条件下的 rank-1 检查项（第一名与第二名区分度不达标 → 淘汰，不换答案）；
- 只有一个可用 outcome 的规则无法组成四选一 → 淘汰；
- 宽松阈值（exploratory）跑出的规则**只能开发调试，不能出正式题**。

## 4. 选项构造逻辑

### 4.1 干扰项（3 个）

候选过滤：

- ≠ 正确答案；可开立（is_orderable）；粒度与答案相同（specific）；非答案同义词/别名；可比较的检查项（排除检查家族、科室、治疗、诊断）。

候选排序（取前 3 个）：

```text
1. 与答案同检查家族 → 优先
2. |候选就诊数 − 答案就诊数| 小 → 优先
3. canonical_name 升序
4. investigation_id 升序
```

设计意图：**同家族 + 就诊数接近**使干扰项在临床上既有迷惑性又合理，同时完全确定性、不依赖模型创造选项。不足 3 个 → 整条规则跳过（insufficient_distractors），不调用 LLM。

### 4.2 答案位置

- 先按 `sha256(rule_id)` 对所有待出题规则稳定排序，再循环分配 A、B、C、D；
- 干扰项内部顺序由 `sha256(rule_id + investigation_id)` 决定；
- 位置在题干生成**之前**锁定，LLM 无法改动；大样本上 A-D 分布近似均衡（防位置偏置）。

## 5. LLM 生成题干：权限边界

LLM 只能返回两个字段：

```json
{
  "stem": "A patient presents with ... Which investigation is most likely to be selected?",
  "rationale": "In the source data, ... is most strongly associated with selection of the keyed investigation."
}
```

**明令禁止**：输出/改写/重排选项；决定正确答案；补充规则之外的患者事实；把问题改成诊断、治疗或规范性建议；在题干中出现答案或其同义词；把观察性关联说成因果关系或指南推荐。

约束规则：

- 题干只用规则中的 2-4 个特征（特征不够也不许编造）；
- 必须使用"真实世界最可能被选择"语义（most likely to be selected），**不得**使用 most appropriate / best next step / gold standard 等规范性措辞；
- rationale 一句话，只描述来源数据中的选择关联；
- 请求采用 JSON response mode + 确定性参数（temperature=0），最多 5 次重试。

## 6. 程序级校验：12 条检查

LLM 输出通过结构化 Schema 后，还必须全过：

| # | 检查 | 防什么 |
|---|---|---|
| 1 | stem/rationale 满足最小长度 | 空答 |
| 2 | 含预测语义 "most likely to be selected" | 语义漂移 |
| 3 | 题干无答案 canonical name 或登记同义词 | 答案泄漏 |
| 4 | 无精确日期/机构/患者标识/脱敏占位符 | 隐私 |
| 5 | 英文题无 CJK 字符 | 语言 |
| 6 | 无未提供的临床事实 | 幻觉/后验泄漏 |
| 7 | 与源文本 5-word shingle Jaccard ≤ 0.55 | 复制病历 |
| 8-9 | options 恰好 A-D 且非空唯一 | 选项结构 |
| 10 | options[correct_option] == correct_answer | 一致性 |
| 11 | correct_answer == 规则 rank-1 | 答案正确 |
| 12 | condition_features 与来源规则一致 | 条件篡改 |

任一失败 → 记录稳定错误码（answer_leaked_in_stem、source_overlap 等），本题丢弃，不进 candidates。

## 7. 审核与发布门禁

### 7.1 自动审题（独立隔离）

- 独立请求 + 独立 prompt（可与生成同模型，但调用、task type、上下文完全隔离）；
- 只返回 9 个布尔裁定 + recommendation（accept/reject/revise），**不得修改题目**；
- 重点核实：RWD 预测语义、唯一最佳答案、无答案泄漏、选项同粒度、统计支持充分、场景合成且安全（危险表现不得包装成常规检查建议）、英文质量；
- 全部 true + accept → `candidate_passed`；任何一项失败或审核异常 → `candidate_rejected`（审核失败不能保持 pending）。

### 7.2 人工审核

- 只有 `candidate_passed` 的题进入人工队列；
- 决定：approved / rejected / revise；重建队列按 question_id 合并、保留已有人工字段；
- 题目内容或来源规则变化 → 必须产生新 ID 或显式作废旧批准。

### 7.3 Gold 门禁（fail-closed）

同时满足才发布：

```text
source rule == accepted
生成校验 == passed
自动审题 == candidate_passed
人工决定 == approved
schema/prompt 版本允许发布
run profile 非 exploratory
```

任何一环缺失 → 不发布。每道 gold 题可完整回溯：来源规则 → 统计量 → 生成模型/prompt → 审核记录 → 人工决定。

## 8. 出题通用红线（五类题型共享）

- **答案来源字段与题干严格分离**：答案字段（如检查医嘱）绝不进题干，后验信息（诊断、检查结果、治疗）一律不得提前泄漏；
- **合成病例**：不复制真实病历，不出现直接身份信息，不得用罕见特征组合重建真实患者；
- **医疗安全优先**：生命体征不稳定的危险情况，不得把常规门诊检查/延迟处理设为最佳答案；
- **单一决策**：一道题只问当前临床阶段的一个决策，题干只保留 2-4 项决定答案的关键信息；
- **确定性优先**：任何一步失败都只淘汰本题，不改变统计答案、不临时放宽门槛凑数。

## 9. 出题决策树速查

```text
规则 X→y 通过 8 道硬门槛？
 ├─ 否 → rejected，不出题
 └─ 是（accepted）
     ├─ 有 ≥3 个合格干扰项？  ── 否 → 跳过（insufficient_distractors）
     ├─ 锁定 3 干扰项 + A-D 位置（程序）
     ├─ LLM 生成 stem+rationale
     ├─ 12 条程序校验通过？    ── 否 → 丢弃本题
     ├─ 自动审题 9 项全过？    ── 否 → 拒绝
     ├─ 人工 approved？       ── 否 → 拒绝/修订
     └─ 全部通过且非 exploratory → 进入 gold ✓
```
