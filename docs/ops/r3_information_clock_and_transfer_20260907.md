# R3：先验证信息时钟，再做冻结跨期迁移

日期：2026-09-07。来源基点：`270db9bc3ce6b8bcba03a66dfdd7fca8f2931cf2`。
这是云端与本地协作。本轮选择用户授权的第二条路线；不猜月度 CloudRidge 公式，不增加消融组。

## 1. 为什么先做这个问题

XFINE 的五条嵌套对比已经完成，原结果、模型与验收保留。本轮不重算这些结果。正的模型对比并不单独证明被移除的通道携带可迁移的市场信息：恒定输入也可能通过非线性编码、偏置或训练路径改变排序。因此先区分：

- state mask 是动态历史可得状态，还是恒定通道、预热日历或股票位置取模的代理；
- reliability 是按当时历史拟合得到的数值质量指标，还是包含后来的样本覆盖/修订；
- 上述来源规则在跨期应用时是否保持不变。

这里不是宣称已经发现泄漏或推翻 XFINE。此前“最可靠的信息层”现在作为**待验证的候选层**使用；五个对比的逐项区间也不是五项同时成立的联合置信保证。

## 2. 本轮已经读到的源码事实

### K1 消费路径

`src/factor_lab/factor_rotation/reaka_intraday_k1_preflight_v1.py`，Git blob `6942fb2dc20d24307578bc7dda45368afaf3d1f5`：

- `assemble_inputs` 的十个端点是 `t + [-180,-160,...,0]`，不是最近连续十天；
- 状态和状态掩码从 `[symbol_position % 5 + 1, endpoint, factor]` 读取。同一个 endpoint、同一个 fold 的股票共用同一 mask；这一事实不否定共同状态经交互影响排序；
- `build_state_store` 将上游 `available=True` 的记录直接物化为 1，没有在该函数中校验发布/首次可读时间；
- `build_exposure_store` 从 available 记录读取 beta/reliability，再按有限值形成 exposure mask；`assemble_inputs` 实际消费的是 `reliability * exposure_mask`；
- 这些数组的“available”不是历史行情到达时间或交易可得性证书。

因此新脚本既统计原 state mask，也统计原装配规则下的 masked reliability；不把一次成功执行写成 PIT 通过。

### Reliability 的来源边界

当前公开的 `orthogonal_index_timing_transport_ot1_v1.py`，blob `bf63cfe9d2018d3b9f20095919ce6cfd743493da`，其 daily `_fit_stock_single` 使用 coverage、半窗口 beta 稳定性、condition-number quality 的最小值。该 daily 文件**不能自动代替当前 intraday 实际调用身份**。当前分支按直接路径读取 `reaka_intraday_orthogonal_ot_v1.py` 返回 404；本地只需要定位实际函数与窗口端点，不需要再次交付整个 FactorLab 或重跑 R2。

不能将 reliability 直接称为正确概率、未来拟合优度或独立 alpha。

## 3. 已实现的零训练审计

执行器：`scripts/reaka_r3_information_clock_audit.py`。

它只 mmap 读取七个 target-free 数组：calendar、inference rows、state values、state available、exposure positions、reliability、exposure available。不会导入 torch，不加载模型，不读取分数、epsilon_future 或 labelled indices。

按 2011–2016、2018–2020、2021–2025 三个事前固定窗口，报告实际消费的十端点上下文中的各因子 min/max/mean/zero fraction、常量位置、跨 fold 变化和支持范围。2017只可作为后续决策的历史上下文，不作为新的评价窗口。若原 store 截止2020，2021–2025输出 `no_support`，不得拼接虚构观测。含2026的 store 被拒绝，须使用原有已界定来源。

所有计数均为重叠上下文槽位，不是独立股票日样本数。相同 fold 内没有股票差异是 schema 性质；跨 fold 或跨日期变化是否存在才是本地实际数据问题。

七个输入文件的真实 SHA256 会记录。提供原回执绑定时逐项比较；未提供则诚实列为历史绑定未建立，不以本次新算摘要冒充原运行来源。仅重哈希本任务七个输入，不扫描行情湖。

`audit_time_rows` 接受带显式时区与 source_ref 的小型来源证据。晚于 decision 的依赖/available_at 会报违反；缺时间或来源是 unknown，不转成 passed。2026年入库时间不能代填2018年的历史可得时间。即便所有提交行时间顺序一致，也只确认提交行，不认证全量 PIT。

`compare_prefix` 是可复用的双向支持比较函数：拒绝空比较、全不可用、有效掩码不一致和活动格非有限值。它**没有自动接通缺失的 intraday 生产器**，不能声称已重建真实因果前缀。

## 4. 云端实际验证

当前会话实际运行35项测试，全部通过，零失败/错误/跳过，并通过 `py_compile`。其中一次测试在新的 Python 进程中，用合成的两时钟 store 跑通 CLI；没有未来标签文件也能完成，时间证据缺失仍返回 unknown。

另一个合成反例展示恒定特征经固定非线性函数可以改变排序。它只说明“消融增量不能自动等同新增信息”，不是证明真实 mask 是常量或真实模型无效。

证据：`cloud_results/r3_infoclock_20260907/`。本轮真实数组、真实网络拟合、真实模型推理、账户、Actions 均为0。整个 FactorLab 测试套件未执行。

## 5. 冻结跨期迁移方案（本轮只预先登记，尚未执行评分）

在本次时钟/来源核验后，最小跨期比较无需训练任何新 arm：

- `F − STATE_VALUE_PLUS_E`：复用原模型，检验 state-mask 嵌套步骤；
- `BETA_RELIABILITY − BETA_ONLY`：复用原模型，检验 reliability 嵌套步骤。

固定两个时钟、三个seed，沿用四组已有模型，共最多24个新期间评分任务，**新训练为0**。不将两层拼成未经比较的新模型；不重新选择2016年末工具、不重估normalizer、不初始化新DMD、不按新期结果选checkpoint。先固定比较，不筛年份/seed/方向。

候选评价区间固定为2021–2025，H20标签须在2025年底前成熟，不能读取2026补尾部。仓库 data_usage_declaration 将2018–2025全部标为 consumed，所以未来成功也只是跨期历史迁移，不是 fresh OOS。原股票位置及因子/通道顺序不可重排，否则 `symbol_position % 5` 的 fold 身份会变化。所有新股票的映射与支持必须事前声明，四臂同支持。

主量沿用同一天先平均两个时钟的配对 RankIC，再等日期平均；分年、分seed、phase以及原残差 decile/Top30 全部报告。两项主比较共同按日期作时间依赖诊断，不把时钟/种子当独立市场重复，不以secondary替代主结果，也不将逐项95%区间称为联合95%通过。

**当前没有声称已实现并实跑完整的“2021–2025新store生成→四组模型新进程加载→评分”执行链。**是否已有对应来源与固定schema的store由本地只读确认；没有则返回最小缺口，不用旧TIMEISO runner的固定2018–2020索引冒充跨期运行。

来源未知仅限制相应PIT主张，不是永久阻断所有研究；发现明确未来依赖则必须先处理该依赖再解释其跨期表现。不要求全湖PIT签字、账户恢复或所有旧测试通过后才研究。

## 6. 本次唯一新本地任务

`LCL-R3-INFOCLOCK-20260907-01`，见 `cloud_local_communication_R3_infoclock_20260907.md`。只做七数组profile、最小生产函数/时钟说明及2021–2025来源可用性核对；0训练、0推理、0checkpoint reload。真实跨期评分不在这个零计算任务中自动启动。
