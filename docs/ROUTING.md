# Model Routing

## Decision

Use sensitivity and capabilities as separate dimensions, implemented as ordered
filters rather than a manually enumerated matrix.

```text
request
-> sensitivity gate
-> capability filter
-> budget filter
-> quality/cost/latency ranking
-> selected profile
-> recorded selection reason
```

## Why One Dimension Is Not Enough

A simple `task_type -> model` mapping hides two different questions:

1. Is this model allowed to see the data?
2. Can this model reliably perform the task?

For example, `portfolio_explain` may require reasoning and structured output,
but the same task can contain public sample holdings or restricted real
holdings. Task type alone cannot enforce the privacy difference.

## Why Not Maintain a Full Matrix

A full sensitivity-by-capability-by-provider matrix grows quickly and duplicates
rules. Adding one capability or model requires editing many cells.

Instead:

- sensitivity policy defines allowed deployments;
- model profiles declare capabilities;
- the router computes the valid intersection;
- eval results and cost rank that intersection.

## Sensitivity Rules

| Sensitivity | Local | Cloud |
|---|---:|---:|
| Public | Allowed | Allowed |
| Internal, raw | Allowed | Denied |
| Internal, redacted | Allowed | Allowed by policy |
| Restricted | Allowed | Denied |

Payment-card data is not a supported Argus V1 sensitivity class. V1 should not
ingest, store, transmit, or process raw cardholder data.

## Capability Examples

- `extraction`
- `summarization`
- `tool_calling`
- `structured_output`
- `long_context`
- `reasoning`

Capabilities describe tested behavior, not vendor marketing. A profile should
only claim a capability after it passes the relevant evaluation cases.

## Auto Mode

`Auto` is the default model-selection mode. It does not mean "pick the most
powerful model." It means:

1. deny any model that cannot receive the data sensitivity;
2. deny any model that lacks required capabilities;
3. deny any model that would exceed the active budget;
4. rank remaining profiles by measured quality, expected cost, and latency;
5. record the selected profile and selection reason on the run.

Manual model override is allowed only inside the same policy constraints. A
manual choice cannot bypass sensitivity, budget, or capability checks.

## Evaluation Feedback

Routing quality should be maintained with measured results:

- golden-question pass/fail status;
- citation coverage;
- temporal consistency;
- latency;
- token usage;
- estimated cost;
- critic flag or downgrade count.

When a cheaper profile reaches the required quality threshold, `Auto` should
prefer it. When a more expensive profile materially improves measured quality,
`Auto` can select it and should record why.

## Routing Request

```python
RouteRequest(
    sensitivity=Sensitivity.INTERNAL,
    redacted=True,
    required_capabilities={
        Capability.TOOL_CALLING,
        Capability.STRUCTURED_OUTPUT,
    },
    max_cost_score=0.8,
)
```

## Interview Narrative

The useful design point is not “I supported many providers.” It is:

> I separated privacy admission from task fitness, then used measured quality,
> cost, and latency to select among only the admissible models.
