# LCL-R3-TRANSFER-INPUT-20260907-01 边界 delta 反馈

任务仍是 `LCL-R3-TRANSFER-INPUT-20260907-01`。  
云端裁决：`cloud_reviewed_build_received_boundary_delta_pending` → 本地已完成 B1—B3 影响检查。  
原 source_bundles / run01 **未覆盖**。无网络训练/推理/checkpoint reload。未启动 24 项评分。

主题仓执行时 HEAD：`53c9acf`（含云端后继 `_basis_frame` / `validate_membership_timing`）。  
FactorLab HEAD 仍为 `b39bb12f43a46b165d18db93191a669234077444`。

## 命令

```bash
python3 -m pytest -q \
  tests/unit/test_reaka_r3_transfer_bridge_contracts.py \
  tests/unit/test_reaka_r3_transfer_source_bridge.py \
  tests/unit/test_reaka_r3_transfer_inputs.py
# exit 0；71 passed

python3 scripts/reaka_r3_transfer_boundary_delta.py \
  --output-root .../tmp/LCL-R3-TRANSFER-INPUT-20260907-01/boundary_delta
# exit 0；boundary_delta_complete_no_array_rewrite
```

未重新运行全源包主命令。

## B1 状态尾部

真实尾部因子基底（6×1212×14=101808 格/时钟）**全部有限，非有限行=0**。

因此旧 `_basis_frame` 多写出的 NaN 日历行在本次真实数据上不存在；`family_tool_state` 的 NaN 分组不会被额外空洞改变。`day_position` 从 0 重置不影响 `build_selected_states`（按 trading_day 排序）。

**状态数组不重建。** 原 `state_values` / `state_available` 继续复用。

## B2 成员时序与有界来源

对**实际使用**的 asof<2026、映射到 3982 的快照检查 `effective_date > asof_date`：

| 源 | 全文件读入行 | asof<2026 | 丢弃 asof≥2026 | 映射到 3982 | 缺日期 | effective≤asof |
|---|---:|---:|---:|---:|---:|---:|
| CloudRidge CSV | 2,168,383 | 2,024,789 | 143,594 | 1,790,492 | 0 | **0** |
| condensation parquet（已滤到原 12 L1+SMALL+LARGE） | 1,308,602 | 1,256,522 | 52,080 | 1,217,859 | 0 | **0** |

原桥接确实整表 pandas 读入后再截断，不能写成读取层从未接触 2026 文件内容。本次 delta **没有**再做 2026 成员科学分析；上表丢弃行数来自与原桥接相同的一次全文件读取+cutoff，只用于披露。

使用快照 asof 最大为 2025-12-31（CR）/ 2025-12-29（core）。CR 使用快照中有 asof=2025-12-31、effective=2026-01-05 的次日生效行，满足 forward-effective，且决策日 searchsorted 在 2025 内不会用到该生效点。不是 2026 标签读取。

**无时序违例，暴露/成员数值不重建。**

## B3 2020-12-31 接缝

每时钟只重算：全日历因子基底投影（检查用缓存，范围约 4498 投影日）+ **1 个**旧末端 D5 的股票 OLS（窗 [day-120, day)）。  
不是再用复制前缀当答案。先前报告的 486 只计股票暴露刷新点。

| 对象 | 1430 | 1445 |
|---|---|---|
| beta / reliability / available | exact，maxdiff 0 | exact，maxdiff 0 |
| epsilon at last D5 | exact，maxdiff 0（3662 finite / 3982） | exact，maxdiff 0 |
| factor basis 84 格 | 支持一致，maxdiff 6.94e-17 | 支持一致，maxdiff 9.02e-17 |

基底差为 float64 舍入，不是可操作的数值漂移。**不另建尾部产物。**

## 结论

真实影响为零：保留原大数组与原 manifest。后继代码修正（有限行 `_basis_frame`、成员时序守卫）对已生成 store 无数值影响。  
`fresh_oos=false`；`PIT_certified=false`；`production_authority=false`。历史到达时间仍 unknown。

回传：`local_feedback_delta.md`、`boundary_checks.json`、`delta_tests.txt`、检查脚本。完成后停止。
