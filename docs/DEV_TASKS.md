# Argus V1 Development Tasks

This checklist is the working plan for building V1. Keep it stricter than the
long-term design docs.

## V1 Status

V1 is complete as of 2026-07-12. Phases 0-10 and their exit criteria are
implemented and verified. Remaining unchecked tasks are explicitly V1.1 or
Post-V1/V2 work and do not block the local V1 release.

## 2026-07-18 portfolio and method-panel refinement

- [x] Add FINRA-style retirement inputs for current savings, after-tax spending,
      other-income tax treatment, ages, inflation, tax rates, return, account type,
      and inflation-adjusted deposits.
- [x] Back-solve the retirement starting deposit with visible accumulation and
      withdrawal formulas and a modeled zero ending balance.
- [x] Render structured FastAPI validation errors as field-level messages instead of
      `[object Object]`.
- [x] Allow a validated sector/industry ETF shortlist to appear without a dollar
      satellite budget; use the budget only to calculate optional DCA dollars.
- [x] Support a bounded panel of up to five expert method documents with per-item deletion.
- [x] Keep expert methods outside the evidence index and deterministic trade math.
- [x] Accept a direct emergency reserve amount plus a savings deadline.
- [x] Separate the ETF research universe from the maximum-three recommendation output.
- [x] Expand the controlled universe to 11 broad sectors + State Street's 18 current industry ETFs + SOXX, grouped in the UI.
- [x] Parse and validate structured, cited market-watchlist candidates.
- [x] Show Exa returned-result diversity separately from Evidence Gate acceptance.
- [x] Render cash goals as funded progress and actionable monthly savings schedules.
- [x] Add a separate real-dollar retirement model that back-solves required monthly investing through age 100.
- [x] Highlight up to three validated sector/industry ETF candidates across Rebalance, missing exposure, and the controlled library.
- [x] Reserve a Profile-capped sector satellite budget and assign it only to validated DCA-suitable candidates.

## 2026-07-20 multi-issuer ETF and retirement-account refinement

- [x] Add Vanguard peers for each of the eleven State Street broad-sector ETFs.
- [x] Verify first-party ETF links; use a specific product profile when it resolves correctly,
      otherwise fall back to the issuer's verified ETF directory with ticker-search guidance.
- [x] Request comparable-window performance, cost, liquidity, benchmark, and overlap
      evidence for same-exposure peers in the bounded second Exa search.
- [x] Explain that `N recommended · max 3` is a quality-gated count, not a search limit.
- [x] Distinguish exact ETF holdings from deterministic direct-stock sector exposure and
      show expandable related stock symbols.
- [x] Add visually distinct exact-held, related-stock, recommended, and combined states.
- [x] Enforce typed ETF candidate modes: new exposure, non-additive diversification
      replacement, or existing-holding review; reject mode/holdings conflicts.
- [x] Support mixed Traditional + Roth retirement savings with an explicit pre-tax
      withdrawal share.
- [x] Display the tax-excluded baseline prominently when relevant tax assumptions are blank.

## Phase 0: Project Hygiene

- [x] Initialize Git repository if missing.
- [x] Remove generated files from source control (`.DS_Store`, caches).
- [x] Update README to point to `docs/V1_SCOPE.md`.
- [x] Add Docker Compose skeleton for frontend, backend, and PostgreSQL.
- [x] Add backend app entry point.
- [x] Add frontend app skeleton.
- [x] Keep tests passing after every phase.

Exit criteria:

- `pytest` passes.
- `docker compose config` validates.
- README explains how to start local dev.

## Phase 1: Backend Foundation

- [x] Create FastAPI app.
- [x] Add health endpoint.
- [x] Add configuration loader.
- [x] Add SQLAlchemy database connection.
- [x] Add Alembic migrations.
- [x] Create tables:
  - [x] documents
  - [x] evidence_items
  - [x] chunks
  - [x] chunk_embeddings
  - [x] reports
  - [x] claims
  - [x] portfolio_positions
  - [x] user_profiles
  - [x] agent_runs
  - [x] tool_calls
  - [x] model_calls
- [x] Add repository layer for documents and evidence.

Exit criteria:

- Backend starts locally.
- Health endpoint works.
- Database migration creates V1 tables.
- Unit tests cover DB connection and a repository write/read.

