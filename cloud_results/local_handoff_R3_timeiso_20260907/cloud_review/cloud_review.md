# R3 时间隔离 F/H 真实运行：云端首轮验收

日期：2026-09-07  
任务：`LCL-R3-TIMEISO-20260907-01`  
本地结果提交：`84ef80f14e18ba8da7f7dd183e4d4bb4ab6388c1`  
运行源码基点：`60f2c9ffb850b11f4858b914078177b1ab6f55eb`

## 1. 裁决

**核心真实运行结果受限接收；冻结报告项尚有一次零训练/零推理补充，故任务当前记为 `cloud_reviewed_core_accepted_reporting_delta_pending`。**

已经接收的核心事实：
- 两时钟 OT2 工具选择只汇总 2009–2016 年成熟前缀，`includes_2017_or_later=false`；
- 两臂统一 CPU 环境；12 次拟合完成（2 arms × 2 clocks × 3 seeds），每次最多 3 cycle；
- 每一组 F/H 的 recipe/source/environment/selection/normalizer/train rows/prediction rows/pre-DMD/batch-order 身份一致，除 arm 外无差异；
- 每组 checkpoint 已持久化；回传了 12 份 checkpoint manifest 与 reload spec；最终评分路径由 fresh-process reload worker 生成本地 score；
- fit receipt 均记录 `future_target_values_read=0`；训练支持为 361,628 行、year<=2016；
- 主评价使用 2018–2020，预测 408,446 行，成熟标签 393,431 行，142 个配对日，2017 不进入主评价；
- 两个时钟的集成逐日表可由云端完整重聚合，主量为 **0.020536824421**。

这仍是**已消费历史材料上的时间隔离、同后端算法比较**，不是 fresh OOS、完整 PIT、经济因果、总收益或扣费账户 alpha。

## 2. 云端独立重聚合

云端读取并重新聚合两份完整 `paired_daily.csv`（各142行）。结果与本地逐时钟摘要一致：

| 指标 | 14:30 | 14:45 |
|---|---:|---:|
| days | 142 | 142 |
| mean F−H RankIC | 0.019232554083 | 0.021841094758 |
| median F−H | 0.016500260835 | 0.020450233697 |
| F胜出日 | 115 | 110 |

两时钟的 day_position、phase、截面 n 完全一致，因此按冻结方案先在每个日期等权平均两时钟：
- 主量 mean = **0.020536824421**
- median = **0.018540300216**
- 正增量日期 = **112/142**
- 两时钟日增量相关系数 = **0.985835**
- 两时钟同时为正 110 日，同时非正 27 日，仅 5 日符号不一致。

冻结方案要求“both clocks together”的 moving-block 诊断，云端按 runner 同一算法重新计算：
- block 4: [0.009205, 0.031424]
- block 8: [0.008335, 0.033177]
- block 12: [0.007359, 0.032470]

四个 phase 的主量均为正：`{"0": 0.015762262767563574, "1": 0.021123067934387826, "2": 0.024737883138064413, "3": 0.020657064461051814}`。

这些区间是已消费样本上的序列依赖诊断，不是 fresh-OOS 显著性签字。两时钟高度相关，不能当作两个独立市场重复。

## 3. 训练和运行身份检查

逐一检查 6 组 F/H fit receipt：
- 同 seed/clock 的 `pre_dmd_state_digest` 一致；
- `recipe_digest`、`source_digest`、`environment_digest`、`selection_digest`、`normalizer_digest`、`train_rows_digest`、`prediction_rows_digest`、`batch_order_digest` 均一致；
- 每个 arm 的 `selected_cycle` 都等于其三次 `canonical_train_loss` 的最小值；
- 所有 fit receipt 均为 361,628 fit rows，`future_target_values_read=0`；
- DMD 在 F/H 内分别估计，故 operator/condition number 不要求相等。H 的 DMD condition number 明显高于 F，是移除 X 后的数值特征，当前未出现非有限训练或失败，不作为事后重训理由。

回传目录中 12 个 model/arm 均有 checkpoint manifest、fit receipt、reload spec。抽查 checkpoint manifest 的 `state_digest` 与对应 fit receipt `checkpoint_state_digest` 一致，manifest 包含 29 个张量及逐张量摘要。

## 4. 运行源码身份的限定

本地实际运行时 Git HEAD 仍为 `60f2c9f...`，但 CLI 为了使用本地 FactorLab 数值栈加入了 bootstrap 注入，因此工作树中的 CLI 字节与该 clean commit 不同。本地 `source_snapshot.json` 单独记录了实际 runner 与 CLI SHA256；结果提交 `84ef80...` 已把这份实际 CLI 字节保存进 Git。

检查差异后，CLI 变化是导入/模块注入桥接；时间隔离 runner 的科学逻辑没有随本地结果提交改变。故本轮接收该混合运行身份，但以后应以“git commit + runner SHA + CLI SHA + FactorLab commit”共同标识，而不能只报 `60f2...`。

这不是完整 source-closure：FactorLab 本地数值栈仍以 `b39bb12f...` 及本地反馈声明绑定，云端没有把其全量工作树重新封存。

## 5. 尚缺的冻结报告项：只读补充，不重训

冻结计划明确要求：
- `report_each_clock_and_seed=true`；
- secondary 包括 all years / all phases / H20 decile spread / Top30；
- 四个固定 no-fit baselines 仍需在同支持下列出。

当前回传已经满足集成主量、逐时钟 mean/median/win days，以及云端可直接补出的 combined block 4/8/12 与 phase 主量；**但没有逐 seed 市场评价、逐年表、decile/Top30 与四基准在 2018–2020 同支持的结果。**

因此只追加同一任务的**只读 reporting delta**：
- 读取现有 12 份本地 `scores.npz` 和已物化 store；
- 不训练、不重新推理、不重载模型重新评分；
- 每个 clock × seed 计算 F/H 的全年、逐年、phase RankIC 与 F−H；
- 集成层补 decile spread、Top30-minus-universe 与四个固定 history-epsilon baselines；
- 保留全部 seed/year，禁止结果后筛选；
- 仅回传小表/JSON，score/checkpoint/store 继续留本地。

这项补充不改变已经接收的核心主结果；它用于完成冻结报告义务和检查 seed/year 稳定性。

## 6. 当前结论

在已消费的 2018–2020 历史材料上，采用 2016 年末冻结的工具选择、同一 CPU 数值环境、同 seed 共同 pre-DMD 初始权重并重新训练的 F/H 对照，完整输入 F 的集成排序表现高于 history-only H：等日期、等时钟的平均 F−H RankIC 为 **0.020537**。block 4/8/12 的预定移动块诊断区间均未跨零。

相较此前 2017 的混合后端描述性消融，这一结果显著提高了“直接 X 信息包在固定算法配方中存在增量”的证据强度，因为选型期与评价期隔离、F/H 后端匹配、共同初始状态和 checkpoint 重载都已实际执行。

但仍不能升级为：
- fresh OOS；
- 全链 PIT / 历史事件可得性认证；
- 直接 X 的经济因果效应；
- 新月度 CloudRidge 条件的效果；
- 总收益、交易成本后账户 alpha；
- 生产授权。

在 reporting delta 完成前，不增加 E、K、seed、cycle、年份，不做结果驱动重跑。
