# LCL-R3-TRANSFER-EVAL-20260908-01 恢复评分 本地反馈

任务：`LCL-R3-TRANSFER-EVAL-20260908-01`（entry-open 验收后 resume）  
状态：**在 archived-score preflight 停止。24 个新期 score jobs 未启动。**  
时间：2026-09-08 15:57–16:03 Asia/Shanghai  
执行方：本地大模型，主题仓 `factorlab-multifactor-stock-lab` 分支 `codex/reaka-foundation-audit-20260905`

先前 target-anchor 失败证据未覆盖，仍在上级目录。

## 身份

- 主题仓 HEAD（执行时）：`8b5800c8450a9d9324f74916ab2db220b77d501e`
- FactorLab HEAD：`b39bb12f43a46b165d18db93191a669234077444`
- Python/numpy/pandas/torch：与 accepted TIMEISO `environment.json` 一致（3.13.5 / 2.2.4 / 2.2.3 / 2.6.0+debian，CPU，cuda=false）
- v1.1 label bundles：未重建
- 1430 bundle SHA：`sha256:72f023efd4073987176290adcedc749ea8051bc54648e7c912a9bc5dbf39e188`
- 1445 bundle SHA：`sha256:d06d29113e51697f95277e972b1a3ef2e8d2ed9610d30e2b708117e48d3e9faf`

## 已通过

### A. targeted tests

`pytest` sidecar@1.1 + transfer_evaluation + score_preflight：**23 passed / 0 failed / 0 skipped**，exit 0。

### B. 两时钟 sidecar v1.1

两时钟 exit 0。

| 项 | 1430 | 1445 |
|---|---|---|
| status | prepared_postscore_labels_not_model_input | 同左 |
| prefix_check | passed，maxdiff=0，5501746 格 | 同左 |
| years | 2021–2025 | 同左 |
| uses_2026_to_complete_2025 | false | false |
| labels_available_to_score_worker | false | false |
| finite_evaluation_rows | 914934 | 914934 |
| target_array_rewritten | false | false |

未使用旧 @1.0 label bundle。

## 工程补丁（评分前）

第一次 `--run` 在 preflight 因缺少 TIMEISO F `fit_receipt.json` 失败。  
accepted TIMEISO 只把同 schema 收据写在 `experiment/result.json` 的 `seed_receipts.F`，模型目录只有 checkpoint / scores / reload_spec。

本地从该已验收 `seed_receipts` **原样写出** 6 个 F `fit_receipt.json`（2 clocks × 3 seeds）。checkpoint `state_digest` 与收据一致，`future_target_values_read=0`。**未改 checkpoint、scores.npz、normalizer、candidate。** 这不是新拟合。

## 停止点：archived-score preflight

第二次 `--run` 在正式 preflight 失败：

`ValueError: archived score numerical mismatch: 1445/29/BETA_ONLY`

按任务书：**停止，不启动新期 score。未改 1e-7 容差。**

checkpoint 重载 digest 匹配，sampled rows 身份匹配。该组 64 点：

- max abs error = **1.7881393432617188e-07**（略高于 1e-7）
- above 1e-7 = 1
- median = 0

只读扫描全部 24 组旧分数（仍 0 新期 score、0 target 读取）失败 4 组，全部在 1445，全部为 1 个样本略超 1e-7：

| clock/seed/arm | max abs error | above 1e-7 |
|---|---:|---:|
| 1445/29/BETA_ONLY | 1.788e-07 | 1 |
| 1445/29/BETA_RELIABILITY | 1.192e-07 | 1 |
| 1445/47/STATE_VALUE_PLUS_E | 1.192e-07 | 1 |
| 1445/47/BETA_RELIABILITY | 2.384e-07 | 1 |

其余 20 组 passed（多数 maxdiff=0；1430/47/STATE_VALUE_PLUS_E max=5.960e-08 仍 <=1e-7）。  
1430 12/12 通过。1445 的 3 个 F 通过。

## 未执行

- 24 fresh-process score jobs = 0
- 新期 feature 评分 = 0
- 评价 RankIC = 0
- new model fit = 0
- checkpoint selection = 0
- 2026 target = false
- Actions = false
- 账户 / CloudRidge 月度 = 否
- 未放宽 1e-7，未因结果重跑

`fresh_oos=false`；`PIT_certified=false`；`production_authority=false`。

完成后停止，待云端裁决 preflight 容差/重放路径。本地不代填云端已复核。
