# LCL-R3-COND-20260906-01 无训练收尾增量

任务：LCL-R3-COND-20260906-01（同一任务追加，不是新训练任务）
执行方：本地 Codex controller
时间：2026-09-06
状态：本地已反馈增量；**未**重跑 `reaka_r3_condition_compare.py`；**未**新增 F/H/E 拟合；**未**重开 R2；**未**账户重放；**未**调用 Actions。

依据桌面文档 `REAKA_R3_condition_cloud_review_20260906.md` 第6节。验收原文已落库：
`cloud_results/local_handoff_R3_condition_20260906/cloud_acceptance/REAKA_R3_condition_cloud_review_20260906.md`。

## 6.1 每 seed 评价（只用已保存分数）

六个 H 分数摘要与 `seed_fit_receipts.json` 一致；六个 F 分数摘要与原 formal 一致。沿原 2017 review 索引、同标签、同股票顺序，对每个 seed 调用既有 `daily_comparisons`/`summarize`，K1 标注为 F。未挑最好 seed。

| 时钟 | seed | F mean RankIC | H mean RankIC | F−H |
|---|---:|---:|---:|---:|
| 1430 | 11 | 0.155524 | 0.141293 | 0.014231 |
| 1430 | 29 | 0.156984 | 0.136844 | 0.020139 |
| 1430 | 47 | 0.148857 | 0.148614 | 0.000244 |
| 1445 | 11 | 0.155828 | 0.126901 | 0.028927 |
| 1445 | 29 | 0.161647 | 0.142494 | 0.019153 |
| 1445 | 47 | 0.151227 | 0.145247 | 0.005980 |

六个 seed 的 F−H 均为非负；1430 seed47 接近零。**不能把集成正差写成每个 seed 都有同等增量。**

用保存的 float32 H/F 分数重做逐日 rank-z 集成后，两时钟 H/F 均值与原 `comparison.json` 差为 **0.0**。本次没有因 dtype 出现需要改容差的偏差。

产物：`per_seed_metrics.json`、`per_seed_daily.csv`（588 行 = 2 时钟 × 3 seed × 2 预测器 × 49 日）。

## 6.2 来源与持久化

见 `source_persistence.json`。

- 原 `verify_source_blobs` 仍绑定 fit-prefix / training / preflight 三文件，当前 blob 与设计一致。
- 实际还消费 `reaka_paper_v1.py`（blob `feeb5716…`）、`reaka_stage6_daily_engine.py`（`8ccb1dd0…`）、`reaka_stage6_parameter_calibration.py`（`84fa10fc…`）。这是当前 FactorLab 快照身份，**不能证明**它们就是历史 F 训练当时的字节。
- 两时钟 `normalizer_from_store` 摘要与 wiring 记录一致（1430 `0bbf62be…`，1445 `edfea759…`）。原 F formal 未保存 normalizer digest，故这不是历史 F 运行时证书。
- review 有序坐标摘要 `sha256:bb8cdc3056b7bf585f71282032a8983b6a07aaf48e625029eb215c578daad926`，n=82321，2017-01-06..2017-12-29；沿用 NOFIT 输入/formal 身份。
- **纠正**：上次 `local_feedback.md` 写“权重留本地”不成立。runner 在写出 npy 后删除内存模型，`run02` 中无 checkpoint。该次 H **不可重新载入**。不会为填这个洞而重训并称为原模型。
- CPU/CUDA 后端差异继续列为未隔离因素，本增量不新训 F。

## 6.3 文字与后继检查

将“历史 epsilon 的表示学习解释了现任相对固定规则的大部分优势”收回。准确表述：

**在现有已消费样本中，H 也高于这四个固定规则，F 进一步高于 H；不同信息输入、学习过程和训练环境的作用尚不能被表述为百分比归因。** H 保留金融残差历史，仍包含上游残差化信息。

原 runner、原比较结果和失败 `run01` 原位保留，不改写以消除问题。后继测试：FactorLab 路径改为 `FACTORLAB_ROOT` 环境变量；合成输入上拒绝非有限差值。云端若无本地根，这些 FactorLab 测试应 skip，不得伪装全绿。

## 未执行

未重跑训练 runner；未增加 F/H/E 拟合；未重开 R2；未账户重放；未 Actions；未合并 main。
