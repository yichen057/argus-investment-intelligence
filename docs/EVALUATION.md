# Evaluation

## Current V1 Local Runner

Implemented entry points:

- CLI: `argus-eval`;
- API: `POST /eval/run`;
- dataset: `evals/golden_questions.yaml`;
- artifacts: JSON and Markdown under `eval-results/`.

The V1 runner is local and deterministic. It does not call cloud LLM APIs,
Gmail, Robinhood, or broker services. It runs local research, report,
portfolio, and prompt-injection fixture checks. Evaluation is intentionally kept out of
the user-facing Runs page because it is a developer maintenance action. The API uses the
current database and can create labeled test Runs and local artifacts; the
temporary-database command below avoids changing normal Runs.

Latest container run on 2026-07-20, using a temporary SQLite database:

| Metric | Measured value |
|---|---:|
| Golden cases | 12 |
| Passed | 11 |
| Partial | 1 |
| Failed | 0 |
| Citation coverage | 100% |
| Temporal consistency | 100% |
| Critic completion | 100% |
| Model calls | 14 |
| Tool calls | 7 |
| Token estimate | 2,393 |
| Estimated cost | USD 0.000000 |

The partial case is intentional: V1 checks prompt-injection fixtures as inert
text, but does not yet persist a dedicated security event. That check is
tracked as skipped rather than claimed as complete.

Run in the backend container without changing the normal Argus database or
calling paid APIs:

```bash
docker compose exec -T \
  -e ARGUS_DATABASE_URL=sqlite:////tmp/argus-eval-smoke.db \
  backend python -m investment_agent.evaluation.cli --no-save
```

The Compose backend mounts `evals/` and `examples/` read-only and mounts
`eval-results/` for generated artifacts. After changing these Compose mounts,
apply them with `docker compose up -d --force-recreate backend`.

Run locally against a named SQLite database:

```bash
ARGUS_DATABASE_URL=sqlite:////path/to/argus/local_argus.db \
  argus-eval
```

For a no-artifact smoke run:

```bash
ARGUS_DATABASE_URL=sqlite:////path/to/argus/local_argus.db \
  python -m investment_agent.evaluation.cli --no-save
```

## Cost-Capped Model Stage Benchmark

`argus-model-benchmark` is a separate, explicitly paid comparison runner. It
does not change the Research page's selected model or production routing. The
checked-in dataset is `evals/model_stage_benchmark.yaml`; every candidate sees
the same evidence and is scored separately for `evidence_extraction` and
`answer_synthesis`.

The runner requires an explicit model list and total USD ceiling. Before each
configured-provider call, it reserves a conservative maximum based on the
bounded 500-token output plus estimated prompt size. If that reservation would
cross the ceiling, the model is recorded as skipped and is not called.

After rebuilding the backend image and configuring only the keys you intend to
test, an example Docker run is:

```bash
docker compose exec backend argus-model-benchmark \
  --models deepseek/deepseek-v4-flash moonshot/kimi-k2.6 \
  --max-cost-usd 0.03
```

Optional candidates are explicit as well:

- `deepseek/deepseek-v4-pro` uses the configured DeepSeek credential;
- `openai/gpt-5.5` requires a separate OpenAI API key—ChatGPT subscription
  access is not reused;
- a future Kimi candidate remains disabled until its exact official API model
  ID and non-zero input/output prices are configured.

Artifacts are timestamped JSON and Markdown under `eval-results/` and include
dataset version, per-stage quality components, latency, token counts, estimated
cost, failures, skipped models, and recommendations. They are evaluation
artifacts, not database Runs and not automatic deployment decisions.

First bounded live comparison on 2026-07-17:

| Measurement | Result |
|---|---:|
| Cases × stages × models | 3 × 2 × 2 = 12 calls |
| Cost ceiling | USD 0.030000 |
| Total estimated cost | USD 0.007132 |
| Extraction quality | DeepSeek 0.950; Kimi 0.950 |
| Synthesis quality | DeepSeek 0.903; Kimi 0.921 |
| Synthesis supported-claim rate | DeepSeek 0.882; Kimi 0.928 |
| Recommendation under the declared near-tie rule | DeepSeek for both stages |

This tiny baseline partially supports stronger Kimi synthesis, but it does not
support a production two-provider pipeline yet. Expand the fixed set and repeat
runs before changing provider policy. The complete checked-in result is
[Model Stage Benchmark Baseline](MODEL_STAGE_BENCHMARK_BASELINE.md).

A separate six-call DeepSeek V4 Pro follow-up cost an estimated `$0.001944`.
Extraction quality/support averaged `0.906/0.889`; synthesis averaged
`0.621/0.614` and failed the declared stage thresholds. This negative result is
retained because it demonstrates why Argus selects by measured task score rather
than model tier or price.

## Month-One Dataset

Build approximately 20-25 cases:

- 5 direct source-retrieval cases;
- 4 historical `as_of_date` cases;
- 4 multi-source synthesis cases;
- 3 counter-evidence cases;
- 3 prompt-injection cases;
- 3 deterministic portfolio cases;
- 2 selected-skill cases.

## Metrics

| Metric | Month-one target |
|---|---:|
| Material-claim citation coverage | 100% |
| Citation precision | >= 90% baseline |
| Historical temporal consistency | 100% |
| Counter-evidence recall | >= 80% baseline |
| Injection fixture pass rate | 100% |
| Deterministic portfolio correctness | 100% |
| Median daily-brief cost | <= USD 0.10 |

Targets are not achievements. Store measured results with dataset version,
commit, provider profile, skill version, latency, and cost.

## Required Comparisons

1. Lexical retrieval versus hybrid retrieval.
2. Research-only versus Research + Evidence Critic.
3. All tool schemas versus lazy tool-schema loading.
4. Economy profile versus reasoning profile.

These comparisons create interview-ready engineering evidence rather than a
feature checklist.

## Regression Gate

Reject a change that:

- introduces temporal leakage;
- lowers citation coverage;
- changes deterministic portfolio results;
- allows an injection fixture to modify tool policy;
- raises benchmark cost by more than 20% without measured quality improvement.
