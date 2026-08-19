# mimic_raw_archive：把 MIMIC 原始表聚合为「一次住院一行」的原始 JSONL 归档

本模块是整条 MIMIC-IV 临床数据处理流水线的**第一站**：从本地锁定的 MIMIC 原始 CSV.GZ 表中抽取选定住院（admission），把 32 张可原生连接到 `hadm_id` 的源表按模块聚合，输出每行一条住院、字段与值逐字保留（all-varchar、不做编码释义、不解析 POE 语义）的原始 JSONL 归档，全程分片、可中断续跑、内容指纹绑定。

## 1. 在流水线中的位置

mimic_raw_archive 完成「原始表 → Admission 级原始 JSONL」这一步：它只做**抽取与聚合**，不做任何清洗、解码或事件化——那些是下游模块的职责。

```text
MIMIC-IV 3.1 HOSP（mimic-iv-3.1/hosp/*.csv.gz）
MIMIC-IV 3.1 ICU （mimic-iv-3.1/icu/*.csv.gz）
MIMIC-IV-ED 2.2 （mimic-iv-ed/ed/*.csv.gz）
MIMIC-IV-Note 2.2（mimic-iv-note-2.2/note/*.csv.gz）
        │  39 个锁定文件（32 张归档表 + 7 张字典表），表头逐字校验
        ▼
┌────────────────────────── mimic_raw_archive ──────────────────────────┐
│  selection.jsonl（确定性抽样 / 外部冠心病队列清单）                      │
│        ▼                                                               │
│  staging/<32 表>/  按 _archive_shard_id 分区的 Parquet（ZSTD）          │
│  reference_tables/<7 表>.parquet（整表字典）                            │
│        ▼                                                               │
│  parts/part-NNNNN.jsonl（多进程分片组装，逐条 schema 校验）              │
│        ▼                                                               │
│  <merged>.jsonl —— schema: mimic_admission_raw 1.0.0，一次住院一行      │
└────────────────────────────────────────────────────────────────────────┘
        │
        ▼
clean_clinical_archive（字典解码 + POE 解析）
        ▼
event_pipeline（事件化 + 归一化 Parquet） → event_aggregation（无损聚合） → phenotype（visit 特征空间）
```

旁路工具：`monitor.py` 对运行目录做只读监控；`module_subset.py` 对已生成的 JSONL 按模块覆盖条件流式筛选子集；`field_dictionary.py` 从冻结契约生成可审计字段字典。**不要**把输出先送进 `mimic_episode` 或 `parquet_to_jsonl`（历史路径），直接交给 `data_pipeline.clean_clinical_archive`。

## 2. 目录结构与职责

| 文件 | 职责 | 关键函数 / 类 |
|---|---|---|
| `__init__.py` | 导出公共接口与 schema 标识 | `SCHEMA_NAME`、`SCHEMA_VERSION`、`run`、`RawArchiveConfig` |
| `__main__.py` | 包入口，仅转发到 extractor 的 `main` | `main` |
| `catalog.py` | 锁定 32 张纳入表、7 张字典表、排除表与 5 种连接规则 | `ARCHIVE_SOURCES`、`REFERENCE_SOURCE_KEYS`、`EXCLUDED_SOURCE_REASONS`、`MODULE_TABLES`、`validate_catalog` |
| `config.py` | 路径/采样/分片/并发/DuckDB 资源配置与校验 | `RawArchiveConfig.validate` |
| `extractor.py` | 核心编排：表头校验→选择→manifest→staging→reference→分片→合并；真正的 argparse 也在这里 | `run`、`_create_staging`、`_staging_query`、`_stage_reference_tables`、`_assemble_missing_shards`、`_assemble_shard`、`_merge_shards`、`create_parser`、`main` |
| `manifest.py` | 原子 manifest、SHA-256 内容指纹、规范化哈希 | `canonical_hash`、`file_sha256`、`source_fingerprint`、`read_manifest`、`write_manifest` |
| `schema.py` | 冻结的记录 schema 与逐条 fail-closed 校验 | `TOP_LEVEL_FIELDS`、`empty_record`、`build_record`、`validate_record`、`canonical_row` |
| `selection.py` | 确定性随机抽样（开发集患者池内） | `subject_bucket`、`select_admissions` |
| `cohort.py` | 冠心病谱系住院清单（独立 CLI） | `is_cad_code`、`build_cad_selection`、`main` |
| `module_subset.py` | 三模块（HOSP+ED+Note）非空子集流式提取（独立 CLI，自带监控页） | `classify_record`、`module_has_content`、`extract_subset`、`render_monitor_html` |
| `monitor.py` | 本地只读 HTTP 监控仪表盘（独立 CLI） | `collect_status`、`StatusCache`、`create_handler`、`main` |
| `field_dictionary.py` | 从冻结表头 + 参考文档生成字段字典（库函数，无 CLI） | `build_field_dictionary`、`parse_schema_table`、`information_phase`、`benchmark_restriction`、`validate_dictionary` |

共享契约：`data_pipeline/mimic_source_catalog.py` 提供 `SOURCE_BY_KEY`（每个源的相对路径、锁定表头、版本号），`catalog.py`、`extractor.py`、`cohort.py`、`field_dictionary.py` 统一从这里取源定义，保证全流水线看到同一份表头契约。

## 3. 工作原理深度解析

