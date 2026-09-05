# Cloud execution prompt

请完整阅读根目录 `README.md`、`AGENTS.md`、`NOTICE.md`、`docs/INDEX.md` 和
`docs/governance/package_scope.json`，然后接管 FactorLab **多因子选股 / REAKA**
后续研究。本仓库与两浪 Layer3 主题、隔夜高开实验室相互独立，禁止合并。

## 当前权威状态

本地控制器冻结的 current 是：

`stage4_machine_evidence_waiting_user_financial_review`

唯一 current 入口：`docs/user/reaka_multifactor_current_workflow_v1_2.md`。
Stage4 机器证据已完成，**没有 K 裁决**。Stage5、训练、K 容量、账户、指针和生产
在本仓库中保持关闭。你不能代签用户金融回执，也不能把 Stage4 的 mixed/aligned
机器描述升级成金融结论或现任策略。

## 本包给了什么

- 论文：ICASSP 2026 *Residual-Enhanced Adaptive Koopman Autoencoder* 全文 PDF
  与 FactorLab 精读卡。私有内部研究使用，禁止对外再分发。
- 论文忠实实现与多因子六位一体基础设施、Stage3/Stage4 代码和测试。
- 2007-2008 预热 + 2009-2025 研究面：A 股日线前复权、165 个非财务因子月度面、
  PIT 市值、自建行业指数、宏观输入、CloudRidge 与中证全指 000985。
- 历史成果：Stage3/4 面板、consumed formula 注册表、当前 K1 正式账户账本、
  机会账案例。它们可查询，不能冒充 current 规范权。

## 你要做的事

1. 先跑 `python scripts/validate_theme_package.py` 和 `pytest -q`，确认包完整。
2. 用 ontology 把论文对象（encoder / gate / K_i / residual / score）映射到
   FactorLab 对象（S_obs / Z / N_max / N_effective / account），不得把 S_obs
   写成 operator 监督标签。
3. 独立阅读 Stage4 金融审核包，给出**顾问级**机制判断：哪些假设符合金融机制、
   哪些应拒绝或重述。这不能替代用户签字，也不能打开 Stage5。
4. 在不执行训练、不改指针的前提下，可以准备一份结果前的 Stage5 输入装配草案
   （S_obs 如何进入 Hx/gate/显式交互）。草案必须保持
   `model_training_allowed=false`。
5. 任何新因子/新策略提案必须先读
   `docs/ops/reaka_factor_parallel_consumed_formula_registry@2.0.json` 和
   `.codex/skills/strategy-slice-rebuild/SKILL.md`。禁止重跑已消费公式身份。
6. 只使用本仓库数据。不得下载、请求、生成或推断 2026 及以后行情。不得把
   2018-2025 写成 fresh OOS。不得把研究面收益写成券商成交。

## 禁止

- 选择或填写 K 矩阵、operator count、portfolio_top_k 冒充 K
- 训练 REAKA / DRC / residual，或改 current 指针
- 优化总收益来选模型
- 把本仓库结果写进本地 FactorLab 权威注册表
- 公开分发论文 PDF

请独立完成可做工作。交付时写清：读了什么、跑了什么、顾问级 Stage4 判断、
未执行的 Stage5 草案、剩余风险和权威状态。
