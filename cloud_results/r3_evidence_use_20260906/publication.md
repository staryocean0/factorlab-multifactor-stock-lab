# R3 脚本补交与当前执行入口

本目录随当前提交补交到 `codex/reaka-foundation-audit-20260905`，基底为 `bfe0f0ae0949154aa6c4019144bac5cdc283e9bc`。本次没有合并 main，没有启动 GitHub Actions。

## 本地直接从 GitHub 取用

真实计算任务仍为 **LCL-R3-NOFIT-20260906-01**。请先读取最新 [沟通记录](../../docs/ops/cloud_local_communication.md)，再读 [裁决报告第5节](../../docs/ops/r3_evidence_use_adjudication_20260906.md)。

脚本：[reaka_r3_frozen_compare.py](../../scripts/reaka_r3_frozen_compare.py)。测试：[test_reaka_r3_frozen_compare.py](../../tests/unit/test_reaka_r3_frozen_compare.py)。两者保持原交付包字节，没有改预测口径、原分数或冻结常量。本地不需要再手工搬运交付包，也不应覆盖原 FactorLab 脏工作区。

在有 NumPy、SciPy 的本地环境，从主题仓工作树执行；输入根指向原数据所在的 FactorLab，新输出目录必须不存在：

```bash
python -m pytest -q tests/unit/test_reaka_r3_frozen_compare.py
python scripts/reaka_r3_frozen_compare.py \
  --factorlab-root /实际/FactorLab \
  --output-dir /实际/FactorLab/tmp/LCL-R3-NOFIT-20260906-01/run01
```

只读取原 2017 分数、坐标和 epsilon，与四个固定零拟合基准比较；不拟合、不加载 checkpoint 重推理、不重放账户。若已有同口径结果，先交其身份与明细，不重复计算。输入缺失/漂移时保留失败，不改摘要、不放宽口径。回传 `comparison.json`、`paired_daily.csv` 与执行说明，大数组留本地。

## 原编写状态与本次发布状态分开

原裁决报告及 `execution_receipt.json` 按交付包原字节保存，其中“尚未写回 GitHub”和 `github_written=false` 描述的是上一轮编写时的状态，不是这次发布后的当前状态。本条是发布补充；不改写旧回执来假装上轮已提交。

本次发布前，当前云端会话重新运行同一份脚本的 13 项针对性测试和 6 项描述算术检查，均通过；重复复跑不增加独立市场证据。新回执位于 [publication_checks.json](publication_checks.json)。真实本地分数对照尚未执行，R2 的 `completed_with_limits` 状态不变。

脚本 SHA-256：`188d9a54746d95e079770cef701837d827880c61bc542dd2ad6f9a4729367e9f`。Git blob：`2bb0f6dd326091d8aa35cc7ce9b73b5244e70f01`。
