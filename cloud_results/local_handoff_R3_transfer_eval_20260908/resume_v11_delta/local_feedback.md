# LCL-R3-TRANSFER-EVAL-20260908-01 batch-context delta 本地反馈

任务：`LCL-R3-TRANSFER-EVAL-20260908-01` archived-score batch-context delta  
状态：**本地已完成。batch-context preflight 24/24 通过；正式 run 24/24 score jobs 完成。**  
时间：2026-09-08 16:26–16:47 Asia/Shanghai  
执行方：本地大模型，主题仓 `factorlab-multifactor-stock-lab` 分支 `codex/reaka-foundation-audit-20260905`

未覆盖先前 target-anchor 失败或 resume_v11 preflight 失败证据。未重建 sidecar / label / target。

## 身份

- 主题仓 HEAD：`ec714cfda9ced07ca36582e7138b5ed4c1a851c4`
- FactorLab HEAD：`b39bb12f43a46b165d18db93191a669234077444`
- 环境与 accepted TIMEISO `environment.json` 一致（Python 3.13.5，numpy 2.2.4，pandas 2.2.3，torch 2.6.0+debian，CPU）
- run spec：既有 `tmp/LCL-R3-TRANSFER-EVAL-20260908-01/specs/transfer_eval_run.json`
- sidecar：既有 `label_sidecars_v11/{1430,1445}`

## 命令与退出码

```bash
python3 -m pytest -q \
  tests/unit/test_reaka_r3_transfer_score_preflight.py \
  tests/unit/test_reaka_r3_transfer_evaluation.py \
  tests/unit/test_reaka_r3_transfer_sidecar_v1_1.py
# exit 0；26 passed / 0 failed / 0 skipped

python3 scripts/reaka_r3_transfer_evaluate.py --preflight-only <existing_run_spec>
# 16:27:01–16:29:28
# {"status": "passed_read_only_checkpoint_score_preflight",
#  "reference_pairs_checked": 24,
#  "archived_batch_geometry_preserved": true,
#  "atol": 1e-07, "new_period_score_jobs": 0}
# exit 0

python3 scripts/reaka_r3_transfer_evaluate.py --run <existing_run_spec>
# 16:34:02–16:47:32
# {"status": "completed_consumed_historical_transfer", "score_jobs": 24, "new_model_fits": 0}
# exit 0
```

ATOL 仍为 1e-7。未改 sample 坐标。未因 RankIC 重跑。

## Preflight

`schema_id=factorlab.r3_transfer_score_preflight@1.1`  
24 组全部 `max_abs_error=0.0`。每组 comparison_rows=64，context_rows=260990，historical_batches=64，batch_size=4096。  
outcome_values_read=0；new_period_score_jobs=0。

## 正式评价（consumed 2021–2025）

24/24 score receipts：`score_rows=931677`，`target_values_read=0`，`label_path_received=false`，`new_model_fits=0`。  
评价行每时钟 914934，238 日。

两时钟等权 combined RankIC：

| contrast | mean | median | win/loss | block4 CI | block8 CI | block12 CI |
|---|---:|---:|---|---|---|---|
| F − STATE_VALUE_PLUS_E | 0.005308 | 0.006977 | 149/89 | [-0.00333, 0.01381] | [-0.00396, 0.01522] | [-0.00492, 0.01531] |
| BETA_RELIABILITY − BETA_ONLY | 0.006430 | 0.005815 | 153/85 | [0.00326, 0.00957] | [0.00320, 0.01022] | [0.00330, 0.01069] |

逐年 combined：

| year | F−STATE | BETA_REL−BETA_ONLY |
|---|---:|---:|
| 2021 | **-0.006809** | 0.002731 |
| 2022 | 0.005120 | 0.008549 |
| 2023 | 0.016185 | 0.004559 |
| 2024 | 0.007134 | 0.003435 |
| 2025 | 0.004886 | 0.013260 |

phase 0 的 F−STATE 为负（-0.002960）。seed 47 的 F−STATE 两时钟均为负（1430 -0.003700，1445 -0.006478）；1430 seed 47 的 BETA_REL−BETA_ONLY 为负（-0.009389）。负结果原样保留。

secondary：combined decile 0.00100 / 0.00130；Top30 0.00687 / 0.00459。不得用 secondary 救 primary。

F−STATE 的 moving-block 区间含 0；BETA_REL−BETA_ONLY 的 4/8/12 区间均在 0 以上。这不是显著性证明、账户 alpha 或动态 mask 信号。INFOCLOCK 已证明 2018–2020 的 14 个 state-mask 恒为 1，第一项只解释为 state-mask **算法路径**跨期表现。

## 未执行 / 边界

new fit=0；checkpoint selection=0；normalizer refit=0；DMD reinit=0；2026 target=false；Actions=false；账户=否。  
sidecar/label 未重建。大 `scores.npz` 留本地。

`fresh_oos=false`；`PIT_certified=false`；`production_authority=false`。

完成后停止，待云端复核。本地不代填云端已复核。
