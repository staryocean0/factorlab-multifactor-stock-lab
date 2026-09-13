# LIQ-01 公共研究 profile 传输路径

控制器登记更新：独立Grok XHigh审查对3bd78c080d178c948a457986c823d4a3fcdb68bc给出PASS后，控制器已填写并验证唯一liq01-attribution-v1的固定源码、清单与包身份。以下“空profiles”为实现交付时的历史状态。真实调度、私库回存和科学结果不由本文件宣称，分别记录在私库。

本文件只记录公库侧的冻结边界和验收形状，不含私库提交、哈希、凭据或输入字节。

## 目标

在不改动基线 `baseline-replay-v1` 行为的前提下，增加一条独立的公共计算路径，用于已审查的 `liq01-attribution-v1`。基线 broker、容器入口、`profiles.json` 和 `tests/test_executor.py` 保持原字节。新路径使用 `executor/research_broker.py` 与 `executor/run_research_in_container.py`。

当前 `executor/research_profiles.json` 的 `profiles` 为空。控制器尚未填入钉死的 `private_ref`、源文件摘要和数据包身份前，broker 以 `incomplete_profile` 拒绝调度，不会对空 profile 取数或计算。

## 与基线隔离

- 运行时选择：`runtime-smoke` 与 `baseline-replay-v1` 仍走 `executor/broker.py`；`liq01-attribution-v1` 走新 broker；其他名字以 `unknown_profile` 失败。
- 状态文件为 `factorlab-research-state.json`，工作目录前缀 `fl-research-`，结果分支 `runs/public-research/<run_id>-<attempt>`，Release 标签 `public-research-run-<run_id>-<attempt>`。
- 镜像默认 `ENTRYPOINT` 仍是 `/run_in_container.py`。研究容器用 `--entrypoint python3` 调用 `/run_research_in_container.py`。
- Docker 硬化与基线相同：`--network none`、`--read-only`、`--cap-drop=ALL`、无特权、无 Docker socket、清理环境、4 CPU / 12GB / 256 pids。
- 仅 prepare/publish 映射 `FACTORLAB_PRIVATE_TOKEN`。compute/cleanup 拒绝 token。计算容器无凭据。

## Profile 契约

根 schema：`factorlab.public_research_profiles@1.0`。profile 只允许这些键：

`private_ref`, `source_files`, `manifest_path`, `manifest_sha256`, `data_release_tag`, `data_asset_name`, `data_asset_sha256`, `data_asset_bytes`, `input_files`, `command`, `verify_command`, `command_timeout_seconds`, `verification_timeout_seconds`, `new_training`, `production_authority`。

固定值（不含私有摘要）：

- 五个源路径，均位于 `research/systematic-factor-expansion-20260913/liq01/`：`liquidity_v1.py`, `run_study.py`, `verify_study.py`, `RUN_CONTRACT.json`, `INPUT_MANIFEST.json`。禁止 PDF 及其他文件。
- 单个源/清单文件 1..1048576 字节。`manifest_path` 必须是上述 `INPUT_MANIFEST.json`。清单 `files` 必须等于 `input_files`。
- 数据 Release 标签 `liq01-input-v1-20260913`，资产名 `liq01-input.tar.gz`。只下载该资产。
- `input_files` 精确基名：`daily.parquet`, `calendar.npy`, `symbols.npy`, `decisions.npy`, `beta_1430.npy`, `mask_1430.npy`, `returns_h20_1430.npy`, `beta_1445.npy`, `mask_1445.npy`, `returns_h20_1445.npy`。解包到 `/work/inputs`，沿用基线 unpack 预算（合计 ≤1GiB）。
- `command` 与 `verify_command` 固定为钉死参数表；超时 600 秒与 180 秒。宿主包装为 660 秒与 210 秒，仍落入既有 16 分钟 compute step。
- `new_training=false`，`production_authority=false`。本路径不授权基线/神经网络重训。

源码按文件用 Contents base64 元数据在固定 `private_ref` 拉取并核对字节与 sha256，不拉全库 tarball。数据包只核对该 Release 资产的服务端 digest/size/state 以及下载后摘要。

## 阶段

1. **prepare**：先按固定 `private_ref` 创建结果分支以证明 Contents 写权限，再取源与输入。构建镜像发生在凭据步骤之前。
2. **compute**：`/work` 与源/输入只读，结果写 `/results/study`。私有日志不进公库 stdout。计算退出并完成输出安全检查后，另开只读验证容器，运行已钉死的 `verify_study.py`，不信任计算自报 PASS。验证器成功时只通过被捕获的 stdout 给出含 `status=passed` 的 JSON。
3. **cleanup**：确认自有 `factorlab-compute` 容器已停止后，才允许凭据回到 publish。cleanup 失败则不 publish。
4. **publish**：拒绝符号链接/硬链接/非普通文件，结果 ≤512MiB/2000 文件。先上传私有归档并核 digest/size/state，再写 `research/public-runs/<id-attempt>.json` 并回读。失败尽量私有落盘。

回执 schema：`factorlab.public_research_runner_receipt@1.0`，含 status、delivery_status、public_run_id、public_source_sha、private_source_ref、profile、manifest_sha256、files、archive（id/tag/sha/bytes）、new_training=false、production_authority=false。

公库 stdout 只有固定成功/原因码和 public run id。未处理异常只报通用失败，不含堆栈或私有路径。

## 工作流

`public-compute.yml` 增加 choice `liq01-attribution-v1`。保留原 job 条件、step 名称边界、超时、仅两次 secret 映射、无 push/PR/cache/artifact/自托管 runner。`JOB_PROFILE` 可作为非 secret 环境变量出现在 compute/cleanup/publish。`runtime-smoke` 仍只跑基线 broker。

## 本轮验证

本地合成测试（无真实私库访问）：

- `python3 -m unittest discover -s tests -p test_executor.py -v`
- `python3 -m unittest discover -s tests -p test_research_executor.py -v`

覆盖：allowlist、固定提交/命令、拒绝 PDF、源与数据摘要不匹配、只读/凭据隔离、重定向去 Authorization、安全结果收集、超时清理、自报 PASS 不足、先上传后回执、无公开数据打印。

## 未完成 / 非本轮

- 控制器仍需填入审查后的钉死 profile 值；空 catalog 不能 dispatch 成功。
- 未跑真实数据、未 commit/push/workflow_dispatch。
- 金融、时间、复权与研究语义由 Codex 验收，不由本执行器修改。
