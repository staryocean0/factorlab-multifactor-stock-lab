# LCL-R3-TRANSFER-TARGET-LINEAGE-20260908-01 本地反馈

任务：`LCL-R3-TRANSFER-TARGET-LINEAGE-20260908-01`  
状态：**本地已反馈。只读诊断完成；未建立 sidecar，未启动评分。**  
时间：2026-09-08 13:47–13:50 Asia/Shanghai  
执行方：本地大模型，主题仓 `factorlab-multifactor-stock-lab` 分支 `codex/reaka-foundation-audit-20260905`

## 身份

- 主题仓 HEAD（执行时）：`554a36b709f4c9aa51d31c0d246299ee99ab82ee`
- FactorLab HEAD：`b39bb12f43a46b165d18db93191a669234077444`
- 诊断器 Git blob：`63aa3263d49f8709d152778f22afe94869c92ecc`（与云端 readiness 一致）
- 守卫测试 Git blob：`c279d4bc3834a9e9f986eae82e07c408acc73674`（与云端 readiness 一致）
- 当前 `reaka_intraday_orthogonal_ot_v1.py` SHA-256：`sha256:4a8ff5fc74adfa474e12a2f0e9c6b770eb7afdb713fe6d676baa423fe5b23c86`
- 当前 bridge `scripts/reaka_r3_transfer_source_bridge.py` SHA-256：`sha256:3ca1cce35a68b23d62632e6921333fcfef4f9df3aa1aa79d6c3fad69d0729c0f`
- Python：`/usr/bin/python3` 3.13.5（与上一轮本地 R3 任务相同；主题仓声明 3.11）
- 正式输出：FactorLab `tmp/LCL-R3-TRANSFER-TARGET-LINEAGE-20260908-01/run01/`（大数组未另存）
- 小产物：`cloud_results/local_handoff_R3_transfer_target_lineage_20260908/`

### 旧 artifact SHA-256

| 文件 | 1430 | 1445 |
|---|---|---|
| TIMEISO `manifest.json` | `sha256:265c1d7b6e319eca87401812a6b696473c44c838734897774c066da8184154ba` | `sha256:c02cc002793f3200bed3ff47a339138b8e2bf6ca99eea3d93c41306b341416cb` |
| 旧 OT `stock_residual_surfaces.npz` | `sha256:7c8854e81288712f0a51e7e50c912d3bf0d63f23c33719fe05c7aaa528dda723` | `sha256:e7d97cef72000218becd7b34c6b653718b889f52716f16307d1ea667eab5cfbf` |
| 旧 `factor_basis_history.parquet` | `sha256:03d13768aa6ab5ede74f93a30b52de8e655b8b318221345fca3d48b71f3f3f87` | `sha256:74eb9c15a41458892d22781a3ee5a0182223ae9d98a4233ca794fb2601cc3226` |
| 旧 `factor_basis_future.parquet` | `sha256:223a53a4c0cfab7d3b00849f669a3f146ca009b2ad548cb0cd197c86580bdbba` | `sha256:188e0123491850edf197ebe832adf01052f4b97ce9d7f2f694e8cd3a54c201a1` |
| P6 `decision_close_{clock}.npy` | `sha256:a771f2b603ede42d1e85a6ab31cb3d396222b1e3f49d70ff0d049c290ff8e68f` | `sha256:fd495e4a7d2979271937445b72e8c18e5c0782bc0d6dd990fe14fc503e348240` |
| P6 `history_h20_raw_{clock}.npy` | `sha256:7a3b830cc5e342fd0d53ecc3f3240d700dfbab814ed9f4f967efb335e24e1a8c` | `sha256:1d15d5dd572b5e7218ed5e4febdbbc1af7720142cbfe1e1b8d02cad588d2eff7` |
| P6 `future_h20_raw_{clock}.npy` | `sha256:1df07ea203a6a14fe51a20db838a34a503a17ff7afa5dcfd723b9e8e0f42fa50` | `sha256:b3769ce087b07325c02e08700c668a50ec709c3b2949458635f213a7e6636039` |

未替换缺失文件名。`future_h20_raw_{clock}.npy` 两时钟均存在。

## 命令与退出码

```bash
python3 -m pytest -q tests/unit/test_reaka_r3_transfer_target_lineage_diag.py
# exit 0；8 passed / 0 failed / 0 skipped

python3 scripts/reaka_r3_transfer_target_lineage_diag.py --self-test
# exit 0；{"status": "self_test_passed", "anchors": [365, 630, 900, 1170, 1440]}

export FACTORLAB_ROOT="/home/starryocean/桌面/量化/baylum terminal 0.4.1/factor_lab"
python3 scripts/reaka_r3_transfer_target_lineage_diag.py \
  --output-root "$FACTORLAB_ROOT/tmp/LCL-R3-TRANSFER-TARGET-LINEAGE-20260908-01/run01"
# start 2026-09-08T13:48:32+08:00
# {"status": "target_lineage_diagnosed_no_scores", "task_id": "LCL-R3-TRANSFER-TARGET-LINEAGE-20260908-01"}
# exit 0 2026-09-08T13:50:28+08:00
```

