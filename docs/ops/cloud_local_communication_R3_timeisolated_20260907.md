# 云端—本地沟通：LCL-R3-TIMEISO-20260907-01

**状态**：`completed_with_limits`。真实运行与只读 reporting delta 均已云端复核并收口；不再要求同任务本地补件、重训、重新推理或 checkpoint reload。大数据继续留本地，不上传整湖，不用 GitHub Actions。

## 目标

按冻结设计 `R3-TIME-ISOLATED-DESIGN-20260906-01`，在本地真实 P6.1/P6.2/K1 数据上执行一次 2016 年末冻结、2018–2020 评价的同环境 F/H 对照。它是已消费历史材料上的时间隔离重复比较，不是 fresh OOS。

## 代码入口

使用开发分支 `codex/reaka-foundation-audit-20260905` 的 runner：

- `src/factor_lab/factor_rotation/reaka_r3_time_isolated_runner.py`
- `scripts/reaka_r3_time_isolated_compare.py`
- `docs/ops/r3_time_isolated_evaluation_plan_20260906.json`

不得用旧 `reaka_r3_condition_compare.py` 代替本任务。

## 真实运行（历史已执行）

固定设计：两臂 × 两时钟 × seed 11/29/47 = 12 次新拟合，每次最多 3 cycle；不增加 E、K、seed、cycle、年份、阈值或调参搜索；两臂统一 CPU 后端。

原运行命令：

```bash
python scripts/reaka_r3_time_isolated_compare.py --spec /path/to/run_spec.json
```

本地运行时主题仓 HEAD `60f2c9f`，FactorLab `b39bb12f`。CLI 为注入本地 FactorLab 数值栈有 bootstrap 字节变化，实际 runner/CLI SHA 已写入 `source_snapshot.json`；结果提交 `84ef80f14e18ba8da7f7dd183e4d4bb4ab6388c1` 保存了该运行身份。

12 次 CPU 拟合完成，退出码 0。OT2 annual selection 只含 2009–2016；2017 不在主评价。评价窗口 2018-01-08..2020-12-03；预测 408,446 行，成熟标签 393,431 行，142 个配对日。6/6 F/H pair identity 除 arm 外一致；每个 selected cycle 是本臂3个 canonical loss 的最小值；fit rows=361,628，`future_target_values_read=0`。12 个 checkpoint 均持久化，并经 fresh-process worker 生成真实 score。

大 store/checkpoint/score 数组保留本地。回传了 `local_feedback.md`、顶层与两时钟 result、paired_daily、source/environment、selection 摘要、12 份 checkpoint manifest / fit receipt / reload spec。

## 云端首轮验收（2026-09-07）

完整报告：[cloud_review.md](../../cloud_results/local_handoff_R3_timeiso_20260907/cloud_review/cloud_review.md)；机器检查：[cloud_checks.json](../../cloud_results/local_handoff_R3_timeiso_20260907/cloud_review/cloud_checks.json)。

**核心结果受限接收。** 云端完整重聚合两时钟各142个逐日配对：14:30 mean F−H=0.0192325541、115/142日为正；14:45=0.0218410948、110/142日为正。冻结主量（每天先等权两个时钟，再跨日平均）=0.0205368244、112/142日为正；两时钟日增量相关0.985835。预定共同 moving-block 区间：block4 [0.009205,0.031424]、block8 [0.008335,0.033177]、block12 [0.007359,0.032470]。四个 phase 主量均为正。

首轮验收后只缺冻结报告项，不影响核心主量，因此安排同任务只读 reporting delta：只读已有 scores/store，不训练、不重新推理、不 reload worker。

## 只读 reporting delta 本地反馈（2026-09-07）

提交 `36a2a37d9841a4342d87274b177ed4d1a37d39d9`。脚本 `scripts/reaka_r3_timeiso_reporting_delta.py` 读取 run01 的既有 12 份 `scores.npz` 与两时钟 store；pytest 与汇总命令本地均退出码0。明确：新 fit=0、新 inference=0、checkpoint reload=0，原始模型/store/score未修改，未调用 Actions，未增加 E/K/seed/cycle/年份或筛掉不利切片。

回传目录：[reporting_delta](../../cloud_results/local_handoff_R3_timeiso_20260907/reporting_delta/)，包括逐 seed、逐年/phase、集成 decile/Top30、四个固定 no-fit baseline 及只读回执。

## 云端最终验收（2026-09-07）

最终报告：[cloud_final_acceptance/cloud_review.md](../../cloud_results/local_handoff_R3_timeiso_20260907/cloud_final_acceptance/cloud_review.md)；最终检查：[cloud_final_acceptance/cloud_checks.json](../../cloud_results/local_handoff_R3_timeiso_20260907/cloud_final_acceptance/cloud_checks.json)。

云端检查 reporting delta 源码：无 torch、training objective、forecast 或 reload-worker 调用；2017 被显式拒绝；mean10 固定为10个 H20 间隔端点；四个 baseline 符号固定；seed/arm 坐标与 labelled support 不一致会硬失败。

云端对回传小表独立执行 71 项结构与算术一致性检查，71/71 通过：

- 六个 clock×seed 全期 mean F−H 全部为正；
- 18 个 clock×seed×year 平均增量全部为正，最小 +0.0012259640；
- 24 个 clock×seed×phase 平均增量全部为正，最小 +0.0021342623；
- 每个 seed 的年度/phase 加权值精确回到全期均值；
- 所有报告 year/phase 的平均 decile spread F−H 与 Top30 F−H 均为正；
- 四个 baseline 在两时钟全部 393,431 行共同支持上都有完整10点历史，无 history-filter 缩样；方向均按预先冻结定义。

全期 secondary：14:30 decile F−H=+0.0091857015（104/142日胜）、Top30=+0.0139008493（100/142）；14:45 decile=+0.0108170167（109/142）、Top30=+0.0175869515（104/142）。这些都是 H20 金融残差目标，不是股票总收益或账户收益。

四个固定规则中最强仍是 `negative_mean10_epsilon`：14:30 RankIC=0.1321169247，H−baseline=+0.0116342422，F−baseline=+0.0308667963；14:45 RankIC=0.1313727603，H−baseline=+0.0082716797，F−baseline=+0.0301127744。说明 history-only H 高于这些简单规则，full-X F 又进一步高于 H；不能把这些差值转成可加的机制归因比例。

## 最终结论与边界

任务 `LCL-R3-TIMEISO-20260907-01` 正式完成。可接受的研究陈述是：

> 在已消费的 2018–2020 历史支持上，采用 2016 年末冻结选型和同一数值环境/算法配方时，直接 X 条件信息包对 K1 的未来 H20 金融残差截面预测表现存在稳定的正向算法增量。

这里的直接 X 是当前 K1 既有 state/exposure/reliability/mask 等信息包，不是单一条件变量的经济因果效应。

保持：`fresh_oos=false`、`PIT_certified=false`、`production_authority=false`。不得继承为全链 PIT、经济因果、新月度 CloudRidge 条件、股票总收益、交易成本后账户 alpha 或生产授权；两个时钟和三个 seed 也不能当作独立市场重复。

同任务不再补件。下一步若继续研究，应单独设计“哪些 X 通道/状态真正贡献”以及“新增月度 CloudRidge 条件是否有独立增量”的预注册对照，不能把本轮整包 F−H 直接归给某一变量。
