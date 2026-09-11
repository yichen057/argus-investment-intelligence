# Argus AWS EC2 Learning Smoke Runbook

> Status: the first real run completed on 2026-07-24 from Git commit
> `b9fe390cabb2`, passed migration/Kafka/page acceptance, and was destroyed with
> two matching zero-residual audits. This is a short-lived learning deployment,
> not a production architecture. Sections 4–8 remain the reproducible procedure;
> section 10 records the actual evidence, failures, lessons, and next changes.

## 1. What we are building / 到底要做什么

把 AWS 想成可以按小时租用的机房。本次只租一台临时 Linux 电脑，在里面用 Docker
Compose 启动 Argus。目标是证明“当前 Git 版本的容器镜像可以被放进 AWS、启动、完成数据库
migration、创建 Kafka Topics，并跑通真实消息验收”，完成后立即销毁。

```text
Mac + AWS CLI
  │
  ├─ Terraform ──> VPC / subnet / security group / EC2 / IAM / ECR / Budget
  │
  ├─ Docker buildx ──> ECR 中两个 sha-<Git SHA> 镜像
  │
  └─ SSM 临时通道 ──> EC2 上的 Docker Compose
                          ├─ frontend
                          ├─ API
                          ├─ worker
                          ├─ event-consumer
                          ├─ PostgreSQL
                          ├─ Redis
                          └─ Kafka
```

它**不创建** EKS、MSK、RDS、ElastiCache、NAT Gateway、ALB、HPA、域名、TLS 或多可用区
副本。原因不是这些服务没有价值，而是当前 Free Plan 不开放 MSK，单人五小时 smoke 也没有
足够业务规模来合理化 EKS、托管数据库和高可用的固定费用。

## 2. Beginner dictionary / 小白名词表

| Term | 小白解释 | Argus 中的用途 |
|---|---|---|
| AWS Region | AWS 在世界不同地区的数据中心集合 | 固定为 `us-west-2`（Oregon），防止资源散落 |
| EC2 | 按时间租用的一台云端电脑 | 一台 `m7i-flex.large` 跑所有 smoke 容器 |
| AMI | 云电脑开机时使用的操作系统模板 | Amazon Linux 2023 x86_64 |
| VPC | 只属于这个账号的一块虚拟网络 | 把本次临时资源放在同一网络边界内 |
| Subnet | VPC 中切出来的一小段地址范围 | 单个 public subnet 给 EC2 出网 |
| Internet Gateway | VPC 通向公网的“大门” | 下载软件和镜像；不等于允许别人进来 |
| Route table | 网络“路牌” | 告诉出站流量经 Internet Gateway 走 |
| Public IPv4 | AWS 给这台机器的公网地址 | 让机器无需 NAT 也能访问 ECR/SSM；按小时收费 |
| Security Group | 云端防火墙 | **0 条入站规则**；只允许实例主动向外访问 |
| EBS / gp3 | EC2 的云硬盘 | 20 GiB、加密、实例删除时一起删除 |
| ECR | AWS 的私有 Docker 镜像仓库 | 保存 backend/frontend 的不可变 SHA 镜像 |
| IAM role | 给 AWS 资源使用的短时权限身份 | EC2 只能连 SSM、拉指定 ECR 镜像 |
| Instance profile | 把 IAM role 装到 EC2 上的“卡槽” | 不在机器里保存 Access Key |
| Least privilege | 只给完成任务必需的权限 | App 本身不获 S3、MSK、RDS 等权限 |
| IMDSv2 | EC2 容器取得短时 role 凭据的受保护入口 | 强制 token；Docker 网络 hop limit 设为 2 |
| SSM | AWS 提供的受审计远程管理通道 | 不开 SSH/22 端口也能发命令和转发网页端口 |
| User data | EC2 第一次开机执行的初始化脚本 | 安装 Docker 和校验过 SHA-256 的 Compose |
| Docker image | 程序和依赖的只读打包模板 | 由同一个 Git commit 构建 |
| Container | 镜像真正运行起来的进程环境 | 七个长期服务加两个一次性初始化任务 |
| Docker Compose | 一张多容器启动清单 | 描述服务、依赖、健康检查、内存和临时数据 |
| Git SHA tag | 源码版本的身份证号码 | 镜像标签为 `sha-<12位 SHA>`，不用 `latest` |
| Migration | 让数据库表结构升级到代码需要的版本 | 启动 API 前执行并验证 `20260722_0022` |
| Topic bootstrap | 幂等创建 Kafka Topics | 单 broker smoke 使用 replication factor 1 |
| Smoke test | 小范围检查最关键路径是否能跑通 | 不代表性能、容灾、安全或生产就绪 |
| Terraform | 用代码描述和管理 AWS 资源 | 同一份蓝图负责 plan、apply、destroy |
| Terraform state | Terraform 记住“我创建过什么”的本地账本 | 敏感且不提交；destroy 依赖它找准目标 |
| `plan` | 预览将改变什么 | 只读；当前是 17 add / 0 change / 0 destroy |
| `apply` | 真正执行已保存的计划 | 必须再次批准 plan SHA、预算和销毁时间 |
| `destroy` | 按 state 删除本栈资源 | 结束计费，并在之后做独立残留检查 |
| AWS Budget | 费用提醒器 | 本栈默认 $10 月度阈值；**不是断电开关** |
| Credits | AWS 先替你抵扣账单的额度 | 不是预算，也不能阻止资源持续计费 |

