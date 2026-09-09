# R3 时间隔离 F/H：云端最终验收

日期：2026-09-07  
任务：`LCL-R3-TIMEISO-20260907-01`  
真实运行提交：`84ef80f14e18ba8da7f7dd183e4d4bb4ab6388c1`  
只读 reporting delta 提交：`36a2a37d9841a4342d87274b177ed4d1a37d39d9`

## 1. 最终裁决

**任务正式收口为 `completed_with_limits`。** 不再要求同任务本地补件、重训、重新推理、checkpoint reload 或扩大实验配置。

已经完成并接受的实验事实：

- OT2 选择只使用 2009–2016 的成熟前缀，不含 2017+；
- F/H 两臂统一 CPU、同 seed/clock 共同 pre-DMD 初始状态、相同训练/预测坐标及共同配方；
- 12 次真实拟合按冻结预算完成，没有追加 E/K/seed/cycle/年份；
- checkpoint 实际持久化，并通过 fresh-process worker 生成真实 scores；训练 receipt 记录未来目标读取为 0；
- 2018–2020 为固定评价期，2017 不参与主评价；
- reporting delta 只读取已有 scores/store：新 fit=0、新 inference=0、checkpoint reload=0，原 scores/store/checkpoint 未修改；
- 冻结计划要求的逐 clock/seed、逐年、phase、H20 decile、Top30 与四个固定 baseline 已全部补齐。

本验收仍是**已消费历史材料上的时间隔离、同环境算法比较**，不是 fresh OOS、完整 PIT、经济因果、总收益/账户 alpha 或生产授权。

## 2. 主结果

首轮云端已经从两时钟完整 142 日配对表重聚合：

- 14:30：mean F−H RankIC = `0.019232554083375177`，115/142 日为正；
- 14:45：mean F−H RankIC = `0.021841094758399272`，110/142 日为正；
- 冻结主量（每天先等权两个时钟，再跨日平均）=`0.020536824420887195`；
- 主量 median=`0.01854030021598827`；
- 正增量日=112/142；
- 两时钟日增量相关=`0.985834736660759`，不能当独立重复。

预先规定的共同 moving-block 95% 诊断区间：

- block4 `[0.0092049531, 0.0314236814]`
- block8 `[0.0083346887, 0.0331771955]`
- block12 `[0.0073590149, 0.0324704877]`

四个 phase 的主量均为正。

## 3. 逐 seed / 年份 / phase 稳定性

六个 clock×seed 的全期 mean F−H 全部为正：

| clock | seed | mean F−H RankIC | win days |
|---|---:|---:|---:|
| 14:30 | 11 | 0.0040218240 | 95/142 |
| 14:30 | 29 | 0.0315289857 | 115/142 |
| 14:30 | 47 | 0.0137511946 | 87/142 |
| 14:45 | 11 | 0.0174902136 | 121/142 |
| 14:45 | 29 | 0.0264193480 | 110/142 |
| 14:45 | 47 | 0.0135214019 | 85/142 |

云端对 `per_seed_year_phase.csv` 做独立结构/算术检查：

- 18 个 `clock×seed×year` 切片全部 mean F−H > 0；
- 24 个 `clock×seed×phase` 切片全部 mean F−H > 0；
- 最小年度增量为 14:30 seed11 的 2019：`+0.0012259640`；
- 最小 phase 增量为 14:30 seed11 phase3：`+0.0021342623`；
- 各 seed 的年度加权均值、phase 加权均值均精确回到其全期均值。

这表明本轮正向增量不是由单个 seed、单一年份或单个 phase 独占；但 seed 强度明显不同，尤其 14:30 seed11 增量较弱，因此仍不应把单一数值当成稳定常数。

## 4. 集中组合类二级指标

所有预先报告的 year/phase 平均 decile spread 与 Top30-minus-universe 的 F−H 都为正。

全期：

| clock | decile spread F−H | spread win days | Top30 F−H | Top30 win days |
|---|---:|---:|---:|---:|
| 14:30 | 0.0091857015 | 104/142 | 0.0139008493 | 100/142 |
| 14:45 | 0.0108170167 | 109/142 | 0.0175869515 | 104/142 |

