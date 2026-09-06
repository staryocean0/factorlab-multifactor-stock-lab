# REAKA 当前 K1 策略两账本更新白皮书

日期：2026-09-02  
状态：@1.5 只允许对已完成的 @1.4 科学数据做包装层修复  
项目级父合同：`post_training_account_audit@1.1`

## 为什么要更新

账本必须与策略身份一一对应。旧 `REAKA_OPPORTUNITY_LEDGER_V8_ALL_INDUSTRY` 使用的是冻结 `d8-K2` 股票分数，而当前正式策略是 `d8-h8-K1-r0_fit_prefix_successor_incumbent`，因此旧机会账不能被改名为当前账本。

旧逐股/逐笔收益账虽已对 2019--2020 的当前 K1 做过精确归因，但时间覆盖不完整。本次生成新版本，不覆盖任何旧束。

## 冻结策略身份

```text
strategy    = REAKA_D5_H20_R5_CURRENT_GENERATION_V1
model       = d8-h8-K1-r0_fit_prefix_successor_incumbent
residual    = r0_exact_zero
account     = N30_equal_backfill_unconstrained
clocks      = 14:30 and 14:45 as separate accounts
cost        = frozen 1x commission/tax/transfer/slippage schedule
execution   = bar close -> next_tradable_after_bar_close raw/PIT
accounting  = HFQ economic-unit identity
```

不开放 TopN、权重、顺延、成本、时钟、模型、checkpoint、分数或因子参数选择。

## 时间边界

- 2011--2016：已消费训练前缀的账户归因；
- 2017：已消费内部 review；
- 2018：已消费回溯确认；
- 2019--2020：已消费 holdout economic replay；
- 2021--2026：已被项目全局消费。用户本次明确要求为当前策略更新两本明细账，因此可读取所需的账户、股票、交易和归因明细；这不恢复 fresh OOS，也不允许结果回流调参。

为精确复现已接受回测，账户保留两个真实 replay segment：`2011_2020` 和 `2021_2026`。两段各从初始资金启动，不伪造 2020 持仓无成本穿越到 2021 的连续账户。

## 第一本：当前策略选择/机会账

对每个 D5 决策日和每个时钟：

1. 只在当时有冻结 K1 分数、可买、进出价有效的同一集合中比较；
2. `selected` 是按分数降序、symbol 升序稳定打破并列后的 Top30；
3. `oracle_top30` 是同一可买集合内，按实际 H20 收益排序的结果后 Top30；
4. H20 收益严格使用当日 bar 收线后第一可交易价到 20 交易日后同时钟第一可交易价，不使用 next-open；
5. 物化 selected、oracle 与实际持有集合的并集，同时保留 `account_held_after_execution` 和 `forced_or_nonselected_holding`；
6. 结果后标签没有模型输入或参数权。

年度摘要报平均 selected/oracle H20收益、选择缺口、Top30重合率和已选股的机会排名。由于 oracle 是同集合最优 Top30，每个决策的 `selected_mean - oracle_mean` 必须小于等于数值容差。

## 第二本：当前策略逐股/逐笔实现收益账

账户每日的每只持仓按实际调仓切成：

- previous close -> current close；或
- previous close -> execution，以及 execution -> close。

每段对应的14因子收益只拟合一次，然后按当时的个股暴露分成：

```text
index + size + industry + other = actual stock return
```

`transaction_cost` 单独记账，年度四类展示时归入 `other`。项目级恒等式为：

```text
sum(simple contributions per account-day) = account daily return
sum(linked-log contributions per account-day) = log(1 + account daily return)
```

@1.0 formal 在任何科学文件落盘前发现：新买入数量从扣完全日成本的 NAV 分配，因此用事后股数变化×成交价重算成本，会比原账户按扣费前换手权重计算的成本少。@1.1 不改全日成本或账户收益；它把原账户的全日成本按“冻结腿权重×方向费率”只分配一次。事故记录为 `pre_result_trade_cost_allocation_incident.json`，结果读取为0。

@1.1 随后在任何策略数据读取前，又因运行时 `SOURCE_FILES` 少列前驱合同和incident而失败关闭。@1.2 只补齐精确 source closure；不改上述金融、数学、账户或权限口径。

@1.2 formal 在结果落盘前发现另一个 adapter 类型错误：扣费后目标股数变化的方向不一定等于原账户按扣费前权重定义的交易腿方向。@1.3 改为直接使用冻结 `buy_legs/sell_legs`作为成交身份，用 `leg_weight × overnight_NAV` 确定成交额；实际持仓数量仍在 holdings 账中独立保留。

@1.3 首次完整 formal 在年度复现门失败：账户日收益与逐笔总和已在 `7.9e-15` 内守恒，但四类内部分组偏移约 `1e-5`。原因是“成本腿”和“PnL切段标的”责任不同：成本只跟冻结 buy/sell legs，PnL切段还必须包含实际股数变化的标的。@1.4 冻结为“成本依旧只用成本腿，PnL切段用成本腿与股数变化的并集”。失败产物已搬到 `invalid_pre_result_v1_3_formal`，没有 result 或 execution receipt，权限为false。

@1.4 formal/isolated 随后完成了全部计算：10个账户/账本科学数据文件均字节一致，但最终包装验证未放行。原因一是验证器还指向历史 `@1.0`，二是 `result.json` 错把 tree-specific snapshot manifest摘要和不确定耗时放进科学结果。@1.5 只允许保留全部10个科学数据文件字节不变，重写 `result.json` 和 `execution_receipt.json`；不允许重算模型、分数、市场、账户、因子面或两本账。

## 性能方案

- 两个时钟的 K1 求分在每个 evidence tree 只做一次；
- 每个账户 segment 只重放一次，随后物化完整 AccountSnapshot；
- 因子收益面使用 ROCm float64 批量 `lstsq`，而不是按年/账户重复 CPU OLS；
- GPU 还必须对抽样时段与 CPU `fit_factor_segment` 做系数、rank、condition number 和 observation count 等价检查；
- 稳定 Top30排序、顺序账户和小表聚合保留 CPU。

已完成的64份合成拟合作业 ROCm 预检：GPU/CPU系数最大误差约 `4.9e-17`，rank和观测数完全一致。这仅是结果前数值预检，不是新账本结果。

## 验收和权限

formal/isolated 必须分别执行，账户快照、两本账、因子收益面、年度摘要和 result 必须字节一致。新逐笔账的年度四类结果必须复现已接受的修正年度归因。

新账本只属于当前策略身份。它不选参数、不修改模型、不授予策略替换、指针或生产权。