### Public subnet 为什么仍然不等于“公开应用”

EC2 有公网地址，意味着它可以经 Internet Gateway 主动连接外部。但 Security Group 没有任何
入站规则，外部不能直接连接 22、8080、5432、6379 或 9092。录制页面时使用 SSM 建立一条临时
隧道，把 Mac 的 `127.0.0.1:18080` 接到 EC2 本机的 `127.0.0.1:8080`。关闭命令后通道立即消失。

## 3. Tonight's completed preparation / 今晚准备的内容

- 新栈位于 `infra/terraform/aws-ec2-smoke`，与禁止 apply 的历史 EKS/MSK 栈完全分开；
- `compose.aws-ec2.yaml` 不挂载本机源码、不使用开发服务器、不向公网暴露数据库或 Kafka；
- PostgreSQL 密码在 EC2 内生成到权限 `0600` 的文件，不进入 user data、Terraform state、
  Git、终端输出或录屏；
- EC2 没有 SSH key；磁盘加密并随实例删除；IMDSv2 强制开启；
- ECR tag 不可变、push 后扫描、只保留最近三个 SHA 镜像；
- 操作脚本会核对已批准 plan SHA，并拒绝超过六小时的销毁窗口；
- 成本脚本使用 AWS Pricing API 和 `Decimal`，不靠心算；
- 当时的 preflight draft plan 为 `17 add / 0 change / 0 destroy`；它只证明计划可执行。
  2026-07-24 后续真实 apply、业务验收和 destroy 结果见第 10 节。

## 4. Before recording tomorrow / 明天录屏前

### 4.1 先装 SSM 本地插件（不必录密码输入）

当前 Mac 已有 AWS CLI，但缺少 Session Manager plugin。它不是装到 AWS 上，而是装到 Mac，
让 `aws ssm start-session` 能真正建立隧道。Apple Silicon 的 AWS 官方安装方法：

```bash
cd /tmp
curl "https://s3.amazonaws.com/session-manager-downloads/plugin/latest/mac_arm64/session-manager-plugin.pkg" \
  -o "session-manager-plugin.pkg"
sudo installer -pkg session-manager-plugin.pkg -target /
sudo ln -s /usr/local/sessionmanagerplugin/bin/session-manager-plugin \
  /usr/local/bin/session-manager-plugin
session-manager-plugin
```

如果最后显示插件已安装即可。`sudo` 密码输入时终端不会显示字符；仍建议把安装放在正式录屏前。
若软链接提示已经存在，不要反复安装，直接执行 `session-manager-plugin` 验证。

结果: 

argus cd /tmp
argus curl "https://s3.amazonaws.com/session-manager-downloads/plugin/latest/mac_arm64/session-manager-plugin.pkg" \
  -o "session-manager-plugin.pkg"
  % Total    % Received % Xferd  Average Speed   Time    Time     Time  Current
                                 Dload  Upload   Total   Spent    Left  Speed
100 9700k  100 9700k    0     0  9599k      0  0:00:01  0:00:01 --:--:-- 9604k
argus sudo installer -pkg session-manager-plugin.pkg -target /
Password:
installer: Package name is session-manager-plugin
installer: Installing at base path /
installer: The install was successful.
argus sudo ln -s /usr/local/sessionmanagerplugin/bin/session-manager-plugin \
  /usr/local/bin/session-manager-plugin
argus session-manager-plugin

The Session Manager plugin was installed successfully. Use the AWS CLI to start a session.

### 2026-07-24 实际验证记录

执行结果：