### 3.1 锁定源契约与表头前置校验

- **目的**：在任何抽取开始前发现「文件缺失 / 版本不对 / 表头漂移」，避免跑到一半才失败或静默产出错位数据。
- **输入**：`config.data_root` 下 39 个 CSV.GZ（相对路径来自 `mimic_source_catalog.SOURCE_BY_KEY`）。
- **处理**：`extractor._validate_source_headers` 对 32 张归档表 + 7 张字典表逐一 `gzip.open` 读取第一行 CSV，与锁定表头元组**逐字比较**（`utf-8-sig` 处理 BOM）；任一缺失或漂移即汇总成 `ValueError("raw source validation failed: ...")` 终止。
- **输出**：通过则继续；否则 fail-closed。
- **代码位置**：`extractor.py: _validate_source_headers`。

### 3.2 源表纳入/排除与连接规则（catalog.py）

- **目的**：只用**源表原生键**把行连到住院，禁止任何按时间窗口「推断归属」的连接。
- **纳入**（`ARCHIVE_SOURCES`，共 32 张）：
  - `mimic_iv_hosp`（16）：`patients`（link=subject）、`admissions`、`transfers`、`services`、`labevents`、`microbiologyevents`、`poe`、`poe_detail`、`pharmacy`、`prescriptions`、`emar`、`emar_detail`、`diagnoses_icd`、`procedures_icd`、`hcpcsevents`、`drgcodes`；
  - `mimic_iv_icu`（6）：`icustays`、`datetimeevents`、`ingredientevents`、`inputevents`、`outputevents`、`procedureevents`；
  - `mimic_iv_ed`（6）：`edstays`（ed_parent）、`triage`、`vitalsign`、`ed_diagnosis`（输出键改名为 `diagnosis`）、`medrecon`、`pyxis`（均为 ed_child）；
  - `mimic_iv_note`（4）：`discharge`、`discharge_detail`、`radiology`、`radiology_detail`。
- **排除**（`EXCLUDED_SOURCE_REASONS`）：`chartevents`——「high-volume ICU bedside monitoring explicitly excluded」（体积与连续监测属性，`validate_catalog` 还会二次断言它绝不允许进入）；`omr`——「no native hadm_id; temporal attribution is forbidden」（无原生住院键，按时间归属是被禁止的）。
- **5 种连接规则**（`extractor._staging_query` 生成 SQL）：

  | link 规则 | 适用表 | SQL 连接方式 |
  |---|---|---|
  | `direct_hadm`（默认） | admissions、transfers、labevents、ICU 6 表、poe/emar/pharmacy/prescriptions、diagnoses_icd 等 | `child JOIN selected_admissions s ON c.subject_id=s.subject_id AND c.hadm_id=s.hadm_id` |
  | `subject` | patients（患者级，无 hadm_id） | `ON c.subject_id=s.subject_id`，该患者行会复制进其每个入选住院 |
  | `ed_parent` | edstays | 直接 `subject_id + hadm_id` 连接 |
  | `ed_child` | triage、vitalsign、ed_diagnosis、medrecon、pyxis | `child JOIN edstays p ON c.subject_id=p.subject_id AND c.stay_id=p.stay_id`，再由 `p.subject_id+p.hadm_id` 连入选清单（ED 子表只有 stay_id） |
  | `parent` | poe_detail(→poe, 匹配 poe_id+poe_seq)、emar_detail(→emar, emar_id+emar_seq)、discharge_detail / radiology_detail(→对应 note 表, note_id) | `child JOIN parent ON c.subject_id=p.subject_id AND <match_fields 逐字段相等>`，再由父表连入选清单 |
- **字典表**（`REFERENCE_SOURCE_KEYS`，7 张，不连住院）：`d_labitems`、`d_icd_diagnoses`、`d_icd_procedures`、`d_hcpcs`、`provider`、`d_items`、`caregiver`，整表落地为 Parquet 供下游解码。
- **一致性自检**：`catalog.validate_catalog` 检查 key 无重复、chartevents 绝不在列、所有 key 存在于共享契约、parent 连接必须带 `parent_key` 与 `match_fields`。
- **代码位置**：`catalog.py: ARCHIVE_SOURCES / validate_catalog`，`extractor.py: _staging_query`。

### 3.3 选择清单：确定性抽样与外部队列

- **目的**：先定「抽哪些住院」，把抽样决策与记录内容完全解耦；同一份原始数据永远得到同一样本，且默认抽样只落在开发集患者池内，防止最终测试集泄漏。
- **输入**：`admissions.csv.gz`，或外部清单（`--selection-input`，如 cohort.py 产物）。
- **处理**（`selection.py`）：
  1. `subject_bucket(subject_id)`：对 `subject_id` 做 SHA-256，取前 8 字节按大端转整数再 `% 100`，得到每名患者稳定的 0–99 桶号；
  2. `select_admissions` 只保留桶号 `< development_percent`（默认 20，即约 20% 患者构成开发池）的住院作为候选——**按患者切分而非按住院切分**，同一患者的所有住院必然同池；候选不足 `sample_size` 时直接报错；
  3. 每个候选打分 `sha256("{subject_id}:{hadm_id}")` 的十六进制串，`heapq.nsmallest` 取最小的 `sample_size` 个——「随机」完全由哈希决定，无需种子、可精确复现；
  4. 按名次枚举得 `selection_rank`（0 起连续）。
