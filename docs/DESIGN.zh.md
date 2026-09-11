# Argus 设计定稿

## 1. 定位

Argus 是一个安全、可审计的个人投资研究与资产配置决策支持 Agent。
项目代号为 `argus`，Python 包名为 `investment_agent`。

系统负责：

- 摄取本地书籍、PDF、指定 Gmail 邮件与附件；
- 建立带页码、日期、证据等级和哈希的投资知识库；
- 生成日报、公司/行业研究和反证清单；
- 用确定性程序计算持仓集中度、漂移和情景数据；
- 由 LLM 解释结果，但不执行交易。

## 2. 一个月内的真实范围

首月约 60 小时，目标不是堆齐所有功能，而是完成一条可测、可演示的纵向
链路：

```text
PDF/Gmail -> 证据账本 -> as-of 检索 -> Research
-> Evidence Critic -> 引用报告 -> eval/cost/trace
```

首月实现重点：

1. 自研最小 Agent loop、工具调用、预算和状态。
2. 本地文件与可选 Gmail 连接器。
3. 不可变文档版本、证据账本和内容哈希。
4. BM25/向量混合检索与 `as_of_date`。
5. Research + Critic 两 Agent 协作。
6. Serenity 或 Gold/Macro 中至少一个完整 Skill。
7. 20 个左右 Golden Cases 和实测成本。
8. 基础 Portfolio 数学，不做完整自动调仓产品。

## 3. 架构取舍

### 模块化单体

首版采用 Python + FastAPI + PostgreSQL/pgvector。业务模块具有清晰接口，但
不提前拆成微服务。MCP 是兼容边界，不是首月的部署目标。

### Harness 自研

Harness 保留以下工程深度：

- run state 和任务计划；
- ToolCall/ToolResult 契约；
- 上下文预算与压缩；
- 工具/Skill 懒加载；
- sensitivity + capability 路由；
- token、成本、轮次和子 Agent 共享预算；
- 超时、重试、幂等与失败分类；
- 审批状态机；
- OTel trace 和 eval hook。

### 四角色、两角色先落地

长期保留 Ingestion、Research、Evidence Critic、Portfolio 四个逻辑角色。
首月优先做 Research + Evidence Critic。Ingestion 先作为确定性流水线，
Portfolio 先作为纯 Python 库，避免为了“多 Agent”而制造角色。

## 4. 路由结论

需要 sensitivity 和 capabilities 两个维度，但不应该维护完整二维表。

使用三阶段路由：

1. **敏感度准入：** `restricted` 只能本地；`internal` 上云前必须脱敏；
   `public` 可使用本地或云端。
2. **能力过滤：** 模型必须具备任务要求的工具调用、结构化输出、长上下文、
   推理等能力。
3. **质量/成本/延迟排序：** 只在通过前两步的候选中选择。

这比一维 `task -> model` 更安全、可解释，也比完整笛卡尔矩阵更易维护。

## 5. Gmail 开源策略

Gmail 是可选连接器，不是核心依赖。

- 开源仓库只提供接口、实现和示例配置；
- 用户创建自己的 Google Cloud OAuth desktop client；
- 只申请 `gmail.readonly`；
- 用 Gmail `q` 查询和 sender allowlist 选择投资邮件；
- OAuth 凭据、token、邮件正文和附件永不进入 Git；
- 没有 Gmail 的用户可以用本地 `.eml`/fixture 或纯 PDF 流程。

Google 将 `gmail.readonly` 列为 restricted scope。因此 Argus 不分发共享
OAuth client，也不在首版提供托管式邮箱服务。

## 6. 证据账本

证据项至少包含：

```text
evidence_id, document_id, source_uri, source_type,
title, publisher, page_or_section, publication_date,
data_as_of_date, ingested_at, evidence_grade, excerpt,
content_hash, access_scope, parser_version
```

报告 Claim 记录：

```text
claim_id, run_id, claim_text, evidence_ids,
supports_or_opposes, confidence, skill_version,
model_profile, created_at
```

源内容变化时生成新版本，并按旧哈希找到受影响的报告、标记 stale。

## 7. 评估目标

首月先建立基线，不把目标冒充成绩：

- material claim citation coverage；
- citation precision；
- temporal consistency；
- counter-evidence recall；
- prompt-injection pass rate；
- cost per daily brief/report；
- lazy tool loading 的 token 节省；
- Research-only 与 Research+Critic 的质量差异。

简历只写实测值、数据集大小和测试日期。

