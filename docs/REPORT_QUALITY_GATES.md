# Research Report Quality Gates / 研究报告质量门控

This document explains why Argus does not turn every Ask answer into an HTML
report and how each requirement is enforced in code. The backend report endpoint
is authoritative; the React checklist mirrors the same rules for usability.

本文说明为什么 Argus 不会把每条简短 Answer 都扩写成 HTML 报告，以及七条准入条件在
代码中分别如何实现。后端 `/reports/generate` 是最终裁决者，前端清单只是把同一套规则
提前解释给用户。

## End-to-end decision / 完整判断流程

```text
Completed Ask Run
    ↓
Evidence Gate: supported + report_eligible
    ↓
Accepted local passages and/or direct-URL web evidence
    ↓
Answer generated from accepted evidence only
    ↓
Citation validation or local Evidence Critic
    ↓
Structured Claim generation for indexed evidence
    ↓
Answer completeness and substantive-content check
    ↓
Render the stored Run as HTML (no second model call)
```

## 1. A completed Ask Run is required / 必须来自已完成的 Ask Run

Why / 依据：A report must be traceable to one exact question, model choice,
evidence scope, Method Pack composition, accepted evidence set, cost, and timestamp.
Generating from free text would break that audit chain.

How / 技术处理：

- The browser sends `source_run_id` to `POST /reports/generate`.
- `src/investment_agent/api/reports.py` loads that Run from `AgentRunRepository`.
- A missing Run returns `404`; a Run without `status == "complete"` returns `422`.
- The report reuses the answer and evidence stored in Run metadata/repositories.
  It does not call Gemini, DeepSeek, or Kimi again.

## 2. Evidence Gate must support reporting / Evidence Gate 必须通过

Why / 依据：Retrieval rank only means “possibly relevant.” It does not prove that
a passage directly answers the question. One shared Gate prevents search, answer,
citation, and report code from using different definitions of sufficient evidence.

How / 技术处理：

- `EvidenceGate.evaluate()` examines complete candidate passages, not only titles or
  similarity scores.
- It rejects passages that do not directly overlap the requested claim or that fail
  requested-year coverage.
- The decision is one of `supported`, `gap`, or `refuse` and is persisted in the Run.
- `report_eligible` is evidence-level depth: accepted CSV data, at least two accepted
  passages, at least 18 word-like tokens, or at least 24 Chinese characters.
- A named gap can trigger at most one bounded follow-up search. A final gap becomes
  refusal rather than an open-ended paid loop.

Important distinction / 重要区别：`report_eligible=true` only says the evidence is
deep enough to continue. The final answer must still pass citation, critic, Claim,
and completeness checks.

## 3. Web evidence needs direct URLs and valid citations / 网页证据必须可追溯

Why / 依据：A model saying “according to research” is not verifiable. The reader
needs a real URL and the system must prove that the answer used only IDs Argus issued.

How / 技术处理：

- The Exa adapter accepts only `http` or `https` URLs with a host.
- Results without extractable passages are discarded; duplicate URLs and near-duplicate
  passages from the same host are removed.
- Accepted sources receive bounded IDs such as `W1` and are passed to the answer model.
- The answer must cite `[source:W1]`-style IDs. `_citation_status()` rejects missing,
  unknown, or malformed IDs.
- A failed citation check changes `report_eligible` to false even if the prose looks good.

## 4. Indexed evidence needs passages, Claims, and a passing Critic / 本地证据审查

Why / 依据：An indexed answer needs both a human-readable passage and a machine-
auditable statement-to-source relationship. Mere keyword overlap is not enough.

How / 技术处理：

- The retrieval result retains evidence ID, document, page/section, and excerpt.
- `ClaimGenerator` normalizes a supported sentence and maps its `evidence_ids` with
  the relation `supports`.
- `EvidenceCritic` fails or warns on empty answers, no-evidence responses, missing
  sources, truncated fragments, and weak key-term overlap between answer and excerpts.
- Only `critic.status == "passed"`, at least one accepted source, and at least one
  structured Claim satisfy the indexed-report path.

## 5. The answer must be complete / 答案不能是残句或碎片

Why / 依据：Earlier versions produced reports that repeated one broken PDF fragment
across multiple headings. A source can be relevant while the extracted answer is still
unreadable or unfinished.

How / 技术处理：`research/quality.py` rejects:

- empty answers and the standard no-evidence refusal;
- answers ending in `...`;
- text containing four or more pipe separators, a common broken-table symptom;
- answers ending with a dangling connector such as `and`, `because`, `with`, `of`,
  or `from`.

## 6. The answer must be substantive / 答案必须有实质内容

Why / 依据：A grammatically complete one-line extract is useful in Ask but too thin
for a multi-section research brief.

How / 技术处理：after removing the local-answer prefix and normalizing whitespace,
`is_substantive_report_answer()` accepts:

- at least 24 Chinese characters; or
- at least 24 English/number word tokens; or
- at least two completed sentences and at least 18 word tokens.

These are deterministic minimums, not a claim that word count proves research quality.
Evidence, citation, and critic gates still apply independently.

## 7. Structured CSV is a depth exception / 结构化 CSV 特例

Why / 依据：A compact table may contain enough auditable data for charts and analysis
without naturally producing long prose during the initial Ask.

How / 技术处理：

- CSV ingestion validates readable rows and preserves structured layout.
- The Evidence Gate can mark accepted CSV evidence report-eligible immediately.
- On the indexed path, a non-empty accepted CSV source can satisfy the substantive-
  answer depth exception.
- It does **not** bypass the completed Run, accepted source, Claim, or Critic checks.

## Frontend versus backend / 前后端职责

`frontend/src/App.tsx` calculates the same route-specific readiness list so the user
can see the failed condition before clicking. A disabled button is not a security or
quality boundary: `src/investment_agent/api/reports.py` repeats all authoritative
checks because API clients can bypass the browser.

## What this guarantees—and what it does not / 能保证什么

The gates guarantee traceability, minimum completeness, bounded evidence support,
and refusal of known broken-output patterns. They do not prove that a source is true,
that an investment conclusion is suitable for a person, or that the report predicts
future returns. Those remain source-quality, analysis, and suitability questions.