- **输出**：`selection.jsonl`（每行 `{subject_id, hadm_id, selection_rank[, cohort, partition], shard_id}`），`shard_id = selection_rank // shard_size`；原子写入（`.tmp` + replace）。
- **外部清单**：`_load_or_create_selection` 允许传入带额外字段（如 `cohort`/`partition`）的清单，但行数必须精确等于 `sample_size`，且 `_validate_selection_rows` 要求三必备键、rank 从 0 连续唯一、`hadm_id` 无重复；额外字段只留在 selection.jsonl，**不会**渗入原始 JSONL（有单测断言）。
- **代码位置**：`selection.py: subject_bucket / select_admissions`，`extractor.py: _load_or_create_selection / _validate_selection_rows`。

### 3.4 运行身份与 manifest：内容指纹绑定

- **目的**：让「这次运行」拥有由**输入内容**决定的唯一身份，任何源文件字节级变化（哪怕大小和 mtime 都不变）都会导致身份漂移而被拒绝续跑。
- **输入**：39 个源 CSV.GZ + 配置 + 选择清单。
- **处理**（`manifest.py` + `extractor._load_or_create_manifest`）：
  1. `file_sha256`：8 MiB 分块流式 SHA-256，大写十六进制；
  2. `source_fingerprint`：每个源文件记录 `{path, size, mtime_ns, sha256, header}`——大小/mtime 只是附带信息，**内容哈希才是身份**（有单测专门验证「同大小同 mtime 的字节篡改」仍会破坏身份）；
  3. `identity` = `{schema_name, schema_version, data_root(解析后 posix 路径), sample_size, shard_size, development_percent, archive_sources(32 key), reference_sources(7 key), selection_sha256(canonical_hash(selection)), source_fingerprints(39 项)}`；
  4. `identity_sha256 = canonical_hash(identity)`：`canonical_hash` 用 `json.dumps(sort_keys=True, separators=(",",":"), ensure_ascii=False)` 规范化后取 SHA-256，键序与空白不影响结果；
  5. 若 `manifest.json` 已存在且 `identity_sha256` 不一致 → `ValueError("manifest identity mismatch; refusing to mix extraction runs")`，**拒绝把不同输入/配置的结果混入同一输出目录**；一致则复用。
- **输出**：`manifest.json`（原子写入），结构 `{identity, identity_sha256, staging{}, reference_tables{}, shards{}, merged}`。
- **代码位置**：`manifest.py: canonical_hash / file_sha256 / source_fingerprint / write_manifest`，`extractor.py: _load_or_create_manifest`。

### 3.5 staging：DuckDB 分区 COPY + 完成标记

- **目的**：把 32 张大表的「入选行」一次性物化为按分片分区的 Parquet，后续组装只读自己的分区，避免反复扫描 CSV.GZ。
- **输入**：源 CSV.GZ + 临时表 `selected_admissions(shard_id, subject_id, hadm_id)`（`_populate_selection` 用 `executemany` 注入）。
- **处理**（`extractor._create_staging`，逐表执行）：
  1. DuckDB 连接按表独立创建（`_connect`）：`threads`、`memory_limit` 来自配置，`temp_directory` 独立在 `output_dir/duckdb_temp/staging-<key>/`，并 `SET preserve_insertion_order=false` 省内存；
  2. `COPY (<_staging_query 生成的 SELECT，附加上 _archive_shard_id/_archive_subject_id/_archive_hadm_id 三列>) TO '<key>.partial' (FORMAT PARQUET, COMPRESSION ZSTD, PARTITION_BY (_archive_shard_id))`——查询用 `read_csv_auto(..., all_varchar=true)` 读源表，**所有列按字符串保留原值**，连接规则见 3.2；
  3. COPY 返回行数必须与实际 Parquet 总行数一致，否则立即失败；
  4. 在 partial 目录内写 `_ARCHIVE_COPY_COMPLETE.json` 完成标记（含 rows 与完整 integrity 报告），再原子 rename 为正式目录 `staging/<key>/`；
  5. integrity 报告由 `_parquet_directory_report` 生成：对目录下每个 `*.parquet` 记录 `{相对路径, bytes, rows, sha256, schema(逐列名/类型/可空)}`（pyarrow 读取，损坏即抛「parquet integrity failure」），再汇总 `{files, file_count, rows, tree_sha256=canonical_hash(逐文件报告)}`；
  6. 每表完成后立刻写 manifest——中断后已完成的表不必重做。
- **输出**：`staging/<source_key>/_archive_shard_id=<n>/*.parquet`（DuckDB 分区目录，无行的分片不产生目录）+ 目录内完成标记。
- **代码位置**：`extractor.py: _create_staging / _staging_query / _connect / _parquet_directory_report`。

### 3.6 reference 字典表整表落地

`_stage_reference_tables` 用单个 DuckDB 连接把 7 张字典表整表 `read_csv_auto(all_varchar=true)` → `COPY` 成 `reference_tables/<key>.parquet`（先 `.partial` 再 rename），逐个记入 manifest（status/单独 sha256/integrity 报告），已完成的复用前同样复算 integrity。这些表没有 hadm_id，不参与住院聚合，是下游 `clean_clinical_archive` 字典解码的输入。

### 3.7 分片组装：多进程并行与记录组装

