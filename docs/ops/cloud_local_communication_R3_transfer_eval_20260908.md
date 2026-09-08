# LCL-R3-TRANSFER-EVAL-20260908-01：冻结模型2021—2025迁移评价

状态：本地已在 target-anchor 门槛停止并回传；未建立 sidecar、未评分。见 `cloud_results/local_handoff_R3_transfer_eval_20260908/local_feedback.md`。

## 1. 唯一任务

生成独立H20金融残差label bundles，建立post-score label sidecars，然后用四组既有冻结模型完成**恰好24项fresh-process score jobs**和两项已预登记的历史迁移对比。

本任务：

- 新网络fit = **0**
- checkpoint selection = **0**
- normalizer refit = **0**
- tool reselection = **0**
- DMD reinitialization = **0**
- Actions = **0**
- 2026 target读取 = **0**

不得新增seed/arm/年份，不跑账户，不猜CloudRidge月度公式。

## 2. 代码入口

分支：`codex/reaka-foundation-audit-20260905`

先同步当前分支，不覆盖并行提交。使用：

- `src/factor_lab/factor_rotation/reaka_r3_transfer_evaluation.py`
- `src/factor_lab/factor_rotation/reaka_r3_transfer_score_preflight.py`
- `scripts/reaka_r3_transfer_evaluate.py`
- `scripts/reaka_r3_transfer_label_bridge.py`
- `tests/unit/test_reaka_r3_transfer_evaluation.py`
- `tests/unit/test_reaka_r3_transfer_score_preflight.py`
- `tests/unit/test_reaka_r3_transfer_label_bridge.py`
- 方案：`docs/ops/r3_transfer_evaluation_plan_20260908.md`

## 3. 第一步：targeted tests

```bash
python3 -m pytest -q \
  tests/unit/test_reaka_r3_transfer_evaluation.py \
  tests/unit/test_reaka_r3_transfer_score_preflight.py \
  tests/unit/test_reaka_r3_transfer_label_bridge.py \
  tests/unit/test_reaka_r3_transfer_inputs.py
```

至少新增三个模块必须全部通过；transfer-input回归也必须通过。失败则停止，不生成标签或score。

记录实际tests/pass/fail/skip与exit code，不使用Actions替代。

## 4. 第二步：生成两时钟有界label bundles

使用前序accepted feature root，例如：

```bash
export FACTORLAB_ROOT="/path/to/factor_lab"
python3 scripts/reaka_r3_transfer_label_bridge.py \
  --feature-root /path/to/FactorLab/tmp/LCL-R3-TRANSFER-INPUT-20260907-01/run01 \
  --output-root /path/to/FactorLab/tmp/LCL-R3-TRANSFER-EVAL-20260908-01/label_bundles
```

要求：

- calendar截止2025-12-31；
- 固定3982股票及原fold；
- 不用2026补最后20位置；
- 目标为 `H20_financial_residual_epsilon_future_K1_v1`；
- 历史旧target前缀来自accepted TIMEISO，不冒充独立重建；
- 2018—2020固定5个盲锚点由当前target producer重算。

每个 `target_anchor_checks.json` 必须：

- `passed=true`
- `anchors_checked>=5`
- `support_mismatches=0`
- `max_abs_error<=1e-7`

任一失败：**停止整个任务**，不改容差、不换锚点、不启动score。

## 5. 第三步：建立两个label sidecars

每个clock创建一个spec，例如1430：

```json
{
  "feature_store": "/.../LCL-R3-TRANSFER-INPUT-20260907-01/run01/stores/1430",
  "label_bundle": "/.../LCL-R3-TRANSFER-EVAL-20260908-01/label_bundles/1430",
  "reference_label_store": "/.../LCL-R3-TIMEISO-20260907-01/run01/1430/prepared/store",
  "output_root": "/.../LCL-R3-TRANSFER-EVAL-20260908-01/label_sidecars/1430",
  "label_bundle_sha256": "sha256:<实际bundle.json摘要>",
  "reference_manifest_sha256": "sha256:<原TIMEISO manifest实际摘要>"
}
```

运行：

```bash
python3 scripts/reaka_r3_transfer_evaluate.py --build-label-sidecar /path/to/1430_sidecar_spec.json
python3 scripts/reaka_r3_transfer_evaluate.py --build-label-sidecar /path/to/1445_sidecar_spec.json
```

