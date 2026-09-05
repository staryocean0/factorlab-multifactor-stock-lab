# REAKA 论文核心策略族工作流

## 1. 先看结论

一次冻结训练版 `reaka_paper_core_best_practice_v2` 已完成：训练健康六门全部通过，扣费年化多空由公式忠实 V1 的 `-7.00%` 改善到 `-2.54%`，Rank IC 提升到 `0.0260`，但全期收益仍为负、Sharpe 为 `-0.115`，且未打赢旧论文启发代理的 `+5.55%`。所以当前结论是“训练健康通过、经济表现未通过”，不得替换旧代理或 incumbent。

上述都是历史实证，不再代表当前流程位置。当前 V2 权威恢复点是 `pair_hypothesis_ledger`：旧 930 组机器扫描保留为 `machine_complete/advisor_review_pending`，先由 AI 与用户完成金融机制范围审查，未通过前不再训练神经网络、搜 Koopman 容量或开残差。

无记忆 AI 和人类协作者先读：

1. [`REAKA 人类供给—模型学习职责白皮书`](../ops/reaka_human_model_authority_whitepaper.md)；
2. [`状态—因子配对同步研究与策略装配手册`](../ops/reaka_state_factor_joint_research_whitepaper.md)：九阶段权威流程；状态与因子没有单边先后，先审查机制配对，再冻结透明核心、验收神经保真、校准算子、最后开残差；
3. [`论文核心最佳实践 V2 白皮书`](../ops/reaka_best_practice_v2_whitepaper.md)；
4. [`V2 三层收益归因白皮书`](../ops/reaka_best_practice_v2_layer_attribution_whitepaper.md)；
5. [`REAKA 论文公式版 V1 白皮书`](../ops/reaka_paper_v1_whitepaper.md)；
6. [`公式版诊断证据`](../ops/evidence/macro_regime_v1_vs_reaka_v1/round3a_reaka_paper_v1_implementation_diagnostic_20260810/README.md)；
7. [`永久研究台账`](../ops/macro_regime_conditioned_multifactor_research_ledger.md)；
8. [`双策略测试规范`](../ops/macro_regime_dual_strategy_test_spec.md)。

## 2. 恢复时不要混淆四个身份

| 身份 | 用途 | 当前状态 |
|---|---|---|
| `macro_regime_conditioned_multifactor_v1` | incumbent | 生产指针未改 |
| `reaka_adaptive_koopman_v1` | 旧论文启发代理 | Round 3A 临时研究领先 `+5.55%`，但不是完整论文架构 |
| `reaka_paper_formula_faithful_v1` | 新论文公式版 | 架构完成；月频适配训练健康阻断，不可晋级 |
| `reaka_paper_core_best_practice_v2` | 论文核心+项目训练护栏 | 健康门通过；扣费年化 `-2.54%`，经济表现不支持晋级 |

旧代理的历史结果不回写、不删除；新公式版也不能借用旧代理的 `+5.55%` 当自己的收益。

V2 也不能把自身结果回写成 V1 的成绩。V2 增加了训练前缀目标对齐、状态/潜空间健康正则、宏观弱状态线索与多抽样，因此必须始终保留独立身份。

## 3. 常规验收

```bash
.venv/bin/python -m pytest -q tests/unit/test_reaka_paper_v1.py
.venv/bin/python -m pytest -q tests/unit/test_reaka_best_practice_v2.py
.venv/bin/python -m pytest -q tests/unit/test_macro_regime_multifactor_research.py
.venv/bin/python -m ruff check \
  src/factor_lab/factor_rotation/reaka_paper_v1.py \
  src/factor_lab/factor_rotation/reaka_paper_v1_runtime.py \
  src/factor_lab/factor_rotation/reaka_paper_v1_health.py \
  src/factor_lab/factor_rotation/macro_regime_research_ledger.py \
  scripts/run_macro_regime_dual_strategy_reaka_paper_v1.py \
  scripts/audit_reaka_paper_v1_health.py \
  tests/unit/test_reaka_paper_v1.py \
  tests/unit/test_macro_regime_multifactor_research.py
```

V2 一次冻结训练与独立重放：

```bash
.venv/bin/python scripts/run_macro_regime_dual_strategy_reaka_best_practice_v2.py
replay_dir=$(mktemp -d /tmp/factorlab-reaka-best-practice-v2-replay.XXXXXX)
.venv/bin/python scripts/run_macro_regime_dual_strategy_reaka_best_practice_v2.py \
  --output-dir "$replay_dir" \
  --no-ledger
.venv/bin/python scripts/verify_reaka_best_practice_v2_replay.py \
  --replay-dir "$replay_dir"
```

正式目录已有结果时，第一条命令只验证并复用，不应重训。重训重放必须写新临时目录。当前封存重放已经证明 spec/result/health 三份 JSON 字节一致。

