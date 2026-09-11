# Argus AWS Deployment Handoff / 上云交接单

**Prepared:** 2026-07-22
**Workspace:** `/path/to/argus`
**Decision:** **Paused / 不再授权当前 EKS+MSK apply**

## 2026-07-23 decision update / 决策更新

用户决定不把 Free account 升级为 Paid plan，也不为当前个人、低流量项目继续创建
EKS、MSK、NAT、RDS 或 ElastiCache smoke 环境。因此：

- 本文后续 EKS+MSK 内容保留为历史设计与未来扩展参考，不再是当前 apply 指令；
- `46ba5f...51be1` 旧 plan 只作审计证据，禁止执行；
- 2026-07-12 已完成并销毁的 EKS/RDS/Redis/S3 smoke 仍是有效历史证据；
- MSK 从未完成真实云端消费验收，简历和面试不得声称已经部署；
- 当前 Kubernetes 学习与验收改用本机 `kind`；
- 如果在 Free account 到期前做新的 AWS 学习实验，必须使用新的轻量方案、新 plan、
  新成本估计和明确的同日硬销毁时间，不能复用本文的 EKS+MSK apply 步骤。

本次决策不删除 Terraform 或 Kubernetes 云端清单，因为它们仍可用于架构讨论、
静态验证和未来条件变化后的重新评审。

这份文档用于把“本地开发窗口”交接给一个新的“上云与学习窗口”。它不是第二份完整
Runbook；具体命令、术语、历史故障和成本运维仍以
[AWS Cloud Runbook](CLOUD_RUNBOOK.md) 为准。

## 1. 一句话结论

Argus 的应用代码、测试、Docker Compose、Terraform 语法和 Kubernetes 清单已经达到
再次进行短时 AWS smoke deployment 的基础条件。

但是，本次希望把 Kafka/MSK 也纳入云端验收，而上一次真实 AWS smoke 明确关闭了
MSK。当前仓库还缺少云端 `event-consumer` Deployment、MSK Consumer IAM 权限和
对应验收步骤。因此现在可以进入“上云准备阶段”，**还不能跳过下列阻断项直接
`terraform apply`**。

## 2. 当前已验证基线

以下结果来自 2026-07-22 的只读或本地验证：

| 检查 | 结果 |
|---|---|
| Python tests | `298 passed` |
| Ruff | 通过 |
| Frontend TypeScript/Vite build | 通过 |
| Docker Compose 合并配置 | 通过 |
| Terraform formatting | 通过 |
| Terraform validation | `Success! The configuration is valid.` |
| Kubernetes base/smoke render | `kubectl kustomize` 通过 |
| Alembic migration head | `20260722_0022` |
| Real Docker Kafka acceptance | 通过：processed `2`、duplicate `1`、DLQ `1`、consumer `running` |
| Terraform local state | 空；旧 AWS 环境已经销毁 |
| 敏感文件 | `.env`、`*.tfvars`、`*.tfstate*` 已被 Git ignore |

上一次真实 AWS smoke 在 2026-07-12 完成并销毁了 71 个资源。它证明了 EKS、RDS、
Redis、S3、IRSA、Gemini 和 pgvector 的基础路径，但**不能替代本次新增 Kafka/MSK
路径的验收**。

### 2026-07-22 local implementation checkpoint

当前窗口已经在不创建 AWS 资源的前提下完成 Gate A–E 的本地实现：

- `argus-event-consumer` 单副本 Deployment 与文件活性探针；
- 一次性、幂等的 topic bootstrap Job，创建/核对 completed、failed、retry 和 DLQ；
- MSK IAM 收紧到本次 cluster、六个 topics 和一个 consumer group；
- ConfigMap 改为显式 model selection，Secret helper 只同步 Gemini 与 Exa key；
- API migration initContainer 在 upgrade 后核对 image/database head；
- smoke overlay 删除 Ingress、HPA 和 eval CronJob，只保留四个单副本 workloads。

本地最新回归为 `303 passed`；真实 Docker Kafka 仍是 processed `2`、duplicate `1`、
DLQ `1`、consumer `running`，Consumer 重启后 lag 为 `0`；临时全新 PostgreSQL
已验证 `20260709_0001 -> ... -> 20260722_0022`。

