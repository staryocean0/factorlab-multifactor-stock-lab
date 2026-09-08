# LCL-R3-TRANSFER-EVAL-20260908-01：archived-score batch-context delta

状态：**本地已反馈（2026-09-08）。** batch-context preflight 24/24 通过（maxdiff=0）；正式 run 24/24 score jobs 完成。见 [resume_v11_delta/local_feedback.md](../../cloud_results/local_handoff_R3_transfer_eval_20260908/resume_v11_delta/local_feedback.md)。本地不代填云端已复核。

云端复核：`cloud_results/local_handoff_R3_transfer_eval_20260908/resume_v11/cloud_review.md`。

## 1. 为什么需要这个delta

旧archived-score preflight抽取64个稀疏坐标后，以新的64-row batch重跑；历史`scores.npz`是在完整prediction序列按FactorLab `BATCH_SIZE`连续批次生成。这样没有保持原forward batch geometry。

本地24组扫描中checkpoint digest与row identity均24/24一致；仅4个1445组合各1个sample超过1e-7，最大差为1.192e-7 / 1.788e-7 / 2.384e-7。云端**不直接放宽1e-7**，而是修复preflight执行路径。

后继 `reaka_r3_transfer_score_preflight.py`：

- comparison coordinates仍最多64个且固定；
- 先恢复每个comparison coordinate所属的原 `BATCH_SIZE` 连续archived batch；
- 整批按原indices顺序score；
- 再抽取64个comparison rows；
- state digest、row identity门不变；
- **ATOL仍为1e-7**；
- outcome、sidecar target、新期features不进入preflight；
- 对TIMEISO F收据可直接只读使用accepted `experiment/result.json -> seed_receipts.F`，不再要求物化缺失的fit_receipt文件。

CLI新增 `--preflight-only`，不会在门通过后自动进入新期score。

## 2. 先跑targeted tests

```bash
python3 -m pytest -q \
  tests/unit/test_reaka_r3_transfer_score_preflight.py \
  tests/unit/test_reaka_r3_transfer_evaluation.py \
  tests/unit/test_reaka_r3_transfer_sidecar_v1_1.py
```

必须exit 0。失败即停止，不评分。

## 3. 单独运行修复后的24组preflight

复用上一轮formal run spec和已经通过的两个sidecar，不重建target/label/sidecar：

```bash
python3 scripts/reaka_r3_transfer_evaluate.py \
  --preflight-only /path/to/existing_transfer_eval_run_spec.json
```

必须输出：

- status=`passed_read_only_checkpoint_score_preflight`
- reference_pairs_checked=24
- `archived_batch_geometry_preserved=true`
- atol=`1e-7`
- new_period_score_jobs=0
- outcome_values_read=0

24组每组必须max abs error <=1e-7。若任一失败，停止并回传该组：comparison rows、context rows、historical batches、batch size、max/mean/median/p99 error、above tolerance、row/state identity。**不得再改容差或换sample坐标。**

## 4. 只有24/24通过后才恢复正式run

```bash
python3 scripts/reaka_r3_transfer_evaluate.py \
  --run /path/to/existing_transfer_eval_run_spec.json
```

正式run会再次执行同一batch-context preflight；通过后才允许恰好24个fresh-process无标签score jobs。

冻结不变：

- clocks 1430/1445
- seeds 11/29/47
- arms F / STATE_VALUE_PLUS_E / BETA_ONLY / BETA_RELIABILITY
- new fit=0
- checkpoint selection=0
- normalizer refit=0
- DMD reinit=0
- 2026 target=0
- Actions=0
- primary只有 `F-STATE_VALUE_PLUS_E` 与 `BETA_RELIABILITY-BETA_ONLY`

不得因最终RankIC弱/负而重跑。

## 5. 回传

沿原目录追加：

`cloud_results/local_handoff_R3_transfer_eval_20260908/resume_v11_delta/`

至少：

1. `local_feedback.md`
2. targeted test log/JUnit
3. `preflight_only.txt`
4. 完整24组preflight小回执JSON
5. 若preflight通过并正式run：24个score_receipt、顶层/两时钟/combined结果及daily/per-seed小表
6. 若失败：首次失败日志和具体pair诊断

已通过的v1.1 sidecar不重建；此前失败证据不覆盖。

证据身份仍为consumed historical transfer：`fresh_oos=false`、`PIT_certified=false`、`production_authority=false`。

## 6. 本地反馈（2026-09-08）

targeted tests 26 passed。`--preflight-only` exit 0，24 组 archived batch-context 重放 max abs error 均为 0，`archived_batch_geometry_preserved=true`，atol=1e-7。随后 `--run` 再次通过同一 preflight 并完成恰好 24 个无标签 score jobs，`status=completed_consumed_historical_transfer`。combined F−STATE mean RankIC≈0.00531（2021 年为负）；BETA_REL−BETA_ONLY≈0.00643。负年份/seed/phase 原样保留。未改容差，未因结果重跑。大 scores 留本地。
