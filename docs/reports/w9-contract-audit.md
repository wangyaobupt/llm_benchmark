# W9 题目生成、审核与 gold 门禁审计

## 结论

W9 的工程契约已实现并通过 4 项合成测试。题目只能由 validated、非旧链规则生成；答案候选由规则固定，题干生成层不能选择统计答案；decision evidence 采用白名单字段；程序复核与临床复核分离；未签字内容保持 `zero_unapproved`。

## 已实现的规则

- 旧规则 ID 和未 validated 规则拒绝进入题目链；
- rule 与 decision 的 track/class 必须一致；
- 题目证据只允许 occurrence/availability、可见性和 feature 等白名单字段；
- 选项 ID 必须唯一，且必须包含规则选定答案；
- protocol、split、rule lineage hash 必须存在；
- 独立程序审核不能冒充临床审核；
- pattern gold 的标签明确为“MIMIC 观察数据中同类最可能选择”；
- `clinical_best_decision` 必须另有 normative source 和专家裁决；
- 未通过完整程序与临床签字门禁的题目不会提升 gold 状态。

## 验证

```text
tests/investigation_selection/test_question_release.py
4 passed
```

## 正式发布状态

本阶段只验证门禁，未读取 W7 validated rule table，也未生成正式题目或 gold。W1 的独立主体问题未解决前，W9 不能发布正式候选题，W10 不能运行 final-test。