- **目的**：把每个分片（`shard_size` 条住院，默认 1000）的 32 表分区行组装成 JSONL 行，多进程并行、失败可按分片重做。
- **处理**：
  1. `_assemble_missing_shards` 按 `shard_id` 分组选择行；manifest 中已 `complete` 的分片复用（见 3.9），其余进入 `pending`；
  2. `ProcessPoolExecutor(max_workers=config.workers)` 提交 `_assemble_shard`；`as_completed` 每完成一个分片立即把报告写进 manifest（`{status, records, bytes, sha256, source_rows(各表行数 Counter)}`）；
  3. `_assemble_shard`（子进程内）：为该分片开独立 DuckDB 连接（独立 temp 目录）；对 32 张表依次读 `staging/<key>/_archive_shard_id=<n>/*.parquet`，`SELECT _archive_hadm_id, <全部表头列>`，`fetchmany(10_000)` 流式取批；每行按 `hadm_id` 归入 `admissions[hadm_id]["rows"][source.key]`（`defaultdict(list)`）并计数；某表该分片无分区目录属正常，跳过；
  4. 写文件：按 `selection_rank` 排序遍历分片内住院，`schema.build_record(subject_id, hadm_id, rows)` 组装记录 → `json.dumps(ensure_ascii=False, separators=(",",":"))` 紧凑单行 + `\n`，写入 `parts/part-NNNNN.jsonl.partial` 后原子 rename；
  5. 返回报告（含 `file_sha256(part)`）。
- **输出**：`parts/part-00000.jsonl …`，每个分片恰好 `shard_size` 条（末片除外）。
- **代码位置**：`extractor.py: _assemble_missing_shards / _assemble_shard`。

### 3.8 记录组装与逐条 schema 校验（schema.py）

- **目的**：冻结「一次住院一行」的 observable 契约，任何结构漂移在写盘前就地失败（fail-closed），绝不静默产出畸形记录。
- **结构**：顶层键**顺序敏感**，固定为 `TOP_LEVEL_FIELDS = (schema, subject_id, hadm_id, mimic_iv_hosp, mimic_iv_icu, mimic_iv_ed, mimic_iv_note)`；`schema` 恒为 `{"name": "mimic_admission_raw", "version": "1.0.0"}`；每个模块容器内表键及顺序由 `catalog.MODULE_TABLES` 决定（hosp 16、icu 6、ed 6、note 4，其中 `ed_diagnosis` 输出键为 `diagnosis`）。
- **build_record**：先 `empty_record` 建全空骨架，再填入各表行；**每张表的行先按 `canonical_row`（紧凑 JSON 序列化文本）排序**——与 DuckDB `preserve_insertion_order=false` 配合，保证无论上游以何种顺序产出，同一输入永远得到字节级确定的 JSONL；最后 `validate_record`。
- **validate_record 的 fail-closed 检查**（全部抛 `RawArchiveValidationError`）：
  1. `tuple(record) != TOP_LEVEL_FIELDS` → 「top-level schema drift」（键集合或顺序漂移都算）；
  2. `record["schema"]` 不精确等于 `{name, version}` → 「schema identity mismatch」；
  3. `subject_id`/`hadm_id` 为空 → 拒绝；
  4. 任一模块不是 dict、或表键元组与目录不符 → 「table schema drift」；
  5. 任一表不是 list → 拒绝；
  6. 任一行不是 dict、或 `tuple(row) != 源表头` → 「raw field drift」（**多一个派生字段、少一个字段、换顺序都会被拒**，从根上杜绝下游出现 `clinical_end_time` 这类派生字段混入）；
  7. 行内 `subject_id`/`hadm_id`（若该表含此列）与顶层冲突 → 「subject/admission conflict」；
  8. `mimic_iv_hosp.admissions` 必须恰好 1 行 → 保证「一次住院一行」语义；
  9. `mimic_iv_icu` 内出现 `chartevents` → 禁止。
- **代码位置**：`schema.py: TOP_LEVEL_FIELDS / empty_record / build_record / validate_record / canonical_row`。

### 3.9 断点续跑判定（恢复矩阵）

恢复逻辑完全由 manifest 状态 + 磁盘现场 + 可复算指纹三者对账决定：

**运行级**：
- manifest 存在且 `identity_sha256` 一致 → 允许续跑；不一致 → 拒绝（防混跑）；
- `selection.jsonl` 存在但行数 ≠ `sample_size` → 拒绝；rank 不连续 / hadm_id 重复 → 拒绝。

**staging（每张表独立判定，`_create_staging`）**：

| 现场状态 | 判定 |
|---|---|
| manifest 记 complete + 目录在 + integrity 复算一致 | 复用跳过 |
| manifest 记 complete + 目录缺失 | `FileNotFoundError` 拒绝（不允许凭空标记） |
| manifest 记 complete + integrity 漂移 | `integrity failure` 拒绝重建 |
| 正式目录在但 manifest 无记录（如 rename 后断电） | 必须存在目录内 `_ARCHIVE_COPY_COMPLETE.json`：无 → 「staging integrity metadata missing for recovered directory」拒绝；有且一致 → 补记 manifest，标 `recovered_after_rename` |
| `<key>.partial` 目录 + 完成标记在 | 复算一致后 rename 转正，标 `recovered_from_completion_marker` |
| `<key>.partial` 无标记 | 视为垃圾安全删除后重做（`_remove_partial_directory` 校验目标父目录必须是 staging 根且名字以 `.partial` 结尾，防误删） |
| COPY 行数 ≠ Parquet 实际行数 | 立即失败 |

