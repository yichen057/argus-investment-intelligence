# Argus V2 Roadmap

V2 turns the local-first Argus V1 demo into a cloud-ready, event-driven research
platform. This document is a post-V1 plan. It should not block the local V1
product loop.

## V2 Goal

Prove that Argus can run as a deployable service with scalable ingestion,
asynchronous workers, event streams, cloud infrastructure, Kubernetes
operations, and production-style observability.

V2 should preserve the V1 product boundary:

- no autonomous trading;
- brokerage integrations are read-only and require explicit user consent;
- no raw payment-card processing;
- restricted household and holdings data remains local-only or policy-gated;
- cloud and model routing must keep sensitivity checks as hard constraints.

## Implementation Status

The repository now contains the V2 cloud foundation: Redis cache/job adapters,
a worker runtime, versioned Kafka event envelopes and idempotent producer
configuration, encrypted S3 artifact storage, AWS Terraform, production images,
Kubernetes API/frontend/worker/CronJob/HPA/Ingress resources, readiness/liveness
probes, and OTLP instrumentation/collector configuration.

The AWS/EKS path completed one bounded live acceptance on 2026-07-12. A
cost-capped development stack passed migrations, probes, Redis worker
processing, S3 archival, Gemini generation, and 768-dimensional pgvector/HNSW
retrieval, then Terraform destroyed all 71 managed resources. This proves the
deployment path; it does not claim a continuously hosted production service.
Full Grafana hosting, production outbox delivery, and optional self-hosted
models remain follow-up work.

## Unified V2 Feature Plan

| Milestone | User / System Capability | Current Status | Completion Signal |
|---|---|---|---|
| V2.0 | Redis retrieval cache, background jobs, and live run progress | Foundation implemented | UI and workers complete cached and queued workflows end to end |
| V2.1 | Kafka event stream with versioned, idempotent consumers | Producer/contracts implemented | Consumers, retries, dead-letter handling, and replay are demonstrated |
| V2.2 | Plaid Investments read-only holdings synchronization | Planned | Sandbox connection, preview, confirmed import, refresh, and disconnect pass |
| V2.3 | Uploadable and composable investment research skill packs | Planned | Safe install and multi-style cited report fusion pass regression tests |
| V2.4 | Reproducible AWS cloud deployment and rollback | Bounded live acceptance complete | Repeat on material infrastructure changes; production hosting remains optional |
| V2.5 | Kubernetes frontend, API, worker, and scheduled workloads | Bounded live acceptance complete | Add production ingress/metrics and exercise rollback under a retained environment |
| V2.6 | OpenTelemetry, Grafana dashboards, alerts, and operating runbooks | Instrumentation foundation | Live traces, dashboards, alerts, queue lag, failures, and cost are visible |
| V2.7 | Optional vLLM or Truss model serving and routing comparison | Planned | API and self-hosted runs are compared for quality, latency, throughput, and cost |

Recommended execution order:

1. Finish V2.0 and V2.1 locally so asynchronous behavior is testable without
   cloud costs.
2. Build V2.2 Plaid against Sandbox and V2.3 skill packs against trusted local
   fixtures.
3. Run the full regression and privacy review before any live financial-data or
   cloud connection.
4. Repeat the completed bounded V2.4/V2.5 AWS acceptance only after material
   infrastructure changes, then follow the shutdown runbook.
5. Finish V2.6 operational dashboards, then treat V2.7 model serving as an
   optional inference-engineering extension.

## Target V2 Stack

| Layer | Technology | Argus Use |
|---|---|---|
| Frontend | React + TypeScript | Same user-facing app, deployed as a web service |
| API | FastAPI | Public API, auth boundary, run orchestration |
| Database | PostgreSQL + pgvector | Evidence ledger, run traces, vector search |
| Cache / jobs | Redis | Retrieval cache, token/cost counters, run progress, job queue |
| Event streaming | Kafka | Durable events for ingestion, embeddings, runs, telemetry |
| Workers | Python worker processes | PDF parsing, embedding, report generation, eval jobs |
| Brokerage data | Plaid Investments | User-authorized, read-only accounts and holdings synchronization |
| Research skills | Versioned skill packs | Upload, validate, compose, and disclose investment-analysis styles |
| Object storage | S3-compatible storage | Raw files, report artifacts, eval outputs |
| Cloud | AWS first, provider-neutral design | Container registry, database, object storage, secrets |
| Orchestration | Kubernetes | Backend, frontend, workers, probes, scaling, rollouts |
| Observability | OpenTelemetry + Grafana | traces, metrics, logs, queue lag, cost dashboards |
| Model serving | Optional vLLM or Truss | Self-hosted model endpoint for cost/latency comparison |

