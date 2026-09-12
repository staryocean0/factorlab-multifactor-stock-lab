# 公库计算、私库存储

用户已明确授权：Chat负责研究交互和GitHub调度，策略数值工作在本公库的标准GitHub-hosted runner运行。私库只存代码/数据/模型/结果，其Actions继续关闭。不使用付费larger runner/GPU，不使用Actions缓存和公开artifact，不把本公库当无关通用算力服务。

## 当前两个固定profile

- `runtime-smoke`：不使用私库凭据或数据，构建依赖环境，验证计算容器断网、没有凭据环境变量，仅报告公共依赖版本及合成算式。
- `baseline-replay-v1`：只取固定私库提交与已验收baseline-replay包，复现既有2018—2020及2021—2022两钟完整账户。模型/参数不变，不训练；本轮不是新因子研究。

工作流仅允许本仓库`cloud-workspace-v1`分支上的`workflow_dispatch`。没有push/PR/fork自动执行。`concurrency`串行、45分钟任务上限、标准`ubuntu-24.04`、计算容器4CPU/12GB/无网络/只读输入。任务调用参数不能任意指定命令、私库版本、runner或数据包。

## 私库授权：一次设置，不在聊天传token

在GitHub创建fine-grained token：resource owner为私库所有者，仅选择`factorlab-multifactor-research-private`，Contents=Read and write（Metadata默认只读），建议30天到期。不授其他仓库或账户级权限，不授Workflows/Actions管理权限。

直接将token保存到本公库Settings → Environments → `private-research` → Environment secrets，名称`FACTORLAB_PRIVATE_TOKEN`。不是仓库级Actions secrets：环境仅允许`cloud-workspace-v1`分支，防止其他分支的工作流取得凭据。勿提交源码、贴聊天或复用本机广权限OAuth令牌。没有该secret，基线profile明确失败且不访问私有数据，不能据此称云端ready。

该凭据只进入可信取数/回存broker；不进入计算容器，不挂载凭据文件或Docker socket。跨主机HTTP重定向清除Authorization。公共日志只显示通用状态；完整计算日志/快照写私库新分支和私有Release，不写公开Actions artifact/summary。

## 调度与结果

Chat可通过已具备的GitHub插件调度该工作流，或由用户在Actions页面Run workflow选择profile；不得改用私库Actions。实际API示例：

```text
POST /repos/staryocean0/factorlab-multifactor-stock-lab/actions/workflows/public-compute.yml/dispatches
{"ref":"cloud-workspace-v1","inputs":{"profile":"runtime-smoke"}}
```

基线通过后，私库新增`runs/public-baseline/<run_id>-<attempt>`分支，回执为`research/public-runs/<run_id>-<attempt>.json`，完整结果位于私有Release `public-run-<run_id>-<attempt>`。Chat从私库读取这些结果，不再要求把大二进制包先送进Chat Python。

新增策略研究须在私库冻结实验目标、数据角色、代码版本、命令、预算和验收条件；然后经主控审查新增执行profile/入口。当前profile不授权任意训练，但扩展沿同一broker/隔离/回存接口，不重建基础设施。已消费期间不能变成fresh OOS，数据准入不从上传或免费计算继承。

## 当前ready口径

工作流存在、runtime-smoke成功、凭据存在、基线回放成功、私库回存及本地独立复核是分开的事实。只有最后两项有真实证据，才称当前基线公共执行通道ready。不会因为源码/数据已上传就提前关闭迁移任务。
