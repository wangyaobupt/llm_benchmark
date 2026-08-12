# Cleaned events 下一轮改善评估

## 结论

当前 `data/derived/event_pipeline_sample_100/cleaning/` **不能判定为 cleaned events 阶段已经完成，必须进行下一轮清洗修复**。现有结果可以作为可复用基础，但不能据此开始新的结构化归一化或文本实体识别。

原因不是现有 57,777 条事件整体失效，而是当前验收只证明了旧 `SOURCE_REGISTRY` 中 14 张事件源的内部一致性，没有覆盖本轮拟纳入的诊断、HCPCS、ED 药物和 ICU 输入输出事件；同时 pharmacy 的拒绝发生在原生键连接之前，eMAR 没有形成可追溯的药物连接，全事件时间倒置也没有得到完整解释。

## 审计范围

- 清洗目录：`data/derived/event_pipeline_sample_100/cleaning/`
- 事件输入：`data/validation/mimic-admission-raw-coronary-sample-100-poe-timeline-decoded.jsonl`
- 原始回查输入：`data/validation/mimic-admission-raw-coronary-sample-100.jsonl`
- 样本：100 次住院
- 审计方式：只读检查 Parquet、manifest、源表对账、全量追溯、原生键连接和时间关系；未调用归一化、NER 或外部模型。

## 当前结果中可以保留的部分

| 检查项 | 结果 | 判定 |
|---|---:|---|
| `cleaned_events.parquet` | 57,777 行，12 个 row groups，ZSTD | 结构可读 |
| `cleaning_rejected.parquet` | 251 行 | 结构可读，但拒绝逻辑需修复 |
| `encounter_manifest.parquet` | 100 行 | 与100次住院一致 |
| `event_id` | 57,777 行均非空且全局唯一 | 通过 |
| 已注册源表对账 | 57,144 个源行全部被 accepted 或 rejected 分类 | 仅在旧注册范围内通过 |
| 现有事件追溯 | 57,777 条事件及251条拒绝记录均可回查 | 通过 |
| 文件哈希 | manifest 中所有输出哈希均与当前文件一致 | 通过 |
| 上游原始内容 | 去除解码字段和 `poe_timeline` 后，100行内容与原始输入一致 | 通过 |
| `post_hoc` | `procedures_icd` 225条、出院小结68条 | 当前范围内正确 |

旧验收脚本复跑结果仍为 `can_start_normalization=true`，但其覆盖集合直接来自旧 `SOURCE_REGISTRY`，因此这个结论只能解释为“旧范围内部通过”，不能解释为“完整 cleaned events 已完成”。

## 阻断问题

### P0-1：源表覆盖契约不完整

100例输入中存在33个表或派生表数组，当前 `source_reconciliation.json` 只覆盖14张事件源，而且没有为其余表提供 `support`、`context` 或 `excluded` 的逐表理由。

以下8,667个拟作为事实拥有者的源行完全没有进入当前 cleaned events：

| 待纳入源表 | 源行数 | 应保持的语义 |
|---|---:|---|
| `hosp.diagnoses_icd` | 1,727 | 诊断记录，`post_hoc` |
| `ed.diagnosis` | 80 | ED诊断记录，`post_hoc` |
| `hosp.hcpcsevents` | 33 | HCPCS记录，`post_hoc` |
| `ed.medrecon` | 521 | 药物核对/用药史，不等于给药 |
| `ed.pyxis` | 143 | 药品取用或发放，不等于给药 |
| `icu.inputevents` | 4,352 | ICU输入/输注事实 |
| `icu.outputevents` | 1,811 | ICU输出测量事实 |
| **合计** | **8,667** |  |

辅助表也没有得到明确的非事实角色。例如 `poe`/`poe_detail`、`emar_detail`、`ingredientevents`、住院和就诊主表应参与连接或提供上下文，但不能因注册而重复产生临床事实。

**影响：** 当前事件集合存在系统性缺失；继续归一化会把旧覆盖范围固化为新的下游版本。

### P0-2：pharmacy 在原生键连接前错误拒绝

当前251条拒绝记录全部为 `PHARMACY_MEDICATION_MISSING`。对100例输入重新按 `pharmacy_id` 和 `poe_id` 核查后：

| 连接结果 | 行数 |
|---|---:|
| 可唯一确定药物 | 208 |
| 多候选，需 review | 23 |
| 无候选，需 unresolved/review | 20 |

至少208条记录本可通过原生键确定性补充，不应被直接拒绝。多候选也不应任选一个；无候选时还需先判断 pharmacy 工作流事实本身是否成立，不能把“药名未解析”等同于“源事件无效”。

**影响：** 当前 rejected 队列混入了可确定性恢复的事实，accepted/rejected 对账在形式上成立，但分类语义错误。

### P0-3：eMAR 没有形成可追溯的药物连接

100例中共有11,343条 eMAR：

| 检查项 | 行数 |
|---|---:|
| 存在 `pharmacy_id` | 9,434 |
| `pharmacy_id` 可匹配 pharmacy | 9,414 |
| `poe_id` 可匹配 prescription | 9,710 |
| 任一原生键可匹配 | 10,880 |
| eMAR 原始药名缺失 | 539 |
| 缺失药名且可唯一解析 | 302 |
| 缺失药名且多候选 | 217 |
| 缺失药名且未解析 | 20 |

