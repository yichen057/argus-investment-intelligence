# Argus Local Operations Runbook / 本地运行维护手册

This runbook records the repeatable operations needed to maintain the local Docker
Compose version of Argus. AWS/EKS operations remain in `docs/CLOUD_RUNBOOK.md`.

本文档记录 Argus 本地 Docker Compose 版本的日常维护操作。AWS/EKS 上云流程仍在
`docs/CLOUD_RUNBOOK.md`，不要把本地环境变量操作和云资源操作混在一起。

## 1. Project location / 项目位置

Run local maintenance commands from the repository root:

```bash
cd /path/to/argus
```

The important configuration files are:

| File | Purpose / 用途 |
|---|---|
| `.env` | Local effective configuration and API keys. Hidden, Git-ignored, and never committed. / 本地真正生效的配置与 Key。隐藏、忽略提交。 |
| `.env.example` | Safe committed template showing supported variable names and defaults. It is not loaded automatically. / 可提交的配置示例，不会自动生效。 |
| `compose.yaml` | Passes `.env` values into Docker services and defines fallback defaults. / 将 `.env` 传入容器并声明默认值。 |

The base `compose.yaml` defines exactly three services: `postgres`, `backend`, and
`frontend`. It does **not** define a separate `worker` service. `worker` exists only when
the V2 overlay (`compose.v2.yaml`) or Kubernetes deployment is used. For ordinary local
`.env` changes, run only:

```bash
docker compose up -d --force-recreate backend
```

基础 `compose.yaml` 只有 `postgres`、`backend` 和 `frontend` 三个服务，没有独立的
`worker`。`worker` 只存在于 V2 Compose overlay 或 Kubernetes 部署中。因此，本地修改
`.env` 后不要在命令末尾添加 `worker`。

Show hidden files in Finder with `Command + Shift + .`, or open the effective file from
Terminal:

```bash
open -a TextEdit .env
```

Do not copy `.env.example` over an existing `.env`, because that can erase real local API
keys.

## 2. When is a browser refresh enough? / 什么时候直接刷新即可？

The local Compose setup bind-mounts `./frontend` and `./src`. Vite watches frontend files,
and Uvicorn runs with `--reload` for Python source changes.

| Change | Required operation |
|---|---|
| React/CSS text or layout | Usually automatic; otherwise refresh or use `Command + Shift + R`. |
| Python code under `src/` | Wait for Uvicorn reload, then refresh the page. |
| Backend `.env` or Compose `environment` value | Run `docker compose up -d --force-recreate backend`; browser refresh alone is insufficient. |
| Python/Node dependency, Dockerfile, or image build input | Run `docker compose up -d --build`. |
| Database migration | Recreate/start backend; its startup command runs `alembic upgrade head`. Verify the logs. |

Source-code changes normally reload automatically. Environment variables are copied into
a container when it is created, so changing `.env` requires container recreation.

### Local URLs are not public links / 本地网址不能直接分享

`http://localhost:5173` and `http://127.0.0.1:5173` always mean "this computer."
Sending either URL to another person makes their browser look for Argus on their own
computer, not on this Mac. They can either clone the repository and run their own local
copy, or use a properly deployed environment with authentication, TLS, and user-data
isolation. Do not expose the current local development build with a public tunnel.

### Local test suite / 本地测试集

The test-suite control is intentionally not shown on the user-facing Runs page: running
tests and refreshing saved Runs are different actions, and the test control was easy to
misread or trigger accidentally. The backend capability remains available to developers.
It executes the deterministic cases in `evals/golden_questions.yaml` without paid model
APIs. For a non-polluting maintenance check, use a temporary SQLite database:

```bash
docker compose exec -T \
  -e ARGUS_DATABASE_URL=sqlite:////tmp/argus-eval-smoke.db \
  backend python -m investment_agent.evaluation.cli --no-save
```

If the command reports a missing local test input, recreate the backend so the `evals/` and
`examples/` mounts from `compose.yaml` are applied:

```bash
docker compose up -d --force-recreate backend
```

## 3. ETF selection-engine switch / ETF 候选引擎开关

Argus supports two explicit backend modes:

```dotenv
# Default: fixed eligibility, scoring, ranking, and independent audit.
ARGUS_ETF_SELECTION_ENGINE=deterministic

# Legacy rollback/A-B mode: the selected model proposes candidates.
ARGUS_ETF_SELECTION_ENGINE=model
```

`deterministic` is the default even if the line is absent from `.env`. `model` removes
the deterministic minimum-score requirement, but it does not remove the controlled ETF
universe, citation allowlist, three-candidate maximum, holdings-mode validation, or DCA
safety rules. Argus never switches modes silently inside one request.

### Switch to legacy model-candidate mode / 回退到模型候选模式

1. Open the project-root `.env` and set:

   ```dotenv
   ARGUS_ETF_SELECTION_ENGINE=model
   ```

2. Recreate only the backend container:

   ```bash
   cd /path/to/argus
   docker compose up -d --force-recreate backend
   ```

3. Verify the effective application setting:

   ```bash
   docker compose exec backend python -c 'from investment_agent.config import get_settings; print(get_settings().etf_selection_engine)'
   ```

   Expected output: `model`.

4. Refresh `http://localhost:5173/`, generate a new Portfolio market analysis, and open
   its Runs audit. The Run should say `selection_engine=model` and disclose the legacy
   rollback limitation.

### Restore deterministic mode / 恢复固定评分模式

Change `.env` back to:

```dotenv
ARGUS_ETF_SELECTION_ENGINE=deterministic
```

Then recreate and verify the backend:

```bash
cd /path/to/argus
docker compose up -d --force-recreate backend
docker compose exec backend python -c 'from investment_agent.config import get_settings; print(get_settings().etf_selection_engine)'
```

Expected output: `deterministic`.

## 4. Why `restart` is not enough / 为什么不能只执行 restart？

`docker compose restart backend` restarts the existing container with the environment
captured when that container was created. It does not reliably apply a newly edited
`.env`. Use this for environment changes:

```bash
docker compose up -d --force-recreate backend
```

`--build` is unnecessary for an environment-only change. Use it when dependencies,
Dockerfiles, or non-mounted image contents changed:

```bash
docker compose up -d --build backend
```

## 5. Verification and troubleshooting / 验证与排错

Check service status and recent backend output:

```bash
docker compose ps
docker compose logs --tail=80 backend
```

Check the resolved Compose value without printing unrelated secrets:

```bash
docker compose config | rg 'ARGUS_ETF_SELECTION_ENGINE'
```

