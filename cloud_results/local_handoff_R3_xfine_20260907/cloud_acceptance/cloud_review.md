# LCL-R3-XFINE-20260907-01 云端验收

日期：2026-09-07  
本地结果提交：`b8a2c30af3ac2384823fa641bfd537cffb9d20e2`  
冻结执行基点：`32b449b5603e034d5dad660cd7fdfdc3117481be`  
任务：`LCL-R3-XFINE-20260907-01`

## 裁决

**验收通过，任务 `completed_with_limits`。**

本轮只接受为 consumed 2018–2020 上、预注册嵌套路径中的 ordered conditional contrasts。它不是 unique causal attribution，也不恢复 fresh OOS、full PIT、交易/账户 alpha 或 production authority。

## 1. 执行边界闭合

本地结果提交相对冻结基点恰好 ahead 1 commit；该提交只新增 XFINE 结果/receipt/manifest/reload-spec/test-log，并把任务文档状态改为“本地已反馈；待云端复核”，**没有修改 Stage-B runner/CLI/数值源码**。

本地回传并经云端读取：

- targeted tests：49 passed / 0 failed / 0 errors / 0 skipped，exit 0；
- read-only preflight：`passed_read_only_reference_preflight`；
- preflight 检查 2 clocks × 3 seeds = 6 组 reference F/E/H；
- preflight `new_fits=0`, `new_inference=0`, `future_result_peeking=false`；
- 两时钟均重建 accepted XCOARSE 142 paired days；
- 正式运行 exit 0；
- 新 arm 仅 `STATE_VALUE_PLUS_E`, `BETA_ONLY`, `BETA_RELIABILITY`；
- new fits = 18；reference F/E/H refits = 0/0/0；
- max 3 cycles/fit，max 54 cycles；
- 18 个 fit receipts、18 个 checkpoint manifests、18 个 reload specs 均随提交存在；
- 正式 runner 在每个 fit 保存前强制 `fit_rows=361628`、`future_target_values_read=0`、minimum canonical loss / earliest-tie checkpoint rule，并在 fresh-process reload 后评分；正式运行 exit 0 说明全部新 fit 通过该 gate；
- 未运行 F+M；未修改原 TIMEISO/XCOARSE scores/store/checkpoint；
- 本地结果提交没有 GitHub Actions workflow run。

运行身份：FactorLab `b39bb12f43a46b165d18db93191a669234077444`；Python 3.13.5 / numpy 2.2.4 / pandas 2.2.3 / torch 2.6.0+debian / CPU / cuda=false，与 accepted TIMEISO/XCOARSE 稳定字段一致。entrypoint/source-stack blob 也与 gate 一致。

云端没有本地大 scores.npz/checkpoint 张量，因此没有重新执行 18 次训练或重载，也没有逐字节重哈希大张量。本验收依赖：GitHub 小回执、冻结 runner 逻辑、正式 exit 0、逐日汇总及云端独立小证据算术复核。

## 2. Combined 主 RankIC 结果

equal-date / equal-clock，142 days：

| ordered contrast | mean | median | wins/losses | block-8 95% |
|---|---:|---:|---:|---|
| `STATE_VALUE_PLUS_E − E` | +0.0008633 | -0.0009710 | 67 / 75 | [-0.00736, +0.00920] |
| `F − STATE_VALUE_PLUS_E` | **+0.0103955** | +0.0098382 | **95 / 47** | **[+0.00481, +0.01730]** |
| `BETA_ONLY − H` | +0.0055073 | +0.0023012 | 78 / 64 | [-0.00869, +0.01963] |
| `BETA_RELIABILITY − BETA_ONLY` | **+0.0056343** | +0.0043558 | **87 / 55** | **[+0.00045, +0.01112]** |
| `E − BETA_RELIABILITY` | **-0.0018636** | -0.0024104 | 58 / 84 | [-0.00485, +0.00052] |

已验收粗分解继续精确重建：

- `F−E = +0.011258802580991234`
- `E−H = +0.009278021839895956`
- `F−H = +0.020536824420887195`

云端用提交中的 combined 汇总独立复算：

- `(STATE_VALUE_PLUS_E−E) + (F−STATE_VALUE_PLUS_E) − (F−E)` = `1.21e-17`；
- `(BETA_ONLY−H) + (BETA_RELIABILITY−BETA_ONLY) + (E−BETA_RELIABILITY) − (E−H)` = `3.47e-18`；
- `(F−E)+(E−H)−(F−H)` = `-6.94e-18`。

