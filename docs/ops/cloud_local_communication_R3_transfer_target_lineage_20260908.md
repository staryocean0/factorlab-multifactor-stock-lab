# LCL-R3-TRANSFER-TARGET-LINEAGE-20260908-01：future residual 目标生产链只读诊断

状态：**本地已反馈（2026-09-08）。** 只读诊断完成；未建立 sidecar、未评分。见 [local_feedback.md](../../cloud_results/local_handoff_R3_transfer_target_lineage_20260908/local_feedback.md)。这是 `LCL-R3-TRANSFER-EVAL-20260908-01` 在 target-anchor 门槛停止后的唯一允许后继。不是新实验。本地不代填云端已复核。

## 1. 云端裁决背景

本地提交 `93ac89560712f8a344982c6885c9c8c3309bd2f9` 已被云端接收为正确停止：targeted tests 77 passed；1430 的 2018-01-08、2018-10-09、2019-07-04、2020-03-31 四个正常旧期锚点有限支持一致但 `epsilon_future` 数值大面积偏离，max abs error 约 0.011--0.017；2020-12-31 则是结构性未成熟锚点，旧 2007--2020 store 不可能有 t+20 标签。

关键源事实：TIMEISO 的 `prepare_store()` 调用 K1 `materialize_store()`，而 `materialize_store()` 直接从旧 OT1 `ot1/stock_residual_surfaces.npz` 复制 `epsilon_history` / `epsilon_future`。当前 `reaka_r3_transfer_label_bridge.py` 则重新用当前 `reaka_intraday_orthogonal_ot_v1.py`、延伸价格、当前 membership 与 `build_causal_basis_pair` / `fit_intraday_stock_exposures` 生成 future residual。两条生产链尚未证明等价，因此**禁止通过调容差、换锚点或直接继续评分绕过此门**。

## 2. 唯一目标

在不训练、不加载 checkpoint、不评分、不建立 sidecar、不读取 2026 target 的前提下，把旧 accepted `epsilon_future` 与当前重建路径分层比较，定位**第一处真实数值分歧**：

1. 旧 OT1 `stock_residual_surfaces.npz` 与 TIMEISO store 是否一致；
2. P6 旧 `future_h20_raw` 与当前延伸 `decision_close` 按固定 t+20 公式计算的 raw future H20 是否一致；
3. 旧 `factor_basis_history/future.parquet` 与当前重建 basis 是否一致；
4. 当前 OT 代码在**旧 P6 raw + 旧 factor basis**上能否重放旧 beta/reliability/available、`epsilon_history`、`epsilon_future`；
5. 当前延伸重建路径在同一批旧锚点上的 beta 与 residual 如何偏离。

不能根据结果改变锚点。锚点规则改为**结构性成熟**而不是检查 target 值：2018--2020 旧 D5 中，仅保留 `day_position + 20 < len(old_calendar)`，再按索引等分固定取 5 个。这个修正只排除天然无 t+20 的 2020-12-31 类日期，不使用任何 target 数值或 finite support 选点。

## 3. 已落库诊断器

使用：

- `scripts/reaka_r3_transfer_target_lineage_diag.py`

先同步当前开发分支，保留本地提交，不 force push。

先运行自检：

```bash
python3 scripts/reaka_r3_transfer_target_lineage_diag.py --self-test
```

必须 exit 0。

然后运行真实只读诊断：

```bash
export FACTORLAB_ROOT="/home/starryocean/桌面/量化/baylum terminal 0.4.1/factor_lab"
python3 scripts/reaka_r3_transfer_target_lineage_diag.py \
  --output-root "$FACTORLAB_ROOT/tmp/LCL-R3-TRANSFER-TARGET-LINEAGE-20260908-01/run01"
```

预期输出：

`target_lineage_diag.json`

如果脚本明确报告缺少 `future_h20_raw_{clock}.npy` 或旧 OT artifact，不允许猜文件名替换；回传缺失路径和候选名后停止。

## 4. 强制停止边界

