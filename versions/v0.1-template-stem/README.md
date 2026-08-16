# 版本 v0.1-template-stem（冻结快照）

> 本目录是对「模板题干 + 确定性统计 gold」这一版 bench 产物的**完整聚类快照**，作为后续任何版本演进的固定基线。目录内产物只读，不得改写；如需演进，在新版本目录（`versions/<新版本名>/`）下派生。

## 1. 版本信息

| 项 | 值 |
|---|---|
| 版本号 | `v0.1-template-stem` |
| 冻结时间 | 2026-08-16 16:15:39 |
| git 分支 / commit | `master` / `d9af459947ecf8333652c681e0beb256e56dbe06` |
| 状态 | `exploratory_unreviewed`（探索性未审核，非正式评测产物） |
| 出题方式 | 模板题干（f-string），**零 LLM 参与** |
| gold 方式 | 确定性统计（selectivity / PSR），来自 MIMIC 真实事件，**零 LLM 参与** |

## 2. 这一版是什么

- **题干**：固定模板 `A patient presents to the emergency department with {主诉}. Which …?`，只含归一化主诉，不含病例级具体特征（年龄/伴随症状/生命体征/化验结果等）。
- **gold 答案**：从 MIMIC-IV 真实事件流用统计方法确定性算出（行为 gold = 真实临床最可能发生什么）。
- **干扰项**：从候选池取「前 3 个非 gold」项（非层次化、跨题复用）。
- **评测**：唯一 LLM 参与环节是「模型答题」（当前仅 DeepSeek `deepseek-v4-flash` 单模型）。

五维中**四维已出 MCQ**，`discharge_followup`（离院指导与随访）无 MCQ gold，仅出院全文抽取 + 随访时间窗正则骨架，不参与本基线。

## 3. 题量与 gold 语义

| 维度 | gold 语义 | development 题 | validated rank-1 | validated top-3 |
|---|---:|---:|---:|---:|
| 检查检验选择 | selectivity | 224 | 84 | 104 |
| 临床诊断 | PSR | 94 | 24 | 27 |
| 治疗 T1（开立） | selectivity | 90 | 30 | 39 |
| 治疗 T2（执行） | selectivity | 77 | 24 | 33 |
| 治疗 T3（手术） | selectivity | 55 | 26 | 34 |
| 转诊与科室选择 | selectivity | 115 | 33 | 42 |
| **合计（validated rank-1）** | | | **221** | |

## 4. DeepSeek 基线（单模型，`deepseek-v4-flash`）

> 仅 `unreviewed_model_output`，非正式榜单结果。`temperature=0`、thinking 关闭、选项按 `question_id` 确定性 shuffle。

| 维度 | n | 准确率 | 分层 |
|---|---:|---:|---|
| 检查检验选择 | 84 | **53.57%** | imaging 79.41% / clinical_order 19.05% / laboratory 48.28% |
| 临床诊断 | 24 | **95.83%** | — |
| 治疗 T1 | 30 | **66.67%** | — |
| 治疗 T2 | 24 | **87.50%** | — |
| 治疗 T3 | 26 | **73.08%** | — |
| 转诊 | 33 | **60.61%** | — |

## 5. 目录结构

```text
versions/v0.1-template-stem/
├── README.md                  # 本文件（版本说明 + 细节）
├── FREEZE_MANIFEST.json       # 版本元信息 + 核心数字（题量/基线/输入哈希）
├── artifacts_sha256.json      # 全部 115 个产物文件的 SHA-256 锚定清单
├── src_sha256.json            # 全部 43 个代码文件的 SHA-256 锚定清单
├── src/                       # 出题/评测代码快照（benchmark_common + 五任务 src/）
│   ├── benchmark_common/      # 共享框架：task.py / stats.py / conditions.py / io.py / __init__.py
│   └── tasks/                 # 五任务核心与 explore 脚本（38 个 .py，含 __init__）
└── artifacts/                 # 聚类产物（与 tasks/ 同构）
    ├── investigation_selection/output/   # split / development / validated / validation / final_test / gold_semantics_comparison
    ├── clinical_diagnosis/output/        # development / validated / validation / final_test
    ├── treatment/output/                 # 分层 t1/t2/t3 + 旧合并版 development/validated/validation
    └── referral/output/                  # development / validated / validation / final_test
```

- `src/` 是**代码快照**：`benchmark_common/`（5 文件）＋五个任务的 `src/`（38 文件，含 explore 勘察脚本与 `__init__.py`），共 43 个 `.py`，与仓库原位置同构。用途是**溯源**（这版产物是哪份代码跑出来的）；实际复现仍在仓库原位置运行，`src/` 只读、不改。

- `gold_semantics_comparison/`：检查维 4 种 gold 语义（likelihood / psr / selectivity / specificity×reliability）对比实验，是「selectivity 最优」结论的方法学证据。
- `treatment/output/development|validated|validation`：P1-1 重构**前**的旧合并版（155 题），已被分层 `t1/t2/t3` 取代，仅存档。
- 各维度 `final_test/`：重构前的**盲测**结果，数字与当前代码不对应，仅存档。
- `investigation_selection/output/development/eval_results.*`：重构前在 development 集上的旧评测（`total_scored=385`，与当前 224 题不对应），仅存档。
- `discharge_followup/output/development/` 的 4 个文件（`discharge_text.parquet` / `extraction_manifest.json` / `followup_window_manifest.json` / `followup_window.parquet`）**未聚类**：该维无 MCQ、不参与本基线，此处仅作范围界定说明。

