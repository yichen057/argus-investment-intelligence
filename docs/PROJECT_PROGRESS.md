# Argus Project Progress

This file tracks implemented features, review notes, interview angles, and
remaining gaps. Keep resume claims tied to what is actually implemented here.

Detailed interview questions and answers are maintained in
`docs/INTERVIEW_QA.md`.

## 2026-07-22 — Kafka audit/metrics closed loop

- Preserved the pre-Kafka Robinhood/Market Data/Heatmap/Profile/Portfolio checkpoint in commit
  `108bc69` before expanding infrastructure behavior.
- Completed one bounded business path: `agent.run.completed.v1` → Kafka → Audit/Metrics
  Consumer → sanitized PostgreSQL projection → Runs Management.
- Added stable-event-ID deduplication, three-attempt bounded retry, manual offset commit only after
  processing or DLQ isolation, consumer heartbeat, contract validation, hashed invalid-message
  records, and separate DLQ topic delivery.
- Runs now acts as a lightweight read-only operations view for processed, duplicate, and DLQ
  counts plus the latest ten sanitized event summaries. Raw prompts, documents, web pages,
  holdings, account data, model responses, and API keys are not stored in this projection.
- Bounded local Kafka log retention to seven days and the audit projection to 5,000 records / 30
  days by default. PostgreSQL Runs and the API Usage Ledger retain their separate semantics.
- Real Docker acceptance passed against Apache Kafka: the event topic and DLQ topic existed,
  duplicate replay was ignored, invalid input reached DLQ, the consumer heartbeat was `running`,
  and consumer-group lag was zero. No external model or paid API was called.
- Final local regression: `284 passed`; Ruff, TypeScript/Vite production build, Compose config,
  and `git diff --check` all passed.

## 2026-07-21 — Robinhood read-only Sidecar and source-aware snapshots

- Completed an authenticated metadata-only capability refresh against the official Robinhood
  Streamable HTTP MCP endpoint. It advertised 50 tools; no positions, balances, quotes, orders,
  or other business data were read.
- Added a local OAuth Sidecar based on the stable MCP Python SDK v1.x. OAuth material stays in
  macOS Keychain; `.env` contains only a local Sidecar bearer token and reviewed Schema-manifest
  fingerprint.
- Enforced a two-tool phase-one allowlist: `get_equity_positions` and `get_equity_quotes`.
  Every order, watchlist, options, scan, account, tax-lot, transaction, and unknown capability is
  unreachable from the Argus business layer. OHLCV is still fail-closed.
- Added source-aware portfolio snapshots. Refreshing Robinhood replaces only the Investments
  scope, Robinhood wins for overlapping tickers, and file-only assets remain available.
- Added partial-response protection, classified provider errors, manual refresh UI, source chips,
  sanitized capability audit metadata, and a Keychain disconnect command.
- Verification: full backend suite `268 passed`; Ruff and the TypeScript/Vite production build
  passed; Docker rebuilt cleanly; PostgreSQL migration reached `20260721_0021 (head)`; container
  health returned the explicit external-data, Robinhood, Sidecar, and provider states. Live
  position/quote acceptance remains pending the user's separate Sidecar OAuth and Schema approval.

## 2026-07-21 — Provider-neutral holdings, quotes, and Heatmap contract

- Added `PortfolioSource` with the default `FileUploadSource` and an injectable,
  strict read-only `RobinhoodMcpSource`. Robinhood write/trade tools are not allowlisted.
- Added `MarketDataSource`, stable provider codes 01–04, normalized quote batches, and
  the first Robinhood read-only quote adapter. Twelve Data, Alpha Vantage, and Massive
  have reserved switch values but no transport yet.
- Added independent `ARGUS_ENABLE_EXTERNAL_MARKET_DATA` and Robinhood switches. External
  data remains off by default; failures never switch to another paid source silently.
- Added `/portfolio/market-map` and a UI source-status strip. Upload prices remain usable
  but are explicitly `Not live`; missing daily change/volume/Z-score stays null.
- Added `/portfolio/sync-robinhood`, which currently requires an authenticated MCP client
  supplied by the host. The repository does not yet implement authorization transport.

## 2026-07-20 — Local Maintenance Runbook

- Added `docs/LOCAL_RUNBOOK.md` as the bilingual maintenance reference for local Docker
  Compose operation.
- Documented when browser refresh/hot reload is sufficient versus when `.env` changes
  require `docker compose up -d --force-recreate backend`.
- Added the deterministic/model ETF engine switch, verification, rollback, rebuild,
  logging, stale-browser, historical-Run, and secret-handling guidance.
- Linked the runbook from the README beside the `.env` setup instructions.

## 2026-07-20 — Deterministic ETF Ranking, Explicit Rollback, and Independent Audit

- Moved sector/industry ETF symbol selection out of Gemini, DeepSeek, and Kimi. The
  versioned Phase A pipeline now applies hard eligibility, Profile/holdings fit,
  timestamped market-signal score, evidence-quality score, and explicit overlap,
  concentration, expense-ratio, and liquidity penalties before a fixed score/ticker sort.
- Requires ticker/name-specific accepted evidence when multiple issuers share the same
  exposure. Missing current fee or liquidity facts receive visible `missing_*` penalties;
  Argus does not fill them from model memory or undated constants.
- The selected model now explains a closed, ordered list. Missing, extra, reordered, or
  safety-conflicting model candidate JSON cannot change the fixed selection and falls back
  to deterministic explanations.
- Added `ARGUS_ETF_SELECTION_ENGINE=deterministic|model`. The default is deterministic;
  `model` is an explicit restart-scoped legacy rollback/A-B path with no deterministic
  score threshold. It still enforces the controlled universe, citations, three-candidate
  bound, holdings mode, and non-additive DCA safety. There is no silent per-request switch.
- Added a separately versioned pure-code Auditor over bounded structured inputs. It checks
  count, uniqueness, rank continuity, stable order, score threshold, decision/outcome
  consistency, citation allowlist, universe membership, holdings mode, and DCA invariants
  before the model call.
- Expanded Runs/API/UI trace schema to show engine/version, auditor status, fixed rank,
  component scores, penalties, market-signal timestamp, eligibility, and rejection codes.
  Existing retention/privacy limits remain unchanged.
- Verification: full backend suite `243 passed`; Ruff, TypeScript/Vite build, Docker Compose
  config validation, and Git whitespace checks passed.

## 2026-07-20 — Multi-issuer ETF Peers and Mixed Retirement Tax Treatment

- Expanded the controlled ETF research universe from 30 to 41 funds by adding a Vanguard
  peer for every State Street broad-sector ETF. Live redirect checks verified the 11 State
  Street broad-sector, 11 Vanguard, and SOXX first-party profiles. The 18 State Street
  industry shortcuts resolved only to the issuer home page, so Argus now uses the verified
  official ETF directory fallback and tells the user which ticker to search.
- Added a bounded second-search peer-comparison scope. When controlled funds share an
  exposure, the selected model is instructed to compare only accepted, same-window evidence
  and weigh return period/as-of date, expense ratio, liquidity/assets, benchmark breadth, and
  holdings overlap. Argus still does not claim full-market coverage or a guaranteed winner.
- Added deterministic direct-stock sector/industry annotations. The UI distinguishes exact
  ETF ownership, related-stock exposure, new-exposure candidates, replacement candidates,
  and existing-holding reviews; expandable stock symbols make overlap visible without
  falsely claiming that the ETF is held.
- Added a typed holdings-fit gate to model output. A related-stock ETF candidate must be a
  non-additive `diversifying_replacement`, while an exact-held ETF must be an
  `existing_holding_review`; both disable automatic DCA. Conflicting model output is rejected.
- Replaced ambiguous `1 / 3` watchlist text with `N evidence-backed candidates · max 3` and explains that
  unused slots mean another candidate did not pass, not that Exa is limited to one fund.
- Added a Mixed Traditional + Roth retirement-account option with an explicit estimated
  pre-tax withdrawal share. Retirement withdrawal gross-up applies tax only to that share;
  current take-home contribution cost remains unestimated without a contribution split.
- Added migration `20260720_0018` and a prominent Portfolio `Tax not included · 未计税基线`
  banner whenever relevant retirement tax assumptions are blank.
- Verification: full backend suite `235 passed`; Ruff and TypeScript/Vite build passed;
  Docker migration reached `20260720_0018`; local browser checks confirmed 41 fund cards,
  verified direct-profile/directory-fallback labels, XSD's official Fund Finder fallback,
  related-stock expansion, mixed-account input, and the tax banner.

## 2026-07-20 — Portfolio Evidence Admission, ETF State Marking, and Optional Tax Baseline

- Replaced the generic Portfolio market-evidence phrase check with deterministic
  market slots for rates, inflation, earnings/valuation, sector demand/leadership,
  liquidity/credit, and counter-evidence while retaining the shared complete-passage gate.
- Normalized common provider citation forms and added conservative local citation repair
  only when an accepted Exa passage has direct lexical support; unmatched claims still
  fail closed and Argus never changes the selected model.
- Moved the bounded ETF watchlist JSON contract before prose and capped prose length so
  the structured recommendation is not lost at the provider output limit.
- Added distinct candidate-library states for exact-ticker holdings, current validated
  recommendations, and held-plus-recommended funds. No broad-fund constituent look-through
  is inferred; the later controlled direct-stock mapping is separately labeled.
- Removed emergency-reserve form defaults; enabling the goal now requires an explicit
  amount and deadline instead of silently inserting `$36,000` and 12 months.
- Made current and retirement marginal tax rates optional. Missing retirement tax yields
  a visible tax-excluded retirement baseline; state alone is deliberately not used to
  invent a personal marginal rate.
- Verification: full backend suite `231 passed`; Ruff and TypeScript/Vite build passed.
  A live
  Exa + DeepSeek browser run returned 10 unique domains, admitted 8 independent domains,
  and generated a complete cited market analysis with one selected-model call.

## 2026-07-18 — FINRA-style Retirement Inputs and Budget-independent ETF Shortlist

- Expanded Profile with FINRA-style retirement inputs: accumulated retirement savings,
  after-tax spending, other income tax treatment, inflation, tax rates, return after
  investment expenses, primary account type, and inflation-adjusted deposits.
- Replaced hidden fixed real-return assumptions with an inspectable nominal, inflation,
  tax, accumulation, and withdrawal formula. The Portfolio page substitutes the user's
  numbers step by step and states the modeled zero ending balance.
- Kept short-term cash goals separate and added a plain-language explanation that the
  section answers whether entered cash covers known 1–120 month bills.
- Fixed FastAPI/Pydantic validation rendering so Profile errors identify the field and
  rule instead of displaying `[object Object]`.
- Made ETF shortlist eligibility independent of the optional dollar budget. Validated
  candidates can appear in Rebalance, Diversification, and DCA research with a zero
  dollar amount until the user chooses a budget.
- Added migration `20260718_0017` and regression coverage for exact zero-return retirement
  math, tax-aware persistence, and budget-free ETF watchlist output.
- Verification: `226 passed`; Ruff and the TypeScript/Vite production build passed.

## 2026-07-18 — Expert Method Panel, ETF Satellite Budget, and Retirement Back-solving

- Replaced the single expert add-on selection with a bounded panel of up to five
  compiled method documents. The panel remains methodology—not evidence—and is resolved
  by one orchestrator through accepted evidence rather than an unbounded agent debate.
- Added a direct emergency-reserve amount and deadline while retaining compatibility
  with existing months-of-expenses profiles.
- Expanded the controlled ETF research universe from 12 to 30 candidates: all eleven
  GICS broad-sector funds, all eighteen funds in State Street's current industry lineup,
  and SOXX as a second
  semiconductor comparison. The UI separates the candidate pool from the maximum three
  evidence-backed configuration candidates.
- Added validated structured market-watchlist output with controlled symbols, citation
  IDs, counter-evidence, invalidation signals, overlap risk, and DCA guidance.
- Split Exa retrieval metrics from Argus Evidence Gate acceptance metrics so a one-domain
  warning can no longer be mistaken for an Exa one-site search limit.
- Replaced the zero-heavy cash-goal table with funded/partially-funded/not-funded status,
  progress, assigned current cash, remaining gap, and explicit monthly saving amounts.
- Added a separate retirement funding model: desired spending minus reliable income,
  finite withdrawal present value through age 100, projection of current invested assets,
  and a required-monthly-investment back-solve in real dollars.
- Added an explicit sector/industry satellite budget within total monthly investment.
  The selected model may mark a validated candidate DCA-suitable, while deterministic code
  assigns the user-capped amount and keeps it separate from core target DCA.
- Added purple recommendation highlighting across Rebalance, missing exposure, and the
  controlled 30-fund library; the unhighlighted library remains research-only.
- Changed whole-share residual rows from ambiguous `REVIEW` to `ROUNDING` in the UI and
  explains why the largest holding receives the actual sell amount first.
- Added migration `20260718_0016`, API fields, UI layout fixes, and regression tests.

Verification:

- Full backend suite: `224 passed`.
- Ruff passed.
- TypeScript/Vite production build passed.
- Docker Compose services are running, PostgreSQL is healthy, migration
  `20260718_0016` is at `head`, and `/health` returns `ok`.
- Browser acceptance confirmed the five-method panel controls, per-document deletion,
  collapsed base-style explanation, retirement back-solve, and QQQ `SELL` versus TSLA
  `ROUNDING` presentation. No paid search or model call was used for this acceptance.

## Timeline

- AWS free access deadline shown by user: 2026-07-29.
- Current planning date: 2026-07-12.
- Practical window: about 17 calendar days.

Priority order:

```text
local runnable V1
-> evidence/RAG core
-> agent/report/portfolio loop
-> eval and cost dashboard
-> minimal cloud deployment polish
```

Cloud deployment should not block the local V1 demo. Kubernetes, Grafana, and
cloud GPU serving remain optional polish unless the local product loop is done.

## Reporting Contract

After each completed feature, record:

- completed functionality;
- technology stack used;
- likely interview questions;
- foundational concepts to review;
- verification results;
- known gaps or follow-up tasks.

## Approved Design / Partially Implemented

### D001: ETF Candidate and Market Data Architecture

Status: sourced market context plus Phase A deterministic evidence-backed ranking are
implemented. Do not claim a complete real-time ETF database, licensed live quotes, or
typed temporal fund-metadata ranking.

Decision:

- Keep gap detection, candidate eligibility/ranking, target amounts, shares,
  projected weights, and limitations deterministic.
- Store stable fund identity plus time-versioned metadata, holdings, quotes,
  bars, derived metrics, and source lineage in PostgreSQL.
- Treat quotes as live/delayed/end-of-day according to the licensed feed;
  retain separate freshness schedules for expense ratio, AUM, holdings, and
  macro facts.
- Use SEC fund/filing data for regulatory identity and holdings disclosures,
  OpenFIGI v3 for identifier mapping, a replaceable quote provider for market
  snapshots, and licensed or curated official sources for fund metadata.
- Rank a small peer-group shortlist by portfolio-role fit, diversification,
  liquidity, cost, history/tracking, and data completeness; deduplicate
  near-identical funds.
- Keep individual stocks out of automatic core gap filling; route them through
  separate cited fundamental research and satellite position limits.
- Let the selected answer model explain only an allowed, structured shortlist. Validate candidate
  IDs, numbers, citations, timestamps, risks, and counter-evidence before
  display.