- Apple Silicon 安装包下载成功；
- macOS installer 安装成功；
- `session-manager-plugin` 命令验证成功；
- 未记录或提交 sudo 密码；
- 后续可使用 SSM 建立到 EC2 的临时通道。

==============================

Q: 你说我有必要通过github上云吗? 是否需要学习通过github自动上云的环节?
我目前已登录aws login --profile argus-login, credits remaining是70刀, 对于这笔钱我可以在云上最长跑多久?

A: 结论：

- 今天没有必要先做“GitHub 自动上云”；先亲手完成一次 EC2 smoke 更有学习价值。
- 面试需要掌握 GitHub Actions + AWS OIDC 的原理，但可以作为下一阶段改进项。
- `$70.04` credits 远远够本次实验；本次建议只运行 4–5 小时，绝对不能为了“用完 credits”长期运行。

### 2026-07-24 GitHub CI/CD 与成本决策

- 当前先完成一次手动 EC2 smoke；
- GitHub Actions + OIDC 作为后续改进；
- 当日 5 小时基础估算为 $0.52；
- 当日 guarded estimate 为 $1.29；
- 价格是历史快照，再次部署前必须重新查询。

## 是否需要通过 GitHub 上云

GitHub 不是上云的必需环节。当前流程是：

```
你的 Mac
→ Terraform 创建 AWS 资源
→ Docker 构建镜像
→ 推送 ECR
→ EC2 启动 Argus
```

加入 GitHub Actions 后才变成：

```
git push
→ GitHub 自动测试
→ GitHub 临时取得 AWS 权限
→ 构建镜像
→ Terraform plan
→ 人工批准
→ apply
```

我的建议是分两步：

1. 现在：你亲手完成一次部署、验收和销毁，理解每一步。
2. 后续：增加 GitHub Actions，但先做 CI，不要立刻做无人监管的自动 apply。

几个小白名词：

- `CI`：代码提交后自动运行测试、代码检查和 Terraform validate。
- `CD`：测试通过后继续部署到 AWS。
- `GitHub Actions`：GitHub 提供的“自动执行命令的机器人”。
- `OIDC`：GitHub 临时向 AWS 领取一张短期通行证，不把长期 AWS Access Key 存入 GitHub。AWS 和 GitHub 都推荐这种方式。[GitHub OIDC 指南](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws)、[AWS IAM OIDC 文档](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_providers_oidc.html)

对于 Argus，未来最合理的是“半自动部署”：

- PR 自动测试；
- 手动点击 `workflow_dispatch` 启动部署；
- 生成 Terraform plan；
- 人工确认环境、成本和销毁时间；
- 再允许 apply；
- 不设置 `push main` 后直接自动 apply。

GitHub Environment 可以加入人工批准和分支限制，但某些保护功能受仓库公开性及 GitHub 套餐限制。[GitHub Environments 文档](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments)

面试可以诚实地说：

> 当前短时学习环境采用 Terraform 和脚本完成可复现部署。考虑到成本和销毁安全，我保留人工 approval gate。下一步会使用 GitHub Actions OIDC 替代长期 AWS 密钥，并自动化 CI、镜像构建和 plan，apply 仍需人工批准。

## `$70.04` 理论上能运行多久

我刚使用 `argus-login` 和 2026-07-24 AWS Price List API 重新计算了当前方案：

```
区域：us-west-2
EC2：1 台 m7i-flex.large
磁盘：20 GiB gp3
公网 IPv4：1 个
ECR 假设：2 GiB
```

计算结果：

| 口径                  | 结果                |
| --------------------- | ------------------- |
| 基础成本              | `$0.103225753/小时` |
| `$70.04` 理论运行时间 | `678.51 小时`       |
| 换算天数              | `28.27 天`          |
| 按两倍成本并留预备金  | `338.05 小时`       |
| 保守换算天数          | `14.09 天`          |
| 本次 5 小时基础估算   | `$0.52`             |
| 本次 5 小时保守估算   | `$1.29`             |

价格通过 AWS Price List API 查询；AWS 说明这个 API 可用于最新价格查询和成本规划，但最终账单仍以实际用量为准。[AWS Price List API](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/price-changes.html)

不过，理论运行时间不等于允许运行时间：

- 你的 Free Plan 明确在 **2026-07-29** 到期，实际剩余时间比 14 天短；
- `$10 Budget` 是提醒器，不会自动关机；
- credits 是账单抵扣额度，不是应该花完的预算；
- Argus 安全脚本拒绝超过 6 小时的销毁窗口；
- 本次仍建议 4–5 小时，预计保守成本 `$1.29`；
- 到硬销毁时间，即使验收没完成也先 destroy。

