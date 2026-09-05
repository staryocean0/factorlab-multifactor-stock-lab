# FactorLab REAKA 多因子选股研究

本仓库研究自研市场、大小盘、行业因子与 REAKA 条件预测框架的组合。
现行入口是 [current@1.3](docs/ops/reaka_multifactor_current_manifest@1.3.json)，
按[工作流 V1.3](docs/user/reaka_multifactor_current_workflow_v1_3.md)执行。
数学定义以[现行白皮书](docs/ops/reaka_foundation_whitepaper_v1_3.md)和
[机器口径合同](docs/ops/reaka_foundation_semantics@1.1.json)为准。

本轮状态：基础设施口径已建立统一合同；研究执行关闭，等待用户通知数据补齐。
代码一致性、数据完整性、历史证据有效性与策略经济效果分别报告。
旧 Stage4 存在重复月份及来源闭包缺口，不能进入金融验收；已有正负结果均不因此重算或改写。

安装 Python 3.11 环境后，运行不依赖行情文件的现行基础设施检查：

```bash
python -m pip install -e .
python -m pip install 'torch>=2.7,<3' --index-url https://download.pytorch.org/whl/cpu
python scripts/validate_reaka_foundation.py
pytest -q tests/unit
```

`python scripts/validate_theme_package.py` 另行严格核验数据清单；上传未完成时失败应保留。
默认 push/PR 不启动数据检查；收到用户通知后可运行上述命令或手动触发 CI 的数据任务。
`python scripts/audit_reaka_foundation.py` 专门审计历史 current@1.2 的证据，已知缺口不能冒充现行代码错误，也不能被代码检查通过消除。

旧 current@1.0—1.2、旧白皮书、旧注册表及旧工作流保留作历史材料。
未列入 current@1.3 五位一体闭包的文件无现行规范权；历史脚本会在写入前拒绝执行。
本仓库合同不变更用户本地 FactorLab 指针，不授权训练、选 K、账户执行或生产。
数据仅到 2025 年；2018—2025 已消耗，`fresh_oos=false`。
IEEE 全文仅供内部研究，见 [NOTICE.md](NOTICE.md)。
