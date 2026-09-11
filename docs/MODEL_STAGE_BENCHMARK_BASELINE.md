# Model Stage Benchmark Baseline — 2026-07-17

This checked-in summary records the first live, cost-capped comparison of the
current DeepSeek and Kimi configurations. It is an evaluation result, not an
automatic production-routing decision.

- Dataset: `evals/model_stage_benchmark.yaml` version 1
- Models: `deepseek/deepseek-v4-flash`, `moonshot/kimi-k2.6`
- Design: 3 fixed cases × 2 stages × 2 models = 12 provider calls
- Configured ceiling: USD 0.030000
- Estimated token cost: USD 0.007132
- Maximum observed completion: 322 tokens (the current runner caps at 500)
- Actual provider dashboards remain authoritative for billing.

| Model | Stage | Case | Quality | Recall | Claim support | Organization | Latency | Estimated cost |
|---|---|---|---:|---:|---:|---:|---:|---:|
| DeepSeek V4 Flash | extraction | gold/real yields | 1.000 | 1.000 | 1.000 | 1.000 | 1,400 ms | $0.000071 |
| DeepSeek V4 Flash | synthesis | gold/real yields | 0.956 | 1.000 | 0.889 | 1.000 | 3,393 ms | $0.000115 |
| DeepSeek V4 Flash | extraction | portfolio concentration | 1.000 | 1.000 | 1.000 | 1.000 | 1,533 ms | $0.000073 |
| DeepSeek V4 Flash | synthesis | portfolio concentration | 0.943 | 1.000 | 0.857 | 1.000 | 3,325 ms | $0.000123 |
| DeepSeek V4 Flash | extraction | conflicting evidence | 0.850 | 0.667 | 1.000 | 1.000 | 1,757 ms | $0.000071 |
| DeepSeek V4 Flash | synthesis | conflicting evidence | 0.810 | 0.667 | 0.900 | 1.000 | 2,837 ms | $0.000129 |
| Kimi K2.6 | extraction | gold/real yields | 1.000 | 1.000 | 1.000 | 1.000 | 7,684 ms | $0.000703 |
| Kimi K2.6 | synthesis | gold/real yields | 0.964 | 1.000 | 0.909 | 1.000 | 10,135 ms | $0.001371 |
| Kimi K2.6 | extraction | portfolio concentration | 1.000 | 1.000 | 1.000 | 1.000 | 10,851 ms | $0.000713 |
| Kimi K2.6 | synthesis | portfolio concentration | 0.950 | 1.000 | 0.875 | 1.000 | 7,934 ms | $0.001309 |
| Kimi K2.6 | extraction | conflicting evidence | 0.850 | 0.667 | 1.000 | 1.000 | 4,600 ms | $0.000773 |
| Kimi K2.6 | synthesis | conflicting evidence | 0.850 | 0.667 | 1.000 | 1.000 | 11,983 ms | $0.001680 |

## Aggregate result

| Stage | DeepSeek Flash quality / support / cost | Kimi quality / support / cost | Recommendation |
|---|---|---|---|
| Evidence extraction | 0.950 / 1.000 / $0.000215 | 0.950 / 1.000 / $0.002189 | DeepSeek Flash |
| Answer synthesis | 0.903 / 0.882 / $0.000368 | 0.921 / 0.928 / $0.004360 | DeepSeek Flash under near-tie value rule |

Kimi's synthesis quality was 0.018 higher and its claim-support rate was 0.046
higher, so the user's qualitative observation has some measured support. The
difference remains inside the declared 0.03 near-tie band, while Kimi's measured
synthesis cost was about 12 times DeepSeek's on this set. The present decision is
therefore to keep explicit single-provider production routing and expand the
benchmark before introducing a two-provider pipeline.

## DeepSeek V4 Pro follow-up

The same versioned set then ran V4 Pro alone under a separate USD 0.01 ceiling.
Six calls cost an estimated USD 0.001944.

| Stage | Average quality | Average claim support | Total estimated cost | Gate result |
|---|---:|---:|---:|---|
| Evidence extraction | 0.906 | 0.889 | $0.000715 | Passed, but below Flash on this set |
| Answer synthesis | 0.621 | 0.614 | $0.001229 | Failed the quality/support gate |

This is a useful negative result: a more expensive or “Pro” model name does not
guarantee better adherence to this evidence-and-citation contract. Flash remains
the current recommendation. Because Pro was measured in a separate run and the
dataset is tiny, this is not a universal ranking; repeat it on the expanded set.

## Limitations

Three cases cannot establish universal model ability. This baseline needs more
Chinese and English questions, long sources, tables, web evidence, time cutoffs,
conflicting sources, and adversarial citation cases. Repeated runs are also needed
to measure provider variance. See `docs/EVALUATION.md` for the reproducible command,
scoring rule, cost guard, and candidate policy.
