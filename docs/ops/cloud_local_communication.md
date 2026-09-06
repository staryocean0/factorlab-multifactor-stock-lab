# 云端—本地沟通文档

执行与交接规则统一见 [AGENTS.md](../../AGENTS.md) 的 Protocol 1 和 Protocol 2；本文件只保存任务交接和反馈，不建立第二套研究流程。项目证据状态仍由 [研究状态](research_state.json) 维护。

## 当前资源说明

2026-09-06，用户告知：云端存在数据缺口，GitHub Actions 当前没有可用额度。此为用户提供的资源状态，不是独立账单核验；具体数据依赖按每个任务判断。当前不派发或重跑 Actions，优先云端直接执行，其次交接本地。

此前协议补充阶段未新发起实证计算任务。现在用户明确要求由本地大模型接手云端因缺数据无法执行的任务，本次实际交接见下方 LCL-R2-20260906-01；其他既有未验证事项仍保留在原状态与回执中，不把所有历史缺口批量转成新工单。

### 2026-09-06：仓库访问与提交恢复通知

用户告知已将仓库改为 public、提交能力恢复。本次通过 GitHub 接口读取仓库元数据，返回 `visibility=public`、`permissions.push=true`；回读开发分支提交 `fac9f27a9c63a75f9e9f6d8947b3cff805904ccd`，确认 `AGENTS.md` 两块协议和本沟通文档已保存，不重复补写协议。保存本条更新的实际 Git 提交及回读结果用于确认写入，不仅凭公开可读或权限字段推断提交成功。

仓库提交能力与 Actions 计算额度是两个独立事项：本次通知不作为 Actions 额度已经恢复的证据，不启动或重跑 Actions。仍按“当前云端会话直接执行 → 本地大模型执行并回传文档 → 最后才考虑 GitHub Actions”的顺序工作。资源说明更新不代表缺失数据已补齐、R2 已通过或 PR 已合并；仅保存本次状态通知，不新发起模型训练或实证任务。

## 实际任务：LCL-R2-20260906-01

**状态与负责人**：云端已复核增量（2026-09-06），本轮有界协作任务 `completed_with_limits`，不再要求同一 A/B/C 补件。R2 状态为 `bounded_reproducibility_review_complete_pit_not_certified`：存盘重现/直接来源在声明范围内接收，强 PIT、历史选型及交易主张仍受限。以下原交接与本地反馈作为历史记录保留，最新裁决见本节末“增量云端验收”。

**任务书**：[REAKA 本地接手 R2 审计](local_handoff_R2_20260906.md)。本文档就是需要转交本地大模型的具体工作说明，不是再次索要全量数据的补件清单。

**云端已完成（原交接阶段）**：读取开发分支 `1904b8fefdf72be648b25b956c42482426b7bcaf` 的协议及旧R1/R2回执；读取 main `af2e478aaff5c8ef7f753424b57fd2d19019f248` 的关键P6.1/P6.2函数；当前会话直接执行盘点器5项合成冒烟检查，见 [cloud_precheck.json](../../cloud_results/local_handoff_R2_20260906/cloud_precheck.json)。未运行真实P6审计，未调用Actions。

**云端未执行及原因（原交接）**：当前运行环境未挂载原始分钟、因子/暴露来源与对应完整P6产物，无法完成真实时钟/收益重建、金融epsilon算术、因子状态PIT及K1消费绑定。main中新文件出现不等于相关来源已验收，不沿用旧missing列表作最新事实。

**交给本地的工作（原交接）**：按任务书 A—E 先定位本地来源，再执行两时钟P6.1价源/标签、OT1残差与系数、OT2/OT3状态/选择、K1消费链检查；必要时做原checkpoint冻结推理核对及最小影响分析。已有数据支持时执行F项的历史测试与Stage4/账户独立诊断。不是新训练、策略搜索或大规模账户重放；独立检查可并行，一处缺件不扩大成项目停工。

**最小依赖、执行命令与验收**：详见任务书第4—7节。已存在的元数据盘点命令与本地需要实现的R2审计器明确分开；R1身份未变不重传。结果留新目录，逐项记录版本、范围、实际命令/退出码、对照误差、异常及未检事项。小切片只支持相应范围，不冒充全量PIT通过。