AWS 独立残留查询中 EKS、RDS、Redis、VPC、NAT、ECR、S3 和 Secrets 均为 `0`。
MSK 只读查询返回账号尚未订阅该服务，因此即使 Terraform plan 通过，**apply 仍必须
先由用户确认账号 MSK 准入**。Decision 继续保持 **Conditional Go**。

### 当前 Git 状态

当前工作区包含尚未提交的本轮功能修改。上云前必须：

1. 审查 `git status` 和 `git diff`；
2. 完整运行本地回归；
3. 创建一个可追溯 commit；
4. 用该 commit SHA 作为 Docker image tag；
5. 验收证据中同时记录 commit SHA 和 image digest。

不要从一个未提交、无法复现的目录构建云端镜像。

## 3. Apply 前必须完成的阻断项

### Gate A — 补齐云端 Kafka Consumer

当前本地闭环是：

```text
FastAPI producer
  -> agent.run.completed.v1 / agent.run.failed.v1
  -> Kafka
  -> event-consumer
  -> dedupe / retry / DLQ / heartbeat
  -> PostgreSQL audit projection
  -> Runs Management
```

云端 Kustomize base 目前只有 API、frontend、worker 等资源，尚无
`event-consumer` Deployment。新窗口需要：

- 新增 `infra/k8s/base/event-consumer.yaml`；
- 加入 base `kustomization.yaml`；
- 在 `aws-smoke` overlay 中保持一个副本；
- 使用与 backend 相同的不可变 image tag；
- 从 Secrets Manager 同步 Kafka bootstrap/security 配置；
- 配置 consumer group、重试、审计保留期；
- 增加适合长运行进程的存活检查；
- 验证 Pod 重启后能继续从已提交 offset 消费。

### Gate B — 修正 MSK IAM 权限

现有 IRSA policy 只有 `Connect`、`DescribeCluster` 和 `WriteData`，无法完整支持
Consumer。需要根据真实 MSK ARN 增加最小必要权限，例如 topic read 和 consumer
group 权限，并把当前 `Resource = "*"` 收紧到本次集群、topic 和 group。

至少需要审核：

- `kafka-cluster:Connect`
- `kafka-cluster:DescribeCluster`
- `kafka-cluster:WriteData`
- `kafka-cluster:ReadData`
- `kafka-cluster:DescribeTopic`
- `kafka-cluster:AlterGroup`
- `kafka-cluster:DescribeGroup`

不要为了“先跑起来”给 Pod 配置 AWS 管理员权限，也不要在容器中放长期
AWS access key。

### Gate C — 明确 topic 创建方式

必须明确创建和验证以下 topics 的方式，不能假定云端一定允许自动建 topic：

- `agent.run.completed.v1`
- `agent.run.failed.v1`
- retry topic
- DLQ topic

可以使用一次性 Kubernetes Job 或受控的 bootstrap 脚本，但需满足：

- 可重复执行；
- 已存在时不报错；
- 分区数和保留期明确；
- 不记录业务正文、持仓、API Key 或完整 prompt；
- 验收后可随基础设施销毁。

### Gate D — 同步当前运行配置

现有云端 ConfigMap 是早期版本，仍包含 `ARGUS_MODEL_PROVIDER=auto`。当前产品要求用户
显式选择 answer model，且外部搜索与回答模型已经解耦。部署前需对照
`.env.example` 和 `compose.yaml`，只把本次 smoke 真正需要的配置同步到 ConfigMap
和 Secrets Manager。

原则：

- Secrets Manager 只存密钥和连接串；
- ConfigMap 存非敏感开关；
- 只启用本次验收需要的一个 answer model 和 Exa，减少费用与密钥暴露面；
- Robinhood Sidecar/OAuth **不上云**；云端验收使用脱敏文件上传；
- 不把 `.env`、provider token、Robinhood token 或 AWS 凭据构建进镜像。

### Gate E — 更新 migration 与验收基线

旧 Runbook 的“migrations 0001–0003”是历史记录。本次必须在全新 RDS 上验证：

```text
20260709_0001 -> ... -> 20260722_0022 (head)
```

还应确认 API 只运行一个 smoke 副本时执行 migration，避免多副本同时迁移。

### Gate F — 提交并冻结版本

完成 Gate A–E 后重新运行：