**reference 表**：同上——complete 必须文件在且 integrity 一致，否则拒绝；未记录则重做。

**分片**：manifest 记 complete 的分片要求 `parts/part-NNNNN.jsonl` 存在且 `file_sha256` 与记录一致，否则 `completed shard integrity failure` **硬失败**（不静默重算）；未标记 complete 的分片才进入重做队列。

**合并**：`_merge_shards` 先断言「全部 complete 分片记录数之和 == sample_size」，不等则拒绝合并；随后按分片号顺序以 8 MiB 块拼接 → `.partial` → 原子 rename 到 `merged_path`，把 `{status, records, bytes, sha256, path}` 写入 `manifest["merged"]` 并落盘。注意：对已完整完成的运行重新执行会**重新生成**合并文件（内容确定一致），而非校验后跳过。

### 3.10 冠心病队列清单（cohort.py，独立 CLI）

- **筛选规则**：`build_cad_selection` 用 DuckDB 对 `diagnoses_icd.csv.gz` 执行 `SELECT DISTINCT subject_id, hadm_id WHERE ((icd_version='9' AND substr(icd_code,1,3) BETWEEN '410' AND '414') OR (icd_version='10' AND substr(icd_code,1,3) BETWEEN 'I20' AND 'I25'))`，且两个 ID 非空——即 ICD-9 410–414 / ICD-10 I20–I25 的冠心病谱系（`CAD_CRITERIA` 常量同义；Python 侧 `is_cad_code` 是去点、大写化后的同规则镜像，供程序化复用）。**只按诊断编码筛，不按医嘱/用药**。
- **排序与分区**：结果按 `sha256("{subject}:{hadm}")` 摘要排序（与 selection.py 同一确定性机制）得到 `selection_rank`；`partition = development`（当 `subject_bucket(subject_id) < development_percent`）`否则 final_test`——即 `--development-percent`（默认 20，1–99）决定**按患者哈希桶**划给开发集的患者比例，其余患者标为最终测试集。
- **输出**：JSONL 每行 `{subject_id, hadm_id, selection_rank, cohort: "coronary_disease_spectrum", partition}`，`.tmp` 原子替换；stdout 打印摘要（标准数、患者数、开发患者数、两分区住院数）。注意该清单**同时包含两个分区**的住院，交给 `--selection-input` 时归档本身不区分用途，分区标签只保存在清单里。
- **代码位置**：`cohort.py: is_cad_code / build_cad_selection / main`。

### 3.11 三模块子集提取（module_subset.py，独立 CLI）

- **目的**：从既有原始 JSONL 中筛出 HOSP、ED、Note 三模块**都有内容**的住院（典型用途：构造多模态子集），ICU 只统计、不作为条件。
- **规则**：`module_has_content` = 模块内**至少一张表的数组非空**；模块不是 dict、表不是数组、缺 subject_id/hadm_id 均抛 `ModuleSubsetError`（fail-closed，不猜测）。
- **流式处理**（`extract_subset`）：逐行读原始字节 → `json.loads` + `classify_record`（任何 JSON/Unicode/结构错误立即置 failed 状态并抛出，含行号与字节偏移，**不跳过坏行**）→ 统计四模块覆盖、两两/三模块交集、非空表计数、字节数/速度/ETA → 命中行**逐字节原样保留**（仅确保尾部换行）写入 `.partial`，`flush + fsync` 后 `os.replace` 转正；输入输出双 SHA-256 边读边算。
- **防覆盖**：`--output/--summary/--monitor-html/--status-json` 四个目标及对应 `.partial` 任一已存在即 `FileExistsError` 拒绝；输入路径 == 输出路径也拒绝。
- **监控产物**：status.json（原子写）+ 自带 HTML 监控页（运行中每 2 秒 meta refresh 自刷新，完成后停）；`--max-records` 可限量试跑（summary 里 `limited_run` 标记）。
- **代码位置**：`module_subset.py: REQUIRED_MODULES / classify_record / extract_subset / render_monitor_html`。

### 3.12 只读监控仪表盘（monitor.py，独立 CLI）

- **目的**：不读取任何患者记录内容，仅凭 manifest + 文件元数据展示运行进度。
- **实现**：`ThreadingHTTPServer`（默认 `127.0.0.1:8765`）提供 `/`（HTML，每 5 秒 fetch `/api/status`）与 `/api/status`；`collect_status` 读 manifest 的 staging/shards/merged 状态、`selection.jsonl` 的 ctime 作为起点、各 staging 目录的字节数与最近写入时间、目标盘 `shutil.disk_usage`、物理内存（`ctypes.windll.kernel32.GlobalMemoryStatusEx`，**Windows 专用**）；分片总数由 `identity` 里 `sample_size/shard_size` 上取整推得。
- **状态判定**：merged complete 且文件在 → `complete`；manifest/工作目录/可选外部活动文件（`--activity-file`）任一 mtime 距今 ≤180 秒 → `running`（阶段=staging 未齐则「源表 staging」否则「分片组装/合并」）；有 manifest 但无近期写入 → `stopped`；无 manifest → 尚未启动。单张大表处理期间只显示「处理中」，不伪造表内百分比。
- **性能**：`StatusCache` 30 秒 TTL + 后台线程非阻塞刷新 + 锁合并并发读，避免仪表盘反复全树扫描拖垮磁盘。
- **EDA 卡片**：可选 `--eda-metrics docs/reports/mimic-raw-10000-eda-metrics.json` 展示唯一患者数、冠心病谱住院数、平均行字节、schema 违规与孤立子行数。
- **代码位置**：`monitor.py: collect_status / StatusCache / create_handler / main`。

