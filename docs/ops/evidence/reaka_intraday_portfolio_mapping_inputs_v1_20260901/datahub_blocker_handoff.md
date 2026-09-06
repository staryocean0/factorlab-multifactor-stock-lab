# REAKA P7 DataHub blocker handoff

P7 固定 K1 分数延伸已通过，formal/isolated 八个输入文件逐字节一致。账户执行仍关闭，
因为 DataHub 的 2011--2020 逐年 `security_day_metadata` 完全缺失股票 `000638`。

该缺口不能降级为“不可买”：每个时钟有143个已评分决策坐标，14:30 有1/7/12次进入
Top10/Top30/Top50，14:45 有2/6/9次。使用当前数据缺口顺延补位或留现金会直接改变
本轮要测试的账户映射。

DataHub raw 日行情和盘中 fill 坐标中有 `000638`，缺的是可证的历史交易所/板块、风险警示
状态、价格笼规则和停复牌状态。修复产品必须：

- 覆盖 2011-08-09 至 2020-12-31 的所有 P7 决策日；
- 严格有效日期/PIT，包含 `exchange/board/risk_warning_state/suspension_status/listing_phase`；
- 绑定源文件、available_at、产品 manifest 与 digest；
- 不得用当前名称、事后 ST 记忆或价格反推冒充官方状态。

修复后 FactorLab 可复用当前两个已验收 score panel，但必须从空目录重建 market panel，再做
formal/isolated 字节验收。修复前 TopN/权重/现金与顺延/市值/时钟测试全部不得运行。
