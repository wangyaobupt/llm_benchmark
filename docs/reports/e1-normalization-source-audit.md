# E1 normalization 数据源探索性审计

> 本报告只用于 EHR-observable Gold 方法学探索，不是 official final-test，也不产生临床 gold。

## 数据规模

- 事件行：`27,336,811`
- 主体：`20,136`；hadm：`39,036`；encounter：`88,785`
- normalized_events SHA-256：`69f29e310a53c980857dd8159b1f2e4cedfa823719754e116935d7d2751bb7cf`

## Gold 候选相关事件

| event_kind | rows | mapped | source_event | post_hoc | resolved time | concept 数 | subject 数 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `clinical_ordered` | 4,015,636 | 0 | 4,015,636 | 0 | 4,015,636 | 0 | 20,065 |
| `imaging_ordered` | 179,223 | 94,628 | 179,223 | 0 | 179,223 | 1 | 18,424 |
| `imaging_reported` | 138,399 | 0 | 138,399 | 0 | 138,399 | 0 | 18,492 |
| `laboratory_ordered` | 969,587 | 0 | 969,587 | 0 | 969,587 | 0 | 19,967 |
| `laboratory_resulted` | 8,237,891 | 8,237,891 | 8,237,891 | 0 | 8,193,986 | 756 | 19,031 |
| `microbiology_resulted` | 153,622 | 153,622 | 153,622 | 0 | 152,446 | 113 | 11,599 |

## 初步门禁结论

1. `post_hoc` 事件不能进入 query evidence；只能作为后验审计信息。
2. `normalization_status=unresolved` 不能静默转为可答候选；需要拒答或进入 review queue。
3. order 与 result 必须分开定义，不能用结果行替代订单行为 Gold。
4. 下一阶段需在 decision-level 构造候选 Gold，检查唯一性、target/evidence overlap、取消/无效订单和同主体重复。

详细计数见同目录 JSON 审计产物。
