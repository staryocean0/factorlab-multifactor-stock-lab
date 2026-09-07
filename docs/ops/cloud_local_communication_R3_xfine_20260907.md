# 云端—本地沟通：LCL-R3-XFINE-20260907-01

**状态**：云端已复核，任务 `completed_with_limits`。Stage A `LCL-R3-XCOARSE-20260907-01` 已验收；Stage B 三个预注册细拆 arm 已完成并验收。月度 F+M 仍禁止。最终裁决见 `cloud_results/local_handoff_R3_xfine_20260907/cloud_acceptance/cloud_review.md`。

> **最终执行门槛以 [`r3_xfine_execution_gate_20260907.md`](r3_xfine_execution_gate_20260907.md) 为准。** 本文件保留任务目标、执行记录与云端验收；历史命令如与 gate 冲突，以 gate 为准。

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

冻结执行基点 `32b449b5603e034d5dad660cd7fdfdc3117481be` 已实现：

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
10. 在结果产生前冻结 residual decile-spread 和 Top30-minus-universe 二级指标；secondary 不得救活失败的 primary。

云端开发阶段没有用户 FactorLab checkout，不能把完整仓库 pytest 冒充云端通过；真实 targeted tests、preflight 与18 fits 均由本地按 gate 执行。

## 4. 本地实际执行（2026-09-07）

本地结果提交：`b8a2c30af3ac2384823fa641bfd537cffb9d20e2`。相对冻结执行基点恰好 ahead 1 commit，只新增结果/receipt/manifest/reload-spec/test log，并更新本任务状态；没有修改 Stage-B runner/CLI/数值源码。

### 4.1 Targeted tests

```bash
python3 -m pytest -q \
  tests/unit/test_reaka_r3_x_decomposition.py \
  tests/unit/test_reaka_r3_x_coarse_runner.py \
  tests/unit/test_reaka_r3_x_fine_runner.py \
  tests/unit/test_reaka_r3_x_fine_preflight.py \
  tests/unit/test_reaka_r3_x_fine_cli.py
```

结果：49 passed / 0 failed / 0 errors / 0 skipped，exit 0。

### 4.2 Zero-fit preflight

`--preflight-only` exit 0：

- `status=passed_read_only_reference_preflight`
- `reference_seed_pairs_checked=6`
- 1430/1445 均为 142 paired days
- XCOARSE `F−E/E−H/F−H` 两时钟逐日重建通过
- `new_fits=0`
- `new_inference=0`
- `future_result_peeking=false`

### 4.3 正式运行

正式命令再次执行同一 preflight 后进入训练，exit 0：

- new fits = 18
- F/E/H refits = 0/0/0
- 每 fit 3 cycles 上限；checkpoint selection 通过 minimum canonical loss / earliest tie gate
- 18/18 `future_target_values_read=0`
- 18/18 checkpoint manifest 与 fresh-process reload spec 回传
- 未增加 seed/cycle/K/arm，未做结果驱动重跑
- 未运行 F+M
- 未调用 Actions

## 5. 云端最终验收结果

云端读取本地回传、比较冻结基点与结果提交、复核测试/preflight/formal receipt、逐 seed 小表、两时钟/combined 汇总，并执行 47 项小证据结构/算术检查，47/47 通过。云端没有重跑本地大数组的18次训练，也没有重哈希本地大 checkpoint/scores.npz；该限制已写入验收报告。

### 5.1 Combined primary RankIC

| contrast | mean | median | wins/losses | block8 |
|---|---:|---:|---:|---|
| `STATE_VALUE_PLUS_E − E` | +0.0008633 | -0.0009710 | 67 / 75 | [-0.00736, +0.00920] |
| `F − STATE_VALUE_PLUS_E` | **+0.0103955** | +0.0098382 | **95 / 47** | **[+0.00481, +0.01730]** |
| `BETA_ONLY − H` | +0.0055073 | +0.0023012 | 78 / 64 | [-0.00869, +0.01963] |
| `BETA_RELIABILITY − BETA_ONLY` | **+0.0056343** | +0.0043558 | **87 / 55** | **[+0.00045, +0.01112]** |
| `E − BETA_RELIABILITY` | **-0.0018636** | -0.0024104 | 58 / 84 | [-0.00485, +0.00052] |

粗分解继续精确闭合：

- `F−E = +0.011258802580991234`
- `E−H = +0.009278021839895956`
- `F−H = +0.020536824420887195`

RankIC、decile spread、Top30 三套 nested contrasts 的云端独立算术闭合误差均在约 `1.2e-17` 以内。

### 5.2 当前科学解释

- **state values 自身没有建立稳定增量**：combined 近0、median负、block 4/8/12 跨0，per-seed 3正/3负；
- **state availability/mask 是 state 侧最稳定的正增量**：combined `+0.01040`，block 4/8/12 均为正；6/6 seed 为正；两时钟×三年度和×四phase 的 ensemble mean 全部为正；
- exposure values (`BETA_ONLY−H`) 为正点估计，但 block 区间跨0；
- **reliability 是 exposure 侧最稳定的正 ordered increment**：combined `+0.00563`，block 4/8/12 均为正；两时钟×三年度和×四phase 的 ensemble mean 全部为正，但 per-seed 4正/2负，所以不能说每个seed都支持；
- exposure availability (`E−BETA_RELIABILITY`) 没有建立正主 RankIC 增量，combined point estimate 为 `-0.00186`；所有两时钟×四phase 均为负，2018/2019 两时钟也为负，2020 两时钟转正；因此不能宣称普遍有害；
- secondary 不能改变主裁决，例如 exposure availability 的 Top30 combined 为正，但主 RankIC 为负，仍判“未建立正主增量”。

这些仍是路径依赖 nested ordered contrasts，不能转换为唯一因果特征重要性或百分比贡献。

完整云端验收：

- `cloud_results/local_handoff_R3_xfine_20260907/cloud_acceptance/cloud_review.md`
- `cloud_results/local_handoff_R3_xfine_20260907/cloud_acceptance/cloud_checks.json`

本任务不再需要本地补件、重训或重推理。

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

任务状态：`completed_with_limits`。