## Phase 2: Local Knowledge Base

- [x] Implement local file ingestion for `.txt`.
- [x] Implement local file ingestion for `.md`.
- [x] Add simple PDF text extraction.
- [x] Normalize document metadata.
- [x] Compute content hash.
- [x] Create chunking function.
- [x] Store chunks and evidence items.
- [x] Add `/documents/ingest`.
- [x] Add `/documents`.
- [x] Auto-upload Research evidence immediately after file selection and keep the
      indexed-source panel as the authoritative success state.
- [x] Return a scanned/image-only PDF OCR message and clean failed managed uploads.

Exit criteria:

- Uploading a local file creates document, evidence, and chunk rows.
- Re-ingesting the same file is idempotent or creates a clearly versioned row.
- Tests cover `.txt` and `.md` ingestion.

## Phase 3: RAG Retrieval

- [x] Add embedding provider abstraction.
- [x] Implement one working embedding path.
- [x] Add `gemini-embedding-001` semantic embeddings for explicitly public
      sources with separate document/query task types.
- [x] Cache chunk embeddings and map provider quota exhaustion to HTTP 429.
- [x] Store vectors in PostgreSQL/pgvector for Docker V1; retain SQLAlchemy JSON
  vector storage as the SQLite test fallback.
- [x] Implement top-k vector search.
- [x] Return evidence snippets and metadata.
- [x] Add basic metadata filters.
- [x] Add `as_of_date` filter where dates are present.
- [x] Create retrieval tool `retrieve_evidence`.
- [x] Add current-document fallback for `this article` / uploaded-document
      questions.
- [x] Scope retrieval to selected `document_id` from the Research UI.
- [x] Add exact/alias retrieval for finance identifiers, dates, numbers, and
      normalized phrases.
- [x] Add PostgreSQL `tsvector` full-text ranking with a GIN index and a portable
      SQLite lexical fallback for tests.
- [x] Fuse exact, full-text, and eligible semantic rankings with weighted RRF;
      deduplicate normalized passages and expand neighboring chunk context.
- [x] Add deterministic Fast/Standard/Deep eligibility routing plus a unified
      Evidence Gate. Run one Hybrid Retrieval, accept/refuse direct support, and
      allow at most one named-gap follow-up under hard one/two-query ceilings.
- [x] Reuse the Gate's accepted evidence IDs for model input, citations, answer
      metadata, report eligibility, and Evidence Ledger acceptance state.
- [x] Add an independent, bounded Exa Search adapter for public-web evidence;
      normalize direct URLs and highlights/text, allow at most one named-gap
      follow-up, and keep Gemini/DeepSeek/Kimi answer-only with no hidden fallback.
- [x] Split Exa search calls/cost from answer-model tokens/cost in Research and
      Runs metadata; validate answer citation IDs before enabling HTML reports.
- [x] Persist normalized Evidence Ledger query-to-chunk/evidence links without
      copying passage bodies into every run; expose the ledger in run detail.
- [x] Mark only Evidence-Gate-accepted items as accepted and rehydrate
      canonical evidence when generating reports from compact traces.

Exit criteria:

- A query retrieves relevant chunks from uploaded documents.
- Retrieval returns evidence IDs and source metadata.
- At least one test proves future-dated evidence is excluded.

## Phase 4: Agent Runtime

- [x] Implement tool registry.
- [x] Implement tool dispatch.
- [x] Implement model provider abstraction.
- [x] Implement one model provider, or a deterministic mock for local demo.
- [x] Add optional Gemini provider for explicitly public research questions.
- [x] Add Gemini request timeout/retry, real usage metadata, and estimated cost.
- [x] Implement agent loop with max iterations.
- [x] Record `agent_runs`.
- [x] Record `tool_calls`.
- [x] Record `model_calls`.
- [x] Track token and cost per model call.
- [x] Connect existing routing policy to runtime.
- [x] Keep local as the privacy-first default and require an explicit UI choice
      for Gemini, DeepSeek, or Kimi external generation.
- [x] Store model-selection reason on each run.
- [x] Add budget/cost guardrails around model calls.
- [x] Add timeout/retry for tool calls where practical. V1.1 hardening.

Exit criteria:

- A mock model can call `retrieve_evidence` and produce a cited answer.
- Tool calls and model calls are persisted.
- Cost totals appear in stored run data.
- Auto selection balances admissible model, capability, cost, and latency.
- Tests cover allowed tool, denied tool, and budget exceed cases.

## Phase 5: Research and Critic Workflow

- [x] Define structured claim schema for generated report sections.
- [x] Implement Research Agent workflow.
- [x] Implement Evidence Critic workflow.
- [x] Critic checks missing citations.
- [x] Critic checks unsupported claims at a simple rule level.
- [x] Critic requires counter-evidence section for reports.
- [x] Add `/chat/query`.
- [x] Add `/reports/generate`.
- [x] Make CSV answers focus on question-specific metrics.
- [x] Clear citations when the final answer has no relevant evidence.
- [x] Avoid answering investment-advice prompts from CSV-only historical metrics.
- [x] Reject answers when explicit query years are not covered by local evidence.
- [x] Route factor/driver questions to factor-like CSV columns instead of
      outcome columns.
- [x] Add vector-plus-lexical hybrid retrieval so exact PDF passages outside a
      weak embedding top-k can still be recovered.
- [x] Add explicit indexed, cited-web, and hybrid evidence scopes while keeping
      local excerpts and provider-grounded URLs in separate assurance classes.
- [x] Expose search scope and selected-provider internet boundary above Ask so
      web-only research works discoverably without uploaded documents.
- [x] Separate evidence-source upload from Method Pack upload and prevent either
      file type from silently entering the other storage path.
- [x] Reject weak-overlap local excerpts, PDF page labels, and question-form headings
      instead of presenting them as source-backed answers.
- [x] Distinguish provider web search not invoked from search completed without URLs;
      persist failed-call tokens and estimated cost without switching providers.

Exit criteria:

- User can ask a question and get an answer with citations.
- User can generate a report with claim/evidence links.
- Critic can downgrade or flag at least one seeded weak claim.

## Phase 6: Report Rendering

- [x] Create report JSON schema.
- [x] Create HTML report template.
- [x] Render company/industry report to HTML.
- [x] Store rendered report.
- [x] Add `/reports/{report_id}`.
- [x] Add `/reports/{report_id}/html`.
- [x] Add thesis, risks, counter-evidence gaps, falsification conditions, and
      investment implications to the report schema and HTML output.
- [x] Reject report generation when no source-backed answer exists.
- [x] Generate reports from an existing source-backed Ask trace instead of
      rerunning the agent workflow.
- [x] Repair sentence splits from bounded neighbor context, reject dangling
      conjunction fragments, and require substantive report-ready analysis in
      both frontend and backend gates while preserving structured CSV reports.
- [ ] Add optional PDF export if time permits. V1.1.

Exit criteria:

- Generated report can be viewed in browser as HTML.
- Report includes citations and critic review.
- One sample report is committed under `examples/` or documented in README.

## Phase 7: Portfolio and Profile

- [x] Define CSV/XLSX/XLS holdings parser.
- [x] Add `/portfolio/upload`.
- [x] Add browser file upload through `/portfolio/upload-file` with a 10 MB
      application limit while retaining the path endpoint for compatibility.
- [x] Persist `portfolio_positions`.
- [x] Calculate total value.
- [x] Calculate position weights.
- [x] Calculate asset-class allocation.
- [x] Calculate concentration flags.
- [x] Define user profile schema.
- [x] Add `/profile` GET/POST/DELETE; DELETE idempotently deactivates the saved
      profile so the UI can restore unsaved example defaults without silently
      applying them as a personal target.
- [x] Persist and display a single `as_of_date` for each imported holdings
      snapshot; accept the date from the browser or an optional spreadsheet
      column and reject mixed/conflicting dates.
- [x] Generate deterministic target buy/sell dollar amounts and estimated
      whole/fractional shares with price-date and tax-data warnings.
- [x] Add diversification-gap candidates backed by official issuer links.
- [x] Add contribution-first dollar-cost-averaging amounts from a saved monthly
      contribution.
- [x] Round DCA budgets to whole dollars while preserving the monthly total;
      keep cash out of DCA, explain whole-share leftovers, and support opt-out
      through a 0% investment target.
- [x] Add deterministic Profile allocation guidance using suitability and cash-
      flow inputs, persist recurring monthly net income, and keep suggested
      one-decimal targets editable and unsaved until explicit Save.
