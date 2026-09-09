# V1.4 基础设施实跑回执

**当前基础设施检查与已选测试范围通过，不代表全仓、R2或策略有效性通过。** 详细机器回执见 [validation_receipt.json](validation_receipt.json)。

实现提交 `ebdf63c5b7ad98c6349e90da6f4410a80f4f8e92` 在实际PR合并快照 `028923e8112a7b215332a9ab056b63d16ca61bcb` 运行 [Actions 34012881110](https://github.com/staryocean0/factorlab-multifactor-stock-lab/actions/runs/34012881110)。合并输入包括main的 `af2e478aaff5c8ef7f753424b57fd2d19019f248`；不是只验旧分支而漏掉新上传源码。

现行40项入口/组件定位、稳定语义和当前链接检查通过，错误为空。22个单元测试模块中20个实际执行，共386项，零失败、零错误、零跳过。包括本轮38项新反例和20项在固定原字节上执行的V1.3历史合同反例；其余为实际当前数学、来源、时序、证书、映射与退役入口测试。

两份历史测试模块因缺 `src/factor_lab/filtering/cloudridge_3_0_hybrid_filter_bank.py` 单独列为未执行：`test_reaka_current_k1_account_ledgers_v1.py` 与 `test_reaka_intraday_orthogonal_ot_v1.py`。没有把它们计为通过，严格全量pytest仍保留。源文件恢复后自动纳入；新增测试默认执行，不凭结果加入忽略列表。

CI只额外读取三个现有小反例文件，共128698字节，逐一记录原Git字节摘要；没有下载全量行情面板或P6.1/P6.2大数组。真实旧证书与重复月反例仍被测试，不因稀疏检出而删除。

扫描83份Markdown、2618个链接目标，现行链断链为零。2491项历史导航限制原样保留，其中2377项来自四份原FactorLab整库索引副本；不把它们当成当前仓库必须补齐的上传清单。扫描器不证明全部历史文字正确，也未访问外链。

已下载该次完整artifact并校验ZIP SHA-256：`0c6898e9ae038b4dca882cdc30b2577adf503b899a214840d7324e397e665c73`。原文件包括checkout、环境、全部导航清单、三份夹具摘要、测试范围和JUnit；[artifact 9983024620](https://github.com/staryocean0/factorlab-multifactor-stock-lab/actions/runs/34012881110/artifacts/9983024620) 在GitHub设置为2026-10-06到期。此前两次真实失败的artifact也已下载并核验，其原因、修复和身份记录在机器回执，不冒充首轮通过。

完整审计裁决见 [基础设施审计](../../docs/ops/infrastructure_audit_20260906.md)。后续AI从根 `CURRENT.json`、[任务工作流](../../docs/user/reaka_multifactor_current_workflow_v1_4.md)、[研究状态](../../docs/ops/research_state.json) 接手。普通文档修改无需重封历史摘要；经验结论仍需与金融对象、时钟、支持及运行身份一致的证据。

没有执行数据全量任务、R2 PIT重建、新拟合、冻结分数重算、选K或账户重放；`fresh_oos=false`，无生产或本地指针权限。仓库公开性与旧私有声明不符的风险另在审计登记，本轮未擅改权限。

本目录仅追加验证证据，不修改已测试代码与指导文件；是否已合并main以PR状态为准，不能把PR分支交付写成main已更新。
