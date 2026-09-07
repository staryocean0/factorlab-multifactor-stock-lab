# LCL-R3-TRANSFER-INPUT-20260907-01：同定义特征输入重建

这是云端与本地协作。状态：本地已反馈；待云端复核。回传见 `cloud_results/local_handoff_R3_transfer_inputs_20260907/local_feedback.md`。开发分支 `codex/reaka-foundation-audit-20260905`。INFOCLOCK已完成，不重复它的审计。

## 本地需要完成的唯一任务

基于原TIMEISO的固定队列、工具与normalizer，生成两时钟2021—2025同定义**特征**源包，再运行已提供的构建器。尚无同定义源包，故本任务不是只改一个目录就能运行旧命令。

网络训练=0；模型推理=0；checkpoint重载=0；账户=0；Actions=0。生成历史特征所需的原配方滚动OLS和固定滤波是允许的，另报范围，不与网络fit混淆。未来标签值不用于此特征构建；不要运行带训练的旧TIMEISO/XFINE主入口。24个跨期评分任务不在本次范围。

## 1. 已有云端代码及已验证范围

- `src/factor_lab/factor_rotation/reaka_r3_transfer_inputs.py`
- `scripts/reaka_r3_build_transfer_inputs.py`
- `tests/unit/test_reaka_r3_transfer_inputs.py`
- [源包与映射合同](r3_transfer_input_rebuild_20260907.md)

云端53项新合成测试通过，合计88项针对性测试通过；包含新进程双时钟无标签端到端构建，不是完整FactorLab集成/真实数据通过。

## 2. 在本地补上的上游桥接（必须如实标为本地实现）

实际 `reaka_intraday_orthogonal_ot_v1.py` 未入库，timing helper为dirty版本；云端没有这两份完整当前源码。因此本地需新写隔离桥接，例如 `scripts/reaka_r3_transfer_source_bridge.py`，只复用实际数值函数，不能调用会覆盖旧目录或自动训练的launcher。这个脚本目前尚不存在，不给出假装已经可用的生成命令。

桥接步骤：

1. 从原TIMEISO reload_spec/manifest读取原store、3982股票的原顺序、14因子和6variant身份、原选型JSON与normalizer位置；原24个checkpoint不重验不重载。
2. 在实际import完成后调用 `snapshot_loaded_sources` 记录直接生产器、timing helper、OT1 helper、滤波实现和桥接的 `__file__`/SHA256。保留原工作区，不把这些文件冒称为b39bb12 HEAD内容。源码快照是本次源包身份，不倒填旧回执。
3. 从独立、截至2025的原始来源延伸P6价格/历史H20/基底/暴露/状态。收益区间、复权、取价代理、membership及原fold定义沿用原配方。原股票位置和固定队列须在生成载体/crossfit前确定；不能用5894且含2026的残差成品切列替换。
4. 新尾部生成可以复用已验收旧历史数组和因子基底，不重算全部R2。预热/递归状态要继承原历史，不从2021硬重启滤波。只使用冻结2016选型，不重选工具、不估计新normalizer。
5. 将完整日历前缀+2021—2025尾部导出为合同第5节的13文件源包，明确历史前缀是复制还是实际重算。已复制前缀的一致性不能宣称独立重建成功。对桥接实际改到的数值接口做合成测试；可从原生成器只重放末端既有2020 D5位置作有界边界比对，不要求全历史OLS重跑，不读取标签。
6. 有界原始来源缺失时，返回具体直接依赖和已完成代码，不转用含2026成品、不填零造输入。当前首要缺口是源包生成，而不是再发一份INFOCLOCK清单。

## 3. 执行构建器

先跑：

```bash
python -m pytest -q tests/unit/test_reaka_r3_transfer_inputs.py
```

run spec（以下尖括号需要用真实原回执/本次源包摘要替换，不能照抄）：

```json
{
  "schema_id": "factorlab.r3_transfer_input_run@1.0",
  "output_root": "/FactorLab/tmp/LCL-R3-TRANSFER-INPUT-20260907-01/run01",
  "clocks": {
    "1430": {
      "reference_store": "/actual/TIMEISO/1430/prepared/store",
      "source_bundle": "/new/bounded_feature_bundle/1430",
      "frozen_selection": "/actual/TIMEISO/1430/prepared/selection/selected_tools.json",
      "frozen_normalizer": "/actual/TIMEISO/1430/experiment/normalizer.json",
      "reference_manifest_sha256": "sha256:<原manifest>",
      "bundle_manifest_sha256": "sha256:<本次bundle.json>",
      "selection_sha256": "sha256:<原选型>",
      "normalizer_sha256": "sha256:<原normalizer>"
    },
    "1445": {
      "reference_store": "/actual/TIMEISO/1445/prepared/store",
      "source_bundle": "/new/bounded_feature_bundle/1445",
      "frozen_selection": "/actual/TIMEISO/1445/prepared/selection/selected_tools.json",
      "frozen_normalizer": "/actual/TIMEISO/1445/experiment/normalizer.json",
      "reference_manifest_sha256": "sha256:<原manifest>",
      "bundle_manifest_sha256": "sha256:<本次bundle.json>",
      "selection_sha256": "sha256:<原选型>",
      "normalizer_sha256": "sha256:<原normalizer>"
    }
  }
}
```

```bash
python scripts/reaka_r3_build_transfer_inputs.py --spec /path/to/run_spec.json
```

成功状态为 `prepared_features_only_not_scored`。输出为 `run01/stores/{1430,1445}/`，不冒充带未来标签的旧K1完整store。退出1表示失败，不修改旧输入、旧摘要或正常数值来让检查转绿。

## 4. 只回传必要的小文件

目录：`cloud_results/local_handoff_R3_transfer_inputs_20260907/`。

回传 `local_feedback.md`、run spec、result.json、两时钟bundle.json / producer_sources.json / 新manifest.json / daily_support.json、桥接实现及其针对性测试日志。大数组仍留本地，不上传整湖、原checkpoint或大源包。

反馈记录实际主题仓HEAD、实际加载源码、命令/退出码、历史前缀来源、生成的年份/股票数/决策日、被排除支持及原因、旧prefix比较、滚动统计计算范围与次数（不能精确计数则明确未计数）、0网络训练/0推理/0重载、未知PIT和所有失败。只填“本地已反馈”，云端另行验收。

source snapshot记录文件身份不替代历史到达日志；unknown可保留，不要求先认证全湖PIT。新特征实际出现未来依赖则必须披露并停止相应结论。

## 5. 完成后停止

不启动24项跨期模型评分，不生成未来标签绩效，不重新选择seed/年份/参数，不新增臂、CloudRidge公式或账户研究。下游标签与评分接线由云端按本次真实源包和接口继续，不把当前构建器冒充完整行情到策略执行器。
