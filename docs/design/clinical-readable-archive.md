# 临床可读 admission 归档

## 目标

`mimic_dictionary.prepare_clinical_readable_archive` 将 admission 级 raw JSONL 转换为可直接供后续评测与临床数据处理使用的可读副本。处理仅增加可确定的官方字典释义和 POE 医嘱时间线，不删除或覆盖原始编码及原始字段。

## 输入与输出

输入必须是逐行 JSONL，每行是一条完整的 `mimic-admission-raw` admission 记录。字典默认从 `data/解析/json/` 读取：

- `d_labitems.json`
- `d_items.json`
- `d_icd_diagnoses.json`
- `d_icd_procedures.json`
- `d_hcpcs.json`

输出仍是一行一个 admission 的 JSONL。各源事件保留原始编码，并增加对应的 `itemid_decoded`、`icd_decoded` 或 `hcpcs_cd_decoded` 对象；`mimic_iv_hosp` 增加 `poe_timeline`。

## 确定性解析范围

| JSON路径 | 主键 | 字典 | 新增字段 |
|---|---|---|---|
| `mimic_iv_hosp.labevents[]` | `itemid` | `d_labitems` | `itemid_decoded` |
| `mimic_iv_hosp.diagnoses_icd[]` | `icd_code + icd_version` | `d_icd_diagnoses` | `icd_decoded` |
| `mimic_iv_ed.diagnosis[]` | `icd_code + icd_version` | `d_icd_diagnoses` | `icd_decoded` |
| `mimic_iv_hosp.procedures_icd[]` | `icd_code + icd_version` | `d_icd_procedures` | `icd_decoded` |
| `mimic_iv_hosp.hcpcsevents[]` | `hcpcs_cd` | `d_hcpcs` | `hcpcs_cd_decoded` |
| ICU `datetimeevents/ingredientevents/inputevents/outputevents/procedureevents[]` | `itemid` | `d_items` | `itemid_decoded` |

ICU 项目还必须满足 `d_items.linksto` 与当前事件表一致。微生物事件已经同时保存 `spec_type_desc`、`test_name`、`org_name` 和 `ab_name`，当前五张字典没有这些编码的独立映射，因此不猜测替换。放射报告同样保留原文，不从 POE 分类猜测检查名称。

POE 时间线使用 `poe + poe_detail + prescriptions + pharmacy`，解析新增、变更、停止、药物剂量和关系链。POE 表只表示医嘱行为，不把医嘱解释为已经执行。

## 命令

```powershell
.\.venv\Scripts\python.exe -m mimic_dictionary.prepare_clinical_readable_archive `
  data\mimic-admission-raw-coronary-all-three-modules-random-100.jsonl `
  --output data\mimic-admission-raw-coronary-all-three-modules-random-100-clinical-readable.jsonl `
  --report data\mimic-admission-raw-coronary-all-three-modules-random-100-clinical-readable.report.json
```

脚本按 admission 流式处理，五张字典只加载一次。输入、输出和报告路径必须互不相同，已有输出不会被覆盖。任何非空编码无法匹配、字典键重复、ICU表归属冲突、POE关联冲突或输入结构错误都会立即失败，并删除未完成的输出，不产生静默降级数据。