### 3.13 可审计字段字典（field_dictionary.py，库函数）

- **目的**：把冻结契约变成「每个字段一行」的审计材料：它是什么键、什么时间语义、属于哪个信息阶段、对下游基准题有什么泄漏限制。
- **输入**：`docs/reference/mimic_reference/<hosp|icu|ed|note>/<表>.md`（ED 的 `ed_diagnosis` 对应 `diagnosis.md`）中的 markdown 表（列：`字段`/类型/约束/中文说明）。
- **处理**（`build_field_dictionary`）：
  1. 先产出 7 个顶层字段行（`TOP_LEVEL_DEFINITIONS`）；
  2. 对 32 张归档表：`parse_schema_table` 解析参考文档，**参考字段集必须与锁定表头完全一致**（missing/extra 任一非空即 `FieldDictionaryError`，fail-closed），随后逐字段生成行：`json_path = <module>.<table>[].<field>`、`archive_type`（参考约束含 NOT NULL → `string`，否则 `string | null`）、`key_role`（患者/住院/stay 连接键、源记录标识、非键）、`time_semantics`（event time / recorded-available time / 待确认）、`information_phase`（`information_phase()`：post_hoc 表如 diagnoses_icd/diagnosis/procedures_icd/hcpcsevents/drgcodes/discharge(_detail)；`patients` 除 dod 外=baseline；`edstays` 的 outtime/disposition=clinical_end；dischtime/deathtime 等=administrative_end；标识列=identifier；其余=source_event）、`benchmark_restriction`（`benchmark_restriction()`：post_hoc/administrative_end 禁止进入前瞻性题干等泄漏规则）；
  3. 对 7 张字典表同样处理（scope=external_reference，json_path 前缀 `references.`）。
- **输出**：行列表（单测口径：archive 380 字段 / 32 表 + 7 顶层 + 7 字典表）；`validate_dictionary` 校验 json_path 无重复、中文说明非空、archive 路径集合与契约期望**恰好相等**。成品由 `eda/analysis/build_raw_field_dictionary.py: build_outputs` 渲染为 markdown + JSON。
- **代码位置**：`field_dictionary.py: build_field_dictionary / parse_schema_table / information_phase / benchmark_restriction / validate_dictionary`。

## 4. 数据契约

**输入目录约定**（`--data-root` 下，路径与表头由 `mimic_source_catalog.py` 锁定，版本 MIMIC-IV 3.1 / ED 2.2 / Note 2.2）：

```text
<data_root>/mimic-iv-3.1/hosp/{patients,admissions,transfers,services,labevents,
  d_labitems,microbiologyevents,omr,poe,poe_detail,pharmacy,prescriptions,emar,
  emar_detail,diagnoses_icd,d_icd_diagnoses,procedures_icd,d_icd_procedures,
  hcpcsevents,d_hcpcs,drgcodes,provider}.csv.gz
<data_root>/mimic-iv-3.1/icu/{icustays,chartevents,datetimeevents,ingredientevents,
  inputevents,outputevents,procedureevents,d_items,caregiver}.csv.gz
<data_root>/mimic-iv-ed/ed/{edstays,triage,vitalsign,diagnosis,medrecon,pyxis}.csv.gz
<data_root>/mimic-iv-note-2.2/note/{discharge,discharge_detail,radiology,radiology_detail}.csv.gz
```

（`omr`/`chartevents` 虽在共享契约中，但被本模块排除；39 个被指纹的文件 = 32 归档表 + 7 字典表。）

**输出目录布局**：

```text
<output_dir>/
├── selection.jsonl                     # 抽样清单（含 shard_id）
├── manifest.json                       # 运行身份 + 各阶段状态与完整性
├── staging/<32 表 key>/
│   ├── _archive_shard_id=<n>/*.parquet # ZSTD，按分片分区
│   └── _ARCHIVE_COPY_COMPLETE.json     # 该表完成标记（rows + integrity）
├── reference_tables/<7 表 key>.parquet # 整表字典
├── parts/part-NNNNN.jsonl              # 每分片一个文件，原子落盘
└── duckdb_temp/<任务名>/               # DuckDB 临时溢写目录
<merged_path>                           # 最终 JSONL（.partial 原子替换生成）
```

**输出 JSONL schema**（`mimic_admission_raw 1.0.0`，一行 = 一次住院，紧凑 JSON、UTF-8、`\n` 分行，按 `selection_rank` 全局有序）：

