# 项目级训练后账户快照与两类账本工作流

方法、性能和权限边界见[白皮书](../ops/post_training_account_research_bundle_whitepaper.md)。本流程是 `post_training_account_audit@1.1` 的执行面。

## 下一轮的标准顺序

1. A0 冻结模型、checkpoint 和分数快照。同一个分数快照不得因新增报表而重算。
2. A1 结果前冻结账户政策族、时钟和成本。
3. A2 策略 adapter 对齐标准 core columns，但保留策略自己的扩展列。
4. A4/A5 每个注册账户只重放一次，物化 `complete_account` AccountSnapshot。
5. 选择/机会账本从冻结分数与结果后机会标签生成；它不依赖账户收益归因。
6. 每个时钟/时段先物化一份 policy-independent `FactorReturnSurface`，再向量化连接账户持仓，生成逐股/逐笔 `RealizedPnlLedger`。
7. 年/季/月、云脊超额、夏普、信息比率、回撤等全部只读 AccountSnapshot。
8. formal/isolated 分别物化；科学文件必须字节一致，manifest 可因 `tree` 身份而不同。

## 策略 adapter 必须输出什么

### AccountSnapshot

- `portfolio_daily`：`date + account_id + variant_id + policy_id + cost_scenario_id + nav/daily_return/cash/cash_weight/holding_count/is_rebalance`
- `holdings`：追加 `asset_id/quantity/mark_price/market_value`
- `trades`：追加 `asset_id/direction/quantity/execution_price/trade_value/transaction_cost`
- `events`：追加 `asset_id/event_type/reason`

交易成本必须是逐腿可加总值。只有日账户而没有后三张完整表时，只能标 `account_daily_only`，不能用于逐笔归因或 A7 完整封口。

### 选择/机会账本

调用 `validate_selection_opportunity_ledger(frame)`。关键门：

- 分数必须在 decision time 可用；
- 选中标的必须 eligible；
- 结果后 forward return 必须明确位于 decision 之后；
- 机会排名没有 runtime authority。

### 逐股/逐笔收益账本

调用 `validate_realized_pnl_ledger(frame, account_daily=...)`。每个 account-day 都必须同时通过 simple return 和 linked-log 恒等式。

## 物化快照

adapter 先将四张表输出为 Parquet/CSV，再运行：

```bash
.venv/bin/python scripts/materialize_post_training_account_snapshot.py \
  --strategy-id <strategy> \
  --model-or-score-digest sha256:<...> \
  --account-policy-family-digest sha256:<...> \
  --market-data-digest sha256:<...> \
  --adapter-digest sha256:<...> \
  --data-usage-digest sha256:<...> \
  --tree formal \
  --execution-semantics next_tradable_after_bar_close_raw_PIT \
  --daily <portfolio_daily.parquet> \
  --holdings <holdings.parquet> \
  --trades <trades.parquet> \
  --events <events.parquet> \
  --initial-nav 1000000 \
  --source-closure <source_closure.json> \
  --output-root <bundle/formal/snapshot>
```

isolated 必须是另一条命令，不得把 formal 目录复制成 isolated。

## 亚秒级派生报表

```bash
.venv/bin/python scripts/derive_post_training_account_reports.py \
  --snapshot-root <bundle/formal/snapshot> \
  --benchmark-levels <cloudridge.levels.csv> \
  --output-root <bundle/formal/reports>
```

该命令只允许读快照中的 `portfolio_daily.parquet`、manifest 和基准。收据中的四个上游计数必须都为 0。

## 性能与验收

```bash
.venv/bin/python scripts/benchmark_post_training_account_research_bundle.py \
  --portfolio-daily <performance-only-fixture.parquet> \
  --benchmark-levels <cloudridge.levels.csv> \
  --output <performance_receipt.json> \
  --rounds 20 \
  --p95-limit-seconds 1.0

.venv/bin/pytest -q \
  tests/unit/test_account_research_bundle.py \
  tests/unit/test_relative_performance.py \
  tests/unit/test_strategy_progressive_development.py

.venv/bin/ruff check \
  src/factor_lab/portfolio/account_research_bundle.py \
  scripts/materialize_post_training_account_snapshot.py \
  scripts/derive_post_training_account_reports.py \
  scripts/benchmark_post_training_account_research_bundle.py \
  scripts/validate_post_training_account_research_bundle.py \
  tests/unit/test_account_research_bundle.py
```

## 缓存失效

下列任一摘要改变，旧快照立即失效并新建目录：

- model/score digest；
- account-policy-family digest；
- market-data digest；
- adapter digest；
- data-usage digest；
- formal/isolated tree；
- execution semantics。

新增一列报表、换一个合法基准或更换展示格式不应重跑模型和账户；它们只生成新 DerivedReports receipt。
