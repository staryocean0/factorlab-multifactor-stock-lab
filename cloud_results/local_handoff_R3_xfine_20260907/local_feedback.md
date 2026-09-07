# LCL-R3-XFINE-20260907-01 本地反馈

任务：`LCL-R3-XFINE-20260907-01`  
执行方：本地 Codex controller  
时间：2026-09-07  
状态：本地已反馈；待云端复核。

## 身份与命令

- 主题仓执行时 HEAD：`32b449b5603e034d5dad660cd7fdfdc3117481be`
- FactorLab HEAD：`b39bb12f43a46b165d18db93191a669234077444`（未改数值源码）
- TIMEISO 原 run：`tmp/LCL-R3-TIMEISO-20260907-01/run01`（只读，未覆盖 scores/store/checkpoint）
- 实际 `accepted_timeiso_run_root`：`tmp/LCL-R3-XCOARSE-20260907-01/accepted_view`  
  原因：原 TIMEISO 模型目录没有 `fit_receipt.json`，Stage-B identity gate 需要它；该 overlay 是 XCOARSE 已验收的只读视图，scores/store/checkpoint 仍指向原 TIMEISO。
- 实际 `accepted_xcoarse_run_root`：`tmp/LCL-R3-XCOARSE-20260907-01/run01`
- 新 output root：`tmp/LCL-R3-XFINE-20260907-01/run01`（新目录）

冻结源码 blob 与 gate 一致：

- fine runner `c6d6cfc940734c3363dc2b81fda80c2518394e80`
- fine preflight `5c85b72ddd85162f46a2d7da38002fdd151759ed`
- x_decomposition `040182c3f8571083a83d8df3cd852f82dc1f4e48`
- x_coarse_runner `5adcfc81dff0a637e0ae21987db02d1c94ba5b9b`
- TIMEISO runner `sha256:ee7036f1925ab61ed88cc96e79a0ee06af9bb2a75812a1a58f4aa2d4a61c3708`
- condition-views `sha256:7d76a03785e2d03623342c63c360ddf7680835433294f5f511163d09fba2f921`

环境：Python 3.13.5 / numpy 2.2.4 / pandas 2.2.3 / torch 2.6.0+debian / CPU / cuda=false。  
UCX `inotify_add_watch ... No space left on device` 仅出现在 stderr，不影响退出码。

### 1) 五模块 targeted tests

```bash
python3 -m pytest -q \
  tests/unit/test_reaka_r3_x_decomposition.py \
  tests/unit/test_reaka_r3_x_coarse_runner.py \
  tests/unit/test_reaka_r3_x_fine_runner.py \
  tests/unit/test_reaka_r3_x_fine_preflight.py \
  tests/unit/test_reaka_r3_x_fine_cli.py
```

- 退出码：**0**
- tests=49 failures=0 errors=0 skipped=0
- 日志：`targeted_tests.txt` / `targeted_tests.junit.xml`

### 2) read-only preflight

```bash
export FACTORLAB_ROOT="/home/starryocean/桌面/量化/baylum terminal 0.4.1/factor_lab"
python3 scripts/reaka_r3_x_fine_compare.py \
  --spec .../x_fine_run_spec.json \
  --preflight-only
```

- 退出码：**0**
- `status=passed_read_only_reference_preflight`
- `reference_seed_pairs_checked=6`
- 两时钟 XCOARSE 逐日重建通过（各 142 days）
- `new_fits=0`，`new_inference=0`，`future_result_peeking=false`
- 回执：`preflight.json`

### 3) 正式 18 fits

同一 spec，无 `--preflight-only`。正式命令再次跑同一 preflight 后训练。

- 退出码：**0**
- `status=completed_consumed_historical_only`
- **new fits = 18**
- F/E/H refits = **0 / 0 / 0**
- 每 fit 恰好 3 cycle；selected checkpoint = 最小 canonical fit-prefix loss，平手取最早
- 18/18 `future_target_values_read=0`
- 18/18 fresh-process CPU reload
- 未因结果改代码、未重跑、未加 seed/cycle/K/arm、未跑 F+M、未调用 Actions
- 未修改原 TIMEISO / XCOARSE scores、store、checkpoint

## Combined equal-date/equal-clock 主量（2018–2020，142 days）

这是预注册嵌套有序差值，不是 unique causal attribution。secondary 不救活 primary。

| contrast | mean RankIC | median | win/loss | block8 |
|---|---:|---:|---:|---|
| STATE_VALUE_PLUS_E − E | 0.000863300155 | -0.000971007128 | 67 / 75 | [-0.007361658091, 0.009204745446] |
| F − STATE_VALUE_PLUS_E | 0.010395502426 | 0.009838207669 | 95 / 47 | [0.004807915919, 0.017297531507] |
| BETA_ONLY − H | 0.005507342318 | 0.002301158922 | 78 / 64 | [-0.008689343902, 0.019631284237] |
| BETA_RELIABILITY − BETA_ONLY | 0.005634296290 | 0.004355834315 | 87 / 55 | [0.000453349950, 0.011124395941] |
| E − BETA_RELIABILITY | **-0.001863616768** | -0.002410356534 | 58 / 84 | [-0.004845891503, 0.000519960361] |
| reconstructed F − E | 0.011258802581 | 0.010801806028 | 105 | [0.005938512541, 0.017342186932] |
| reconstructed E − H | 0.009278021840 | 0.007066025050 | 86 | [-0.001062136513, 0.019458336697] |
| reconstructed F − H | 0.020536824421 | 0.018540300216 | 112 | [0.008334688698, 0.033177195543] |

嵌套闭合：`(STATE_VALUE_PLUS_E−E) + (F−STATE_VALUE_PLUS_E) = F−E`；`(BETA_ONLY−H) + (BETA_RELIABILITY−BETA_ONLY) + (E−BETA_RELIABILITY) = E−H`。  
XCOARSE `F−E / E−H / F−H` 逐日重建通过，数值与已验收 XCOARSE 一致。

负结果原样保留：combined `E−BETA_RELIABILITY` 为负；1445 seed29 的 `STATE_VALUE_PLUS_E−E` 为负。没有重跑。

## 逐 clock ensemble 与逐 seed

详见 `1430/result.json`、`1445/result.json`、`*/per_seed.csv`。年份 2018/2019/2020 与 phase 0/1/2/3 均已写入各 clock `summary.by_year` / `summary.by_phase`，含负年份/负 phase。

## Secondary（H20 financial residual，不救活 primary）

combined decile spread / Top30-minus-universe 见顶层 `result.json` → `combined.secondary`。  
`E−BETA_RELIABILITY` 的 primary 为负；其 secondary 不得解释为“曝光 availability 已成立”。

## 月度 CloudRidge

`formula_identity_not_found` 仍成立。未猜公式，未执行 F+M。

## 证据边界

- `fresh_oos=false`
- `full_pit_certified=false`
- `production_authority=false`
- 非 unique causal attribution
- 非股票总收益 / 非账户 alpha

## 产物

回传目录：`cloud_results/local_handoff_R3_xfine_20260907/`

已提交小文件：`local_feedback.md`、`run_spec.json`、`preflight.json`、`targeted_tests.txt`、`targeted_tests.junit.xml`、`formal_run.txt`、顶层 `result.json`、`runtime_identity.json`、`combined_daily.csv`、两时钟 `result.json` / `paired_daily.csv` / `per_seed.csv`、18 个 `fit_receipt.json`、18 个 `checkpoint/manifest.json`、18 个 `reload_spec.json`。

大 scores.npz / checkpoint 张量留本地：

`FactorLab/tmp/LCL-R3-XFINE-20260907-01/run01/`
