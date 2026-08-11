# 临床可读归档 schema 契约

## 输入

输入是 UTF-8 admission 级 JSONL，一行一条记录。顶层字段及顺序必须为：

```text
schema, subject_id, hadm_id,
mimic_iv_hosp, mimic_iv_icu, mimic_iv_ed, mimic_iv_note
```

`schema` 必须严格等于：

```json
{"name": "mimic_admission_raw", "version": "1.0.0"}
```

`subject_id`、`hadm_id` 必须非空，四个 MIMIC 模块必须是对象。该校验防止把旧格式或已经加工过的数据再次作为 raw 数据清洗。

## 输出

输出仍为一行一个 admission，但 schema 改为：

```json
{"name": "mimic_admission_clinical_readable", "version": "1.0.0"}
```

同时新增顶层 `source_schema`，值为原始 raw schema。字典释义新增在对应源行的 `itemid_decoded`、`icd_decoded` 或 `hcpcs_cd_decoded`；POE 结果新增在 `mimic_iv_hosp.poe_timeline`。

输出 schema 与 raw schema 分开，是为了让下游能明确区分“未经加工的原始归档”和“含确定性派生字段的临床可读归档”。

## 可逆性

对每条输出执行以下逆变换，必须逐字段等于对应输入：

1. 删除所有名称以 `_decoded` 结尾的派生字段；
2. 删除 `mimic_iv_hosp.poe_timeline`；
3. 删除顶层 `source_schema`；
4. 用 `source_schema` 恢复顶层 `schema`。

流水线在写出每条记录前执行这项比较。任何原始字段被删除、覆盖或改值都会失败。

## 输出报告

报告记录输入、输出和五张字典的绝对路径、字节数及 SHA-256，并给出 admission 数、各路径解码数、空键数、POE 事件数、动作分布和质量标志分布。`unresolved_total` 在成功报告中固定为 `0`；出现未解析的非空完整键时不会产出成功报告。
