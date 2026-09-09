# R3 Stage-B Fine X：最终执行门槛

任务：`LCL-R3-XFINE-20260907-01`  
日期：2026-09-07

本文件覆盖此前任务书中任何与 Stage-B 启动顺序冲突的旧文字。科学 arm、seed、年份和预算没有改变；本轮只强化了运行前证据绑定与报告口径。

## 1. 已冻结的 Stage-B arm

只允许新增三类模型：

1. `STATE_VALUE_PLUS_E` = `0:14 + 28:70`
2. `BETA_ONLY` = `28:42`
3. `BETA_RELIABILITY` = `28:56`

只读参考：accepted `F / E / H`。

主 RankIC contrasts：

- `STATE_VALUE_PLUS_E − E`
- `F − STATE_VALUE_PLUS_E`
- `BETA_ONLY − H`
- `BETA_RELIABILITY − BETA_ONLY`
- `E − BETA_RELIABILITY`

前两者逐日算术闭合到 accepted `F−E`；后三者闭合到 accepted `E−H`。闭合是嵌套差值恒等关系，不是唯一因果贡献份额。

## 2. 冻结预算

- clocks = `1430 / 1445`
- seeds = `11 / 29 / 47`
- new arms = 3
- new fits = **18 exactly**
- max cycles per fit = **3**
- max total cycles = **54**
- F refit = 0
- E refit = 0
- H refit = 0
- F+M = 0
- CPU only
- 2018–2020 consumed evaluation support unchanged
- no extra year / seed / cycle / K / arm / residual network
- negative or weak result is accepted; never rerun to turn positive

## 3. 当前冻结源码身份

CLI 在任何 preflight / real fit，以及每个 fresh-process reload 前都会拒绝错误的 Stage-B entrypoint source。

Frozen Git blobs：

- `reaka_r3_x_fine_runner.py` = `c6d6cfc940734c3363dc2b81fda80c2518394e80`
- `reaka_r3_x_fine_preflight.py` = `5c85b72ddd85162f46a2d7da38002fdd151759ed`
- upstream X decomposition = `040182c3f8571083a83d8df3cd852f82dc1f4e48`
- upstream X coarse runner = `5adcfc81dff0a637e0ae21987db02d1c94ba5b9b`

同时继续绑定：

- TIMEISO numerical runner SHA256 = `sha256:ee7036f1925ab61ed88cc96e79a0ee06af9bb2a75812a1a58f4aa2d4a61c3708`
- condition-view SHA256 = `sha256:7d76a03785e2d03623342c63c360ddf7680835433294f5f511163d09fba2f921`
- FactorLab commit = `b39bb12f43a46b165d18db93191a669234077444`

## 4. 先跑 targeted tests，失败则禁止训练

在主题仓最新开发分支执行：

```bash
python -m pytest -q \
  tests/unit/test_reaka_r3_x_decomposition.py \
  tests/unit/test_reaka_r3_x_coarse_runner.py \
  tests/unit/test_reaka_r3_x_fine_runner.py \
  tests/unit/test_reaka_r3_x_fine_preflight.py \
  tests/unit/test_reaka_r3_x_fine_cli.py
```

必须 exit 0。

若失败：

- **不要开始任何 Stage-B fit**；
- 保存测试日志；
- 回传 blocker；
- 不自行修改 arm、数学定义、support 或训练预算来绕过。

## 5. 再单独执行 zero-fit preflight

run spec：

```json
{
  "schema_id": "factorlab.r3_x_fine_run_spec@1.0",
  "accepted_timeiso_run_root": "/path/to/FactorLab/tmp/LCL-R3-TIMEISO-20260907-01/run01",
  "accepted_xcoarse_run_root": "/path/to/FactorLab/tmp/LCL-R3-XCOARSE-20260907-01/run01",
  "output_root": "/path/to/FactorLab/tmp/LCL-R3-XFINE-20260907-01/run01",
  "expected_factorlab_commit": "b39bb12f43a46b165d18db93191a669234077444"
}
```

执行：

```bash
export FACTORLAB_ROOT="/path/to/factor_lab"
python scripts/reaka_r3_x_fine_compare.py \
  --spec /path/to/x_fine_run_spec.json \
  --preflight-only
```

preflight 必须：

- `status = passed_read_only_reference_preflight`
- `reference_seed_pairs_checked = 6`
- 两个 clock 都完成 accepted F/E/H 重建
- accepted E receipt / checkpoint / reload identity 均通过
- accepted XCOARSE `F−E / E−H / F−H` 逐日重建一致
- `new_fits = 0`
- `new_inference = 0`

receipt 会写到 `output_root` 同级的：

`run01.preflight.json`

若 preflight 失败，禁止正式训练。

## 6. preflight 通过后才跑正式18 fits

使用**同一 run spec**：

```bash
python scripts/reaka_r3_x_fine_compare.py \
  --spec /path/to/x_fine_run_spec.json
```

正式命令会再次执行同一 read-only preflight，然后才进入 fit。

每个新 arm / clock / seed：

- same pre-DMD initial-state digest as accepted F/H
- own DMD
- own optimizer
- exactly 3 candidate cycles
- selected checkpoint = minimum canonical fit-prefix loss；平手取最早 cycle
- `future_target_values_read = 0`
- checkpoint persisted
- fresh Python process reload
- reload process itself also checks frozen fine-runner/preflight sources
- no score-coordinate drift

## 7. 预先冻结的评价指标

### Primary

每日截面 H20 financial residual RankIC。

报告每 contrast 的：

- each seed / clock
- ensemble each clock
- combined equal-clock/equal-date
- mean / median / win-loss days
- year 2018/2019/2020
- phase 0/1/2/3
- moving-block 4/8/12 for combined primary contrasts

### Secondary（结果产生前已经冻结）

同一 H20 financial residual target：

1. decile spread
2. Top30 minus same-universe mean

这些只作为形态/集中度辅助诊断。**secondary 不能把一个失败的 primary RankIC contrast“救活”。**

## 8. 回传

主题仓小产物目录：

`cloud_results/local_handoff_R3_xfine_20260907/`

至少：

- `local_feedback.md`
- `run_spec.json`
- `preflight.json` 或原 `run01.preflight.json` 的小型复制/摘要
- targeted test log
- 顶层 `result.json`
- `runtime_identity.json`
- 两时钟 `result.json`
- 两时钟 `paired_daily.csv`
- 两时钟 `per_seed.csv`
- 18个 fit receipts
- 18个 checkpoint manifests
- 18个 reload specs
- 若出现失败，首次失败日志必须保留

大 scores/checkpoint/store 保持本地。

## 9. 月度 CloudRidge 仍未授权

当前 `formula_identity_not_found=true`。没有恢复 S_obs / 1σ 的精确定义、估计窗口、方向编码、availability 和 missing rule。

因此 Stage B 完成前后都不得自行运行 F+M，也不得根据名称猜公式。

## 10. 证据边界

即使五个 fine contrasts 全部为正，也仍然是 consumed 2018–2020 上的**预注册嵌套有序差值**，不是 unique causal attribution。

保持：

- `fresh_oos=false`
- `full_pit_certified=false`
- `production_authority=false`
- 非总收益/非账户 alpha
