# LCL-R3-TRANSFER-EVAL-20260908-01 本地反馈

任务：`LCL-R3-TRANSFER-EVAL-20260908-01`  
状态：**在 target-anchor 门槛停止。未建立 sidecar，未启动 24 项评分。**  
时间：2026-09-08

## 身份

- 主题仓 HEAD：`71662bab6eff81445075efaf1cd3113cacfaf91f`
- FactorLab HEAD：`b39bb12f43a46b165d18db93191a669234077444`
- accepted feature root：`tmp/LCL-R3-TRANSFER-INPUT-20260907-01/run01`（未重建）
- TIMEISO environment：`tmp/LCL-R3-TIMEISO-20260907-01/run01/environment.json`（原验收文件，未重写）

## 已完成

```bash
python3 -m pytest -q \
  tests/unit/test_reaka_r3_transfer_evaluation.py \
  tests/unit/test_reaka_r3_transfer_score_preflight.py \
  tests/unit/test_reaka_r3_transfer_label_bridge.py \
  tests/unit/test_reaka_r3_transfer_inputs.py
```

exit 0；**77 passed / 0 failed / 0 skipped**。

## 停止点：label bundle 锚点门槛

```bash
python3 scripts/reaka_r3_transfer_label_bridge.py \
  --feature-root .../LCL-R3-TRANSFER-INPUT-20260907-01/run01 \
  --output-root .../label_bundles
```

首次 root `label_bundles`：仅 mkdir，无产物。  
第二次新 root `label_bundles_run02`：exit 1，

`ValueError: target producer does not reproduce accepted old anchors`

按任务书：**不改容差、不换锚点、不启动 score。**

### 同一 5 个盲锚点的失败证据（1430）

选择规则未改：2018–2020 旧 D5 等分 5 个索引。容差仍为 1e-7。

| 日期 | day | support mismatch | max abs error | 说明 |
|---|---:|---:|---:|---|
| 2018-01-08 | 2680 | 0 | 0.017107 | 有限支持一致，数值超过 1e-7（2559/2559 格超容差） |
| 2018-10-09 | 2860 | 0 | 0.012295 | 同上 2957 格 |
| 2019-07-04 | 3040 | 0 | 0.011489 | 3329/3331 格超容差 |
| 2020-03-31 | 3220 | 0 | 0.016294 | 3439/3441 格超容差 |
| 2020-12-31 | 3405 | **3663** | 0.0 | TIMEISO `epsilon_future` 全 NaN（日历止于 2020-12-31，无 t+20）；新 producer 用延伸到 2025 的 close 算出 3663 个有限值 |

合计 `anchors_checked=5`，`passed=false`，`support_mismatches=3663`，`max_abs_error≈0.0171`。

未对 1445 再跑全量 label 主命令。B3 昨日核对的是 **epsilon_history 接缝 exact**，不是 epsilon_future。本次锚点失败发生在 **future residual** 路径。

## 未执行

- label sidecar
- archived-score preflight
- 24 fresh-process score jobs
- 账户 / 2026 target / CloudRidge 月度

新网络 fit=0；checkpoint selection=0；inference score jobs=0。

## 回传

`cloud_results/local_handoff_R3_transfer_eval_20260908/`：targeted tests、local_feedback、label_bridge_run02.txt、target_anchor_failure_1430.json。

大数组未生成成功 label bundle。原 feature stores / TIMEISO / XFINE 未覆盖。

`fresh_oos=false`；`PIT_certified=false`；`production_authority=false`。完成后停止，待云端裁决。
