# Argus V1 Scope

## Goal

Build a local-first full-stack AI investment research system that is real
enough for a portfolio demo and resume discussion.

V1 should prove the core product loop:

```text
local research files
-> evidence ledger
-> RAG retrieval
-> Research/Critic agent workflow
-> cited report
-> portfolio CSV analysis
-> auto model selection, cost, and run tracking
```

V1 is not a brokerage integration, not an autonomous trading system, and not a
cloud platform. Post-V1 cloud, Redis, Kafka, Kubernetes, and production
observability work is tracked in [V2 Roadmap](V2_ROADMAP.md).

## Target Stack

| Layer | Technology | Purpose |
|---|---|---|
| Frontend | React + TypeScript | User interface |
| Backend | Python + FastAPI | API and application services |
| Database | PostgreSQL + pgvector | Relational data and vector search |
| Agent | Custom lightweight runtime | Tool calls, runs, budgets, critic workflow |
| RAG | Chunking + embeddings + pgvector | Evidence-grounded retrieval |
| Reports | Jinja2/HTML, optional PDF export | Company/industry report output |
| Local dev | Docker Compose | Run frontend, backend, database locally |
| Model ops | Auto routing + cost tracking | Balance quality, latency, privacy, and spend |
| Evaluation | Golden cases + regression metrics | Measure citation, temporal, cost, and quality behavior |
| Tests | pytest | Backend correctness and regression checks |

## User-Facing V1 Features

### 1. Local Knowledge Base

Users can upload or place local investment materials into the app:

- Markdown (`.md`)
- text (`.txt`)
- simple text PDFs (`.pdf`)
- structured research datasets (`.csv`)

The system parses files, splits them into chunks, stores metadata, and indexes
them for retrieval.

Research CSV files are for market, industry, company, or asset indicators used
in cited reports. Portfolio holdings CSV files still use the separate Portfolio
workflow.

Obsidian is optional. An Obsidian vault can be ingested as a folder of Markdown
files, but V1 is not an Obsidian plugin.

### 2. Evidence Ledger

Every retrieved claim should trace back to source evidence.

Minimum fields:

- source file path or URL;
- title;
- page or section;
- publication date when known;
- data as-of date when known;
- evidence grade;
- content hash;
- excerpt.

The evidence ledger is what makes Argus different from a generic ChatGPT
wrapper.

### 3. Knowledge Chat

Users can ask questions about their local knowledge base.

The answer must show:

- concise response;
- supporting evidence snippets;
- source references;
- a warning when evidence is insufficient.

### 4. Company or Industry Report Generation

Users can ask Argus to generate a company or industry report.

The report should include:

- title;
- executive summary;
- key facts and metrics;
- thesis;
- supporting evidence;
- counter-evidence;
- risks;
- falsification conditions;
- investment implications;
- citations.

V1 should support at least one investment style workflow:

- Serenity / supply-chain bottleneck, or
- Gold Macro.

### 5. HTML Report Export

Users can view and export a generated report as HTML.

PDF export is a stretch goal. If PDF becomes costly or brittle, V1 can ship
with HTML export only and keep PDF for V1.1.

### 6. Portfolio CSV Import

Users can upload a `holdings.csv`.

Minimum schema:

```csv
symbol,name,asset_class,quantity,price,market_value,cost_basis,account
```

Monarch screenshot OCR is a stretch goal. If implemented, OCR output must be
human-confirmed before analysis.

### 7. Portfolio Dashboard

Users can view:

- total portfolio value;
- position weights;
- asset-class allocation;
- single-position concentration;
- small positions that may not matter;
- basic risk flags.

This is deterministic Python calculation, not LLM math.

### 8. Profile and Preferences

Users can configure:

- risk tolerance;
- life stage;
- investment horizon;
- income stability;
- liquidity needs;
- target allocation;
- preferred investment style.

V1 can implement this as a simple form persisted in PostgreSQL.

### 9. Scenario-Based Rebalance Suggestions

Argus can produce bounded scenarios such as:

- maintain current allocation;
- reduce concentration;
- increase defensive assets;
- increase growth exposure;
- keep on watchlist.

The language must stay as decision support:

```text
If your goal is X, consider Y. Confirm manually before taking action.
```

V1 must not execute trades.

### 10. Auto Model Selection, Runs, and Cost Dashboard

Users can keep the model setting on `Auto` by default. Argus chooses among
admissible model profiles by sensitivity, required capabilities, measured
quality, expected cost, and latency.

Users can inspect agent runs and LLM cost.

Minimum metrics:

- total runs;
- total tokens;
- total estimated cost;
- cost by model/provider;
- selected model/provider;
- selection mode (`auto` or manual);
- selection reason;
- recent runs;
- most expensive run;
- tool calls per run;
- failed or retried runs.

This panel is an engineering feature for interviews: it shows cost awareness,
traceability, and agent runtime ownership.

### 11. Evaluation and Performance Maintenance

Argus should measure whether the system is getting better or more expensive.

Minimum metrics:

- golden-question pass/fail status;
- citation coverage;
- temporal consistency;
- critic flag or downgrade count;
- token and estimated cost per report;
- model-call latency where available;
- retrieval hit quality on seeded cases.

V1 can use deterministic mocks for local demos, but any mock usage must be
clearly labeled in the UI and README.