**告知与转交（原交接）**：原回复提供任务编号、本任务书和沟通文档路径，请用户转交本地执行。没有本地直连执行通道；此记录不表示自动派发。

**本地反馈（2026-09-06，保留原结论）**：报告 [local_feedback.md](../../cloud_results/local_handoff_R2_20260906/local_feedback.md)，摘要 [local_audit_summary.json](../../cloud_results/local_handoff_R2_20260906/local_audit_summary.json)，审计器 `scripts/reaka_r2_local_audit_v1.py`。原 FactorLab `master` `b39bb12f43a46b165d18db93191a669234077444`；P6.1/P6.2 源码 blob 与任务书 main 定位一致；DataHub `bars_cn_a_1m_raw_canonical_4ceca170a851`。官方盘点退出码 2（13 match / 17 unbound / 0 missing）；独立审计器退出码 0 且 `full_pit_certified=false`。在已声明支持上，P6.1 全量 H20、OT1 epsilon 应用、K1 绑定通过；DataHub 抽样 5 日×4 股×2 时钟价源匹配；14:30 seed11 冻结推理 512 行通过。未发现需重算现任输入或分数的构造错误。明确保留：lineage 未来公式字面不一致、`available_at` 非当时、OT2 选型用 2009–2020 future、Stage4 2018-01/2021-01 重复月、两份旧账户源码未找回。大数组留本地 `tmp/LCL-R2-20260906-01/`。抽样或脚本成功不是全量 PIT。

**云端复核（原轮，已执行）**：对提交 `8ffdd90b5a664337058fad4a301f85ddfa6aa599` 的反馈、摘要和完整审计器进行了复核，并读取 K1 实际特征装配代码。当前会话重算四份公开 OT2 JSON 身份（Git blob、raw/canonical 与原 manifest 对齐），复现五处审计器判定漏洞；未运行本地大数组、冻结推理、九项本地测试或全仓测试。完整裁决见 [cloud_review.md](../../cloud_results/local_handoff_R2_20260906/cloud_review.md)，实跑记录见 [cloud_review_checks.json](../../cloud_results/local_handoff_R2_20260906/cloud_review_checks.json)。

**原轮已接受的范围**：保留本地 P6.1 存盘 H20 算术、分钟标签顺序和申明样本价源对照；OT1 存盘有限支持上的算术与 OLS 抽查；固定已选工具在所报 full_reference 因子上的前缀/存盘一致；K1 epsilon/轴/标签子集；14:30 seed11 的512行冻结推理一致。均注明本地执行、云端文档与源码复核，不冒称云端全量重算。

**原轮未关闭及理由（历史，以下增量验收更新适用范围）**：JSON raw比对失败后直接信任嵌入canonical的检查不充分；K1 实际消费 symbol_position%5+1 的crossfit状态及暴露/可靠性/掩码，而本地 D/E 没有覆盖该全部直接链；分钟标签先后不等于事件/到达时钟；fresh_oos=false 不消除事后选型的历史证据限制。五处判定漏洞没有推翻摘要中已经报告的零差异观察，不因此重训。lineage 的 t_minus_1 字符串收敛为歧义问题，不认定数组算错。R2 当时状态为 partially_reviewed_not_closed，Stage4及账户局限保留。