同样对预注册 secondary 的 decile spread 和 Top30-minus-universe 做三层闭合，6 个误差量级均小于 `1.2e-17`。这是算术路径闭合，不代表机制贡献可加或因果份额。

## 3. 科学解释

### 3.1 State side

**当前最强证据指向 state availability/mask，而不是 state values 本身。**

- `STATE_VALUE_PLUS_E−E` combined mean 只有 `+0.00086`，median 为负，block 4/8/12 全跨 0；
- per-seed 该 contrast 3 正 / 3 负；
- 两时钟×三年度中，state-values contrast 有 2 个 2018 切片为负；phase 也存在多处负值；
- 相反 `F−STATE_VALUE_PLUS_E` combined `+0.01040`，block 4/8/12 下界均 > 0；
- 6/6 per-seed `F−STATE_VALUE_PLUS_E` 为正；
- 2 clocks × 3 years 与 2 clocks × 4 phases 的该 contrast 全部为正。

因此，在这条预注册嵌套路径和已消费历史支持上，**state availability/mask 是 state 包稳定增量的主要承载位置；state values 自身没有建立稳定增量。** 这仍不是唯一因果归因。

### 3.2 Exposure side

- `BETA_ONLY−H` mean `+0.00551`，但 block 4/8/12 跨 0，说明 exposure values 单独是正点估计但稳定性不足；
- `BETA_RELIABILITY−BETA_ONLY` mean `+0.00563`，block 4/8/12 下界均 > 0；两个时钟、三个年度、四个 phase 的 ensemble mean 均为正；
- per-seed reliability contrast 4 正 / 2 负，因此不能说每个 seed 都支持；
- `E−BETA_RELIABILITY` mean `-0.00186`、58/142 日为正、84/142 日为负，block 4/8/12 仍跨 0；两个时钟的 2018/2019 与所有四个 phase 均为负，2020 转正。

因此，当前 exposure 侧最有证据的是 **reliability 的正向 ordered increment**。Exposure availability/mask **没有建立正的主 RankIC 增量，点估计反而为负**；不能因此宣称它在所有时期有害，因为区间仍跨 0，且 2020 切片转正。

### 3.3 Secondary 不改变主裁决

预注册 secondary combined：

- state-values decile `+0.00139`，Top30 `+0.00167`；
- state-availability decile `+0.00486`，Top30 `+0.00835`；
- beta-only decile `+0.00359`，Top30 `+0.00089`；
- reliability decile `+0.00024`，Top30 `+0.00245`；
- exposure-availability decile `-0.00008`，Top30 **`+0.00238`**。

尤其 exposure-availability 的 Top30 为正，但主 RankIC 为负；按预注册规则，secondary **不能救活**其主结论。因此该组件仍判为“未建立正主增量”。

## 4. 当前可接受的 R3 细分结论

在 consumed 2018–2020、固定 2016 前缀选型、同 CPU 环境、同 seed pre-DMD 初始化及独立 arm DMD/训练的条件下：

1. 完整 direct-X 包对 history-only 的正增量仍成立；
2. state 包的稳定增量主要沿 **state availability/mask** 这一嵌套步骤出现；state values 自身证据弱；
3. exposure 包中，**reliability** 是当前最稳定的正 ordered increment；
4. exposure values 单独为正点估计但不稳定；
5. exposure availability/mask 没有建立正 RankIC 增量，平均点估计为负；
6. 这些都是路径依赖的嵌套算法对比，不能转换为唯一特征重要性、Shapley 份额或经济因果贡献百分比。

## 5. 月度 CloudRidge 与后续边界

`formula_identity_not_found` 仍未解决，F+M 没有运行。当前结果不能替代月度 CloudRidge 的独立增量实验，也不能根据 fine split 反推其公式。

本任务无需补件或重跑。禁止因某个 fine contrast 弱/负而新增 seed、cycle、arm 或改路径追求转正。

仍未建立：fresh OOS、full PIT、historical event availability、tradability、total-return/account alpha、unique causal attribution、production authority。

`fresh_oos=false`、`full_pit_certified=false`、`production_authority=false` 保持。