- [x] Distinguish a saved personal policy target from the no-profile 20%
      example concentration review level in the API and UI.
- [x] Expand Profile target classes to Commodity / Gold, International Equity,
      and Alternatives with symbol-aware position normalization.
- [x] Compare maintain, contribution dilution, and partial sell/reallocation
      scenarios with projected weights, amounts, shares, and known limits.
- [x] State in the product that portfolio reasons and calculations come from
      deterministic rules rather than Gemini.
- [x] Preserve an explicit uploaded-price/non-live-quote degraded mode until a
      licensed market-data provider is configured.
- [x] Replace the Research path field with repeatable single-file browser
      upload; support Unicode filenames, persistent all/single-source scope,
      and indexed-source deletion.
- [x] Make Auto privacy-first/local, use explicit Gemini selection as external-
      AI consent, keep the evidence cutoff as an optional advanced control, and
      combine report generation/opening in one module.
- [x] Keep the current answer visible when the next-run model selection changes;
      return only complete directly supported local passages and prevent report
      generation when Evidence validation does not pass.
- [x] Show the allocation guide's internal calculation method, input-dependent
      adjustments, SEC/FINRA/World Gold Council references, cash-goal scope,
      and Alternatives examples before the user saves policy targets.
- [x] Remove Cash from the 100% investment allocation and migrate saved targets;
      calculate emergency, education, and selected one-time cash goals separately.
- [x] Retain the fractional-share constraint because it changes executable
      share math; explain whole-share rounding and that Argus never submits orders.
- [x] Add official asset descriptions and detail links beside deterministic
      rebalance and DCA suggestions.
- [x] Add explicit DeepSeek V4 Flash and Kimi K2.6 research providers with
      provider-specific pricing, retry/timeout, local-evidence-first guards,
      and environment-only API-key configuration.
- [x] Remove the duplicate Auto/Local UI choice and hide cloud-token/cost
      presentation for local-only research runs.
- [x] Block source-backed Ask when the document index is empty and distinguish a
      selected cloud provider from a cloud call skipped by the evidence guard.
- [x] Make emergency and education cash goals optional/conditional; add a named
      known cash need with amount and months until needed.
- [x] Replace the misleading retirement cash-runway input with a separate real-dollar
      accumulation/withdrawal projection through age 100; expose return assumptions,
      reliable-income input, and tax/health-care/sequence-risk limitations.
- [x] Format valid money inputs with real-time thousands separators inside the field;
      parse the comma-formatted value safely and remove scientific-notation UI.
- [x] Compare cash-goal saving with net income minus total spending and planned
      investing; show a monthly shortfall and deterministic adjustment order.
- [x] Expand Saved Profile into investor context, cash flow, cash goals, and
      investment policy; make product names themselves official-source links.
- [x] Move Saved Profile into a sticky right-hand review panel and remove the
      completed V1 Targets sidebar from non-Research pages.
- [x] Keep future investment horizon separate from years of investing experience;
      use experience only for implementation-complexity guidance.
- [x] Show per-model input/output tokens and estimated cost in Runs with one
      explicit pricing formula.
- [x] Replace long cash-plan, DCA, and risk prose with compact metrics/tables and
      expandable methodology details.
- [x] Replace the single free-text near-term need with selectable, repeatable
      short-term cash-goal types, optional estimates/deadlines, and priorities.
- [x] Keep short-term one-time goals in current savings/investment-capacity checks
      and separate them from the retirement planning horizon.
- [x] Distinguish Kimi zero balance, provider overload, and account rate limits;
      never show Gemini quota-reset guidance for a Kimi failure.
- [x] Remove the redundant Portfolio Summary refresh control; refresh automatically
      on load, holdings import, Profile save, and Profile clear.
- [x] Use one shared model timeout/retry policy for Gemini, DeepSeek, and Kimi
      while retaining provider-specific model names, keys, URLs, and prices.
- [x] Give grounded market search a longer one-attempt policy so a slow or already
      billable search is not automatically replayed; require a completed search plus
      structured direct source URLs from Kimi.
- [x] Distinguish an external model's evidence-based refusal from a locally skipped
      provider call and display only provider-billed tokens in the API cost formula.
- [x] Require structured Gemini/Kimi cited-web answers and safely render headings,
      bullets, paragraphs, and older one-paragraph results.