## Deployment and Compliance Policy

V1 is local-first. The default deployment target is a local Docker Compose stack.

Deployment rules:

- public data may be processed locally or by approved cloud models;
- internal raw data stays local unless redacted;
- restricted household and holdings data stays local;
- cloud deployment, Kubernetes manifests, and managed cloud databases are
  post-V1 deployment polish, not V1 requirements.

PCI boundary:

- Argus V1 must not ingest, store, transmit, or process payment card data;
- PCI compliance certification is out of scope for V1;
- future paid offerings should use hosted checkout/payment providers so Argus
  does not directly handle raw cardholder data.

## Backend V1 API Surface

Suggested FastAPI endpoints:

```text
POST /documents/ingest
POST /documents/upload
GET  /documents
DELETE /documents/{document_id}
POST /chat/query
POST /reports/generate
GET  /reports/{report_id}
GET  /reports/{report_id}/html
POST /portfolio/upload
GET  /portfolio/summary
POST /profile
POST /profile/guidance
GET  /profile
DELETE /profile
GET  /runs
GET  /runs/{run_id}
POST /eval/run
```

## Frontend V1 Pages

### Research

Combines knowledge chat and report generation.

Components:

- document upload;
- question input;
- report request form;
- answer/report viewer;
- citations panel;
- critic review panel;
- export button.

### Portfolio

Components:

- holdings CSV upload;
- positions table;
- asset-class chart;
- concentration flags;
- scenario suggestions.

### Profile

Components:

- risk tolerance;
- life stage;
- investment horizon;
- income stability;
- liquidity needs;
- target allocation;
- preferred style.

### Runs and Cost

Components:

- auto/manual model selector;
- recent runs table;
- token and cost summary cards;
- model/provider breakdown;
- model-selection rationale;
- evaluation summary;
- tool call trace;
- failed/retried run list.

## V1 Database Tables

Minimum tables:

```text
documents
evidence_items
chunks
chunk_embeddings
reports
claims
portfolio_positions
user_profiles
agent_runs
tool_calls
model_calls
```

Optional for V1:

```text
eval_cases
eval_results
portfolio_imports
```

## Agent Runtime V1

The runtime should support:

- run IDs;
- tool registry;
- tool dispatch;
- per-run state;
- model routing by sensitivity and capability;
- default auto model selection using sensitivity, capability, quality, cost, and
  latency;
- token and cost recording;
- max-iteration guard;
- timeout/retry for tools where useful;
- Research -> Evidence Critic workflow.

The runtime does not need to support:

- autonomous background agents;
- unbounded planning;
- multiple persistent agent teams;
- MCP integration.

## RAG V1

Required:

- chunk local documents;
- create embeddings;
- store embeddings in PostgreSQL/pgvector;
- retrieve top-k chunks;
- apply metadata filters where available;
- return evidence IDs and snippets;
- require citations for generated answers.

Stretch:

- BM25 + vector hybrid retrieval;
- reranking;
- SEC-specific parsing.

## Explicitly Out of Scope for V1

- Gmail connector;
- Robinhood API;
- Monarch direct login or scraping;
- automated trading;
- cloud deployment;
- AWS/Azure resources;
- Redis-backed async job platform;
- Kafka event streaming;
- Kubernetes production deployment;
- payment-card processing or PCI compliance certification;
- Grafana/Datadog/Splunk;
- RabbitMQ or async worker platform;
- MCP server/client integration;
- full Obsidian plugin;
- production-grade PDF table extraction;
- complex generated infographic reports.

## V1 Demo Script

The demo should be able to show:

1. Start local stack with Docker Compose.
2. Upload 2-3 local research files.
3. Ask a knowledge-base question and show citations.
4. Generate a company or industry report.
5. Show counter-evidence and critic notes.
6. Export or view the report as HTML.
7. Upload `holdings.csv`.
8. View portfolio allocation and concentration flags.
9. Configure risk profile.
10. Generate scenario-based rebalance suggestions.
11. Open the Runs and Cost page to show auto model choice, tokens, cost, model,
    and tool calls.

## Resume-Ready Definition of Done

V1 is resume-ready when all are true:

- local Docker Compose starts frontend, backend, and database;
- demo script runs from a clean checkout;
- at least 15 backend tests pass;
- at least 10 golden/eval cases exist;
- one generated report is saved as an example artifact;
- README has screenshots or a short demo flow;
- Runs and Cost page shows real model-call usage or clearly labeled mock usage;
- `Auto` model selection records a defensible selection reason;
- eval output reports citation, temporal, latency, and cost metrics;
- project bullets use only features that are actually implemented.

## Suggested Resume Bullets After V1

Use these only after implementation:

```text
Built Argus, a full-stack AI investment research platform using React,
Python/FastAPI, PostgreSQL/pgvector, and a custom agent runtime to generate
cited company and industry reports from local research files.
```

```text
Implemented evidence-grounded RAG with document chunking, vector search,
metadata filtering, and an evidence ledger tracking source, as-of date,
evidence grade, and content hash for generated claims.
```

```text
Developed a Research/Critic workflow with tool dispatch, sensitivity-aware
model routing, token/cost tracking, and portfolio scenario analysis from
user-uploaded holdings data.
```
