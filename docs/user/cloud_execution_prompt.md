# REAKA 云端接管说明 V1.3

从 `docs/ops/reaka_multifactor_current_manifest@1.3.json` 进入，依次阅读
`docs/user/reaka_multifactor_current_workflow_v1_3.md`、
`docs/ops/reaka_foundation_whitepaper_v1_3.md`、
`docs/ops/reaka_foundation_semantics@1.1.json`。
本轮用户已授权确保文档、白皮书、代码、测试、工作流口径正确一致。

先运行 `python scripts/validate_reaka_foundation.py` 与 `pytest -q tests/unit`。
它们只验证现行口径和合成反例，不等待行情上传，也不训练模型。
旧 Stage4 重复月份及来源缺口仍阻断该历史证据；不要请用户对它作金融验收。
需要追溯时运行 `python scripts/audit_reaka_foundation.py`，保留其失败/缺口结论。

数据补齐由用户通知。收到通知后先运行 `python scripts/validate_theme_package.py`，
再按 V1.3 工作流处理证据与后继合同；数据通过本身不开放训练、选 K、账户或生产。
保留待上传的 2023/2024 文件和已有数据，禁止修改封存行情、历史验收摘要或本地 FactorLab 指针。

其他旧“current”说明仅供历史溯源。现行检查器严格拒绝来源漂移、口径变动和关闭动作被打开；
旧写入脚本已封闭，不能用旧 validate 命令重写通过收据。
