# Phase 0 Learning Guide

This document explains Argus Phase 0 for a beginner. The goal is not to learn
Docker, FastAPI, React, Git, and AI agents all at once. The goal is to
understand what we built, why it exists, and what you should be able to explain
before moving into Phase 1.

## What Phase 0 Built

Phase 0 created the local development skeleton for Argus V1.

In plain language:

```text
browser UI
-> React frontend on localhost:5173
-> FastAPI backend on localhost:8000
-> PostgreSQL/pgvector database on localhost:5432
```

No Gmail, no Robinhood, no cloud services, and no trading execution are involved
in Phase 0.

The important files are:

- `compose.yaml`
- `Dockerfile`
- `src/investment_agent/app.py`
- `frontend/src/App.tsx`
- `README.md`
- `.gitignore`

## Mental Model

Think of Argus as three local programs that need to cooperate:

```text
Frontend: what the user sees and clicks
Backend: the API that receives requests and runs application logic
Database: where documents, evidence, reports, portfolio rows, and run traces live
```

The frontend should not talk directly to the database. It talks to the backend.
The backend is responsible for validation, business logic, database access, and
later agent/RAG workflows.

## File 1: `compose.yaml`

`compose.yaml` describes how to run several services together on your machine.

Phase 0 defines three services:

```yaml
services:
  postgres:
  backend:
  frontend:
```

### `postgres`

This service runs PostgreSQL with pgvector:

```yaml
image: pgvector/pgvector:pg16
```

PostgreSQL is the relational database. pgvector adds vector storage and vector
search, which we need later for RAG retrieval.

This block creates the default local database credentials:

```yaml
POSTGRES_DB: argus
POSTGRES_USER: argus
POSTGRES_PASSWORD: argus
```

This exposes the database to your machine:

```yaml
ports:
  - "5432:5432"
```

Meaning:

```text
your machine port 5432 -> container port 5432
```

This keeps database data even if the container restarts:

```yaml
volumes:
  - postgres_data:/var/lib/postgresql/data
```

Without a volume, the database could disappear when the container is removed.

### `backend`

This service runs the FastAPI backend.

It builds from the root `Dockerfile`:

```yaml
build:
  context: .
  dockerfile: Dockerfile
```

It starts the backend with:

```yaml
uvicorn investment_agent.app:app --host 0.0.0.0 --port 8000 --reload
```

Meaning:

- `uvicorn`: Python web server for FastAPI.
- `investment_agent.app:app`: import `app` from `src/investment_agent/app.py`.
- `--host 0.0.0.0`: listen inside Docker so your browser can reach it.
- `--port 8000`: backend uses port 8000.
- `--reload`: restart automatically when source code changes.

The backend has environment variables:

```yaml
ARGUS_ENABLE_CLOUD_SERVICES: "false"
ARGUS_ENABLE_GMAIL: "false"
ARGUS_ENABLE_ROBINHOOD: "false"
```

This makes the V1 boundary explicit: local-first only.

This line gives the backend the database connection string:

```yaml
ARGUS_DATABASE_URL: postgresql+psycopg://argus:argus@postgres:5432/argus
```

Breakdown:

```text
postgresql+psycopg:// user : password @ host : port / database
```

Here, `postgres` is the Docker Compose service name. Inside the Compose network,
the backend can reach the database by using that service name.

### `frontend`

This service runs the React/Vite frontend.

It builds from `frontend/Dockerfile` and starts:

```yaml
npm run dev -- --host 0.0.0.0
```

It exposes:

```yaml
ports:
  - "5173:5173"
```

So you can open:

```text
http://localhost:5173
```

The frontend has:

```yaml
VITE_API_BASE_URL: http://localhost:8000
```

That tells the browser where the backend API lives.

## File 2: `Dockerfile`

The root `Dockerfile` builds the backend image.

```dockerfile
FROM python:3.12-slim
```

Start from a small Python image.

```dockerfile
WORKDIR /app
```

All later commands run inside `/app`.

```dockerfile
COPY pyproject.toml README.md ./
COPY src ./src
```

Copy project metadata and source code into the image.

```dockerfile
RUN pip install --no-cache-dir -e .
```

Install the Python package. The `-e` means editable install. In local
development, this makes package imports work cleanly.