sidecar会再次完整核对旧2007—2020 `epsilon_future` prefix的有限支持与 `1e-7` 数值容差，然后仅选择2021—2025成熟且有限target坐标。失败则停止，不评分。

## 6. 第四步：正式run spec

示例：

```json
{
  "schema_id": "factorlab.r3_transfer_evaluation_run@1.0",
  "output_root": "/.../LCL-R3-TRANSFER-EVAL-20260908-01/run01",
  "timeiso_root": "/.../LCL-R3-TIMEISO-20260907-01/run01",
  "xfine_root": "/.../LCL-R3-XFINE-20260907-01/run01",
  "transfer_feature_root": "/.../LCL-R3-TRANSFER-INPUT-20260907-01/run01",
  "repo_root": "/path/to/factorlab-multifactor-stock-lab",
  "factorlab_root": "/path/to/factor_lab",
  "accepted_environment": "/.../LCL-R3-TIMEISO-20260907-01/run01/environment.json",
  "label_sidecars": {
    "1430": "/.../LCL-R3-TRANSFER-EVAL-20260908-01/label_sidecars/1430",
    "1445": "/.../LCL-R3-TRANSFER-EVAL-20260908-01/label_sidecars/1445"
  }
}
```

如TIMEISO实际environment文件在另一个accepted路径，必须用原验收使用的实际文件，不重新生成一个“看起来相同”的环境JSON。

正式运行：

```bash
python3 scripts/reaka_r3_transfer_evaluate.py --run /path/to/transfer_eval_run_spec.json
```

CLI先自动执行read-only archived-score preflight：24组旧模型各重放最多64个旧score坐标。必须全部row一致且max abs error <= `1e-7`。该preflight新期score=0、target读取=0。任一失败停止。

preflight通过后才启动：

`2 clocks × 3 seeds × 4 arms = 24 fresh-process score jobs`

worker spec中没有label/target路径。必须全部完成后，主进程才打开sidecar评价。

## 7. 固定评价口径

只评价：

- `F − STATE_VALUE_PLUS_E`
- `BETA_RELIABILITY − BETA_ONLY`

seed ensemble：每日每seed截面rank-z后3seed等权。

主统计：同一天两时钟contrast等权，再跨日期平均daily H20金融残差RankIC。

报告：

- two clocks；
- six clock×seed切片；
- 2021、2022、2023、2024、2025全部年份；
- phase 0/1/2/3；
- block 4/8/12；
- residual decile spread和Top30-minus-universe secondary。

负年份、负seed、负phase必须原样保留。secondary不能救失败primary。不允许看结果后追加seed、年份或其他arm。

## 8. 失败与重试规则

- target anchor / prefix / identity / environment / archived-score preflight失败：停止，不评分；
- 正式run部分score已生成后失败：保留失败目录和已生成receipt，不在同一output root猜测resume；修复工程错误时另建新root，并在反馈中逐项说明旧root执行到哪里；
- 不因RankIC结果弱/负而重跑。

## 9. 回传小产物

提交：

`cloud_results/local_handoff_R3_transfer_eval_20260908/`

至少包含：

1. `local_feedback.md`
2. targeted test log/JUnit
3. label bridge `result.json`
4. 两时钟 `bundle.json`
5. 两时钟 `target_anchor_checks.json`
6. 两时钟 `producer_sources.json`
7. 两个sidecar `manifest.json`
8. formal run spec
9. 24个 `score_receipt.json`
10. 顶层 `result.json`
11. 两时钟 `result.json`
12. 两时钟 `paired_daily.csv`
13. 两时钟 `per_seed.csv`
14. `combined_result.json`
15. `combined_daily.csv`
16. 如失败，首次失败日志和失败root说明

大 `scores.npz`、label矩阵、feature arrays、checkpoint留本地。

反馈明确：实际主题仓HEAD、FactorLab HEAD、实际环境、label source identity、命令/exit code、target anchors、finite evaluation rows/days、24/24 score receipt、0 new fits、是否发生工程重试及其原因、所有未知。

## 10. 证据边界

即使两项primary都很强，也仍为：

- consumed 2021—2025 historical transfer；
- `fresh_oos=false`
- `PIT_certified=false`
- `production_authority=false`

不得升级成账户alpha、总收益、可交易生产结论或唯一因果特征归因。

完成后停止，由云端验收，不自行进入下一研究阶段。