因此，钱不是限制因素。当前真正的限制是账号到期日、硬销毁时间和你能否完整完成录屏验收。下一步应该先执行新的 `plan` 和只读 preflight，确认后再设一个距 apply 不超过 5 小时的硬销毁时间。

=============

会影响上云流程，但不是因为 AWS 会读取文档，而是因为部署脚本要求 Git 工作区保持干净。

具体影响：

- 在 `build-push` 之前修改 Runbook：脚本发现未提交修改，会拒绝构建镜像。
- 修改后再 commit：Git SHA 会改变，镜像标签也要跟着改变。
- 镜像推送后再 commit：当前 Git SHA 和云端镜像 SHA 不一致，会破坏“源码版本和部署版本完全对应”的证据。
- 已运行的 EC2 不会因为 Markdown 变化而宕机，但审计和复现会变得混乱。

因此推荐这样做：

```
现在整理 Runbook
→ commit
→ 确认 git status 为空
→ 冻结仓库，不再编辑任何 tracked 文件
→ plan
→ apply
→ build-push
→ deploy
→ accept
→ destroy
→ 残留检查
→ 最后把实际结果整理进 Runbook
→ 再做一个 docs-only commit
```

上云期间需要记录内容时，不要直接修改仓库。可以：

- 暂时记在 macOS Notes；
- 在聊天里把脱敏结果发给我；
- 手写关键时间和结果；
- 录屏结束后再统一整理进 Runbook。

不要记录账号 ID、邮箱、密码、token、API Key、数据库密码或持仓。

所以你现在应该把已有 Runbook 修改整理并 commit。提交后，从生成最终 plan 开始直到 destroy 和残留检查结束，暂时不要再修改项目文件。销毁完成后，我们再把全过程统一同步进 Runbook。

### 4.2 登录和清理屏幕

如果登录已过期：

```bash
aws login --profile argus-login
```

浏览器中使用 IAM 用户会话，不使用 root 日常操作。录屏前关闭含个人邮箱、账号 ID、支付方式、
Access Key、Token、API Key、数据库密码或个人持仓的页面。操作脚本会验证身份，但故意不打印
identity。

### 4.3 明确当天安全参数

开始前重新截图 Credits，并选一个**距现在不超过五小时**的销毁时间。预算建议保持 $10；
根据 2026-07-23 Pricing API，五小时 base estimate 是 $0.52，二倍基础价再加 $0.25
未知用量准备金后的 guarded estimate 是 $1.29。Budget 可能延迟提醒，硬销毁时间才是主要防线。

## 5. Video 1 — Plan, cost, and stop gate / 计划、成本和停手点

### 这段要证明什么

证明你不是直接点“创建”：先确认身份会话、工具、源码版本、变更范围和价格，再等待批准。
建议 5–10 分钟。

### 操作

```bash
cd /path/to/argus
./scripts/aws_ec2_smoke.py --profile argus-login doctor
git status --short
git rev-parse --short=12 HEAD
```

给 Budget 加邮件提醒时，下面命令隐藏输入，避免邮箱进入录屏或 shell history：

```bash
read -s "TF_VAR_budget_notification_email?Budget alert email (hidden): "
export TF_VAR_budget_notification_email
echo
```

然后生成**当天最终 plan**和成本。最终 plan 会替换今晚的 draft plan，因此必须使用新的 SHA：

```bash
./scripts/aws_ec2_smoke.py --profile argus-login plan
./scripts/aws_ec2_smoke_cost.py --profile argus-login --hours 5
```

看到 `17 to add, 0 to change, 0 to destroy` 后解释：

- `17 add` 是 Terraform 对象数量，不是 17 台收费机器；
- 真正主要计时的是 1 台 EC2、1 个公网 IPv4 和 20 GiB EBS；
- `plan` 文件是二进制执行清单，SHA-256 证明批准后没人换计划；
- 此时必须停下，把 plan SHA、Credits、$10 Budget、预计运行时长和硬销毁时间发给审核者；
- 没有明确回复前，不设置 approval 环境变量，不执行 `apply`。

### 失败如何回退

- `AWS IAM session` 失败：重新 `aws login --profile argus-login`，不要换 root；
- `Session Manager plugin: MISSING`：不会影响 plan，但必须在页面录制前按 4.1 安装；
- Terraform 提示凭据无效：脚本会把 CLI login 的短时凭据只传给 Terraform 子进程；重新登录后再跑；
- plan 不是 `17/0/0`：停止，不 apply，先查为什么范围变化；
- 价格 API 失败：不猜价格，重新登录/联网后再查。

