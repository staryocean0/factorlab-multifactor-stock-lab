# REAKA 当前 K1 两账本交接

当前账本已更新为 `d8-h8-K1-r0_fit_prefix_successor_incumbent + N30_equal_backfill_unconstrained + 14:30/14:45 + 1×成本`。

主要入口：

- [最终结果](../ops/reaka_current_k1_account_ledgers_final_result.md)
- [执行白皮书](../ops/reaka_current_k1_account_ledgers_whitepaper.md)
- [工作流](reaka_current_k1_account_ledgers_workflow.md)
- [当前合同@1.5](../ops/reaka_current_k1_account_ledgers@1.5.json)
- [当前证据指针](../ops/evidence/reaka_current_k1_account_ledgers_v1_20260902/current.json)

账本查询：

```text
选择/机会明细：
output/factor-rotation/reaka_current_k1_account_ledgers_v1_2011_2026/formal/selection_opportunity_ledger.parquet

选择/机会年度摘要：
output/factor-rotation/reaka_current_k1_account_ledgers_v1_2011_2026/formal/selection_opportunity_annual.csv

逐股/逐笔PnL明细：
output/factor-rotation/reaka_current_k1_account_ledgers_v1_2011_2026/formal/realized_pnl_ledger.parquet

四类PnL年度摘要：
output/factor-rotation/reaka_current_k1_account_ledgers_v1_2011_2026/formal/realized_pnl_annual.csv

可复用账户快照：
output/factor-rotation/reaka_current_k1_account_ledgers_v1_2011_2026/formal/account_snapshot/
```

下一轮可以从两本账中生成问题材料，但在结果前必须重新冻结有界因子假设和尝试数。不得把oracle股票、日期、机会排名或本次年度贡献直接写成运行时规则。
