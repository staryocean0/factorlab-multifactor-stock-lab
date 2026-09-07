# 云端—本地沟通：LCL-R3-TIMEISO-20260907-01

**状态**：云端已复核核心真实运行；`cloud_reviewed_core_accepted_reporting_delta_pending`。不重训、不重新推理；只需完成冻结方案尚缺的只读 reporting delta。大数据留在本地，不上传整湖，不用 GitHub Actions。

## 目标

按冻结设计 `R3-TIME-ISOLATED-DESIGN-20260906-01`，在本地真实 P6.1/P6.2/K1 数据上执行一次 2016 年末冻结、2018–2020 评价的同环境 F/H 对照。它是已消费历史材料上的时间隔离重复比较，不是 fresh OOS。

## 代码入口

使用开发分支 `codex/reaka-foundation-audit-20260905` 的本次 runner 集成版本：

- `src/factor_lab/factor_rotation/reaka_r3_time_isolated_runner.py`
- `scripts/reaka_r3_time_isolated_compare.py`
- `docs/ops/r3_time_isolated_evaluation_plan_20260906.json`

不得用旧 `reaka_r3_condition_compare.py` 代替本任务。

## 本地只读准备检查

两时钟各自确认存在：

- `ot_root/ot1/factor_basis_history.parquet`
- `ot_root/ot1/factor_basis_future.parquet`
- `ot_root/ot1/stock_residual_surfaces.npz`
- `ot_root/ot1/d5_stock_exposures.parquet`
- `ot_root/ot1/d5_stock_industry_exposures.parquet`
- P6.1 `decision_positions.npy`

路径或依赖缺失只阻断对应 clock；不要回到 R0/R1，不要重算已验收的 OT1 epsilon。

## 运行规范（历史已执行）

真实运行使用固定设计：两臂 × 两时钟 × seed 11/29/47 = 12 次新拟合，每次最多 3 cycle；不增加 E、K、seed、cycle、年份、阈值或调参搜索；两臂统一 CPU 后端。

原运行命令：

```bash
python scripts/reaka_r3_time_isolated_compare.py --spec /path/to/run_spec.json
```

## 原必须回传的小产物

大 store/checkpoint/score 数组保留本地。已回传：

1. `local_feedback.md`；
2. 顶层 `result.json`；
3. 两时钟 `result.json`、`paired_daily.csv`；
4. `source_snapshot.json`、`environment.json`；
5. 两时钟 selection 摘要；
6. 12 个 checkpoint `manifest.json`、reload spec 与每个 seed/arm fit receipt。

## 本地反馈（2026-09-07）

主题仓运行时 HEAD `60f2c9f`。FactorLab `b39bb12f` 未改脏区。CLI 注入 FactorLab 数值栈后执行正式 runner，退出码 0。12 次 CPU 拟合完成。2017 不在主评价；窗口 2018-01-08..2020-12-03。等日期等时钟平均 F−H RankIC 0.020537。pair identity 6/6 通过。报告 [local_feedback.md](../../cloud_results/local_handoff_R3_timeiso_20260907/local_feedback.md) 与同目录小产物。store/checkpoint 张量/score npz 留本地。fresh_oos=false，PIT_certified=false，production_authority=false。未跑 E，未 Actions。

## 云端首轮验收（2026-09-07）

复核提交 `84ef80f14e18ba8da7f7dd183e4d4bb4ab6388c1`。完整报告见 [cloud_review.md](../../cloud_results/local_handoff_R3_timeiso_20260907/cloud_review/cloud_review.md)，机器检查见 [cloud_checks.json](../../cloud_results/local_handoff_R3_timeiso_20260907/cloud_review/cloud_checks.json)。

**核心结果受限接收。** 云端完整重聚合两时钟各142个逐日配对：14:30 mean F−H=0.0192325541、115/142日为正；14:45=0.0218410948、110/142日为正。按冻结方案先逐日等权平均两时钟，主量=0.0205368244、112/142日为正；两时钟日增量相关0.985835。预定 moving-block 的共同两时钟区间：block4 [0.009205,0.031424]、block8 [0.008335,0.033177]、block12 [0.007359,0.032470]。四个 phase 主量均为正。

六组 F/H receipt 已核：除 arm 外配对身份一致，pre-DMD digest 同 seed/clock 一致；每个 selected cycle 均是本臂3个 canonical loss 的最小值；所有 fit rows=361628、`future_target_values_read=0`。两时钟 annual selection 仅 2009–2016，各171行，不含2017及以后。12个 model/arm 均回传 checkpoint manifest、fit receipt、reload spec；抽查 checkpoint state digest 与 fit receipt 一致。

运行时 CLI 为了注入本地 FactorLab 数值栈相对 clean `60f2...` 有 bootstrap 字节变化；`source_snapshot.json` 已记录实际 runner/CLI SHA，结果提交 `84ef80...` 已保存该 CLI。以后将 git commit、runner SHA、CLI SHA、FactorLab commit 联合视为运行身份，不单凭 clean HEAD。

## 同任务只读 reporting delta（待本地补充）

冻结方案原先明确 `report_each_clock_and_seed=true`，并要求 secondary 的 all years / all phases / H20 decile spread / Top30，以及四个固定 no-fit baselines。当前核心集成结果已接收，但这些报告项未完整回传。

**只读现有产物，不训练、不重新推理、不重新加载模型评分。** 使用 run01 已保存的 12 份 `scores.npz`、两时钟 store 与现成目标：

1. 每个 `clock × seed` 分别计算 F、H 及 F−H：全期 mean/median/win days、2018/2019/2020逐年、四 phase；不得筛掉任何 seed/year。
2. 集成层补 H20 epsilon top-bottom decile spread 与 Top30-minus-same-universe mean，F/H均报并给差值。
3. 在同一 labelled support 上计算四个固定历史 epsilon 基准：`last_epsilon`、`negative_last_epsilon`、`mean10_epsilon`、`negative_mean10_epsilon`；报告逐时钟与等时钟合并的 mean RankIC，不能事后只保留最优方向。
4. 不需要重复 block 4/8/12；共同主区间已由云端从上传的逐日表重算。
5. 仅回传 `local_feedback_delta.md`、`per_seed_metrics.json/csv`、`secondary_metrics.json/csv`、`baseline_metrics.json/csv` 等小文件。大 score/store/checkpoint 继续本地保留。

这次 reporting delta **不得新增拟合、推理、seed、E、K、cycle、年份或结果驱动重跑**。它不改变已接收的 +0.0205368 主结果，只完成冻结报告义务并检查 seed/year 稳定性。

## 结论边界

即使最终报告项均为正，也只能称为“已消费历史材料上的时间隔离、同环境算法比较”。`fresh_oos=false`、`PIT_certified=false`、`production_authority=false` 保持不变；不继承为新月度 CloudRidge 条件、总收益或账户 alpha 的证明。