- Deliver a cost-controlled curated universe and on-demand delayed/free quotes
  before considering paid consolidated real-time coverage.

Architecture, schemas, refresh policy, provider interfaces, scoring proposal,
failure handling, phased cost plan, tests, and exit criteria:
`docs/ETF_MARKET_DATA_ARCHITECTURE.md`.

## Completed Feature Log

### F065: Profile Input Clarity and Diversity-Aware Market Synthesis

Status: implemented and verified locally on 2026-07-18.

Completed functionality:

- Removes the default Moderate risk choice; Profile now requires an explicit selection.
- Replaces scientific notation with real-time comma-grouped money fields, aligns all
  one-time-goal inputs, and gives disabled education fields one consistent appearance.
- Combines the emergency-fund toggle, coverage months, completion deadline, formula,
  and calculated dollar target in one labeled module.
- Shows the base Investment Style `+` optional Expert Method relationship explicitly;
  the backend continues to compile both into one bounded method context.
- Exposes the Primary financial/life priority in Portfolio cash-plan trade-offs rather
  than leaving it as an unexplained Profile input.
- Uses Exa `excludeDomains` for the second market facet and increases the bounded result
  request from five to eight. Two accepted domains remain the preferred quality target;
  one domain now produces a visible limitation instead of blocking every answer model.
- Adds a source-backed sector opportunity watchlist contract and the SOXX semiconductor
  industry candidate. Candidates remain research-only and cannot create orders.
- Adds both CSV and Markdown known-good Report Generation examples and documents that
  complete text passages—not file type—determine report eligibility.
- Removes an import-order-dependent retrieval cycle by lazily loading repository-heavy
  retrieval adapters, so focused market-analysis tests run independently.

Verification:

- Targeted market-analysis citation suite: `10 passed` after the bounded repair test.
- Full backend suite: `217 passed`.
- Ruff passed.
- TypeScript/Vite production build passed.
- Docker Compose rebuilt successfully with PostgreSQL healthy and both app services running.
- One bounded live Portfolio acceptance used two Exa calls plus the explicitly selected
  DeepSeek call, accepted Citi and State Street across two independent domains, and cost
  an estimated `$0.0146237` (`$0.014` search + `$0.0006237` synthesis).
- Kimi crossed the same Exa/Gate path but remained nondeterministic on the strict citation
  contract: standard and safe combined citation forms are normalized, and one bounded
  same-model citation rewrite is permitted with disclosed call count and combined cost.
  A second invalid response is deliberately rejected instead of being displayed.
- Final live Kimi acceptance succeeded with two Exa searches and two disclosed Kimi calls
  (initial draft + citation repair), two domains, a complete under-900-word response, and
  `$0.0235357` estimated total cost (`$0.014` Exa + `$0.0095357` Kimi).

### F064: Profile Method Documents, Diverse Market Evidence, and Sector Research Library

Status: implemented and verified locally on 2026-07-18.

Completed functionality:

- Replaces the confusing Profile declarative-pack uploader with the same safe expert-
  document compiler used by Research; accepts Markdown, TXT, Word DOC/DOCX, text PDF,
  or research CSV and fixes the React click-event-as-file upload bug.
- Persists a Profile's base Investment Style AND optional expert method document. The
  pair seeds Research and Portfolio explanation while preserving the boundary between
  deterministic allocation policy, non-executable methodology, and factual evidence.
- Groups the Profile editor into six numbered sections; formats money inputs with
  thousands separators; clarifies emergency reserve size versus savings
  deadline; and visibly disables both education amount and year for no education goal.
- Makes Portfolio market context run two capped Exa facets and prefer at least two
  accepted source domains before synthesis; F065 later changed the hard block into a
  visible limited-source degradation path.
- Adds an official-source, research-only library for all eleven GICS Select Sector SPDR
  ETFs; sector candidates are excluded from automatic core gap filling and DCA.
- Adds an in-page, known-good Report Generation walkthrough using the repository's
  structured gold macro CSV and exact regression-tested question.

Verification:

- Targeted backend suite: `58 passed`; full backend suite: `211 passed`.
- Ruff passed.
- TypeScript/Vite production build passed.

### F063: Portfolio Exa Search and Answer-Model Separation

Status: implemented and verified locally on 2026-07-17.

Completed functionality:

- Replaces Portfolio's provider-native Gemini/Kimi search paths with the same
  independent boundary used by Research: Exa retrieval, deterministic Evidence
  Gate, then exactly one manually selected synthesis model.
- Adds DeepSeek to Portfolio AI market analysis alongside Gemini and Kimi; none of
  the three answer adapters may invoke built-in web search or silently fall back.
- Sends Exa and the answer model only a bounded portfolio view: up to 12 symbols,
  asset classes, weights, and holdings date, excluding account names and dollars.
- Rejects insufficient excerpts before the model call and rejects output with
  missing or invented `[source:Wn]` IDs after the model call.
- Reports search provider/call count, Exa request cost, model-token cost, total
  estimated cost, direct URLs, and retrieval timestamps separately in the API/UI.
- Makes the existing concentration rules visible in the main panel: every single
  non-cash holding is screened at `>=25%`, while every aggregated asset class is
  screened separately at `>=70%`; neither is the Profile drift threshold.

Verification:

- Ruff passed.
- Backend suite: `209 passed` (obsolete provider-native search tests were removed
  with the retired Gemini/Kimi built-in-search adapters).
- TypeScript/Vite production build passed.
- Docker Compose rebuilt successfully and all three local services are running.
- One live Exa + DeepSeek Portfolio request succeeded with one Exa call, one
  direct-URL source, validated `W1` citation, 1,009 input tokens, 823 output
  tokens, `$0.007` search estimate, `$0.0003717` model estimate, and
  `$0.0073717` total estimate. No other answer model was called.
- The first live attempt exposed an over-constrained gate: requiring one passage
  to overlap all six tickers blocked generation. Search scope and per-passage
  admission were separated, retaining the Gate rather than bypassing it.

Known gaps:

- The current Exa query is intentionally bounded and market-context oriented; a
  future typed macro/quote adapter can improve coverage without changing the
  search/model separation.
- Market commentary still cannot alter deterministic trades, and it remains
  decision support rather than personalized investment advice.

### F062: Cost-Capped Stage Model Benchmark and Per-Claim Citation Verification

Status: implemented and verified locally on 2026-07-17. The first bounded live
DeepSeek V4 Flash/Kimi K2.6 comparison completed 12 calls for an estimated
`$0.007132` under a `$0.03` ceiling. This result does not alter production routing.

Completed functionality:

- Splits substantive answers into atomic, run-local `C1`, `C2`, ... Claim keys and
  retains citation IDs, evidence IDs, relations, and deterministic verification.
- Checks each Claim for an accepted citation, material numeric consistency, and
  meaningful source-term overlap; weak/unsupported Claims downgrade the critic and
  block report eligibility.
- Adds a fixed, versioned three-case dataset and scores evidence extraction and
  answer synthesis separately on expected-fact recall, supported-claim rate,
  organization, latency, tokens, and estimated cost.
- Requires an explicit model list, uses no hidden fallback, caps benchmark output at
  500 tokens, and reserves conservative per-call cost before contacting a configured
  provider.
- Configures optional DeepSeek V4 Pro and GPT-5.5 benchmark candidates. A separate
  six-call V4 Pro run cost an estimated `$0.001944`; extraction averaged `0.906`, while
  synthesis averaged `0.621` and failed the stage gate. The future Kimi slot remains
  disabled until an exact official model ID and prices are known.
- First result: extraction quality tied at `0.950`; Kimi synthesis was slightly
  stronger (`0.921` vs `0.903`) but DeepSeek remained the value recommendation under
  the declared 0.03 near-tie rule. More multilingual/long/conflicting cases are needed.

### F061: Resource-Bounded Research Document Execution

Status: implemented and verified locally on 2026-07-17.

Completed functionality:

- Streams actual request bytes to a temporary file with a 25 MiB ceiling rather than
  materializing the full HTTP body in API memory.
- Enforces 500-page, 2-million-character, 90-second, admission-pressure, and
  cgroup-aware RSS controls.
- Parses one document in an isolated child process, samples RSS every 500 ms, and uses
  `SIGTERM`, a five-second grace period, then `SIGKILL` if necessary.
- Returns stable structured failure details with stage, observed value, limit,
  external-call count, cleanup result, and safe next action; failed extraction creates
  no partial document record and temporary data is removed.
- Adds Docker Compose memory limits and tests for actual-byte upload rejection,
  extracted-text limits, memory termination, timeout termination, and cleanup.
- Keeps the current boundary explicit: the HTTP request waits for the isolated child;
  asynchronous queueing, global concurrency control, exported alerts, and Kubernetes
  OOM status reconciliation remain hardening work.

### F060: Unified Research Upload Library and Overflow-safe Composition UI

Status: implemented and verified locally on 2026-07-17. TypeScript/Vite production
build passes, and the live page was checked against the existing long Chinese PDF
and expert-method filenames with no horizontal overflow.

Completed functionality:

- Aligns both Research upload actions in the card header and lets each card keep
  its natural content height, eliminating the large empty area in the Evidence card.
- Moves saved Evidence and Method add-ons into one right-side **Uploaded research
  items** library with explicit type badges and independent active-state styling.
- Keeps selection separate from storage: an inactive item does not participate in
  that part of the next Run, while confirmed trash deletion permanently removes it
  plus the historical Runs and Reports that used it.
- Removes the long compiled-checklist preview and delete controls from the Method
  composition card; long expert filenames now wrap inside both the active-method
  row and the unified library.

### F059: Base Framework AND Expert Method Add-on

Status: implemented and verified locally on 2026-07-17. Full backend regression
passes with `202 passed`; Ruff and TypeScript/Vite production build pass. Docker
backend/frontend images rebuild successfully, PostgreSQL is healthy, Alembic
`20260717_0013` is at head, and the live read-only method-document API responds.

Completed functionality:

- Replaced the ambiguous Research custom-Pack upload with an explicit composition:
  one required base Investment Method Pack plus one optional expert method add-on.
- Added Markdown, TXT, text-based PDF, and research CSV add-on upload. Scanned or
  invalid PDFs fail with an OCR/extractable-text message.
- Compiles at most twelve headings, bullets, or complete research steps; filters
  code blocks plus prompt-control, credential, and shell-like instructions. Only
  the bounded checklist, detected lenses, hashes, and warnings are stored—not raw
  method text or evidence chunks.
- Adds up to four optional known-lens retrieval hints without raising the hard
  one/two-search budget. The base pack and add-on context both reach indexed,
  web, and hybrid answer paths and are snapshotted in the Run.
- Added list/delete lifecycle APIs and UI preview so users can inspect exactly what
  was compiled before relying on the method.
- Documented each report-quality gate, its code path, threshold, failure behavior,
  and the difference between the frontend explanation and backend authority in
  `docs/REPORT_QUALITY_GATES.md`.

### F058: Explicit Research Configuration and Report Readiness

Status: implemented and verified locally on 2026-07-17: `198 passed`, Ruff, and
TypeScript/Vite production build pass; the running Docker frontend responds on
port 5173.

Completed functionality:

- Removed the Research answer-model default and the scope-change auto-selection.
  Every page session requires an explicit available model, and Argus never silently
  replaces an incompatible or failed provider.
- Reset stale answers and report state when the answer model or Method Pack changes,
  so results cannot be mistaken for output from the newly selected configuration.
- Removed the ambiguous `Advanced` drawer. The useful per-run input is now a directly
  labeled optional historical evidence cutoff; project-level API-key setup remains in
  `.env` documentation rather than the question form.
- Clarified that Profile supplies the initial Method Pack default, the Research selector
  applies to the next Ask without saving Profile, and uploaded packs auto-select after
  validation. Packs guide evidence requirements, analysis lenses, and report order but
  are never evidence.
- Added route-specific report-readiness checks for Evidence Gate approval, accepted
  sources/citations, critic status, structured claims, and substantive complete prose.
  Report generation still reuses the stored answer and does not make another model call.

### F057: Independent Exa Web Evidence and Answer-Model Separation

Status: implemented and verified locally on 2026-07-16: `198 passed`. Contract and API tests
cover success, Exa failure auditing, DeepSeek/Gemini/Kimi eligibility, the hard
two-search refusal ceiling, and zero model calls when evidence is insufficient.
Ruff, TypeScript/Vite production build, Docker rebuild/health, and Compose
validation pass. A direct Exa adapter call returned three URLs. Final real Run 60
completed Exa + DeepSeek with valid citations, all eight answer sections, one
`$0.007` search, about `$0.0004144` model cost, and a zero-additional-model-cost
HTML report. Including the diagnostic adapter call and the first citation-format
failure, the full live acceptance session estimated about `$0.02184`; provider
dashboards remain authoritative.

Completed functionality:

- Replaced Research's Gemini/Kimi provider-native web search with an independent
  Exa adapter. Exa discovers evidence; the explicitly selected Gemini, DeepSeek,
  or Kimi model only synthesizes accepted evidence.
- Normalizes direct URLs, title, author, publish/retrieval time, bounded text and
  highlights, relevance signals, content identity, request ID, and API cost into
  an Argus-owned web-evidence contract.
- Applies the same deterministic Evidence Gate used by indexed evidence. One
  initial search may be followed by exactly one named-gap search; otherwise the
  run stops and the answer model is not called.
- Records each search call separately from model calls, retains failed search
  audits, and displays search provider/calls/cost apart from answer tokens/cost.
- Requires the selected answer model to use supplied `[source:ID]` values. Missing
  or invented IDs disable HTML report generation even when prose was returned.
- Keeps portfolio market analysis on its existing adapter for now; the Research
  model capability flag is separate so enabling DeepSeek+Exa does not falsely
  advertise DeepSeek support in that older portfolio route.

Known boundary:

- The live call verifies authentication, response parsing, direct URLs, and cost
  extraction—not general finance relevance, production uptime, or retention
  rights. Those require a fixed evaluation set and operational/legal review.

### F056: Automatic Research Upload and Evidence/Provider Failure Boundaries

Status: implemented and verified locally on 2026-07-16: `185 passed`, Ruff,
TypeScript/Vite production build, Docker rebuild/health, one zero-cost indexed
acceptance, and one bounded Kimi web acceptance attempt.

Completed functionality:

- Replaced the clipped native file field plus large Upload button with one compact
  `Choose & upload` control. Selecting evidence or a Method Pack now immediately
  starts the corresponding upload; the right-side source index remains the source
  of truth for successfully searchable evidence.
- Added an explicit web-only warning when indexed files exist, because `web` ignores
  those files while `hybrid` uses both local excerpts and cited public sources.
- Detects PDFs without an extractable text layer, returns a clear scanned/image-only
  PDF and OCR message, and deletes the failed managed upload so retries do not leak
  disk space.
- Tightened the deterministic local extractor to reject weak partial overlap, page
  numbers, source labels, and short question-form PDF headings. It checks additional
  ranked results and now refuses rather than returning an incoherent but superficially
  overlapping sentence.
- Removed JSON Mode from Kimi cited-search requests, retained the provider-required
  disabled-thinking tool flow, and distinguished “search not invoked” from “search
  completed without direct URLs.” No failure silently falls back to another model.
- Persisted failed external Run/model-call token and estimated-cost audit records.
  A rejected uncited provider answer may still consume billable tokens and must not
  disappear from Runs merely because the API response is an error.

Acceptance evidence and boundary:

- Run 53 asked why gold might benefit when real yields fall. The currently indexed
  Citi PDF only supplied a weak spending/supply passage, so Argus correctly returned
  no relevant local evidence instead of appending the PDF heading “5 Why are gold
  prices where they are?”.
- The newly selected seven-page `金泰和亚…20260302.pdf` has no usable text layer and
  correctly returned the OCR-required error; it was not added to the right-side index.
- The one Kimi web acceptance returned HTTP 502 and was not retried. Kimi's current
  official documentation says its built-in web search is under upgrade and is not
  recommended in the near term. Argus therefore exposes the provider limitation and
  rejects ungrounded output instead of presenting it as researched fact.

### F055: Structured Web Answers, Provider-Specific 429s, and Cost-Split Reports

Status: implemented and verified locally on 2026-07-16: `180 passed`, Ruff,
TypeScript/Vite production build, and Docker acceptance.

Completed functionality:

- Required Gemini/Kimi cited-web answers to use stable sections for the direct
  answer, drivers, supporting evidence, risks, counter-evidence, falsification,
  implications, and next checks instead of returning one unbroken paragraph.
- Added safe frontend rendering for headings, lists, paragraphs, and older
  single-paragraph answers without rendering provider HTML.
- Reused those stored answer sections when constructing the deterministic HTML
  report, so the report organizes rather than repeatedly copies the same prose.
- Distinguished provider balance, daily quota, short-window rate limit,
  overload, authentication, and unknown 429 cases where the provider exposes
  enough information. Error copy states that Argus did not switch models.
- Relabeled report metrics as `Source Ask` usage and separately records HTML
  report generation as zero provider tokens and `$0` additional model cost.

Design decision:

- Ask owns the only provider call in the current workflow. Report generation
  reuses the saved answer and citations, so it improves presentation without a
  second, potentially surprising token bill. A future AI-expanded report must
  be a separately authorized and separately costed action.

### F054: Explicit Web Boundary, Separate Method Upload, and Report Quality Gate

Status: implemented and verified locally on 2026-07-16: `178 passed`, Ruff,
TypeScript/Vite production build, and Docker Compose service rebuild/health
acceptance.

Completed functionality:

- Moved evidence scope and answer-model selection above Ask. Web-only mode is
  now discoverable and remains usable with zero uploads; indexed and hybrid
  prerequisites are stated in place.
- Added two visually distinct Research inputs: evidence files enter the
  document/chunk index, while JSON or fenced Markdown Method Packs enter only
  the validated methodology registry.
- Documented the exact internet-call boundary. Current production web search is
  provider-native Gemini/Kimi cited search; Python can call a future independent
  search API but is not itself a searchable web index.
- Changed the local extractor to use bounded neighboring-chunk context, reject
  dangling conjunctions, and retain only the bounded answer context needed for
  later audit/report reconstruction.
- Added separate Ask/report quality bars. A short extract can remain visible,
  but HTML requires complete substantive analysis, citations, and critic
  approval; structured CSV reports remain eligible through deterministic data.
- Collapsed route, trace, cost, and structured-claim internals into an audit
  panel so the default result emphasizes the answer and citations.

### F053: Adaptive Hybrid Retrieval, Evidence Ledger, and Method Evidence Slots

Status: implemented and verified locally on 2026-07-16: `172 passed`, Ruff,
TypeScript/Vite production build, PostgreSQL migration `20260716_0012`, Docker
health/migration checks, Alembic schema-drift check, and a real indexed-PDF
acceptance run passed.

Completed functionality:

- Replaced raw lexical/vector-score merging with three independent retrieval
  channels: exact/alias matching, PostgreSQL `tsvector` full-text ranking backed
  by a GIN index, and semantic pgvector retrieval when a genuine non-local
  embedding provider is enabled.
- Added weighted Reciprocal Rank Fusion, normalized-passage deduplication,
  neighboring-chunk context, document/access/date filters, and per-result signal
  and channel-rank diagnostics.
- Replaced router-led sufficiency with one authoritative Evidence Gate. Every run
  starts with one Hybrid Retrieval; the Gate accepts direct complete support,
  names one material gap, or refuses. Fast stops after one query; Standard/Deep
  may run exactly one targeted follow-up, for a universal two-query maximum.
- Retained deterministic Fast/Standard/Deep scoring as an inspectable
  eligibility/budget layer. Evidence slots remain diagnostic research rubrics;
  Method Pack slots are bounded query hints and cannot create calls. Run metadata
  now records Gate decision, gap, accepted IDs, executed queries, hard limits,
  follow-up trigger, and stop reason.
- Made the Gate's accepted evidence IDs authoritative for model input, citations,
  answer metadata, Ledger acceptance, and report eligibility. Incomplete
  fragments and keyword-only matches are refused before an external model call.
- Added normalized Evidence Ledger query/link tables. Tool traces omit passage
  bodies, reports rehydrate canonical evidence, and the final local answer marks
  only evidence it actually used. This fixed repeated citations while avoiding
  per-run document-text duplication.
- Extended the declarative Investment Style Pack safely into a Method Pack:
  JSON or fenced `argus-method-pack` Markdown may add at most eight validated
  `required_evidence_slots`. At runtime these are methodology/query hints.
  Free-form `SKILL.md` instructions are rejected, and pack requirements cannot
  raise router budgets.
- Added a supply-chain Method Pack example and tests proving that method slots
  flow into Research without forcing an unbounded Agent Search.

Acceptance evidence:

- Evidence-Gated minimal-loop regression: `189 passed`; Ruff passed; TypeScript/Vite
  production build passed on 2026-07-16.

- The uploaded gold PDF question about downside risks in 2H 2026 ranked the
  direct page-17 passage first, produced one accepted citation, passed the local
  critic, and incurred `$0` provider cost.
- Final Docker Run 42 stored three selected Ledger links from ten bounded query
  candidates, marked only Evidence 170 accepted, and generated Report 14 by
  rehydrating the compact trace from canonical evidence rows.
- Exact rank currently uses RRF weight `3.0` after the regression case exposed
  a page-7/page-17 ordering error. This is a benchmark candidate, not a universal
  finance-search constant.

Known boundaries:

- The deterministic 16-dimensional hash adapter is not treated as real semantic
  search. Local, DeepSeek, and Kimi indexed runs currently use exact + full-text
  unless a permitted real embedding provider is configured; Argus does not
  silently call Gemini behind another provider selection.
- Agent Search is currently deterministic, local, Evidence-Gate-driven
  orchestration with at most one follow-up.
  It does not yet use an LLM planner, entity graph, reranker, or repeated paid
  web search. Provider-grounded web research remains a separate bounded call.
- Automated TTL/retention controls and a larger labeled Recall@k/MRR/citation
  evaluation set remain follow-up work.

Architecture and interview walkthrough:
`docs/RESEARCH_AND_STYLE_PACK_ARCHITECTURE.md` and
`docs/INTERVIEW_QA.md`.

### F052: Hybrid Evidence Scope and Declarative Investment Style Packs

Status: implemented and verified locally on 2026-07-15: `163 passed`, Ruff,
TypeScript/Vite build, Docker Compose config/build, PostgreSQL migration
`20260715_0011`, live five-pack API listing, and a zero-cost browser/API
regression of the Trace 32 PDF question all passed.

Completed functionality:

- Fixed Trace 32 by merging semantic retrieval with lexical document scanning,
  normalizing `2H'26`/`2026`, and reconstructing PDF sentences split across lines.
- Added explicit `indexed`, `web`, and `hybrid` research scopes. Web-only research
  can run without uploads; Gemini/Kimi direct URLs are separated from local
  excerpt-validated citations and labeled `provider_grounded`.
- Added schema-validated, data-only Investment Style Packs with five built-ins,
  bounded allocation adjustments, official methodology references, persistent
  custom JSON upload/delete, and no arbitrary code execution.
- Wired the selected style into external indexed synthesis, web research, HTML
  report order/metadata, deterministic Profile allocation guidance, and cited
  Portfolio market-analysis prompts without allowing it to change trade math.
- Added a web-report path that preserves grounding method, direct URLs, retrieval
  timestamps, Style Pack, token count, and estimated API cost.

Design and interview walkthrough:
`docs/RESEARCH_AND_STYLE_PACK_ARCHITECTURE.md`.

### F051: External Provider Acceptance and Cost-Safe Grounded Search

Status: complete.

Completed functionality:

- Diagnosed Research Trace 29 as a successful Kimi request followed by an
  evidence-sufficiency refusal, not an API or domestic-endpoint failure. Research now
  distinguishes `cloud_declined_unsupported` from a locally skipped cloud call and
  explains that provider tokens were billed.
- Separated provider-billed tokens from local retrieval-planner tokens so the displayed
  API token count and expanded cost formula use the same billable calls.
- Disabled DeepSeek V4 thinking mode for concise source synthesis, avoiding unnecessary
  reasoning tokens while retaining the uploaded-evidence guard.
- Required Kimi market analysis to execute `$web_search` and return structured analysis
  plus direct source URLs. Free-form URLs without a completed search are rejected.
- Added a 60-second grounded-search timeout with one attempt, separate from ordinary
  model retry settings, so slow web searches can finish without replaying a potentially
  billable tool call. Market prompts now prefer authoritative primary sources.

Verification:

- Real DeepSeek and Kimi Research calls both answered a minimal public evidence fixture
  with the required evidence ID. DeepSeek used 187 input/27 output tokens; Kimi used
  191 input/31 output tokens.
- Real Kimi Portfolio acceptance returned HTTP 200 with 3,709 input/1,170 output tokens,
  a 3,912-character analysis, and four direct web-source URLs after one search attempt.
- Full backend regression passed with 157 tests; Ruff and the TypeScript/Vite production
  build passed. Docker Compose loaded a 60,000 ms market timeout and one maximum attempt.
- Provider balance checks exposed no keys. DeepSeek remained available at CNY 9.99;
  Kimi showed CNY 64.82955 immediately after acceptance. Provider posting can lag, so
  the token/tool estimates remain the per-call audit record rather than a final invoice.

### F050: Retirement Horizon and Provider-Specific Portfolio UX

Status: complete.

Completed functionality:

- Replaced retirement cash-buffer months with a planning-through age that defaults
  to 100. The saved Profile shows years after planned retirement, while Portfolio no
  longer treats retirement as a short-term cash goal.
- Added migration `20260715_0010` for `retirement_planning_age` and retained legacy
  retirement-cash fields only for API/database compatibility.
- Distinguished Kimi zero balance, rate limit, and provider overload. Kimi errors no
  longer include Gemini reset instructions or claim that a rejected request cost money.
- Removed the redundant Summary refresh button because Portfolio already refreshes on
  load, holdings import, Profile save, and Profile clear.
- Gave the three rebalance scenarios distinct visual roles: neutral reference,
  contribution option, and trade option. Deterministic rationale is now split into
  policy signal, portfolio role, and expandable pre-action checks.
- Made diversification gaps multi-column, consolidated cash-plan assumptions, moved
  Profile reset to the top, and visually separated editable Profile modules from the
  saved-policy review panel. Clearing also changes the right panel to an explicit
  no-active-profile state.

Verification:

- Full backend regression passed with 154 tests; Ruff and the TypeScript/Vite
  production build passed.
- Docker Compose rebuilt successfully, PostgreSQL reached migration
  `20260715_0010 (head)`, and all three local services remained running.
- Browser acceptance confirmed the two-column Profile layout, distinct module and
  scenario colors, multi-column gap cards, consolidated cash explanation, automatic
  Summary synchronization, and zero browser warnings/errors. The saved Profile was
  not cleared and no additional portfolio payload was sent to Kimi during acceptance.
- The configured Kimi key authenticated successfully, while the official balance
  endpoint returned zero available, voucher, and cash balance; the observed 429 was
  therefore an unfunded-account rejection rather than evidence of prior usage.

### F049: Profile Review Layout, Model Cost Ledger, and Compact Decision Views

Status: complete.

Completed functionality:

- Removed the completed `V1 Targets` panel so Portfolio, Profile, and Runs use
  the full workspace width.
- Moved the complete Saved Profile into a sticky right-hand review panel beside
  the editable form.
- Added migration `20260715_0009` and an independent `investing_experience`
  field. Future investment horizon remains the risk-capacity input; experience
  only simplifies implementation and education prompts.
- Introduced a plain-language retirement cash buffer formula; F050 later replaced it
  with a planning-through age after usability review showed the formula was misleading.
- Expanded Runs model grouping with input/output tokens and made per-model
  estimated cost a first-class table using one shared pricing formula.
- Replaced verbose cash-goal, DCA, and concentration sections with metric cards,
  compact tables, status chips, and expandable assumptions.
- Added visible Portfolio copy explaining that DeepSeek is available in Research
  but not the cited Market Analysis panel in the current adapter.

Current verification:

- Full backend regression passed with 152 tests; Ruff and the TypeScript/Vite
  production build passed.
- Docker backend rebuilt, PostgreSQL upgraded to migration `20260715_0009`, and
  existing Profile/Runs data remained readable.
- Server-side configuration reports Gemini, DeepSeek, and Kimi available without
  exposing API keys; read-only DeepSeek and Kimi model-list authentication both
  returned HTTP 200 without generating billable content.
- Browser acceptance passed for the Profile two-column layout, Runs cost table,
  compact Portfolio plans, model eligibility explanation, and removal of the V1
  sidebar.

### F048: Selectable Cash Goals and Shared Provider Resilience

Status: complete.

Completed functionality:

- Replaced the free-text near-term goal UI with eight selectable one-time expense
  types covering medical/dental, home/appliance, vehicle, travel, tuition,
  insurance/tax, family support, and other major purchases.
- Each selected type supports an optional estimate, 1–120 month horizon, and
  urgent/important/flexible priority. Incomplete selections remain visible but
  cannot silently affect numeric savings advice.
- Multiple short-term goals now reduce current liquidity and investable capacity.
  F050 subsequently removed the retirement cash-runway target. Unknown shocks
  remain part of the separate emergency-fund model.
- Added migration `20260715_0008` and backwards migration of the legacy named
  near-term goal into the preset major-purchase representation.
- Replaced Gemini-prefixed shared request controls with `ARGUS_MODEL_TIMEOUT_MS`,
  `ARGUS_MODEL_MAX_ATTEMPTS`, and `ARGUS_MODEL_RETRY_BACKOFF_MS`, applied across
  Gemini, DeepSeek, Kimi, Gemini embeddings, and market analysis.
- Updated the ignored local `.env` without exposing or replacing the existing
  Gemini key; DeepSeek and Kimi model/key slots are ready for user entry.
- Documented that `.env.example` is a template, why dotfiles are hidden, and why
  ChatGPT-connected banking data is not automatically available to local Argus.

Current verification:

- Backend regression: 152 tests passed; Ruff passed.
- TypeScript checking and Vite production build passed.
- Compose rebuild passed with backend, frontend, and healthy PostgreSQL running;
  Alembic reports migration `20260715_0008` at head.
- Browser acceptance passed for checkbox selection, two simultaneous goal editors,
  scientific-notation amount parsing, independent deadlines/priorities, responsive
  removal, and zero browser warnings/errors. Test values were not saved over the
  user's active Profile.

### F047: Research Execution Clarity and Cash-Flow Feasibility

Status: complete.

Completed functionality:

- Diagnosed Trace 26: the user selected Gemini, but all indexed documents had
  been deleted, retrieval returned no results, and the local evidence guard
  correctly skipped the cloud call. Replaced the misleading Local billing copy
  with an explicit selected-versus-executed outcome.
- Disabled Ask when no sources are indexed and added API-level 422/404 guards
  for empty or stale source scope. A cloud selection with insufficient evidence
  now reports `cloud_skipped_no_evidence` and zero provider cost.
- Added project-root `.env` setup guidance for Gemini, DeepSeek, and Kimi without
  exposing browser-side keys. Documented that DeepSeek/Kimi promotional balances
  are not guaranteed free API tiers.
- Reproduced Gemini market analysis through the real local endpoint and confirmed
  a structured `provider_quota_exhausted` 429. The UI now states short-window
  versus midnight-Pacific reset possibilities and that Argus did not enable billing.
- Added ordinary/scientific-notation money entry with parsed-dollar previews.
- Made emergency planning optional; disabled education amount/year when education
  context is `none`; added a named near-term cash need with amount and months.
- Replaced the user-invented retirement cash total with a transparent formula at
  that milestone; F050 later removed it after usability review and adopted a
  retirement planning-through age instead.
- Added total monthly spending and primary life/financial priority. Portfolio now
  compares cash-goal minimums with net income minus total spending and planned
  investing, reports the shortfall, and gives a deterministic adjustment order.
- Made the product name/symbol itself the official-source link. Optional sourced
  market analysis receives policy actions without dollar values and explains
  current supporting and counter-evidence separately from the trade math.
- Expanded Saved Profile into investor context, cash flow, cash goals, and the
  active investment policy instead of a few labels.

Current verification:

- Backend regression: 150 tests passed; Ruff passed.
- TypeScript checking and Vite production build passed.
- Migration `20260715_0007` is at Alembic head. Rebuilt Compose acceptance passed
  with backend, frontend, and healthy PostgreSQL services running.
- Browser acceptance passed for no-source Research protection, scientific-notation
  parsing, conditional education/emergency/near-term fields, expanded Saved Profile,
  cash-plan guidance, and direct official product links; no browser warnings or
  errors were recorded.

### F046: Multi-Provider Research, Goal-Driven Cash, and Sourced Market Context

Status: complete.

Completed functionality:

- Replaced duplicate Auto/Local Research choices with one privacy-first local
  default plus explicit Gemini 3.1 Flash-Lite, DeepSeek V4 Flash, and Kimi K2.6
  providers. Keys remain server-side environment configuration.
- Kept local retrieval and evidence-sufficiency checks ahead of every external
  generation call; added provider retry/timeout, usage, and model-specific cost
  tracing. Local answers no longer present internal text counters as billable
  API tokens.
- Removed transient Research upload/delete success prose while preserving error
  and loading states.
- Removed Cash from the 100% investment target allocation. Added a migration
  that removes and renormalizes Cash in existing saved policies.
- Added deterministic emergency, child-education, and retirement-cash goals
  using current savings, entered target amounts, and deadlines. Portfolio now
  shows targets, allocated savings, gaps, and whole-dollar minimum monthly
  savings separately from investment DCA.
- Added World Gold Council methodology context. Argus uses 5%, 7.5%, and 10%
  gold as its versioned example policy; it does not misstate those values as a
  universal institutional recommendation.
- Retained fractional-share support because it changes executable share math,
  and clarified that it never authorizes order placement.
- Added asset descriptions and official issuer/SEC links beside buy/sell and
  DCA output.
- Added a separate opt-in AI market-analysis endpoint and panel. Gemini uses
  Google Search grounding and Kimi uses built-in web search; output must contain
  direct sources and retrieval timestamps. Only symbol, asset class, weight,
  and holdings date leave the local app. The AI panel cannot rewrite deterministic
  allocations, trades, DCA, or cash goals.

Architecture decisions:

- Model-provider APIs and MCP solve different problems. The current adapters
  call provider HTTPS/SDK APIs behind `ModelProvider`; no executable MCP server
  or client exists yet, and MCP is not needed for model selection.
- DeepSeek is available for local-evidence synthesis but not the current-market
  panel because that panel requires provider-native cited web search.
- A complete real-time ETF database remains a separate temporal-data project
  with licensed adapters, identifier reconciliation, freshness rules, and
  deterministic eligibility/ranking.

Verification:

- Backend regression: 149 tests passed; Ruff passed.
- TypeScript checking and Vite production build passed.
- Docker Compose configuration passed; backend/frontend images rebuilt and all
  three local services started.
- PostgreSQL migration `20260715_0005 -> 20260715_0006` passed.
- Read-only API acceptance confirmed four model options, provider-specific
  price metadata, asset descriptions/links, and the separate cash-plan contract.
- Browser acceptance confirmed the single local default plus external model
  choices, Profile cash goals, Cash-free investment targets, the sourced AI
  market panel, separate cash/DCA sections, and no console errors.

### F045: Research Source Lifecycle and Explainable Portfolio Guidance

Status: complete.

Completed functionality:

- Changed Research upload from a multi-select batch to the clearer repeated
  flow: choose one file, upload it, then choose the next file.
- Percent-encoded browser filenames before placing them in an HTTP header and
  decoded them server-side, fixing Unicode/Chinese filename upload failures.
- Added `DELETE /documents/{document_id}` and a confirmed delete control in the
  right-hand source panel. Browser-uploaded raw files and artifact copies are
  deleted together with evidence, chunks, and embeddings in the active index;
  explicit user-owned local paths remain. As of F060, linked historical Runs and
  Reports are also removed after the same explicit confirmation.
- URL-decoded displayed source names, removing `%20` and `%27` artifacts.
- Replaced arbitrary 220-character local answer truncation with a complete-
  passage selector. Local mode now requires direct key-term support or returns
  the no-evidence response instead of turning Markdown table fragments into an
  apparent conclusion.
- Grounded Evidence validation and generated-report evidence in the exact
  retrieved chunk instead of a generic first-page excerpt. Reports are blocked
  unless validation passes.
- Preserved the current answer when the model dropdown changes; the new model
  applies only after the next Ask.
- Added a plain-language paid-tier formula and worked token-cost example.
- Moved recurring income and planned investment before Allocation guide, and
  exposed the input-dependent rule rationale, the internal Argus policy, and
  SEC Investor.gov / FINRA method references.
- Clarified that Cash can include in-scope savings, CDs, Treasury bills, and
  money-market cash equivalents; a brokerage-only file cannot reveal bank
  balances. Added explicit Alternatives examples and kept gold in its separate
  Commodity / Gold class.
- Replaced `Snapshot pricing` in the user-facing UI with `Using uploaded prices
  · not live quotes` while retaining the warning against trading on stale data.
- Expanded concentration flags to state the built-in 25% single-position and
  70% asset-class thresholds, use invested holdings with cash excluded, expose
  the threshold and percentage-point excess as structured API fields, and
  distinguish this screen from the saved Profile rebalance-drift threshold.
  A flag remains a review prompt rather than an automatic sale instruction.

Design and safety decisions:

- Institutional sources establish general factors and definitions but do not
  prescribe Argus's exact percentages. The numerical policy stays explicit,
  deterministic, versionable, and editable.
- Gemini is not needed to trigger or calculate concentration flags. A future
  labeled AI market-commentary layer may explain cited current context but may
  not alter deterministic weights, amounts, thresholds, or warnings.
- Previously generated report 11 remains an immutable historical artifact of
  run 18. The corrected pipeline prevents the same weak-evidence report from
  being generated again; it does not silently rewrite prior audit records.

Verification:

- Full backend regression: 136 tests passed; Ruff passed.
- TypeScript checking and Vite production build passed.
- Docker backend/frontend images rebuilt; backend, frontend, and PostgreSQL are
  running with migration 0005 at head.
- Browser acceptance confirmed decoded Unicode source display, complete local
  answer, exact supporting passage, passing Evidence validation, clean report
  12 HTML, model-switch answer persistence, inline confirmed source deletion,
  input-before-guidance order, SEC/FINRA method links, uploaded-price language,
  explicit bank/CD Cash scope, and the expanded 30.3% GLD risk explanation.
- Browser Console contained no errors; the temporary Unicode acceptance source
  was removed from the index after the deletion test.

### F044: Research Workflow Consolidation and Profile Allocation Guide

Status: complete.

Completed functionality:

- Removed the desktop-only source-path field from the Research UI and added
  repeatable Markdown/text/PDF/CSV browser upload.
- Added explicit `All indexed sources` and single-document search scopes; the
  panel now explains that entries can come from earlier local demos and that a
  click changes retrieval scope rather than opening the file.
- Made Auto privacy-first/local by default. Explicit Gemini selection now
  serves as public-excerpt consent, replacing the redundant external-AI box.
- Retained the optional evidence cutoff under Advanced for reproducible
  historical questions and future-evidence leakage protection.
- Collapsed successful Evidence validation into an expandable audit detail and
  combined report generation, completion metadata, and Open HTML in one card.
- Replaced six-decimal UI costs with adaptive precision and documented the
  token-rate formula for Gemini 3.1 Flash-Lite.
- Added migration 0005 and a recurring monthly net-income field.
- Added deterministic, auditable allocation guidance that fills an unsaved,
  one-decimal target mix from profile/cash-flow inputs. Commodity/gold and
  alternatives default to 0% unless the user opts in.
- Changed DCA output to whole-dollar budgets with total-preserving rounding,
  explicit cash-reserve semantics, whole-share leftover warnings, and an
  unsupported-instrument warning.
- Standardized Cash across policy actions and all three scenario cards as
  `HOLD` / `No shares — cash reserve`; positive targets without an approved
  product are marked `UNASSIGNED` / `No instrument assigned` instead of being
  presented as executable purchases.

Safety boundaries:

- The guide is an educational starting point, not a suitability determination
  or Gemini-generated advice. It does not know expenses, debts, emergency-fund
  balance, taxes, or account restrictions.
- Suggested percentages are applied only to the editable form and do not affect
  Portfolio calculations until the user explicitly saves them.
- The cost figure is a paid-tier equivalent, not an observed Google bill.

Verification:

- Full backend regression: 132 tests passed; Ruff passed.
- TypeScript checking and Vite production build passed.
- Docker backend, frontend, and PostgreSQL services are running with migration
  0005 at head.
- Browser acceptance confirmed multi-source Research scope and privacy-first
  Auto labels, unsaved deterministic Profile guidance with 0% Alternatives,
  one-decimal target inputs, whole-dollar DCA totals, explicit Cash semantics,
  unsupported-instrument labeling, and no browser console errors.

### F043: Auditable Profile Clear and Default Restore

Status: complete.

Completed functionality:

- Defined `Investment horizon` in the Profile UI as the future time until the
  invested money is expected to be used, not prior investing experience.
- Added idempotent `DELETE /profile`; it deactivates every active profile while
  preserving historical rows for auditability.
- Added **Clear & restore defaults** to restore the initial moderate-risk,
  60% equity / 30% bond / 10% cash, 5% drift-threshold form in one action.
- Kept restored defaults explicitly unsaved. Portfolio immediately returns to
  no-personal-target behavior until the user reviews and saves the form.
- Added an API regression proving clear, subsequent 404, history preservation,
  and repeated-clear safety.

Verification:

- Profile/Portfolio API regression: 12 tests passed.
- Ruff passed for the changed Python files.
- TypeScript checking and Vite production build passed.

### F042: Rebalancing Scenario Comparison and Expanded Asset Classes

Status: deterministic scenario comparison complete.

Completed functionality:

- Replaced ambiguous `target` wording with explicit `policy_target` and
  `example_review_level` semantics; the 20% no-profile reference is visibly not
  a personal recommendation.
- Added maintain, new-contribution dilution, and partial sell/reallocation
  projections with rebalancing amount, post-action weights, trade amounts,
  estimated shares, and known limitations.
- Expanded Profile target inputs to Commodity / Gold, International Equity,
  and Alternatives.
- Added symbol-aware class normalization so GLD, VXUS, common bond funds, and
  cash remain in the correct allocation sleeve even when an import uses a
  generic ETF label.
- Added analysis provenance to the API and UI: portfolio reason/limit text and
  arithmetic are deterministic Python, not Gemini output.
- Clarified Dollar-cost averaging as `定期定额投资 / 定投计划` in the UI.

Calculation notes:

```text
new cash required to dilute a position to a review line
  = position value / review weight - current portfolio value

partial-sale projection
  = current class value - executable sale amount + funded reallocation
```

Verification:

- Full backend regression: 127 tests passed; Ruff passed.
- TypeScript checking and Vite production build passed.
- Docker backend, frontend, and PostgreSQL services are running; API health is
  `ok` after rebuilding the local images with migration 0004 included.
- Browser verification against the existing 2026-07-14 holdings confirmed the
  three scenario cards, GLD `13 shares / $4,842.50` illustrative partial sale,
  `$24,795.72` contribution-dilution amount, expanded Profile controls, and no
  console errors.

Known limitations:

- The no-profile contribution and sale scenarios remain illustrations until
  the user supplies personal targets; unknown destination share counts stay
  blank.
- Projections use the uploaded dated price snapshot and exclude taxes, tax-lot
  selection, spreads, fees, and post-snapshot market movement.

### F041: Dated Portfolio Decision Support

Status: deterministic recommendation slice complete; licensed live market data
remains an explicit follow-up.

Completed functionality:

- Added migration 0004 for portfolio `as_of_date`, monthly contribution,
  rebalance threshold, fractional-share support, and contribution-first policy.
- Added browser and spreadsheet date inputs with one-snapshot validation and
  conflict rejection.
- Replaced vague portfolio scenarios in the primary UI with auditable BUY,
  SELL, and REVIEW rows containing dollar amount, estimated shares, reference
  price/date, current-versus-target weights, rationale, and constraints.
- Added contribution-first DCA calculations and missing-exposure reviews with
  official issuer links for diversified ETF candidates.
- Kept individual-stock selection behind the evidence-backed research workflow
  instead of using an unverified ticker list as personalized advice.
- Added explicit snapshot-pricing status so uploaded prices are never presented
  as live quotes.

Calculation contract:

```text
target value = portfolio value * target weight
drift amount = current asset-class value - target value
estimated shares = drift amount / dated reference price
DCA allocation = monthly contribution * class deficit / total positive deficits
```

Verification:

- Full backend regression: 125 tests passed; Ruff passed.
- Unit tests cover dated CSVs, mixed-date rejection, exact buy/sell amounts,
  whole-share estimates, taxable-account warnings, coverage gaps, and DCA.
- API tests cover form dates, spreadsheet conflicts, profile target-sum
  validation, persistence, and response dates.
- TypeScript and Vite production build pass with the expanded Portfolio and
  Profile interfaces.
- Browser verification confirmed the dated upload control, dated summary,
  shares/prices table, constrained GLD review amount, snapshot-pricing banner,
  DCA empty-state guidance, and new Profile controls with no console errors.

Known limitation:

- Current recommendations use the uploaded price snapshot. A licensed market
  quote provider and source-timestamped macro context are required before Argus
  can claim current-market-aware share estimates for new candidates.

### F039: V2 AWS/EKS Cloud-Ready Foundation

Status: bounded live AWS acceptance complete; environment destroyed.

Completed functionality:

- Added Redis cache and job contracts, a worker process, and local V2 Compose.
- Added versioned Kafka envelopes, idempotent producer settings, and AWS MSK IAM
  authentication support.
- Archived raw uploads through an encrypted S3 adapter and emitted ingestion
  and completed-run events.
