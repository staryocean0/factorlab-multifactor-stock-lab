# REAKA P6.1 盘中 target/fill 因果物化白皮书

> 日期：2026-08-31  
> 责任项：`bd://fl-eginj.1`  
> 机器合同：`docs/ops/reaka_intraday_target_fill@1.0.json`

## 1. 本步只回答什么

P6.1只冻结并物化14:30和14:45两个独立盘中坐标：决策时已知价格、决策后的
第一可交易raw fill、H20历史收益、H20未来可交易target和不读取未来结果的推理
支持集。

本步不做市场/规模/行业正交化，不训练模型，不生成分数，不运行账户。旧OT1的
close-to-close epsilon不能直接改名成盘中target；P6.1通过后必须另建盘中OT1
successor。

## 2. 四个价格坐标

对每个股票、交易日和时钟分别定义：

1. `decision_close_t`：当天13:00至14:30/14:45之间最后一笔raw 1m成交bar收盘价；若下午无成交则决策价不可用，不用上午陈旧价代替；
2. `entry_open_t`：当天严格晚于决策时钟的第一根可交易raw 1m bar开盘价；
3. `decision_close_t_minus_20`：20个交易日前同一时钟的已知决策价；
4. `entry_open_t_plus_20`：20个交易日后同一时钟之后的第一可交易raw fill。

历史输入收益为：

```text
decision_close_t / decision_close_t_minus_20 - 1
```

未来可交易target为：

```text
entry_open_t_plus_20 / entry_open_t - 1
```

历史收益不能使用尚未发生的`entry_open_t`；未来target不能使用决策前价格替代真实
成交。两者都禁止next-open。

## 3. 稀疏成交与停牌

- 决策价使用13:00之后、时钟前最后已知成交，不后看、不使用上午陈旧价；
- fill使用时钟后第一根真实成交，不前填；
- 当天时钟后没有成交时，entry不可用；
- entry不可用只影响执行/标签，不得删除当时的score universe；
- 当天决策前没有成交时，历史输入不可用，可从因果支持中删除。

## 4. 因果推理支持

推理行只由两项决定：

1. 10个H20历史观测点在决策时已完整；
2. 使用严格早于当日的OT3特征支持。

`future_target`和`entry_fill`不参与推理行构造。评分后才能用future target形成评价
索引；执行时才能处理entry资格。

## 5. D5/H20/R5

2008-12-01为D5网格锚点，四相位只用于报告。每个决策点重新预测新的未来H20，
继续采用`rolling_h20_reforecast_r5`；不自动生成四袖套。重叠标签的n_eff和
block/HAC义务保留到后续兼容证书。

## 6. 数据与证据边界

- 权威真源：DataHub `bars_cn_a_1m_raw_canonical_4ceca170a851`；
- 股票分区：2007-01至2020-12；
- 2007--2008只作warmup；
- 2009--2020为已消费development material；
- post-2020读取必须为0；
- formal和isolated各自从同一不可变真源完整物化，全部核心文件逐字节比较。

预结果性能事件：首次8进程尝试在同机DataHub重任务期间造成Pandas月分区内存过度
并行，主控在正式目录产生前终止。无科学结果、无formal目录、无参数选择。执行器
随后增加Arrow下午时段预过滤并降为4进程；算法、数据和金融坐标不变。事件回执
必须由合同绑定。

## 7. 下一步

P6.1验收不开放K1训练。下一合法动作是用户checkpoint后冻结盘中OT1正交收益
successor，使市场、规模、行业和股票特异残差与14:30/14:45可交易target处于同一
坐标。只有新的OT1--OT3与完整兼容证书通过，才讨论神经载体。
