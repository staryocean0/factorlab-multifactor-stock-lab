# R3 transfer-eval resume 云端复核

日期：2026-09-08。任务：`LCL-R3-TRANSFER-EVAL-20260908-01`。
本地回传提交：`58d19ffb97bc704f5f04869961538b27d773a527`。
本地执行基点：`8b5800c8450a9d9324f74916ab2db220b77d501e`。

## 裁决

**本地停止正确；sidecar阶段受限接收，24项新期score尚未放行。** 当前状态：`sidecars_accepted_archived_score_preflight_delta_required`。

本轮不是预测结果验收：新期score=0、RankIC评价=0、new model fit=0、checkpoint selection=0、2026 target=false。不得将preflight停止写成策略失败或通过。

## 1. 已接受的sidecar阶段

本地23项 targeted tests 全部通过。两时钟v1.1 sidecar均为 `prepared_postscore_labels_not_model_input`：

- 旧TIMEISO target prefix比较 5,501,746 个有限格，support mismatch=0、max abs error=0；
- finite evaluation rows=914,934；evaluation days=238；years仅2021–2025；
- `uses_2026_to_complete_2025=false`；
- `labels_available_to_score_worker=false`；
- `target_array_rewritten=false`；
- source binding仍绑定已验收entry-open `label_bundle@1.1` 与同一target-source bundle。

因此不要求重建target、label bundle或sidecar。

## 2. 第一次formal run的缺receipt问题

原TIMEISO模型目录没有单独 `fit_receipt.json`，同schema收据保存在accepted `experiment/result.json -> seed_receipts.F`。本地将其中6个F收据原样物化到本地模型目录后继续preflight；报告声明checkpoint/scores/normalizer/candidate未改，state digest与收据一致，且不是新拟合。

该做法在本次本地运行中可作为工程桥接接受，但不应成为可复现执行器的隐式前置。后续云端会单独让执行器直接支持accepted embedded receipt，避免要求修改accepted run目录；本轮不因此要求重跑模型。

## 3. archived-score停止点的含义

旧preflight固定抽取64个**稀疏坐标**，然后把这64个坐标作为一个新的score batch送入 `score_no_labels`。但历史`scores.npz`是在完整prediction index序列上按FactorLab `BATCH_SIZE`连续批次生成。

因此，旧preflight并没有严格保持历史forward的batch geometry。在CPU float32矩阵计算中，改变batch大小/矩阵形状可以改变GEMM内核或累加顺序，从而产生ULP级舍入差；即便checkpoint、输入行和环境完全一致，也不应把这种不同执行路径下的绝对误差阈值当作严格identity证明。

本地全24组只读扫描显示：

- checkpoint state digest：24/24匹配；
- sampled row identity：24/24匹配；
- 20/24在旧 `1e-7` 规则下通过；
- 4组均仅1个sample超阈值，全部在1445；
- 最大差依次为 `1.1920928955078125e-07`、`1.7881393432617188e-07` 或 `2.384185791015625e-07`；
- 其余样本大多为0，示例失败组64点median=0、mean abs error约2.79e-9。

这些数值与float32 ULP量级相符，但**本报告不据此直接放宽容差，也不把“ULP级”升级成已证明无漂移**。正确下一步是保持 `1e-7` 不变、恢复历史原batch边界后再重放。

## 4. 云端修复原则

`reaka_r3_transfer_score_preflight.py` 后继实现改为：

1. 仍预先固定最多64个archived comparison coordinates；
2. 对每个comparison coordinate，找到它在原archived score序列所属的 `BATCH_SIZE` 连续批次；
3. 每个唯一历史批次按原完整indices顺序重放；
4. 再从这些重放批次里抽取原64个comparison coordinates进行比较；
5. row identity与state digest门保持；
6. **数值门仍为 max abs error <= 1e-7，不修改阈值**；
7. outcome/sidecar/new-period feature仍不进入preflight。

这让preflight检验“同模型、同输入、同batch geometry”是否能重现archived score，而不是比较两个不同batch形状下的float32 forward。

同时新增 `--preflight-only` CLI模式，先让本地单独完成24/24旧score门；只有该门真正通过后，才允许再次运行正式 `--run`。

## 5. 下一本地delta

同一任务ID，不重建sidecar、不重建label、不训练。

顺序：

```bash
python3 -m pytest -q \
  tests/unit/test_reaka_r3_transfer_score_preflight.py \
  tests/unit/test_reaka_r3_transfer_evaluation.py \
  tests/unit/test_reaka_r3_transfer_sidecar_v1_1.py

python3 scripts/reaka_r3_transfer_evaluate.py \
  --preflight-only /path/to/existing_transfer_eval_run_spec.json
```

必须24/24通过且 `max_abs_error<=1e-7`。若仍有任一失败：停止，不评分，回传按batch-context重放后的具体数值。

若24/24通过，再运行原正式：

```bash
python3 scripts/reaka_r3_transfer_evaluate.py \
  --run /path/to/existing_transfer_eval_run_spec.json
```

正式run仍会再次执行同一preflight，然后才允许24个fresh-process score jobs。

## 6. 证据边界

当前只接受sidecar与正确停止；没有2021–2025模型表现结果。

`fresh_oos=false`、`PIT_certified=false`、`production_authority=false`不变。state-mask继续解释为algorithm-path transfer，不是动态mask信号；不得因preflight工程问题改变研究臂、seed、年份、normalizer、checkpoint或primary contrast。
