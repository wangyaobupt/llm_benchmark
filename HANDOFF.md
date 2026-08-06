# RWD Clinical Benchmark — Agent Handoff

> 生成时间：2026-08-06 ｜ 目标读者：接手本项目的下一位 Agent

## 0. 项目位置与环境（已变更）

项目已从 `G:\Projects\llm_benchmark` **迁移至** `D:\Projects\llm_benchmark`。

| 项 | 路径 / 值 | 说明 |
|---|---|---|
| 项目根 | `D:\Projects\llm_benchmark` | WDAC 放行 D 盘，python.exe 可执行 |
| Git 仓库 | `.git/`（已从 G 盘拷回，历史完整） | HEAD = `7ec7e98`，2 个 commit |
| Python venv | `D:\Projects\llm_benchmark\.venv` | CPython 3.14.2，uv 管理 |
| uv cache | `D:\Projects\llm_benchmark\.uv-cache` | 同盘，避免跨盘拷贝 |
| 已装依赖 | pandas 3.0.5, matplotlib 3.11.1, numpy 2.5.1 | uv pip install |
| 运行命令 | `.venv\Scripts\python.exe <script>` | 无需提权 |

**环境硬约束（必读）**：
- 本机 WDAC 应用控制策略**拦截 G 盘和 C:\Users 下新创建的 python.exe 执行**（WinError 4551），仅 D 盘放行。
- uv 默认 cache 路径 `C:\Users\Fan\AppData\Local\uv\cache` 存在同名文件冲突，必须设 `$env:UV_CACHE_DIR` 指向 D 盘。
- uv managed Python（符号链接）在 D 盘创建失败（os error 1）；必须用系统 Python `C:\Python314\python.exe` 作为 `--python` 参数。
- G 盘旧目录 `G:\Projects\llm_benchmark` 仅剩 `.git`，用户确认后可删。

## 1. 项目背景（不重复，引用）

完整项目背景、数据契约、流水线设计、文件清单、已知问题与风险见：

- **`项目接手文档.md`** — 项目一句话定位、五类题型、四阶段流水线、17 列字段映射表、技术约定
- **`Hong Kong RWD Clinical Benchmark Question Types.md`** — 题型 2–5 规范
- **`rwd_benchmark_extraction_spec.md`** / `cleaning_spec.md` / `standardization_spec.md` / `mcq_generation_design.md` — 各阶段设计文档

## 2. 四阶段流水线现状

| 阶段 | 状态 | 关键信息 |
|---|---|---|
| [1] 抽取 extraction | ✅ 完成 | 产物 `data/rwd_benchmark_visits.csv`（254 MB, 11687 行 × 17 列） |
| [2] 清洗 cleaning | ✅ 完成 | 产物 `data/rwd_benchmark_visits_cleaned.csv`（235 MB），4 个文本字段已抽 JSON |
| [3] 标准化 standardization | ❌ **代码缺口** | `rwd_standardization/` 模块不存在，`standardize_rwd_benchmark.py` 已就绪但 ImportError；spec + `tests/test_standardization.py` 契约完备 |
| [4] MCQ 生成 | ❌ **仅设计** | 题型 1 有 Stage 0–10 设计文档；题型 2–5 仅题型规范 |

## 3. 本次会话完成的工作

1. **`git init` + 初始基线**（commit `2b61fc4`）— 76 文件，含 .gitignore（排除 `*.csv`/`*.pdf`/`.venv`/`out/`）
2. **D 盘 venv 搭建** — 绕过 WDAC 约束，pandas + matplotlib 就绪
3. **EDA 数据画像**（commit `7ec7e98`）— 7 维度分析 + 7 张图 + 关键发现
   - 脚本：`eda/profile_rwd.py`（可复跑）
   - 报告：`eda/EDA_REPORT.md`
   - 图表：`eda/figures/01–07_*.png`
4. **项目迁移 G→D** — .git 拷回，venv 无需改动

## 4. EDA 关键发现（详见 `eda/EDA_REPORT.md`）

| 级别 | 发现 | 下一步建议 |
|---|---|---|
| **P0** | `discharge_record` 在 raw 和 cleaned 中**均 100% 空** | 排查 `rwd_extraction/discharge.py` 的 DS Follow-up Instructions 章节解析；题型 5 完全无数据来源 |
| **P1** | `investigation_orders.poe_detail` 99.99% 空 | 医嘱仅存分类标签（如 "Lab"），无具体检查项；题型 1 须依赖 `investigation_reports`（97.1% 有数据，人均 45.7 项） |
| **P1** | 157 条就诊 `chief_complaint` 为空 | 数据契约规定主诉缺失应排除 Visit，但清洗产物仍保留——需确认是清洗引入还是抽取遗漏 |
| **P2** | `procedures` 缺失率 41% | 影响题型 3 操作类题目样本量 |
| **P2** | ICD-9 (63%) / ICD-10 (37%) 混用 | 标准化需处理版本差异 |
| **P3** | 1 位患者最多 51 次就诊 | 数据泄漏风险，按 subject_id 划分 train/test |

## 5. 数据画像核心数字速查

- **11,687 次就诊**，**5,328 位患者**，人均 2.19 次就诊
- 年龄中位 63 岁（IQR 50–75），男女 51.5% / 48.5%
- **2,891 种**独立主诊断；Top 1 急性肾损伤（160 例）
- 检查报告：94.7% 有化验（均值 43.3 项），80.1% 有放射（均值 2.4 项）
- 处方：99.8% 就诊有数据，人均 21.3 条
- 数据质量：13 个非清洗列 raw↔cleaned 完全一致，无重复 hadm_id，0 条 JSON 解析失败

## 6. 下一步（按优先级）

1. **排查 P0**：深入 `rwd_extraction/discharge.py`，定位 Follow-up Instructions 章节为何未提取——这是题型 5 的唯一阻塞
2. **实现 `rwd_standardization/`**：spec + 测试已就绪，实现后跑通标准化产物
3. **P1 追查**：157 条空 `chief_complaint` 的来源（raw 是否也空？还是清洗引入？）
4. **凭据治理**：`run_*.sh` 中 `DEEPSEEK_API_KEY` 明文硬编码 → 改环境变量
5. **MCQ 题型 1 实现**：标准化就绪后按 Stage 0–10 编码

## 7. Suggested Skills

接手 Agent 应优先调用以下 skills：

- **`handoff`** — 如需再次交接，用此 skill 生成新 handoff 文档
- **`code-review`** — 审查 `rwd_extraction/discharge.py` 定位 P0 问题根因
- **`arxiv`** / **`nature-academic-search`** — 若需检索 RWD / clinical benchmark 相关文献
- **`nature-reader`** — 参考论文 `data/Li 等 - 2020.pdf` 的深度阅读
- **`medical-content-publisher`** — 若涉及临床内容输出

## 8. 敏感信息

- `run_*.sh` 含明文 `DEEPSEEK_API_KEY`——本文档不记录其值
- venv 和 uv cache 路径不含凭据
