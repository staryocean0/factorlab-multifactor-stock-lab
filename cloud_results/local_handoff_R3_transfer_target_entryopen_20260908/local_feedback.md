# LCL-R3-TRANSFER-TARGET-ENTRYOPEN-20260908-01 本地反馈

任务：`LCL-R3-TRANSFER-TARGET-ENTRYOPEN-20260908-01`  
状态：**本地已反馈。entry-open target source 与 successor label bundle 两时钟均通过 1e-7 锚点门。未建立 sidecar，未评分。**  
时间：2026-09-08 14:24–14:54 Asia/Shanghai  
执行方：本地大模型，主题仓 `factorlab-multifactor-stock-lab` 分支 `codex/reaka-foundation-audit-20260905`

## 身份

- 主题仓 HEAD（执行时）：`d6f4bd3a6a7150250fba89e0365d506588e3cf1d`
- FactorLab HEAD：`b39bb12f43a46b165d18db93191a669234077444`
- target-source bridge Git blob：`a72b531707f41f5539f895c88993dcedc0a2162f`
- label bridge v1.1 Git blob：`28fc75615d50fcc901f36ae448c33c42846c4c6a`
- 守卫测试 Git blob：`ad4f25d8f900b39fb89cb2e1ede0ae024eef5574`
- 当前 `reaka_intraday_orthogonal_ot_v1.py` SHA-256：`sha256:4a8ff5fc74adfa474e12a2f0e9c6b770eb7afdb713fe6d676baa423fe5b23c86`
- DataHub 根：`/home/starryocean/桌面/量化/unified_datahub/.runtime/live/lake/bars/dataset_version=bars_cn_a_1m_raw_canonical_4ceca170a851`
- Python：`/usr/bin/python3` 3.13.5
- 未换 DataHub 版本、未改事件规则、未改容差、未用 decision close 替代 future H20
- 未重试；各步均为首次成功

读取月份（69 个分区，无 2026）：  
锚点验证 `2018-01,2018-02,2018-09,2018-10,2019-06,2019-07,2020-03,2020-04,2020-12`；  
尾部 `2021-01`–`2025-12`。

## 命令与退出码

```bash
python3 -m pytest -q \
  tests/unit/test_reaka_r3_transfer_target_source_bridge.py \
  tests/unit/test_reaka_r3_transfer_target_lineage_diag.py \
  tests/unit/test_reaka_r3_transfer_inputs.py
# exit 0；71 passed / 0 failed / 0 skipped

export FACTORLAB_ROOT="/home/starryocean/桌面/量化/baylum terminal 0.4.1/factor_lab"
export DATAHUB_BARS_ROOT="/home/starryocean/桌面/量化/unified_datahub/.runtime/live/lake/bars/dataset_version=bars_cn_a_1m_raw_canonical_4ceca170a851"

python3 scripts/reaka_r3_transfer_target_source_bridge.py \
  --output-root "$FACTORLAB_ROOT/tmp/LCL-R3-TRANSFER-TARGET-ENTRYOPEN-20260908-01/target_source"
# start 2026-09-08T14:25:09+08:00
# {"status": "bounded_entry_open_targets_prepared", "task_id": "LCL-R3-TRANSFER-TARGET-ENTRYOPEN-20260908-01"}
# exit 0 2026-09-08T14:47:38+08:00

python3 scripts/reaka_r3_transfer_label_bridge_v1_1.py \
  --feature-root "$FACTORLAB_ROOT/tmp/LCL-R3-TRANSFER-INPUT-20260907-01/run01" \
  --target-source-root "$FACTORLAB_ROOT/tmp/LCL-R3-TRANSFER-TARGET-ENTRYOPEN-20260908-01/target_source" \
  --output-root "$FACTORLAB_ROOT/tmp/LCL-R3-TRANSFER-TARGET-ENTRYOPEN-20260908-01/label_bundles_v11"
# start 2026-09-08T14:48:30+08:00
# {"status": "bounded_entry_open_label_bundles_prepared", "new_model_fits": 0, "model_inference": 0}
# exit 0 2026-09-08T14:54:13+08:00
```

旧失败的 `scripts/reaka_r3_transfer_label_bridge.py` 未再运行。

## Target source 硬门

`bundle.json.status = bounded_entry_open_targets_prepared`  
`anchor_checks.json.passed = true`  
`calendar_end = 2025-12-31`  
`contains_2026_target = false`

结构成熟锚点（两时钟相同，未用 2020-12-31 作为 future 锚点）：

| 日期 | day_position |
|---|---:|
| 2018-01-08 | 2680 |
| 2018-09-25 | 2855 |
| 2019-06-20 | 3030 |
| 2020-03-10 | 3205 |
| 2020-12-03 | 3385 |

两时钟 `entry_minute_mismatches = 0`。  
entry-open 价格门（含 t 与 t+20）全部 `passed=true`，max abs error = 0。  
future H20 相对旧 P6：两时钟五锚点全部 `support_mismatches=0` 且 `max_abs_error=0.0`（<= 1e-7）。

## Successor label bundle 硬门

两时钟 `target_anchor_checks.json`：

| 时钟 | passed | support_mismatches | max_abs_error | anchors_checked |
|---|---|---:|---:|---:|
| 1430 | true | 0 | 0.0 | 5 |
| 1445 | true | 0 | 0.0 | 5 |

每锚点 finite 支持：2559 / 2949 / 3321 / 3445 / 3630。  
`raw_future_definition = entry_open_t_plus_20_div_entry_open_t_minus_1`。  
calendar 4618 日、3982 股票、尾部 242 个 decision。

## 未执行 / 硬停止

- label sidecar = 0
- archived-score preflight = 0
- 24 fresh-process score jobs = 0
- new model fit = 0
- checkpoint reload = 0
- 2026 target = false
- Actions = false
- 账户 / CloudRidge 月度 = 否

按任务书到此停止，不自行恢复 `LCL-R3-TRANSFER-EVAL-20260908-01` 的 sidecar/preflight/24 score。

`fresh_oos=false`；`PIT_certified=false`；`production_authority=false`。

## 回传

`cloud_results/local_handoff_R3_transfer_target_entryopen_20260908/`：targeted tests、target source `bundle.json`/`anchor_checks.json`/`source_receipt.json`、label `result.json`、两时钟 `bundle.json`/`target_anchor_checks.json`/`producer_sources.json`、运行日志。

大 `entry_open.npy` / `future_h20_raw.npy` / `epsilon_future.npy` 留本地。

本地不代填“云端已复核”。
