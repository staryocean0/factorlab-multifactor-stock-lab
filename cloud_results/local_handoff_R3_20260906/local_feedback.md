# LCL-R3-NOFIT-20260906-01 本地反馈

任务：LCL-R3-NOFIT-20260906-01
执行方：本地 Codex controller
时间：2026-09-06
状态：本地已反馈；**不是**云端已复核；**不是** PIT / fresh OOS / 盈利 / 生产通过。

## 身份

- 主题仓分支 `codex/reaka-foundation-audit-20260905` 提交 `d6804cdb2b321f7b5ae74eb98fc8dcc5f59613d6`
- 脚本 `scripts/reaka_r3_frozen_compare.py` SHA-256 `188d9a54746d95e079770cef701837d827880c61bc542dd2ad6f9a4729367e9f`（与任务书一致）
- 原 FactorLab `master` `b39bb12f43a46b165d18db93191a669234077444`
- 未修改 ensemble、门禁、脚本或冻结输入
- 未训练、未加载 checkpoint 重新推理、未读取 DataHub 分钟、未账户重放、未调用 Actions、未打开 2026

## 环境与命令

- python `3.13.5`；numpy `2.2.4`；platform `Linux-7.1.8+deb13-amd64-x86_64-with-glibc2.41`
- 实际命令：

```bash
python3 scripts/reaka_r3_frozen_compare.py \
  --factorlab-root "/home/starryocean/桌面/量化/baylum terminal 0.4.1/factor_lab" \
  --output-dir "/home/starryocean/桌面/量化/baylum terminal 0.4.1/factor_lab/tmp/LCL-R3-NOFIT-20260906-01/run01"
```

- 退出码：**0**
- 本地主题仓测试：`python3 -m pytest -q tests/unit/test_reaka_r3_frozen_compare.py` 退出码 0（13 passed）
- 输出目录事先不存在，位于 `tmp/`，未写入 sealed `data/` 或 `output/`

## 结果摘要

两时钟均为 `completed_consumed_diagnostic`。K1 2017 review 汇总与原 formal 回执在 atol=1e-4 内复原（1430 rankic error ≈ 2.8e-17，1445 为 0；spread error 均为 0）。日期 2017-01-06..2017-12-29，每天 n≥1447，无 2026 行。paired_daily 490 行 = 2 时钟 × 49 日 × 5 预测器。

### 1430
- status: `completed_consumed_diagnostic`
- support_rows=82321, support_days=49
- receipt parity: passed=True, mean_rankic_error=2.7755575615628914e-17, mean_spread_error=0.0, atol=0.0001
- formal_blob `57a1ab18761e39cb66001090ac1782bd8eda2d8d`; input_manifest `sha256:7b8050270c72894ff2e6c67f1fb4a5a5513ca46e8cc0b8c02ed7e0ce3523dfd3`

| predictor | mean_rankic | mean_K1_minus_baseline | mean_decile_spread | mean_top30_minus_universe |
|---|---|---|---|---|
| `K1` | 0.159926 | 0.000000 | 0.063503 | 0.044997 |
| `last_epsilon` | 0.050194 | 0.109732 | 0.016648 | -0.019497 |
| `mean10_epsilon` | -0.133221 | 0.293147 | -0.050429 | -0.041041 |
| `negative_last_epsilon` | -0.050194 | 0.210120 | -0.016648 | -0.045886 |
| `negative_mean10_epsilon` | 0.133221 | 0.026705 | 0.050429 | 0.038769 |

- closest baseline by mean_rankic: `negative_mean10_epsilon`; phase deltas (K1−baseline)={'0': 0.023365692767411544, '1': 0.03268055705514344, '2': 0.03202343803545132, '3': 0.018307338818194886}

### 1445
- status: `completed_consumed_diagnostic`
- support_rows=82321, support_days=49
- receipt parity: passed=True, mean_rankic_error=0.0, mean_spread_error=0.0, atol=0.0001
- formal_blob `ab75bd55f2a990dffc2036fa2f03a6295e88ec64`; input_manifest `sha256:e979fce98e3a6e67f6e5b2bef2701f100d2b174fcdef4539e417ba3aa0c9a7e7`

| predictor | mean_rankic | mean_K1_minus_baseline | mean_decile_spread | mean_top30_minus_universe |
|---|---|---|---|---|
| `K1` | 0.161526 | 0.000000 | 0.064994 | 0.042900 |
| `last_epsilon` | 0.049098 | 0.112428 | 0.015552 | -0.020446 |
| `mean10_epsilon` | -0.134393 | 0.295919 | -0.051103 | -0.041647 |
| `negative_last_epsilon` | -0.049098 | 0.210623 | -0.015552 | -0.046618 |
| `negative_mean10_epsilon` | 0.134393 | 0.027133 | 0.051103 | 0.038189 |

- closest baseline by mean_rankic: `negative_mean10_epsilon`; phase deltas (K1−baseline)={'0': 0.02641789654427561, '1': 0.030146642522431082, '2': 0.03196887472620067, '3': 0.019594160378808567}


科学读取限制（脚本已写入，此处不升级）：

- 已消费 2017 review，不是 fresh OOS。
- 四个基准是固定、零拟合的 epsilon 方向；不是条件特征消融，也不是选方向后的结果。
- 无 iid 标准误/p 值。
- 无尺度校准 MSE、总收益或账户结论。
- `full_pit_certified=false`，`production_authority=false`。

观察（仅相对这 49 个已消费 H20 端点）：K1 mean rankIC 约 0.160/0.162，四个固定基准里最接近的是 `negative_mean10_epsilon`（约 0.133/0.134）。K1 相对该基准的配对差约 +0.027，四个 phase 均为正。这不构成 successor 晋级，也不识别条件特征增量。

## 产物

本地运行目录（含原始大数组之外的小结果）：

- `/home/starryocean/桌面/量化/baylum terminal 0.4.1/factor_lab/tmp/LCL-R3-NOFIT-20260906-01/run01/comparison.json`
- `/home/starryocean/桌面/量化/baylum terminal 0.4.1/factor_lab/tmp/LCL-R3-NOFIT-20260906-01/run01/paired_daily.csv`

回传到主题仓的小文件：

- `cloud_results/local_handoff_R3_20260906/comparison.json`
- `cloud_results/local_handoff_R3_20260906/paired_daily.csv`
- `cloud_results/local_handoff_R3_20260906/local_feedback.md`

epsilon / inference_rows / 分数 npy 留在原 FactorLab output 树，未上传。

## 未执行 / 未验证

- 条件特征独立增量、重训消融、K 搜索、残差网络、账户重放、全量 PIT、2026 数据
- 未把负/弱结果改写成通过