当前 eMAR 转换器没有使用这些连接，输出中的 eMAR 事件也没有 pharmacy、prescription 或 `emar_detail` 的 supporting lineage。现有 supporting references 只有5,169条指向 `poe_timeline`，来自处方订单时间连接。

**影响：** 539条 eMAR 的药物实体为空，其中302条本可确定性恢复；其余歧义也没有进入独立 review 队列。药物事实的来源链不完整。

### P0-4：全事件时间倒置没有完整解释

当前事件中共有267条 `available_time < event_time`：

| 源表 | 行数 | 当前处理 |
|---|---:|---|
| `hosp.emar` | 266 | 有通用 `AVAILABLE_BEFORE_EVENT_TIME` 标志，但无源表特异原因 |
| `note.discharge` | 1 | 没有该质量标志，也没有解释 |

当前验证器只对一组预设的结果类事件拒绝时间倒置，并非全事件检查。通用标志只能说明“发现倒置”，不能说明为何允许该事件通过以及下游如何使用它。

拟新增的 ICU 表还存在尚未进入现有审计的倒置：

| 原始表 | `storetime` 早于事件时间 |
|---|---:|
| `inputevents` | 265 |
| `outputevents` | 258 |
| `ingredientevents` | 320 |
| `datetimeevents` | 173 |

**影响：** 如果下游只使用 `available_time <= index_time`，倒置事件可能造成未来信息泄漏。决策快照必须同时要求 `event_time <= index_time` 和 `available_time <= index_time`，清洗层还必须记录源表特异的解释和允许策略。

## 重要但可随下一轮一并修复的问题

### P1-1：缺少独立 cleaning review 队列

当前目录只有 accepted 和 rejected。药物多候选、连接未解析、无法解释的时间倒置需要独立 review 状态；这些情况不应被迫塞入 accepted 或 rejected。

### P1-2：缺少全源表覆盖清单和支持表对账

需要分别对账：

- 事件源：`input source rows = accepted + review + rejected`；
- 支持源：`input support rows = linked + unlinked`；
- 上下文或排除源：每张表必须有明确原因。

不能用事件行数代替源行数，也不能只遍历事件注册表来证明全部原始表已处理。

### P1-3：现有 `term_inventory.parquet` 属于旧清洗快照

该文件本身不证明已执行术语归一化，但它只对应当前 SHA-256 为 `f9b485bf227c95a2d36413309111a8fb0da66dee9fb4fbcf28c6b1412a43fe97` 的旧 `cleaned_events.parquet`。下一轮清洗重建后必须重新生成，不能沿用。

## 下一轮改善的正确边界

下一轮仍只处理 cleaned events，不运行结构化归一化或NER：

1. 建立覆盖全部输入表的 source catalog，分离事件事实拥有者与 support/context/excluded 表。
2. 先构建 pharmacy、prescription、POE、eMAR、`emar_detail` 的确定性连接层，再执行 pharmacy 和 eMAR 转换。
3. 纳入诊断、ED诊断、HCPCS、ED medrecon、ED Pyxis、ICU input/output；保持各自原始语义和 `post_hoc` 属性。
4. `ingredientevents` 先作为 inputevents 的组成/支持信息；`datetimeevents` 在值时间与记录时间语义冻结前不独立生成事实。
5. 对所有事件执行统一时间门禁，并给每种允许倒置配置源表特异的 reason code 和下游可见性规则。
6. 在临时输出目录重建100例，全部门禁通过后再原子替换当前 cleaning 目录。
7. 重新运行独立审计；在此之前不启动下游处理。

## 下一轮必须生成的清洗层产物

- `cleaned_events.parquet`
- `cleaning_review.parquet`
- `cleaning_rejected.parquet`
- `encounter_manifest.parquet`
- `source_coverage_manifest.parquet`
- `source_lineage.parquet`
- `medication_linkage.parquet`
- `source_reconciliation.json`
- `run_manifest.json`
- 由新 cleaned SHA-256 重新生成的 `term_inventory.parquet`

## 下一轮完成门槛

只有同时满足以下条件，才能宣布 cleaned events 阶段完成：

1. 全部输入表均有且仅有一个明确角色和纳入/排除原因。
2. 上述8,667个拟纳入源行全部进入 accepted、review 或 rejected 对账，不再从注册表中缺失。
3. pharmacy 不再因药名为空而在原生键连接前直接拒绝；208条唯一可解析记录得到确定性处理。
4. eMAR 的302条唯一可解析缺失药名得到带来源的派生补充，217条多候选和20条未解析记录被明确分类。
5. 所有 supporting source references 可回查到同一患者和住院的原始行。
6. 所有 `available_time < event_time` 均有源表特异的解释、质量标志和允许策略；无法解释的进入 review/rejected。
7. `event_id` 全局唯一且在相同输入、规则和版本下可重复生成。
8. accepted/review/rejected、linked/unlinked 及逐住院对账全部成立。
9. manifest 的输入、输出、规则版本和 SHA-256 与实际文件一致。
10. 新的独立审计报告明确给出通过结论后，才允许进入结构化归一化或文本NER。

## 最终判定

**需要继续下一轮改善。当前 cleaned events 的旧覆盖范围内部一致，但完整性、药物连接、拒绝分类和全事件时间契约均未达到阶段完成标准。**