容差仍为 `1e-7`。未改锚点规则、未换文件、未重跑。

## 结构成熟锚点

规则：2018–2020 旧 D5，且 `day_position + 20 < len(old_calendar)`；按索引等分固定取 5 个。不看 target 值或 finite support。

两时钟相同：

| 日期 | day_position | structurally_mature |
|---|---:|---|
| 2018-01-08 | 2680 | true |
| 2018-09-25 | 2855 | true |
| 2019-06-20 | 3030 | true |
| 2020-03-10 | 3205 | true |
| 2020-12-03 | 3385 | true |

`2020-12-31` **未被选中**。

## 分层结果

诊断器字段 `diagnosis`（两时钟相同）：`raw_future_H20_path_diverges`

`historical_artifact_replay_with_current_OT_code`：**通过**（两时钟、五锚点、beta/reliability/available/`epsilon_history`/`epsilon_future` 的 max abs error 均为 **0.0**，support mismatch=0）。

因此属于云端判定 **A**：当前 OT 代码在旧 P6 raw + 旧 factor basis 上能重放旧 accepted target；不是判定 B（历史 producer/membership 无法复刻）。

| 层 | 1430 | 1445 |
|---|---|---|
| 旧 OT residual → TIMEISO store history | pass，maxdiff=0 | pass，maxdiff=0 |
| 旧 OT residual → TIMEISO store future | pass，maxdiff=0 | pass，maxdiff=0 |
| P6 `future_h20_raw` vs 延伸 close 的 t+20 公式 | **fail**，max=0.017076，support=0，above=11603 | **fail**，max=0.020367，support=0，above=11702 |
| 旧 vs 重建 factor_basis_history | pass，max≈3.05e-16 | pass，max≈9.71e-17 |
| 旧 vs 重建 factor_basis_future | fail，max=0.000985，above=420 | fail，max=0.000651，above=420 |
| 旧 P6 raw + 旧 basis + 当前 OT 重放 exposure | pass，maxdiff=0（278740 格） | pass，maxdiff=0（278740 格） |
| 同上重放 epsilon_history | pass，maxdiff=0 | pass，maxdiff=0 |
| 同上重放 epsilon_future | pass，maxdiff=0 | pass，maxdiff=0 |
| 延伸重建路径 exposure / epsilon_history | pass，maxdiff=0 | pass，maxdiff=0 |
| 延伸重建路径 epsilon_future | **fail**，max=0.017107，above=15902 | **fail**，max=0.020399，above=15893 |

按诊断器既定优先级，**第一处真实分歧是 raw future H20**：旧 P6 `future_h20_raw` 与当前延伸 `decision_close` 按 `r[t+20]/r[t]-1` 计算的值，有限支持一致但数值大面积超过 1e-7。history 侧（P6 close 前缀、history H20、history basis、history residual、exposure）在旧锚点上一致。future basis 也偏离，但量级更小（约 1e-3），且排在 raw future H20 之后；其偏离与用已偏离的 future raw 去重建 future carrier/basis 相符，本反馈不把它改写成独立第一因。

### 1430 raw future H20 锚点

| 日期 | max abs error | above 1e-7 | finite | support mismatch |
|---|---:|---:|---:|---:|
| 2018-01-08 | 0.017076 | 2047 | 2946 | 0 |
| 2018-09-25 | 0.009626 | 2111 | 3242 | 0 |
| 2019-06-20 | 0.012485 | 2278 | 3390 | 0 |
| 2020-03-10 | 0.012802 | 2465 | 3568 | 0 |
| 2020-12-03 | 0.012826 | 2702 | 3913 | 0 |

### 1445 raw future H20 锚点

| 日期 | max abs error | above 1e-7 | finite | support mismatch |
|---|---:|---:|---:|---:|
| 2018-01-08 | 0.012882 | 2030 | 2946 | 0 |
| 2018-09-25 | 0.020367 | 2171 | 3242 | 0 |
| 2019-06-20 | 0.012694 | 2336 | 3390 | 0 |
| 2020-03-10 | 0.013362 | 2410 | 3568 | 0 |
| 2020-12-03 | 0.012453 | 2755 | 3913 | 0 |

延伸重建 `epsilon_future` 的 maxdiff 与上一轮 label-bridge 旧锚点量级一致（约 0.011–0.020），支持仍对齐。

## 未执行 / 硬停止

- label sidecar = 0
- archived-score preflight = 0
- model score jobs = 0
- new model fit = 0
- checkpoint reload = 0
- 2026 target = false
- Actions = false
- 账户 / CloudRidge 月度 / 调容差 / 换锚点 = 否
- 未自行修改 OT/label producer，未继续评分

`fresh_oos=false`；`PIT_certified=false`；`production_authority=false`。

## 未知

- 未打开 P6 原始 producer 源码/receipt 去解释 `future_h20_raw` 与当前 `close[t+20]/close[t]-1` 为何数值不同；本任务只定位第一层。
- 未证明 2021–2025 延伸 target 可与旧定义同口径。
- 未独立重算 TIMEISO `materialize_store()` 复制链以外的历史拟合过程。

完成后停止，待云端裁决最小修复；本地不代填“云端已复核”。