- Added AWS Terraform for VPC, EKS, RDS PostgreSQL, ElastiCache, S3, ECR,
  Secrets Manager, IRSA, and optional MSK Serverless.
- Added production containers and Kubernetes API/frontend/worker/eval/Ingress/
  HPA resources with probes and resource limits.
- Added FastAPI/SQLAlchemy OTLP tracing and an OpenTelemetry Collector with a
  Prometheus-compatible exporter.
- Added architecture, cost, deployment, rollback, and destroy documentation.
- Added a cost-bounded `aws-smoke` Kustomize overlay with one replica per
  service and no ALB or HPA dependency.
- Added a secret-sync helper that merges non-empty local Gemini settings into
  Secrets Manager and Kubernetes without printing values or persisting
  plaintext files.
- Added a 31 USD AWS Budget configuration and development-only force cleanup
  for S3, ECR, and Secrets Manager.
- Fixed Redis blocking-read timeouts so an empty TLS-backed queue does not
  crash the worker.

Verification:

- Cloud adapter tests use fake Redis, Kafka, and S3 clients, including a
  blocking-read timeout regression.
- A live `us-west-2` deployment used EKS 1.35, one Free Tier-eligible
  `m7i-flex.large` node, RDS PostgreSQL 16.14, ElastiCache Redis, S3, ECR,
  Secrets Manager, IRSA, and a 31 USD monthly budget; MSK remained disabled.
- Kubernetes migrations 0001-0003 completed, API/frontend/worker became Ready,
  and the fixed worker consumed a Redis healthcheck job with `complete/ok`.
- A public fixture produced a 768-dimensional `gemini-embedding-001` pgvector
  row, used the HNSW index path, and completed a
  `gemini-3.1-flash-lite` answer with citations and recorded cost.
- S3 archival through IRSA succeeded, with no static AWS credential placed in
  the Pod secret.
- Terraform destroyed 71 resources immediately after acceptance. Independent
  checks found no Argus EKS, RDS, ElastiCache, VPC, NAT, ECR, S3, Secret,
  Budget, or Terraform-state residue.
- Cost Explorer still showed an estimated near-zero amount immediately after
  teardown; final AWS billing remains subject to normal reporting delay.

### F038: V1.1 Manual Model Selection and Tool Resilience

Status: complete.

Completed functionality:

- Added a model catalog endpoint and Research advanced-control picker for Auto
  routing or explicit local/Gemini selection.
- Enforced manual choices in the backend without weakening sensitivity,
  capability, cloud-configuration, or API-key gates.
- Persisted manual selection mode, selected profile, and selection rationale in
  the existing run trace.
- Added bounded tool timeouts, retryable-result and exception retries, linear
  backoff, terminal error classification, and attempt metadata.
- Added environment controls for timeout, maximum attempts, and retry backoff.

Verification:

- Unit and API tests cover manual selection, unavailable-model rejection,
  retry-until-success, and bounded timeout behavior.
- Full verification results are recorded with the V1.1 commit.

### F037: V1 Release Audit and Reproducible Acceptance

Status: complete.

Completed functionality:

- Audited all Phase 0-10 tasks and confirmed that remaining unchecked work is
  explicitly V1.1 or Post-V1/V2.
- Added an isolated clean-database acceptance runner covering migrations,
  semantic retrieval, cited answers, refusal guards, reports, Profile,
  Portfolio, and Runs.
- Fixed `.gitignore` so the documented sample HTML report is included in a
  clean checkout.
- Marked V1 complete without reclassifying PDF export, manual model override,
  tool retry hardening, or cloud infrastructure as required V1 work.

Verification:

- Clean PostgreSQL database migrated from revision 0001 through 0003.
- Acceptance run created a 768-dimensional indexed Gemini embedding, a cited
  answer, a 10-section report, a profile, and a $3,500 sample portfolio.
- Unsupported future-year and unrelated questions returned no evidence.
- Backend regression: 98 tests passed; Ruff passed.
- Frontend TypeScript and Vite production build passed.
- Docker Compose configuration validated.

### F036: Semantic Retrieval, Rich Reports, and Cost Semantics

Status: complete.

Completed functionality:

- Added `gemini-embedding-001` with 768-dimensional normalized vectors and
  distinct `RETRIEVAL_DOCUMENT` and `RETRIEVAL_QUERY` task types.
- Cached chunk embeddings by provider/model so repeated questions only embed
  the query, not every stored chunk.
- Resized the PostgreSQL pgvector column and HNSW cosine index from 16 to 768
  dimensions while retaining JSON hash vectors for internal/SQLite fallback.
- Combined a calibrated semantic-similarity guard with lexical relevance and
  temporal evidence guards.
- Added report sections for investment thesis, risks and uncertainties,
  counter-evidence gaps, falsification conditions, and investment implications.
- Relabeled model cost as paid-tier equivalent, explained that actual billing
  is unavailable per request, and mapped Free Tier quota/rate-limit errors
  without automatic paid fallback.

Technology stack:

- Google Gen AI embeddings API
- PostgreSQL/pgvector and HNSW cosine search
- SQLAlchemy and Alembic schema migration
- FastAPI error mapping
- React/TypeScript cost and quota states
- pytest provider fakes and retrieval regression tests

Verification:

- Real database row: `google / gemini-embedding-001 / 768 / indexed=true`.
- Related gold-factor queries scored approximately 0.68-0.73; an unrelated
  semiconductor query scored approximately 0.56 and remained blocked.
- A real public query returned cited real-yield and central-bank factors.
- Unrelated and unsupported 2027 questions returned no evidence and no report.
- A real source-backed run generated an expanded HTML report.
- Full regression result: 98 backend tests passed; Ruff and frontend production
  build passed.

Known limitations:

- The 0.62 semantic threshold is calibrated on the V1 demo corpus and needs a
  larger labeled retrieval evaluation before production use.
- Paid-tier equivalent currently tracks model generation calls, not a separate
  embedding-call cost ledger.

### F035: Optional Gemini Provider and Public-Data Consent Gate

Status: complete.

Completed functionality:

- Added a Google Gemini provider using the current `google-genai` SDK.
- Selected stable `gemini-3.1-flash-lite` as the default economy model after
  live validation showed that 2.5 Flash is unavailable to new API users.
- Kept retrieval planning local and skipped the external API when retrieval
  returns no evidence.
- Removed the selected-document fallback that previously returned unrelated
  evidence; full-document fallback now requires explicit `this article` or
  current-document wording.
- Added per-request timeout/retry configuration, real token usage parsing, and
  configurable estimated token cost.
- Added a frontend consent checkbox that marks only the current research
  question and retrieved excerpts as public and eligible for Gemini.
- Kept internal and restricted research, Portfolio, and Profile flows local.
- Added provider tests covering retrieval-first planning, zero-call
  no-evidence behavior, token/cost recording, and API failure handling.

Technology stack:

- Google Gen AI Python SDK
- provider abstraction and custom agent loop
- sensitivity-aware model routing
- React/TypeScript consent control
- environment-based secret configuration
- pytest fakes for network-independent provider tests

Verification:

- Gemini provider unit tests pass without a real network call.
- Docker image installs `google-genai` successfully.
- A credentialed live request returned a cited answer from Gemini 3.1
  Flash-Lite with 332 provider tokens and 638 ms recorded model latency.
- Future-year and unrelated questions were stopped by the local evidence guard
  with zero Gemini calls and zero estimated external cost.
- A Gemini-backed Ask run generated a complete cited HTML report, and uploaded
  source names render without internal UUID storage prefixes.
- Full regression result: 94 backend tests passed; Ruff and frontend production
  build passed.

This gap was closed by F036 for explicitly public research. Internal research
retains the local deterministic fallback by design.

### F034: Docker Compose and Native PostgreSQL/pgvector Retrieval

Status: complete.

Completed functionality:

- Installed and started Docker Desktop on Apple Silicon.
- Started frontend, FastAPI, and PostgreSQL/pgvector through Docker Compose.
- Added an Alembic migration that enables the `vector` extension and initially
  created a native `vector(16)` column with an HNSW cosine index. F036 later
  migrated this column to `vector(768)` for semantic embeddings.
- Added PostgreSQL database-side cosine retrieval while retaining the SQLite
  JSON/cosine fallback for deterministic tests.
- Made the backend run `alembic upgrade head` before starting FastAPI.
- Added a frontend `.dockerignore` and deterministic `npm ci` image build.

Technology stack:

- Docker Desktop and Docker Compose
- PostgreSQL 16 and pgvector 0.8.5
- SQLAlchemy and Alembic
- pgvector SQLAlchemy integration
- HNSW cosine index

Verification:

- All three Compose services are running.
- API health check returns 200.
- The initial pgvector proof stored native `vector(16)` values; F036 migrated
  the active semantic index to `vector(768)`.
- PostgreSQL `EXPLAIN` uses `ix_chunk_embeddings_vector_hnsw`.
- A real FastAPI query retrieved cited evidence from PostgreSQL.

### F033: Factor-Question Intent Handling for CSV Evidence

Status: complete.

Completed functionality:

- Added local intent handling for factor/driver questions such as
  `What factors influence gold price?`.
- Prevented factor questions from selecting outcome columns such as
  `gold_return_pct`.
- Summarized factor-like CSV columns such as real yields, ETF flows, and
  central-bank demand share.
- Added regression coverage for the gold-price-factor question against
  `gold_macro_indicators.csv`.

Technology stack:

- Python deterministic model provider
- intent-aware CSV column selection
- FastAPI chat workflow
- pytest

Interview questions:

- Why did a factor question previously return a gold-return trend?
- What is the difference between an outcome column and a driver/factor column?
- Why is intent classification important in a RAG application?
- Why should the local answer say `possible factors` instead of making a causal
  claim?

Foundational concepts to review:

- query intent classification
- RAG false positives
- feature/driver variables versus outcome variables
- evidence-grounded wording
- deterministic baseline versus LLM reasoning

### F032: Temporal Evidence Sufficiency Guard

Status: complete.

Completed functionality:

- Hid the Research report builder when the current answer has no local
  source-backed evidence.
- Added a CSV temporal coverage guard: if a question asks for a specific year
  that is not present in the CSV time column, Argus returns no evidence instead
  of summarizing historical data.
- Added a text evidence year check: if a question names a specific year, text
  evidence must also contain that year to support the answer.
- Added regression coverage for `What's the gold trend in 2027?` against a
  2021-2025 gold macro CSV.

Technology stack:

- React/TypeScript conditional rendering
- Python deterministic model provider
- CSV time-column validation
- FastAPI chat workflow
- pytest

Interview questions:

- Why is keyword relevance not enough for evidence-grounded answers?
- How does Argus handle a question whose requested time period is not covered by
  the retrieved evidence?
- Why hide report generation for no-evidence answers instead of showing a
  disabled report builder?
- What are the limits of deterministic local evidence rules compared with an
  external LLM plus stronger retrieval?

Foundational concepts to review:

- temporal consistency
- evidence sufficiency
- historical data versus forecast questions
- false-positive retrieval
- UX guardrails for unavailable actions

### F031: Report Generation Split from Q&A Runs

Status: complete.

Completed functionality:

- Split report generation from the Q&A agent run.
- Changed `/reports/generate` to require a completed source-backed Ask
  `source_run_id`.
- Reused the stored answer, citations, and trace metadata from the Ask run
  instead of running the research agent a second time.
- Stored final answers in `agent_runs.metadata_json` for report rendering.
- Moved `Generate HTML report` into a separate Research report builder section
  in the frontend.
- Blocked CSV-only historical metrics from answering direct investment advice
  questions such as `Can I invest gold in 2026?`.
- Cleaned report topics for personal-investment wording such as `Can I invest`.

Technology stack:

- FastAPI
- Pydantic request models
- SQLAlchemy run/tool-call persistence
- React/TypeScript
- local deterministic agent runtime
- pytest

Interview questions:

- Why should report generation reuse an existing Ask run?
- How does separating Q&A from report rendering reduce LLM cost?
- What should happen if a user asks for investment advice but the source only
  contains historical CSV metrics?
- Why should frontend product flow reflect backend cost boundaries?

Foundational concepts to review:

- idempotent artifact generation
- trace/run reuse
- token cost control
- source-backed report artifacts
- product workflow separation

### F030: Query-Focused CSV Answers and Citation Guard

Status: complete.

Completed functionality:

- Made local CSV answers focus on question keywords instead of always
  summarizing the same default columns.
- Returned different answers for different questions against the same CSV, such
  as gold return versus ETF flows.
- Returned no-evidence answers when the selected CSV has no matching metric,
  such as asking for semiconductor margins in a gold macro dataset.
- Cleared citation IDs and sources when the final answer is no-evidence.
- Filtered CSV-backed report charts to question/claim-relevant metrics instead
  of charting every numeric column in the cited file.
- Kept report generation blocked when no source-backed claim can be produced.

Technology stack:

- Python deterministic model provider
- CSV parsing
- keyword-based metric selection
- FastAPI chat/report workflow
- local agent loop
- pytest

Interview questions:

- Why did two different CSV questions previously return the same answer?
- How does Argus decide which CSV columns are relevant to a question?
- Why should no-evidence answers clear citations even when retrieval returned a
  fallback source?
- Why should report generation require claims and citations?
- Why should report charts be filtered by the question even when the cited CSV
  contains more data?

Foundational concepts to review:

- lexical matching versus semantic retrieval
- structured-data answer generation
- false citations
- chart relevance
- API-level guardrails
- regression tests for AI product behavior

### F029: Report Data Interpretation Narratives

Status: complete.

Completed functionality:

- Added a `Data Interpretation` section to generated reports when chart data is
  available.
- Added `What it shows` narrative text to each chart card.
- Generated chart narratives from cited chart data instead of fixed copy.
- Summarized line-chart start/end values, peaks, lows, and positive crossings.
- Summarized time-series bar chart flow changes.

Technology stack:

- Python report rendering
- structured report JSON
- deterministic chart narration
- SVG/HTML report output
- pytest

Interview questions:

- Are the charts fixed or data-driven?
- Why should charts have narrative text?
- Why use deterministic chart interpretation before an LLM writer?
- How does Argus prevent chart text from drifting away from cited evidence?

Foundational concepts to review:

- chart templates versus chart data
- deterministic rendering
- evidence-backed visualizations
- narrative generation from structured data

### F028: CSV Answer Summaries and Cleaner Report Titles

Status: complete.

Completed functionality:

- Converted CSV evidence answers from raw table text into readable trend
  summaries.
- Prevented raw CSV headers/rows from becoming the main answer and report claim.
- Cleaned generated report topics such as `Is The Gold Asset Value Trend` into
  `Gold Asset Value Trend`.
- Added frontend and backend title cleanup.
- Added regression tests for CSV answer formatting and report title cleanup.

Technology stack:

- Python CSV parsing
- deterministic local model provider
- FastAPI report API
- React/TypeScript topic derivation
- pytest

Interview questions:

- Why is raw retrieved evidence not always a valid answer?
- When should evidence-backed reports still be blocked or improved?
- Why clean persisted report titles in the backend as well as the frontend?
- How does deterministic summarization differ from using a real LLM?

Foundational concepts to review:

- structured data summarization
- answer quality versus evidence presence
- artifact quality controls
- frontend/backend validation duplication

### F027: Current Source Question Context

Status: complete.

Completed functionality:

- Added current-source tracking to the Research page.
- Set the active source after local path ingestion or browser upload.
- Made the indexed source list clickable and highlighted the current source.
- Added `document_id` to chat and report generation requests.
- Passed selected document context through the local agent loop into the
  `retrieve_evidence` tool.
- Let retrieval rank and fallback within the selected document, so broad
  questions can still produce source-backed answers from the current article.

Technology stack:

- React
- TypeScript
- FastAPI
- Pydantic request models
- local agent tool dispatch
- SQLAlchemy retrieval filters
- pytest

Interview questions:

- Why did free-form questions need current-document context?
- Why is selected-document fallback safer than global latest-document fallback?
- How does `document_id` move through frontend, API, agent, and tool layers?
- What are the remaining limits before real semantic retrieval?

Foundational concepts to review:

- UI state as retrieval context
- request schema evolution
- tool-call arguments
- source scoping
- false citation prevention

### F026: No-Evidence Report Guard and Current-Article Fallback

Status: complete.

Completed functionality:

- Blocked report generation when the current answer has no local source-backed
  claim.
- Added backend `422` guard to `/reports/generate` for no-evidence runs.
- Disabled Research page `Generate report` until a source-backed answer exists.
- Cleared stale answer/report results when the user changes the question or
  evidence cutoff date.
- Added retrieval fallback for `this article`, `uploaded file`, and Chinese
  document-reference prompts, using the most recently indexed document.
- Changed the local critic to mark no-evidence answers as `warning` instead of
  `passed`.

Technology stack:

- FastAPI
- React
- TypeScript
- SQLAlchemy
- local JSON-vector retrieval fallback
- pytest

Interview questions:

- Why should report generation be stricter than chat answers?
- Why enforce the no-evidence rule in both frontend and backend?
- How does the current-article fallback differ from true semantic retrieval?
- Why mark no-evidence answers as warnings instead of passes?

Foundational concepts to review:

- HTTP `422 Unprocessable Entity`
- source-backed claims
- frontend state invalidation
- lexical retrieval versus semantic retrieval
- product guardrails for evidence-grounded AI

### F000: Local Development Skeleton

Status: complete.

Completed functionality:

- Initialized local project skeleton.
- Added FastAPI backend entry point with `/health`.
- Added React/TypeScript frontend skeleton.
- Added Docker Compose services for frontend, backend, and PostgreSQL/pgvector.
- Added local-only integration flags for cloud, Gmail, and Robinhood.

Technology stack:

- Python
- FastAPI
- React
- TypeScript
- Vite
- Docker
- Docker Compose
- PostgreSQL/pgvector image
- pytest

Interview questions:

- Why split the app into frontend, backend, and database services?
- Why should the frontend not connect directly to PostgreSQL?
- What does `/health` prove and what does it not prove?
- What problem does Docker Compose solve for local development?
- Why keep Gmail, Robinhood, and cloud integrations disabled in V1?

Foundational concepts:

- HTTP API
- localhost and ports
- container vs image
- environment variables
- CORS
- health checks
- `.gitignore` and generated files

Verification:

- Backend unit tests passed at the time of implementation.
- Docker Compose config could not be formally validated in the current
  environment because Docker CLI was unavailable.

Known gaps:

- No real product workflow yet.
- No database tables existed yet at the end of Phase 0.

### F001: Phase 1 Backend Foundation Slice

Status: complete.

Completed functionality:

- Added central settings loader in `investment_agent.config`.
- Connected FastAPI app to settings for environment mode and CORS origins.
- Added SQLAlchemy database session helpers.
- Added V1 ORM models for:
  - `documents`
  - `evidence_items`
  - `chunks`
  - `chunk_embeddings`
  - `reports`
  - `claims`
  - `portfolio_positions`
  - `user_profiles`
  - `agent_runs`
  - `tool_calls`
  - `model_calls`
- Added Alembic configuration and first migration for V1 tables.
- Added document/evidence repository layer.
- Added tests for settings and storage metadata/repository behavior.

Technology stack:

- Python dataclasses
- Environment variables
- FastAPI app state
- SQLAlchemy ORM
- Alembic migrations
- PostgreSQL-compatible schema design
- SQLite-compatible repository test path
- pytest

Interview questions:

- Why use a settings object instead of reading environment variables everywhere?
- What is the difference between an ORM model and a database table?
- What problem does Alembic solve?
- Why do schema migrations matter in a real project?
- What is a repository layer and why not call SQLAlchemy directly everywhere?
- What is the difference between `documents`, `evidence_items`, and `chunks`?
- Why does Argus store `agent_runs`, `tool_calls`, and `model_calls`?
- How does the schema prepare for self-hosted model serving?

Foundational concepts:

- Configuration management
- Twelve-factor app style config
- Relational tables
- Primary keys and foreign keys
- One-to-many relationships
- ORM session lifecycle
- Transactions, commit, and rollback
- Database migrations
- Evidence provenance
- Run tracing

Verification:

- `.venv/bin/python -B -m pytest -p no:cacheprovider`
  - 16 passed after dependency validation and ingestion work.
- `python3 -B -m py_compile ...`
  - passed for new Python files and Alembic migration.
- `ARGUS_DATABASE_URL=sqlite:////private/tmp/argus_alembic_check.db .venv/bin/alembic upgrade head`
  - created all V1 tables in a temporary SQLite database.

Known gaps:

- PostgreSQL migration still needs to be run through Docker/Postgres when Docker
  is available.
- `chunk_embeddings.embedding_json` is a V1-friendly placeholder. Phase 3 should
  convert retrieval storage to true pgvector behavior.

### F002: Dependency Validation and Test Harness

Status: complete.

Completed functionality:

- Created local `.venv`.
- Installed `.[dev,storage]`.
- Added missing `httpx2` dev dependency for FastAPI/Starlette TestClient.
- Added FastAPI health endpoint test.
- Ran full test suite without skipped storage tests.
- Ran Ruff across the repository.
- Validated Alembic migration against a temporary SQLite database.

Technology stack:

- Python virtual environment
- pip extras
- pytest
- FastAPI TestClient
- SQLAlchemy
- Alembic
- Ruff

Interview questions:

- What are Python package extras such as `.[dev,storage]`?
- Why separate dev dependencies from storage dependencies?
- Why did the earlier storage test skip, and what changed?
- Why validate Alembic against SQLite if production target is PostgreSQL?
- Why does FastAPI TestClient require an additional test dependency?

Foundational concepts:

- virtual environments
- dependency groups/extras
- test dependencies
- integration tests vs unit tests
- linting
- migration smoke tests

Verification:

- `.venv/bin/python -B -m pytest -p no:cacheprovider`
  - 16 passed
- `.venv/bin/ruff check .`
  - passed
- Alembic temporary SQLite upgrade
  - created `documents`, `evidence_items`, `chunks`, `chunk_embeddings`,
    `reports`, `claims`, `portfolio_positions`, `user_profiles`, `agent_runs`,
    `tool_calls`, and `model_calls`.

Known gaps:

- Docker CLI is still unavailable in the current environment, so Compose and
  PostgreSQL container validation are still pending.

### F003: Local Text and Markdown Ingestion

Status: complete. Superseded by F004 for PDF coverage.

Completed functionality:

- Added local file ingestion package.
- Implemented `.txt` ingestion.
- Implemented `.md` ingestion.
- Added deterministic text chunking with overlap.
- Computed SHA-256 content hashes for documents and chunks.
- Stored document, evidence item, and chunk rows through the repository layer.
- Added idempotency by document content hash.
- Rejected unsupported file types explicitly.

Technology stack:

- Python `pathlib`
- SHA-256 hashing
- UTF-8 text parsing
- deterministic chunking
- SQLAlchemy repository
- pytest temporary directories
- SQLite-backed repository tests

Interview questions:

- Why compute a content hash during ingestion?
- What is idempotent ingestion and why does it matter?
- Why split documents into chunks?
- Why use overlap between chunks?
- What is the difference between parser metadata and evidence metadata?
- Why reject unsupported file types explicitly?

Foundational concepts:

- file parsing
- content hashing
- idempotency
- chunk size
- chunk overlap
- provenance
- citation granularity

Verification:

- `.venv/bin/python -B -m pytest -p no:cacheprovider`
  - 16 passed at initial `.txt`/`.md` implementation
- `.venv/bin/ruff check .`
  - passed

Known gaps:

- API endpoints were added later in F005.
- Chunking is character-based for V1 simplicity; token-aware chunking can be
  added later if needed.

### F004: Simple Text PDF Ingestion

Status: complete.

Completed functionality:

- Added `pypdf` as a V1 dependency.
- Added `.pdf` support to local file ingestion.
- Extracted text from text-based PDF pages.
- Created one evidence item per extracted PDF page.
- Stored page metadata on evidence items and chunks.
- Added PDF ingestion test using a minimal text PDF fixture.

Technology stack:

- pypdf
- page-level PDF text extraction
- SQLAlchemy repository
- pytest fixture generation
- SHA-256 hashing

Interview questions:

- What kind of PDFs does V1 support?
- Why is scanned PDF OCR out of scope?
- Why store page number metadata?
- Why create page-level evidence for PDFs?
- What are the limitations of `pypdf` text extraction?

Foundational concepts:

- text PDF vs scanned/image PDF
- OCR
- page-level provenance
- extraction quality
- citation granularity

Verification:

- `.venv/bin/python -B -m pytest -p no:cacheprovider`
  - 17 passed
- `.venv/bin/ruff check .`
  - passed

Known gaps:

- No OCR for scanned PDFs.
- No production-grade table extraction.
- No layout-aware multi-column parsing.
- API endpoints were added later in F005.

### F005: Documents Ingestion API

Status: complete.

Completed functionality:

- Added FastAPI DB session dependency with commit/rollback/close lifecycle.
- Added documents API router.
- Added `POST /documents/ingest`.
- Added `GET /documents`.
- Wired application startup to create SQLAlchemy engine and session factory.
- Added API tests for text ingestion, PDF ingestion, duplicate ingestion, and
  error mapping.

Technology stack:

- FastAPI `APIRouter`
- FastAPI dependency injection
- Pydantic request/response schemas
- SQLAlchemy session lifecycle
- HTTP status codes
- FastAPI TestClient
- SQLite-backed API tests

Interview questions:

- What is the difference between Argus API and model provider APIs like Gemini?
- Why use FastAPI dependency injection for DB sessions?
- Why should API routes return typed Pydantic response models?
- How does `POST /documents/ingest` handle missing or unsupported files?
- Why test API behavior separately from repository behavior?
- What does session commit/rollback protect against?

Foundational concepts:

- REST API
- request body
- response model
- HTTP status codes
- dependency injection
- transaction lifecycle
- API integration testing

Verification:

- `.venv/bin/python -B -m pytest -p no:cacheprovider`
  - 21 passed
- `.venv/bin/ruff check .`
  - passed

Known gaps:

- `POST /documents/ingest` currently accepts a local filesystem path; browser
  file upload is not implemented yet.
- No authentication or authorization yet.
- No pagination/filtering on `GET /documents` yet.

### F006: Deterministic Local Embedding Path

Status: complete.

Completed functionality:

- Added embedding provider abstraction.
- Added deterministic local hash embedding provider.
- Added embedding service to embed stored chunks.
- Added repository methods to upsert and list chunk embeddings.
- Stored embeddings in `chunk_embeddings.embedding_json`.
- Made embedding generation idempotent per chunk/provider/model.

Technology stack:

- Python Protocol
- dataclasses
- SHA-256 token hashing
- vector normalization
- SQLAlchemy
- pytest

Interview questions:

- What is an embedding?
- Why add an embedding provider abstraction?
- Why use deterministic hash embeddings first?
- Why is deterministic hash embedding not a semantic embedding model?
- Why make embedding writes idempotent?
- Why is this not yet true pgvector retrieval?

Foundational concepts:

- embedding vector
- vector dimensions
- normalization
- provider abstraction
- deterministic tests
- semantic vs non-semantic embeddings
- idempotent indexing

Verification:

- `.venv/bin/python -B -m pytest -p no:cacheprovider`
  - 23 passed
- `.venv/bin/ruff check .`
  - passed

Known gaps:

- Embeddings are stored as JSON for now, not pgvector columns.
- The deterministic provider is for local testing, not semantic retrieval
  quality.
- Top-k retrieval is not implemented yet.

### F007: JSON Vector Top-K Retrieval Fallback

Status: complete.

Completed functionality:

- Added vector retrieval service.
- Embedded user query with the configured embedding provider.
- Compared query vector against stored JSON chunk vectors.
- Implemented cosine similarity ranking.
- Returned top-k chunks with document and evidence metadata.
- Added basic `access_scope` filter.
- Added retrieval tests for ranking, evidence metadata, filtering, and invalid
  `top_k`.

Technology stack:

- cosine similarity
- local JSON vector fallback
- SQLAlchemy joins
- embedding provider abstraction
- pytest

Interview questions:

- What is top-k retrieval?
- What is cosine similarity?
- Why return evidence metadata with retrieved chunks?
- Why is this a fallback instead of final pgvector retrieval?
- Why apply metadata filters before or during retrieval?
- What are the limitations of deterministic embeddings for ranking?

Foundational concepts:

- vector similarity
- top-k search
- query embedding
- chunk embedding
- evidence snippets
- metadata filtering
- fallback implementation

Verification:

- `.venv/bin/python -B -m pytest -p no:cacheprovider`
  - 26 passed
- `.venv/bin/ruff check .`
  - passed

Known gaps:

- Uses JSON vectors in Python, not PostgreSQL/pgvector operators.
- `as_of_date` filtering was added later in F008.
- Does not yet expose a runtime tool named `retrieve_evidence`.
- Ranking quality is limited by deterministic hash embeddings.

### F008: Retrieval `as_of_date` Filtering

Status: complete.

Completed functionality:

- Added `as_of_date` filtering to chunk embedding queries.
- Excludes evidence where `publication_date` is after the requested as-of date.
- Excludes evidence where `data_as_of_date` is after the requested as-of date.
- Preserves undated evidence by allowing null date fields.
- Added seeded future-evidence test proving future evidence is excluded.

Technology stack:

- SQLAlchemy filter expressions
- date metadata
- vector retrieval service
- pytest seeded fixtures

Interview questions:

- Why does Argus need `as_of_date` filtering?
- What is the difference between `publication_date` and `data_as_of_date`?
- Why allow null dates through the filter?
- Why should temporal filtering happen before ranking?
- How does the test prove future evidence does not leak?

Foundational concepts:

- temporal consistency
- hindsight bias
- metadata filtering
- nullable fields
- publication date vs data as-of date
- historical research correctness

Verification:

- `.venv/bin/python -B -m pytest -p no:cacheprovider`
  - 27 passed
- `.venv/bin/ruff check .`
  - passed

Known gaps:

- Ingestion does not yet parse dates from files automatically.
- Date metadata currently needs to be supplied by repository/API workflows.
- pgvector-backed retrieval is still pending.

### F009: `retrieve_evidence` Tool Runtime

Status: complete.

Completed functionality:

- Added a small `ToolRegistry` for registering and dispatching agent tools.
- Added explicit unknown-tool errors for unsupported tool names.
- Added `retrieve_evidence` tool factory.
- Wrapped vector retrieval behind `ToolCall` and `ToolResult` contracts.
- Validated tool arguments for query, `top_k`, `access_scope`, and
  `as_of_date`.
- Returned structured evidence results with chunk, document, source, score, and
  citation metadata.
