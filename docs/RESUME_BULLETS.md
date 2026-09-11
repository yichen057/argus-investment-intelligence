# Argus Resume Bullets

Use these bullets only after the V1 local demo remains green. They describe
implemented functionality, not V2 plans.

## Project Entry

**Argus - AI Investment Research and Portfolio Analysis Platform**  
Python, FastAPI, React, TypeScript, SQLAlchemy, PostgreSQL/pgvector, Docker
Compose, Gemini semantic embeddings, RAG, agent workflow, HTML/SVG reports,
AWS, Terraform, EKS, Redis, S3

## Concise Resume Version

- Built a local-first AI investment research platform with React/TypeScript,
  FastAPI, PostgreSQL/pgvector, SQLAlchemy, and Docker Compose for document
  ingestion, cited research answers, generated HTML reports, and portfolio CSV
  analysis.
- Implemented evidence-grounded RAG over local Markdown, text, PDF, and
  research CSV files using parsing, chunking, deterministic embeddings,
  optional 768-dimensional Gemini semantic embeddings, pgvector/HNSW top-k
  retrieval, metadata/as-of-date filtering, and an evidence ledger with source,
  section, content hash, and evidence ID tracking.
- Developed a custom Research/Critic workflow with tool dispatch, auto model
  routing policy, max-iteration guards, token/cost budgets, persisted run
  traces, citation validation, report-linked claims, and deterministic
  portfolio allocation/concentration analysis.
- Built evaluation and observability workflows with golden-question tests,
  citation and temporal-consistency checks, report regression artifacts, and a
  runs/cost dashboard for tokens, model calls, tool calls, failures, and
  estimated cost.
- Provisioned and live-validated a bounded Terraform/EKS environment with RDS
  PostgreSQL/pgvector, ElastiCache Redis, S3, ECR, Secrets Manager, IRSA, and
  Kubernetes API/frontend/worker workloads; passed a public Gemini product flow
  and Redis job, then destroyed all 71 managed resources and verified no
  project residue remained.

## Interview-Safe One-Liner

Argus is a local-first AI research system that turns local investment files and
structured datasets into evidence-cited answers, auditable HTML reports with
source-backed charts, and deterministic portfolio analysis while keeping Gmail,
brokerage, cloud, and trading integrations out of V1.

## Do Not Claim Yet

- A continuously hosted or production-hardened AWS/Kubernetes service. One
  bounded deployment-and-destroy acceptance has completed.
- Live market-data connector.
- Real external LLM API routing in production.
- Robinhood, Gmail, broker execution, or autonomous trading.
- Production-scale semantic retrieval quality; V1 validates Gemini embeddings
  on a small local corpus and retains a deterministic internal fallback.
- OpenTelemetry/Grafana production dashboard.