## 6. Approval gate / 必须由本人再次确认

收到明确批准后，把审核者回复中的**完整 64 位 plan SHA**和当天销毁时间设置到当前终端。
以下值不是密码，可以录制；时间示例必须换成当天实际值：

```bash
export ARGUS_AWS_APPLY_APPROVED=CREATE-ARGUS-EC2-SMOKE
export ARGUS_APPROVED_PLAN_SHA256='<完整 plan SHA-256>'
export ARGUS_HARD_DESTROY_AT='2026-07-24T20:00:00-07:00'
```

脚本会拒绝 SHA 不一致、时间已过或销毁时间超过六小时的 apply。它不能在电脑睡眠时替你自动
destroy，所以同时设置手机闹钟：“提前 30 分钟停止验收”和“硬销毁时间”。

## 7. Video 2 — Apply, images, deploy, acceptance / 创建与验收

### 这段要证明什么

证明真正创建的资源和已审核 plan 相同；镜像来自干净 Git commit；服务能完成 migration、
Kafka bootstrap、正常消费、重复去重和 DLQ；页面只能通过 SSM 临时隧道访问。总耗时可能
30–60 分钟。无需录制长时间等待画面，可以把这一个证据主题分成 “2A 创建/推镜像” 与
“2B 部署/验收” 两个原始片段，简历证据仍算一组。

### 2A：基础设施和镜像

```bash
./scripts/aws_ec2_smoke.py --profile argus-login apply
./scripts/aws_ec2_smoke.py --profile argus-login build-push
```

解释：

- `apply` 只接受刚批准的 `.tfplan`，脚本不打印账号 ID；
- Mac 是 ARM64，EC2 是 x86_64，所以 buildx 明确构建 `linux/amd64`；
- backend 和 frontend 都使用 `sha-<Git SHA>`；ECR 禁止覆盖同名 tag；
- ECR 是“保存镜像”，EC2 是“运行镜像”，两者不是同一服务。

若 ECR 报 tag 已存在，说明这个 commit 已推过；不要改成 `latest` 或开放覆盖。确认仓库中该 SHA
镜像存在后可跳过重复 push。若出现 `exec format error`，检查是否漏了 `linux/amd64`。

### 2B：Compose 和真实业务验收

```bash
./scripts/aws_ec2_smoke.py --profile argus-login deploy
./scripts/aws_ec2_smoke.py --profile argus-login accept
```

`deploy` 通过 SSM 让 EC2：

1. 确认 user data 已安装 Docker；
2. 接收不含密码的 Compose 文件；
3. 只在 EC2 内生成数据库密码；
4. 使用 EC2 IAM role 的短时凭据登录 ECR；
5. 拉 SHA 镜像；
6. 先等 PostgreSQL/Kafka healthy；
7. 执行 migration 0022 和六个 Topic bootstrap；
8. 再启动 API、worker、event-consumer 和 frontend。

`accept` 的预期证据：

- 七个长期服务处于 running；
- `Verified migration head: 20260722_0022`；
- `processed_delta: 2`、`duplicate_delta: 1`、`dlq_delta: 1`；
- completed/failed Topics 的 Consumer Group `LAG 0`。

然后启动临时页面通道：

```bash
./scripts/aws_ec2_smoke.py --profile argus-login port-forward
```

浏览 `http://127.0.0.1:18080`，录制页面和 Runs/Kafka 摘要。结束按 `Control+C`。这只关闭
Mac 到 EC2 的隧道，不删除服务，也不开放公网入口。

### 常见失败与判断

| 现象 | 小白原因 | 先检查什么 | 处理 |
|---|---|---|---|
| `TargetNotConnected` | EC2 还没在 SSM 报到 | 等 1–3 分钟；查看 bootstrap 是否完成 | 不开 22 端口；先查 IAM role、出网和 SSM agent |
| `bootstrap-complete` 不存在 | user data 安装 Docker 尚未完成或失败 | `/var/log/argus-bootstrap.log`（通过 SSM） | 修复初始化原因；必要时重建实例 |
| ECR `AccessDenied` | EC2 role 缺拉镜像权限 | role attachment 与指定 repo | 不给 Administrator；修最小权限 |
| image `exec format error` | 镜像 CPU 架构错误 | tag 和 buildx platform | 重新构建 `linux/amd64` |
| migration 失败 | DB 未 ready 或代码/schema 不匹配 | migration 容器日志 | 不绕过 migration 启 API |
| Topic bootstrap 失败 | Kafka 端口开了但 Admin API 未 ready，或副本因子错误 | Kafka health/logs | 等 healthy；单 broker 明确使用副本 1 |
| Consumer running 但验收失败 | 活着不等于正确处理消息 | processed/duplicate/DLQ/lag/DB | 逐层检查，不只看绿色状态 |
| 页面打不开 | SSM 插件、隧道或 frontend health 有问题 | 插件版本、终端是否仍运行、`127.0.0.1` | 不给 SG 添加 8080 入站作为捷径 |
| Budget 没立刻邮件 | AWS 费用和 forecast 不是实时流 | Budget 配置和账单延迟 | 仍按手机闹钟与硬时间 destroy |