```dockerfile
CMD ["uvicorn", "investment_agent.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

Default command if the container starts without an override.

## File 3: `src/investment_agent/app.py`

This is the backend application entry point.

Important pieces:

```python
class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    mode: str
```

This defines the shape of the health response. FastAPI uses it to validate and
document the endpoint.

```python
def create_app() -> FastAPI:
```

This function creates the FastAPI app. This pattern is useful because tests can
create a fresh app later.

```python
@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
```

This creates a GET endpoint:

```text
GET /health
```

It returns:

```json
{
  "status": "ok",
  "service": "argus-api",
  "version": "0.1.0",
  "mode": "development"
}
```

The health endpoint is the first backend endpoint because it answers the most
basic operational question:

```text
Is the backend alive?
```

Before adding document ingestion, RAG, reports, or portfolio logic, we need this
simple heartbeat.

### CORS

The backend includes:

```python
CORSMiddleware
```

CORS matters because the browser sees these as different origins:

```text
frontend: http://localhost:5173
backend:  http://localhost:8000
```

Without CORS, the browser may block frontend requests to the backend even though
both are running on your machine.

## File 4: `frontend/src/App.tsx`

This is the first frontend screen.

The important line is:

```ts
fetch(`${apiBaseUrl}/health`)
```

When the frontend loads, it calls:

```text
GET http://localhost:8000/health
```

Then it shows whether the backend is reachable.

This is not the final UI. It is a skeleton for the future V1 pages:

- Research
- Portfolio
- Profile
- Runs

Those page names are already visible because they represent the user-facing V1
product areas.

## File 5: `README.md`

The README is the entry point for humans.

It now explains:

- where the V1 scope lives;
- how to run the local stack;
- which services exist;
- how to run tests;
- that Gmail, Robinhood, and cloud services are disabled for V1.

Good README behavior:

```text
new person clones repo
-> follows commands
-> gets local app running
-> understands current scope
```

## File 6: `.gitignore`

`.gitignore` tells Git what not to track.

Examples:

```text
.venv/
__pycache__/
.pytest_cache/
frontend/node_modules/
credentials.json
token.json
secrets/
data/
artifacts/
reports/
```

This matters because a serious repo should not commit:

- local Python environments;
- generated caches;
- Node dependencies;
- secrets;
- OAuth tokens;
- private research data;
- generated report artifacts.

## Request Flow

When everything is running locally, the simple Phase 0 request flow is:

```text
1. You open http://localhost:5173
2. React renders App.tsx
3. App.tsx calls GET http://localhost:8000/health
4. FastAPI receives the request
5. app.py returns JSON
6. React displays backend status
```

This tiny flow proves that:

- frontend can start;
- backend can start;
- frontend can call backend;
- backend can return typed JSON;
- local development wiring works.

## Why We Did Not Build Features Yet

Phase 0 is foundation work.

It does not implement:

- document ingestion;
- RAG retrieval;
- agent loop;
- report generation;
- portfolio upload;
- user profile;
- cost dashboard.

Those belong to later phases.

Building them before the local skeleton works would create confusion. The right
order is:

```text
make it run
-> make it store data
-> make it ingest documents
-> make it retrieve evidence
-> make it generate cited answers
-> make it observable
```

## Learn Claude Code Mapping

For Phase 0, you do not need to understand all AI agent internals yet. You only
need a high-level idea of what an agent harness will become.

Use this order:

### Before Phase 1

Read lightly:

- Learn Claude Code homepage overview
- s01 Agent Loop

You only need to understand:

```text
agent = model loop + tools + returned tool results
```

Do not try to implement it yet.

### During Phase 1

Focus on backend foundations first:

- FastAPI app structure
- settings/configuration
- SQLAlchemy connection
- Alembic migrations
- repository pattern
- pytest

Learn Claude Code is less important during Phase 1 than backend/database basics.

### Before Phase 4

Study carefully:

- s01 Agent Loop
- s02 Tool Use
- s03 Permission
- s04 Hooks
- s05 TodoWrite
- s11 Error Recovery

These map directly to:

- custom agent loop;
- tool registry and dispatch;
- approval and deny policies;
- pre/post runtime checks;
- run planning;
- timeout/retry handling.

### Before Phase 5

Study:

- s06 Subagent
- s07 Skills
- s10 System Prompt

These map to:

- Research/Critic workflow;
- investment style skills;
- prompt assembly from policy, tools, skills, and evidence.

### Later, Not Now

Study after V1 core works:

- s08 Context Compact
- s09 Memory
- s12 Task System
- s13 Background Tasks
- s14 Cron Scheduler
- s15-s20 multi-agent platform lessons

These are useful, but they are not needed to understand Phase 0.

## Concepts You Should Know Before Phase 1

You do not need mastery. You need working definitions.

### Frontend

The browser app. In Argus, it is React and TypeScript.

### Backend

The API server. In Argus, it is Python and FastAPI.

### Database

Persistent storage. In Argus, it will be PostgreSQL with pgvector.

### API

A contract between programs. Example:

```text
GET /health -> returns backend status JSON
```

### Container

A packaged runtime environment for one service.

### Docker Image

The blueprint used to create containers.

### Docker Compose

A local tool to run multiple containers together.

### Environment Variable

A configuration value passed into a program without hardcoding it in source
code.

### Port

A network door on your machine. Examples:

- `5173`: frontend
- `8000`: backend
- `5432`: PostgreSQL

### Volume

Persistent or mounted storage for a container.

### Health Check

A small test that answers whether a service is alive and ready.

## Hands-On Exercises

Do these before Phase 1.

1. Open `compose.yaml` and identify the three services.
2. Explain why backend depends on postgres.
3. Find which port the frontend uses.
4. Find which port the backend uses.
5. Find where cloud, Gmail, and Robinhood are disabled.
6. Open `app.py` and identify the `/health` endpoint.
7. Open `App.tsx` and find where it calls `/health`.
8. Open `.gitignore` and explain why `credentials.json` should not be committed.

## Quiz

Answer these in your own words. If you cannot answer a question, go back to the
relevant section above.

### Basic

1. What is the difference between frontend, backend, and database?
2. Why does Argus V1 use Docker Compose locally?
3. What does `GET /health` prove?
4. Why is PostgreSQL included in Phase 0 even though no tables exist yet?
5. What is pgvector for?
6. What does a port mapping like `"8000:8000"` mean?
7. Why do we use environment variables instead of hardcoding everything?
8. Why should `.venv/`, `node_modules/`, and `__pycache__/` not be committed?

### Applied

9. When you open `http://localhost:5173`, which file renders the first UI?
10. Which file defines the backend FastAPI app?
11. Which line in the frontend tells it where the backend API is?
12. Which Compose service name does the backend use to reach PostgreSQL?
13. If the frontend says the API is unreachable, what are three things you would
    check first?