Expected default: `ARGUS_ETF_SELECTION_ENGINE: deterministic`.

If the page still looks old:

1. Confirm `backend` and `frontend` are running with `docker compose ps`.
2. Check backend reload/startup errors with `docker compose logs --tail=80 backend`.
3. Use `Command + Shift + R` in the browser.
4. Generate a new market-analysis Run. Historical Runs preserve the engine used at their
   original execution time and do not change when the configuration changes.

Never paste the full `.env`, API keys, or unrestricted `docker compose config` output into
an issue, interview document, or Git commit.

## 6. Market-data source and privacy switch / 行情来源与隐私开关

The safe local default is:

```dotenv
ARGUS_ENABLE_EXTERNAL_MARKET_DATA=false
ARGUS_ENABLE_ROBINHOOD=false
ARGUS_MARKET_DATA_PROVIDER=01
```

Provider codes are `01` Robinhood, `02` Twelve Data, `03` Alpha Vantage, and `04`
Massive. Codes 02–04 reserve stable configuration slots; their REST transports are not
yet implemented. Selecting one does not make Argus call it and does not trigger a hidden
fallback. With external access disabled or disconnected, `/portfolio/market-map` uses
only the uploaded holding price and reports `Not live`.

After editing `.env`, recreate the backend and verify the effective configuration:

```bash
cd /path/to/argus
docker compose up -d --force-recreate backend
curl -s http://localhost:8000/health
curl -s http://localhost:8000/portfolio/market-map
```

The Robinhood sync endpoint is `POST /portfolio/sync-robinhood`. It succeeds only when both
switches are true and the local Argus Sidecar has completed OAuth, passed the live capability
fingerprint check, and is running. The browser performs the read only when the user clicks
**Refresh positions**; Argus never refreshes in the background. Never paste a brokerage
password, session cookie, OAuth callback/code, or Robinhood token into a model prompt, `.env`,
the Argus database, or a Git-tracked file.

### 6.1 Robinhood Trading MCP: official endpoint and terminology / 官方入口与术语

Robinhood operates a remote **Streamable HTTP MCP Server** at:

```text
https://agent.robinhood.com/mcp/trading
```

There is no Robinhood server package to start inside this repository. In MCP terms:

- **Host / 宿主:** Codex, Claude, ChatGPT, Cursor, or the Argus local Sidecar;
- **Client / 客户端:** the MCP connection component inside that host;
- **Server / 服务端:** Robinhood's remote Trading MCP endpoint.

Robinhood currently documents these host setup paths:

| Host | Official connection path |
|---|---|
| Codex desktop | **Settings → MCP servers → Streamable HTTP**, then add the URL above |
| Codex CLI | `codex mcp add robinhood-trading --url https://agent.robinhood.com/mcp/trading`, then use `/mcp` |
| Claude Code | `claude mcp add robinhood-trading --transport http https://agent.robinhood.com/mcp/trading`, then use `/mcp` |
| Claude Desktop | **Settings → Connectors → Add custom connector** |
| ChatGPT | Enable Developer Mode, then **Settings → Apps → Create app** |
| Cursor | **Settings → Tools & MCPs → Connect** |
| Other MCP hosts | Add the same Streamable HTTP endpoint using that host's documented custom-MCP flow |

Official references:

- <https://robinhood.com/us/en/support/articles/agentic-trading-overview/>
- <https://robinhood.com/us/en/support/articles/trading-with-your-agent/>

An authorization completed in Codex, ChatGPT, or Claude belongs to that host. The local Argus
backend cannot reuse another application's private MCP session. Connecting Codex is useful for
capability discovery, but end-to-end Argus sync still requires the approved local
`argus-robinhood-sidecar` or an equivalent Argus-owned MCP client boundary.

### 6.2 Authorization risk and the meaning of "strictly read-only" / 授权风险与只读含义

Robinhood's public documentation says a connected agent can read all Robinhood accounts,
account numbers, positions, balances, transactions, order history, watchlists, and scans. It
also exposes order-placement tools for the separate Agentic account. The public documentation
does not currently describe a server-issued read-only OAuth scope.

Therefore, use precise language:

- **Argus behavior is strictly read-only:** its compiled policy may call only approved read
  wrappers and must never expose a generic model-selected brokerage tool call.
- **The underlying Robinhood connection is not proven to be a read-only token:** a stolen or
  incorrectly used connection could have broader server capabilities.

The local sidecar must enforce defense in depth:

1. Keep the Robinhood session in the sidecar or OS credential store, never `.env` or the Argus
   database.
2. Discover tools after authentication and compare their names and input schemas with approved
   fingerprints.
3. Expose typed methods such as `read_positions()` and `read_quotes()` to Argus; do not expose
   a generic `call_tool(name, arguments)` boundary to business code or an LLM.
4. Validate the exact tool name again at the transport boundary.
5. Project responses into approved DTO fields and drop account numbers, cookies, tokens, and
   unrelated transaction data before returning anything to Argus.
6. Record only correlation ID, tool name, timestamps, status, duration, accepted/rejected counts,
   and a safe error category.
7. Fail closed when a tool is missing, its schema changes, a source timestamp is absent, or a
   response is partial.

Do not assume that leaving an Agentic account unfunded creates a complete security boundary. It
may reduce trade exposure, but it does not reduce the documented read access to the user's other
Robinhood data.

### 6.3 Approved capability matrix / Argus 允许的工具范围

The official support page confirms the following tool names and descriptions. It does not
publish their complete MCP input/output JSON schemas; those must be captured from `list_tools`
after the user authorizes a connection.

**Initial allowlist / 第一阶段允许：**

| Tool | Argus purpose | Rule |
|---|---|---|
| `get_equity_positions` | Import open equity/ETF quantities and cost basis | Allow only through `read_positions()` after schema validation |
| `get_equity_quotes` | Retrieve real-time quote and prior close for at most 20 symbols | Allow only through `read_quotes(symbols)` with bounded, validated symbols |

**Review later / 完成 Schema 与隐私审核后再考虑：**

| Tool | Possible purpose | Current decision |
|---|---|---|
| `get_equity_historicals` | OHLCV, trend charts, volume Z-score | Deny until the Heatmap historical-cache phase |
| `get_equity_fundamentals` | Valuation, market cap, 52-week range, dividend facts | Deny until field and ETF coverage are verified |
| `get_portfolio` | Total value, asset-class totals, buying power | Deny initially because positions can be aggregated locally and this response is broader |
| `get_indexes`, `get_index_quotes`, `search` | Index context and ticker resolution | Deny initially; not required for holdings sync |