```bash
cd /path/to/argus
.venv/bin/pytest -q
.venv/bin/ruff check .
npm --prefix frontend run build
docker compose -f compose.yaml -f compose.v2.yaml config -q
terraform -chdir=infra/terraform/aws fmt -check -recursive
terraform -chdir=infra/terraform/aws validate -no-color
kubectl kustomize infra/k8s/base >/dev/null
kubectl kustomize infra/k8s/overlays/aws-smoke >/dev/null
git diff --check
```

全部通过后再 commit。不要在 commit 之后悄悄修改文件再构建。

### Non-blocking limitation — Redis queue 可靠性边界

这项限制**不阻止短时 smoke deployment**，但限制了可以对外宣称的能力。当前
`argus-worker` 使用 Redis List 的 `LPUSH + BRPOP` 领取任务，Job 状态保存 24 小时。Worker
领取任务后若在完成前崩溃，当前没有 visibility timeout、ack 或自动重新入队，任务可能停在
`running` 或丢失。

本次云端只验证非资金类 `healthcheck.v1` 的 `queued → running → complete` 路径，不能把它描述为
production-grade durable job queue。需要长期运行或处理关键业务前，应补充 acknowledgment、
超时重领、幂等、bounded retry 和 stuck-job recovery，或迁移到 Redis Streams/数据库队列。
详细取舍见 [Interview Q&A Q17–Q21](INTERVIEW_QA.md)。

## 4. 本次上云的严格范围

### 包含

- Terraform：VPC、EKS、ECR、RDS PostgreSQL/pgvector、ElastiCache Redis、
  S3、Secrets Manager、IRSA、AWS Budget、MSK Serverless；
- Kubernetes：API、worker、frontend、event-consumer；
- 一个节点、单副本、短时 smoke；
- 本地 `kubectl port-forward` 访问；
- Kafka completed、failed、dedupe、DLQ、heartbeat 验收；
- 验收后立即销毁并独立检查残留。

### 不包含

- 公网 ALB、DNS、TLS；
- 多 AZ、高可用、HPA；
- 生产级远程 Terraform state；
- 长时间负载测试；
- Robinhood 账号或 Sidecar；
- 自动交易；
- 生产级可靠任务队列或资金类后台任务；
- MSK Connect、Kafka Replicator；
- 长期保留任何云资源。

这次只能描述为 **cost-controlled private acceptance environment**，不能描述为
production deployment。

## 5. 成本与停止线

此前约定的最大预算是 **USD 31**，但 credits、过期时间和账号限制会变化，因此每次
`apply` 前必须由用户重新确认：

- 当前 credits；
- credits 过期日期；
- 本次可用上限；
- 计划销毁时间；
- Budget 通知邮箱仍可用。

AWS 当前说明：