本任务全部为只读诊断。严格禁止：

- label sidecar；
- archived-score preflight；
- 24 个 fresh-process score jobs；
- 任何网络 fit / DMD 初始化 / checkpoint reload；
- tool / seed / arm / normalizer 变更；
- 2026 target；
- 账户；
- CloudRidge 月度条件研究；
- 为让检查通过而修改 `1e-7` 容差。

诊断输出弱、负或不完整都不得触发结果驱动重跑。

## 5. 云端验收判定

### A. 若 historical artifact replay 成功

若当前 OT 代码在**旧 P6 raw + 旧 factor basis**上，对两时钟 5 个结构成熟锚点能同时重放：

- beta/reliability/available；
- epsilon_history；
- epsilon_future；

且 support 一致、max abs error <= 1e-7，则说明当前函数主体仍能表达旧 target 语义。随后依据诊断结果定位是 raw future H20、future factor basis，还是延伸 membership / 输入重建导致偏离。云端再提供最小修复，不授权本地自行修后继续评分。

### B. 若 historical artifact replay 失败

这表示当前 OT 源码或当前 membership 已不能复刻旧 accepted target producer。此时必须停止扩展标签，并回收旧 OT1 真实生产身份：至少旧 execution receipt / source digest / commit 或可定位的历史源码 byte。未恢复前，2021--2025 target producer 不具备同定义资格。

### C. 2020-12-31 的处理

旧 TIMEISO 日历止于 2020-12-31，因此该日不可能有 H20 future target。它是原 anchor 选择规则缺少结构成熟约束造成的**门槛设计缺陷**，不是证明 target 数值发生漂移的有效锚点。以后若恢复 label gate，云端会先修正式 anchor 规则；在本诊断任务中只使用结构成熟盲锚点，且不因此放宽其他四类数值检查。

## 6. 回传

提交到：

`cloud_results/local_handoff_R3_transfer_target_lineage_20260908/`

至少包含：

1. `local_feedback.md`
2. `self_test.txt`
3. `formal_run.txt`
4. `target_lineage_diag.json`
5. 若失败，首次失败日志

`local_feedback.md` 必须写：

- 主题仓实际 HEAD；
- FactorLab HEAD；
- 实际加载 `reaka_intraday_orthogonal_ot_v1.py` SHA256；
- 旧 `stock_residual_surfaces.npz`、old basis、P6 raw 的 SHA256；
- 两时钟 5 个结构成熟锚点；
- 每层比较 pass/fail 与 maxdiff；
- `historical_artifact_replay_with_current_OT_code` 是否通过；
- `diagnosis` 字段；
- new model fit=0；checkpoint reload=0；model score=0；sidecar=0；2026 target=false；Actions=false；
- 所有未知和缺失。

完成后停止，由云端裁决是否存在可接受的同定义 2021--2025 target producer。

## 7. 本地反馈（2026-09-08）

本地已执行 targeted tests（8 passed）、`--self-test` 与正式只读诊断，exit 均为 0。产物在 `cloud_results/local_handoff_R3_transfer_target_lineage_20260908/`。

- 主题仓执行 HEAD：`554a36b709f4c9aa51d31c0d246299ee99ab82ee`
- FactorLab HEAD：`b39bb12f43a46b165d18db93191a669234077444`
- `historical_artifact_replay_with_current_OT_code`：两时钟通过，max abs error = 0
- `diagnosis`：两时钟均为 `raw_future_H20_path_diverges`
- 结构成熟锚点：2018-01-08、2018-09-25、2019-06-20、2020-03-10、2020-12-03；未使用 2020-12-31
- new model fit=0；checkpoint reload=0；model score=0；sidecar=0；2026 target=false；Actions=false

属于云端判定 A：当前 OT 代码在旧 P6 raw + 旧 basis 上能重放旧 `epsilon_future`。第一处分歧是旧 P6 `future_h20_raw` 与当前延伸 close 的固定 t+20 公式；未调容差、未继续评分、未自行修复。等待云端裁决。