## Why These Technologies Fit

Redis is useful when Argus has repeated work:

- cache query embeddings and retrieval results;
- store run progress for the frontend;
- track rate limits and token/cost budgets;
- back background jobs for ingestion, embeddings, reports, and eval runs.

Kafka is useful when Argus becomes multi-service:

- publish `document.ingested` after a source is accepted;
- publish `embedding.completed` after vectors are ready;
- publish `agent.run.completed` for dashboards and eval workflows;
- publish `model.call.logged` for cost analytics;
- keep async events durable when workers restart.

Plaid Investments is preferable to brokerage-page scraping:

- use Plaid Link for explicit institution connection and consent;
- query supported investment accounts and holdings through a documented API;
- normalize institution data into the Argus holdings schema;
- avoid storing brokerage usernames, passwords, or browser sessions;
- preserve a read-only boundary with no trading or transfer capability.

Research skill packs make report methodology explicit and reusable:

- separate analysis instructions from the core agent and citation policy;
- let users select one or more investment-analysis styles for a report;
- preserve the source-backed Research/Critic workflow regardless of style;
- record skill names, versions, weights, and outputs in the report trace;
- compare how different methodologies interpret the same evidence.

Kubernetes is useful when Argus has multiple deployable components:

- frontend deployment;
- backend API deployment;
- worker deployment;
- scheduled eval CronJob;
- Redis/Kafka clients;
- health probes and rolling deployments;
- horizontal scaling for workers.

Cloud deployment is useful after the local demo is stable:

- host the frontend and API;
- use managed PostgreSQL where appropriate;
- store uploaded artifacts and generated reports in object storage;
- manage secrets outside Git;
- monitor service health and cost.

## V2 Milestones

### V2.0: Redis Cache and Background Jobs

Implement Redis locally first with Docker Compose.

Tasks:

- Add Redis service to Compose.
- Add `CacheStore` abstraction.
- Cache retrieval results by query, filters, and corpus version.
- Add job queue for document ingestion and embedding.
- Store run progress in Redis for UI polling.
- Add tests for cache hits, cache misses, and job status transitions.

Acceptance:

- repeated retrieval avoids duplicated embedding/search work;
- long ingestion/report tasks can run asynchronously;
- frontend can show queued/running/completed states.

### V2.1: Event Bus and Kafka

Add an event contract before depending on Kafka directly.

Tasks:

- Define `EventBus` interface.
- Add local in-process event bus for tests.
- Add Kafka producer/consumer implementation.
- Define versioned event schemas:
  - `document.ingested.v1`
  - `embedding.completed.v1`
  - `agent.run.started.v1`
  - `agent.run.completed.v1`
  - `model.call.logged.v1`
  - `eval.completed.v1`
- Add retry and dead-letter topic policy.
- Add consumer idempotency using event IDs.

Acceptance:

- events are published from ingestion, agent runs, and model-call logging;
- consumers can rebuild dashboard metrics from events;
- duplicate events do not create duplicate database records.

### V2.2: Plaid Investments Holdings Sync

Add a supported, user-authorized path for importing brokerage holdings. Keep CSV
upload as a fallback for unsupported institutions and local-only users.

Tasks:

- Add Plaid Link to connect an institution with explicit user consent.
- Exchange the temporary public token on the backend; never expose the resulting
  access token to the frontend.
- Encrypt Plaid access tokens at rest and redact them from logs and traces.
- Query the Investments holdings endpoint for accounts, securities, quantities,
  prices, market values, and cost basis when the institution supplies it.
- Map Plaid security and account types into the Argus holdings schema.
- Show an import preview with validation warnings before the user confirms the
  database write.
- Make refreshes idempotent using provider item, account, and security IDs so a
  repeated sync does not duplicate positions.
- Record source, provider as-of time, sync time, and missing-field provenance.
- Add manual refresh, connection status, and disconnect/delete-token controls.
- Handle Plaid item errors, re-authentication, rate limits, partial data, and
  institutions that do not support investment holdings.