**同任务最小补充（本地已执行，原反馈保留）**：后继审计器 `scripts/reaka_r2_local_audit_v1_1.py`，报告 [local_feedback_delta.md](../../cloud_results/local_handoff_R2_20260906/local_feedback_delta.md)，摘要 [local_audit_delta_summary.json](../../cloud_results/local_handoff_R2_20260906/local_audit_delta_summary.json)。原 FactorLab 仍为 `master` `b39bb12f43a46b165d18db93191a669234077444`；主题仓接手 HEAD `d6cccfea5e9d7eddcae17a7833c0b15732d74e6f`。后继审计器退出码 0，`full_pit_certified=false`；7 项 G1–G5 反例测试通过。A：导出原 81 条 A.rows；两份 selection 按仓库 canonical 重算后与云端已公布 raw `cd5d7ed8…` / `fffcd456…` 对齐；用原统计按 G2–G5 重判仍通过，未重扫价/residual 大面。B：两时钟 K1 实际消费 `symbol_position%5+1` 的 5 个 crossfit 状态及暴露/可靠性/掩码，与 OT1/OT2 重建 286,104 / 32,556,832 格误差为 0；70/70 消费组合前缀通过；OT3 不进入该 K1。C：`2009-01-07T14:30:00Z` → `[11:16]=14:30` 可重现；`available_at` 为 2026 入库时间；事件可得性与可成交性明确未验证。未重训、未账户重放、未调用 Actions。大数组留本地 `tmp/LCL-R2-20260906-01/local-20260906-delta/`。

**原增量反馈方式**：本地已在原目录写入 `local_feedback_delta.md` 及后继代码/测试；其“本地已反馈”身份和原文本保留，不将本地报告改写成云端全量重算。

### 增量云端验收（2026-09-06，已完成）

被复核提交 `eb1fa92e81e7548bd9b50b48c9848fc2853e6cde`。报告 [cloud_delta_review.md](../../cloud_results/local_handoff_R2_20260906/cloud_delta_review.md)，回执 [cloud_delta_review_checks.json](../../cloud_results/local_handoff_R2_20260906/cloud_delta_review_checks.json)。当前云端先核对源码/测试/摘要 blob，实际运行 7 项后继单元反例、6 项五折/71通道合成装配检查和 48 项小证据一致性检查，均无失败。不是旧409项全仓范围检查，也未重跑本地大数组。

**接收**：A 81项本地身份明细及两份重算canonical、G1–G5针对性修复与已有统计重判；B 两时钟原构造器对状态/暴露/可靠性/掩码的存盘重建一致性、每时钟70个消费组合在固定工具/基底与单截止点下的前缀一致；C 明确保留事件可得性未知，符合上轮“有则补、不能证明则保留未知”的要求。OT3非该K1直接特征依赖，不强制重建无关传输链。

**不扩大结论**：重建用原build函数，不是独立重写算法；格数含默认零，不是有效独立观测；本地映射抽查未实际装配全inference，云端合成检查不代替真实全样本。时间合同ID在后继函数中是常量，未据此证实合同正文或Z语义。事后选型、全量PIT、可成交性、旧Stage4及账户源码局限保留。

**任务收口与下一步**：本轮 `completed_with_limits`，不再重复 A/B/C 补件、不上传整湖、不重训或账户重放。转入 R3 的证据用途裁决，先以已消费开发材料身份明确现任模型与条件特征可支持的预测问题、基准和评价；本验收不自动启动该实证研究。只有后续新任务确实依赖未证事件/PIT时再按最小依赖安排，不把已知限制转成永久全项目阻断。原反馈、代码、数据和大产物不改写；此次不调用Actions、不合并main、不改生产或本地指针。

## 实际任务：LCL-R3-NOFIT-20260906-01

**状态与当前入口（2026-09-06）**：云端 R3 首轮裁决已完成。**本地已反馈**真实零拟合对照；尚未云端复核。上一轮交付包没有写回 GitHub，本次补交原脚本、测试、报告和计算证据。请直接使用本开发分支文件，不再要求本地搬运交付包。当前发布说明见 [publication.md](../../cloud_results/r3_evidence_use_20260906/publication.md)；原报告里的“尚未写回”是编写时的历史状态。

**协作与任务边界**：这是云端与本地协作，按 AGENTS Protocol 1/2。R2 的 completed_with_limits 状态及历史记录保持不变。任务书是 [R3 证据用途裁决](r3_evidence_use_adjudication_20260906.md) 第5节，只比较已消费2017现任K1与四个固定、零拟合的epsilon基准，不识别条件特征的全部独立增量，不恢复fresh OOS。

