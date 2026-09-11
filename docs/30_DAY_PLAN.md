# 30-Day Learning and Build Plan

## Operating Rhythm

Budget: 30 days, about 2 hours per day, approximately 60 hours.

Daily structure:

```text
25-35 min  Learn one focused concept
70-80 min  Implement it in Argus
10-15 min  Test, measure, and write one interview decision note
```

The course is [Learn Claude Code](https://learn.shareai.run/en/), which currently
contains 19 chapters across Core Loop, System Hardening, Task Runtime, and
Multi-Agent Platform.

Do not extend a missed task indefinitely. Preserve the weekly demo and reduce
scope.

## Week 1: First-Party Harness

| Day | Learn | Build | Acceptance |
|---|---|---|---|
| 1 | Read project docs; define agent versus workflow | Initialize repo, run tests, write ADR-001 for modular monolith | Package imports; decision recorded |
| 2 | s01 Agent Loop | Implement mock model -> tool call -> tool result -> final response | Three-turn mock loop passes |
| 3 | s02 Tool Use | Implement typed ToolCall/ToolResult and registry | Unknown/denied tools fail explicitly |
| 4 | Provider abstraction and structured output | Implement provider profile and fake adapters | Same request runs on two fake profiles |
| 5 | Routing design | Implement sensitivity gate + capability filter + ranking | Restricted request never selects cloud |
| 6 | Budget engineering | Implement shared parent/child token and cost budget | Child charge propagates; cap halts run |
| 7 | s03 TodoWrite; weekly review | Persist a structured run plan and record baseline trace/cost fields | Week-one CLI demo and 5+ tests |

Interview focus: explain the loop, tool contract, routing trade-off, and why
budgets belong in control flow rather than prompts.

## Week 2: Sources, Gmail, and Evidence

| Day | Learn | Build | Acceptance |
|---|---|---|---|
| 8 | Connector/interface design | Implement `SourceConnector`, local file connector, fixtures | PDF/text source becomes RawSource |
| 9 | Gmail official quickstart and OAuth boundary | Configure local desktop OAuth; keep secrets outside Git | List message IDs locally |
| 10 | Gmail search, MIME, and attachments | Ingest body + allowed attachments from selected query/senders | 5-10 investment emails normalized |
| 11 | Immutable data and hashing | Implement DocumentVersion and EvidenceItem schema | Reingest is idempotent; changed content versions |
| 12 | RAG basics; review local RAG notes | Implement lexical retrieval with metadata filters | Relevant evidence IDs returned |
| 13 | Vector retrieval and reranking | Add embeddings/pgvector or a local fallback; compare with lexical | Small retrieval comparison recorded |
| 14 | Temporal retrieval | Enforce `as_of_date`; add one future-leak fixture | Temporal leakage test passes |

Interview focus: Gmail open-source constraints, evidence identity, idempotency,
chunking trade-offs, and time-correct retrieval.

## Week 3: Research, Critic, Skills, and Evals

| Day | Learn | Build | Acceptance |
|---|---|---|---|
| 15 | s04 Subagent | Add WorkRequest/WorkResult and isolated child context | Parent delegates to critic |
| 16 | Multi-agent evaluation boundary | Implement independent citation verification | Seeded unsupported claim is downgraded |
| 17 | s05 Skills | Implement cheap skill discovery and lazy body loading | Skill list does not load full text |
| 18 | Serenity or Gold/Macro | Complete one skill end to end; keep the other as protocol | First structured skill report |
| 19 | s06 Context Compact | Compact run history while preserving evidence IDs | Citations survive compaction |
| 20 | s09 Memory + s10 System Prompt | Separate persistent evidence from constructed prompt; cache stable prefix | Prompt sections and token counts visible |
| 21 | Evaluation-driven iteration | Build 12-15 golden cases and baseline metrics | JSON/Markdown eval report generated |

Interview focus: why a critic is a context boundary, shared evidence versus
shared chat memory, lazy loading, compaction invariants, and measured quality.

## Week 4: Hardening, Scheduling, Portfolio, and Multi-Agent Operations

| Day | Learn | Build | Acceptance |
|---|---|---|---|
| 22 | s07 Permission System | Implement deny/check/allow/ask policy pipeline | Restricted cloud route is denied |
| 23 | s08 Hooks + prompt injection | Add pre-tool and post-claim hooks; quarantine injection fixture | Injection cannot change permissions |
| 24 | s11 Error Recovery | Classify retryable, reroutable, approval, and terminal failures | Failure test resumes without duplicate paid work |
| 25 | Deterministic finance boundary | Implement concentration and target-drift calculations | Known numeric fixtures pass |
| 26 | s12 Task, s13 Background, s14 Cron | Model daily brief as durable task fed into the same loop | Manual scheduled-run simulation works |
| 27 | s15 Agent Teams + s16 Team Protocols | Implement request IDs, role identity, status, and bounded delegation | Research/Critic protocol trace complete |
| 28 | s17 Autonomous Agents + s18 Worktree Isolation | Add one bounded scan/claim/resume rule; document worktree use for development | No unbounded agent loop |
| 29 | s19 MCP & Plugin; observability | Expose or mock one MCP-ready tool; emit trace/cost/eval artifacts | End-to-end run has traceable stages |
| 30 | Final benchmark and interview rehearsal | Run 20-25 cases, update README with measured numbers, record demo, answer review questions | Reproducible demo and honest resume bullets |

## Multi-Agent Office Practice

Use multiple coding agents only for bounded, independent tasks:

- one agent implements routing while another writes routing tests;
- one agent researches Gmail edge cases while another implements fixtures;
- one agent writes a skill while another builds its evaluation cases.

Rules:

1. Give every agent a concrete output and disjoint file ownership.
2. Use request IDs and require a structured result.
3. Do not delegate the immediate blocking task.
4. Review and integrate every patch; agents do not approve their own work.
5. Record where parallelism reduced elapsed time and where it increased review
   cost.

This turns “multi-agent collaboration” into an engineering story rather than a
demo with many role names.

## Final Interview Checklist

Be able to whiteboard and defend:

- Why modular monolith before MCP services?
- Why sensitivity gating precedes capability selection?
- How does Gmail remain optional and open-source friendly?
- How does `as_of_date` work at the database filter level?
- How do content hashes invalidate affected reports?
- Why is the critic independent?
- What state survives context compaction?
- How do child budgets propagate?
- Which failures are retried, rerouted, or escalated?
- What measured result improved after adding the critic?
- What is deterministic code versus model interpretation?
- What would you redesign for 1,000 users?

