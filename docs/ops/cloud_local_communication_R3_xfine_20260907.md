# 云端—本地沟通：LCL-R3-XFINE-20260907-01

**状态**：待本地执行。Stage A `LCL-R3-XCOARSE-20260907-01` 已由云端验收通过；本任务只执行此前预注册的 Stage B 三个细拆 arm。不得运行月度 F+M。

## 1. 研究目标

在 accepted H → E → F 粗分解之内继续做嵌套有序拆分：

### state side

- `STATE_VALUE_PLUS_E`: 保留 `0:14` state values 与 `28:70` E 包，去掉 `14:28` state availability。
- `STATE_VALUE_PLUS_E − E`: state values 在 E 之上的有序条件增量。
- `F − STATE_VALUE_PLUS_E`: state availability 在 state values + E 之上的有序条件增量。

两者算术闭合到 accepted `F−E`，但不是唯一因果贡献。

### exposure side

- `BETA_ONLY`: 只保留 `28:42` exposure values。
- `BETA_RELIABILITY`: 保留 `28:56` exposure values + reliability。
- accepted `E`: `28:70` exposure values + reliability + exposure availability。

有序对比：

- `BETA_ONLY − H`: exposure values 在 history-only 之上的增量；
- `BETA_RELIABILITY − BETA_ONLY`: reliability 在 exposure values 之上的增量；
- `E − BETA_RELIABILITY`: exposure availability 在前两者之上的增量。

三者算术闭合到 accepted `E−H`，仍不是唯一因果贡献。

## 2. 为什么现在授权 Stage B

Stage A 云端验收显示：

- combined `F−E = +0.011258802580991234`，block 4/8/12 区间均为正；
- combined `E−H = +0.009278021839895956`，但 block 4/8/12 区间均跨 0；
- 所以 state 包已有较稳定增量，需要区分 value 与 mask；exposure 包虽均值为正但稳定性较弱，更需要区分 value/reliability/mask 谁在贡献或抵消。

本任务使用的是**此前已冻结的三个 fine arms**，不是看完粗结果后新发明的有利消融。

## 3. 代码入口

开发分支：`codex/reaka-foundation-audit-20260905`

- `src/factor_lab/factor_rotation/reaka_r3_x_decomposition.py`
- `src/factor_lab/factor_rotation/reaka_r3_x_fine_runner.py`
- `scripts/reaka_r3_x_fine_compare.py`
- `tests/unit/test_reaka_r3_x_fine_runner.py`

本轮云端通过 connector 完成代码发布与人工边界审查，但没有本地 FactorLab checkout，因此**未声称已在云端执行新增 fine-runner 单元测试**。本地必须先跑 targeted tests；若失败，不进入18次拟合。

## 4. 冻结预算

只新增：

- `STATE_VALUE_PLUS_E`
- `BETA_ONLY`
- `BETA_RELIABILITY`

固定：

- clocks: `1430`, `1445`
- seeds: `11, 29, 47`
- new fits: **18 exactly**
- max cycles per fit: **3**
- max total new cycles: **54**
- reference F new fits: 0
- reference E new fits: 0
- reference H new fits: 0
- CPU only，环境必须与 accepted TIMEISO / XCOARSE 稳定环境一致
- 每个新 arm 自己 DMD、自己 optimizer
- 每个新 arm 同 seed/clock pre-DMD digest 必须等于 accepted F/H 的 digest
- 每个 checkpoint 保存后必须通过 fresh Python process `--reload-fine-worker` 评分
- 不读取 future target 进行 fit/checkpoint selection
- 不因任何 contrast 负/弱而增 seed、增 cycle、换顺序、换 arm 或重跑到转正

## 5. 执行前必须重建 Stage A

fine runner 会先复用：

- TIMEISO F/H scores
- XCOARSE E scores

然后逐时钟重建：

- `F−E`
- `E−H`
- `F−H`

必须逐日与 accepted XCOARSE `paired_daily.csv` 一致，否则停止，不允许细拆。

## 6. run spec

例如：

```json
{
  "schema_id": "factorlab.r3_x_fine_run_spec@1.0",
  "accepted_timeiso_run_root": "/path/to/FactorLab/tmp/LCL-R3-TIMEISO-20260907-01/run01",
  "accepted_xcoarse_run_root": "/path/to/FactorLab/tmp/LCL-R3-XCOARSE-20260907-01/run01",
  "output_root": "/path/to/FactorLab/tmp/LCL-R3-XFINE-20260907-01/run01",
  "expected_factorlab_commit": "b39bb12f43a46b165d18db93191a669234077444"
}
```

先测试：

```bash
python -m pytest -q \
  tests/unit/test_reaka_r3_x_decomposition.py \
  tests/unit/test_reaka_r3_x_coarse_runner.py \
  tests/unit/test_reaka_r3_x_fine_runner.py
```

再运行：

```bash
export FACTORLAB_ROOT="/path/to/factor_lab"
python scripts/reaka_r3_x_fine_compare.py --spec /path/to/x_fine_run_spec.json
```

## 7. 回传小产物

大 checkpoint / scores.npz 留本地。提交：

`cloud_results/local_handoff_R3_xfine_20260907/`

至少：

1. `local_feedback.md`
2. `result.json`
3. `runtime_identity.json`
4. 两时钟 `result.json`
5. 两时钟 `paired_daily.csv`
6. 两时钟 `per_seed.csv`
7. 18 个新 arm `fit_receipt.json`
8. 18 个 checkpoint `manifest.json`
9. 18 个 `reload_spec.json`
10. targeted test log
11. 首次失败日志（如有）

反馈明确实际主题仓 HEAD、FactorLab HEAD、测试命令/退出码、正式命令/退出码、新 fits/cycles、是否发生失败后修代码、是否重跑数值结果。

## 8. 月度 CloudRidge 继续阻断

本地与云端历史上下文都没有恢复精确 `S_obs / 1σ` 公式；`formula_identity_not_found` 仍成立。

因此：

- 不运行 F+M；
- 不根据名称猜公式；
- 不把 fine split 结果当作月度条件证据。

## 9. 证据边界

Stage B 仍只是 consumed 2018–2020 的 nested ordered contrasts。不得解释成 unique causal attribution、fresh OOS、full PIT、tradability、total return/account alpha 或 production authority。

`fresh_oos=false`、`full_pit_certified=false`、`production_authority=false` 保持。
