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

## 3. 代码入口与当前云端开发状态

开发分支：`codex/reaka-foundation-audit-20260905`

- `src/factor_lab/factor_rotation/reaka_r3_x_decomposition.py`
- `src/factor_lab/factor_rotation/reaka_r3_x_coarse_runner.py`
- `src/factor_lab/factor_rotation/reaka_r3_x_fine_runner.py`
- `scripts/reaka_r3_x_fine_compare.py`
- `tests/unit/test_reaka_r3_x_fine_runner.py`
- `docs/ops/r3_x_fine_design_20260907.json`
- `cloud_results/r3_x_fine_design_20260907/execution_receipt.json`

云端已经完成：

- Stage-B runner/CLI；
- accepted E 逐 seed receipt/checkpoint/reload identity 守卫；
- XCOARSE coarse contrasts 逐日重建守卫；
- 新 arm 的 fit-row/future-target/minimum-cycle/earliest-tie 守卫；
- 依赖的 `x_decomposition` 与 `x_coarse_runner` Git blob identity 守卫；
- RankIC 主指标；
- 在真实 fine 结果产生前预注册 H20 financial residual decile spread 与 Top30-minus-universe 二级指标；
- 二级指标不能用于“救活”主 RankIC 失败的对比。

云端终端无法解析 GitHub raw 域名，也没有本地 FactorLab checkout，因此**没有声称执行完整仓库 targeted pytest**。云端独立执行了 22 项不依赖真实大数组的隔离数值/identity guard 检查，22/22 通过。真实仓库 targeted tests 仍是本地正式运行前硬门槛。

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
- cycle 选择固定为三轮 canonical fit-prefix loss 的最小值；如数值在 `1e-12` 内并列，选最早 cycle
- 不因任何 contrast 负/弱而增 seed、增 cycle、换顺序、换 arm 或重跑到转正

## 5. 执行前必须验证 accepted E 与重建 Stage A

在任何 Stage-B fit 前，runner 必须验证 accepted XCOARSE E 的：

- arm/seed/clock；
- recipe / selection / normalizer / train rows / prediction rows / pre-DMD / batch-order digests；
- `fit_rows = 361628`；
- `future_target_values_read = 0`；
- selected cycle 确实是三轮最低 canonical loss（并列取最早）；
- checkpoint manifest state digest 与 E receipt 一致；
- reload spec 是同 seed、CPU、输出 `scores.npz`。

随后复用：

- TIMEISO F/H scores
- XCOARSE E scores

并逐时钟重建：

- `F−E`
- `E−H`
- `F−H`

必须逐日与 accepted XCOARSE `paired_daily.csv` 一致，否则停止，不允许细拆。

runner 还会验证当前依赖源码 Git blob：

- `reaka_r3_x_decomposition.py`: `040182c3f8571083a83d8df3cd852f82dc1f4e48`
- `reaka_r3_x_coarse_runner.py`: `5adcfc81dff0a637e0ae21987db02d1c94ba5b9b`

若不一致，不通过“差不多的当前代码”继续跑，先回报云端。

## 6. 冻结评价指标

### 主指标

每日横截面 H20 financial residual RankIC；两个 clock 仍按 equal-date / equal-clock 聚合，报告：

- mean / median / win-loss days；
- 每个 seed；
- 2018 / 2019 / 2020；
- phase 0/1/2/3；
- combined moving-block length 4/8/12。

### 预注册二级指标

使用 TIMEISO reporting delta 已冻结的定义：

1. `decile_spread`
   - stable mergesort 按 score 排序；
   - `count = floor(n/10)`，至少1；
   - `top decile epsilon_future mean - bottom decile epsilon_future mean`。
2. `top30_minus_universe`
   - score 排名前30；
   - `Top30 epsilon_future mean - 当日同一评价 universe epsilon_future mean`。

它们仍是 **H20 financial residual**，不是总收益或账户收益。

二级指标按相同 nested contrasts 报告，并要求算术闭合到 `F−E` / `E−H`。**如果一个主 RankIC contrast 为弱/负，不能用 secondary 正值把它改判为主证据成立。**

## 7. run spec

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

**只有退出码 0 才允许执行真实 18 fits。**若测试失败，停止并提交失败日志；不得一边修测试一边保留已经看过的市场结果。若任何真实 fit 已经开始后才发现实现错误，必须明确回报污染范围，由云端决定是否可以无结果窥视地重启。

再运行：

```bash
export FACTORLAB_ROOT="/path/to/factor_lab"
python scripts/reaka_r3_x_fine_compare.py --spec /path/to/x_fine_run_spec.json
```

## 8. 回传小产物

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

反馈明确实际主题仓 HEAD、FactorLab HEAD、测试命令/退出码、正式命令/退出码、新 fits/cycles、是否发生失败后修代码、是否重跑数值结果，以及三项 secondary 是否只作为预注册二级报告使用。

## 9. 月度 CloudRidge 继续阻断

本地与云端历史上下文都没有恢复精确 `S_obs / 1σ` 公式；`formula_identity_not_found` 仍成立。

因此：

- 不运行 F+M；
- 不根据名称猜公式；
- 不把 fine split 结果当作月度条件证据。

## 10. 证据边界

Stage B 仍只是 consumed 2018–2020 的 nested ordered contrasts。不得解释成 unique causal attribution、fresh OOS、full PIT、tradability、total return/account alpha 或 production authority。

`fresh_oos=false`、`full_pit_certified=false`、`production_authority=false` 保持。
