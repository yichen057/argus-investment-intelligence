# Current Limitations

This is the complete limitations and future-work record. The root README keeps
only the constraints a new user must understand before running Argus.


- V1 is a local-first demo. File upload remains the complete default workflow.
  Robinhood now has an optional local OAuth Sidecar, read-only tool allowlist, sync endpoint,
  source-aware snapshots, and manual refresh UI. Live acceptance still requires the user to
  authorize the Argus Sidecar and approve the captured Schema manifest. Gmail remains
  unconnected.
- ChatGPT account/app connections, including any finance or banking connection,
  are not inherited by Argus. No bank transaction connector is available to this
  local application or the current Codex session.
- The default model provider remains deterministic and local. Public research
  questions can explicitly opt into Gemini 3.1 Flash-Lite, DeepSeek V4 Flash,
  or Kimi K2.6. Local evidence guards stop unsupported questions before an
  external generation call.
- DeepSeek and Kimi use their OpenAI-compatible HTTPS APIs; Gemini uses the
  Google SDK. Model switching does not use MCP. No executable MCP server or
  client has been implemented yet.
- Public-web Research uses an independent Exa Search adapter rather than the
  selected model's built-in web search. Exa returns direct URLs and bounded
  highlights/text; the shared Evidence Gate accepts, requests at most one
  targeted follow-up, or refuses before generation. Gemini, DeepSeek, or Kimi
  then acts only as the explicitly selected answer model. The UI and Run trace
  separate Exa search calls/cost from answer-model tokens/cost, and reports
  require valid Argus citation IDs. API Token summaries exclude local
  deterministic word-count estimates; Exa is metered by search usage/cost, not
  model-style input/output Tokens.
- Docker V1 stores and searches vectors in PostgreSQL/pgvector with an HNSW
  cosine index. Public-mode research can use 768-dimensional Gemini semantic
  embeddings. Exact and PostgreSQL full-text channels remain available without
  Gemini; internal mode and SQLite tests retain deterministic JSON vectors only
  as storage/plumbing infrastructure, not as a semantic-quality claim.
- Adaptive Agent Search currently means one deterministic, Evidence-Gate-named
  local or Exa web follow-up under a universal one/two-query ceiling. It does not include a
  selected-provider LLM planner, reranker, provider-independent multilingual
  embedding model, automated ledger-retention job, or multi-round paid web
  search orchestration.
- Cloud model generation calls are dual-written to a deletable Run trace and an
  independent append-only `api_usage_ledger`. The latter stores input/output
  tokens, request status, and the call-time input/output price snapshot without
  prompts, holdings, or API keys. Deleting Evidence or a Run may reduce
  **Retained Run usage**, but must not reduce **Historical API usage**. Migration
  `20260720_0019` backfills Model Calls that still exist; usage deleted before
  that migration cannot be reconstructed without a provider export. Migration
  `20260720_0020` adds exact-precision provider imports and keeps account balance/
  Free Tier snapshots separate from charges.
