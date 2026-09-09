# REAKA 本轮基础设施审计入口

本入口管理2026-09-05接管审计及代码修复，先读[完整报告](../ops/reaka_foundation_audit_20260905.md)。冻结研究状态仍见 current manifest@1.2 与 current_workflow_v1_2；旧 handoff 中的@1.0入口和“唯一动作”只描述其封存时点，不能用来跳过本次审计发现。

## 可执行检查

```bash
python -m pip install -e .
python -m pip install 'torch>=2.7,<3' --index-url https://download.pytorch.org/whl/cpu
python scripts/validate_theme_package.py
python scripts/audit_reaka_foundation.py
pytest -q tests/unit/test_reaka_foundation_audit.py tests/unit/test_reaka_residual_certificate.py tests/unit/test_reaka_paper_math_contract.py tests/unit/test_reaka_bounded_imports.py tests/unit/test_reaka_stage6_health_estimand.py
```

第一项包检查仍严格核对所有数据。2023/24上传未完成会失败，不能删条目或改哈希让其通过。
审计默认退出码：0=审计范围完整，1=存在实质错误，2=存在缺证。
`--report-only` 仅让报告生成步骤返回0，JSON内的阻断状态完全保留。
标准包CI与新数学/审计CI各自报告；测试通过不授予模型或金融权限。

## 五位一体

| 责任 | 文件 |
|---|---|
| 用户入口 | 本文件 |
| 白皮书与金融解释 | docs/ops/reaka_foundation_audit_20260905.md |
| 机器语义合同 | docs/ops/reaka_foundation_semantics@1.0.json |
| 验证实现 | governance/reaka_foundation_audit.py、governance/reaka_residual_certificate.py |
| 测试 | 五个本轮 test_reaka_*.py 文件 |
| 执行 | scripts/audit_reaka_foundation.py、.github/workflows/foundation-audit.yml |

## 剩余完成条件

1. 上传现有2023/24分片后通过包级哈希检查；不重新采集或删除。
2. 从组件账证明Stage4重复月的覆盖与加总规则，再在新版本重建证据，保留旧文件。
3. 还原或明确封存闭包缺失范围；未附isolated树不能宣称已在本包独立重放。
4. 在后继训练获准前落实预测目标、可见时点、K容量与残差估计对象。
5. 将历史条件forecast的残差证据送入新@1.1证书；旧teacher-forced训练诊断不得冒充。

本轮无训练、无用户金融回执、无策略晋级、无账户或生产操作。