**Always denied / 永久禁止进入 Argus Brokerage adapter：**

- `review_equity_order`, `place_equity_order`, `cancel_equity_order`;
- all option order, position, quote, chain, and access-upgrade tools;
- all watchlist create/update/follow/add/remove tools;
- all scan create/update/run tools;
- `get_accounts`, `get_realized_pnl`, `get_pnl_trade_history`, `get_equity_orders`;
- any future transfer, banking, margin, crypto-trading, or account-setting mutation;
- every unknown tool, even when the Robinhood MCP Server advertises it successfully.

`get_accounts` is read-only but still denied because it exposes account identifiers that are not
needed for the approved Portfolio and Heatmap use cases.

### 6.4 Capability-audit procedure / 首次连接能力审计

This procedure is an explicit user-authorized security check. It is not portfolio sync.

Prerequisites:

- use a desktop device; Robinhood documents desktop-only onboarding/authentication;
- understand that authorization can trigger creation of a Robinhood Agentic account;
- review the broad read access described in section 6.2;
- never send a username, password, cookie, onboarding URL, OAuth code, or token to an AI prompt.

The 2026-07-28 metadata-only refresh observed **52 tools**. The newly advertised
`exercise_option` and `cancel_option_exercise` capabilities were reviewed as
write operations and remain excluded from every Argus allowlist. Only
`get_equity_positions` and `get_equity_quotes` enter the phase-one allowlist.
`get_equity_historicals` is fingerprinted but remains disabled until its live Schema is reviewed.
No Robinhood business-data tool was called during this audit.

Codex authorization and Argus Sidecar authorization are intentionally separate security
contexts. The backend must never copy or reuse Codex's private MCP session. Complete the local
audit as follows:

```bash
cd /path/to/argus
.venv/bin/pip install -e '.[robinhood]'
.venv/bin/argus-robinhood-sidecar authorize
```

The second command opens Robinhood's official OAuth page. Complete identity/login steps yourself.
If the final localhost page cannot load, copy the full callback URL from the browser address bar
and paste it only into that terminal prompt. Do not send it in chat. This command performs
`list_tools` only and writes `artifacts/robinhood-capability-audit.json`; the file contains tool
metadata and Schema fingerprints, not holdings, credentials, cookies, account numbers, or tokens.

Review `added_tools`, `missing_tools`, both allowlisted Schemas, and the manifest fingerprint. A
changed directory or Schema stays fail-closed. Never approve a fingerprint merely to bypass a
warning.

### 6.5 Start, refresh, verify, and disconnect / 启动、刷新、验收与断开

Generate a local Sidecar-to-backend bearer token. This token is not a Robinhood credential:

```bash
openssl rand -hex 32
```

Put the generated value and the reviewed manifest printed by `authorize` into local `.env`:

```dotenv
ARGUS_ENABLE_EXTERNAL_MARKET_DATA=true
ARGUS_ENABLE_ROBINHOOD=true
ARGUS_MARKET_DATA_PROVIDER=01
ARGUS_ROBINHOOD_SIDECAR_URL=http://host.docker.internal:8765
ARGUS_ROBINHOOD_SIDECAR_TOKEN=<local-random-value>
ARGUS_ROBINHOOD_APPROVED_MANIFEST=<reviewed-manifest-fingerprint>
ARGUS_ROBINHOOD_ENABLE_HISTORICALS=false
```

Start the Sidecar in a dedicated Terminal and keep it open:

```bash
cd /path/to/argus
set -a
source .env
set +a
.venv/bin/argus-robinhood-sidecar serve
```

In a second Terminal, recreate only the backend and check status:

```bash
cd /path/to/argus
docker compose up -d --force-recreate backend
curl -s http://localhost:8000/health
```

Then open **Invest Suggestions** and click **Refresh positions** once. Expected behavior:

1. Robinhood rows show the `Robinhood` source chip; file-only bank/CD/outside assets remain.
2. If the same ticker exists in both sources, Robinhood wins in the merged decision view.
3. A second manual refresh replaces only the Robinhood `investments` snapshot.
4. A partial or malformed response is rejected and the last complete snapshot remains.
5. Heatmap quotes refresh only through the selected provider; Argus does not silently switch.
6. Robinhood Activity contains no order, review, cancellation, watchlist, option, crypto,
   margin, transfer, or banking action.

Stop the Sidecar with `Control+C`. Disable both switches to return to the offline file workflow.
To remove the Sidecar's OAuth material from macOS Keychain:

```bash
.venv/bin/argus-robinhood-sidecar disconnect
```

Disconnecting does not delete uploaded files or stored source snapshots. Deleting those is a
separate user-controlled data operation.

### 6.6 Connection states, troubleshooting, and rollback / 状态、排错与回退

| State | Meaning | Operator action |
|---|---|---|
| `DISABLED` | Argus external/Robinhood switch is off | Keep file upload; enable only after implementation acceptance |
| `NOT_CONFIGURED` | No approved MCP endpoint/sidecar configuration | Configure the official endpoint through the approved host path |
| `CONNECTION_REQUIRED` | Host exists but user has not authenticated | Use the host's Connect flow |
| `CONNECTING` | Authorization or MCP initialization is in progress | Wait or cancel; do not start a second flow |
| `CONNECTED` | Transport and capability fingerprint passed | A separate user action may start read-only sync |
| `AUTH_EXPIRED` | Robinhood session expired | Reconnect through the host; do not paste credentials into `.env` |
| `PERMISSION_DENIED` | User denied access or the required read capability is unavailable | Review authorization; do not broaden Argus's tool allowlist |
| `TOOL_UNAVAILABLE` | Tool missing or schema fingerprint changed | Stop sync and repeat capability review |
| `RATE_LIMITED` | Server returned a limit/retry window | Honor `retry-after`; do not loop retries |
| `STALE` | Source timestamp is too old | Label data stale and retry manually; never call it Live |
| `PARTIAL` | Only part of the requested snapshot validated | Keep the previous committed snapshot and show rejected counts |
| `ERROR` | Classified transport/provider error | Use correlation ID and redacted logs; disconnect if repeated |

Rollback and revocation:

1. Disconnect `robinhood-trading` in the MCP Host.
2. Keep `ARGUS_ENABLE_ROBINHOOD=false` and `ARGUS_ENABLE_EXTERNAL_MARKET_DATA=false`.
3. Stop `argus-robinhood-sidecar` if it is running.
4. Confirm Portfolio uses `FileUploadSource` and `/portfolio/market-map` reports `Not live`.
5. Preserve only redacted audit metadata; run `argus-robinhood-sidecar disconnect` to remove
   OAuth material from macOS Keychain.