```json
{
  "schema": {"name": "mimic_admission_raw", "version": "1.0.0"},
  "subject_id": "1",
  "hadm_id": "10",
  "mimic_iv_hosp": {"patients": [], "admissions": [], "transfers": [], "services": [],
    "labevents": [], "microbiologyevents": [], "poe": [], "poe_detail": [],
    "pharmacy": [], "prescriptions": [], "emar": [], "emar_detail": [],
    "diagnoses_icd": [], "procedures_icd": [], "hcpcsevents": [], "drgcodes": []},
  "mimic_iv_icu":  {"icustays": [], "datetimeevents": [], "ingredientevents": [],
    "inputevents": [], "outputevents": [], "procedureevents": []},
  "mimic_iv_ed":   {"edstays": [], "triage": [], "vitalsign": [], "diagnosis": [],
    "medrecon": [], "pyxis": []},
  "mimic_iv_note": {"discharge": [], "discharge_detail": [], "radiology": [],
    "radiology_detail": []}
}
```

要点：顶层键顺序固定；`admissions` 恰好 1 行；每张表数组内的行 dict 键序 = 源 CSV 表头、全部为字符串原值；空表保留为 `[]`（结构永不缺省）；`chartevents` 永不出现。

**manifest.json 内容**：`identity`（见 3.4，含 39 项源指纹与 `selection_sha256`）、`identity_sha256`、`staging`（每表 `{status, rows, integrity, [恢复标记]}`）、`reference_tables`（每表 `{status, sha256, integrity}`）、`shards`（每分片 `{status, records, bytes, sha256, source_rows}`）、`merged`（`{status, records, bytes, sha256, path}` 或 null）。

## 5. 正确性与可靠性保障

**fail-closed 条件清单**（任一触发即终止，不降级、不跳过、不静默修复）：

1. 配置非法：`sample_size/shard_size/workers/duckdb_threads ≤ 0`、`duckdb_memory_limit` 不匹配 `[1-9][0-9]*(MB|GB)`、`development_percent` 不在 1–99、`selection_input` 文件不存在（`config.RawArchiveConfig.validate`）；
2. 目录自检失败：key 重复 / 出现 chartevents / 未知源 / parent 连接缺参（`catalog.validate_catalog`）；
3. 任一源文件缺失或表头漂移（`extractor._validate_source_headers`）；
4. manifest 身份不一致（`_load_or_create_manifest`，拒绝混跑）；
5. selection 行数不符 / rank 不连续 / hadm_id 重复（`_validate_selection_rows`）；
6. staging 或 reference 复算 integrity 漂移、或缺少完整性证据（`_verify_integrity`：「integrity metadata missing; rebuild required」/「integrity failure」）；
7. Parquet 物理损坏（`_parquet_file_report` 包装 pyarrow 异常）；
8. COPY 行数 ≠ Parquet 行数（`_create_staging`）；
9. 已完成分片 part 缺失或哈希不符（`_assemble_missing_shards`，硬失败不重算）；
10. 合并前分片记录总数 ≠ `sample_size`（`_merge_shards`）；
11. 记录级 schema 漂移（`schema.validate_record` 全部 9 类检查，写入前逐条执行）；
12. module_subset：坏行（含行号与字节偏移）立即失败；四个输出目标任一已存在即拒绝覆盖。

**防覆盖 / 防误删策略**：

- 所有产物一律「临时名 + 原子 rename」：manifest `.tmp`、selection `.tmp`、staging `<key>.partial` 目录、reference `.parquet.partial`、分片 `.jsonl.partial`、合并 `.partial`、module_subset 全部产物（`os.replace` + `fsync`）；
- staging 只有在 COPY 成功、行数对账、写入完成标记**之后**才 rename 转正——任何时点断电，现场要么是可验证的完整目录、要么是可安全识别/删除的 `.partial`；
- `_remove_partial_directory` 删除前校验「父目录必须是 staging 根 且 名字以 `.partial` 结尾」，杜绝路径注入式误删；
- 同一输出目录重跑：身份一致则全链复用；身份不同则拒绝——新配置请换新目录。

**哈希完整性链**（每层都可独立复算）：

```text
39 个源 CSV.GZ 的 file_sha256（内容级，8MiB 分块）
  └─► identity_sha256 = canonical_hash(identity)          # 运行身份
        └─► staging 每文件 sha256 → tree_sha256            # 目录级指纹
              └─► 分片 part-NNNNN.jsonl 的 sha256           # 逐分片指纹
                    └─► merged JSONL 的 sha256              # 最终产物指纹
```

`canonical_hash` 对 JSON 做键排序 + 紧凑编码后再哈希，保证「同一逻辑内容只有一种哈希」；单测覆盖：同大小同 mtime 的字节篡改破坏身份、追加篡改 staging/reference Parquet 触发 integrity failure、续跑复用已完成分片且哈希不变。

## 6. 使用方法

主入口（`__main__.py` 只转发；argparse 真正定义在 `extractor.create_parser`）：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.mimic_raw_archive `
  --data-root data\RawData `
  --output-dir data\raw_archive\shards `
  --merged-output data\mimic-admission-raw.jsonl `
  --sample-size 10000 `
  --shard-size 1000 `
  --workers 2 `
  --duckdb-threads 4 `
  --duckdb-memory-limit 12GB
