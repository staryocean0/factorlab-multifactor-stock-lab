# LCL-R3-TRANSFER-EVAL-20260908-01：冻结模型2021—2025迁移评价

状态：**继续冻结评分；先执行 `LCL-R3-TRANSFER-TARGET-ENTRYOPEN-20260908-01`。** 旧target-anchor失败已经由target-lineage诊断定位：旧P6 future H20的真实定义是 `entry_open[t+20] / entry_open[t] - 1`，不是decision close。失败的旧 `reaka_r3_transfer_label_bridge.py` 保留为历史反例，不再作为正式target生产器。

当前唯一执行入口：`docs/ops/cloud_local_communication_R3_transfer_target_entryopen_20260908.md`。

在该entry-open target-source与successor label bundle通过云端验收前，以下全部保持0：label sidecar、archived-score preflight、24个fresh-process score jobs、checkpoint reload、新网络fit、2026 target、账户、月度CloudRidge。

后续评分合同保持不变：四组冻结模型 F / STATE_VALUE_PLUS_E / BETA_ONLY / BETA_RELIABILITY；两时钟；seed 11/29/47；两项primary为 `F - STATE_VALUE_PLUS_E` 与 `BETA_RELIABILITY - BETA_ONLY`；新训练=0；不重选工具、normalizer、checkpoint、seed、arm或年份。评价仍为consumed 2021–2025 historical transfer，`fresh_oos=false`、`PIT_certified=false`、`production_authority=false`。

历史完整执行说明可从本文件上一Git版本查看；本页只保留当前有效路由，避免再次运行已知错误的decision-close label producer。