6. If unexplained trading, account access, or credential exposure is suspected, stop testing and
   contact Robinhood Support through the official Help Center before reconnecting.

The implementation rationale and interview answers for this boundary are documented in
[`INTERVIEW_QA.md`](INTERVIEW_QA.md#2026-07-21-robinhood-trading-mcp-host-authorization-and-strict-read-only-design).

## 7. Uploaded evidence and local disk cleanup / 上传证据与本地磁盘清理

Base Compose persists managed browser uploads in `./data/uploads` and raw artifact copies
in `./artifacts`; both paths are mounted into the backend container. Recreating `backend`
therefore no longer removes the original files silently.

基础 Compose 会把浏览器上传文件持久化到 `./data/uploads`，并把原始文件制品保存到
`./artifacts`。二者都映射进 backend，因此重新创建容器不会再悄悄丢失原始上传文件。

### Clear all evidence from the browser / 从网页一键清除全部证据

Open **Research → Uploaded research items → Clear evidence**, review the scope, then
press **Clear evidence**. When no evidence is indexed, the confirmation instead offers
**Clear leftovers** for failed-upload or test residue. This operation removes:

- every indexed evidence document;
- managed files under `data/uploads` and their known raw artifact copies;
- chunks, embeddings, Evidence Ledger links, and Claims derived from those documents;
- historical Runs and Reports that depend on the removed evidence.

It deliberately keeps expert Method Packs, Profile, Portfolio holdings, API keys, and
unrelated web-only Runs. Individual trash buttons remain available when only one source
should be removed. Method Packs appear in their own group because they are analysis
instructions rather than searchable evidence; delete one with the trash button beside that
method when it is no longer needed. Do not delete a UUID folder manually in Finder while its
document is still indexed, because that separates the database record from its original file.

### Which local folders are disposable? / 哪些本地目录可重建？

| Path | Safe action / 安全操作 | Cost of deletion / 删除后的代价 |
|---|---|---|
| `.pytest_cache`, `.ruff_cache`, `.mypy_cache`, `__pycache__`, `frontend/dist` | Safe to remove after tools stop. / 可安全清理。 | Recreated by tests, linters, type checks, or builds. |
| `.venv` | Removable when reclaiming disk. | Python dependencies must be installed again. |
| `frontend/node_modules` | Removable when reclaiming disk. | Run `npm install` again before local non-Docker builds. |
| `infra/terraform/aws/.terraform` | Provider/module cache only; removable after Terraform stops. | Run `terraform init` again; the current cache is much larger than the source tree. |
| `data`, `artifacts`, `eval-results` | Generated/private data, not source code. Use the product cleanup action or review first. | May remove uploaded evidence, raw files, or evaluation history. |
| `local_argus.db` | Legacy/manual local SQLite file; base Compose uses PostgreSQL. Archive or remove only if no manual SQLite workflow uses it. | Manual SQLite history is lost. |
| Terraform `*.tfstate*`, `*.tfvars`, and saved plans | Do **not** bulk-delete as cache. Review separately. | State/audit context or private deployment inputs may be lost; plans can also become stale. |

Never use `git clean -fdX` as a general cleanup command in this repository. It would also
target the ignored `.env`, API configuration, uploads, Terraform state, and other private
runtime data—not only harmless caches.

## 8. Cost history, Run deletion, and provider reconciliation / 成本历史、Run 删除与供应商对账

The **Runs Management** workspace has three different scopes. Do not compare one scope with a
provider total as if they measured the same retention window:

- **Retained Run usage** totals only the Run/Model Call traces still stored for debugging. It
  may decrease when evidence-dependent Runs expire or are deleted.
- **Historical API usage** comes from `api_usage_ledger`. It survives Evidence and Run
  deletion and is the local cumulative estimate from migration `20260720_0019` onward, plus
  Model Calls that still existed when that migration ran.
- **Provider actual billing** is imported from an official provider dashboard/export and is
  the final source of truth. It is not added to the Argus USD estimate automatically.
- **Provider account status** is not a fourth cost total. It stores a point-in-time billing
  tier, available balance, paid balance, or promotional balance. A remaining balance says how
  much capacity is left; it does not say how much the account has spent.

Important limitation: Model Calls deleted before migration `0019` cannot be reconstructed
from the local database. Do not manufacture request-level rows from an aggregate screenshot.
When an official export provides only a period total, record it as a provider billing
snapshot. For example:

```bash
curl -X POST http://localhost:8000/runs/provider-billing-snapshots \
  -H 'Content-Type: application/json' \
  -d '{
    "provider": "provider-id",
    "period_start": "2026-06-01",
    "period_end": "2026-06-30",
    "currency": "CNY",
    "actual_cost": 1.23,
    "total_tokens": 100000,
    "request_count": 30,
    "source_reference": "official-console-export-2026-06"
  }'
```

Use a non-secret provider identifier and an export reference, not an API Key, raw prompt,
full response, or holdings data. Reload **Runs Management** after a successful import.

DeepSeek's official Usage ZIP can be imported directly. The importer is idempotent by file
hash, accepts only the expected bounded CSV files, preserves exact CNY decimals and model/token
breakdowns, and discards identity and API-key columns:

```bash
curl -X POST http://localhost:8000/runs/provider-billing-snapshots/import/deepseek \
  -H 'Content-Type: application/zip' \
  -H 'X-Argus-Filename: usage_data_YYYY-MM-DD_YYYY-MM-DD.zip' \
  --data-binary '@usage_data_YYYY-MM-DD_YYYY-MM-DD.zip'
```

Record a balance or Free Tier state separately from spend:

```bash
curl -X POST http://localhost:8000/runs/provider-account-snapshots \
  -H 'Content-Type: application/json' \
  -d '{
    "provider": "provider-id",
    "billing_tier": "Free Tier",
    "billing_status": "active",
    "currency": "USD",
    "available_balance": 10.00,
    "promotional_balance": 10.00,
    "source_reference": "official-account-console"
  }'
```

Provider-specific reconciliation rules:

- **DeepSeek:** import the official Usage ZIP for actual period cost, requests, and tokens.
  Its balance API is suitable only for a current balance snapshot.
- **Kimi:** the tokenizer endpoint estimates a request before sending it; it cannot recover
  historical billed tokens. The balance endpoint returns available, cash, and voucher balances.
  Import actual spend from the account console/statement when no detailed export is available.
- **Exa:** each Search response returns per-request `costDollars`. Exa also documents a separate
  Team Management usage endpoint for authoritative API-key cost over a bounded period, but it
  requires a service API key plus the target API-key UUID. The ordinary Search API key configured
  in Argus is not sufficient. This endpoint reports usage/cost and key budget status—not remaining
  account balance—so it belongs under billing reconciliation rather than **Refresh balances**.
- **Gemini:** a Free Tier project can have request/token telemetry without a paid invoice.
  Store `Free Tier` as account status; do not manufacture a provider billing row with `$0`.

### 7.1 What is automatic, and what still needs operations? / 自动与手工边界

| Data / 数据 | Current behavior / 当前方式 | Operator action / 运维操作 |
|---|---|---|
| Token usage for external model calls made by Argus | Automatically appended after each response. It survives Run deletion. Local deterministic word-count estimates and Exa searches are excluded. / 外部模型响应后自动写入；本地单词数估算和 Exa 搜索不计入。 | None during normal use. / 正常使用无需操作。 |
| Argus model-cost estimate | Automatically uses returned input/output tokens and the price snapshot recorded at call time. | Review only; never treat it as an invoice. / 只需查看，不能当正式账单。 |
| DeepSeek actual usage | Official ZIP import is implemented. | Download and import after a test campaign or monthly. |
| Kimi actual spend | No supported historical billing API is currently integrated. | Record the monthly statement/account total. Token Estimate and Balance are not bills. |
| DeepSeek/Kimi current balance and API availability | Runs Management → **Refresh balances** calls the configured official balance APIs on demand and stores point-in-time snapshots. | Refresh before a paid test campaign or when checking runway. There is no background polling. |
| Other provider balance or Free Tier | Stored separately as a point-in-time account snapshot. | Record it manually when no supported official balance API is integrated. |
| Exa search cost | Each Search response supplies per-request `costDollars`. Exa's separate Team Management API can return API-key usage/cost when a service key and key UUID are available; it is not a balance endpoint. | Reconcile the Usage dashboard today. Add the more privileged Team Management credentials only after a separate security review. |
| Gemini Free Tier | Model response usage is recorded; no paid invoice is created. | Recheck only if paid billing is enabled. |

The Runs Management page includes a compact **Update provider records** control for the
structured DeepSeek Usage ZIP. Do not upload Kimi billing screenshots: Argus intentionally does
not use OCR to turn a screenshot into authoritative cost or Token rows. **Refresh balances** now
queries the configured DeepSeek and Kimi official endpoints. It records current remaining balance
and derives `active` versus `insufficient_balance` from the provider response; it cannot retrieve
historical charges, a detailed usage statement, or a full subscription/billing tier. A balance is
not historical spend. Exa's Search response exposes the completed request's estimated
`costDollars`. Its separately documented Team Management usage API can reconcile an API key, but
Argus does not currently request or store the extra service credential and key UUID it requires.

Never automate billing by scraping a logged-in provider webpage. Use an official API, official
export, or a manually verified statement. Web sessions expire, CAPTCHA and page layouts change,
and a scraper would expand the security scope of provider credentials.

### 7.2 Recommended operating cadence / 建议维护频率

- **After every Argus call:** no manual action. The API Usage Ledger is written automatically.
- **After a concentrated test session:** open **Runs Management** and compare request count,
  Token totals, and estimated cost with the provider dashboard. This catches retry or adapter
  defects early.
- **Weekly while actively testing paid APIs:** check remaining provider balances. Update an
  account snapshot only when the value changed or a dated audit record is useful.
- **Monthly:** import the DeepSeek ZIP, record the Kimi statement total, record the Exa Usage
  dashboard period total, and confirm Gemini is still Free Tier or reconcile paid billing.
- **Before a demo/interview:** check that the latest provider periods and currencies are visible,
  but do not trigger paid calls merely to make the dashboard look current.

### 7.3 Step-by-step reconciliation / 手工对账步骤

1. Open Terminal and start from the repository root:

   ```bash
   cd /path/to/argus
   docker compose up -d backend
   docker compose exec backend alembic current
   ```

   Expected migration: `20260722_0022 (head)`.

2. Open `http://localhost:5173`, choose **Runs Management**, and note the three cost scopes plus the
   separate Provider account status. Do not add balances to costs.

3. For DeepSeek, download the official Usage ZIP without editing or extracting it, then run:

   ```bash
   curl -X POST http://localhost:8000/runs/provider-billing-snapshots/import/deepseek \
     -H 'Content-Type: application/zip' \
     -H 'X-Argus-Filename: usage_data_2026-06-22_2026-07-21.zip' \
     --data-binary '@/path/to/downloads/usage_data_2026-06-22_2026-07-21.zip'
   ```

   Re-importing the identical ZIP returns the existing snapshot instead of double-counting it.
   The maximum archive size is 5 MB; Argus does not retain user ID or API-key columns.

4. For Kimi or Exa, use the generic provider-billing command shown earlier in this section.
   Copy the exact period, currency, and total from the official statement/dashboard. Omit Token
   and request fields when the provider does not report them; do not estimate missing actuals.

5. For configured DeepSeek and Kimi accounts, click **Refresh balances** in Runs Management.
   Argus uses the API Keys already stored in local environment configuration and never returns
   them to the browser. Use the manual account-snapshot endpoint shown earlier only for providers
   without an integrated official balance API or for a dated Free Tier state. Never submit an API
   Key, raw prompt, holdings, or login cookie in a snapshot request.

6. Reload **Runs Management** and verify:

   - the provider name, period, currency, request count, Token count, and actual charge match the
     official source where those fields exist;
   - balance appears only under **Provider account status**;
   - `Historical API usage` does not fall after a Run is deleted;
   - different currencies remain separate and are not silently converted or added.

### 7.4 Failure and discrepancy handling / 失败与差异处理

| Symptom / 现象 | Meaning / 原因 | Action / 处理 |
|---|---|---|
| DeepSeek import returns HTTP 413 | ZIP is larger than the 5 MB safety limit. | Confirm it is the official bounded export; do not bypass the limit without reviewing the file. |
| DeepSeek import returns HTTP 422 | ZIP structure, filenames, period, currency, or numeric rows failed validation. | Download a fresh official export and retry; do not hand-edit cost rows. |
| The same DeepSeek snapshot appears unchanged | Expected idempotent behavior for the same file hash. | No action; it was not charged twice in Argus. |
| Argus estimate differs from provider actual | Possible cache pricing, credits, retries, rounding, taxes, delayed settlement, or missing pre-migration history. | Treat the provider total as authoritative, keep both records, and document the reason when known. |
| Balance changed but no matching usage appears | Top-up, promotional grant, refund, expiration, or delayed posting may be involved. | Do not infer a bill from balance delta; inspect the official statement. |
| Balance refresh says `not_configured` | The provider API Key is not present in the backend environment. | Add the Key to local `.env`, recreate the backend container, and retry. Never paste a Key into the Runs page. |
| One balance refresh succeeds and another fails | Providers are refreshed independently; the failed provider's previous snapshot remains visible. | Read the sanitized error, verify that the Key matches the configured domestic/international endpoint, and retry only that operation later. |
| Provider dashboard is unavailable | Actual billing cannot be verified at that moment. | Keep the existing dated snapshot and retry later; do not overwrite it with a guess. |

Current automation boundary: on-demand DeepSeek/Kimi balance refresh and DeepSeek Usage ZIP import
are implemented. Background balance polling, an append-only Exa Tool Usage Ledger, a generic
browser statement-upload control, and Google Cloud Billing Export for a future paid Gemini project
remain future work, not current production claims.

To verify that the ledger schema is active:

```bash
docker compose exec backend alembic current
```

Expected revision: `20260722_0022 (head)`.

## 8. Robinhood Heatmap and Volume Activity / 行业热力矩阵与成交量活跃度

The Heatmap is an optional presentation layer. It does not change holdings, ETF eligibility,
rebalance math, or model prompts. The default in `.env.example` is off so an operator can keep the
previous compact market-data card.

```bash
# Fixed-size sector/industry HeatmapMatrix.
ARGUS_ENABLE_MARKET_HEATMAP=true

# One ETF Universe with switchable Market and Research views.
# false restores the prior separate Heatmap and candidate directory.
ARGUS_ENABLE_UNIFIED_ETF_UNIVERSE=true

# Optional completed-session OHLCV retrieval for Volume activity.
ARGUS_ROBINHOOD_ENABLE_HISTORICALS=true
```

After changing either value, restart the backend:

```bash
cd /path/to/argus
docker compose up -d --force-recreate backend
```

The historicals permission is enforced by both the backend and the local Sidecar. If the Sidecar
was started before the flag changed, stop it with `Ctrl+C` in its Terminal and start it again:

```bash
cd /path/to/argus
.venv/bin/argus-robinhood-sidecar serve
```

Use the refresh icon in **Invest Suggestions → Market intelligence** to refresh quotes and bypass
the six-hour normalized historical-volume cache. The cache retains only ticker, trading date, and
bounded close/volume fields for up to 61 completed sessions per ticker; it does not retain full
provider responses, account identifiers, OAuth material, or API Keys.

Heatmap reading rules:

- fixed tile size prevents market volume from looking like recommendation strength;
- muted green/red is the latest regular-session price versus the prior completed regular-session
  close (`1D`); it is not a weekly or yearly return;
- border strength is completed-session Volume activity;
- the readable `Normal`, `Elevated`, `High`, `Unusual`, and `Quiet` labels use separate text colors
  so volume state is not confused with red/green price direction;
- neutral badges are a separate holdings/research dimension: `● HELD ETF`, `◆ RELATED n`,
  `＋ NEW`, `⇄ REPLACE`, or `◎ REVIEW`;
- clicking a tile opens a modal with the prior-close date, Z-score inputs, formula, quality status,
  label thresholds, plain-language interpretation, related stock names, recommendation role,
  issuer, and official fund source. `Escape`, the Close button, or the backdrop closes it.

When `ARGUS_ENABLE_UNIFIED_ETF_UNIVERSE=true`, the evidence-backed shortlist remains above one
shared ETF Universe. Use **Market view** for 1D price/volume observations and **Research view** for
fund identity, issuer verification, holdings overlap, and recommendation role. The views are two
projections of the same frontend view model; switching views does not call a model or change a
recommendation. Red/green in Market view never means recommended/not recommended. In this mode the
older full-width market-data status card is hidden because it duplicates Market view. Provider,
Live/Delayed state, and quote refresh appear only inside Market view; Research view instead states
that its fund metadata, holdings mappings, and accepted recommendation roles come from Argus rather
than Robinhood. The fund count remains in the shared ETF Universe header. A no-data message appears
inline when zero quotes are available. The refresh button is functional: it requests current quotes
again and, when historicals are enabled, rebuilds the bounded historical-volume cache.

Core policy candidates such as BND or VXUS may not appear in the sector/industry Heatmap, but Argus
still adds any unheld candidate used by Rebalance or DCA to the same provider-neutral quote request.
The backend passes only trusted returned quotes into deterministic Python calculations. This allows
the UI to show a quote and estimated shares without asking the answer model to calculate trade math.
If no valid quote returns, the dollar target remains visible and the existing `fetch a current quote`
warning is preserved. Existing holdings always retain their saved snapshot price; the live overlay
is only for approved candidates that are not already held.

Robinhood can roll its quote-level `previous_close` to the just-completed session after the market
closes. If Argus compared that field directly with the same session's last price, nearly every tile
would incorrectly look flat. When historicals are enabled, Argus therefore identifies the regular
session represented by the quote, selects the latest non-interpolated historical close strictly
before that session, and computes:

```text
1D percent change = (latest regular-session price - prior completed close)
                    / prior completed close × 100
```

The modal displays both the comparison close and its date. If the bounded historical close is not
available, Argus retains the provider quote value but does not invent another period return.

Argus uses a robust log-MAD score rather than a conventional mean/standard-deviation Z-score:

```text
Robust Z
  = [ln(1 + latest completed-session volume)
     - median(ln(1 + each reference-session volume))]
    / [1.4826 × MAD(ln(1 + each reference-session volume))]
```

The latest completed regular session is compared with up to 60 earlier completed regular
sessions. The current/incomplete session and interpolated bars are excluded. At least 20 reference
sessions and non-zero variation are required. `Elevated`, `High`, and `Unusual` describe unusual
participation only; they do not predict direction and are never a standalone BUY/SELL signal.

Rollback requires no data migration:

```bash
ARGUS_ENABLE_MARKET_HEATMAP=false
ARGUS_ENABLE_UNIFIED_ETF_UNIVERSE=false
docker compose up -d --force-recreate backend
```

When disabled, the API still returns the provider-neutral market-data contract and Portfolio shows
the earlier compact status card. To stop historical calls as well, set
`ARGUS_ROBINHOOD_ENABLE_HISTORICALS=false` and restart both backend and Sidecar.

To roll back only the unified two-view layout while retaining the Heatmap, keep
`ARGUS_ENABLE_MARKET_HEATMAP=true`, set `ARGUS_ENABLE_UNIFIED_ETF_UNIVERSE=false`, and restart only
the backend. No database migration or cache deletion is required.

### 8.8 Kimi research timeout / Kimi 研究回答超时

普通模型请求默认最多等待 20 秒。Kimi 处理多份本地和网页证据时可能需要更久，因此单独使用：

```bash
ARGUS_KIMI_TIMEOUT_MS=60000
```

修改 `.env` 后要重建后端容器的环境变量；仅刷新网页不够：

```bash
cd /path/to/argus
docker compose up -d --force-recreate backend
```

无费用的诊断顺序是：先到 Runs 查看失败 Run；如果 Exa 和本地检索成功、模型为 0 Token、耗时约
20 秒且状态为 failed，通常是旧超时窗口，不是 Evidence Gate 拒绝。`/models` 连通性和模型名称
检查不生成答案 Token。Argus 不自动重试超时请求，因为第一次请求可能已经在供应商端处理并计费。
修复后新超时会记录为 `provider_timeout`；旧 Run 的通用 `model_provider_error` 不会被改写。

The Kimi-specific timeout is a response window, not a token or spending budget. The existing
output-token cap still bounds generation. Keep provider billing as the final source of truth.

## 9. Local Kafka Event Pipeline / 本地 Kafka 事件流水

### 9.1 What this operates / 这套流程管理什么

Argus supports one production-shaped but deliberately small Research Run lifecycle
with two terminal event contracts:

```text
Research Run ends normally
  -> API publishes agent.run.completed.v1
     -> ANSWER GENERATED or NO ANSWER · SAFE STOP
Research answer-model call fails
  -> API publishes agent.run.failed.v1
     -> provider_timeout / provider_authentication_failed /
        provider_quota_exhausted / model_provider_error
  -> Kafka stores the event
  -> Audit/Metrics Consumer validates it
  -> processed / duplicate / DLQ summary is saved
  -> Runs Management displays the operational result
```

PostgreSQL Runs is still the business source of truth. Kafka supplies a replayable
event stream, while the event-audit tables are a sanitized operational projection.
Runs Management is not a full Kafka administrator: it cannot replay events, reset
offsets, delete topics, or inspect arbitrary raw messages.

In the completed topic name, `completed` means the Research workflow reached a terminal auditable state. It
does **not** guarantee that an answer was generated. A safe Evidence-Gate refusal is also consumed
and is shown with `answer_generated=false` plus its `execution_outcome`. This lets operations track
no-answer rates without storing the question or answer. Answer-model timeouts, authentication
failures, quota/balance/rate-limit failures, and other provider failures use `agent.run.failed.v1`.
Search-tool failures remain in PostgreSQL Runs and tool traces because this event is specifically a
model-failure contract. Neither event stores the raw provider message.

### 9.2 Start and validate / 启动与验收

From the Argus directory:

```bash
cd /path/to/argus
docker compose -f compose.yaml -f compose.v2.yaml up -d --build \
  postgres redis kafka backend event-consumer
docker compose -f compose.yaml -f compose.v2.yaml ps
```

The Kafka settings live in `compose.v2.yaml`. Starting or recreating the backend with only
`docker compose ...` and no `-f compose.v2.yaml` removes `ARGUS_KAFKA_BOOTSTRAP_SERVERS` from that
container, so Runs Management correctly shows `disabled` and no live heartbeat. Re-run the combined
command above to restore Kafka configuration and the consumer heartbeat.

Expected services: PostgreSQL healthy, Redis healthy, backend healthy, Kafka up,
and `event-consumer` up. Validate Compose syntax without printing expanded `.env`
secrets:

```bash
docker compose -f compose.yaml -f compose.v2.yaml config --quiet
```

Run the real-broker acceptance test. It sends one sanitized synthetic completion
twice, one sanitized synthetic model failure, and one invalid message. It never
calls a model or web-search API:

```bash
docker compose -f compose.yaml -f compose.v2.yaml exec -T backend \
  argus-kafka-topic-bootstrap \
  --partitions 1 \
  --replication-factor 1

docker compose -f compose.yaml -f compose.v2.yaml exec -T backend \
  python /app/scripts/kafka_local_acceptance.py \
  --bootstrap kafka:9092 --api-base http://localhost:8000
```

The bootstrap command is idempotent: existing topics are accepted, missing
topics are created, and every topic's partition count and retention are checked.
Passing output contains `status: passed`, `processed_delta: 2`,
`duplicate_delta: 1`, `dlq_delta: 1`, and `consumer_status: running`.
The normal application publisher is separately covered by the API integration
test. To exercise it against the real broker too, first upload an evidence source,
then add `--verify-api-publisher`; this deliberately creates and retains one local
Research Run.

### 9.3 Check it in Runs and Kafka / 在页面和 Kafka 中检查

Open <http://localhost:5173/> and select **Runs Management → Event pipeline**.
Verify:

- Transport is Kafka and consumer status is Running.
- Completed workflow events increases for a new answered or safely stopped event.
- Failed model events increases for a timeout, authentication, quota, or provider failure.
- Duplicates ignored increases when the same `event_id` is replayed.
- DLQ increases for an invalid contract or exhausted processing retries.
- Recent events shows 10 sanitized summaries per page with type, Run ID, answer/no-answer
  outcome, attempts/duplicates, partition/offset, and time. Use **Previous** and **Next** with the
  `Showing x–y of n` range, consistent with Recent Runs. The Event type and Processed headers sort
  the loaded rows, return to page one, and show the active direction arrow.

### 9.3.1 Test document summary without unnecessary web cost / 测试文档总结且避免网页费用

For a summary of one uploaded Markdown, TXT, DOC/DOCX, or text-based PDF:

1. Upload or select exactly one evidence document.
2. Choose **Uploaded / indexed sources only**. Do not choose combined web search unless current
   external context is genuinely required.
3. Base investment framework and expert methods may both remain empty; Argus uses neutral
   evidence-first research.
4. Ask `总结上传的这篇文档，并列出主要观点、依据和局限。`
5. Confirm the Answer badge says `ANSWER GENERATED`. If it says `NO ANSWER · SAFE STOP`, open the
   audit details and inspect the Evidence Gate outcome before changing models.

For a cross-language summary, the bounded summary channel samples representative complete passages
from the single selected document. It does not relax ordinary fact questions, mix multiple uploads,
or call another model silently.

For a broker-level check:

```bash
docker compose -f compose.yaml -f compose.v2.yaml exec -T kafka \
  /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:9092 --list

docker compose -f compose.yaml -f compose.v2.yaml exec -T kafka \
  /opt/kafka/bin/kafka-consumer-groups.sh --bootstrap-server localhost:9092 \
  --describe --group argus-audit-metrics-v1
```

Expected topics include `agent.run.completed.v1`, `agent.run.failed.v1`, and matching
`.retry` and `.dlq` topics. Current handler retries are bounded in-process; the
pre-created retry topics reserve an explicit future delayed-retry path and are not
part of the accepted processing behavior yet. `LAG 0` means this consumer group has caught up;
it does not prove that the business result itself is correct, so also check the
Run and the audit status.

### 9.4 Failure guide / 故障排查

| Symptom / 现象 | Meaning / 含义 | Action / 处理 |
|---|---|---|
| Consumer status `waiting` immediately after clean start | The topic or broker coordinator is still initializing. Local Kafka may create a versioned topic only when its first event is published. | Wait up to the bounded 10-second metadata refresh window, then inspect logs. Production topics should be pre-created through IaC. |
| Consumer status `stale` | No heartbeat arrived within the configured threshold. | Check `docker compose -f compose.yaml -f compose.v2.yaml logs --tail=200 event-consumer kafka`. |
| DLQ count rises | Contract validation failed or all bounded handler retries failed. | Review the sanitized error code and event ID in Runs; inspect service logs. Do not copy raw sensitive payloads into the UI. |
| Duplicate count rises | Kafka delivered an already-seen stable event ID. | Normally safe: Argus ignored the repeated business effect and committed the offset. Investigate only if the rate is unexpectedly high. |
| A model failed but Failed model events did not rise | The Run was committed but the direct Kafka publish failed, or the Consumer has not caught up. | Treat PostgreSQL Runs as truth, inspect backend/consumer logs and Kafka lag; do not retry a billable model merely to create an audit event. |
| Run exists but no Kafka audit event | Direct publish is not atomic with the database transaction or Kafka was unavailable. | Treat PostgreSQL as truth, inspect producer/broker logs, and plan the documented transactional-outbox upgrade before making Kafka business-critical. |

Configuration defaults:

```dotenv
ARGUS_KAFKA_CONSUMER_GROUP=argus-audit-metrics-v1
ARGUS_KAFKA_CONSUMER_MAX_ATTEMPTS=3
ARGUS_KAFKA_AUDIT_RETENTION_COUNT=5000
ARGUS_KAFKA_AUDIT_RETENTION_DAYS=30
```

Local Kafka logs retain seven days in `compose.v2.yaml`. These event-audit limits
do not delete PostgreSQL Runs or API Usage Ledger entries. To stop only this local
event path without deleting database data:

```bash
docker compose -f compose.yaml -f compose.v2.yaml stop event-consumer kafka
```

## 10. Local Kubernetes with kind / 使用 kind 验收本地 Kubernetes

这条路径用于学习 Kubernetes 和验证 manifests，不创建 AWS 资源，也不证明 MSK 已经在云端运行。
它在本地单节点集群中运行 API、frontend、worker、event-consumer、PostgreSQL、Redis 和
单节点 Kafka。所有数据都是临时数据；删除 kind cluster 后会一起消失。

### 10.1 Prerequisites / 前置工具

```bash
brew install kind
docker version
kind version
kubectl version --client
```

Docker Desktop 建议至少提供约 8 GB 内存。脚本会严格检查 kubectl context 必须是
`kind-argus-learning`，避免误操作其他 Kubernetes cluster。

### 10.2 First reproducible deployment / 第一次可复现部署

```bash
cd /path/to/argus
./scripts/kind_local.sh deploy
./scripts/kind_local.sh status
./scripts/kind_local.sh accept
```

`deploy` 会：

1. 创建或选择 `argus-learning` kind cluster；
2. 使用当前 Git short SHA 构建本机 arm64 backend/frontend 镜像；
3. 把镜像直接加载到 kind，不推送公共 registry；
4. 在 cluster 内随机生成临时 PostgreSQL 密码；
5. 把连接字符串放入运行时 Kubernetes Secret，不写入文件或 Git；
6. 等待 PostgreSQL、Redis 和 Kafka Ready；
7. 运行 migration、六个 Kafka topics 的 bootstrap 和四个应用 Deployment。

`accept` 的通过条件是：

- migration 输出 `Verified migration head: 20260722_0022`；
- Kafka acceptance 输出 `status: passed`；
- `processed_delta: 2`、`duplicate_delta: 1`、`dlq_delta: 1`；
- consumer status 是 `running`；
- completed/failed topics 的 consumer group lag 都是 `0`。

### 10.3 Clean second run for recording / 录屏前的干净第二遍

第一次已经构建过当前 SHA 镜像时，可以跳过重新构建：

```bash
./scripts/kind_local.sh destroy
ARGUS_KIND_SKIP_BUILD=true ./scripts/kind_local.sh deploy
./scripts/kind_local.sh accept
```

只有当前 Git SHA 对应的两个本地镜像都存在时才能使用
`ARGUS_KIND_SKIP_BUILD=true`；脚本会先检查镜像，缺失时立即停止。

建议录制：

1. `git status --short --branch` 和 `git rev-parse --short=12 HEAD`；
2. 上述 clean deploy 的最终资源创建与 rollout；
3. `./scripts/kind_local.sh status`；
4. `./scripts/kind_local.sh accept`；
5. 删除一个 `argus-event-consumer` Pod，展示 Deployment 自动补回；
6. `kubectl -n argus port-forward service/argus-frontend 18080:8080` 后展示页面；
7. `./scripts/kind_local.sh destroy`。

不要录制或输出 `.env`、`kubectl get secret -o yaml`、数据库连接字符串、API key、
AWS account ID 或 token。镜像首次构建、依赖下载和长时间等待可以暂停录制。

### 10.4 Failure and rollback / 失败与回退

```bash
kubectl -n argus get pods
kubectl -n argus get events --sort-by=.metadata.creationTimestamp
kubectl -n argus describe pod POD_NAME
kubectl -n argus logs deployment/argus-api --all-containers --tail=200
kubectl -n argus logs deployment/argus-event-consumer --tail=200
./scripts/kind_local.sh destroy
```

`destroy` 只删除名称精确匹配的本地 `argus-learning` cluster。它不调用 AWS，也不会删除
其他 kubectl context。
