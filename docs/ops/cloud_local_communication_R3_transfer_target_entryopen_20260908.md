# LCL-R3-TRANSFER-TARGET-ENTRYOPEN-20260908-01：恢复P6 entry-open future target

状态：**本地已反馈（2026-09-08）。** entry-open target source 与 successor label bundle 两时钟均通过 1e-7 锚点门；未建立 sidecar、未评分。见 [local_feedback.md](../../cloud_results/local_handoff_R3_transfer_target_entryopen_20260908/local_feedback.md)。前置 `LCL-R3-TRANSFER-TARGET-LINEAGE-20260908-01` 判定A保持。本地不代填云端已复核。

## 1. 已恢复的旧P6精确定义

R2独立审计源码已经冻结并验证：

- history H20：`decision_close[t] / decision_close[t-20] - 1`；
- future H20：**`entry_open[t+20] / entry_open[t] - 1`**；
- `entry_open[t]`：同一交易日中，timestamp字符串 `[11:16]` 的会话墙钟时间严格晚于决策时钟、且不晚于15:00的**第一条正且有限的一分钟open**；
- 14:30对应最早可用entry分钟通常为14:31，14:45对应14:46；缺失或无效分钟向后取第一条有效open；
- 该时间字符串用法是历史实现约定，不是UTC→上海时区变换证明。

`2020-12-31`在旧2020年末日历上无`t+20`，继续不作为future target锚点。

## 2. 新增代码

使用：

- `scripts/reaka_r3_transfer_target_source_bridge.py`
- `scripts/reaka_r3_transfer_label_bridge_v1_1.py`
- `tests/unit/test_reaka_r3_transfer_target_source_bridge.py`

旧失败的 `scripts/reaka_r3_transfer_label_bridge.py` **保留不改**，不得再次作为正式target生产器。

新target-source bridge：

1. 复用accepted P6的2007–2020 `entry_open/entry_minute/future_h20_raw`前缀；
2. 从DataHub一分钟月分区按旧事件规则抽取2021–2025 entry open；
3. 只为5个结构成熟旧锚点及其`t+20`日读取少量2018–2020月份来验证事件规则；
4. 正式尾部只打开2021-01到2025-12分区，不打开2026 target月份；
5. 先要求DataHub重建的旧锚点entry minute一致、entry open满足原R2价格容差，再要求重建的future H20在`1e-7`内复现旧P6；
6. 最后20个2025日历位置target必须保持NaN，不用2026补。

新label bridge v1.1只接受上述通过锚点的target-source bundle；future factor basis与future residual均使用该`future_h20_raw`，不再从decision close计算future return。label bridge自身仍用5个结构成熟旧D5再次重放accepted TIMEISO epsilon_future。

## 3. 本地执行顺序

先同步开发分支，保留并行提交，不force push。

### A. targeted tests

```bash
python3 -m pytest -q \
  tests/unit/test_reaka_r3_transfer_target_source_bridge.py \
  tests/unit/test_reaka_r3_transfer_target_lineage_diag.py \
  tests/unit/test_reaka_r3_transfer_inputs.py
```

必须exit 0，否则停止。

### B. 构建有界entry-open target source

```bash
export FACTORLAB_ROOT="/home/starryocean/桌面/量化/baylum terminal 0.4.1/factor_lab"
export DATAHUB_BARS_ROOT="/home/starryocean/桌面/量化/unified_datahub/.runtime/live/lake/bars/dataset_version=bars_cn_a_1m_raw_canonical_4ceca170a851"

python3 scripts/reaka_r3_transfer_target_source_bridge.py \
  --output-root "$FACTORLAB_ROOT/tmp/LCL-R3-TRANSFER-TARGET-ENTRYOPEN-20260908-01/target_source"
```

硬门：

- `bundle.json.status == bounded_entry_open_targets_prepared`；
- `anchor_checks.json.passed == true`；
- 两时钟 `entry_minute_mismatches == 0`；
- 两时钟5个结构成熟锚点的future H20全部 support mismatch=0 且 max abs error <= `1e-7`；
- calendar截止2025-12-31；
- 最后20位置future target无有限值；
- 不打开2026月份作为target来源。

失败则停止，不换DataHub版本、不改事件规则、不改容差、不用decision close替代。

### C. 用successor label bridge构建两时钟label bundle

仅当B通过：

```bash
python3 scripts/reaka_r3_transfer_label_bridge_v1_1.py \
  --feature-root "$FACTORLAB_ROOT/tmp/LCL-R3-TRANSFER-INPUT-20260907-01/run01" \
  --target-source-root "$FACTORLAB_ROOT/tmp/LCL-R3-TRANSFER-TARGET-ENTRYOPEN-20260908-01/target_source" \
  --output-root "$FACTORLAB_ROOT/tmp/LCL-R3-TRANSFER-TARGET-ENTRYOPEN-20260908-01/label_bundles_v11"
```

硬门：两时钟 `target_anchor_checks.json.passed=true`，`support_mismatches=0`，`max_abs_error<=1e-7`。锚点只能由结构成熟日期规则选择，不看target值。

## 4. 本任务停止点

即使label bundle两时钟都通过，也**在此停止**。本任务不允许：

- label sidecar；
- archived-score preflight；
- 24个fresh-process score jobs；
- 模型fit、DMD、checkpoint reload；
- seed/arm/normalizer/tool变化；
- 2026 target；
- 账户或月度CloudRidge。

云端验收target source与label bundle后，才恢复原 `LCL-R3-TRANSFER-EVAL-20260908-01` 的sidecar/preflight/24 score阶段。

## 5. 回传

提交到：

`cloud_results/local_handoff_R3_transfer_target_entryopen_20260908/`

小产物至少包括：

1. `local_feedback.md`
2. targeted test log/JUnit
3. target source `bundle.json`
4. `anchor_checks.json`
5. `source_receipt.json`
6. successor label bridge顶层 `result.json`
7. 两时钟label `bundle.json`
8. 两时钟 `target_anchor_checks.json`
9. 两时钟 `producer_sources.json`
10. 首次失败日志（如有）

大 `entry_open.npy`、`future_h20_raw.npy`、`epsilon_future.npy` 留本地。

反馈必须报告实际主题仓HEAD、FactorLab HEAD、DataHub根、命令/exit code、读取月份范围、锚点、maxdiff、有限支持、是否发生重试、fit/reload/score/sidecar均为0、2026 target=false、Actions=false及所有未知。

本任务仍为consumed historical extension准备：`fresh_oos=false`、`PIT_certified=false`、`production_authority=false`。

## 6. 本地反馈（2026-09-08）

本地已执行 targeted tests（71 passed）、entry-open target source 与 successor label bridge v1.1，exit 均为 0。产物在 `cloud_results/local_handoff_R3_transfer_target_entryopen_20260908/`。

- 主题仓执行 HEAD：`d6f4bd3a6a7150250fba89e0365d506588e3cf1d`
- FactorLab HEAD：`b39bb12f43a46b165d18db93191a669234077444`
- DataHub：`bars_cn_a_1m_raw_canonical_4ceca170a851`；读取 69 个月份，无 2026
- `anchor_checks.json.passed=true`；两时钟 `entry_minute_mismatches=0`；future H20 五锚点 max abs error=0
- 两时钟 label `target_anchor_checks.json.passed=true`，`support_mismatches=0`，`max_abs_error=0.0`
- new model fit=0；checkpoint reload=0；model score=0；sidecar=0；2026 target=false；Actions=false

按任务书停止，等待云端验收后再恢复原 transfer-eval 的 sidecar/preflight/24 score。
