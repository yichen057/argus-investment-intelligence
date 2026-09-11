# Portfolio Decision Contract

This document preserves the detailed deterministic portfolio and money-planning
contract. The root README contains only a user-facing summary.


Argus treats target allocation as the policy and the dated holdings file as the
calculation snapshot:

```text
target value = total portfolio value * target weight
drift amount = current asset-class value - target value
estimated shares = executable dollar amount / dated reference price
```

When no Profile target exists, the UI may show a 20% concentration review
line. That line is explicitly labeled as an **example review level, not the
user's personal target**. It cannot silently become a trade instruction. The
policy signal, asset role, checks-before-acting, dollar math, and share
estimates come from deterministic Python rules rather than Gemini, so the same
holdings and Profile settings produce the same result. The optional AI market
panel provides cited time-sensitive context but cannot modify these numbers.

The **Invest Suggestions** workspace compares three concrete scenarios side by side:

1. maintain the uploaded allocation with no trade;
2. dilute concentration with new contributions;
3. partially sell an overweight holding and reallocate the proceeds.

Each scenario returns its rebalancing amount, projected total, post-action
asset-class weights, trade amounts, estimated shares when a dated quote exists,
and known limitations. Investment targets cover U.S. equity, international
equity, bond, commodity/gold, and alternatives. Cash is deliberately excluded
from this 100% investment mix. Symbol-aware normalization keeps
GLD and VXUS from being misclassified by a generic spreadsheet label.

The Profile **Allocation guide** provides an unsaved, editable starting mix.
Its deterministic policy uses risk tolerance, future investment horizon, life
stage, investing experience, income stability, liquidity needs, investment
style, recurring net income, and planned monthly contribution. Experience is
used for implementation simplicity and education prompts, while horizon remains
the future time until the money is needed. It never asks Gemini to invent
percentages. The guide keeps Alternatives at 0% unless the user opts in and all
percentage inputs support one decimal place. Its risk-based example policy uses
5%, 7.5%, or 10% Commodity / Gold and clearly distinguishes those Argus values
from the World Gold Council's tested hypothetical allocations.

The institutional references shown in the guide support the decision factors
and asset definitions, not the exact percentages. The numerical 40%/60%/80%
stock starting points and subsequent adjustments are an explicit Argus example
policy. Savings deposits, CDs, Treasury bills, money-market cash equivalents,
and brokerage cash may be entered as current cash savings for goal planning.
The separate short-term cash plan allocates current savings in priority order to
emergency, education, and selected dated expense goals, then calculates each gap and
whole-dollar minimum monthly saving. Its Alternatives field can cover investment real
estate/REITs, private investments, complex strategies, or crypto, while a
personal-use primary home is normally excluded from the investable portfolio.

Portfolio quotes use a provider-neutral contract. External quote access is off by
default, so uploaded prices are labeled **Not live** and daily change, volume,
dollar volume, and volume Z-score remain unavailable. `ARGUS_MARKET_DATA_PROVIDER`
accepts `01` Robinhood, `02` Twelve Data, `03` Alpha Vantage, or `04` Massive, but
only an explicitly connected adapter is called; Argus never silently spends through
another external provider. The phase-one Robinhood boundary allowlists only positions and
quotes. Historical prices remain disabled until their live MCP Schema is reviewed and pinned.
The three independent REST transports remain implementation work.

A Robinhood-only file cannot reveal bank balances; users seeking a total-investable-
asset view must add the bank cash/CD positions to the holdings file. Risk flags
use transparent built-in concentration screens: 25% for one position and 70%
for one asset class, calculated against invested holdings with cash excluded.
The API and UI expose the current weight, threshold, and percentage-point excess.
These screens are separate from the saved Profile rebalance-drift threshold;
they are not regulatory limits, personal targets, or automatic sale instructions.