如果关键验收到硬销毁时间仍未完成，优先执行 destroy。学习证据不值得突破费用边界。

## 8. Video 3 — Destroy and independent residual audit / 销毁与残留检查

### 这段要证明什么

证明你理解部署的最后一步不是“页面能开”，而是结束计费、确认没有孤儿资源。建议 5–10 分钟。

### destroy 会删除什么

- 这台 EC2 及其加密 root EBS；
- Docker named volumes 中的 PostgreSQL 数据、Redis 数据、Kafka Topics/消息/offset；
- 两个 ECR 仓库及 smoke 镜像；
- VPC、subnet、route、Internet Gateway、Security Group；
- EC2 IAM role、instance profile 和 inline policy；
- 本次 Terraform 管理的 AWS Budget。

这些运行数据没有备份，删除后不可恢复；Git、源码、本机 Docker images、其他 Terraform
目录和非本栈 AWS 资源不会被这个 state 删除。

### 操作

```bash
./scripts/aws_ec2_smoke.py --profile argus-login destroy \
  --confirm DESTROY-ARGUS-EC2-SMOKE
```

脚本随后独立检查 EC2、EBS、VPC、NAT、ECR、EKS、MSK、RDS、ElastiCache、S3、Secrets Manager、
Budget 和 Terraform state，预期均为 `0`。Free Plan 对 MSK API 可能显示
`unavailable for this account/plan`，它不等于有残留；应结合部署计划根本没有 MSK 资源解释。

最后：

```bash
aws logout --profile argus-login
unset TF_VAR_budget_notification_email
unset ARGUS_AWS_APPLY_APPROVED
unset ARGUS_APPROVED_PLAN_SHA256
unset ARGUS_HARD_DESTROY_AT
```

等 Cost Explorer 更新后再截一次费用与 Credits。它常有延迟，因此销毁后的即时数值不能单独
证明没有资源；资源 API 的零残留检查才是即时证据。

## 9. Who operates what / 哪些你做、哪些 Codex 做

| Stage | 你本人 | Codex |
|---|---|---|
| 录屏和口头解释 | 开始/结束录屏，隐藏私人窗口，用自己的话说明证据 | 提供逐段提词和即时解释 |
| 登录与批准 | 使用 IAM 用户登录；亲自确认 Credits、Budget、plan SHA 和硬销毁时间 | 只读核对，不替你扩大权限 |
| 命令执行 | 可以亲手运行上面的高层脚本，不必逐条敲底层 AWS API | 脚本替你安全编排重复命令并解释结果 |
| `apply` | 必须由你明确批准后才允许 | 不会根据旧批准或模糊表达擅自 apply |
| 验收 | 观察输出、页面并能解释 migration/Kafka/SSM | 帮你定位失败，但不伪造通过证据 |
| destroy | 到硬时间无论是否成功都亲自确认销毁 | 执行精确 state destroy 并做独立残留审计 |

“掌握”不等于背下每一条底层 CLI。面试可用的标准是：你能画出链路、解释为什么选 EC2
而不是 EKS/MSK、知道 plan/apply/state/destroy 的区别、能说出至少三类真实失败的定位顺序，
并坚持验收后 destroy。

## 10. 2026-07-24 completed run retrospective / 实际上云复盘

这一节记录真实发生过的结果，不是计划或模拟输出。重新部署时仍必须回到第 4–8 节重新登录、
重新生成 plan 和价格、重新批准，并设置新的硬销毁时间，不能把这次成功当作永久授权。

### 10.1 What was actually proven / 实际证明了什么