- Add Sandbox fixtures and contract tests before enabling Development or
  Production credentials.
- Publish versioned `portfolio.sync.*` events for successful, partial, and failed
  refreshes without placing sensitive holding details in event payloads.

Acceptance:

- a Plaid Sandbox institution can be connected from the Argus UI;
- holdings appear in a preview and are persisted only after confirmation;
- repeated synchronization updates existing positions without duplicates;
- missing cost basis or delayed prices are displayed honestly rather than
  inferred;
- disconnecting removes the stored access token and stops future refreshes;
- Argus cannot place trades, transfer funds, or retrieve full account numbers.

### V2.3: Uploadable Research Skill Packs

Allow users to install versioned analysis methodologies and select which styles
the report should use. A skill pack influences the questions, scoring rubric,
and report sections; it must never weaken evidence, sensitivity, budget, or tool
permission controls.

Initial built-in styles:

- value / fundamentals: valuation, earnings quality, balance sheet, and margin of
  safety;
- growth: revenue durability, addressable market, reinvestment, and operating
  leverage;
- quality: competitive advantage, returns on capital, governance, and resilience;
- macro / top-down: rates, inflation, currencies, policy, and business cycle;
- dividend / income: payout coverage, cash-flow durability, yield, and dividend
  growth;
- momentum / technical: price trend, relative strength, volatility, and liquidity;
- contrarian: consensus assumptions, positioning, catalysts, and variant view;
- risk-first / capital preservation: downside scenarios, drawdown, liquidity,
  concentration, and falsification conditions.

Tasks:

- Define a declarative skill-pack format with a manifest, semantic version,
  supported report types, required inputs, analysis rubric, output sections, and
  prompt templates.
- Support `.zip` upload containing Markdown/YAML/JSON configuration; reject
  executables, path traversal, oversized files, undeclared tools, and invalid
  schemas.
- Add install preview, validation results, enable/disable, version history,
  update, and removal controls.
- Add a report-style selector with one primary style and optional secondary
  styles plus explicit weights.
- Merge compatible sections deterministically and surface conflicting findings
  rather than silently averaging them.
- Require every skill-produced claim and score to reference evidence IDs and an
  as-of date; the Critic remains independent of the selected style.
- Persist the skill-pack name, version, content hash, configuration, and model
  profile in each run trace for reproducibility.
- Display a `Methodologies used` section in HTML reports describing each style's
  contribution, agreements, disagreements, and evidence gaps.
- Add per-skill token budgets and measure latency, citation coverage, unsupported
  claim rate, and incremental cost.
- Add trusted built-in packs first; keep third-party packs sandboxed as data-only
  configuration with no arbitrary Python or shell execution.
- Add regression fixtures where the same company is analyzed using value, growth,
  macro, and risk-first styles separately and in a fused report.

Acceptance:

- a valid skill pack can be previewed, installed, selected, versioned, and
  disabled from the Argus UI;
- invalid or unsafe packages are rejected without executing their contents;
- one report can combine a primary and secondary style without duplicate
  sections or hidden contradictions;
- every conclusion remains citation-grounded and reproducible from the recorded
  skill versions and content hashes;
- reports clearly distinguish source evidence from methodology-driven
  interpretation;
- selecting additional styles shows the user the estimated token/cost impact
  before generation.

### V2.4: Cloud Deployment

Containerize the deployable services and run them in a minimal cloud
environment.

Tasks:

- Build production Docker images for frontend, backend, and worker.
- Push images to a container registry.
- Use managed PostgreSQL or a cloud database instance.
- Use S3-compatible object storage for raw files and report artifacts.
- Move secrets to a cloud secrets manager.
- Add deployment runbook and rollback steps.

Acceptance:

- a clean cloud environment can run the API and frontend;
- health checks pass;
- ingestion and chat flow work against cloud infrastructure;
- cost controls and shutdown instructions are documented.

### V2.5: Kubernetes Deployment

Move the cloud deployment behind Kubernetes manifests.

Tasks:

- Add Kubernetes manifests or Helm chart for:
  - frontend Deployment and Service;
  - backend Deployment and Service;
  - worker Deployment;
  - eval CronJob;
  - ConfigMaps;
  - Secrets references;
  - Ingress;
  - readiness and liveness probes.
