# REAKA 文档入口

唯一现行清单：`docs/ops/reaka_multifactor_current_manifest@1.3.json`。
其作用域仅限本研究仓库的基础设施，不修改用户本地 FactorLab 注册表或指针。

| 五位一体 | 现行入口 | 职责 |
|---|---|---|
| 文档与机器合同 | [current@1.3](ops/reaka_multifactor_current_manifest@1.3.json)、[口径合同@1.1](ops/reaka_foundation_semantics@1.1.json) | 唯一权威、对象、状态、来源摘要 |
| 白皮书 | [V1.3 白皮书](ops/reaka_foundation_whitepaper_v1_3.md) | 金融意图、数学映射、成立条件与反例 |
| 代码 | [现行检查器](../src/factor_lab/governance/reaka_foundation_contract.py)及清单中的实现 | 对象、时序、证据与执行边界 |
| 测试 | [单元测试](../tests/unit/) | 合成数学反例、证据造假与入口越界 |
| 工作流 | [V1.3 工作流](user/reaka_multifactor_current_workflow_v1_3.md) | 无行情检查、历史审计、数据通知后的下一步 |

[云端接管说明](user/cloud_execution_prompt.md)与根目录 README / AGENTS / ai-readme 使用同一清单。

历史材料保留原字节和原错误状态，不能充当现行规范：

- [初次审计报告](ops/reaka_foundation_audit_20260905.md)与[历史证据审计工作流](user/reaka_foundation_audit_workflow.md)。
- current@1.0、@1.1、@1.2，旧注册表、旧模型组装/输入兼容性/算子识别/残差准入白皮书与合同。
- [原 ai-readme](reference/ai_readme_before_foundation_v1_3.md)及旧年度策略技能，供追溯原研究政策。

论文以 `research_materials/` 内部授权 PDF 为源，现行数学解释见 V1.3 白皮书。
包边界与数据用途见 [package_scope](governance/package_scope.json)、
[data_usage_declaration](governance/data_usage_declaration.json)。严格数据校验独立于基础设施检查。