| Layer | Actual evidence | Correct conclusion |
|---|---|---|
| Source and artifact | 干净 Git commit `b9fe390cabb2`；Backend/Frontend 均构建为 `linux/amd64`，使用不可变 `sha-b9fe390cabb2` ECR tag | 云端镜像可追溯到精确源码版本；没有使用 `latest` |
| Infrastructure | 已批准 saved plan 被真实 apply；一台 EC2、加密 gp3、零 SG 入站、IAM role、SSM、两个 ECR 和 $10 Budget 创建成功 | 证明的是单 EC2 learning smoke，不是 EKS/MSK 或生产 HA |
| Deployment | EC2 通过 instance role 拉取 ECR 镜像；Compose 启动 PostgreSQL、Redis、Kafka、API、Worker、Consumer 和 Frontend | 不需要在机器中保存长期 AWS Access Key，也没有开放 SSH |
| Database and messaging | `Verified migration head: 20260722_0022`；`processed_delta=2`、`duplicate_delta=1`、`dlq_delta=1`；completed/failed Topics 的 Consumer Group lag 为 0 | 同时证明正常处理、幂等去重、坏消息隔离和无积压；不是只看容器 Running |
| Private access | SSM port-forward 把 Mac `127.0.0.1:18080` 临时接到 EC2 loopback Frontend | 有 public IPv4 不等于应用公开；关闭隧道后入口消失 |
| Teardown | Terraform destroy 成功；EC2、VPC、NAT、EBS、ECR、EKS、RDS、ElastiCache、S3、Secrets、Budget 和 state 连续两次为 0；MSK 查询因账号计划显示 unavailable | 本栈主要计费资源和 Terraform 账本均清空；MSK unavailable 不是全账号 MSK 零残留证明，但本 plan 从未创建 MSK |
| Credential closure | `aws logout --profile argus-login` 删除本地 login cache；已签发 token 最多 15 分钟后过期 | CLI logout 与浏览器 Console sign-out 是两件事，二者都要完成 |

销毁后 Console 仍可能短时显示 `Terminated` EC2，CloudTrail 仍保留管理事件，Cost Explorer/Credits
也会延迟更新。这些是历史记录，不等于实例或磁盘仍在计费；即时判断应以资源 API 和 state 为准。

### 10.2 Problems encountered and how they were handled / 实际问题与解决办法

| Symptom | Root cause | Safe handling | Lesson |
|---|---|---|---|
| `fatal: not a git repository` | 终端当时位于 `/tmp`，不是项目目录 | 先 `pwd`，再回到项目绝对路径后执行 Git 命令 | 先确认上下文，再怀疑 Git 或代码 |
| `argus-terraform` 无法再次 `aws login` | 该 profile 已配置 Credential Process，CLI 拒绝覆盖 | 新建用途单一的 `argus-login`；日常使用 IAM 用户而不是 root | Profile 是本机登录配置，不是 AWS 账号或 IAM 用户本身 |
| 新 login 提示没有 Region | 新 profile 没有默认区域 | 本栈固定使用 `us-west-2`；所有脚本也显式传 Region | Region 是资源隔离和残留审计边界，不能随意接受不同默认值 |
| Mac 缺少 `session-manager-plugin` | AWS CLI 不包含交互式 Session Manager transport | 安装 AWS 官方 Apple Silicon package，并在正式录屏前验证 | CLI 发 API 请求与本机建立 SSM 隧道是两个组件 |
| ECR push 出现 Docker `broken pipe` | Docker Desktop 通过本地代理上传 layer 时连接中断；不是应用编译错误 | 保持同一不可变 SHA，不改成 `latest`；网络稳定后重试，成功 layer 可按内容复用 | 先区分 build 失败与 registry/network push 失败 |
| `--progile` 导致 `invalid choice: argus-login` | CLI option 拼写错误，解析器把后续值当成子命令 | 改为 `--profile argus-login`，不修改云端资源 | 读 usage 中“哪个 token 被当成 command”，比盲目重跑更快 |
| CloudTrail 首页像是没有 Event history | 新 Console 默认停在介绍页/`Data event coverage`；左侧导航折叠 | 展开导航或进入 Event history；没有创建 Trail/Lake | Event history、Trail、Lake、Data Events 是不同概念 |
| `Data event coverage=0%` / `Not covered` | 没有显式创建收费的 data-event selector；很多 VPC/ECR 类型本身不支持 data events | 保持关闭；使用免费的 90 天 management Event history 审计创建/修改/删除操作 | 0% data coverage 不等于管理操作没有审计 |
| ECR scan 出现大量 Critical/High | 基础镜像包含当日漏洞数据库命中的 OS packages | 导出脱敏 CSV，先按架构、调用路径、修复版本和暴露面分流；不在硬销毁窗口内临时大升级 | Scanner 是风险信号，不是 exploitability 或生产事故结论 |
| 想在同一 EC2 上发布第二个 Git SHA 时发现脚本缺口 | `/opt/argus/.env` 只在首次部署创建，后续 `deploy` 不会更新其中的 image URI | 本轮不做不可审计的服务器手改；销毁后把 secrets 与 release metadata 分离，再补二次发布测试 | “能首次部署”不等于“能安全升级和回滚” |
| residual 中 MSK 为 `unavailable for this account/plan` | Free Plan 不允许该 API，不是发现了 MSK 集群 | 结合 approved plan 无 MSK、Terraform state=0 如实说明范围 | 查询失败必须标为 unavailable，不能伪造成 0 |

