# LCL-R3-INFOCLOCK-20260907-01：信息时钟与迁移准备

这是云端与本地协作。状态：待用户转交、本地尚未执行。当前唯一任务是来源与信息结构审计，不是新的消融/训练任务。

## 问题与边界

XFINE已收口。仅回答 state availability 与 exposure reliability 的实际变化、历史依赖和2021–2025冻结迁移的最小来源是否存在。不重开R2，不重复六份原checkpoint验收，不重放账户，不猜S_obs/1σ，不跑F+M。

新网络fit=0；inference=0；checkpoint reload=0；scores读取=0；未来标签值读取=0；Actions=0。不得运行会训练的旧TIMEISO/XFINE主命令。原store及工作区只读；没有新模型、没有全量OLS重拟合任务。

## 代码和命令

仓库 `staryocean0/factorlab-multifactor-stock-lab`，分支 `codex/reaka-foundation-audit-20260905`。以本任务发布提交为代码起点，保留后续并行提交，不覆盖main。

先运行本任务独立测试：

```bash
python -m pytest -q tests/unit/test_reaka_r3_information_clock_audit.py
```

两时钟store根从已验收TIMEISO/XFINE的 `reload_spec.json` 中读取，不猜目录，不改accepted_view。创建spec：

```json
{
  "schema_id": "factorlab.r3_information_clock_audit@1.0",
  "output_root": "/path/to/FactorLab/tmp/LCL-R3-INFOCLOCK-20260907-01/run01",
  "stores": {
    "1430": {"root": "/actual/1430/prepared/store"},
    "1445": {"root": "/actual/1445/prepared/store"}
  },
  "time_evidence": []
}
```

每个store可加 `expected_hashes`，键只能是脚本的七个输入文件名，值为原回执的 `sha256:...`；不要将本轮新算摘要标成历史绑定。没有现成外部绑定则先保留unbound。空time_evidence合法，但结果是unknown，不是PIT通过。

```bash
python scripts/reaka_r3_information_clock_audit.py --spec /path/to/spec.json
```

输出目录必须不存在且不与store重叠。退出0代表profile完成，允许时间证据unknown；退出2代表提交时间证据中发现违反；退出1代表输入/结构/运行失败。三者均不代表交易/PIT/alpha认证。不要为制造退出0删掉违反行。

## 同任务最小来源说明

另外写 `source_clock_review.md`，只读当前实际 intraday 生产器和已存在的来源/审计记录，分别说明：

1. `selected_factor_states.available` 由哪个函数/判定生成。是否仅有限值、预热、成员数、成交覆盖、还是依赖标签；最大被读位置与决策时钟如何对应。
2. `d5_stock_exposures` 和 industry表的 `reliability` 精确公式、回看窗口首尾、有效样本规则、beta半窗稳定性/condition等是否实际参与；明确asof/effective/首次可读时钟，不直接套用公开daily helper。
3. 来源文件路径、commit与实际SHA，以及关键函数短摘录/行号。只交本任务必要来源，不追全仓闭包。原代码未上传时给小型关键函数即可，不要求大源码快照。
4. 有现成前缀核验明细则复用并标覆盖范围；没有则只追源说明。脚本的compare_prefix是工具函数，并非已接通的真实生成器；不要编造“全量前缀通过”。本次不要求重新运行全OT1拟合来补证。
5. 若只有2026年入库available_at或缺少历史到达日志，明确unknown，不代填历史时间、不申请tick整湖。

可将有真实来源的小型时间记录放入spec.time_evidence，每行包含feature、decision_at、dependency_max_at、available_at、source_ref，时间必须带时区。没有证据不能凭asof_date生成到达时间。仅检查几行就只能报告几行。

## 跨期准备：只检查元数据，不打开新期标签或评分

固定未来候选为2021–2025，2026禁止。只报告已有相同定义的P6/OT/store是否覆盖、具体版本、calendar末端、factor/symbol顺序是否延续，以及四组原模型 F/STATE_VALUE_PLUS_E/BETA_ONLY/BETA_RELIABILITY 的checkpoint是否在原路径存在。

缺少哪个直接来源就列哪个；不要新物化数据、重算normalizer、训练或推理。此次profile只有原store支持的区间；原store不含2021+是合法的no_support，不是让本地补训练的理由。

这是一份给云端决定最小跨期执行器输入的准备记录，不是新的全项目审批链。

## 回传与验收

提交 `cloud_results/local_handoff_R3_infoclock_20260907/`：

- `local_feedback.md`：实际代码/FactorLab版本、原store根、命令、退出码、0fit/0inference/0reload、异常与所有未知；
- `audit.json` 与测试日志；
- `source_clock_review.md`：含上述跨期准备说明，无需单独制作多个合同。

七个原数组、大模型和行情留本地。云端验收只关闭已覆盖问题；unknown不伪装通过。完成后停止，不自行启动24个跨期评分任务，不加新arm。