## 6. 输入数据（未聚类，仅引用哈希）

| 输入 | 位置 | 说明 |
|---|---|---|
| `normalized_events.parquet` | G 盘 `data\derived\coronary_all_three_modules_full\event_pipeline\normalization\` | 出题/验证/划分的统一输入；SHA-256 `69f29e310a53c980857dd8159b1f2e4cedfa823719754e116935d7d2751bb7cf`；体积大不复制 |
| `subject_split.parquet` | 已聚类进 artifacts | 患者级划分；SHA-256 `80f9b4e213102e40abedf86b6c7fa5fe6498ba69d22222e4bc1f5d6e79471846` |
| `mimic-admission-raw-coronary-all-three-modules.jsonl` | G 盘 `data\validation\` | `discharge_followup/extract_discharge.py` 引用；未聚类 |
| `raw_source_records.parquet` | D 盘 `data\test_1000_0812\event_pipeline_output\aggregation\` | `investigation_selection/explore_seqnum.py` 引用；未聚类 |

患者级划分比例：60/20/20（development/validation/final_test）。

> 后两个文件是部分脚本（discharge 抽取、一个 explore 勘察脚本）的硬编码输入，非本快照「产物」范围，也未纳入哈希锚定；此处仅登记其存在，避免遗漏。

## 7. 关键参数（占位值，未冻结）

各维度统计阈值、词表、白名单均为**占位值**，尚未经临床审核冻结，逐项待裁问题见 [`docs/reports/clinical-review-freeze-checklist.md`](../../docs/reports/clinical-review-freeze-checklist.md)。本快照只锚定「产物 + 输入」哈希，**不把占位参数视为已冻结**。

- 检查：`min_condition_support=10, max_baseline_share=0.85, min_baseline_share=0.02, min_candidate_support=10, fdr_q=0.10, score_ratio=1.5, min_share_gap=0.10`
- 诊断：`psr_nco_min=5, psr_p_min=0.005, max_baseline_share=0.15, min_candidate_support=20`
- 治疗 / 转诊：`min_share_gap=0.10, min_gold_share=0.0`

## 8. 复现方式

出题与验证为纯 pandas、无随机数、无 LLM；评测为 OpenAI-compatible 接口调用。以检查检验选择为例：

```powershell
.\.venv\Scripts\python.exe .\tasks\investigation_selection\src\split.py            # 患者级划分
.\.venv\Scripts\python.exe .\tasks\investigation_selection\src\run_development.py  # 出题（dev）
.\.venv\Scripts\python.exe .\tasks\investigation_selection\src\run_validation.py   # 验证（val）
.\.venv\Scripts\python.exe .\tasks\investigation_selection\src\build_validated.py  # 筛稳定题
.\.venv\Scripts\python.exe .\tasks\investigation_selection\src\evaluate.py         # DeepSeek 评测
```

其余维度见各任务 README。输入哈希 fail-closed 校验，漂移即停跑。

## 9. 完整性校验

- **产物**：`artifacts/` 下全部 115 个文件与源 `tasks/` 同名文件 SHA-256 逐一比对一致（`mismatch=0`），清单见 `artifacts_sha256.json`。
- **代码**：`src/` 下全部 43 个 `.py` 与源 `benchmark_common/`、`tasks/*/src/` 同名文件 SHA-256 逐一比对一致（`mismatch=0`），清单见 `src_sha256.json`。

## 10. 外部依赖与运行边界

**本快照是「归档 / 溯源」快照，不是可脱离项目独立运行的包。** 运行仍回到项目根目录 `D:\Projects\llm_benchmark`，下列运行环境一律现取、不随快照迁移。

**自包含的（已进快照）**

- 产物 `artifacts/`（115 文件）＋ 代码 `src/`（43 文件），均以 SHA-256 锚定。
- 代码间的内部 `import`（`benchmark_common` 与各任务 `src/`）依赖 `sys.path` 相对层级定位，快照内保持了同构层级，因此**内部引用在快照内自洽**。

**不随快照迁移（运行时从根目录现取）**

| 依赖 | 位置 | 说明 |
|---|---|---|
| Python 运行时 + 第三方包 | 根目录 `.venv`（由 `pyproject.toml` / `uv.lock` 定义，Python 3.12） | 代码直接 import `pandas` / `pyarrow` / `openai` |
| 环境变量 / API 密钥 | 根目录 `.env`（`TEXT_NER_API_KEY` / `TEXT_NER_BASE_URL` / `TEXT_NER_MODEL` / `TEXT_NER_MODEL_VERSION` / `TEXT_NER_PROVIDER`） | `evaluate.py` 读取其中 4 个（不含 `MODEL_VERSION`）；含密钥，不进快照 |
| 输入数据 | G 盘 / D 盘 `data\...` | `normalized_events.parquet`、discharge raw jsonl、`raw_source_records.parquet`（见第 6 节），代码硬编码路径直接指向 |

**结论**：代码中的绝对路径（`D:\Projects\llm_benchmark\...` 与 `G:\Projects\llm_benchmark\...`）说明本快照的运行环境就是该根目录 + 数据盘；在根目录下运行，上述环境、密钥、数据均原地可用，无需迁进快照，也无需重复存储。