- Independent Exa search cost remains stored in the Run trace; a unified durable
  external-tool usage ledger is still future work. Provider billing snapshots
  are stored separately from Argus estimates because actual bills can use other
  currencies and include credits, caching, retries, taxes, or rounding. These
  values do not yet include a separate embedding-cost event ledger. The official
  DeepSeek ZIP importer records exact period totals and per-model breakdowns while
  discarding user and API-key identity columns. Kimi's tokenizer endpoint is a
  preflight estimate, and its balance endpoint reports remaining funds; neither is
  treated as historical actual usage. Gemini Free Tier is recorded as account
  status rather than a fabricated `$0` paid invoice.
  For example, `gemini-3.1-flash-lite` uses:

  ```text
  estimated USD
    = input tokens / 1,000,000 * $0.25
    + (output + thinking tokens) / 1,000,000 * $1.50
  ```

  These defaults track the
  [official Gemini Developer API pricing](https://ai.google.dev/gemini-api/docs/pricing).
  Free Tier can still produce an actual bill of $0, and Argus does not infer
  billing from this estimate. DeepSeek and Kimi defaults likewise track their
  [official DeepSeek pricing](https://api-docs.deepseek.com/quick_start/pricing/)
  and [official Kimi K2.6 pricing](https://platform.kimi.ai/docs/pricing/chat-k26).
- Browser uploads are saved under `data/uploads/`, which is ignored by Git.
- Invest Suggestions can optionally render a fixed-size sector/industry HeatmapMatrix. Set
  `ARGUS_ENABLE_MARKET_HEATMAP=true` to enable it; false retains the compact market-data card.
  Red/green encodes the latest regular-session price versus the prior completed close (`1D`, not
  weekly/yearly), neutral badges encode holdings/research roles, and an optional robust log-MAD
  Volume activity metric uses completed daily historicals when
  `ARGUS_ROBINHOOD_ENABLE_HISTORICALS=true`. The metric is a participation indicator, not a
  BUY/SELL signal. Volume states use separately colored text labels, and clicking a tile opens a
  modal with the prior-close date and Z-score calculation. Both switches require a backend restart;
  the historicals switch also requires restarting the local Sidecar.
- Set `ARGUS_ENABLE_UNIFIED_ETF_UNIVERSE=true` to replace the duplicate full Heatmap and ETF
  candidate directory with one `ETF Universe` and explicit `Market view` / `Research view` tabs.
  Both views consume the same merged view model, but the source boundary remains explicit:
  configured market data supplies Market view, while the controlled library, holdings mappings,
  and accepted evidence supply Research view. Provider status and refresh therefore appear only in
  Market view; the evidence-backed shortlist remains above both. Unheld core Rebalance/DCA
  candidates such as BND are also included in the bounded quote request so deterministic Python can
  calculate shares without model-generated numbers. Set the flag to false and restart the backend
  to restore the prior separate-directory UI without changing stored data or recommendation math.
- Research upload is capped at 25 MiB, 500 PDF pages, about 2 million extracted
  characters, and 90 seconds. Parsing runs in a monitored child process with a
  cgroup-aware RSS ceiling and a structured user-facing stop reason. The HTTP
  request still waits for parsing; an asynchronous ingestion queue, global
  concurrency semaphore, and exported Grafana memory alerts remain V2 work.
- PDF support covers simple extractable text. Complex table extraction,
  scanned PDFs, and OCR are out of scope for V1.
- Report charts are generated only from source-backed local evidence or
  structured research CSVs.
- Portfolio recommendations currently use the uploaded holdings price and
  `as_of_date`, which are shown beside the calculations. Product candidates
  link to official issuer pages, but Argus does not yet fetch licensed live
  quotes or current macro data. It therefore leaves candidate share counts
  blank when the candidate is not already in the dated holdings snapshot.
- Portfolio analysis is deterministic decision support. It can calculate
  target buy/sell amounts, estimated shares, contribution-first DCA amounts,
  and diversification review candidates, but it does not provide tax-lot
  optimization, trade execution, autonomous rebalancing, or a guarantee that a
  candidate is suitable for the user.
- DCA monthly budgets are apportioned in whole dollars and contain investments
  only. Cash saving appears in the separate deadline-based cash plan. Any
  investment class with a positive saved target can appear; set Alternatives or
  another unwanted class to 0% to exclude it. A positive target without an
  approved product is marked `UNASSIGNED` / `No
  instrument assigned`, not presented as an executable purchase.
- Kubernetes, Redis, Kafka, cloud object storage, OpenTelemetry/Grafana, and
  self-hosted GPU model serving are tracked in the V2 roadmap. The AWS/EKS
  foundation completed one bounded live acceptance on 2026-07-12: the public
  Gemini/pgvector product flow and Redis worker passed, then all 71 Terraform
  resources were destroyed. No hosted Argus environment remains online.

Argus also includes an explicit, cost-capped model-stage benchmark. It evaluates
evidence extraction and answer synthesis separately using atomic Claim IDs and
per-claim citation checks. Its recommendations never change the production
provider automatically. See [Evaluation](EVALUATION.md) and
[Interview Q&A](INTERVIEW_QA.md).

Cloud design and operations are documented in
[V2 Cloud Architecture](V2_ARCHITECTURE.md) and the
[AWS Cloud Runbook](CLOUD_RUNBOOK.md). Start the next short-lived
AWS/Kafka learning deployment with the
[Cloud Deployment Handoff](CLOUD_DEPLOYMENT_HANDOFF.md), which records
the current readiness gates, cost stop conditions, acceptance scope, and
destroy checklist.
