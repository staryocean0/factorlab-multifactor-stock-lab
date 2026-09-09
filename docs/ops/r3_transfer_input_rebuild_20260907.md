# R3：2021—2025 同定义特征输入重建与映射

日期：2026-09-07；开发基点：`c35ad8329f321301cfb5d2d774a260c4aa06aa40`。这是云端—本地协作的后继开发，不重新审计 INFOCLOCK。

## 1. 当前交付及其边界

已实现 **有来源绑定的特征数组包 → 映射到原 K1 身份 → 历史前缀比较 → 2021—2025无标签支持 → 双时钟隔离特征仓**，以及71通道装配和冻结normalizer调用接口。

**尚未在云端实现或执行**用户本地未入库盘中生产器的“原始行情/成分 → H20金融残差/OT1/OT2”扩展生成；真实数据依赖及实际生产器在本地。后继本地任务包含这段有界桥接，不能把本构建器说成直接从行情一键完成全流程的执行器。真实四臂跨期评分也尚未接通，本任务不运行它。

这是一次输入重建任务，不是再做元数据盘点，不是新增神经模型实验。网络拟合=0，推理=0，checkpoint重载=0。生成历史暴露所需的原配方滚动OLS/滤波计算允许执行，须另报次数/范围，不能把它们混称为“完全没有任何计算”。

## 2. 保留的研究判断

INFOCLOCK确认2018—2020的14个state mask在实际推理上下文中全为1。`F−STATE_VALUE_PLUS_E`保留为原算法差异，不再解释成评价期动态mask信号。Reliability仍是变化的质量信息候选，但历史首次可读时间与泛化均未认证。

后继候选对比仍为已登记的 `F−STATE_VALUE_PLUS_E`、`BETA_RELIABILITY−BETA_ONLY`，四组原模型×两时钟×三seed，未来最多24个新期间评分任务；本轮不评分、不新训、不新增合并特征臂、不猜CloudRidge公式。2021—2025仍是已消费历史，不能改名fresh OOS。

## 3. 身份和宇宙：在上游确定，而不是最后切列

本轮保留原TIMEISO的股票队列和原位置（已报告3,982只），不新增上市股票，也不因股票后来退市、停牌或无数据而先删列。缺数据保留NaN并依原支持规则记录排除原因。这是固定原队列的迁移研究，不代表未来全部A股。

必须在成分/载体构建和cross-fit之前使用原股票位置及原定义。不能先用5,894只股票生成残差/交叉拟合，再切成3,982列冒充同定义；含2026的residual-only产品不得作为本任务输入。

允许数组存盘顺序不同，但source bundle必须提交 `symbol_fold_ids.npy`，明确每个source symbol在上游实际使用的原折号。构建器逐一验证该折号等于原symbol位置%5；再按名称映射symbol、factor和variant到原顺序。不以当前数组下标重新分折，不用“名称相同”掩盖fold不同。

factor、variant必须与原集合完全相同，缺项、重复或额外项均拒绝。原variant顺序为full_reference及crossfit_fold_0..4。原71通道registry原字节保留，channel70仍是原零age，不注入新月度信号。

## 4. 冻结规则及来源绑定

继续使用TIMEISO在2016年末成熟前缀选出的原工具JSON，不能重新评分选工具；复制原normalizer文件，不重新估计均值/尺度、不改架构/DMD/checkpoint。原网络训练配方完全不动。

本轮实际生产源码必须按**加载模块的 `__file__` 与真实SHA256**记录；不能仅写FactorLab HEAD。提供 `snapshot_loaded_sources(modules, output)`，由本地桥接在实际导入其数值模块后调用，至少纳入直接生产器、dirty timing helper、被调用的OT1 helper、滤波实现及桥接自身。无需封存整仓或强迫清理原脏工作区。构建器在开始和结束时复核这些已声明文件的字节。

这证明的是“当前声明加载的文件未变”，不是完整执行trace，也不是恢复原训练时所有源码或证明PIT。历史首次可读时间继续unknown；源清单成功不改变该状态。

## 5. Source bundle合同

每时钟一个独立目录，`bundle.json` schema为 `factorlab.r3_transfer_source_bundle@1.0`。只消费：

- `calendar.npy`、`symbols.npy`、`factor_ids.json`、`variant_ids.json`、`exposure_decision_positions.npy`；
- float32 `epsilon_history.npy`、`state_values.npy`、`stock_factor_exposures.npy`、`exposure_reliability.npy`；
- uint8 `state_available.npy`、`exposure_available.npy`；
- integer `symbol_fold_ids.npy`、`producer_sources.json`。

