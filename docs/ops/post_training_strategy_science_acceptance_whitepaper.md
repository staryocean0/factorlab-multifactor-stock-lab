# 训练后策略科学验收白皮书

日期：2026-09-04  
状态：项目级基础设施冻结  
机器合同：`post_training_strategy_science_acceptance@1.0`  
账户父契约：`post_training_account_audit@1.1`（不改写）

## 一屏结论

冻结模型或分数之后，不得直接进入 A0—A7 账户族开发。必须先做策略科学验收（SSA）：

```text
冻结模型/分数
  -> S0 身份绑定
  -> S1 两本诊断账
       |-> 选择/机会账本（单一冻死选择器，不是笛卡尔账户族）
       `-> 分数路径诊断账本（无成本、无公司行为、不是完整 RealizedPnl）
  -> S2 因子 / K·状态 / 残差 归因
  -> S3 过门
       |-- no_signal 或 infrastructure_gap -> 停止，不开账户合同
       `-- diagnostic_signal_present_account_contract_may_open
              -> 才允许另冻 A0—A7 账户合同
```

SSA 回答的是“这个冻结分数本身有没有站得住的截面信号”，不是“这个账户政策赚不赚钱”。完整账户快照、成本、停牌涨跌停、强制持有和逐笔 RealizedPnl 仍是 A0—A7 的产品。

## 为什么要插这一层

`post_training_account_audit@1.1` 已经定义了两本账和 AccountSnapshot，但它们被埋在 A4—A6：先冻账户族，再重放，再出账本。如果分数本身没有排序能力，账户族搜索是在没有信号的载体上做政策优化。

用户要求的顺序是：多因子模型训练完 → 先看两本账和因子/K/残差归因 → 通过才做 A0—A7。本层把这个顺序写成项目级硬门，不把 `@1.1` 改成别的东西。

## S0—S3

### S0 身份

绑定不可变模型、checkpoint、分数定义、数据角色和候选臂。账户结果不能回写模型。K 是否有用是科学结论，不是必须点；没有第二算子时，候选可以是联合 K=1 消融，且不必因此重训。

### S1 两本诊断账

1. **SelectionOpportunityLedger**  
   问：在决策时已可买的集合里，冻结分数选出的名字是否接近事后实现的好机会。事后机会排名永远没有 runtime 权威。SSA 只允许一个结果前冻死的诊断选择器，禁止 TopN/成本笛卡尔搜索。

2. **ScorePathDiagnosticLedger**  
   问：同一选择器下，等权分数路径的逐名贡献能否守恒。  
   恒等式与账户层相同：

   ```text
   sum(simple_contribution) = daily_path_return
   sum(linked_log_contribution) = log1p(daily_path_return)
   ```

   但本账明确：`complete_realized_pnl=false`，`cost_applied=false`，`account_snapshot=false`。它不是 NAV 账户。

诊断选择器冻结为 `N30_equal_eligible_unconstrained`。TopN=30 与等权来自已经存在的 REAKA N30 身份，只借其选择器身份，不复用旧 K1 分数、旧市场面板或 2018+ 账户树。SSA 的可买集合是训练入口里已经 labelled 的截面，不是账户层停牌/涨跌停 tradability。

### S2 三项归因

在同一坐标上保留三个分数：

- `score_factor`：decoder(encoder latent)，无算子、无残差；
- `score_k_state`：decoder(K·latent)，残差为零；
- `score_full`：官方 unlabelled forecast，decoder(K·latent + residual)。

残差增量定义为 `score_full - score_k_state`。这是分数空间的嵌套归因，不是账户 P&L 拆分。归因符号是报告，不是额外否决，除非官方分数与 `score_full` 对不上（基础设施缺口）。

### S3 过门

结果中立，三种合法结局：

- `diagnostic_signal_present_account_contract_may_open`
- `no_signal`
- `infrastructure_gap`

过门条件（结果前冻结，不得看完再改）：

- 2017 零读，2018+ 零读；
- 科学 JSON 不含墙钟；
- formal/isolated 科学字节一致；
- 禁止把 K2 选成候选，禁止搜账户族；
- 每个时钟：全样本与 2011—2013、2014—2016 子期的日均 RankIC 均严格大于 0；
- 每个时钟：入选名字的机会排名中位数严格优于合格集合中点。

通过只表示“可以另冻账户合同”，不表示策略已验证、fresh OOS 或生产权。失败则停止，不重训、不调账户参数。

## 时间角色

自然年是材料/反例，不是日历运行规则。SSA 只消费训练入口的拟合段诊断角色。已被打开过的回顾年不得再当通过证据。未授权的更晚年份零读。

## 权限

SSA 不授予因子准入、策略变更、账户执行、指针或生产权。`@1.1` 仍是账户审计权威；本层是它的前置门。
