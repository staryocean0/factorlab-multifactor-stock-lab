# REAKA V2 Stage4 可观测条件×因子配对白皮书

## 责任边界

Stage4 把用户已声明的金融机制变成可审阅证据。机器负责 PIT join、同口径条件内外差、factor-active episode、年度和episode离散度；用户负责判断这些结果是否符合金融机制。Stage4 不选择权重、不构造股票分数、不决定K。

## 冻结假设

| ID | 因子组 | `S_obs` | 用户预期 |
|---|---|---|---|
| H_INDEX_UP | 指数 | 上涨 | 增强 |
| H_INDEX_DOWN | 指数 | 下跌 | 减弱 |
| H_INDUSTRY_UP | 行业 | 上涨 | 增强 |
| H_INDUSTRY_SIDEWAYS | 行业 | 横盘 | 增强 |
| H_INDUSTRY_DOWN | 行业 | 下跌 | 减弱 |

规模不进入本轮配对。指数横盘是中性参照，不建立“接近零即通过”的伪等价检验。

## 数据身份

因子组结果来自第一轮 K1 已选持仓的指数/行业 linked-log 贡献，只能用于已消费历史的机制归因，不能冒充因子本体收益。状态必须重新从 Stage3 的上一自然月 `S_obs` join；旧 selector panel 中同月 `trend` 列必须丢弃。

2011-05至2016-12是开发材料；2017只列示；2018-2025是已消费重复对照。后两者不得改变五个假设、方向或统计口径。

## 统计量

对每个假设、时钟和数据角色：

```text
lift = mean(factor contribution | S_obs condition)
       - mean(factor contribution | other S_obs states)
```

增强预期要求正方向，减弱预期要求负方向。年度表只在当年同时存在条件内外月份时计算；episode表以独立 `S_obs` episode 为单位，并相对同角色、同时钟的条件外均值报告差。`factor_active_episode_count`只表示该episode有有限、可测贡献，不表示机制通过。

机器可以报告 `aligned/opposed/mixed/insufficient` 的描述性方向，但不得签署金融通过。最终只生成 `advisor_interpretation_request`，由用户决定保留、修改或拒绝机制。

## 权限

Stage5、Stage6、模型训练、operator容量、residual、SSA、账户、指针和生产关闭。