14. Why is CORS needed between `localhost:5173` and `localhost:8000`?
15. Why is it good that Gmail, Robinhood, and cloud services are disabled in V1?

### Deeper Understanding

16. Why should the frontend not connect directly to PostgreSQL?
17. Why is `create_app()` useful instead of only creating a global FastAPI app?
18. What is the difference between a Docker image and a Docker container?
19. What would break if the database did not use a persistent volume?
20. What does "local-first" mean for Argus?

### Agent Preview

21. In one sentence, what is an AI agent loop?
22. Why does an agent need tools?
23. Why should dangerous tools require permission checks?
24. Why will Argus need run traces and token/cost budgets later?
25. Why is a Research/Critic workflow more reliable than a single answer-only
    model call?

## Minimum Passing Bar

Before moving to Phase 1, you should be able to explain this flow without
looking:

```text
browser -> React frontend -> FastAPI backend -> PostgreSQL
```

And this Phase 0 flow:

```text
browser opens localhost:5173
-> frontend calls localhost:8000/health
-> backend returns JSON
-> frontend displays API status
```

If you can explain those two flows, you are ready to continue.

## Common Beginner Confusions

This section collects the concepts that are easy to miss when first reading
Phase 0.

### Docker Compose

Beginner definition:

```text
Docker Compose = a tool for starting multiple local services with one file
```

Argus is not one single program. It needs three programs to work together:

```text
frontend
backend
database
```

Without Docker Compose, you would need to start and configure them manually:

