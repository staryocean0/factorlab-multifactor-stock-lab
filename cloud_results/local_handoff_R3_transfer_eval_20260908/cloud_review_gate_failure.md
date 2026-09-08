# 云端裁决：LCL-R3-TRANSFER-EVAL-20260908-01 target-anchor 门槛失败

日期：2026-09-08  
本地回传提交：`93ac89560712f8a344982c6885c9c8c3309bd2f9`  
裁决：**停止有效；transfer evaluation 未开始；当前 label producer 不接收。**

## 1. 接收的事实

本地按冻结任务先运行 targeted tests，结果 77 passed / 0 failed / 0 skipped。随后 label bridge 在 target-anchor 门槛失败，未建立 sidecar，未执行 archived-score preflight，未启动 24 个 fresh-process score jobs；new network fit=0，checkpoint selection=0，model inference score jobs=0。

1430 已返回 5 个原规则锚点：

- 2018-01-08：support mismatch=0，max abs error≈0.017107；
- 2018-10-09：support mismatch=0，max abs error≈0.012295；
- 2019-07-04：support mismatch=0，max abs error≈0.011489；
- 2020-03-31：support mismatch=0，max abs error≈0.016294；
- 2020-12-31：旧 TIMEISO future target 全 NaN，而延伸路径有 3663 个 finite 值。

本地没有修改 1e-7 容差，没有结果驱动换锚点，也没有绕过门槛继续评分。该停止行为符合任务合同。

## 2. 云端复核发现

### 2.1 不是浮点误差

前四个正常锚点几乎整行超过容差，误差达到 1e-2 量级。不能通过放宽 1e-7 容差处理。

### 2.2 B3 旧验收没有覆盖 future residual

前序 transfer-input B3 重放脚本把 `future_returns` / `future_basis` 显式置为 NaN，并将重放 `epsilon_h` 与 TIMEISO `epsilon_history` 比较。因此 B3 的 `epsilon exact` 仅证明 **epsilon_history** 接缝，不证明 `epsilon_future` 生产链。

### 2.3 TIMEISO accepted target 与当前 label bridge 来自不同生产路径

TIMEISO `prepare_store()` 调用 K1 `materialize_store()`。当前仓库中的 `materialize_store()` 直接打开旧 OT1：

`ot1/stock_residual_surfaces.npz`

并复制其中：

- `epsilon_history`
- `epsilon_future`

进入 K1 store。

而当前 `scripts/reaka_r3_transfer_label_bridge.py` 不是读取/延伸同一 sealed target artifact；它使用当前 FactorLab `reaka_intraday_orthogonal_ot_v1.py`，从延伸到 2025 的 decision close 重新计算 future H20、future carriers、basis，并再次调用 `fit_intraday_stock_exposures()` 生成 future residual。

因此本次 gate 失败首先证明：**当前重新生成路径尚未被证明与旧 accepted OT1 target producer 同定义。** 不能把它称为可用的 2021--2025 同定义 label producer。

### 2.4 2020-12-31 是独立的门槛设计缺陷

旧 TIMEISO 日历止于 2020-12-31，H20 target 要求 t+20，因此 2020-12-31 在结构上不可能成熟。原 `anchor_decisions()` 只按年份选 D5，没有要求 `day+20 < len(old_calendar)`，故把天然无标签的末日选成锚点。

该点应在未来修订为“结构成熟盲锚点”：只用日期和 horizon 判断 maturity，再做固定索引等分，不读取 target 数值或 finite support 选点。这不是事后按结果挑锚点，而是修复目标定义本身的结构约束。

但即使排除该无效末日锚点，前四个成熟锚点仍大幅失败，因此当前任务仍然被硬阻断。

## 3. 结论

`LCL-R3-TRANSFER-EVAL-20260908-01` 当前状态：

`blocked_at_target_lineage_gate_no_scores`

不接收当前 label producer；不允许建立 sidecar，不允许 archived-score preflight，不允许 24 项评分。

本次失败不改变此前已接受的 2018--2020 TIMEISO / XFINE 结果，也不证明那些旧结果错误；它只说明**向 2021--2025 延伸 future residual target 的生产身份尚未闭合**。

## 4. 唯一后继

新任务：`LCL-R3-TRANSFER-TARGET-LINEAGE-20260908-01`

入口：

`docs/ops/cloud_local_communication_R3_transfer_target_lineage_20260908.md`

已提供只读诊断器：

`scripts/reaka_r3_transfer_target_lineage_diag.py`

该任务只分层比较 old P6 raw、old factor basis、old stock residual artifact 与当前 OT 代码/延伸重建路径，寻找第一处分歧；模型训练、checkpoint reload、sidecar和score全部保持为0。

只有在两时钟的历史 artifact replay 与目标身份闭合后，云端才会修正式成熟锚点规则并决定是否重新开放原 transfer evaluation。