- [x] Split Source Ask usage from deterministic HTML-report usage; report generation
      records zero additional provider tokens/model cost.
- [x] Surface provider-specific balance, daily quota, short-window rate-limit,
      overload, authentication, and ambiguous 429 failures without model fallback.
- [x] Persist a Profile's base Investment Style AND optional compiled expert method;
      accept Markdown, TXT, Word DOC/DOCX, text PDF, or research CSV without treating
      methodology as evidence or executable instructions.
- [x] Run two bounded Portfolio market-search facets, exclude first-round domains
      from the second Exa call, prefer two accepted domains, and visibly degrade
      instead of blocking synthesis when only one passes.
- [x] Add all eleven GICS sector SPDRs plus State Street industry ETFs and SOXX as
      research-only satellite candidates; exclude them from automatic core gap filling
      and require a user-capped budget plus validated suitability before optional DCA.
- [x] Add known-good in-page Report Generation examples for both structured CSV and
      Markdown text evidence.

Phase 7 exit criteria:

- User selects a holdings CSV or Excel file in the browser and sees summary.
- Scenarios update when risk profile changes.
- Recommendation amounts are reproducible from holdings, target allocation,
  drift threshold, and share constraints.
- Tests cover portfolio math with known fixture.

### Next Portfolio Milestone: Market-Aware Candidate Layer

Status: first sourced market-context slice implemented; temporal catalog,
quote adapters, and deterministic ranking remain planned.

- [ ] Add temporal ETF instrument, metadata, quote, bar, holdings, metric, and
      source-lineage tables.
- [ ] Add provider interfaces for reference data, quotes, fund metadata,
      holdings disclosures, and daily bars.
- [ ] Implement one cost-controlled delayed/free quote adapter with explicit
      feed and freshness labels.
- [ ] Reconcile stable identifiers through SEC fund data and OpenFIGI v3;
      quarantine ambiguous mappings and ticker changes.
- [ ] Add versioned ETF eligibility rules, peer groups, scoring, and exclusion
      reasons.
- [ ] Add holdings-overlap and correlation-aware shortlist deduplication.
- [ ] Keep broad ETFs as core gap candidates; route individual stocks through
      separate fundamental research and satellite position limits.
- [x] Add a separately labeled `AI market analysis` that sends only symbols,
      asset classes, weights, and holdings date to an independent Exa search,
      then lets the selected Gemini, DeepSeek, or Kimi model synthesize only
      Evidence-Gate-accepted direct-URL excerpts.
- [x] Split Exa request cost from answer-model token cost and validate returned
      Argus citation IDs without silent model fallback.
- [ ] Reject model output that adds a ticker, changes a deterministic number,
      lacks a current-market timestamp/citation, or omits risk/counter-evidence.
- [ ] Add stale-data, provider timeout/`429`, partial-batch, identifier conflict,
      numeric integrity, and snapshot-degraded-mode tests.
- [ ] Record market-data licensing, monthly provider cost, and redistribution
      limits before enabling a paid or full-SIP feed.

Detailed design:
`docs/ETF_MARKET_DATA_ARCHITECTURE.md`.

Planned milestone exit criteria:

- Candidate facts retain provider and temporal lineage.
- Ranking is deterministic and reproducible from a dated snapshot.
- Stale or partial data cannot silently produce a current trade estimate.
- Gemini cannot add candidates or alter deterministic numbers.
- The UI separates rule-based output from AI market analysis.

## Phase 8: Frontend

- [x] Create React + TypeScript app.
- [x] Add API client.
- [x] Build Research page:
  - [x] local file path ingestion
  - [x] document upload
  - [x] chat query
  - [x] report generation
  - [x] no-evidence report guard
  - [x] current-source question context
  - [x] basic source display
  - [x] citations panel
  - [x] critic panel
  - [x] separate report builder using current Trace ID
  - [x] hide report builder for no-evidence answers
- [x] Build Portfolio page:
  - [x] CSV/XLSX/XLS file picker and holdings upload
  - [x] positions table
  - [x] asset allocation chart
  - [x] dated snapshot summary
  - [x] buy/sell amount and estimated-shares table
  - [x] missing-exposure ETF candidates with issuer sources
  - [x] recurring-investment plan