- EKS 标准支持集群按 `$0.10/cluster-hour` 收费，另收 EC2、EBS、IPv4 等费用；
- NAT Gateway 按小时和流量收费；
- MSK Serverless 同时收 cluster-hour、partition-hour、读写流量和存储费用。
  AWS 官方示例中的 cluster 固定费用已达到每小时级别；实际 `us-west-2` 价格必须在
  apply 当天通过 [AWS MSK Pricing](https://aws.amazon.com/msk/pricing/) 或
  AWS Pricing Calculator 复核。

因此本次建议：

- 目标运行时间：**2–4 小时**；
- 硬性最晚销毁时间：apply 前写入交接记录；
- 不过夜；
- 不启用 ALB、HPA、NAT 之外的附加网络产品；
- 不启用 MSK Connect 或 Replicator；
- 先 `plan` 和估价，再由用户确认是否 `apply`；
- 成本异常、资源创建反复失败或预计超预算时立即停止并 destroy。

AWS Budget 是提醒，不是自动断电开关，不能把它当作绝对消费上限。

## 6. 新窗口执行阶段

### Phase 0 — 只读接管

先阅读：

1. 本交接单；
2. [AWS Cloud Runbook](CLOUD_RUNBOOK.md)；
3. [V2 Cloud Architecture](V2_ARCHITECTURE.md)；
4. [Local Runbook](LOCAL_RUNBOOK.md) 的 Kafka 验收部分；
5. [Interview Q&A](INTERVIEW_QA.md) 的 Q17–Q21：Worker、Redis、Kafka、MSK、EKS 和
   Kubernetes 取舍。

然后只读检查：

```bash
cd /path/to/argus
git status --short
git log -1 --oneline
aws sts get-caller-identity
terraform -chdir=infra/terraform/aws state list
```

预期 Terraform state 为空。`aws sts get-caller-identity` 只用于确认当前身份，不要把
完整账号信息复制到公开文档。

### Phase 1 — 本地补齐 Kafka 云端清单

完成本文件 Gate A–E。此阶段不创建 AWS 资源。

### Phase 2 — 完整本地回归

运行 Gate F 的所有命令，并使用 Docker 中的真实 Kafka 验证，而不只跑 mock：

```bash
docker compose -f compose.yaml -f compose.v2.yaml up -d \
  postgres redis kafka backend worker event-consumer frontend

docker compose -f compose.yaml -f compose.v2.yaml exec -T backend \
  python /app/scripts/kafka_local_acceptance.py \
  --bootstrap kafka:9092 \
  --api-base http://localhost:8000
```

验收应看到：

- `completed.v1` 被消费；
- `failed.v1` 被消费；
- 重复 event ID 不产生重复记录；
- 无效事件进入 DLQ；
- consumer heartbeat 为新鲜状态。

### Phase 3 — 成本和账号 preflight

- 用户确认 credits、到期日、预算和销毁时间；
- 确认 region 仍为 `us-west-2`；
- 确认学生账号允许所需 EC2、EKS、RDS、Redis 和 MSK 资源；
- 通过 AWS Pricing Calculator 更新短时成本估算；
- 确认没有旧 EKS、RDS、Redis、NAT、MSK 或 ECR 残留。

### Phase 4 — Terraform plan only

确保 `enable_kafka=true`，但不要把 tfvars 内容贴进日志。然后：

```bash
terraform -chdir=infra/terraform/aws init
terraform -chdir=infra/terraform/aws plan \
  -out=argus-aws-smoke.tfplan
terraform -chdir=infra/terraform/aws show \
  -no-color argus-aws-smoke.tfplan
```

人工审查：

- 没有意外删除或替换；
- MSK Serverless 被创建；
- 只有一个 EKS node group；
- RDS/Redis 为 smoke 尺寸；
- ALB/HPA 仍关闭；
- Budget 金额和通知地址正确；
- IAM 没有管理员权限；
- 资源数量与架构图一致。

**先向用户汇报 plan 和预计成本，再进入 apply。**

### Phase 5 — Apply、构建和部署

按 [AWS Cloud Runbook](CLOUD_RUNBOOK.md#end-to-end-procedure) 的完整流程执行：

1. apply 已审查的 saved plan；
2. 用 commit SHA 构建 `linux/amd64` images；
3. 推送 ECR；
4. 保存 image digest；
5. 生成 `aws-smoke` manifests；
6. 部署 API、worker、frontend、event-consumer；
7. 等待全部 Pod Ready/Running。

### Phase 6 — 逐项验收

不要只看 `Pod Running`。至少验证：

| 层 | 必须证明的结果 |
|---|---|
| Version | Git SHA、image tag、image digest 一致 |
| Database | 全新 RDS migration 到 `20260722_0022` |
| API | `/health` 和核心只读 API 正常 |
| Worker | Redis healthcheck job 从 queued 到 complete |
| Storage | Pod 通过 IRSA 写入和读取 S3，无静态 AWS key |
| Research | 一次低成本、脱敏的 Exa + 显式 answer model 请求 |
| Vector | 768 维 embedding、pgvector 查询和 HNSW 索引正常 |
| Kafka producer | 成功发布 completed 和 failed 事件 |
| Kafka consumer | heartbeat 新鲜、offset 推进、consumer group 正常 |
| Kafka safety | duplicate 被忽略；synthetic invalid event 进入 DLQ |
| UI | port-forward 后 Research、Portfolio、Runs Management 可访问 |
| Privacy | Robinhood 未启用，日志中无密钥、持仓金额或完整 prompt |

### Phase 7 — 学习记录

用户应亲自完成或观察以下动作，并用自己的话解释：

- `terraform plan` 与 `apply` 的区别；
- ECR 为什么只存镜像、EKS 为什么运行容器；
- Pod、Deployment、Service、ConfigMap、Secret 的关系；
- RDS、Redis、S3 分别存什么；
- 为什么较慢任务可以直接在 API 内执行，但 Argus 选择 Redis + Worker，以及当前
  `LPUSH/BRPOP` 的任务丢失边界；
- IRSA 如何让 Pod 获得短期 AWS 权限；
- Kafka producer、broker、topic、partition、offset、consumer group、DLQ；
- 为什么 PostgreSQL Runs 是 source of truth，而 Kafka 是异步传递；
- 为什么本项目现在只有少量 Consumer，Kafka 是学习与可扩展性设计，
  不是业务运行的绝对必需；
- 为什么 smoke 不能宣称 production-ready。

只保存脱敏证据：资源名称、状态、时间、SHA、digest、测试结果、成本估计。不要保存
API Key、Secret value、OAuth token、数据库密码、完整持仓或未脱敏 prompt。

### Phase 8 — 立即销毁

先生成 destroy plan，再执行它：

```bash
terraform -chdir=infra/terraform/aws plan \
  -destroy \
  -out=argus-aws-destroy.tfplan
terraform -chdir=infra/terraform/aws apply \
  argus-aws-destroy.tfplan
terraform -chdir=infra/terraform/aws state list
```

`state list` 必须为空。随后按 Cloud Runbook 独立查询并确认没有残留：

- EKS/node groups；
- MSK；
- RDS；
- ElastiCache；
- NAT Gateway/EIP/VPC；
- ECR images/repositories；
- S3 buckets；
- Secrets Manager secrets；
- AWS Budget；
- CloudWatch log groups 或其他收费资源。

第二天再看 Cost Explorer 和 credits 变化。Terraform 显示 destroy complete 并不等于
账单立刻完成结算。

## 7. Stop Conditions / 立即停止条件

出现以下任一情况，不要继续堆修复或反复 apply：

- Terraform plan 出现范围外资源；
- 预算/credits/到期日无法确认；
- 学生账号限制导致资源连续失败；
- MSK、NAT、EKS 或数据库成本估算超出上限；
- IAM 只能通过管理员权限才能运行；
- Secret 出现在 Git、终端日志或构建层；
- migration 无法在干净 RDS 一次完成；
- Kafka consumer 无法使用最小权限读取或提交 offset；
- destroy plan 不能解释每个将删除的资源；
- 用户要求停止。

此时保存脱敏错误证据，执行已有资源的 destroy，再回到本地排查。

## 8. 新窗口首条提示词

复制下面内容到新的 Codex 窗口：

```text
请接管 Argus 的 AWS 短时上云与学习验收。

工作目录：
/path/to/argus

必须先完整阅读：
1. docs/CLOUD_DEPLOYMENT_HANDOFF.md
2. docs/CLOUD_RUNBOOK.md
3. docs/V2_ARCHITECTURE.md
4. docs/LOCAL_RUNBOOK.md 的 Kafka 验收部分
5. docs/INTERVIEW_QA.md 的 Q17-Q21

当前决策是 Conditional Go。第一阶段只做只读审计和本地代码补齐，不执行
terraform apply。请先：
1. 检查 Git 状态、当前 SHA、Terraform state 和 AWS caller identity；
2. 验证交接单中的本地测试结果；
3. 补齐云端 event-consumer、MSK consumer IAM、topic bootstrap、当前 ConfigMap/
   Secrets 和 migration 0022 验收；
4. 使用 Docker 真实 Kafka 完成本地验收；
5. 提交一个可复现 commit，并用 SHA 作为 image tag；
6. 生成 terraform plan 和最新成本估计后停下来向我汇报。

只有我确认 plan、当前 credits、预算和销毁时间后，才执行 apply。部署范围是
us-west-2 的私有、单节点、单副本 smoke，包含 MSK Serverless，不包含 ALB/HPA、
生产 HA 或 Robinhood。验收后立即 destroy，并独立检查 EKS、MSK、RDS、Redis、
NAT、ECR、S3、Secrets、Budget 和 state 残留。

全过程不得输出或提交 .env、tfvars、tfstate、API Key、AWS Secret、OAuth token、
数据库密码或个人持仓。每完成一个阶段，用小白能理解的中文解释做了什么、为什么、
预期结果和失败时如何回退。
```

## 9. 最终完成定义

本次任务只有同时满足以下条件才算完成：

1. 云端 Kafka/MSK producer-consumer 闭环真实通过；
2. 应用、数据、检索、队列、对象存储和 UI smoke 通过；
3. 用户能用自己的话解释每个主要 AWS/Kafka 组件；
4. 脱敏证据记录了版本、验收和成本；
5. Terraform state 为空；
6. 独立 AWS 查询没有残留收费资源；
7. 本地版仍可通过 Docker Compose 继续使用。