历史epsilon为`[calendar,symbol]`；state为`[6,calendar,14]`；exposure/reliability/mask为`[D5,symbol,14]`。不需要epsilon_future、labelled indices、scores或checkpoint张量；这些文件即使存在也不遍历读取。不得将未来标签用于输入构造。

manifest必须声明并绑定：

```json
{
  "schema_id": "factorlab.r3_transfer_source_bundle@1.0",
  "clock": "1430",
  "calendar_end": "2025-12-31",
  "reference_manifest_sha256": "sha256:<原store manifest实际摘要>",
  "frozen_selection_sha256": "sha256:<原选型JSON摘要>",
  "frozen_normalizer_sha256": "sha256:<原normalizer摘要>",
  "selection_freeze_end": "2016-12-31",
  "carrier_universe_policy": "incumbent_cohort_before_crossfit",
  "fold_policy": "explicit_incumbent_symbol_position_mod5",
  "historical_prefix_origin": "reused_accepted_arrays",
  "new_model_fits": 0,
  "selection_refit": false,
  "normalizer_refit": false,
  "labels_used_for_features": false,
  "artifact_digests": {"<上述13个文件名>": "sha256:<实际文件摘要>"}
}
```

原历史前缀可直接复用已验收数组；明确 `historical_prefix_origin=reused_accepted_arrays`。确由新生产器重算则填 `recomputed_from_bound_producer`，不得把复制比对写成独立前缀生成验证。两种模式均检查映射后的老前缀值与NaN支持完全一致；构建器本身不签署独立生产器重放结论。

新尾部的选中滤波器要续用真实历史上下文/原初始化。IIR等不能因为只输出2021+就从2021重新零初始化。可复用原历史因子基底以预热原选中滤波器；无需重新选择工具或重拟合全部历史股票暴露。

`artifact_digests`是raw SHA256，重新哈希正文，不信任文件内自带的canonical字段。绑定来自原回执还是本次新生成，须在反馈中区分。本轮源manifest、原manifest、选型、normalizer各自的外部摘要放入run spec。

## 6. 构建器实际执行

入口：`scripts/reaka_r3_build_transfer_inputs.py`；核心：`src/factor_lab/factor_rotation/reaka_r3_transfer_inputs.py`。

1. 验证两时钟独立来源、外部摘要、固定规则；先读截止元数据/日历，拒绝含2026的混合包。
2. 原calendar截至2020-12-31必须是新calendar的完全一致前缀；新calendar截止2025-12-31。交易日历由有界源提供，不把自然日当交易位置。本代码检查一致性，不认证外部交易日历来源。
3. symbol/factor/variant重映射及上游fold映射核对；完整保留原D5位置，2021+继续同一个2008-12-01锚点，不重新起算phase。
4. 以固定大小块写新memmap，逐块比较六个相关历史数组的值/NaN支持；拒绝非有限特征、无效mask或旧前缀漂移。原文件只读不覆盖。
5. 逐决策按十个H20端点历史epsilon全有限、当日任一暴露可用建立支持。所有未入选原因和日级数量写入 `daily_support.json`，不按标签或表现删样本。
6. 生成预测索引；另用 `decision_position+20 < len(calendar)` 给出成熟时间候选索引。它不是有限标签索引、更不是当时可成交性证明。保留年末未成熟预测行，不读取2026补标签。
7. 原normalizer、selection、registry按字节复制；`TransferFeatureStore.assemble_inputs`输出原10×71顺序，`normalized_inputs`使用复制的冻结参数。接口没有epsilon_future，调用assemble_batch会拒绝。
8. 两时钟轴一致后才发布 `stores/` 和成功result；另一时钟失败时不发布半成品。既有输出目录不覆盖，失败目录保留failure.json而非通过回执。仅为排错、尚未评分的构建错误可修复后用新目录重启，保留原因，不增加额外研究审批。

## 7. 云端验证与未覆盖

53项新增合成/接口测试通过；连同原INFOCLOCK35项回归共88项通过，零失败/错误/跳过。新增测试包括真实新Python进程构建双时钟特征仓、乱序映射与fold错误反例、全部六数组旧前缀、无标签文件、独立逐坐标71通道/normalizer对照、NaN支持、D5/年份/来源身份、半成品隔离和原文件不变。

这是小型合成数组，不是市场数据，不是原神经模型推理，也不是完整FactorLab测试。实际原始生产器、2021—2025真实数组、真实特征仓构建和四臂评分均未执行。回执见 `cloud_results/r3_transfer_inputs_20260907/execution_receipt.json`。

下一项本地任务见 [执行记录](cloud_local_communication_R3_transfer_inputs_20260907.md)，仍由云端验收，现有研究结果不倒填、不重训。
