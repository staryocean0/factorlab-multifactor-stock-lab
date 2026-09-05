# 多因子状态—因子配对研究：数据准备操作手册

## 目标

本手册把“正式研究前的数据准备”变成可重复执行的开工门。执行顺序固定为：上游权威核对 → V9 行业指数 → V9 个股因子面 → 全数据合同 → V9 状态复验 → 打开配对门。任何一步失败，都只修对应输入，不绕过检查。

## 1. 读取机器合同

先读：

```text
docs/ops/multifactor_research_data_contract@1.0.json
```

合同分别记录必需数据、限域权限、非阻断增强缺口和明确禁用版本。不得使用 `latest` 或按文件夹修改时间猜权威。

## 2. 核对 DataHub 当前权威

DataHub 当前股票复权必须精确为：

```text
adjust_factors_cn_a_xdxr_v9_20260814
bars_cn_a_1d_qfq_canonical_xdxr_v9_factorlab_2009_2025_20260814
```

V8、Sina QFQ 和百度复权因子均不得进入活跃输入。行业构建代码必须从 DataHub 的中央复权权威读取版本，不得另写旧字面量。

## 3. 构建 V9 自建行业指数

使用 DataHub `scripts/build_common_history_industry.py` 构建不可变后继：

```text
industry_index_common_history_cn_a_2009_2025_v5_xdxr_v9_media_repair_20260814
```

必须同时包含 L1/L2/L3，每层 equal_weight、market_cap、dir_signal、vol_signal 四个载体；保留 V4 已确认的传媒桶覆盖修复。每层的 replay、prefix invariance、coverage 和 certification 必须通过。

## 4. 重建 165 个非财务因子面

```bash
PYTHONPATH=src .venv/bin/python \
  scripts/factor_rotation/materialize_multifactor_nonfinancial_v2.py
```

输出固定为：

```text
output/factor-rotation/factorlab_multifactor_stock_nonfinancial_165f_2009_2025_v2_xdxr_v9_20260814
```

验收必须看到 `factor_count=165`，且 `lineage_audit.json.bar_parent.authority` 为 `xdxr_v9_fixed_qfq_return_and_feature_research`。旧 V1 的 raw-bar 因子面只能作历史审计。

## 5. 生成并复核全数据准备回执

先把 V90 的 9 条物理序列全部对齐到 204 个月度决策时点，并检查
严格的 `source_available_at < decision_as_of`：

```bash
PYTHONPATH=src .venv/bin/python \
  scripts/factor_rotation/materialize_multifactor_macro_input.py

PYTHONPATH=src .venv/bin/python \
  scripts/factor_rotation/check_multifactor_macro_input.py
```

验收必须显示 9 条序列、204 个决策月、逐行血缘齐全；同时必须把
6 条消费者合同认证的条件序列与 3 条原始父序列分开。原始父序列
可供学术研究和血缘复核，但不默认获得状态投票权。

随后生成总数据回执：

```bash
PYTHONPATH=src .venv/bin/python \
  scripts/factor_rotation/materialize_multifactor_research_data_readiness.py

PYTHONPATH=src .venv/bin/python \
  scripts/factor_rotation/check_multifactor_research_data_readiness.py
```

合格结果必须是：必需数据失败数为 0，九类研究表面全部验证；宏观增强缺口可以存在，但必须原样列出。严格年报数据应显示 `READY_LIMITED_HONEST_GAP`，不是伪装成全市场无缺口。

九类中的市场指数面同时固定云脊 ResultPackage 和中证全指 000985 快照的路径、身份与 SHA-256。两者角色不同：云脊是项目自建状态载体，000985 是广义市场参考；不得只拉一个指数后让它兼任所有市场含义。所有研究读取均在 2025-12-31 截止。

## 6. 重新验证状态目录

数据回执通过仍不等于状态已准备。当前已完成 V9 分布/波动顺序重放、12 行业载体迁移审计和 AMS-008 四轮冻结协议重放；新权威目录为 `docs/ops/authoritative_market_state_catalog@2.0.json`，校验已通过。

## 7. 开工停止线

以下准备条件已满足，下一步可以进入状态—因子配对预登记：

- 数据准备检查通过；
- V9 状态目录检查通过；
- 每个因子、状态、窗口、成本与多重检验家族在读取未来收益前冻结；
- 研究仍遵守年度顺序材料生成和整案重建合同；
- `fresh_oos=false`、`production_authority=false` 保持不变。
