# P7 市场输入重建交接

市场输入基础设施已经通过主控复核，账户层尚未打开。

- 固定输入：`reaka_intraday_portfolio_mapping_inputs_v2_2011_2020`
- 两时钟 score：原字节保留；853,732 行/时钟
- 两时钟 market：6,459,216 行/时钟
- 全 score-market join：853,732/853,732
- `000638`：143/143/时钟，size bucket 零空值
- formal/isolated：11/11 文件逐字节一致
- post-2020、账户结果、政策结果、生产写入：均为 0

唯一下一动作不是 Stage7。项目早已完成历史 Stage7；当前应在用户复核后另行冻结 P7
account-execution admission，只打开 2009 年 session。2009 完成并由用户复核前，不得打开
2010，更不得批量跑 2009—2020。
