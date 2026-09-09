# LCL-R3-TIMEISO-20260907-01 reporting delta

任务：LCL-R3-TIMEISO-20260907-01（只读补充，不是新实验）
执行方：本地 Codex controller
时间：2026-09-07
状态：reporting delta completed；待云端最终验收。

## 身份与禁令

- 实际主题仓 HEAD（读取时）：`5daeade80ddb02dd4ee698dc33b6d46890e23a9f`
- 实际 FactorLab commit：`b39bb12f43a46b165d18db93191a669234077444`
- 原真实运行提交：`84ef80f14e18ba8da7f7dd183e4d4bb4ab6388c1`
- 原运行源码基点：`60f2c9ffb850b11f4858b914078177b1ab6f55eb`
- 原 run 根目录：`/home/starryocean/桌面/量化/baylum terminal 0.4.1/factor_lab/tmp/LCL-R3-TIMEISO-20260907-01/run01`
- 使用既有 `models/seed_{11,29,47}/{F,H}/scores.npz` 与 `{1430,1445}/prepared/store` 的 inference_rows / labelled_row_indices / epsilon_history / epsilon_future / calendar
- **新 fit = 0**
- **新 inference = 0**
- **checkpoint reload = 0**
- 是否修改任何原始模型/store/score：**否**
- 是否运行 Actions：**否**
- 未加入 E、未改 K/LR/seed/cycle/年份，未筛不利 seed/year/phase

## 命令

```bash
python3 -m pytest -q tests/unit/test_reaka_r3_timeiso_reporting_delta.py
python3 scripts/reaka_r3_timeiso_reporting_delta.py \
  --run-root ".../tmp/LCL-R3-TIMEISO-20260907-01/run01" \
  --output-dir ".../cloud_results/local_handoff_R3_timeiso_20260907/reporting_delta"
```

退出码：**0** / **0**

## 逐 seed（全期）

| clock | seed | days | mean F | mean H | mean F−H | median F−H | win | loss |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1430 | 11 | 142 | 0.151422 | 0.147400 | 0.004022 | 0.004527 | 95 | 47 |
| 1430 | 29 | 142 | 0.168064 | 0.136535 | 0.031529 | 0.033611 | 115 | 27 |
| 1430 | 47 | 142 | 0.157113 | 0.143362 | 0.013751 | 0.010051 | 87 | 55 |
| 1445 | 11 | 142 | 0.150488 | 0.132997 | 0.017490 | 0.017126 | 121 | 21 |
| 1445 | 29 | 142 | 0.165743 | 0.139324 | 0.026419 | 0.027950 | 110 | 32 |
| 1445 | 47 | 142 | 0.155546 | 0.142025 | 0.013521 | 0.008269 | 85 | 57 |

六个 clock×seed 的 mean F−H 均为正。2018/2019/2020 与 phase 0–3 全表见 `per_seed_year_phase.csv`（负切片数：year=0, phase=0；全部切片均已列出）。

集成 F−H 重聚合（不是新的独立市场证据）与已验收主量一致：1430 0.019232554083375177，1445 0.021841094758399272。云端 combined 主量 0.020536824421 仍以云端验收为准，不另报为新证据。

## 集成二级指标

H20 epsilon decile spread 与 Top30-minus-universe 见 `ensemble_secondary_metrics.csv`。全期 1430/1445 的 mean F−H spread 约 +0.0092 / +0.0108，mean Top30 增量约 +0.0139 / +0.0176。这是金融残差目标，不是账户收益。

## 四个固定 baseline

方向预先固定，mean10 为 10 个 H20 spacing endpoints，不是连续 10 个交易日。两时钟 labelled 行均具备完整 10 点历史（missing=0）。相对 F/H 的 RankIC 差见 `baseline_comparison.csv`。最强固定规则仍是 `negative_mean10_epsilon`。

## 产物

`cloud_results/local_handoff_R3_timeiso_20260907/reporting_delta/`：

- local_feedback_delta.md
- per_seed_summary.json
- per_seed_year_phase.csv
- ensemble_secondary_metrics.csv
- baseline_comparison.csv
- reporting_delta_summary.json

只读脚本：`scripts/reaka_r3_timeiso_reporting_delta.py`
测试：`tests/unit/test_reaka_r3_timeiso_reporting_delta.py`

大 scores/store/checkpoint 继续留本地。

## 边界

fresh_oos=false；PIT_certified=false；production_authority=false。不解释为因果、总收益 alpha、账户 alpha 或生产策略。
