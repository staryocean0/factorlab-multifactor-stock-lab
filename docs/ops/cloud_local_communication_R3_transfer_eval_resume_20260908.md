# LCL-R3-TRANSFER-EVAL-20260908-01：在entry-open target验收后恢复评分

状态：**本地已反馈（2026-09-08）。** sidecar v1.1 两时钟通过；archived-score preflight 在 1445/29/BETA_ONLY 以 maxdiff≈1.788e-7 停止；24 个新期 score 未启动。见 [resume_v11/local_feedback.md](../../cloud_results/local_handoff_R3_transfer_eval_20260908/resume_v11/local_feedback.md)。本地不代填云端已复核。

## 1. 已完成且不要重复

- 2021–2025 feature store已验收；
- target-lineage已定位并关闭：旧future raw定义为`entry_open[t+20]/entry_open[t]-1`；
- `LCL-R3-TRANSFER-TARGET-ENTRYOPEN-20260908-01`已完成，两时钟DataHub→旧P6 target锚点maxdiff=0；
- successor label bundle v1.1两时钟→accepted TIMEISO epsilon_future锚点maxdiff=0；
- target/label不重建，不改容差、不换锚点；
- 旧错误label bridge保留为历史反例，不再运行。

验收报告：`cloud_results/local_handoff_R3_transfer_target_entryopen_20260908/cloud_acceptance/cloud_review.md`。

## 2. 第一道门：sidecar adapter工程测试

新增：

- `scripts/reaka_r3_transfer_sidecar_v1_1.py`
- `tests/unit/test_reaka_r3_transfer_sidecar_v1_1.py`

运行：

```bash
python3 -m pytest -q \
  tests/unit/test_reaka_r3_transfer_sidecar_v1_1.py \
  tests/unit/test_reaka_r3_transfer_evaluation.py \
  tests/unit/test_reaka_r3_transfer_score_preflight.py
```

必须exit 0。新增adapter严格拒绝旧@1.0 label bundle，要求：

- bundle schema `factorlab.r3_transfer_label_bundle@1.1`；
- raw future=`entry_open_t_plus_20_div_entry_open_t_minus_1`；
- target source task=`LCL-R3-TRANSFER-TARGET-ENTRYOPEN-20260908-01`；
- structural anchor schema `@1.1`；
- 5个结构成熟锚点，support mismatch=0，max error<=1e-7。

adapter只做metadata schema兼容；target arrays通过symlink保持原字节不变，随后复用原sidecar的完整symbol/fold/calendar/historical-prefix/maturity/finite-target检查。

失败则停止，不退回旧@1.0，不改bundle metadata制造通过。

## 3. 建立两时钟sidecar

以本地实际路径和摘要创建两个spec。示意1430：

```json
{
  "feature_store": "/.../LCL-R3-TRANSFER-INPUT-20260907-01/run01/stores/1430",
  "label_bundle": "/.../LCL-R3-TRANSFER-TARGET-ENTRYOPEN-20260908-01/label_bundles_v11/1430",
  "reference_label_store": "/.../LCL-R3-TIMEISO-20260907-01/run01/1430/prepared/store",
  "output_root": "/.../LCL-R3-TRANSFER-EVAL-20260908-01/label_sidecars_v11/1430",
  "label_bundle_sha256": "sha256:<本地v1.1 bundle.json实际SHA>",
  "reference_manifest_sha256": "sha256:<accepted TIMEISO manifest实际SHA>"
}
```

运行：

```bash
python3 scripts/reaka_r3_transfer_sidecar_v1_1.py --spec /path/to/1430.json
python3 scripts/reaka_r3_transfer_sidecar_v1_1.py --spec /path/to/1445.json
```

要求两边成功，且sidecar `manifest.json`：

- status=`prepared_postscore_labels_not_model_input`；
- prefix_check passed；
- years仅2021–2025；
- `uses_2026_to_complete_2025=false`；
- `labels_available_to_score_worker=false`。

额外`label_source_binding_v1_1.json`必须绑定真实@1.1 bundle SHA、entry-open target-source SHA，并声明target array未重写。

## 4. archived-score preflight + 24 score jobs

sidecar两时钟均通过后，沿原正式run spec恢复：

```bash
python3 scripts/reaka_r3_transfer_evaluate.py --run /path/to/transfer_eval_run_spec.json
```

run spec的`label_sidecars`改为上一步`label_sidecars_v11/{1430,1445}`。

CLI必须先自动运行read-only archived-score preflight：

- 2 clocks × 3 seeds × 4 arms = 24组；
- 每组最多64个旧score坐标重放；
- row identity一致；
- max abs error <=1e-7；
- target读取=0；
- 新期score=0。

任一失败停止，不启动新期score。

通过后才运行恰好24个fresh-process score jobs。每个worker spec没有label/target路径，`target_values_read=0`、new fits=0。不得增删arm、seed、年份或换checkpoint/normalizer。

## 5. 固定评价

只评价：

- `F − STATE_VALUE_PLUS_E`（继续解释为state-mask algorithm-path transfer，不是动态mask信号）；
- `BETA_RELIABILITY − BETA_ONLY`。

主统计：每日每seed截面rank-z后三seed等权；同日两时钟contrast等权；再跨日期平均H20 financial residual RankIC。

必须报告2021–2025逐年、6个clock×seed、phase 0–3、moving block 4/8/12及decile/Top30 secondary。负结果原样保留，secondary不能救primary。

## 6. 预算与停止规则

- new model fit=0
- checkpoint selection=0
- normalizer refit=0
- DMD reinit=0
- score jobs恰好24
- 2026 target=0
- Actions=0
- 账户=0
- CloudRidge月度=0

工程失败用新output root重试并完整披露；不得因RankIC弱/负而重跑。

回传沿原目录`cloud_results/local_handoff_R3_transfer_eval_20260908/`追加，不覆盖先前target-anchor失败证据。大score、sidecar target数组留本地。

即使成功，身份仍是consumed 2021–2025 historical transfer：`fresh_oos=false`、`PIT_certified=false`、`production_authority=false`。

## 7. 本地反馈（2026-09-08）

sidecar adapter 测试 23 passed；两时钟 sidecar 构建成功，prefix maxdiff=0，years=2021–2025，2026=false。正式 `--run` 在 archived-score preflight 失败：`1445/29/BETA_ONLY` max abs error≈1.788e-7。只读补扫描 24 组旧分数有 4 组略超 1e-7，全部在 1445。未启动 24 个新期 score，未改容差。等待云端裁决。
