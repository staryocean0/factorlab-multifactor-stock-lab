# REAKA P6.4.4 Fit-Prefix Per-Seed K1 后继

三方数学—金融对齐审计通过后，本步固定`d8-h8 / LR0.03 / max3 complete cycles / K1-r0`。
不重开容量、LR或coverage搜索。

每个seed从零训练最多3个完整无放回coverage cycle，仅按fit-prefix固定batch canonical loss
选最小值，平局选最早cycle。2017不参与checkpoint选择，只用于冻结checkpoint后的RankIC/spread评审。

两时钟使用同一配置和同一算法，formal/isolated独立重建。硬门为每seed best fit loss低于DMD后pre-loss、
参数有限、条件数安全，以及三种子集成的成员/输入扰动和2017 RankIC/spread。谱半径只作diagnostic。

2018--2020、P6.5、账户和生产仍关闭。即使通过，也只能成为已消费历史上的回顾候选，等待真正未见确认。