### 10.3 ECR vulnerability snapshot / 镜像漏洞快照

2026-07-24 的 ECR Basic Scanning CSV 保存在仓库之外，未提交账号标识、凭据或部署 state。扫描结果
绑定当时的镜像 digest 和漏洞数据库快照；基础镜像或漏洞数据库变化后，数量也会变化。

| Image | Total | Critical | High | Medium | Low | Main inherited package finding counts |
|---|---:|---:|---:|---:|---:|---|
| Backend (`python:3.12-slim`) | 16 | 4 | 8 | 3 | 1 | Perl 10、SQLite 2、glibc 2、util-linux 1、diffutils 1 |
| Frontend runtime (`nginxinc/nginx-unprivileged:1.27-alpine`) | 74 | 4 | 28 | 35 | 7 | Expat 21、OpenSSL 19、libpng 11、libxml2 6、curl 5 等 |

不能只按红色数字排序。至少要问：

1. **Fix available?** 当前 CSV 没有 fixed-version 字段，必须查 Debian/Alpine/上游镜像公告。
2. **Architecture applicable?** 本次是 `linux/amd64`；只影响 32 位或其他架构的条目要单独标记。
3. **Reachable?** 静态 Nginx 是否真的解析不可信 XML/CMS？Python API 是否调用 Perl
   Storable/Socket？“包存在”不等于“漏洞路径可达”。
4. **Exposed?** 本次零 SG 入站且页面只经 SSM；它降低远程暴露，但不替代补丁。
5. **Residual risk?** 无可用修复或不可达时要记录接受理由和复查日期，而不是删除扫描结果。

因此正确动作是“升级最小基础镜像、重建、重新扫描、跑本地与云端回归”，而不是看到 Critical 就
直接在正在计费的机器里 `apk upgrade`、`apt upgrade` 或手改容器。

### 10.4 Approved-next-change candidates / 待确认的下一轮修改

以下尚未实施，必须在新的本地分支中完成、测试并提交，再开新的短时云窗口：

1. **Base-image refresh and pinning**：把 Backend、Frontend build/runtime 镜像升级到有安全修复的
   受支持版本，并使用明确 patch tag + digest；不要继续依赖漂移的宽泛 tag。
2. **Smaller runtime images**：Backend 使用 multi-stage wheel/runtime，Frontend 使用更精简的
   unprivileged static runtime，减少不需要的 Perl、图像/XML 等包；不能为了少告警删除运行必需库。
3. **Local scan gate**：在 push 前生成 SBOM，并用 Trivy/Grype 或等价工具检查 fixable
   Critical/High；保存机器可读报告，并为暂不可修条目建立有到期日的 baseline。
4. **Safe second release**：把永久 secret 与每次发布的 image URI 分开；新 SHA 原子更新 release
   metadata，先验证两个 ECR 镜像存在，再 pull、migration、health 和 `accept`。
5. **Rollback boundary**：记录 previous SHA，提供显式回滚；migration 必须向前兼容，不能承诺
   Docker image 回滚会自动回滚数据库 schema。
6. **Idempotent/retriable push**：为 Docker/ECR transient `broken pipe` 增加有上限的退避重试；
   仓库已有 SHA 时只在确认目标 image/digest 有效后跳过，不开放 mutable tag。
7. **Regression tests**：证明第二次 deploy 更新 Backend/Frontend SHA、保留数据库密码和 named
   volumes、重新跑 migration/topic bootstrap/accept，并在失败时保留上一版可恢复路径。
8. **Evidence and docs hygiene**：部署期间冻结 tracked worktree；扫描 CSV、截图、视频放在仓库外并
   脱敏；销毁后再做 docs-only commit。

单 EC2、单副本 Compose 的更新可能短暂停机。补完上述能力后也只能称为“可重复的 staging-style
in-place release”，不能称为 ALB/ECS/EKS blue-green、rolling update 或 zero-downtime production
deployment。
