# 字典解码规则

## 目标

解码只增加官方字典原行，不替换或删除源编码。每个新增对象均包含 `source_dictionary` 和该字典匹配行的全部字段，便于复核来源。

## 所需字典

默认从清洗包自身的 `dictionaries/` 读取以下标准 JSON 数组：

- `d_labitems.json`
- `d_items.json`
- `d_icd_diagnoses.json`
- `d_icd_procedures.json`
- `d_hcpcs.json`

这些字典 JSON 已作为本地授权资源纳入便携目录。每张表的键必须完整且唯一；文件缺失、根节点不是数组、行不是对象、键为空或键重复都会立即失败。`bundle-manifest.json` 固定记录文件名、行数、大小和 SHA-256，可通过 `python -m clean_clinical_archive.verify_bundle` 自检。

## 固定映射

| 源 JSON 路径 | 源键 | 字典及字典键 | 新增字段 |
|---|---|---|---|
| `mimic_iv_hosp.labevents[]` | `itemid` | `d_labitems(itemid)` | `itemid_decoded` |
| `mimic_iv_hosp.diagnoses_icd[]` | `icd_code + icd_version` | `d_icd_diagnoses(icd_code, icd_version)` | `icd_decoded` |
| `mimic_iv_ed.diagnosis[]` | `icd_code + icd_version` | `d_icd_diagnoses(icd_code, icd_version)` | `icd_decoded` |
| `mimic_iv_hosp.procedures_icd[]` | `icd_code + icd_version` | `d_icd_procedures(icd_code, icd_version)` | `icd_decoded` |
| `mimic_iv_hosp.hcpcsevents[]` | `hcpcs_cd` | `d_hcpcs(code)` | `hcpcs_cd_decoded` |
| `mimic_iv_icu.datetimeevents[]` | `itemid` | `d_items(itemid)` | `itemid_decoded` |
| `mimic_iv_icu.ingredientevents[]` | `itemid` | `d_items(itemid)` | `itemid_decoded` |
| `mimic_iv_icu.inputevents[]` | `itemid` | `d_items(itemid)` | `itemid_decoded` |
| `mimic_iv_icu.outputevents[]` | `itemid` | `d_items(itemid)` | `itemid_decoded` |
| `mimic_iv_icu.procedureevents[]` | `itemid` | `d_items(itemid)` | `itemid_decoded` |

`chartevents` 不在当前 raw archive 契约内，因此不纳入。微生物表已经保存可读描述字段，且这五张字典没有其独立可靠映射；放射内容也不从 POE 类别猜测检查名称。

## 键和失败规则

所有键分量会先转为字符串并去除首尾空白：

- 单键为空，或组合键全部为空：不解码，计入 `null_keys_by_path`；
- 组合键仅部分为空，例如存在 `icd_code` 但缺少 `icd_version`：立即失败；
- 非空完整键无法匹配：立即失败，并报告 admission 序号、路径、行号、键和值；
- 目标行已有同名 `*_decoded` 字段：立即失败，防止重复加工；
- ICU `itemid` 除了必须匹配 `d_items`，其 `linksto` 必须与当前事件表名完全相同。

这些规则的含义是：只输出可由官方字典确定的内容，绝不把缺失版本、跨表 ID 或模糊项目解释成临床概念。

## 共享实现

规则和实现的唯一来源是 `data_pipeline.clean_clinical_archive.decoder`。统一清洗入口和 `data_pipeline.mimic_dictionary.decode_archive` 都调用这一内核，因此修正规则时不需要维护两份逻辑。
