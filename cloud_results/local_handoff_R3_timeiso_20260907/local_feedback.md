# LCL-R3-TIMEISO-20260907-01 本地反馈

任务：LCL-R3-TIMEISO-20260907-01
执行方：本地 Codex controller
时间：2026-09-07
状态：本地已反馈；**不是**云端已复核；**不是** fresh OOS / PIT / 生产。

## 身份

- 主题仓执行时 HEAD `60f2c9ffb850b11f4858b914078177b1ab6f55eb`（云端 runner 集成提交）
- 原 FactorLab `master` `b39bb12f43a46b165d18db93191a669234077444`（脏工作区未改）
- runner SHA-256 `ee7036f1925ab61ed88cc96e79a0ee06af9bb2a75812a1a58f4aa2d4a61c3708`
- CLI SHA-256 `490ee35222584c381656f9d41e0536ef064328eae2a521785db6c14f51d4bd4d`
- 本地 CLI 增加 FactorLab `src` 注入：主题仓缺少 `reaka_intraday_orthogonal_ot_v1` / `reaka_intraday_k1_training_v1`，因此把 FactorLab 数值栈作为 `factor_lab` 包，再注入本主题的 time-isolated / condition-view 模块。未改 FactorLab 文件。
- 设备：两臂 CPU；`cuda_available=false`

## 命令

```bash
python3 -m pytest -q tests/unit/test_reaka_r3_time_isolation.py tests/unit/test_reaka_r3_time_isolated_runner.py tests/unit/test_reaka_r3_wiring_validation.py
python3 scripts/check_reaka_r3_time_isolated_plan.py
python3 scripts/reaka_r3_time_isolated_compare.py --spec \
  "/home/starryocean/桌面/量化/baylum terminal 0.4.1/factor_lab/tmp/LCL-R3-TIMEISO-20260907-01/run_spec.json"
```

- 合成/计划测试：通过
- 真实运行退出码：**0**，`status=completed_consumed_historical_only`
- 输出目录事先不存在：`tmp/LCL-R3-TIMEISO-20260907-01/run01`
- 新拟合 12 次（2 臂 × 2 时钟 × 3 seed），每 seed ≤3 cycle；未跑 E；未因结果重跑

数据根：

- OT：`output/factor-rotation/reaka_intraday_orthogonal_OT_v1_2007_2020/formal/{1430,1445}`
- P6.1：`output/factor-rotation/reaka_intraday_target_fill_v1_2007_2020/formal/decision_positions.npy`

## 选型（仅 2009–2016 成熟前缀）

两时钟选出同一组工具：industry=`causal_haar_wavelet_bandpass`，market=`simple_moving_average_trend`，size=`laplace_iir_mixed_bandpass`。annual_metrics 171 行，年份 2009–2016，无 2017+。

## 评价窗口

训练行 year≤2016（n=361628）。预测行 2018–2020（408446），挂标签后 393431。配对日 142，日期 2018-01-08..2020-12-03。**2017 日数=0。** 2021+/2026 未读。

F/H pair identity 除 arm 外字段一致（6/6 seed 无 mismatch）。同一 seed 的 pre-DMD digest 跨臂一致。12 个 checkpoint 均经新进程 `--reload-worker` 重载后打分。

## 主量（已消费历史材料上的时间隔离、同环境算法比较）

等日期、等时钟平均 F−H RankIC = **0.020537**。

| 时钟 | 日数 | 胜出 | mean F−H | median | block8 95% 区间 |
|---|---:|---:|---:|---:|---|
| 1430 | 142 | 115 | 0.019233 | 0.016500 | [0.0077, 0.0312] |
| 1445 | 142 | 110 | 0.021841 | 0.020450 | [0.0089, 0.0351] |

这不是 fresh OOS、外部 PIT、经济因果或账户 alpha。`fresh_oos=false`，`PIT_certified=false`，`production_authority=false`。

## 产物

本地大数组/checkpoint 张量/score npz 留在 `tmp/LCL-R3-TIMEISO-20260907-01/run01/`。

回传小文件：`cloud_results/local_handoff_R3_timeiso_20260907/`（顶层 result/source/environment、两时钟 result 与 paired_daily、选型摘要、12 份 manifest/reload/fit receipt）。

## 未执行 / 限制

未增加 E/K/seed/cycle；未读 2021–2026；未重开 R2/账户；未调用 Actions。FactorLab 主题包需要本地注入才能导入 OT/training。区间是移动块诊断，不是独立确认。