V2 三层归因与独立重放：

```bash
.venv/bin/python scripts/run_macro_regime_dual_strategy_reaka_best_practice_v2_layer_attribution.py
attribution_replay_dir=$(mktemp -d /tmp/factorlab-reaka-v2-attribution-replay.XXXXXX)
.venv/bin/python scripts/run_macro_regime_dual_strategy_reaka_best_practice_v2_layer_attribution.py \
  --output-dir "$attribution_replay_dir" \
  --no-ledger
.venv/bin/python scripts/verify_reaka_best_practice_v2_layer_attribution_replay.py \
  --replay-dir "$attribution_replay_dir"
```

归因使用同一 fit 的四条 nonlinear decoder 路径，不训练四套变体。当前 Shapley 为因子 `-3.53%`、状态 `+0.69pp`、残差 `+0.30pp`；状态与残差单独加入都变差，约 `+2.16pp` 来自二者协同。训练损失与健康护栏如需独立贡献，必须另做预注册重训消融。

健康审计：

```bash
.venv/bin/python scripts/audit_reaka_paper_v1_health.py
```

当前这条命令应返回退出码 `2` 和 `status=blocked`；这是发现并拦住训练健康问题，不是审计器故障。

## 4. 封存结果和确定性重放

正式证据目录已存在时，下列命令只验证已存的 spec/result 并复用台账序号 16，不应重训或新增科学票。健康审计命令同理复用 blocked validation 序号 17；首次提交前源码收尾已由序号 18 验证产物不变：

```bash
.venv/bin/python scripts/run_macro_regime_dual_strategy_reaka_paper_v1.py
.venv/bin/python scripts/register_reaka_paper_v1_implementation_migration.py
```

真正的独立字节重放必须写到新临时目录：

```bash
replay_dir=$(mktemp -d /tmp/factorlab-reaka-paper-v1-replay.XXXXXX)
.venv/bin/python scripts/run_macro_regime_dual_strategy_reaka_paper_v1.py \
  --output-dir "$replay_dir" \
  --no-ledger
sha256sum \
  docs/ops/evidence/macro_regime_v1_vs_reaka_v1/round3a_reaka_paper_v1_implementation_diagnostic_20260810/spec.json \
  "$replay_dir/spec.json"
sha256sum \
  docs/ops/evidence/macro_regime_v1_vs_reaka_v1/round3a_reaka_paper_v1_implementation_diagnostic_20260810/diagnostic_result.json \
  "$replay_dir/diagnostic_result.json"
```

当前封存收据已证明两个文件分别字节一致。

## 5. 数据使用规则

- 当前月频 adapter 只能做 implementation diagnostic，不能声称复现论文 Alpha158 benchmark。
- 历史收益必须在当期决策前严格可见；不可见的窗口整体丢弃，不补零、不顺延。
- 完整窗口只用当期之前的特征和收益；改写未来行情不得改变历史窗口。
- 公式忠实 V1 核心不使用慢宏观；V2 已把 6 路折前缀缩放宏观上下文登记为项目扩展，不能回写成论文明示输入。

## 6. 已打开考卷禁止事项

2021—2025 已经被 Round 3A 打开。下列动作都不能产生新科学票：

- 换模型名、换 mechanism 名或重打包同一目标数据；
- 因 V1 的 `-7.00%` 或 V2 的 `-2.54%` 改 epoch、learning rate、seed、operator count、loss weight 或 diffusion steps；
- 从当前年度结果挑最好配置后再称 OOS；
- 把诊断运行追加成 scientific trial。

台账层的 `exam_scope_digest` 会按 target/action/universe/period/fold 拦截这类重复消费。

## 7. 两个不可混淆的恢复点

**策略研发主线**从[`状态—因子配对同步研究与策略装配手册`](../ops/reaka_state_factor_joint_research_whitepaper.md)的步骤 1 恢复，对应责任项 `bd://fl-60b7q`。现有 186 原子因子、5 个结构就绪上下文、930 组机器扫描和 3 条机器候选关系保留，但只是待顾问审查材料。因子覆盖不足只能写 `factor_coverage_gap`，不得否决状态。

**论文日频 benchmark 输入线**仍由 `bd://fl-wtbm9` 跟踪。它负责完整可重放的日频 Alpha158 + 同步历史收益、论文未公开超参数和固定消融、训练健康收据及新鲜时间 lockbox。该输入线不能替代状态—因子配对研究，也不能因日频面就绪自动产生策略收益或晋级权。

两条线汇合的条件是：三个用户金融顾问回执已绑定具体配对和透明核心，日频输入与训练健康也已通过。之后才按装配手册步骤 6—8 先验收神经保真，再校准 Koopman 容量、开放残差、完成组合归因，并与 incumbent 做同口径 battle。
