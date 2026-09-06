# REAKA P7 市场输入重建白皮书

## 结论

P7 v1 的两个 K1 score panel 数学上通过，但旧年度 tradeability 分母漏掉 `000638`，导致
两个时钟各 143 个 score-coordinate 没有市场事实。DataHub 已把同一根因下的证券日元数据
和 XDXR 事件分别修复为固定、未 serving 的候选；FactorLab 随后只重建 market panel，
没有重算 score、读取 checkpoint、训练模型或执行账户。

当前执行合同是 `reaka_intraday_portfolio_mapping_market_rebuild@1.4.json`。它继承并保留
@1.0—@1.3 及四个发布前 incident，不追改旧合同迎合结果。

## 固定语义

- score：从已接受 v1 formal/isolated 逐字节复制；digest 必须保持
  `7ad947...` 与 `29c643...`。
- raw execution：继续使用两个时钟的 `next_tradable_after_bar_close` target-fill。
- metadata：仅新增 DataHub 固定 `000638` 2011—2020 证券日候选。
- tradeability：固定 raw-canonical 正 bar + 有效期价格限制规则；full-day/known intraday
  保持不可买卖，not-full-day 只表示当日有成交。
- HFQ：其他股票沿用 V9 与原十只 bounded XDXR。`000638` 的 V9 行数为 0，使用精确 TDX
  successor 中唯一一条 2013-04-10 category-1 事件，沿用原 previous-close 公式。事件日在
  停牌区间内时，取第一条后续可交易行携带的 previous-tradable close；因子仍从事件日起生效。
- provenance label：数学公式仍是 `bounded_xdxr_event_formula_v1`；目标专属来源写在合同和
  closure，不扩大 validator 白名单。
- 市值：继续使用固定 PIT 月度总市值，并在每个决策截面重算三分位。

## 发布前 incidents

1. 脚本入口漏仓库根目录，`scripts.*` 导入失败。
2. `000638` 同样被旧 V9/XDXR 分母漏掉，触发未登记 HFQ 缺口。
3. 2013-04-10 除权事件日在全日停牌内，没有同日 market row。
4. 新 provenance label 不在精确 validator 白名单中。

四次均在原子发布前停止：正式 score/market 文件、账户结果、策略结果和 post-2020 读取均为 0。

## 最终结果

- formal/isolated 11 个文件逐字节一致。
- 每时钟 score 853,732 行，digest 与 v1 完全相同。
- 每时钟 market 6,459,216 行，主键重复 0、post-2020 行 0。
- 所有 score-coordinate 均可连接；`000638` 为 143/143。
- `000638` 每时钟有 1,986 个正市场日，HFQ multiplier 只取 1 或 2。
- bounded XDXR 行从 20,680 增至 22,666，新增 1,986 行全部属于 `000638`；V9 行仍为
  6,436,550。
- raw × HFQ = accounting execution/close 的最大绝对误差均为 0。
- 143 个目标决策坐标的 size bucket 空值为 0。

该结果只关闭市场输入基础设施 gap。账户执行、年度 session、TopN 政策选择、策略变更和生产
仍未授权。

执行与后续边界见
[`reaka_intraday_portfolio_mapping_market_rebuild_workflow.md`](../user/reaka_intraday_portfolio_mapping_market_rebuild_workflow.md)。
