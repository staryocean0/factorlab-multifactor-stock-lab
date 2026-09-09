# R2 云端验收：独立计算补充与本地续接入口

任务：**LCL-R2-20260906-01**。被复核本地提交：`8ffdd90b5a664337058fad4a301f85ddfa6aa599`。

## 裁决与单一交接入口

**云端验收已完成，受限结果接受；R2 尚未整体关闭。暂不要求重训、全面重算输入或账户重放。**

提交前发现开发分支已有并行复核 `d6cccfea5e9d7eddcae17a7833c0b15732d74e6f`。本次重新读取该报告及状态，结论一致，故保留其原文、研究状态和任务定义，只追加本目录的独立计算证据。不覆盖并行工作，也不增加第二套审批或任务书。

**本地接手时，请继续同一任务，读取仓库 `cloud_results/local_handoff_R2_20260906/cloud_review.md` 第4节。** 本目录只补计算明细，其验收与任务说明以[已有云端复核报告](../cloud_review.md)为统一入口；反馈仍写入 [云端—本地沟通文档](../../../docs/ops/cloud_local_communication.md)。

## 已保留的本地证据

两时钟存盘 H20 重算、存盘有限支持上的 OT1 epsilon 算术、每时钟10个 OLS 抽查点、指定 full_reference 序列的固定工具前缀、K1 epsilon/坐标绑定，以及14:30 seed11的512/82,321 review行冻结推理，均有非空支持及明确误差统计。本次接收这些限定断言，不等同于云端独立重算大数组，也不等同于完整 PIT 或全71通道的来源验收。

保留旧原产物用于冻结复现和已消费开发研究，不意味着批准其历史时点可交易或独立样本外效力。Stage4重复月份、无组件账的守恒缺口和旧账户源码原字节缺口均仍保留。

## 当前云端会话实际计算

本目录保存 [cloud_checks.json](cloud_checks.json) 与可重跑的 [cloud_review_checks.py](cloud_review_checks.py)。程序只读取公开小摘要与四份原 JSON，不接触本地市场数组或 checkpoint。

| 项目 | 实际结果与边界 |
|---|---|
| 公开摘要的60项一致性检查 | 60通过，0失败；检查非空支持、计数、误差、有限值掩码、抽查与重复键等，不只是读取顶层passed |
| 四份原始OT2 JSON | Git blob身份、正文canonical摘要和两个manifest的外部selection_digest均对上；不能代表全部81项大文件已由云端核验 |
| 八个隔离验证 | 均复现预期现象，含原审计器判定表达式、摘要函数、控制例及分钟边界逻辑；不是八项实证策略通过，也不是八个独立金融缺陷 |
| 原始本地数据及Actions | 未读取大数组、未重跑模型或账户、未使用Actions |

原摘要身份为 Git blob `89f89a3524c5643bd55ae7554f29210c9087328a`，SHA-256 `c77979d1e35fb7068c78b028956b0d20880ec27c68520bb67078eab084c1db61`；审计器是 blob `a003fe75fbb127761b63b963c320deecd88de539`。四份小文件取自 main 定位 `af2e478aaff5c8ef7f753424b57fd2d19019f248`，本目录使用相同 Git blob，不改写原对象。

执行环境为 Python3.13.5、NumPy2.3.5。复核程序的计算部分实际运行成功，保存前再次复跑，输出计算部分与原回执一致。其代码为一次性证据复核辅助，不是新增全仓强制测试。

## 关键问题及为什么只要求补充

**实际特征支路未覆盖。** K1使用 `symbol_position % 5 + 1` 对应的cross-fit状态，而本地D主要核对变体0的full_reference。E只比epsilon和轴，没有独立核对 `state_values/state_available`、beta、reliability及有效掩码构成的71通道。已有epsilon结果不受这一缺口推翻，但不能据此宣称整个K1输入已验证。

**事后选型与固定工具计算是两件事。** 2009—2020 future收益参与工具选择；固定该工具后前缀稳定，不证明早期决策已经知道该工具身份。`fresh_oos=false`应保留，但不能消除历史可实施性的前视问题。当前可以保留开发材料，未来若要求因果/独立预测评价，应据新的正确选型身份再判断是否重建与重训，而不是一概说任何用途都无需重训。

**审计器的通过判定有缺陷。** raw摘要不符时，原`digest_row`只信任JSON自带的canonical字段，没有重算正文。云端已复现它接受修改正文、保留旧摘要的JSON；但四份真实选型/manifest正文已在云端补核有效，因此没有证实这些文件实际损坏。原B/C/D还遗漏缺数据、空评价列表、有限支持缺失或存盘状态差异的部分检查。本次已返回的详细指标正常者仍保留，不因潜在漏判而要求重算全部数据。

本独立计算还复现了**无比较点时prefix_stable也会为真**。后继审计器修正相应保护时加入`compared > 0`即可；当前六个已报告序列均非空，此发现不追加一项市场数据任务。

**时间标签不是可成交证明。** 无13:00、有13:01及15:00只是end-label线索；即使14:31是端标签，其open也可能在14:30区间起点，而非读取14:30close并完成计算之后。Z后缀、墙钟和入库时间需要来源解释，缺证则保留未知，不强求逐笔或全湖任务。lineage中`t_minus_1`的字符串应视为歧义，不能只凭字面断言分母取错；数值公式可写成`(entry[t+20]/entry[t])-1`。

## 本地下一步：只做同任务增量

统一复核报告第4节已给出三组要求：从已有结果导出严格raw/canonical逐项身份并修审计保护；核对真正进入K1的两时钟cross-fit状态、暴露与掩码；有现成时间转换依据则补充，没有则明确不关闭事件可得性。

执行时保留原报告，新增`local_feedback_delta.md`和必要的小JSON。已有足够明细的H20/epsilon只重新裁决，不重扫大数组；不重复R1、不扩大到六模型推理、不重训、不重放账户。实际使用的本地模块需内容身份，脏工作区HEAD不能代替加载字节。不能取得的证据只限制对应断言，不要求其他工作一起停止。

## 复算本目录小证据

从仓库根目录执行，先选择一个新的已存在输出目录：

```bash
python cloud_results/local_handoff_R2_20260906/cloud_review_v1/cloud_review_checks.py \
  --summary cloud_results/local_handoff_R2_20260906/local_audit_summary.json \
  --small-dir cloud_results/local_handoff_R2_20260906/cloud_review_v1/inputs \
  --output /新目录/cloud_checks.json
```

下载的独立证据包以本目录为根时，可用：

```bash
python cloud_review_checks.py --summary local_audit_summary.json --small-dir inputs --output recheck.json
```

程序会绑定原摘要blob，防止拿另一份报告套本回执。输出通过仅说明上述摘要、JSON和隔离观察被复算，不授予PIT、科学验收或生产权限。两个复核计算中的重叠观察不能累加成独立市场证据。