- Exported retrieval tool helpers from the retrieval package.
- Added tests for unknown tools, duplicate registration, successful retrieval,
  and invalid arguments.

Technology stack:

- Python dataclasses
- callable-based tool registry
- Fast local deterministic embeddings
- vector retrieval service
- SQLAlchemy session-backed repositories
- pytest

Interview questions:

- Why introduce a tool registry instead of calling retrieval directly?
- What is the difference between a normal function and an agent tool?
- Why use `ToolCall` and `ToolResult` as contracts?
- How does `retrieve_evidence` connect RAG retrieval to an agent loop?
- How should invalid tool arguments be handled?
- Why should an LLM not directly query the database?

Foundational concepts:

- tool dispatch
- tool contracts
- allowlisted tools
- structured errors
- RAG context retrieval
- argument validation
- agent runtime boundaries

Verification:

- `.venv/bin/python -B -m pytest -p no:cacheprovider tests/test_retrieval_tool.py`
  - 4 passed
- `.venv/bin/python -B -m pytest -p no:cacheprovider`
  - 31 passed
- `.venv/bin/ruff check .`
  - passed

Known gaps:

- A deterministic mock agent loop is implemented in F010, but no real LLM
  provider is connected yet.
- Runtime routing policy integration is still pending.
- The current retrieval backend still uses JSON vectors instead of pgvector.

### F010: Deterministic Mock Agent Loop

Status: complete.

Completed functionality:

- Added model provider runtime contracts:
  - `ModelProvider`
  - `ModelRequest`
  - `ModelResponse`
- Added `DeterministicMockModelProvider` for local-only agent-loop tests.
- Added `AgentRunRepository` for persisted run traces.
- Added `AgentLoop` with max-iteration guard.
- Agent loop creates `agent_runs` with `selection_mode="auto"`.
- Agent loop stores selected model and model-selection reason.
- Agent loop records each mock `model_call`.
- Agent loop dispatches `retrieve_evidence` through `ToolRegistry`.
- Agent loop records each `tool_call`.
- Agent loop produces a cited answer when local evidence is found.
- Agent loop records token totals and estimated cost totals.
- Agent loop returns structured failures for unknown tool, budget exceeded, and
  max-iteration exceeded cases.

Technology stack:

- Python dataclasses and protocols
- local deterministic mock model provider
- callable tool registry
- SQLAlchemy ORM persistence
- `agent_runs`, `tool_calls`, `model_calls`
- token/cost accounting scaffold
- pytest

Interview questions:

- What is an agent loop?
- Why use a deterministic mock model before connecting a real LLM?
- How does the loop decide when to call `retrieve_evidence`?
- What do `agent_runs`, `tool_calls`, and `model_calls` record?
- What is a max-iteration guard and why is it necessary?
- How does the current budget handling work, and what is still missing?
- Why is this not yet a production agent runtime?

Foundational concepts:

- model provider abstraction
- model request/response contracts
- tool call round trip
- persisted traces
- token accounting
- cost accounting
- max-iteration guard
- structured runtime failure

Verification:

- `.venv/bin/python -B -m pytest -p no:cacheprovider tests/test_agent_loop.py`
  - 4 passed
- `.venv/bin/python -B -m pytest -p no:cacheprovider`
  - 35 passed
- `.venv/bin/ruff check .`
  - passed

Known gaps:

- The agent loop still uses a deterministic mock model, not Gemini/Claude/local
  vLLM.
- Existing routing policy is not yet connected to runtime model selection.
- Budget handling records/blocks after the deterministic mock response; a real
  provider should add pre-call estimation before external API calls.
- Tool retries/timeouts are not implemented yet.
- `/chat/query` is implemented in F011, but no critic or report generation is
  connected yet.

### F011: Chat Query API and Minimal Research UI

Status: complete.

Completed functionality:

- Added `POST /chat/query`.
- The endpoint auto-indexes embeddings for already ingested documents.
- The endpoint runs the local deterministic mock agent loop.
- The endpoint returns answer, evidence IDs, run ID, iteration count, token
  total, estimated cost, and error code.
- Added chat API tests for successful evidence retrieval, no-document response,
  and blank-query validation.
- Added a demo research file under `examples/research/`.
- Replaced the Research placeholder with a minimal working React UI:
  - local file path ingestion;
  - document list refresh;
  - question input;
  - `as_of_date` input;
  - answer, evidence IDs, run ID, iterations, tokens, and cost display.
- Added a small frontend API helper around `fetch`.
- Ignored local `.db` files created during local smoke testing.

Technology stack:

- FastAPI
- Pydantic request/response models
- SQLAlchemy session dependency
- local deterministic embeddings
- local deterministic mock model provider
- React
- TypeScript
- Vite
- lucide-react
- curl smoke tests

Interview questions:

- Why add `/chat/query` before the full Research/Critic workflow?
- Why does `/chat/query` auto-create embeddings for ingested documents?
- What does the chat response return, and why are run IDs important?
- How does the frontend call the FastAPI backend?
- Why is local file path ingestion different from browser file upload?
- What is still mocked in this workflow?

Foundational concepts:

- HTTP POST endpoint
- request/response schema
- API orchestration
- idempotent embedding indexing
- frontend API client
- local dev server
- CORS
- UI loading/error states

Verification:

- `.venv/bin/python -B -m pytest -p no:cacheprovider tests/test_chat_api.py`
  - 3 passed
- `.venv/bin/python -B -m pytest -p no:cacheprovider`
  - 38 passed
- `.venv/bin/ruff check .`
  - passed
- `npm run build --prefix frontend`
  - passed
- Local smoke checks:
  - `GET /health` returned ok.
  - frontend dev server returned Vite HTML.
  - `POST /documents/ingest` indexed
    `examples/research/gold_real_yields.md`.
  - `POST /chat/query` returned `status=complete`, `evidence_ids=[1]`, and
    a cited answer.

Known gaps:

- Browser file upload is not implemented yet; current UI uses local server file
  paths.
- The model is still deterministic mock logic, not Gemini/Claude/local vLLM.
- Evidence display now shows source filenames, not full page-level citation
  details.
- Evidence Critic is implemented in F013, but report generation is not
  connected yet.
- Browser screenshot validation was not run because Playwright is not installed
  in the current Node REPL environment.

### F012: Runtime Routing and Source Display Polish

Status: complete.

Completed functionality:

- Connected the existing sensitivity/capability `Router` to `AgentLoop`.
- Added a default local model profile for the deterministic mock provider.
- Agent runs now store an actual router-generated selected model and selection
  reason.
- Routing failure is persisted as `routing_failed` before any model/tool call.
- Added runtime routing tests for success and policy denial.
- Added local relevance filtering to the JSON-vector fallback tool so unrelated
  questions do not reuse the only indexed source.
- Added source display data to chat responses.
- Removed internal `[evidence:1]` labels from the answer text.
- Frontend now shows `Source: filename.md` instead of internal evidence IDs.
- Moved date filtering to the hidden Advanced section as `Evidence cutoff date`.

Technology stack:

- model routing policy
- model profiles
- sensitivity gate
- capability requirements
- FastAPI response models
- retrieval fallback filtering
- React/TypeScript UI state
- pytest
- Ruff
- Vite build

Interview questions:

- What does runtime model routing add beyond storing `selection_mode="auto"`?
- Why should routing fail before model calls?
- How does Argus prevent restricted data from reaching cloud models?
- Why did unrelated questions previously reuse the same answer?
- Why show source filenames instead of internal evidence IDs?
- Why keep evidence IDs internally if the UI only shows sources?

Foundational concepts:

- hard constraints vs optimization
- sensitivity-aware routing
- capability matching
- selected model trace
- source provenance
- retrieval relevance threshold
- internal IDs vs user-facing labels

Verification:

- `.venv/bin/python -B -m pytest -p no:cacheprovider tests/test_agent_loop.py`
  - 5 passed
- `.venv/bin/python -B -m pytest -p no:cacheprovider`
  - 41 passed
- `.venv/bin/ruff check .`
  - passed
- `npm run build --prefix frontend`
  - passed

Known gaps:

- Runtime routing currently has one concrete provider registered in the loop.
  A true multi-provider runtime still needs provider registry/adapter wiring.
- Budget handling still needs pre-call estimation for real external APIs.
- Relevance filtering is a conservative local fallback, not a real semantic
  reranker.
- The UI still shows source filename only, not page/section/excerpt details.

### F013: Local Evidence Critic

Status: complete.

Completed functionality:

- Added `investment_agent.research` package.
- Added rule-based `EvidenceCritic`.
- Critic passes explicit no-evidence answers without requiring sources.
- Critic fails substantive answers that have no source.
- Critic warns when answer/source word overlap is weak.
- `AgentEvidenceSource` now carries internal excerpts for critic checks.
- `/chat/query` now returns a `critic` object with status and findings.
- Frontend displays a compact `Review: passed/warning/failed` line.
- Added critic unit tests.
- Added chat API assertions for critic output.

Technology stack:

- Python dataclasses
- Protocol-based source contract
- rule-based evidence validation
- FastAPI response models
- React/TypeScript UI state
- pytest

Interview questions:

- Why add a critic after retrieval and answer generation?
- What does the local Evidence Critic check today?
- Why is a no-evidence answer allowed to pass?
- What is the difference between `missing_source` and `weak_source_overlap`?
- Why use a rule-based critic before an LLM critic?
- What are the limitations of word-overlap support checking?

Foundational concepts:

- evidence-grounded generation
- citation/source validation
- guardrails
- rule-based validation
- false positives and false negatives
- critic workflow

Verification:

- `.venv/bin/python -B -m pytest -p no:cacheprovider tests/test_critic.py tests/test_chat_api.py`
  - 8 passed
- `.venv/bin/python -B -m pytest -p no:cacheprovider`
  - 45 passed
- `.venv/bin/ruff check .`
  - passed
- `npm run build --prefix frontend`
  - passed

Known gaps:

- This is not an LLM critic; it cannot deeply verify semantic support.
- Structured claims are implemented in F014.
- Counter-evidence retrieval is not implemented yet.
- Report generation is not connected yet.

### F014: Structured Claims for Chat Answers

Status: complete.

Completed functionality:

- Added `ClaimGenerator`.
- Added `GeneratedClaim` schema with:
  - claim text;
  - evidence IDs;
  - evidence relations;
  - confidence;
  - source names.
- Added `ClaimCreate` repository payload.
- Persisted chat claims to the existing `claims` table.
- `/chat/query` now returns `claims`.
- Frontend shows a compact `Key claim` block under the answer.
- Cleaned generated claim text so Markdown headings and truncated tails are not
  shown as the claim.
- Reused the same cleaning path in the local deterministic mock provider so the
  main answer does not show Markdown headings or half sentences.
- Added claim generator unit tests.
- Added mock provider answer-cleaning test.
- Added chat API tests proving claims are returned and persisted.

Technology stack:

- Python dataclasses
- Protocol-based claim source contract
- SQLAlchemy ORM persistence
- `claims` table
- FastAPI response models
- React/TypeScript UI state
- pytest

Interview questions:

- Why convert an answer into structured claims?
- What is the relationship between a claim and evidence IDs?
- Why store `relations` such as `supports`?
- Why persist claims in the database instead of only returning text?
- Why is the current claim generator still limited?

Foundational concepts:

- claim extraction
- evidence relation
- structured output
- run-to-claim traceability
- report generation pipeline
- database persistence

Verification:

- `.venv/bin/python -B -m pytest -p no:cacheprovider tests/test_claims.py tests/test_mock_provider.py tests/test_chat_api.py`
  - 8 passed
- `.venv/bin/python -B -m pytest -p no:cacheprovider`
  - 49 passed
- `.venv/bin/ruff check .`
  - passed
- `npm run build --prefix frontend`
  - passed

Known gaps:

- The current generator creates one simple claim from the final answer.
- It does not yet split multi-claim reports into separate claim records.
- Claims are not yet attached to generated report sections.
- Counter-evidence relations are not implemented yet.

### F015: Report Generation and HTML Rendering

Status: complete.

Completed functionality:

- Added reusable `LocalResearchWorkflow` for local V1 research runs.
- Refactored chat API to share the same workflow used by reports.
- Added report JSON schema:
  - schema version;
  - topic and question;
  - run ID and run key;
  - answer;
  - structured claims;
  - evidence ledger entries;
  - report sections;
  - critic review;
  - run metrics.
- Added deterministic report builder for research briefs.
- Added required `Counter-Evidence and Gaps` report section.
- Rendered reports to escaped HTML.
- Persisted report JSON and rendered HTML in the existing `reports` table.
- Linked persisted report claims to `report_id` and `run_id`.
- Added FastAPI endpoints:
  - `POST /reports/generate`;
  - `GET /reports/{report_id}`;
  - `GET /reports/{report_id}/html`.
- Added Research page report generation controls and HTML report link.
- Added report API tests for persistence, HTML rendering, and missing reports.

Technology stack:

- FastAPI routers and `HTMLResponse`
- Pydantic request/response models
- SQLAlchemy ORM persistence
- Python dataclasses
- HTML escaping with Python standard library
- React/TypeScript UI state
- pytest

Interview questions:

- Why separate the local research workflow from the API route?
- What is the difference between chat output and report output?
- Why store both `report_json` and `rendered_html`?
- Why escape report HTML?
- Why include a `Counter-Evidence and Gaps` section even when no opposing
  evidence is found?
- How are report claims linked back to evidence and agent runs?

Foundational concepts:

- service/workflow layer
- JSON schema
- HTML rendering
- XSS prevention through escaping
- persistence model
- API resource endpoints
- traceability across runs, reports, claims, and evidence

Verification:

- `.venv/bin/python -B -m pytest -p no:cacheprovider tests/test_reports_api.py tests/test_chat_api.py`
  - 7 passed
- `.venv/bin/python -B -m pytest -p no:cacheprovider`
  - 52 passed
- `.venv/bin/ruff check .`
  - passed
- `npm run build --prefix frontend`
  - passed

Known gaps:

- The report is deterministic and template-based; it is not yet a rich LLM
  report writer.
- Counter-evidence retrieval is not implemented yet; the report currently marks
  this as a review gap.
- Report sections are generated from one local research answer, not a multi-step
  report planning workflow.
- HTML export exists; PDF export remains optional.

### F016: Portfolio Spreadsheet Import, Summary, and Profile

Status: complete.

Completed functionality:

- Added holdings CSV/XLSX/XLS parsers for:
  - symbol;
  - name;
  - asset class;
  - quantity;
  - price;
  - market value;
  - cost basis;
  - account.
- Added deterministic portfolio summary logic:
  - total portfolio value;
  - position weights;
  - asset-class allocation;
  - single-position concentration flags;
  - asset-class concentration flags;
  - scenario suggestions.
- Added active user profile persistence:
  - risk tolerance;
  - life stage;
  - investment horizon;
  - income stability;
  - liquidity needs;
  - preferred style;
  - target allocation.
- Added FastAPI endpoints:
  - `POST /portfolio/upload`;
  - `POST /portfolio/upload-file`;
  - `GET /portfolio/summary`;
  - `POST /profile`;
  - `GET /profile`.
- Added Portfolio page with browser file upload, summary cards, allocation,
  positions table, risk flags, and scenario cards. The original path endpoint
  remains for local scripts and backward compatibility.