```

参数表（默认值取自 `extractor.create_parser` / `config.RawArchiveConfig`）：

| 参数 | 默认 | 说明 |
|---|---|---|
| `--data-root` | `D:/Projects/llm_benchmark/data/RawData` | MIMIC 原始表根目录（布局见第 4 节） |
| `--output-dir` | `G:/Projects/llm_benchmark/data/validation/mimic-admission-raw-10000` | 工作目录（selection/manifest/staging/parts） |
| `--merged-output` | `.../mimic-admission-raw-10000.jsonl` | 最终合并 JSONL 路径 |
| `--sample-size` | 无 → 有 `--selection-input` 时取其非空行数，否则 10,000 | 抽取住院数；与已存在 selection/manifest 身份绑定 |
| `--selection-input` | 无 | 外部住院清单 JSONL（需 `subject_id/hadm_id/selection_rank`，rank 从 0 连续，hadm_id 唯一，行数=sample_size） |
| `--shard-size` | `1000` | 每分片住院数 |
| `--workers` | `2` | 分片组装进程数 |
| `--duckdb-threads` | `4` | 每个 DuckDB 连接线程数 |
| `--duckdb-memory-limit` | `12GB` | DuckDB 内存上限，格式 `512MB`/`4GB` 等，非法即失败 |

注意：`development_percent`（默认 20）只在 `RawArchiveConfig`（编程接口）与 cohort CLI 中可调，主 CLI 不暴露；它同时是随机抽样的患者池比例与 manifest 身份的一部分。

先生成冠心病谱系清单再归档（清单含 development/final_test 两分区，全部进入归档）：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.mimic_raw_archive.cohort `
  --data-root data\RawData `
  --output data\coronary-admission-selection.jsonl `
  --development-percent 20

.\.venv\Scripts\python.exe -m data_pipeline.mimic_raw_archive `
  --data-root data\RawData `
  --output-dir data\raw_archive_coronary\shards `
  --merged-output data\coronary-raw.jsonl `
  --selection-input data\coronary-admission-selection.jsonl `
  --shard-size 1000 --workers 2 --duckdb-threads 4 --duckdb-memory-limit 12GB
```

三模块子集提取（输出默认为 `<输入名>-all-three-modules*` 系列）：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.mimic_raw_archive.module_subset `
  --input data\mimic-admission-raw.jsonl `
  --refresh-seconds 1.0
```

（可选 `--output/--summary/--monitor-html/--status-json` 覆盖默认路径，`--max-records N` 限量试跑；已存在的目标会拒绝覆盖。）

只读监控（另开终端，运行中即可启动）：

```powershell
.\.venv\Scripts\python.exe -m data_pipeline.mimic_raw_archive.monitor `
  --output-dir data\raw_archive\shards `
  --merged-output data\mimic-admission-raw.jsonl `
  --host 127.0.0.1 --port 8765 --open-browser
```

（可选 `--eda-metrics docs/reports/mimic-raw-10000-eda-metrics.json`、`--activity-file <外部活动文件>` 用于长表处理期间的活跃判定。）

单元测试（相关测试均在 `tests/` 下，已确认存在）：

```powershell
.\.venv\Scripts\python.exe -m unittest -v `
  tests.test_raw_admission_archive `
  tests.test_raw_archive_monitor `
  tests.test_module_subset `
  tests.test_raw_field_dictionary
```

（另有 `tests.test_raw_archive_eda`、`tests.test_raw_coronary_eda_html` 覆盖 EDA 产物；`test_raw_admission_archive` 内含端到端抽取、断点续跑、身份防篡改、Parquet 防篡改与外部清单五个场景。）

## 7. 设计取舍与已知限制

- **原生键连接 only**：`omr` 无 `hadm_id`、任何需要按时间窗推断归属的连接都被明确禁止；代价是放弃 omr 这类只能按 subject+时间挂靠的数据。
- **chartevents 永久排除**：体积与连续监测属性使其不适合进入 admission 级原始归档（`validate_catalog` 二次断言）；ICU 生理波形类信息只能来自其余 6 张 ICU 表。
- **全字符串（all_varchar）落档**：不猜类型、不丢 `NULL`/前后缀细节，类型解释权完全交给下游 `clean_clinical_archive`；代价是归档体积更大、下游必须自行转型。
- **确定性优先于「真随机」**：抽样与排序全部由 SHA-256 派生（无随机种子概念），同输入必得同输出；配合 `canonical_row` 行排序与 `preserve_insertion_order=false`，分片与合并文件字节级可复现。
- **按患者切分开发/测试**：`subject_bucket` 保证同一患者所有住院同池，杜绝同一患者横跨开发与最终测试造成的标签泄漏；随机抽样默认只从开发池取数，冠心病清单则显式带分区标签。
- **续跑粒度**：staging 以「表」为恢复单位、组装以「分片」为恢复单位；单张大表 COPY 中断只能整表重做（无表内断点）。已完成分片损坏时选择硬失败而非重算，是为了把「磁盘静默腐坏」暴露给人看。
- **合并文件每次重跑都会重建**：身份一致的重跑会重新拼接 merged JSONL（内容确定一致），而不是校验既有文件后跳过；如需保留旧文件请先归档。
- **`shard_size` 与 `sample_size` 绑进身份**：改任一参数都会导致 manifest 身份不一致，需换新输出目录——这是防混跑的代价。
- **平台限制**：`monitor.py` 的内存读取依赖 Windows `GlobalMemoryStatusEx`（ctypes），非 Windows 平台该函数会失败（其余功能正常）；EDA 卡片依赖外部 metrics JSON，缺省时显示「尚未生成」。
- **主 CLI 面较窄**：`development_percent` 未暴露给主 CLI；module_subset / monitor / cohort 是独立子入口，统一聚合在本包下。