这些单位仍是未来 H20 **金融残差目标**，不是股票总收益或净账户收益。日胜率也没有到“几乎每天占优”的程度，例如 14:45 的 2018 Top30 为 24/48 日胜出，虽然平均差为正。因此不能将平均正增量扩写为每天稳定获利。

## 5. 四个固定 no-fit baseline

四个方向均按预先冻结定义报告，`mean10` 使用 10 个 H20 间隔端点，不是连续10个交易日。两个时钟全部 393,431 个 labelled rows 都有完整10点历史，baseline 对照没有因缺历史缩小支持。

四个规则中最强仍为 `negative_mean10_epsilon`：

| clock | strongest baseline RankIC | H − baseline | F − baseline |
|---|---:|---:|---:|
| 14:30 | 0.1321169247 | +0.0116342422 | +0.0308667963 |
| 14:45 | 0.1313727603 | +0.0082716797 | +0.0301127744 |

因此在同一 2018–2020 支持上：

1. history-only H 仍优于这四个固定简单历史规则中的最强者；
2. full-X F 又进一步优于 H；
3. F/H 与简单规则的差值不能转成“历史表示学习解释多少、条件信息解释多少”的可加百分比归因。

## 6. 云端最终复核范围

本轮云端没有读取本地大 scores/store/checkpoint，也没有重新训练或重新推理。对 GitHub 回传的小表与脚本源码执行了以下独立复核：

- 检查 reporting delta 源码不导入 torch，不调用 training/forecast/reload worker；
- 核对 evaluation years 被硬限制在 2018–2020，2017 被显式拒绝；
- 核对 mean10 offsets 为 `-180,-160,...,0` 共10个 H20 spaced endpoints；
- 核对四个 baseline 方向固定且 F/H/support 坐标必须一致；
- 对逐 seed/year/phase、secondary 和 baseline 表做 71 项独立结构与算术一致性检查，**71/71 通过**；
- 本地 reporting delta 的 pytest 和汇总脚本均声明退出码0；云端没有在本地真实 score 数组上重跑该脚本，因此不把本地测试称为云端原数组复验。

## 7. 证据含义升级

相比此前 2017 的混合后端描述性消融，本次证据强度有实质提升：

- 工具选择与评价期隔离；
- F/H 统一 CPU；
- 同 seed 共同初始权重；
- 两臂各自 DMD/训练；
- checkpoint 持久化与 fresh-process reload 实际执行；
- 6个 seed×clock、18个年度切片、24个 phase 切片的平均 F−H 均为正；
- 排序、decile、Top30 与简单基准方向一致。

因此可以接受以下较强但仍有限的研究陈述：

> **在已消费的 2018–2020 历史支持上，采用 2016 年末冻结选型和同一数值环境/算法配方时，直接 X 条件信息包对 K1 的未来 H20 金融残差截面预测表现存在稳定的正向算法增量。**

这里的“直接 X 信息包”是当前 K1 的既有 state/exposure/reliability/mask 等直接输入集合；它不是对单一具体条件变量的因果归因，也不是新月度 CloudRidge 条件的验证。

## 8. 仍然不能声称

- fresh OOS；
- 全链 PIT / 历史事件到达时间认证；
- 直接 X 的经济因果效应；
- 新月度 CloudRidge 条件已有效；
- 股票总收益或交易成本后账户 alpha；
- 生产策略授权；
- 两个时钟或三个 seed 是独立市场重复。

`fresh_oos=false`、`full_pit_certified=false`、`production_authority=false` 保持不变。

## 9. 收口与下一步

`LCL-R3-TIMEISO-20260907-01` 现在完成，不再要求同任务本地补件。旧 R2、NOFIT、2017 F/H 不重开。

下一步研究应基于这个已确认的“直接 X 信息包有算法增量”事实，进一步回答**究竟哪些直接条件通道/经济状态贡献有效，以及新增月度 CloudRidge 条件是否有独立增量**。新问题必须单独预注册对照，不能把本轮整包 F−H 直接归给某一个条件变量。