```text
1. Start PostgreSQL.
2. Make sure pgvector is available.
3. Start the FastAPI backend.
4. Start the React frontend.
5. Configure ports.
6. Configure environment variables.
7. Make sure backend can connect to database.
8. Make sure frontend can connect to backend.
```

Docker Compose stores that local wiring in `compose.yaml`, so the intended
developer workflow becomes:

```bash
docker compose up --build
```

Compose is not the investment research feature. It is local development
infrastructure.

### `/health`

`/health` is a backend health-check endpoint.

When you call:

```text
GET http://localhost:8000/health
```

the backend returns JSON like:

```json
{
  "status": "ok",
  "service": "argus-api",
  "version": "0.1.0",
  "mode": "development"
}
```

This proves:

- FastAPI can start;
- backend code can be imported;
- HTTP requests can reach the backend;
- backend can return typed JSON;
- frontend can use this endpoint to check whether the API is online.

It does not prove that database, RAG, reports, portfolio, or agents are done.
It only proves that the backend is alive.

### `localhost` and Ports

`localhost` means:

```text
this computer
```

The number after the colon is the port. A port is like a separate network door
on the same machine.

Argus uses:

```text
http://localhost:5173 -> React frontend
http://localhost:8000 -> FastAPI backend
localhost:5432        -> PostgreSQL database
```

These can all exist at the same time because they use different ports.

The main user-facing page is the frontend:

```text
http://localhost:5173
```

The backend is mostly for API calls:

```text
http://localhost:8000/health
```

### Why Three Services?

The services have different jobs:

```text
frontend service:
  pages, buttons, upload UI, tables, user interactions

backend service:
  API, validation, business logic, RAG, agent workflow, database reads/writes

postgres service:
  persistent storage for documents, evidence, reports, portfolio rows, runs
```

The basic full-stack flow is:

```text
user action -> frontend -> backend -> database
```

This separation makes the system easier to test, secure, and maintain.

### Why Frontend Should Not Connect Directly to Database

The frontend runs in the user's browser. If it connected directly to PostgreSQL,
the browser would need database access details.

That would create problems:

- database address could be exposed;
- database username/password could be exposed;
- users could bypass backend validation;
- permissions would be harder to enforce;
- business rules would be easier to break.

The safer architecture is:

```text
frontend -> backend -> database
```

The backend is the security and business-logic boundary in front of the
database.

### Why `.gitignore` Matters

Git should store source code, documentation, tests, and required configuration.
It should not store local generated files, dependency folders, private data, or
secrets.

Do not commit secrets:

```text
credentials.json
token.json
secrets/
```

Do not commit generated local folders:

```text
.venv/
node_modules/
__pycache__/
.pytest_cache/
```

Reasons:

- secrets can leak account access;
- dependency folders can be huge;
- generated files can be recreated;
- generated files can differ across machines;
- they make code review noisy.

### Better Definition of AI Agent Loop

A beginner version:

```text
The user asks a question. The LLM decides whether it needs a tool. If it does,
the system runs the tool, sends the tool result back to the LLM, and the LLM
continues until it can answer.
```

A more engineering-focused version:

```text
An AI agent loop is a controlled loop where a model decides whether to call
tools, the system executes allowed tools, tool results are appended back into
context, and the loop continues until a final answer, iteration limit, timeout,
or budget limit is reached.
```

Argus will later add engineering controls:

- tool dispatch;
- permission checks;
- retry and timeout handling;
- max iteration guards;
- token and cost budgets;
- run traces;
- citation validation.

So an agent is not just "an LLM with tools." In Argus, it should become a
bounded, observable execution system.

## Correction Quiz

Use this shorter quiz if the first quiz felt too broad.

1. What core problem does Docker Compose solve in Argus?
2. What does `localhost` mean?
3. Why can `localhost:5173` and `localhost:8000` both exist at the same time?
4. If `/health` returns JSON successfully, which part of the system is working?
5. Why does the backend connect to `postgres:5432` inside Docker Compose instead
   of `localhost:5432`?
6. Why should `.venv/` not be committed?
7. Why should `node_modules/` not be committed?
8. Why should `credentials.json` not be committed?
9. Why is `frontend -> backend -> database` safer than `frontend -> database`?
10. In one sentence, why does Argus split into frontend, backend, and database?