- [x] Build Profile page:
  - [x] risk tolerance
  - [x] life stage
  - [x] investment horizon
  - [x] investing experience
  - [x] target allocation
  - [x] monthly contribution
  - [x] drift threshold and whole/fractional-share preference
- [x] Build Runs and Cost page:
  - [x] trace the explicit local/Gemini/DeepSeek/Kimi model choice.
  - [x] aggregate input/output tokens and estimated API cost by model.
  - [x] recent runs
  - [x] token totals
  - [x] cost totals
  - [x] label cost as paid-tier equivalent and explain that actual billing is
        not returned per request
  - [x] model breakdown
  - [x] model-selection rationale
  - [x] eval summary
  - [x] tool call trace

Exit criteria:

- User can complete V1 demo through the UI.
- Frontend handles loading and error states.
- Screenshots can be used in README.

## Phase 9: Evaluation

- [x] Create 10+ golden cases.
- [x] Implement eval runner.
- [x] Measure citation coverage.
- [x] Measure temporal consistency.
- [x] Measure critic flag/downgrade count.
- [x] Measure token and cost per report.
- [x] Measure model-call latency.
- [x] Compare quality/cost between model profiles or mocks.
- [x] Flag regressions in citation, temporal, latency, and cost metrics.
- [x] Save eval output as JSON/Markdown.

Exit criteria:

- `argus eval` or equivalent command produces a metrics report.
- README reports honest measured quality, latency, and cost results.

## Phase 10: Resume Demo Polish

- [x] Add demo fixture documents.
- [x] Add sample holdings CSV.
- [x] Add one sample generated report.
- [x] Add data-backed portfolio allocation/concentration charts.
- [x] Add market/company/asset chart fixtures only when numeric source data exists.
- [x] Render report data-analysis charts from cited numeric evidence.
- [x] Support research CSV ingestion for structured report datasets.
- [x] Render CSV-backed trend and time-series bar charts in HTML reports.
- [x] Summarize CSV evidence into readable answers and report claims.
- [x] Make CSV report answers query-focused instead of fixed-column summaries.
- [x] Filter CSV report charts to question-relevant metrics.
- [x] Clean generated report titles from question-derived topics.
- [x] Add data-interpretation narrative text for report charts.
- [x] Add README demo previews.
- [x] Add demo commands.
- [x] Add limitations section.
- [x] Draft final resume bullets using only implemented features.

Exit criteria:

- Clean checkout can run demo locally.
- Project is ready to discuss in interviews.

## Post-V1 / V2 Roadmap

The detailed plan lives in `docs/V2_ROADMAP.md`. These tasks are intentionally
post-V1 so the local demo can finish first.

## 2026-07-20 portfolio reliability and input safety

- [x] Distinguish exact-ticker holdings, current ETF recommendations, and the combined
      state with separate colors and an explicit legend.
- [x] Replace the over-literal Portfolio market Evidence Gate query with deterministic
      market evidence slots while preserving complete-passage and URL validation.
- [x] Normalize bounded provider citation syntax and repair only directly supported
      sentences without switching the selected model.
- [x] Emit the validated ETF watchlist contract before capped prose to prevent output-limit
      truncation.
- [x] Remove emergency-reserve amount and deadline defaults and validate both only when
      the goal is enabled.
- [x] Permit blank current/retirement tax rates, calculate a labeled tax-excluded baseline,
      and avoid a misleading state-only personal marginal-rate lookup.
- [x] Move ETF eligibility and fixed ranking ahead of model explanation with versioned
      Profile/holdings, market-signal, evidence-quality, and penalty components.
- [x] Add a deterministic structured Auditor plus Runs visibility for scores, exclusions,
      timestamps, engine/version, and audit status.
- [x] Add an explicit `ARGUS_ETF_SELECTION_ENGINE=model` legacy rollback/A-B switch without
      silent request-level fallback or removal of the existing safety validators.

- [ ] Monarch screenshot OCR import.
- [ ] PDF export.
- [x] Manual model override UI and backend enforcement.
- [x] Tool timeout/retry hardening.
- [x] PostgreSQL/pgvector retrieval hardening.
- [ ] Gmail connector.
- [x] Define provider-neutral PortfolioSource/MarketDataSource protocols, a strict
      read-only Robinhood MCP client boundary, explicit source switches, and a Heatmap
      data contract with uploaded-price `Not live` fallback.
