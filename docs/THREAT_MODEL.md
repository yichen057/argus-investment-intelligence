# Focused Threat Model

| Threat | Example | Control |
|---|---|---|
| Prompt injection | Email requests credential upload | Untrusted-content boundary, fixed permissions |
| Knowledge poisoning | Research document silently changes | Immutable versions, content hash, stale-report lookup |
| Temporal leakage | Future filing enters historical answer | Mandatory `as_of_date` filters and tests |
| Data disclosure | Holdings sent to cloud model | Restricted local-only gate |
| Citation laundering | News presented as primary evidence | Evidence grades and independent critic |
| Denial of wallet | Recursive agents exhaust budget | Parent-child token, cost, iteration, and deadline caps |
| Credential exposure | OAuth token committed to Git | Secret paths, `.gitignore`, local setup |
| Excessive agency | Agent attempts order placement | No brokerage-write tool; explicit prohibited list |

Retrieved documents, emails, and web pages are data. They cannot grant
permissions, alter routing policy, or authorize tool calls.

