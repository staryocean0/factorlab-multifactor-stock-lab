# FactorLab REAKA 多因子选股研究

研究自研市场、大小盘、行业及个股信息，如何借助条件预测改善 A 股横截面选股。既有产品是满仓主动多头；研究中的风险控制不自动把产品改为中性组合。

**接手从 [任务工作流](docs/user/reaka_multifactor_current_workflow_v1_4.md) 开始。** 当前版本由 [CURRENT.json](CURRENT.json) 唯一定位；具体进度只在 [研究状态](docs/ops/research_state.json) 维护，按需阅读 [文档索引](docs/INDEX.md) 与 [数学白皮书](docs/ops/reaka_foundation_whitepaper_v1_4.md)。

```bash
python -m pip install -e .
python -m pip install 'torch>=2.7,<3' --index-url https://download.pytorch.org/whl/cpu
python scripts/validate_reaka_foundation.py
python scripts/run_infrastructure_tests.py
```

使用 Python 3.11。历史合同反例测试需要固定 Git 修订；浅克隆首次运行前执行：

```bash
git fetch --no-tags --depth=1 --filter=blob:none origin 3a75376e1f7f871bb72e48f886c275919b3c9671
```

以上验证不要求行情上传齐全。测试报告明确列出依赖尚缺的历史模块，**不把当前范围通过说成全仓测试通过**；`pytest -q tests/unit` 仍保留为不排除任何模块的严格全量命令。

缺件只阻断依赖它的复现或结论，不阻断文档、数学推导、接口实现、合成反例和独立来源审计。当前任务不运行新训练或账户；未来已授权研究按任务与实际依赖开展，不必为了普通修订逐项申请新的流程许可。历史回执不可改写，旧写入入口不可拿来覆盖旧结果。

仓库检查、数据完整性、历史复现、预测证据和经济结果分别报告。已消费材料不恢复为 fresh OOS；生产、交易和本地 FactorLab 指针不在本仓库授权范围内。数据用途与版权见 [用途声明](docs/governance/data_usage_declaration.json) 和 [NOTICE.md](NOTICE.md)。