- Added Profile page with risk/profile fields and target allocation inputs.
- Added sample holdings file at `examples/portfolio/holdings_sample.csv`.
- Added portfolio parser/math tests and API tests.

Technology stack:

- Python standard-library `csv`
- `openpyxl` for XLSX and `xlrd` for legacy XLS read-only parsing
- multipart browser upload with a 10 MB application limit
- FastAPI routers
- Pydantic validation
- SQLAlchemy ORM persistence
- Deterministic Python portfolio math
- React/TypeScript form state
- pytest

Interview questions:

- Why should portfolio math be deterministic instead of LLM-generated?
- How does the holdings CSV parser validate input?
- How are position weights and asset-class allocations calculated?
- What concentration thresholds does V1 use?
- How does the saved user profile affect scenario suggestions?
- Why does portfolio data stay local/restricted?

Foundational concepts:

- CSV parsing
- numeric validation
- weighted allocation
- concentration risk
- active profile pattern
- deterministic calculations
- local-only handling of restricted household data

Verification:

- `.venv/bin/python -B -m pytest -p no:cacheprovider tests/test_portfolio.py tests/test_portfolio_api.py`
  - 12 passed
- `.venv/bin/python -B -m pytest -p no:cacheprovider`
  - 118 passed
- `.venv/bin/ruff check .`
  - passed
- `npm run build --prefix frontend`
  - passed

Known gaps:

- Scenario suggestions are deterministic guardrails, not personalized financial
  advice.
- No tax-lot optimization or trading execution exists.
- Allocation chart is a structured list in V1; richer charts can be added later.

### F017: Runs and Cost Dashboard

Status: complete.

Completed functionality:

- Added read-only run observability API:
  - `GET /runs`;
  - `GET /runs/{run_id}`.
- Added run dashboard metrics:
  - total runs;
  - total token estimate;
  - total estimated cost;
  - non-complete runs;
  - model call count;
  - tool call count.
- Added model breakdown by provider, model, and deployment.
- Added recent runs table with objective, status, selected model, tokens, and
  trace action.
- Added run detail response with:
  - model calls;
  - prompt/completion/total tokens;
  - estimated cost;
  - serving engine;
  - tool calls;
  - tool arguments;
  - latency;
  - model-selection reason.
- Added Runs frontend page with summary cards, model breakdown, recent runs, and
  trace view.
- Added Runs API tests for zero state, populated dashboard, run detail, and 404.

Technology stack:

- FastAPI routers
- Pydantic response models
- SQLAlchemy read queries
- React/TypeScript dashboard UI
- persisted `agent_runs`, `model_calls`, and `tool_calls`
- pytest

Interview questions:

- Why persist agent runs, model calls, and tool calls?
- What does a Runs and Cost dashboard prove?
- How does the dashboard support model routing and cost control?
- What is the difference between estimated cost and actual billing?
- How can tool traces help debug agent behavior?
- Why keep this as read-only observability first?

Foundational concepts:

- observability
- audit trail
- run trace
- model-call telemetry
- tool-call telemetry
- cost attribution
- routing rationale

Verification:

- `.venv/bin/python -B -m pytest -p no:cacheprovider tests/test_runs_api.py`
  - 3 passed
- `.venv/bin/python -B -m pytest -p no:cacheprovider`
  - 60 passed
- `.venv/bin/ruff check .`
  - passed
- `npm run build --prefix frontend`
  - passed

Known gaps:

- The model selector is visible but not yet user-switchable from the UI.
- Eval summary is not connected to the Runs page yet.
- Costs are estimated from provider responses; current local mock cost is zero.
- No external provider API has been connected yet.

### F018: Data-Backed Report Charts

Status: complete.

Completed functionality:

- Added `report_json.charts` to generated research reports.
- Extracted cited percent indicators from local evidence into bar-chart data.
- Extracted cited dollar indicators and normalized K/M/B values to USD millions.
- Rendered a `Data Analysis` chart section in HTML reports.
- Updated the Research page report summary to show chart count.
- Added numeric indicators to the local gold research demo fixture.

Technology stack:

- Python deterministic parsing
- FastAPI report API
- structured JSON report schema
- HTML/CSS report rendering
- React/TypeScript report summary UI
- pytest

Interview questions:

- Why should report charts be data-backed instead of decorative?
- Why store chart data in JSON before rendering HTML?
- Why does charting not require an LLM API?
- What is the difference between local cited indicators and live market data?
- What are the limits of regex-based numeric extraction?

Foundational concepts:

- structured report artifacts
- deterministic extraction
- data provenance
- chart rendering
- source-backed metrics
- local evidence versus live market feeds

Verification:

- `.venv/bin/python -B -m pytest -p no:cacheprovider tests/test_reports_api.py`
  - 3 passed
- `.venv/bin/python -B -m pytest -p no:cacheprovider`
  - 62 passed
- `.venv/bin/ruff check .`
  - passed
- `npm run build --prefix frontend`
  - passed

Known gaps:

- V1 charts extract common percent and dollar indicators only.
- Complex tables, valuation comps, and live prices require stronger structured
  data ingestion or a market-data connector.
- Chart labels are deterministic best-effort labels from nearby source text.

### F019: Structured Research CSV Trend Charts

Status: complete.

Completed functionality:

- Added `.csv` support to local research ingestion.
- Validated CSV header rows and non-empty data rows.
- Stored research dataset metadata:
  - columns;
  - column count;
  - row count.
- Added CSV demo fixture for gold macro indicators.
- Parsed cited CSV evidence into structured report chart schemas.
- Rendered SVG line charts for percent trends in generated HTML reports.
- Rendered SVG time-series bar charts for currency/flow metrics in generated
  HTML reports.

Technology stack:

- Python `csv` module
- FastAPI document ingestion API
- deterministic dataset parsing
- structured report JSON
- HTML/SVG chart rendering
- pytest
- Ruff

Interview questions:

- Why did report charts need structured CSV data?
- How is Research CSV different from Portfolio holdings CSV?
- Why generate chart data in the backend instead of the frontend?
- Why use SVG in generated HTML reports?
- Why should LLMs explain charts but not invent chart values?

Foundational concepts:

- structured data versus unstructured prose
- time-series data
- x-axis and numeric series
- line chart versus bar chart
- SVG rendering
- deterministic parsing
- data provenance

Verification:

- `.venv/bin/python -B -m pytest -p no:cacheprovider tests/test_ingestion.py tests/test_documents_api.py tests/test_reports_api.py`
  - 15 passed
- `.venv/bin/python -B -m pytest -p no:cacheprovider`
  - 65 passed
- `.venv/bin/ruff check src/investment_agent/research/reports.py src/investment_agent/ingestion/local_files.py tests/test_ingestion.py tests/test_documents_api.py tests/test_reports_api.py`
  - passed
- `.venv/bin/ruff check .`
  - passed
- `npm run build --prefix frontend`
  - passed
- Browser check on `/reports/11/html`
  - 4 chart cards;
  - 2 SVG charts;
  - 3 line-series polylines;
  - 5 time-series bars.

Known gaps:

- CSV parsing is intentionally simple and expects clean rectangular datasets.
- The chart engine supports basic percent trends and currency/flow bars, not
  advanced financial statement tables or valuation comps.
- Live market data still requires a later market-data connector.

### F020: V1 Demo Polish and Browser Upload

Status: complete.

Completed functionality:

- Added browser file upload endpoint:
  - `POST /documents/upload`;
  - accepts raw file bytes with `X-Argus-Filename`;
  - saves files under `data/uploads/`;
  - reuses the existing local ingestion pipeline.
- Added Research page browser upload control for Markdown, text, simple PDF,
  and research CSV files.
- Added citations panel with evidence IDs, source type, source name, and
  section/page metadata.
- Added critic panel with validation status and critic findings.
- Added committed sample HTML report artifact.
- Added README local demo flow, limitations, and resume-safe notes.
- Added final resume-safe bullets in `docs/RESUME_BULLETS.md`.

Technology stack:

- FastAPI raw request body handling
- local filesystem upload staging
- React/TypeScript file input
- evidence-ledger UI
- critic-result UI
- static HTML report artifact
- Markdown documentation

Interview questions:

- Why add browser upload on top of local file path ingestion?
- Why store uploaded files under a Git-ignored directory?
- How does the citations panel support RAG auditability?
- What is the difference between citations and critic validation?
- Why is V1 local-demo ready but not production-ready?

Foundational concepts:

- browser file upload
- request body bytes
- local staging directory
- evidence traceability
- validation surface
- demo artifact
- implementation claims versus roadmap claims

Verification:

- `.venv/bin/python -B -m pytest -p no:cacheprovider tests/test_documents_api.py`
  - 7 passed
- `npm run build --prefix frontend`
  - passed
- `.venv/bin/python -B -m pytest -p no:cacheprovider`
  - 67 passed
- `.venv/bin/ruff check .`
  - passed
- Browser DOM check
  - Research page renders browser file upload, local path ingestion, Ask, and
    Generate report controls.
- Local API check
  - `/chat/query` returns sources, claims, and critic output for citation and
    critic panels.

Known gaps:

- Browser upload is local-only and writes to `data/uploads/`.
- Manual model override, pgvector hardening, cloud deployment, live market data,
  and production observability remain V1.1/V2 work.

## Daily Execution Plan

### Day 1: Phase 1 Dependency Validation

Learning:

- Python package extras
- SQLAlchemy install/runtime dependency boundary
- Alembic command flow

Project:

- Install `.[dev,storage]` in a virtual environment.
- Run full pytest including storage tests.
- Run Alembic upgrade against local PostgreSQL when Docker is available.

Acceptance:

- No skipped storage tests.
- Migration creates all V1 tables.

### Day 2: Local File Ingestion Start

Learning:

- File parsing
- Metadata normalization
- Content hashing

Project:

- Implement `.txt` ingestion.
- Implement `.md` ingestion.
- Create document/evidence/chunk rows.

Acceptance:

- Ingesting a text fixture writes rows through the repository.

### Day 3: Chunking and Idempotency

Learning:

- Chunk size
- Chunk overlap
- Idempotency

Project:

- Implement chunking function.
- Detect re-ingestion by content hash.
- Add tests for deterministic chunks.

Acceptance:

- Same file does not create duplicate document content unexpectedly.

### Day 4: Simple PDF Ingestion

Learning:

- PDF text extraction limits
- Why table extraction is hard

Project:

- Add simple text PDF extraction.
- Store page/section metadata when available.

Acceptance:

- Simple PDF fixture can be ingested.

### Day 5: Embedding Provider Abstraction

Learning:

- Embeddings
- Vector similarity
- Provider abstraction

Project:

- Add embedding provider interface.
- Add deterministic local/mock embedding provider.

Acceptance:

- Chunks can receive stable test vectors without cloud APIs.

### Day 6: pgvector Retrieval Path

Learning:

- Vector search
- top-k retrieval
- metadata filters

Project:

- Store and retrieve embeddings.
- Return evidence snippets and IDs.

Acceptance:

- Query retrieves relevant fixture chunks.

### Day 7: Temporal Filtering

Learning:

- `as_of_date`
- future-leak prevention

Project:

- Add publication/data-as-of filters.
- Seed future-dated evidence fixture.

Acceptance:

- Future evidence is excluded in tests.

### Day 8: Tool Registry

Learning:

- Learn Claude Code s01/s02
- Tool call contracts

Project:

- Implement tool registry.
- Register `retrieve_evidence`.

Acceptance:

- Unknown tools fail explicitly.

### Day 9: Mock Agent Loop

Learning:

- Agent loop
- max iterations

Project:

- Mock model calls retrieval tool.
- Tool result returns to loop.

Acceptance:

- Mock agent produces cited answer.

### Day 10: Auto Model Routing and Cost

Learning:

- Sensitivity gate
- Capability filter
- Cost/latency tradeoff

Project:

- Connect router to runtime.
- Store selection reason and model calls.

Acceptance:

- Restricted data cannot select cloud profile.

### Day 11: Self-Hosted Model Provider Adapter

Learning:

- Model serving
- OpenAI-compatible endpoints
- vLLM/Truss concepts

Project:

- Add self-hosted provider config.
- Record deployment and serving engine in `model_calls`.

Acceptance:

- Mocked self-hosted endpoint path records latency/cost fields.

### Day 12: Research/Critic Workflow

Learning:

- Critic as independent check
- Citation validation

Project:

- Add Research/Critic workflow.
- Flag missing citation.

Acceptance:

- Seeded unsupported claim is downgraded or flagged.

### Day 13: Report Rendering

Learning:

- Structured report schema
- HTML rendering

Project:

- Generate and store HTML report.

Acceptance:

- Browser can view report HTML.

### Day 14: Portfolio CSV

Learning:

- Deterministic finance calculations
- CSV parsing

Project:

- Upload/parse holdings CSV.
- Compute allocation and concentration.

Acceptance:

- Known fixture math passes.

### Day 15: Profile and Scenarios

Learning:

- Decision support vs financial advice

Project:

- Store user profile.
- Generate bounded scenario suggestions.

Acceptance:

- Scenario wording stays manual-confirmation oriented.

### Day 16: Frontend Research Page

Learning:

- API client
- loading/error states

Project:

- Upload/query/report UI.

Acceptance:

- Research workflow works through browser.

### Day 17: Frontend Portfolio/Profile

Learning:

- Table UI
- form state

Project:

- Portfolio and Profile pages.

Acceptance:

- CSV upload and profile save work through browser.

### Day 18: Runs/Cost and Eval

Learning:

- Observability
- golden-question evaluation

Project:

- Runs/Cost page.
- Eval runner output.

Acceptance:

- Tokens, cost, model calls, tool calls, and eval metrics are visible.

### Day 19: Cloud Deployment Minimum

Learning:

- Docker image
- cloud service environment variables
- managed database tradeoffs

Project:

- Deploy minimal frontend/backend if local V1 is stable.
- Keep database strategy conservative.

Acceptance:

- Hosted demo or documented deployment runbook exists.

### Day 20: Demo Polish and Resume

Learning:

- Interview narrative
- limitations section

Project:

- Add fixtures, sample report, screenshots, README demo flow.
- Finalize resume bullets using implemented features only.

Acceptance:

- Clean demo path and interview answer sheet are ready.

### 2026-07-21: Read-only market Heatmap checkpoint

- Audited the live Robinhood historicals input Schema and kept the capability behind an explicit
  read-only Sidecar flag.
- Normalized completed daily volumes, excluded current/interpolated bars, and implemented a
  60-session robust log-MAD activity score with a 20-session quality floor.
- Added a fixed-size industry matrix with independent channels for daily return, volume activity,
  exact ETF holdings, related stocks, and deterministic ETF research roles.
- Added formula-level drill-down and independent Heatmap/historicals rollback switches.
- Validated the projector against a real read-only SPY historical response without placing or
  reviewing any order.

### 2026-07-21: Unified ETF Universe checkpoint

- Replaced duplicate full-universe presentation with one feature-flagged ETF Universe and explicit
  Market/Research view buttons while retaining the evidence-backed shortlist above it.
- Unified fund metadata, market quote, active holdings relationship, and current validated
  recommendation role into a single frontend view model without merging their semantics.
- Expanded the shared ETF modal with market data, plain-language Volume activity thresholds and
  limitations, related holdings, current recommendation identity, issuer, and verified source.
- Preserved the prior Heatmap plus candidate directory behind
  `ARGUS_ENABLE_UNIFIED_ETF_UNIVERSE=false` for migration-free rollback.
