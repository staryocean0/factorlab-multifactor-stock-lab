# LCL-R3-XCOARSE-20260907-01 云端验收

日期：2026-09-07  
本地结果提交：`a427827dc9253d16ff8ec786d58c8cac13f7b050`  
任务：`LCL-R3-XCOARSE-20260907-01`

## 结论

**验收通过，限于 consumed 2018–2020 的有序条件增量诊断。**

本地执行符合冻结 Stage A：只新增 E（`28:70` exposure + reliability + exposure availability）6 次拟合；F/H 新拟合均为 0；未执行细拆臂，未执行 F+M，未因结果重跑。

## 身份与执行闭合

- 主题仓实际执行基线：`43920405fc6368620740ae1ee3c9b8c88d668413`
- FactorLab：`b39bb12f43a46b165d18db93191a669234077444`
- TIMEISO runner：`sha256:ee7036f1925ab61ed88cc96e79a0ee06af9bb2a75812a1a58f4aa2d4a61c3708`
- condition view：`sha256:7d76a03785e2d03623342c63c360ddf7680835433294f5f511163d09fba2f921`
- Python/numpy/pandas/torch/device/cuda stable fields 与 accepted TIMEISO 一致；CPU、CUDA unavailable。
- 本地提交相对云端设计提交恰好 ahead 1 commit，新增回传结果/receipt/manifest/reload spec，并只把任务文档状态改为“本地已反馈；待云端复核”；未改研究 runner 或 FactorLab 数值源码。
- 最新本地结果提交未触发 GitHub Actions。

## 6 个 E fit receipt

全部满足：

- 每 clock × seed = `1430/1445 × 11/29/47`，共 6 fits；
- 每 fit 最多 3 cycles；
- selected cycle 为该 seed/clock 三个 canonical fit-prefix losses 的最小值：
  - 1430 seed11: cycle3
  - 1430 seed29: cycle3
  - 1430 seed47: **cycle2**（cycle3 反而更差，正确保留 cycle2）
  - 1445 seed11: cycle3
  - 1445 seed29: cycle3
  - 1445 seed47: cycle3
- 每个 receipt `future_target_values_read = 0`；
- 每个 fit `fit_rows = 361628`；
- E 有独立 DMD operator digest 和 checkpoint state digest；
- 同 seed 的 pre-DMD state digest 在两时钟一致，并与 accepted F/H 身份约束对应；
- checkpoint manifest + reload spec 均随每个 E fit 回传，真实大 checkpoint / scores.npz 保持本地。

## 结果

同 TIMEISO 142 个 paired days，两时钟 F−H 逐日重建守卫通过。

### 1430

- `F−E` mean = `+0.011914758637763551`, wins `106/142`
- `E−H` mean = `+0.007317795445611625`, wins `84/142`
- `F−H` mean = `+0.019232554083375177`, wins `115/142`

三个年度的 `F−E`、`E−H` 都为正。

### 1445

- `F−E` mean = `+0.010602846524218962`, wins `100/142`
- `E−H` mean = `+0.011238248234180313`, wins `94/142`
- `F−H` mean = `+0.021841094758399272`, wins `110/142`

per-seed 中唯一明显方向例外是 1445 seed47 的 `F−E = -0.003998780136208841`；已原样保留，没有重试到转正。

### 两时钟等权 combined

- `F−E`: mean `+0.011258802580991234`, median `+0.010801806027513076`, wins `105/142`
  - moving-block 4: `[+0.006048725864005559, +0.01705598018418932]`
  - block 8: `[+0.00593851254102115, +0.017342186931933002]`
  - block 12: `[+0.005482454351278891, +0.017314750393172196]`
- `E−H`: mean `+0.009278021839895956`, median `+0.007066025050025826`, wins `86/142`
  - block 4: `[-0.00020247231790254154, +0.018143080797615427]`
  - block 8: `[-0.0010621365125196335, +0.019458336697201546]`
  - block 12: `[-0.00162036666959406, +0.019908617518263047]`
- accepted `F−H`: mean `+0.020536824420887195`, median `+0.01854030021598827`, wins `112/142`
  - block 8: `[+0.008334688697785642, +0.03317719554298435]`

按同一日同一时钟 RankIC 差值的定义，`(F−E)+(E−H)=F−H` 是算术恒等式，不是机制份额或因果可加性。

## 科学解释

1. **state package（0:28）在 E 之上提供了更稳定的有序条件增量。** `F−E` 在两个时钟、combined mean/median、105/142 日以及 block 4/8/12 区间上均为正。
2. **exposure/reliability/mask package（28:70）也有正的样本内有序增量，但稳定性较弱。** 两时钟 mean、6/6 per-seed `E−H` 都为正，不过 combined moving-block 4/8/12 区间均跨 0，因此当前不能表述为已建立的稳定独立增量。
3. 不允许将 0.01126 与 0.00928 转换为“state 占 X 多少百分比、exposure 占多少百分比”。这是按预注册嵌套路径得到的 ordered conditional contrasts，交互与顺序依赖仍存在。
4. 结果支持进入已经预注册的 Stage B 细拆，而不是重新发明 arm：
   - state side: `STATE_VALUE_PLUS_E` 以区分 state values 与 state availability；
   - exposure side: `BETA_ONLY → BETA_RELIABILITY → E` 以区分 exposure values、reliability 与 exposure availability。

## 月度 CloudRidge

本地只读搜索返回 `formula_identity_not_found=true`；云端再次检查可恢复历史上下文也没有找到精确 S_obs/1σ 定义。因此 **F+M 仍不得训练**。不能根据名称猜公式。

## 仍未建立

- fresh OOS；
- full PIT / historical causal selection；
- tradability / total return / account alpha；
- unique causal feature attribution；
- production authority；
- 月度 CloudRidge 独立增量。

`fresh_oos=false`、`full_pit_certified=false`、`production_authority=false` 保持。