- [x] Implement the user-authorized local Robinhood OAuth/MCP Sidecar with macOS
      Keychain token storage, metadata-only `list_tools`, an exact manifest gate, and
      typed positions/quotes routes.
- [x] Store file and Robinhood holdings as source-aware snapshots; prefer Robinhood for
      overlapping tickers while preserving unrelated file-only assets.
- [x] Reject partial Robinhood responses before storage and retain the last complete snapshot.
- [x] Add a manual read-only refresh UI and explicit source labels.
- [ ] Complete the user's Argus-Sidecar-specific OAuth authorization and capture the
      real Schema manifest; Codex's MCP authorization is intentionally not reusable.
- [x] Review the live `get_equity_historicals` Schema, gate it separately, normalize completed
      daily volume, and calculate a cached robust log-MAD Volume activity metric locally.
- [x] Add a reversible fixed-size industry HeatmapMatrix with separate price, volume-activity,
      holdings, and recommendation visual channels plus formula-level detail.
- [x] Verify the integration with `268 passed`, Ruff, TypeScript/Vite build, Docker rebuild,
      and PostgreSQL migration `20260721_0021`.
- [ ] Implement Twelve Data, Alpha Vantage, and Massive REST adapters behind the same
      interface, including licensed-use review, rate limits, TTL, and freshness tests.
- [x] Bounded AWS/EKS deployment, product-flow acceptance, and full teardown.
- [ ] Azure deployment.
- [x] Redis cache and background job foundation.
- [x] Kafka versioned event bus and local/AWS producer foundation.
- [x] Complete the bounded `agent.run.completed.v1` local Kafka loop with an
      Audit/Metrics Consumer, manual offset commit, stable-ID deduplication,
      bounded retry, sanitized DLQ records, heartbeat, retention bounds, Runs
      visibility, and a real Docker Kafka acceptance script.
- [x] Kubernetes manifests for backend/frontend deployment.
- [x] Kubernetes worker deployment and eval CronJob.
- [ ] Plaid Investments Sandbox integration for user-authorized, read-only
  accounts and holdings synchronization.
- [ ] Plaid Link UI, backend token exchange, encrypted token storage, and
  disconnect/delete-token flow.
- [ ] Holdings normalization, import preview, validation, idempotent refresh,
  as-of metadata, and partial-data handling.
- [ ] Plaid contract tests and `portfolio.sync.*` events with sensitive fields
  excluded from event payloads.
- [x] Define a declarative Style Pack schema and trusted built-in strategic,
  value, quality-growth, income-quality, and macro/risk-balanced packs.
- [x] Add data-only JSON Style Pack upload, strict schema/security validation,
      listing, selection, persistence, and custom-pack deletion without arbitrary
      code execution.
- [x] Extend Style Packs into backward-compatible Method Packs with safe JSON or
      fenced Markdown upload and up to eight validated
      `required_evidence_slots`; keep Argus router/query budgets authoritative.
- [ ] Add immutable Style Pack versions/content hashes, upload diff preview,
  momentum/contrarian packs, and a per-style evaluation dashboard.
- [ ] Add primary/secondary report-style selection, weighted methodology fusion,
  conflict disclosure, and pre-generation token/cost estimates.
- [ ] Persist skill versions in run traces and evaluate per-skill citation
  coverage, unsupported claims, latency, and cost.
- [x] OpenTelemetry instrumentation and collector/Prometheus export foundation.
- [x] Cloud object storage adapter and raw-upload archival.
- [ ] Optional vLLM or Truss self-hosted model endpoint.
- [ ] MCP integration.
- [x] PostgreSQL full-text + exact + eligible pgvector Hybrid Retrieval with RRF.
- [ ] Benchmark BM25 or a learned/cross-encoder reranker against the RRF baseline;
      add it only if measured relevance gain justifies latency and cost.
- [ ] Add a provider-independent local multilingual embedding model and compare
      Recall@k/MRR with Gemini embeddings before enabling it by default.
- [ ] Add automated Evidence Ledger retention/TTL and user-facing test-run cleanup.
- [ ] Add selected-provider LLM planning or multi-round paid web Agent Search only
      after local bounded gap search passes labeled quality/cost gates.
- [ ] Payment integration through hosted checkout.
- [ ] PCI scope review for any future payment-card handling.
