# LCL-R3-TRANSFER-INPUT-20260907-01 云端最终验收

日期：2026-09-08  
原构建提交：`1c9f78f7f31282473f715ce7302be867d1aea440`  
边界修复基点：`53c9acf50e2cfd2efcd8a73fa74e1eaddb0ff6a1`  
本地 delta 提交：`3ea55e503296761233f992b97ca4ae7decbaf349`

## 裁决

**验收通过，任务 `completed_with_limits`。**

接收两时钟 2021–2025、固定原 3982 股票队列、14 因子、71 通道的无标签 transfer feature stores，作为后继冻结模型历史迁移评分的输入。无需重跑全桥接，也无需重建现有大数组。

本验收只说明：在本次已绑定的当前生产源码/输入路径和冻结合同下，前次指出的 B1/B2/B3 边界问题已经闭合到不会改变现有 transfer arrays 的程度。它**不**认证历史首次可读时间、完整 PIT、fresh OOS、生产或交易权限。

## 1. delta 执行边界

GitHub 比较确认：`53c9acf... -> 3ea55e...` 只新增 `boundary_checks.json`、delta 测试日志、`local_feedback_delta.md`、边界检查脚本，并更新同任务沟通状态；没有覆盖原 `source_bundles`/`run01`，没有修改模型、checkpoint 或评分结果。

本地回传：

- 71 targeted tests，0 failure / 0 error / 0 skipped，exit 0；
- `boundary_delta_complete_no_array_rewrite`；
- 新网络 fit = 0；
- 新 model inference = 0；
- checkpoint reload = 0；
- full bridge rerun = false；
- 24 项跨期评分仍未启动；
- 本地 delta commit 没有 GitHub Actions workflow run。

## 2. B1：state tail 的 `_basis_frame` 差异对本次真实数组无数值影响

原桥接将 2021+ tail DataFrame 的 `day_position` 从 0 重置，并保留可能的 NaN basis 行；后继代码已恢复原 producer 的有限行语义和全局 `day_position`。

真实本地检查显示，每个时钟的 tail basis 为 `6 × 1212 × 14 = 101,808` 格，**101,808/101,808 全部有限，nonfinite=0**。因此旧桥接在本次实际 tail 中没有额外 NaN 行可影响滤波输入。

云端另外读取原 intraday producer Git blob `0f4fb990...`，确认 `build_selected_states` 对每个 `(variant,factor)` 使用 `trading_day` 建索引并排序，**不读取 `day_position`**。所以旧 tail 的局部位置编号错误是元数据问题，不改变本次 `build_selected_states` 数值输入。

结论：现有 `state_values` / `state_available` 不需要重建。后继 `_basis_frame` 修正只用于防止未来再次发生该合同偏差，不能倒签旧桥接源码已经正确。

## 3. B2：成员表使用快照没有 forward-effective 违例；物理读取 2026 仍如实保留

本地对原桥接实际使用规则（`asof_date < 2026-01-01`，映射回原 3982 股票）做只读检查：

### CloudRidge

- 全文件读取：2,168,383 行；
- `asof<2026`：2,024,789；
- 因 `asof>=2026` 丢弃：143,594；
- 映射原 3982 后：1,790,492；
- 缺日期：0；
- `effective_date <= asof_date`：0。

最大使用 asof 为 `2025-12-31`，其最大 effective 为 `2026-01-05`。这是一条 forward-effective 记录；2025 年有界 calendar 中没有 `2026-01-05`，因此不会成为 2025 决策使用的生效快照。

### Core/industry

- 经原 12 L1 + SMALL + LARGE 目标过滤后全文件读取：1,308,602 行；
- `asof<2026`：1,256,522；
- 因 `asof>=2026` 丢弃：52,080；
- 映射原 3982 后：1,217,859；
- 缺日期：0；
- `effective_date <= asof_date`：0；
- 最大使用 effective 为 `2025-12-30`。

原 producer 的 `load_memberships` 本来就要求 `effective_date > asof_date`；后继 bridge 已恢复这个硬检查。

**重要限制**：原 bridge 确实先读取包含 2026 行的 CSV/parquet 再过滤，不能改写成“读取层完全没有接触 2026”。本次仅确认被实际用于 2021–2025 feature construction 的日期快照没有回溯生效违例；没有历史 arrival log，成员上游产品的完整 PIT 仍未认证。

这不足以构成已证明的未来收益泄漏，也不要求因为文件包含 2026 行就重建已有数值。

## 4. B3：2020-12-31 接缝闭合

本地没有用复制前缀冒充重放，而是每时钟重新生成完整有界因子 basis 作为检查缓存，并只重新执行 **1 个最后旧 D5** 的股票 OLS（窗口 `[day-120, day)`）。

最后旧 D5：index `3405`，日期 `2020-12-31`。

### 14:30

- factor basis：84/84 有限支持一致，max abs diff `6.94e-17`；
- beta：55,748 cells exact，max diff 0；
- reliability：55,748 cells exact，max diff 0；
- available：55,748 cells exact，max diff 0；
- epsilon：3,662/3,982 finite support exact，max diff 0。

### 14:45

- factor basis：84/84 有限支持一致，max abs diff `9.02e-17`；
- beta/reliability/available：各 55,748 cells exact，max diff 0；
- epsilon：3,662/3,982 finite support exact，max diff 0。

basis 的约 `1e-16` 差异属于 float64 舍入量级；支持完全一致，且下游旧边界 beta/reliability/mask/epsilon 已精确恢复。本验收不将 `seam_all_exact=false`（因 basis 非逐 bit exact）误写为所有接缝失败。

结论：没有证据要求局部或全量重建现有 2021–2025 transfer arrays。

## 5. 当前可以放行什么

现在可以进入**冻结模型、零新训练的 2021–2025 历史迁移评分接线**，仍仅使用事前已登记的四组模型：

- `F`；
- `STATE_VALUE_PLUS_E`；
- `BETA_ONLY`；
- `BETA_RELIABILITY`。

主要对比仍为：

1. `F − STATE_VALUE_PLUS_E`：只能称既有 state-mask **算法路径**的跨期表现，不能重新称为动态 mask 信号，因为 INFOCLOCK 已证明 2018–2020评价期 mask 恒为1；
2. `BETA_RELIABILITY − BETA_ONLY`：reliability 的冻结跨期算法增量。

新网络训练仍为 0；不重新选工具、不重估 normalizer、不重新初始化 DMD、不新增 arm、不读取2026补标签。2021–2025 在治理声明中仍为 consumed historical material，成功也不是 fresh OOS。

在真正评分前还需要云端接通**独立 label/evaluation sidecar 与 fresh-process checkpoint scoring**。feature store 本身保持无标签，不把 future target 倒灌进输入支持。

## 6. 仍未建立

- historical arrival-time PIT；
- 完整上游 membership / price product 的因果生成闭包；
- fresh OOS；
- unique causal attribution；
- tradability、股票总收益或账户 alpha；
- production authority。

`fresh_oos=false`、`PIT_certified=false`、`production_authority=false` 保持。
