# 文档索引

当前版本只由 [CURRENT.json](../CURRENT.json) 指定。本索引按问题导航，不是要求全部顺序阅读的清单。

| 需要回答的问题 | 唯一主入口 |
|---|---|
| 现在做什么、已有何种证据？ | [研究状态](ops/research_state.json) |
| 接手后如何行动、何时才需要停止？ | [任务工作流](user/reaka_multifactor_current_workflow_v1_4.md) |
| 金融需求如何对应数学对象、如何证伪？ | [白皮书 V1.4](ops/reaka_foundation_whitepaper_v1_4.md) |
| 稳定数学语义如何机器检查？ | [语义@1.2](ops/reaka_foundation_semantics@1.2.json) |
| 代码、测试与执行入口在哪里？ | [现行清单](ops/reaka_multifactor_current_manifest@1.4.json) |
| 本轮为何这样改、覆盖了哪些问题？ | [基础设施审计](ops/infrastructure_audit_20260906.md) |
| 原始数据、用途与授权是什么？ | [包边界](governance/package_scope.json)、[用途声明](governance/data_usage_declaration.json)、[版权](../NOTICE.md) |

## 按需追溯，不是附加前置步骤

[R1 已验收与 R2 恢复回执](../cloud_results/first_round_rework_20260906/rework.md)及[原恢复清单](../cloud_results/first_round_rework_20260906/recovery_request.json)描述当时实际检查，不能代替最新上传状态。

[首次基础审计](ops/reaka_foundation_audit_20260905.md)、[V1.3 白皮书](ops/reaka_foundation_whitepaper_v1_3.md)、[旧长篇接手资料](reference/ai_readme_before_foundation_v1_3.md)用于追溯。旧 current@1.0—1.3、旧 workflow、旧 admission 与封存结果保留历史身份；其临时权限、K 顺序或“只等签字”的状态不自动生效。

全仓 Markdown 链接与孤立历史资料由 `scripts/validate_reaka_foundation.py --inventory` 输出清单；只有现行链中的断链会阻断基础设施检查。历史断链保留为来源问题，不强迫为每个历史文件再建立一套索引。
