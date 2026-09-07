# 云端—本地沟通：LCL-R3-XFINE-20260907-01

**状态**：本地已反馈；待云端复核。Stage A `LCL-R3-XCOARSE-20260907-01` 已由云端验收通过。本任务只执行此前预注册的 Stage B 三个细拆 arm；月度 F+M 仍禁止。本地回传见 `cloud_results/local_handoff_R3_xfine_20260907/local_feedback.md`。

> **最终执行门槛以 [`r3_xfine_execution_gate_20260907.md`](r3_xfine_execution_gate_20260907.md) 为准。** 本文件保留任务目标与回传约定；如果旧命令与 gate 冲突，使用 gate。

## 1. 研究目标

在 accepted H → E → F 粗分解内继续做预注册 nested ordered contrasts：

### state side

- `STATE_VALUE_PLUS_E = 0:14 + 28:70`
- `STATE_VALUE_PLUS_E − E`: state values 条件增量
- `F − STATE_VALUE_PLUS_E`: state availability 条件增量

两者逐日闭合到 accepted `F−E`。

### exposure side

- `BETA_ONLY = 28:42`
- `BETA_RELIABILITY = 28:56`
- accepted `E = 28:70`

依次报告：

- `BETA_ONLY − H`
- `BETA_RELIABILITY − BETA_ONLY`
- `E − BETA_RELIABILITY`

三者逐日闭合到 accepted `E−H`。

这些都是预注册嵌套有序差值，不是唯一因果贡献份额。

## 2. 冻结预算

- clocks: `1430`, `1445`
- seeds: `11`, `29`, `47`
- new arms: `STATE_VALUE_PLUS_E`, `BETA_ONLY`, `BETA_RELIABILITY`
- new fits: **18 exactly**
- max cycles per fit: **3**
- max total cycles: **54**
- F / E / H refits: **0 / 0 / 0**
- CPU only
- same 2018–2020 consumed support
- no new years / seeds / cycles / K / arms / residual network
- no result-driven rerun

## 3. 云端开发完成内容

当前开发分支已实现：

- `src/factor_lab/factor_rotation/reaka_r3_x_fine_runner.py`
- `src/factor_lab/factor_rotation/reaka_r3_x_fine_preflight.py`
- `scripts/reaka_r3_x_fine_compare.py`
- `tests/unit/test_reaka_r3_x_fine_runner.py`
- `tests/unit/test_reaka_r3_x_fine_preflight.py`
- `tests/unit/test_reaka_r3_x_fine_cli.py`

并强化：

1. accepted E 逐 seed receipt/checkpoint/reload identity；
2. F/E/H 同支持与 XCOARSE `F−E/E−H/F−H` 逐日重建；
3. 新 arm 的 same pre-DMD state、own DMD、own optimizer；
4. exactly 3 cycles，按 minimum canonical fit-prefix loss 选 checkpoint，平手取最早；
5. checkpoint 保存后 fresh Python process reload；
6. fine runner / preflight / upstream decomposition/coarse runner 源码 blob 冻结；
7. 每次 fresh reload 也重新验证冻结 fine source；
8. **全时钟、6个 reference seed pair 的 zero-fit / zero-inference preflight 必须在任何新 fit 前完成**；
9. 主指标仍为 daily H20 financial residual RankIC；
10. 在结果产生前已冻结 residual decile-spread 和 Top30-minus-universe 二级指标；secondary 不得救活失败的 primary。

云端容器不含用户 FactorLab checkout，且实际 `git clone` 尝试因 `Could not resolve host: github.com` 失败，因此没有把当前最终代码说成已在云端完成仓库 pytest。真实 targeted tests 必须在本地通过后才训练。云端开发范围记录在：

`cloud_results/r3_x_fine_development_20260907/execution_receipt.json`

## 4. 本地执行顺序——不得跳步

### 4.1 先跑五个 targeted test modules

```bash
python -m pytest -q \
  tests/unit/test_reaka_r3_x_decomposition.py \
  tests/unit/test_reaka_r3_x_coarse_runner.py \
  tests/unit/test_reaka_r3_x_fine_runner.py \
  tests/unit/test_reaka_r3_x_fine_preflight.py \
  tests/unit/test_reaka_r3_x_fine_cli.py
```

必须 exit 0。失败则停止，不启动真实 fit。

### 4.2 创建 run spec

```json
{
  "schema_id": "factorlab.r3_x_fine_run_spec@1.0",
  "accepted_timeiso_run_root": "/path/to/FactorLab/tmp/LCL-R3-TIMEISO-20260907-01/run01",
  "accepted_xcoarse_run_root": "/path/to/FactorLab/tmp/LCL-R3-XCOARSE-20260907-01/run01",
  "output_root": "/path/to/FactorLab/tmp/LCL-R3-XFINE-20260907-01/run01",
  "expected_factorlab_commit": "b39bb12f43a46b165d18db93191a669234077444"
}
```

### 4.3 单独跑 read-only preflight

```bash
export FACTORLAB_ROOT="/path/to/factor_lab"
python scripts/reaka_r3_x_fine_compare.py \
  --spec /path/to/x_fine_run_spec.json \
  --preflight-only
```

必须满足：

- `status=passed_read_only_reference_preflight`
- `reference_seed_pairs_checked=6`
- `new_fits=0`
- `new_inference=0`
- 两时钟 XCOARSE 逐日重建均通过

preflight 失败则停止。

### 4.4 最后才运行18 fits

```bash
python scripts/reaka_r3_x_fine_compare.py \
  --spec /path/to/x_fine_run_spec.json
```

正式命令还会再次跑同一 preflight，然后才进入训练。

## 5. 回传小产物

提交到：

`cloud_results/local_handoff_R3_xfine_20260907/`

至少回传：

1. `local_feedback.md`
2. `run_spec.json`
3. preflight receipt / 小型复制
4. targeted test log
5. 顶层 `result.json`
6. `runtime_identity.json`
7. 两时钟 `result.json`
8. 两时钟 `paired_daily.csv`
9. 两时钟 `per_seed.csv`
10. 18 个新 arm `fit_receipt.json`
11. 18 个 checkpoint `manifest.json`
12. 18 个 `reload_spec.json`
13. 首次失败日志（如有）

大 scores/checkpoint/store 保持本地。

反馈必须明确：实际主题仓 HEAD、FactorLab HEAD、测试命令和退出码、preflight 命令和退出码、正式命令和退出码、新 fits/cycles、是否发生失败后修代码、是否有任何结果驱动重跑。

## 6. 月度 CloudRidge 继续阻断

`formula_identity_not_found=true` 仍成立。没有恢复精确 S_obs / 1σ 公式、估计窗口、方向编码、availability 与 missing rule。

因此：

- 不运行 F+M；
- 不猜公式；
- 不把 Stage-B 结果写成月度条件证据。

## 7. 证据边界

Stage B 仍属于 consumed 2018–2020 的 nested ordered contrasts：

- `fresh_oos=false`
- `full_pit_certified=false`
- `production_authority=false`
- 非 unique causal attribution
- 非股票总收益/账户 alpha
