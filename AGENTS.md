# 公库：标准免费计算执行器

2026-09-13用户授权新增独立LIQ-01研究profile：`liq01-attribution-v1`，沿research_broker.py和research_profiles.json，仅取固定私库提交的五个源/清单文件与一个有界输入包；论文及其他私库文件不进入容器。原baseline broker、容器入口与profile原字节保留。下文“两profile”是基线验收时范围，现按这一显式追加读取。真实LIQ结果仍须公库执行、私库回存和独立核验，不能把配置/合成测试当金融增量。

用户明确采用ChatGPT网页版Chat作为研究交互入口，GitHub插件具备公私库读写。实际策略数值计算由本公库标准GitHub-hosted runner执行；私库只存数据、代码版本、模型与结果，私库Actions保持关闭。不使用Work、付费larger runner/GPU或额外云服务。

先读docs/public_execution.md。当前仅允许public-compute.yml的手动runtime-smoke与baseline-replay-v1两个profile。不得添加push、pull_request或pull_request_target执行私密任务；不得输入任意代码版本/命令/runner。新研究在私库冻结目标与数据边界，经审查注册新profile，不能借本轮基线迁移自动开启训练或因子搜索。

FACTORLAB_PRIVATE_TOKEN仅存于private-research环境；该环境只允许cloud-workspace-v1分支。不得放仓库级Secrets，不在聊天/代码/日志打印token，不复用本机广权限OAuth。broker持凭据取数回存；断网只读计算容器没有凭据，不挂载Docker socket或宿主敏感目录。

全部私密结果、模型、数据、日志、异常堆栈只存私库；不使用公开Actions artifact、cache或summary传私密内容。公库日志只允许通用状态/公共依赖信息。不得把输出写公库作为“回存成功”。

独立源码审查和合成单元测试可由本地主控执行；真实数据回放及策略计算只跑本公库标准runner。检查执行状态、私库回执和独立结果比对后才能验收，文件存在或缺凭据的预检不能称云端ready。

保留旧main、旧PR与冻结基线，不清理或强推。bootstrap.py仅是旧终端参考，不是当前Chat入口。用户预算与金融/时间/复权语义不由执行器或子代理修改。