**云端已完成及未执行**：已审阅原formal与评价实现，生成6项算术检查、13项脚本测试的原回执；本次发布前同一源码复跑13项测试、6项算术仍通过，重复复跑不累加为独立证据。实跑回执见 [publication_checks.json](../../cloud_results/r3_evidence_use_20260906/publication_checks.json)。原数据数组未挂载到云端运行时，真实配对差值尚未知；不通过Actions代算或搬运。

**最小输入与命令**：原FactorLab两时钟K1输入仓的manifest、坐标、epsilon_history/future，以及两份formal和六份已生成review分数。不需要checkpoint重推理、DataHub分钟或账户数据。先查已有同口径结果，充分则直接提交身份明细；否则在主题仓工作树运行：

```bash
python scripts/reaka_r3_frozen_compare.py \
  --factorlab-root /实际/FactorLab \
  --output-dir /实际/FactorLab/tmp/LCL-R3-NOFIT-20260906-01/run01
```

输入指向真实本地根，新输出目录必须不存在。脚本SHA-256为 `188d9a54746d95e079770cef701837d827880c61bc542dd2ad6f9a4729367e9f`，与原包一致。缺件或身份/回执不符即报告，不改ensemble、不重训、不放宽规则。具体口径、输出、容差和停止条件见任务书第5节。

**回传与验收**：新 `local_feedback.md`、`comparison.json`、`paired_daily.csv`，附实际命令/退出码、脚本及输入身份、失败和未执行范围。大数组留本地。本地只填写“本地已反馈”；云端读取后独立记录复核结果。零退出码不等于PIT、条件增量、盈利或生产通过。负结果正常保留。

**告知与提交规则**：用户已收到原R3任务编号和交付包，本次回复提供GitHub实际提交与脚本入口。由用户安排本地执行；不声称已远程派发。保存使用 `[skip ci]`，不调用Actions、不force-push、不合并main，不改变原始数据和模型。


**本地反馈（2026-09-06）**：主题仓 `d6804cd`；脚本 SHA-256 `188d9a54746d95e079770cef701837d827880c61bc542dd2ad6f9a4729367e9f`；FactorLab `b39bb12f`。`pytest tests/unit/test_reaka_r3_frozen_compare.py` 退出码 0（13 passed）。`python3 scripts/reaka_r3_frozen_compare.py --factorlab-root <FactorLab> --output-dir <FactorLab>/tmp/LCL-R3-NOFIT-20260906-01/run01` 退出码 0。两时钟 `completed_consumed_diagnostic`，各 82321 行 / 49 日；K1 与原 formal 回执 atol=1e-4 复原。报告 [local_feedback.md](../../cloud_results/local_handoff_R3_20260906/local_feedback.md)，[comparison.json](../../cloud_results/local_handoff_R3_20260906/comparison.json)，[paired_daily.csv](../../cloud_results/local_handoff_R3_20260906/paired_daily.csv)。未训练、未 checkpoint 推理、未读 DataHub、未账户重放、未打开 2026、未调用 Actions。大数组留本地。零退出码不是 PIT/fresh OOS/生产通过。

## 任务记录与反馈模板

以下是其他任务的模板，不是新增派发任务。记录可简写，字段可合并；只填写本次步骤必需的信息，不要求另外生成多份合同、报告或签字。

### 任务编号／任务名称（待填写）

**状态与负责人**：待本地执行／本地已反馈／云端已复核；标明日期和实际执行方。失败、需补充或取消另写事实，不强制得到“通过”。

**云端交接**：问题与目标；代码分支/提交；已完成的步骤及证据；未执行步骤与原因；最小数据依赖、范围和口径；执行命令或尚需实现的步骤；输出位置、应回传的内容与验收条件。

**已告知用户**：交接文档路径、任务编号及需转交本地大模型的事项；尚未实际告知时不得填为已通知。

**本地反馈**：实际代码版本、数据范围及必要身份摘要、环境；执行命令和退出码；结果摘要、产物位置、错误/失败及未验证事项。回传必要的小报告，不默认上传整套数据；无法回写时由用户转交文档。

**云端复核与后续**：收到的文档/产物；实际核对内容及尚不能核对的内容；本地结果能支持的结论；下一步动作。只有确实复核后才更新复核状态，不能将文档反馈等同于云端独立全量重算。
