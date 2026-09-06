# REAKA P6.2 盘中 OT1--OT3 透明正交层白皮书

> 日期：2026-08-31  
> 责任项：`bd://fl-eginj.2`  
> 机器合同：`docs/ops/reaka_intraday_orthogonal_OT1_OT3@1.0.json`

## 1. 为什么旧OT不能直接复用

P6.1把产品时钟改为14:30/14:45决策、bar后第一可交易raw fill和未来H20可交易
target。旧OT1使用日收盘到日收盘收益，旧beta下一session生效，旧OT2按每日收益
累加。公式顺序仍有价值，但这些时间和收益内容均已失效。

本步继承的只有：市场→单一small-minus-large规模→接受行业→股票特异的正交顺序、
120/96窗口、五折排除自身、可靠度、七个结果前工具家族和OT3三列不预求和。

## 2. OT1双角色收益

每个时钟独立生成：

- `history`：决策时已知的decision-close H20收益；
- `future_target`：决策后entry fill至t+20同钟fill的H20收益。

市场、规模和行业投影全部只用history的`t-120:t-1`拟合；同一组冻结系数分别作用于
history t和future_target t。股票beta同样只用`t-1`及更早历史拟合，在当日决策bar
之后生效。任何future target都不能进入factor或beta fit。

五折carrier继续按`symbol_position mod 5`排除股票的整个fold，防止股票通过自身
进入因子再解释自身。

## 3. OT2重审

输入时钟改变后，旧选中的market/size/industry工具没有继承权。候选仍是结果前
固定的七个去重代表工具加透明naked control。

2009--2020必须按自然年顺序执行12个digest链式session。每个session同时审查
14:30和14:45，但两个时钟不互相选择、借结果或合并参数。

OT2只在D5决策点评价当时state对未来H20 factor target的作用：

```text
net_H20 = state_t * future_factor_H20_t - D5_state_change_cost
```

年度指标是每个D5决策的平均H20净值，不把高度重叠的H20标签按日求和冒充可实现
年收益。最终每个时钟、每个经济族选择一个工具；无工具通过年度分布门时精确回退
transparent control。

## 4. OT3

OT3在同一时钟、同一D5日期把所选state与当时已冻结的beta/reliability相乘，输出：

1. `market_timing_transport`；
2. `size_timing_transport`；
3. `industry_timing_transport`。

三列不得预求和，不得输出工具投票总分，不授予账户或买入权。

## 5. 边界

- 2007--2008仅warmup；
- 2009--2020为已消费development material；
- post-2020读取为0；
- formal/isolated从P6.1各自树独立重建；
- 本步不训练神经模型、不生成股票最终分数、不运行账户。

P6.2通过后停下，下一步只能由用户checkpoint开放K1输入合同。