The engine supports the three common rebalance paths described by
[Investor.gov](https://www.investor.gov/additional-resources/general-resources/publications-research/info-sheets/beginners-guide-asset):
sell overweight assets, add money to underweight assets, or direct recurring
contributions toward underweight assets. Its DCA label follows the
[Investor.gov definition](https://www.investor.gov/introduction-investing/investing-basics/glossary/dollar-cost-averaging):
equal-dollar investing at regular intervals rather than a promise of better
returns. The UI also labels this as `定期定额投资 / 定投计划` for clarity.

ETF candidates are role-based examples, not auto-approved trades. Their links
go to first-party issuer product pages so the user can verify the
fund objective and concentration. Broad core candidates are ranked ahead of
satellite exposures; QQQ is labeled as a growth satellite. Individual-stock
candidates require separate, cited Argus research and position sizing.
Portfolio also exposes State Street and Vanguard peers for all eleven GICS sectors,
State Street industry funds, and iShares SOXX in a 41-fund controlled research library.
Direct-stock holdings are marked as related sector/industry exposure without being
misrepresented as ETF ownership. These are narrow satellite candidates and are excluded
from automatic core gap filling. The cited AI market
analysis may place at most three on a research watchlist with a bull case, counter-
evidence, invalidation signal, overlap warning, and typed DCA-suitability result; it
never places a trade. A sector/industry DCA amount exists only when the user has saved
a capped satellite budget inside the total monthly investment, and deterministic code
allocates that budget among validated DCA-suitable candidates.

By default, ETF selection uses the versioned deterministic pipeline
`hard eligibility -> Profile/holdings fit -> timestamped market signal -> evidence
quality -> overlap/concentration/expense/liquidity penalties -> fixed ranking`.
The selected answer model explains that closed list and cannot add, remove, replace,
or reorder symbols. A separately versioned code Auditor verifies the structured
invariants before synthesis. `ARGUS_ETF_SELECTION_ENGINE=model` is an explicit legacy
rollback/A-B mode; it removes the score threshold but still enforces the controlled
universe, citation, maximum-count, holdings-mode, and DCA safety validators. Argus never
switches between these engines silently inside a request.

The market-context slice uses the same independent-search boundary as Research:
Exa retrieves source-linked, time-stamped evidence; the Evidence Gate validates
it; and the manually selected Gemini, DeepSeek, or Kimi model organizes the
separately labeled `AI market analysis`. Argus sends only up to 12 symbols, asset
classes, weights, and the holdings date—not account names or dollar values.
Portfolio runs two bounded Exa facets—current drivers, then sector leadership and
independent counter-evidence plus bounded same-exposure ETF peer comparison. The second
request uses Exa `excludeDomains` to avoid
domains returned by the first request when possible. Two accepted domains are preferred,
not a hard availability gate: if only one domain passes, Argus calls the explicitly
selected model with a visible limited-source warning and prohibits a claim of
comprehensiveness. The UI shows source/domain counts and Exa search cost separately
from model-token cost. If the first synthesis draft fails citation-ID validation,
Argus permits exactly one repair call to the same selected model, exposes an answer-call
count and combined model cost, and still rejects a second invalid draft. Market synthesis
is capped at 1,600 output tokens and instructed to finish within 900 words. The analysis
cannot change deterministic targets, amounts, shares, or projected weights. A
time-versioned ETF catalog, licensed quote adapters, richer numeric market snapshots,
and numeric-output validation remain the next-stage design documented in
[ETF Candidate and Market Data Architecture](ETF_MARKET_DATA_ARCHITECTURE.md).

Cash-planning fields display real-time thousands separators such as `125,000` while
the user types. Monthly spending is normalized as recurring spending plus predictable
annual bills divided by 12. Emergency and education goals can be disabled.
Short-term one-time goals are selected from medical/dental, home/appliance,
vehicle, travel, tuition, insurance/tax, family support, and major-purchase
presets. Each selection can record an estimate, months-until-needed, and priority;
an unestimated selection remains a warning and is not silently assigned a number.
These goals reduce current investable capacity and remain separate from retirement
planning. Profile records a default planning-through age of 100, desired monthly
retirement spending in today's dollars, and expected reliable Social Security/pension
income. Traditional, Roth, taxable, or mixed Traditional + Roth tax treatment can be
selected; mixed plans record the estimated pre-tax withdrawal share. Portfolio calculates
the real-dollar present value of the retirement spending gap, projects current uploaded
non-cash investments to retirement, and back-solves the equal monthly investment needed
from now using the entered nominal return and inflation assumptions. Blank relevant tax
rates produce a prominent tax-excluded baseline. The result warns that taxes, fees, health-care shocks,
and sequence risk require a deeper plan; it never treats lifetime retirement spending
as idle cash. Portfolio also compares the current cash goals' minimum monthly
saving with `net income - normalized spending - planned investing` and reports a
shortfall plus a deterministic adjustment order. Current employer or salary
recommendations require a separate, cited labor-market research flow with the
user's skills, location, and constraints; the portfolio model does not guess them.

ChatGPT-connected app data is not automatically an Argus data source. A connection
authorized inside ChatGPT is scoped to the app, account permissions, and supported
ChatGPT surface; it does not give this local service a reusable bank token or API.
Argus currently accepts user-selected portfolio files. A future banking workflow
must use either an explicit transaction export (CSV/OFX) or a separately authorized,
read-only bank-data provider integration with consent, revocation, least-privilege
scopes, encrypted secrets, and an audit trail.

Portfolio presents cash goals, DCA, and concentration flags as compact metrics
and tables. Longer methodology, warnings, and next steps are available through
expandable details so the primary decision numbers remain scannable.

Kimi is a metered API, not an automatically funded free tier. A valid API key can
list models while generation still returns HTTP 429 when cash/voucher balance is
zero, a project budget is exhausted, or RPM/TPM/concurrency limits are reached.
Argus distinguishes those Kimi errors from Gemini quota resets and never claims a
cost for a rejected request.