- Add resource requests and limits.
- Add horizontal scaling policy for workers.
- Add rolling deployment and rollback instructions.

Acceptance:

- `kubectl apply` deploys the app into a namespace;
- pods pass readiness and liveness checks;
- backend and worker scale independently;
- failed rollout can be rolled back.

### V2.6: Observability and Operations

Add production-style monitoring after the service is deployed.

Tasks:

- Add OpenTelemetry traces across API, worker, retrieval, and model calls.
- Export metrics to Grafana-compatible backend.
- Add dashboards for:
  - API latency;
  - retrieval latency;
  - model-call latency;
  - tokens and estimated cost;
  - Kafka consumer lag;
  - Redis hit rate;
  - job failures;
  - pod restarts.
- Add alert thresholds for failures and cost spikes.

Acceptance:

- one trace shows API -> retrieval -> model -> persistence;
- dashboards show service health and cost;
- failed jobs and consumer lag are visible.

### V2.7: Optional Self-Hosted Model Serving

Add model serving only after the app and deployment path are stable.

Tasks:

- Serve a small open model with vLLM or Truss.
- Expose it through the existing model provider abstraction.
- Compare local/API/self-hosted latency and estimated cost.
- Add routing policy so self-hosted models can serve approved workloads.

Acceptance:

- the same Argus query can run against API and self-hosted profiles;
- latency, token use, and cost are recorded per provider;
- sensitivity policy still blocks disallowed cloud routes.

## V2 Interview Talking Points

- Why Redis is a better first step than Kafka for V1-scale async work.
- When Kafka becomes necessary: durable event streams, multiple consumers,
  replay, and independent services.
- How idempotent consumers prevent duplicate ingestion or duplicate metrics.
- Why Kubernetes is useful only after there are multiple services to operate.
- How readiness/liveness probes differ.
- How Redis cache keys must include query, filters, corpus version, and model.
- Why queue lag and worker failures matter for user experience.
- How OpenTelemetry traces help debug agent workflows.
- How cloud deployment changes the security boundary.
- Why Plaid Link and token exchange are safer than collecting brokerage login
  credentials or scraping an authenticated webpage.
- How provider IDs, as-of timestamps, and idempotent upserts prevent duplicate or
  misleading portfolio snapshots.
- Why absent cost basis must remain missing instead of being estimated.
- Why research skills are declarative, versioned configuration instead of
  arbitrary executable code.
- How style fusion exposes agreements and disagreements without weakening the
  Critic or citation requirements.
- How skill content hashes and run traces make generated reports reproducible.
- Why sensitivity-aware routing still matters after moving to cloud.

## V2 Resume Target Bullets

Use these only after implementation:

- Added Redis-backed caching and asynchronous workers for ingestion, embedding,
  retrieval caching, report generation, and agent run progress tracking.
- Designed and implemented Kafka event contracts for ingestion, embedding,
  agent-run, model-call, and eval telemetry events with idempotent consumers and
  dead-letter handling.
- Deployed Argus on Kubernetes with separate frontend, API, worker, and scheduled
  eval workloads, including probes, resource limits, rolling updates, and
  rollback runbooks.
- Built production observability with OpenTelemetry traces and Grafana dashboards
  for API latency, retrieval latency, token/cost metrics, Redis hit rate, Kafka
  lag, failed jobs, and pod health.
- Integrated Plaid Investments for consent-based, read-only brokerage holdings
  synchronization with encrypted tokens, schema normalization, import preview,
  idempotent refreshes, and disconnect controls.
- Built a versioned research-skill platform for uploading and composing value,
  growth, quality, macro, income, momentum, contrarian, and risk-first analysis
  styles with schema validation, citation enforcement, reproducible traces, and
  methodology-aware report fusion.

## V2 Non-Goals

- Do not add Kafka just to claim Kafka.
- Do not deploy Kubernetes before the local app is demo-ready.
- Do not process raw cardholder data.
- Do not loosen V1 sensitivity gates for cloud convenience.
- Do not turn Argus into an autonomous trading system.
- Do not collect brokerage credentials, scrape authenticated brokerage pages as
  a production integration, or request trading/transfer permissions.
- Do not execute arbitrary code from uploaded skill packs or allow a skill to
  override citation, privacy, model-routing, tool-permission, or budget controls.
